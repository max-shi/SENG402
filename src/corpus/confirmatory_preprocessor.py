"""
confirmatory_preprocessor — Extract prose text from cloned libraries and
apply F5 (word count) and F6 (English language) filters.

Reads:
    files/corpus/frame_YYYYMMDD/sample_manifest.csv
        Only rows with role='primary' and status starting with
        'primary_cloned' are processed. Cloner + preprocessor form a
        two-step loop: any reserves promoted here are picked up by the
        next cloner run, then re-processed on the next preprocessor run.

For each cloned repository, this script:
    1. Walks the clone tree for prose files (README*, docs/**, doc/**,
       documentation/**) with prose extensions (.md, .rst, .txt, .adoc,
       .asciidoc, .html). Skips CHANGELOG/LICENSE/CONTRIBUTING and
       anything under .git/, node_modules/, vendor/.
    2. Extracts plain-text prose from each file according to its format
       (markdown -> HTML -> text; RST -> HTML -> text; HTML via
       BeautifulSoup; adoc/txt via light regex cleanup). Strips code
       blocks, HTML tags, and boilerplate.
    3. Concatenates the cleaned prose (files in a stable alphabetical
       order for reproducibility).
    4. Counts whitespace-separated tokens. Applies:
         F5: word_count_post_clean >= 500        (fail: primary_failed_f5)
         100k word cap: truncate to first 100k tokens, set word_capped
         F6: dominant paragraph language is English (>=50% by langdetect)
                                                  (fail: primary_failed_f6)
    5. Writes the cleaned text (post-cap) to:
           files/corpus/frame_YYYYMMDD/text/<eco>/<safe_name>.txt
    6. Records outcome in preprocess_log.csv and updates the manifest.

Failed rows (F5/F6) are appended to exclusion_log.csv under stage
'preprocess'. After the pass, reserves are promoted in draw_order to
fill vacated primary slots; those newly promoted rows need to be
cloned by re-running confirmatory_cloner.py, then this script again.

Usage:
    venv/bin/python3 src/corpus/confirmatory_preprocessor.py [--freeze-date YYYYMMDD]
                                                             [--lang java|python|all]
                                                             [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# --- Third-party --------------------------------------------------------
import markdown as md
from bs4 import BeautifulSoup
from docutils.core import publish_parts
from docutils.utils import SystemMessage
from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0   # deterministic language detection

# --- Reuse the pilot's pause helper -------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "crawl-clone"))
from pause_helper import PauseController  # noqa: E402

CORPUS_DIR = ROOT / "files" / "corpus"
CLONE_ROOT = ROOT / "files" / "raw" / "confirmatory"

WORD_MIN = 500                 # F5 threshold
WORD_CAP = 100_000             # §7.6.5 per-library cap
ENGLISH_MIN_FRACTION = 0.5     # F6 threshold
LANG_SAMPLE_PARAGRAPHS = 200   # cap on paragraphs sent to langdetect
LANG_MIN_TOKENS = 5            # skip too-short paragraphs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Silence chatty docutils warnings on malformed RST.
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("docutils").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

DOC_DIR_NAMES = {"docs", "doc", "documentation"}
# Also match directories with a doc-family prefix and an explicit
# suffix, e.g. `documentation_builder`, `docs_source`, `doc-src`,
# `docs_v2`. Uses a regex so we don't accidentally match `docker`,
# `document_processor`, `docx*`, `docstring*`, etc.
_DOCS_DIR_RE = re.compile(r"^(docs?|documentation)[-_].+$", re.IGNORECASE)


def _is_docs_dir(name: str) -> bool:
    n = name.lower()
    if n in DOC_DIR_NAMES:
        return True
    return bool(_DOCS_DIR_RE.match(n))
PROSE_EXT_MD = {".md", ".markdown", ".mdown", ".mkd"}
PROSE_EXT_RST = {".rst"}
PROSE_EXT_HTML = {".html", ".htm"}
PROSE_EXT_ADOC = {".adoc", ".asciidoc"}
PROSE_EXT_TXT = {".txt"}
PROSE_EXT_IPYNB = {".ipynb"}
PROSE_EXTS = (
    PROSE_EXT_MD | PROSE_EXT_RST | PROSE_EXT_HTML
    | PROSE_EXT_ADOC | PROSE_EXT_TXT | PROSE_EXT_IPYNB
)

# Filenames (case-insensitive, stem only) to always skip.
SKIP_STEM_PATTERNS = (
    "changelog", "changes", "history", "release-notes", "releasenotes",
    "license", "licence", "notice", "copying", "authors", "contributors",
    "code_of_conduct", "code-of-conduct", "codeofconduct",
    "contributing", "security", "governance", "maintainers",
    "support", "funding",
)

# Path segments that are always excluded (auxiliary trees).
IGNORE_HARD = {
    ".git", ".github", ".idea", ".vscode",
    "node_modules", "vendor", "target", "build", "dist",
    "__pycache__", ".tox", ".venv", "venv", "site-packages",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".eggs",
}

# Path segments to skip UNLESS the file is inside a docs/-family tree.
# (Example: `docs/examples/tutorial.rst` is legitimate documentation and
# should be kept; `examples/foo.py` at the repo root is code and should
# be excluded.)
IGNORE_SOFT = {
    "test", "tests", "testdata", "test-data", "fixtures",
    "example", "examples", "sample", "samples", "demo", "demos",
    "benchmark", "benchmarks", "conftest",
}


def find_prose_files(clone_dir: Path) -> list[Path]:
    """Return a stable, sorted list of prose files under `clone_dir`."""
    if not clone_dir.is_dir():
        return []
    out: list[Path] = []
    for path in clone_dir.rglob("*"):
        if not path.is_file():
            continue
        parts_lower = [p.lower() for p in path.parts]
        if any(seg in IGNORE_HARD for seg in parts_lower):
            continue

        stem_lower = path.stem.lower()
        if any(pat in stem_lower for pat in SKIP_STEM_PATTERNS):
            continue

        in_docs_tree = any(_is_docs_dir(p) for p in parts_lower)

        # Outside a docs tree, apply the softer test/example/etc. filter.
        if not in_docs_tree and any(seg in IGNORE_SOFT for seg in parts_lower):
            continue

        ext = path.suffix.lower()

        # README*: keep regardless of extension (README, README.md, README.rst, ...)
        if stem_lower.startswith("readme"):
            if ext in PROSE_EXTS or ext == "":
                out.append(path)
                continue

        # Files under a docs/-family directory (any depth).
        if in_docs_tree and ext in PROSE_EXTS:
            out.append(path)

    out.sort(key=lambda p: str(p).lower())
    return out


# ---------------------------------------------------------------------------
# Prose extraction per format
# ---------------------------------------------------------------------------

def _html_to_text(html_str: str) -> str:
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup(["code", "pre", "script", "style", "nav", "footer",
                     "aside", "form", "figure"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _normalise_whitespace(text)


def _md_to_text(md_str: str) -> str:
    try:
        html = md.markdown(md_str, extensions=["fenced_code", "tables",
                                               "sane_lists"])
    except Exception:
        html = md_str
    return _html_to_text(html)


def _rst_to_text(rst_str: str) -> str:
    try:
        parts = publish_parts(
            source=rst_str,
            writer_name="html5",
            settings_overrides={
                "report_level": 5,
                "halt_level": 5,
                "warning_stream": None,
                "embed_stylesheet": False,
                "doctitle_xform": False,
                "sectsubtitle_xform": False,
                "input_encoding": "utf-8",
                "output_encoding": "unicode",
            },
        )
        return _html_to_text(parts.get("html_body", ""))
    except (SystemMessage, Exception):
        return _strip_rst_regex(rst_str)


_RST_DIRECTIVE_RE = re.compile(
    r"^\.\.\s+[A-Za-z_][\w-]*::.*(?:\n(?:[ \t]+.*|\s*$))*",
    re.MULTILINE,
)
_RST_ROLE_RE = re.compile(r":[a-z]+:`([^`]+)(?:\s*<[^>]+>)?`", re.IGNORECASE)
_RST_LITERAL_RE = re.compile(r"``([^`]+)``")
_RST_UNDERLINE_RE = re.compile(r"^([=\-~^\"'`*+#]{3,})\s*$", re.MULTILINE)


def _strip_rst_regex(text: str) -> str:
    text = _RST_DIRECTIVE_RE.sub("", text)
    text = _RST_ROLE_RE.sub(r"\1", text)
    text = _RST_LITERAL_RE.sub(r"\1", text)
    text = _RST_UNDERLINE_RE.sub("", text)
    return _normalise_whitespace(text)


_ADOC_ATTRIBUTE_RE = re.compile(r"^:[\w-]+:\s*.*$", re.MULTILINE)
_ADOC_MACRO_RE = re.compile(r"\w+:[^\s\[]+\[[^\]]*\]")
_ADOC_HEADER_RE = re.compile(r"^=+\s+", re.MULTILINE)


def _adoc_to_text(text: str) -> str:
    text = _ADOC_ATTRIBUTE_RE.sub("", text)
    text = _ADOC_MACRO_RE.sub("", text)
    text = _ADOC_HEADER_RE.sub("", text)
    return _normalise_whitespace(text)


def _txt_to_text(text: str) -> str:
    return _normalise_whitespace(text)


def _ipynb_to_text(nb_str: str) -> str:
    """Extract prose from a Jupyter notebook: markdown cells only."""
    try:
        nb = json.loads(nb_str)
    except json.JSONDecodeError:
        return ""
    parts: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        if not isinstance(src, str):
            continue
        parts.append(src)
    if not parts:
        return ""
    return _md_to_text("\n\n".join(parts))


_MULTI_BLANK_RE = re.compile(r"\n\s*\n\s*(?:\n\s*)+")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")


def _normalise_whitespace(text: str) -> str:
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def extract_prose(path: Path) -> str:
    """Read `path` and return cleaned prose (empty string on failure)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    ext = path.suffix.lower()
    if ext in PROSE_EXT_MD or (ext == "" and path.stem.lower().startswith("readme")):
        return _md_to_text(raw)
    if ext in PROSE_EXT_RST:
        return _rst_to_text(raw)
    if ext in PROSE_EXT_HTML:
        return _html_to_text(raw)
    if ext in PROSE_EXT_ADOC:
        return _adoc_to_text(raw)
    if ext in PROSE_EXT_IPYNB:
        return _ipynb_to_text(raw)
    return _txt_to_text(raw)


