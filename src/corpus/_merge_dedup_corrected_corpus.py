"""
One-off: build the corrected 400-library corpus (text + final manifest)
by merging the 339 untouched original texts (files/corpus/frame_locked)
with the 61 rescoped/backfilled texts (files/corpus/frame_locked_corrected),
without modifying either source directory.

Output: files/corpus/frame_locked_corrected/{sample_manifest_final_corrected.csv, text_corrected/}
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIG = ROOT / "files" / "corpus" / "frame_locked"
CHECK = ROOT / "files" / "corpus" / "frame_locked_corrected"
OUT_TEXT = CHECK / "text_corrected"

with open(CHECK / "sample_manifest.csv") as f:
    rows = list(csv.DictReader(f))
final = [r for r in rows if r["role"] == "primary" and r["status"] == "primary_ready"]
assert len(final) == 400, len(final)
by_eco = {}
for r in final:
    by_eco.setdefault(r["ecosystem"], 0)
    by_eco[r["ecosystem"]] += 1
print("final counts:", by_eco)

OUT_TEXT.mkdir(parents=True, exist_ok=True)
for eco in by_eco:
    (OUT_TEXT / eco).mkdir(exist_ok=True)

n_from_orig = n_from_check = n_missing = 0
for r in final:
    eco = r["ecosystem"]
    sname = r["package_name"].replace(":", "_").replace("/", "_")
    dst = OUT_TEXT / eco / f"{sname}.txt"
    check_src = CHECK / "text" / eco / f"{sname}.txt"
    orig_src = ORIG / "text" / eco / f"{sname}.txt"
    if check_src.exists():
        shutil.copy(check_src, dst)
        n_from_check += 1
    elif orig_src.exists():
        shutil.copy(orig_src, dst)
        n_from_orig += 1
    else:
        n_missing += 1
        print("MISSING TEXT for", eco, r["package_name"])

print(f"from original (untouched): {n_from_orig}")
print(f"from dedup_check (rescoped/backfilled): {n_from_check}")
print(f"missing: {n_missing}")

fieldnames = list(final[0].keys())
with open(CHECK / "sample_manifest_final_corrected.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(final)
print("wrote", CHECK / "sample_manifest_final_corrected.csv")
