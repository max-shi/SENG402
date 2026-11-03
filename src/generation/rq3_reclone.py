"""
rq3_reclone: Re-materialize the 400 confirmatory libraries for RQ3.

RQ3 (human vs LLM-generated documentation) needs source-level API signatures for each
of the 400 libraries already used in RQ1/RQ2
(files/corpus/frame_locked_corrected/sample_manifest_final.csv,
the monorepo-duplication-corrected 400, RULES.md).
The raw git clones from that frame were deleted after the n=1000
extension (~300GB reclaimed), this script re-clones exactly the same
400 libraries, independently of that frame, into files/raw/rq3/.

sample_manifest_final.csv is read-only here and never modified: it is
the locked RQ1/RQ2 corpus record. The reproduction target is the exact
commit_sha recorded in that manifest, not just the version tag, if a
shallow tag-based clone lands on a different commit (a moved tag, or
the original clone having fallen back to the default branch), this
script fetches and checks out the exact recorded SHA. A library whose
recorded commit is no longer reachable (rewritten history, deleted
repo, force-push, etc.) is logged as a reclone failure and becomes a
genuine RQ3-specific exclusion, reported in reclone_log.csv, not
silently dropped, since RQ3's paired design needs a 1:1 match with the
human corpus and can't substitute a reserve the way RQ1/RQ2 could.

Outputs:
    files/raw/rq3/{python,java}/<safe_name>/     # git clones
    files/corpus/rq3/reclone_log.csv             # per-library outcome

Usage:
    venv/bin/python3 src/generation/rq3_reclone.py [--lang java|python|all]
                                               [--libraries START-END]
                                               [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_cloner import (  # noqa: E402
    _git,
    commit_sha as resolve_head_sha,
    is_clonable_url,
    safe_name,
    try_clone,
)

from pause_helper import PauseController  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
)
RAW_DIR = ROOT / "files" / "raw" / "rq3"
RQ3_DIR = ROOT / "files" / "corpus" / "rq3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

RECLONE_LOG_COLS = [
    "timestamp", "package_name", "ecosystem", "repository_url",
    "version_pinned", "target_commit_sha", "resolved_commit_sha",
    "strategy", "checkout_action", "status", "error",
]


def load_manifest_rows(lang_filter: Iterable[str]) -> list[dict]:
    with open(SOURCE_MANIFEST) as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["ecosystem"] in lang_filter]


def checkout_exact_sha(dest: Path, target_sha: str) -> tuple[bool, str]:
    """
    Attempt to make `dest`'s HEAD equal `target_sha`. Tries a shallow
    fetch of the exact SHA first (fast; works on hosts that allow
    fetching arbitrary reachable commits, which GitHub/GitLab do for
    public repos); falls back to unshallowing the whole clone if the
    server rejects a fetch-by-SHA. Returns (success, action_taken).
    """
    code, _ = _git(["fetch", "--depth", "1", "origin", target_sha], cwd=dest)
    if code == 0:
        code2, out2 = _git(["checkout", "--detach", target_sha], cwd=dest)
        if code2 == 0:
            return True, "shallow-fetch-by-sha"

    code, _ = _git(["fetch", "--unshallow", "origin"], cwd=dest, timeout=600)
    if code != 0:
        code, _ = _git(["fetch", "origin"], cwd=dest, timeout=600)
    code2, out2 = _git(["checkout", "--detach", target_sha], cwd=dest)
    if code2 == 0:
        return True, "unshallow-then-checkout"
    return False, f"checkout failed: {out2[:300]}"


def process_row(row: dict, dry_run: bool) -> dict:
    pkg = row["package_name"]
    eco = row["ecosystem"]
    repo = row.get("repository_url", "").strip()
    ver = row.get("version_pinned", "").strip()
    target_sha = row.get("commit_sha", "").strip()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_name": pkg, "ecosystem": eco, "repository_url": repo,
        "version_pinned": ver, "target_commit_sha": target_sha,
        "resolved_commit_sha": "", "strategy": "", "checkout_action": "",
        "status": "", "error": "",
    }

    if not is_clonable_url(repo) or not target_sha:
        entry["status"] = "skipped_unclonable_or_no_sha"
        entry["error"] = (
            f"repo={repo or '(empty)'} target_sha={target_sha or '(empty)'}"
        )
        return entry

    dest = RAW_DIR / eco / safe_name(pkg)

    # Already reproduced correctly by a prior run of this script?
    if dest.is_dir() and (dest / ".git").is_dir():
        current = resolve_head_sha(dest)
        if current == target_sha:
            entry["status"] = "already_exact"
            entry["resolved_commit_sha"] = current
            return entry
        if not dry_run:
            shutil.rmtree(dest, ignore_errors=True)

    if dry_run:
        entry["status"] = "dry_run_would_clone"
        return entry

    result = try_clone(repo, dest, ver)
    if not result["cloned"]:
        entry["status"] = "clone_failed"
        entry["error"] = result["error"]
        return entry

    entry["strategy"] = result["strategy"]
    current = resolve_head_sha(dest)
    entry["resolved_commit_sha"] = current

    if current == target_sha:
        entry["status"] = "exact_match"
        return entry

    ok, action = checkout_exact_sha(dest, target_sha)
    entry["checkout_action"] = action
    if ok:
        entry["resolved_commit_sha"] = resolve_head_sha(dest)
        entry["status"] = "exact_match_via_checkout"
    else:
        entry["status"] = "no_exact_match"
        entry["error"] = action

    return entry


def parse_range(value: str) -> tuple[int, int]:
    if "-" in value:
        a, b = value.split("-", 1)
        return int(a), int(b)
    n = int(value)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["java", "python", "all"], default="all")
    ap.add_argument(
        "--libraries", help="Range within this pass, e.g. '1-10' (1-indexed)."
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SOURCE_MANIFEST.exists():
        raise SystemExit(f"source manifest not found: {SOURCE_MANIFEST}")

    ecosystems = ["java", "python"] if args.lang == "all" else [args.lang]
    rows = load_manifest_rows(ecosystems)
    if args.libraries:
        start, end = parse_range(args.libraries)
        rows = rows[start - 1:end]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RQ3_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RQ3_DIR / "reclone_log.csv"
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=RECLONE_LOG_COLS)
    if not log_exists:
        writer.writeheader()

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume between clones. Press 'q' or Ctrl-C to abort.")
    log.info("re-cloning %d libraries (lang=%s)", len(rows), args.lang)

    counts: dict[str, int] = {}
    try:
        for i, row in enumerate(rows, 1):
            pause.check()
            log.info("[%d/%d] %s (%s)", i, len(rows), row["package_name"], row["ecosystem"])
            entry = process_row(row, args.dry_run)
            writer.writerow(entry)
            log_fh.flush()
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            log.info(
                "  -> %s%s",
                entry["status"],
                f" ({entry['error'][:150]})" if entry["error"] else "",
            )
    finally:
        log_fh.close()
        pause.stop()

    print("\n--- reclone summary ---")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
