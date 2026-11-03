"""
build_libraries_csv: Consolidate the confirmatory sample into libraries.csv.

Reads sample_manifest_final.csv (one row per confirmatory library, with a
pointer to its cleaned text file) and writes a single libraries.csv with
one row per library and the full text inlined. This is the direct input
to LIWC-22 desktop for the confirmatory phase, mirroring the pilot's
_write_consolidated_libraries() step in preprocess.py.

Usage:
    venv/bin/python3 src/corpus/build_libraries_csv.py [--freeze-date <name>]
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

LIBRARIES_COLUMNS = ["library", "ecosystem", "domain", "n_words", "text"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest_final.csv"
    out_path = frame_dir / "libraries.csv"

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    csv.field_size_limit(sys.maxsize)

    with open(manifest_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows = [r for r in rows if r["status"] == "primary_ready"]
    print(f"Found {len(rows)} primary_ready rows.")

    # The extended n=2000 frame carries no domain tags; its
    # manifest has no domain_tag column and libraries.csv omits `domain`.
    has_domain = rows and "domain_tag" in rows[0]
    columns = LIBRARIES_COLUMNS if has_domain else [
        c for c in LIBRARIES_COLUMNS if c != "domain"]

    out_rows: list[dict] = []
    missing: list[str] = []
    for r in rows:
        text_path = ROOT / r["text_file_path"]
        if not text_path.is_file():
            missing.append(r["text_file_path"])
            continue
        text = text_path.read_text(encoding="utf-8")
        if "\x00" in text:
            # Defensive: a stray NUL byte breaks CSV readers (incl. LIWC).
            # Found once in frame_n2000 (org.jbundle:org.jbundle.model,
            # 1 byte in 349KB), almost certainly a binary artefact that
            # slipped through prose extraction. Stripped here rather than
            # tracing the exact source file, given the narrow scope.
            print(f"  stripped {text.count(chr(0))} NUL byte(s) from {r['package_name']}")
            text = text.replace("\x00", "")
        out_row = {
            "library": r["package_name"],
            "ecosystem": r["ecosystem"],
            "n_words": r["word_count_post_clean"],
            "text": text,
        }
        if has_domain:
            out_row["domain"] = r["domain_tag"]
        out_rows.append(out_row)

    if missing:
        print(f"WARNING: {len(missing)} rows have no text file on disk:")
        for m in missing[:10]:
            print(f"    {m}")
        if len(missing) > 10:
            print(f"    ...and {len(missing) - 10} more")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {len(out_rows)} rows to {out_path}")

    for eco in sorted({r["ecosystem"] for r in out_rows}):
        n = sum(1 for r in out_rows if r["ecosystem"] == eco)
        print(f"  {eco:6s}  n={n}")


if __name__ == "__main__":
    main()
