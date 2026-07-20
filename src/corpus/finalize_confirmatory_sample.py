"""
finalize_confirmatory_sample — Snapshot the confirmatory sample.

Reads the working sample_manifest.csv and writes a frozen snapshot of
just the primary_ready rows (plus F7-review columns) as
sample_manifest_final.csv. Also writes a summary_stats.csv with per-
ecosystem counts and word-count percentiles.

The final CSV is the authoritative record of the confirmatory sample:
each row corresponds to exactly one .txt file under text/<eco>/.

Usage:
    venv/bin/python3 src/corpus/finalize_confirmatory_sample.py [--freeze-date YYYYMMDD]
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_")


def percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    k = max(0, min(len(sorted_values) - 1, int(round(p * (len(sorted_values) - 1)))))
    return sorted_values[k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    text_root = frame_dir / "text"
    final_path = frame_dir / "sample_manifest_final.csv"
    stats_path = frame_dir / "summary_stats.csv"

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    ready = [r for r in rows if r["status"] == "primary_ready"]
    print(f"Found {len(ready)} primary_ready rows.")

    # Verify text file exists for every row and record its size.
    missing: list[str] = []
    ready_with_files: list[dict] = []
    for r in ready:
        eco = r["ecosystem"]
        sname = safe_name(r["package_name"])
        p = text_root / eco / f"{sname}.txt"
        if not p.is_file():
            missing.append(f"{eco}/{sname}")
            continue
        r = dict(r)   # copy so we don't mutate
        r["text_file_path"] = str(p.relative_to(ROOT))
        r["text_file_bytes"] = str(p.stat().st_size)
        ready_with_files.append(r)

    if missing:
        print(f"WARNING: {len(missing)} ready rows have no text file on disk:")
        for m in missing[:10]:
            print(f"    {m}")
        if len(missing) > 10:
            print(f"    ...and {len(missing) - 10} more")

    # Add columns for the F7 manual review (default: not reviewed).
    if "f7_manual_reviewed" not in fieldnames:
        fieldnames.append("f7_manual_reviewed")
    if "f7_manual_flag" not in fieldnames:
        fieldnames.append("f7_manual_flag")
    if "text_file_path" not in fieldnames:
        fieldnames.append("text_file_path")
    if "text_file_bytes" not in fieldnames:
        fieldnames.append("text_file_bytes")

    for r in ready_with_files:
        r.setdefault("f7_manual_reviewed", "false")
        r.setdefault("f7_manual_flag", "")

    ready_with_files.sort(key=lambda r: (r["ecosystem"], int(r["draw_order"])))

    with open(final_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(ready_with_files)
    print(f"Wrote {final_path}")

    # Summary stats per ecosystem.
    summary_rows: list[dict] = []
    for eco in ("java", "python"):
        eco_rows = [r for r in ready_with_files if r["ecosystem"] == eco]
        wcs = sorted(int(r["word_count_post_clean"]) for r in eco_rows)
        capped = sum(1 for r in eco_rows if r.get("word_capped") == "true")
        summary_rows.append({
            "ecosystem": eco,
            "n": len(eco_rows),
            "min_words": wcs[0] if wcs else 0,
            "p25_words": percentile(wcs, 0.25),
            "median_words": median(wcs) if wcs else 0,
            "p75_words": percentile(wcs, 0.75),
            "max_words": wcs[-1] if wcs else 0,
            "n_capped_100k": capped,
        })
    with open(stats_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"Wrote {stats_path}")

    print()
    print("--- summary ---")
    for r in summary_rows:
        print(f"  {r['ecosystem']:6s}  n={r['n']}  words: min={r['min_words']}  "
              f"p25={r['p25_words']}  median={r['median_words']}  "
              f"p75={r['p75_words']}  max={r['max_words']}  "
              f"capped(100k)={r['n_capped_100k']}")


if __name__ == "__main__":
    main()
