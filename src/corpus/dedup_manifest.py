"""
One-off patch: dedup sample_manifest.csv and the frame_*.jsonl.gz
snapshots after discovering that the ecosyste.ms API's sort by
`dependent_packages_count` is not stable across ties, so pagination
surfaced some packages on two consecutive pages, and the draw
consequently contained a handful of duplicate names.

Applies the reserve-promotion mechanism to remove duplicates
and shift reserves into vacated primary slots. Logs every removal
to exclusion_log.csv under stage=frame-dedup, filter_failed=DEDUP.

The sample_frame.py script itself has been fixed (frame-level dedup
added to run_for_ecosystem), so this patch script does not need to
be re-run for future freeze dates.

Usage:
    python3 src/corpus/dedup_manifest.py [--freeze-date <name>]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from frame_config import load_n_target

ROOT = Path(__file__).resolve().parents[2]
N_TARGET = 200  # overridden in main() from the frame's frame_metadata.json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--freeze-date",
        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    excl_path = frame_dir / "exclusion_log.csv"

    global N_TARGET
    N_TARGET = load_n_target(frame_dir)

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    timestamp = datetime.now(timezone.utc).isoformat()

    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    with open(excl_path) as f:
        er = csv.DictReader(f)
        excl_fieldnames = er.fieldnames
        excl_rows = list(er)

    new_rows: list[dict] = []
    new_excl = list(excl_rows)

    ecosystems = sorted({r["ecosystem"] for r in all_rows})

    for eco in ecosystems:
        eco_rows = [r for r in all_rows if r["ecosystem"] == eco]
        eco_rows.sort(key=lambda r: int(r["draw_order"]))
        seen: set[str] = set()
        kept: list[dict] = []
        dropped: list[dict] = []
        for r in eco_rows:
            name = r["package_name"]
            if name in seen:
                dropped.append(r)
                new_excl.append({
                    "package_name": name,
                    "ecosystem": eco,
                    "draw_order": r["draw_order"],
                    "stage": "frame-dedup",
                    "filter_failed": "DEDUP",
                    "evidence": "duplicate of earlier draw_order (kept first occurrence)",
                    "timestamp": timestamp,
                })
                continue
            seen.add(name)
            kept.append(r)

        promoted = 0
        for i, r in enumerate(kept):
            new_role = "primary" if i < N_TARGET else "reserve"
            old_role = r["role"]
            if new_role != old_role:
                r["status"] = f"{new_role}_pending_promoted_from_{old_role}"
                promoted += 1
            else:
                r["status"] = f"{new_role}_pending"
            r["role"] = new_role
        new_rows.extend(kept)
        print(f"[{eco}] kept {len(kept)} unique, dropped {len(dropped)} duplicates, promoted {promoted} reserves")

    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(new_rows)
    print(f"wrote {manifest_path}  ({len(new_rows)} rows)")

    with open(excl_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=excl_fieldnames)
        w.writeheader()
        w.writerows(new_excl)
    print(f"wrote {excl_path}  ({len(new_excl)} rows)")

    # Dedupe the frame snapshot files (keep first occurrence per name).
    for eco in ecosystems:
        src = frame_dir / f"frame_{eco}.jsonl.gz"
        if not src.exists():
            print(f"[{eco}] snapshot missing, skipping: {src}")
            continue
        tmp = frame_dir / f"frame_{eco}.jsonl.gz.tmp"
        snap_seen: set[str] = set()
        kept = read = 0
        with gzip.open(src, "rt", encoding="utf-8") as fin, \
             gzip.open(tmp, "wt", encoding="utf-8") as fout:
            for line in fin:
                read += 1
                pkg = json.loads(line)
                if pkg["name"] in snap_seen:
                    continue
                snap_seen.add(pkg["name"])
                fout.write(line)
                kept += 1
        os.replace(tmp, src)
        print(f"[{eco}] snapshot: kept {kept}/{read}, size = {src.stat().st_size / 1024:.1f} KB")

    # Verification.
    print("\n--- verify ---")
    with open(manifest_path) as f:
        rows = list(csv.DictReader(f))
    per = Counter((r["ecosystem"], r["role"]) for r in rows)
    for k, v in sorted(per.items()):
        print(f"  {k}: {v}")
    for eco in ecosystems:
        names = [r["package_name"] for r in rows if r["ecosystem"] == eco]
        print(f"  {eco}: {len(names)} rows, {len(set(names))} unique names")


if __name__ == "__main__":
    main()
