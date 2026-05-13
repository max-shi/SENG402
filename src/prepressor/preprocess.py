"""
preprocess — Unified API documentation corpus builder.

Replaces the old `preprocessor.py` (Java) and `preprocessor_python.py`
scripts. Language-specific rules (HTML stripping, AST walking, etc.) live
in `extractor_java.py` and `extractor_python.py`; this driver handles all
shared logic: discovery, chunk filtering, per-library concatenation,
output writing, and logging.

Usage:
    python preprocess.py                    # both java and python
    python preprocess.py --lang java        # java only
    python preprocess.py --lang python      # python only
    python preprocess.py --min-words 10     # override chunk floor
    python preprocess.py --libraries 1      # only first library
    python preprocess.py --libraries 3-4   # only libraries 3 and 4 (1-indexed)

Outputs (per language <lang>):
    files/preprocess/preprocess_output_{timestamp}/{lang}/<lang>_chunks.csv
    files/preprocess/preprocess_output_{timestamp}/{lang}/<lang>_libraries.csv
    files/preprocess/preprocess_output_{timestamp}/{lang}/preprocess_<lang>.csv
"""

from __future__ import annotations

import argparse
import csv
import importlib
import logging
import re
from datetime import datetime
from pathlib import Path
from types import ModuleType

# ---------------------------------------------------------------------------
# Shared configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
OUTPUT_BASE_DIR = _HERE.parent.parent / "files" / "preprocess"

MIN_CHUNK_WORDS = 10          # drop chunks shorter than this (post-clean)
JOIN_SEP = " "                 # separator between concatenated chunks
SENTENCE_TERMINATORS = ".!?"   # chunks not ending in one of these get a "."

CHUNK_COLUMNS = [
    "library",
    "ecosystem",
    "domain",
    "organisation",
    "javadoc_version",
    "source_file",
    "class_name",
    "section_type",
    "element_id",
    "n_words",
    "text",
    "text_html",
]

LIBRARY_COLUMNS = [
    "library",
    "ecosystem",
    "domain",
    "organisation",
    "n_chunks",
    "n_words",
    "text",
]