# ---------------------------------------------------------------------------
# Word counting, capping, language detection
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return text.split()


def apply_word_cap(text: str, cap: int = WORD_CAP) -> tuple[str, int, bool]:
    """Return (text, word_count_post_cap, was_capped)."""
    tokens = tokenize(text)
    if len(tokens) <= cap:
        return text, len(tokens), False
    return " ".join(tokens[:cap]), cap, True


def english_fraction(text: str) -> tuple[float, int]:
    """
    Return (english_fraction, paragraphs_checked). Empty or unreliable
    inputs return (0.0, 0).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return 0.0, 0

    # Even-stride sampling across the document to avoid front-heavy bias.
    if len(paragraphs) > LANG_SAMPLE_PARAGRAPHS:
        step = len(paragraphs) / LANG_SAMPLE_PARAGRAPHS
        sampled = [paragraphs[int(i * step)] for i in range(LANG_SAMPLE_PARAGRAPHS)]
    else:
        sampled = paragraphs

    en, total = 0, 0
    for p in sampled:
        if len(p.split()) < LANG_MIN_TOKENS:
            continue
        total += 1
        try:
            langs = detect_langs(p)
            if langs and langs[0].lang == "en":
                en += 1
        except LangDetectException:
            continue
    if total == 0:
        return 0.0, 0
    return en / total, total


# ---------------------------------------------------------------------------
# Manifest / exclusion-log I/O and reserve promotion
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_")


def load_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path) as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def save_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


N_TARGET = 200


def promote_reserves(rows: list[dict]) -> int:
    """
    Same reserve-promotion policy as confirmatory_cloner.promote_reserves.
    A row is 'eligible' if its status doesn't start with 'primary_failed',
    'reserve_failed', or 'primary_excluded' (the F7 manual-exclusion
    marker). The first N_TARGET eligible rows (in draw_order) per
    ecosystem are marked primary; the rest reserve.
    """
    promoted = 0
    for eco in ("python", "java"):
        eco_rows = sorted(
            (r for r in rows if r["ecosystem"] == eco),
            key=lambda r: int(r["draw_order"]),
        )
        primaries: list[dict] = []
        reserves: list[dict] = []
        for r in eco_rows:
            s = r.get("status", "")
            if (s.startswith("primary_failed")
                    or s.startswith("reserve_failed")
                    or s.startswith("primary_excluded")):
                continue
            if len(primaries) < N_TARGET:
                primaries.append(r)
            else:
                reserves.append(r)

        for r in primaries:
            if r["role"] != "primary":
                r["role"] = "primary"
                if not r["status"].startswith("primary_"):
                    r["status"] = "primary_pending_promoted_from_reserve"
                promoted += 1
        for r in reserves:
            if r["role"] != "reserve":
                r["role"] = "reserve"
                r["status"] = "reserve_pending_demoted_from_primary"
    return promoted


# ---------------------------------------------------------------------------
# Per-library processing
# ---------------------------------------------------------------------------

PREPROC_LOG_COLS = [
    "timestamp", "package_name", "ecosystem", "safe_name",
    "n_prose_files", "raw_char_count", "word_count_post_clean",
    "word_capped", "english_fraction", "paragraphs_checked",
    "status", "reason",
]


def process_library(row: dict, text_root: Path) -> dict:
    """
    Extract prose, count/cap words, detect language, and write the
    per-library text file if F5+F6 pass. Returns a dict for the
    preprocess log with the outcome; also mutates `row` in-place with
    word_count_post_clean, word_capped, and status.
    """
    pkg = row["package_name"]
    eco = row["ecosystem"]
    sname = safe_name(pkg)
    clone_dir = CLONE_ROOT / eco / sname

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_name": pkg, "ecosystem": eco, "safe_name": sname,
        "n_prose_files": 0, "raw_char_count": 0,
        "word_count_post_clean": 0, "word_capped": "false",
        "english_fraction": 0.0, "paragraphs_checked": 0,
        "status": "", "reason": "",
    }

    if not clone_dir.is_dir():
        entry["status"] = "clone_missing"
        entry["reason"] = f"clone dir not found: {clone_dir}"
        row["status"] = "primary_failed_f4"  # treat missing clone as F4
        return entry

    files = find_prose_files(clone_dir)
    entry["n_prose_files"] = len(files)

    # Extract in stable order until we hit the word cap. This means we
    # avoid loading huge repos entirely.
    chunks: list[str] = []
    running_words = 0
    raw_chars = 0
    for path in files:
        text = extract_prose(path)
        if not text:
            continue
        chunks.append(text)
        raw_chars += len(text)
        running_words += len(text.split())
        # Stop early if far beyond the cap to save time on huge repos.
        if running_words > WORD_CAP * 2:
            break

    entry["raw_char_count"] = raw_chars

    if not chunks:
        entry["status"] = "F5_fail"
        entry["reason"] = "no prose files extracted"
        row["status"] = "primary_failed_f5"
        row["word_count_post_clean"] = "0"
        row["word_capped"] = "false"
        return entry

    combined = "\n\n".join(chunks)
    capped_text, wc, was_capped = apply_word_cap(combined)
    entry["word_count_post_clean"] = wc
    entry["word_capped"] = "true" if was_capped else "false"
    row["word_count_post_clean"] = str(wc)
    row["word_capped"] = "true" if was_capped else "false"

    if wc < WORD_MIN:
        entry["status"] = "F5_fail"
        entry["reason"] = f"word_count_post_clean={wc} < {WORD_MIN}"
        row["status"] = "primary_failed_f5"
        return entry

    frac, checked = english_fraction(capped_text)
    entry["english_fraction"] = round(frac, 3)
    entry["paragraphs_checked"] = checked

    if checked > 0 and frac < ENGLISH_MIN_FRACTION:
        entry["status"] = "F6_fail"
        entry["reason"] = f"english_fraction={frac:.2f} < {ENGLISH_MIN_FRACTION}"
        row["status"] = "primary_failed_f6"
        return entry
    if checked == 0:
        # Nothing detectable; conservative: fail F6 to avoid noise.
        entry["status"] = "F6_fail"
        entry["reason"] = "no paragraphs long enough to language-detect"
        row["status"] = "primary_failed_f6"
        return entry

    # Success — write the text file.
    dest = text_root / eco / f"{sname}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(capped_text, encoding="utf-8")

    entry["status"] = "ready"
    row["status"] = "primary_ready"
    return entry


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def reset_preprocess_state(rows: list[dict], excl_rows: list[dict]) -> int:
    """
    Revert F5/F6 exclusions and their reserve promotions so a subsequent
    pass can retry those libraries. Used by --retry-failed after a bug
    fix or threshold change. Idempotent.
    """
    n = 0
    for r in rows:
        s = r.get("status", "")
        if s.startswith("primary_failed_f5") or s.startswith("primary_failed_f6"):
            r["status"] = "primary_cloned"
            r["word_count_post_clean"] = ""
            r["word_capped"] = ""
            n += 1
    # Undo promotions so promote_reserves can redo the assignment.
    for r in rows:
        if r.get("status", "") == "primary_pending_promoted_from_reserve":
            r["role"] = "reserve"
            r["status"] = "reserve_pending"
    # Remove preprocess-stage exclusions so the log stays consistent.
    excl_rows[:] = [r for r in excl_rows if r.get("stage") != "preprocess"]
    promote_reserves(rows)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--lang", choices=["java", "python", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N libraries (for smoke tests).")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Revert primary_failed_f5/f6 rows to primary_cloned "
                         "and re-process them (undoes prior preprocess-stage "
                         "exclusions and reserve promotions).")
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    excl_path = frame_dir / "exclusion_log.csv"
    preproc_log_path = frame_dir / "preprocess_log.csv"
    text_root = frame_dir / "text"

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    fieldnames, rows = load_csv(manifest_path)
    excl_fields, excl_rows = load_csv(excl_path)

    if args.retry_failed:
        n_reset = reset_preprocess_state(rows, excl_rows)
        log.info("--retry-failed: reset %d F5/F6 rows to primary_cloned; "
                 "undone reserve promotions; cleared preprocess-stage "
                 "exclusion-log entries.", n_reset)

    ecosystems: Iterable[str] = ("java", "python") if args.lang == "all" else (args.lang,)

    # Rows to process: primaries currently at status starting with 'primary_cloned'
    # and whose word_count_post_clean is still empty (meaning we haven't
    # preprocessed them yet).
    todo = [
        r for r in rows
        if r["ecosystem"] in ecosystems
        and r["role"] == "primary"
        and r["status"].startswith("primary_cloned")
        and not r.get("word_count_post_clean", "").strip()
    ]
    if args.limit > 0:
        todo = todo[:args.limit]

    log.info("preprocessing %d libraries (lang=%s)", len(todo), args.lang)

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume between libraries. Press 'q' to abort.")

    # Open preprocess log in append mode across runs.
    log_exists = preproc_log_path.exists()
    log_fh = open(preproc_log_path, "a" if log_exists else "w",
                  newline="", encoding="utf-8")
    log_writer = csv.DictWriter(log_fh, fieldnames=PREPROC_LOG_COLS)
    if not log_exists:
        log_writer.writeheader()

    n_ready = n_f5 = n_f6 = n_missing = 0
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        for i, row in enumerate(todo, 1):
            pause.check()
            pkg = row["package_name"]
            eco = row["ecosystem"]
            log.info("[%d/%d] %s  (%s)", i, len(todo), pkg, eco)

            entry = process_library(row, text_root)
            log_writer.writerow(entry)
            log_fh.flush()

            if entry["status"] == "ready":
                n_ready += 1
                log.info("  OK  words=%d  capped=%s  en=%.2f",
                         entry["word_count_post_clean"],
                         entry["word_capped"],
                         entry["english_fraction"])
            elif entry["status"] == "F5_fail":
                n_f5 += 1
                log.warning("  F5 FAIL: %s", entry["reason"])
                excl_rows.append({
                    "package_name": pkg, "ecosystem": eco,
                    "draw_order": row["draw_order"],
                    "stage": "preprocess", "filter_failed": "F5",
                    "evidence": entry["reason"],
                    "timestamp": timestamp,
                })
            elif entry["status"] == "F6_fail":
                n_f6 += 1
                log.warning("  F6 FAIL: %s", entry["reason"])
                excl_rows.append({
                    "package_name": pkg, "ecosystem": eco,
                    "draw_order": row["draw_order"],
                    "stage": "preprocess", "filter_failed": "F6",
                    "evidence": entry["reason"],
                    "timestamp": timestamp,
                })
            elif entry["status"] == "clone_missing":
                n_missing += 1
                log.warning("  MISSING CLONE: %s", entry["reason"])
                excl_rows.append({
                    "package_name": pkg, "ecosystem": eco,
                    "draw_order": row["draw_order"],
                    "stage": "preprocess", "filter_failed": "F4",
                    "evidence": entry["reason"],
                    "timestamp": timestamp,
                })
    finally:
        log_fh.close()
        pause.stop()

    # Promote reserves in draw order to replace any new failures.
    promoted = promote_reserves(rows)
    log.info("promoted %d reserves to primary; rerun confirmatory_cloner "
             "then this script again to close the loop.", promoted)

    save_csv(manifest_path, fieldnames, rows)
    save_csv(excl_path, excl_fields, excl_rows)

    from collections import Counter
    status_counts = Counter((r["ecosystem"], r["status"]) for r in rows)
    print("\n--- pass summary ---")
    print(f"  ready: {n_ready}")
    print(f"  F5 (word count) failures: {n_f5}")
    print(f"  F6 (english) failures: {n_f6}")
    print(f"  missing clones (F4-late): {n_missing}")
    print(f"  reserves promoted: {promoted}")
    print("\n--- final status counts ---")
    for k, v in sorted(status_counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
