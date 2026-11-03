"""
One-off: build files/corpus/frame_locked_corrected/ from the locked
files/corpus/frame_locked/ working manifest, resetting only the rows
whose repository_url is shared by >1 of the 400 final libraries so the
standard cloner/preprocessor pipeline (now with monorepo scoping) can
reclone+reprocess just those, backfilling from the existing reserve pool
on any that fail after proper scoping. Never modifies the original
frame_locked directory.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "files" / "corpus" / "frame_locked"
DST = ROOT / "files" / "corpus" / "frame_locked_corrected"

with open(SRC / "sample_manifest_final.csv") as f:
    final_rows = list(csv.DictReader(f))
assert len(final_rows) == 400, len(final_rows)

repo_counts: dict[str, int] = {}
for r in final_rows:
    u = r.get("repository_url", "")
    if u:
        repo_counts[u] = repo_counts.get(u, 0) + 1
shared_repos = {u for u, c in repo_counts.items() if c > 1}
shared_names = {(r["ecosystem"], r["package_name"]) for r in final_rows
                if r.get("repository_url") in shared_repos}
print(f"{len(shared_repos)} shared repos among the 400 finals, "
      f"{len(shared_names)} rows to reset")

with open(SRC / "sample_manifest.csv") as f:
    working_rows = list(csv.DictReader(f))
    fieldnames = list(working_rows[0].keys())

n_reset = 0
for r in working_rows:
    key = (r["ecosystem"], r["package_name"])
    if key in shared_names and r["role"] == "primary":
        r["status"] = "primary_pending"
        r["word_count_post_clean"] = ""
        r["word_capped"] = ""
        r["pages_crawled"] = ""
        if "commit_sha" in r:
            r["commit_sha"] = ""
        n_reset += 1
print(f"reset {n_reset} rows to primary_pending")

DST.mkdir(parents=True, exist_ok=True)
if "commit_sha" not in fieldnames:
    fieldnames.append("commit_sha")
    for r in working_rows:
        r.setdefault("commit_sha", "")

with open(DST / "sample_manifest.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(working_rows)

shutil.copy(SRC / "exclusion_log.csv", DST / "exclusion_log.csv")

meta = json.loads((SRC / "frame_metadata.json").read_text())
meta["_dedup_check_note"] = (
    "Derived from frame_locked to re-clone/re-process, "
    "with monorepo subpackage scoping, only the rows whose repository_url "
    "is shared by >1 of the original 400 final libraries. See "
    "confirmatory_preprocessor.py's find_scoped_root."
)
(DST / "frame_metadata.json").write_text(json.dumps(meta, indent=2))

print("wrote", DST / "sample_manifest.csv")
print("wrote", DST / "frame_metadata.json")
print("wrote", DST / "exclusion_log.csv")