LOG_COLUMNS = [
    "timestamp", "library", "source_file",
    "chunks_extracted", "chunks_kept", "status", "error",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def load_libraries(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        return list(reader)


def clean_text(raw: str) -> str:
    """Collapse whitespace and drop trivially short lines.

    Mirrors the cleaning the old preprocessor.py did so that Java and Python
    chunks go through the same final polish step.
    """
    text = re.sub(r"[ \t]+", " ", raw)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 2:
            lines.append(line)
    return " ".join(lines)


def ensure_terminator(text: str) -> str:
    """Append a period if the chunk doesn't end in a sentence terminator.

    Ensures LIWC sees clean sentence boundaries when chunks are concatenated.
    """
    if not text:
        return text
    if text[-1] in SENTENCE_TERMINATORS:
        return text
    return text + "."


def word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def parse_library_range(value: str) -> tuple[int, int]:
    """Parse a libraries argument like '3' or '3-4' into a (start, end) 1-indexed range."""
    if "-" in value:
        parts = value.split("-", 1)
        return int(parts[0]), int(parts[1])
    n = int(value)
    return n, n


def run_language(extractor: ModuleType, min_words: int,
                run_dir: Path,
                library_range: tuple[int, int] | None = None) -> None:
    ecosystem = extractor.ECOSYSTEM
    libraries = load_libraries(extractor.LIBRARIES_CSV)
    libraries = [lib for lib in libraries
                 if lib.get("ecosystem", "").strip().lower() == ecosystem]

    if library_range is not None:
        start, end = library_range
        libraries = libraries[start - 1:end]
        log.info("[%s] restricting to libraries %d\u2013%d (%d total)",
                 ecosystem, start, end, len(libraries))

    eco_dir = run_dir / ecosystem
    eco_dir.mkdir(parents=True, exist_ok=True)

    chunks_csv = eco_dir / f"{ecosystem}_chunks.csv"
    library_csv = eco_dir / f"{ecosystem}_libraries.csv"
    log_csv = eco_dir / f"preprocess_{ecosystem}.csv"

    total_chunks_kept = 0

    with (
        open(chunks_csv, "w", newline="", encoding="utf-8") as chunks_f,
        open(library_csv, "w", newline="", encoding="utf-8") as lib_f,
        open(log_csv, "w", newline="", encoding="utf-8") as log_f,
    ):
        chunk_writer = csv.DictWriter(chunks_f, fieldnames=CHUNK_COLUMNS)
        chunk_writer.writeheader()

        lib_writer = csv.DictWriter(lib_f, fieldnames=LIBRARY_COLUMNS)
        lib_writer.writeheader()

        log_writer = csv.DictWriter(log_f, fieldnames=LOG_COLUMNS)
        log_writer.writeheader()

        for library_meta in libraries:
            name = library_meta["name"].strip()
            files = list(extractor.discover_files(library_meta))

            if not files:
                log.warning("[%s] no source files for library '%s' — skipping",
                            ecosystem, name)
                log_writer.writerow({
                    "timestamp": datetime.now().isoformat(),
                    "library": name, "source_file": "",
                    "chunks_extracted": 0, "chunks_kept": 0,
                    "status": "SKIP", "error": "no source files",
                })
                continue

            log.info("[%s] '%s': %d source files", ecosystem, name, len(files))

            # Per-library buffers
            lib_concat_parts: list[str] = []
            lib_chunk_count = 0
            lib_word_count = 0

            for file_path in files:
                # rel path: handled by extractors internally for the log;
                # use file_path.name fallback if not under RAW_DIR (shouldn't happen).
                try:
                    rel = str(file_path.relative_to(extractor.RAW_DIR))
                except ValueError:
                    rel = str(file_path)

                try:
                    raw_chunks = extractor.extract_chunks(file_path, library_meta)
                except Exception as exc:  # noqa: BLE001 — keep pipeline going
                    log.exception("[%s] error extracting %s", ecosystem, rel)
                    log_writer.writerow({
                        "timestamp": datetime.now().isoformat(),
                        "library": name, "source_file": rel,
                        "chunks_extracted": 0, "chunks_kept": 0,
                        "status": "ERROR", "error": str(exc),
                    })
                    continue

                kept = 0
                for ch in raw_chunks:
                    cleaned = clean_text(ch.get("text", ""))
                    n = word_count(cleaned)
                    if n < min_words:
                        continue

                    extra = ch.get("extra", {}) or {}
                    row = {
                        "library": name,
                        "ecosystem": ecosystem,
                        "domain": library_meta.get("domain", "").strip(),
                        "organisation": library_meta.get("organisation", "").strip(),
                        "javadoc_version": extra.get("javadoc_version", "n/a"),
                        "source_file": rel,
                        "class_name": ch.get("class_name", ""),
                        "section_type": ch.get("section_type", ""),
                        "element_id": ch.get("element_id", ""),
                        "n_words": n,
                        "text": cleaned,
                        "text_html": ch.get("text_html", ""),
                    }
                    chunk_writer.writerow(row)
                    kept += 1

                    lib_concat_parts.append(ensure_terminator(cleaned))
                    lib_word_count += n

                lib_chunk_count += kept

                status = "OK" if kept else "EMPTY"
                log_writer.writerow({
                    "timestamp": datetime.now().isoformat(),
                    "library": name, "source_file": rel,
                    "chunks_extracted": len(raw_chunks),
                    "chunks_kept": kept,
                    "status": status, "error": "",
                })

            # Write the per-library concatenated row
            lib_writer.writerow({
                "library": name,
                "ecosystem": ecosystem,
                "domain": library_meta.get("domain", "").strip(),
                "organisation": library_meta.get("organisation", "").strip(),
                "n_chunks": lib_chunk_count,
                "n_words": lib_word_count,
                "text": JOIN_SEP.join(lib_concat_parts),
            })
            total_chunks_kept += lib_chunk_count
            log.info("[%s] '%s' done: %d chunks kept, %d words concatenated",
                     ecosystem, name, lib_chunk_count, lib_word_count)
            log_f.flush()

    log.info("[%s] complete: %d chunks \u2192 %s", ecosystem, total_chunks_kept, chunks_csv)
    log.info("[%s] per-library corpus \u2192 %s", ecosystem, library_csv)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

EXTRACTORS = {
    "java": "extractor_java",
    "python": "extractor_python",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--lang", choices=["java", "python", "all"], default="all",
        help="Which ecosystem to preprocess (default: all)",
    )
    parser.add_argument(
        "--min-words", type=int, default=MIN_CHUNK_WORDS,
        help=f"Drop chunks with fewer than this many words "
             f"(default: {MIN_CHUNK_WORDS})",
    )
    parser.add_argument(
        "--libraries",
        help="Process only a specific library or range, e.g. '1' or '3-4' (1-indexed)",
    )
    args = parser.parse_args()

    library_range = parse_library_range(args.libraries) if args.libraries else None

    timestamp = datetime.now().strftime("%d-%m-%y_%H-%M-%S")
    run_dir = OUTPUT_BASE_DIR / f"preprocess_output_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", run_dir)

    targets = list(EXTRACTORS) if args.lang == "all" else [args.lang]
    for lang in targets:
        extractor = importlib.import_module(EXTRACTORS[lang])
        run_language(extractor, min_words=args.min_words,
                     run_dir=run_dir, library_range=library_range)


if __name__ == "__main__":
    main()
