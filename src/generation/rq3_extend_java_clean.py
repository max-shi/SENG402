"""
rq3_extend_java_clean: top the Java side of the RQ3 corpus back up to 50
libraries whose human README actually belongs to the library.

Why. rq3_readme_scope_audit.py showed both extractors fall back to the
clone-root README when the scoped module has none of its own, which for a
multi-module Maven repo hands the library its parent project's front page
(Keycloak's README paired with keycloak-model-legacy-services, and so on).
23 of the 50 sampled Java libraries are affected. Only 43 of the 127 ready
Java libraries survive an "own README" rule, so reaching n=50 means drawing
more candidates rather than filtering the ones already extracted.

Sampling. Candidates come from the RQ3 frame's own parent manifest
(files/corpus/frame_locked/sample_manifest.csv, 496 Java rows) in
pre-specified draw_order, skipping every package already attempted. Rows
that FAILED the frame's filters (primary_failed_f4/f5/f6, primary_excluded_f7)
are never resurrected. Eligible:

  primary_ready    44 rows, passed every frame filter, pinned commit_sha
  reserve_pending 103 rows, drawn but never crawled, so no pinned sha;
                             only used with --allow-reserve, cloned at
                             version_pinned and logged as sha_unpinned

Inclusion rule, applied to repository structure only and blind to any LIWC
score (the point of running it as a separate pass):

    keep if the scoped module directory has its own README,
    or the repository holds fewer than 2 sub-module build manifests
    (single-package repo, so the root README *is* the library's)

Rejected clones are deleted unless --keep-rejected: they are reproducible
from the manifest, and the Java monorepos in this pool are large.

Outputs:
    files/corpus/rq3/rq3_extension_log.csv   per-candidate outcome, append-only
    files/corpus/rq3/extract_log_java.csv    extraction rows for kept libraries
    files/raw/rq3/java/<safe_name>/          clones of kept libraries
    files/corpus/rq3/api_surface/java/...    API surfaces, via the extractor
    files/corpus/rq3/readme_only/java/...    human READMEs, via the extractor

Usage:
    venv/bin/python3 src/generation/rq3_extend_java_clean.py --target 50
    venv/bin/python3 src/generation/rq3_extend_java_clean.py --target 50 --allow-reserve
"""
from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]

from rq3_extract_java import (  # noqa: E402
    EXTRACT_LOG_COLS, RAW_DIR, RQ3_DIR, process_library, safe_name,
)
from rq3_readme_scope_audit import (  # noqa: E402
    has_readme, module_dirs, multi_module_root,
)
from confirmatory_cloner import try_clone  # noqa: E402

PARENT_MANIFEST = ROOT / "files" / "corpus" / "frame_locked" / "sample_manifest.csv"
# The later, larger frame built by the same sampling machinery and used for
# the RQ1/RQ2 confirmatory corpus. 994 unused Java rows, every one
# primary_ready with a pinned commit_sha, so drawing from it needs no
# loosening of any filter, only the note that RQ3's Java sample now spans
# both frames. Used via --manifest once frame_locked's pool runs dry.
N2000_MANIFEST = (ROOT / "files" / "corpus" / "frame_n2000"
                  / "sample_manifest_final.csv")
USED_MANIFEST = (ROOT / "files" / "corpus" / "frame_locked_corrected"
                 / "sample_manifest_final.csv")
EXTRACT_LOG = RQ3_DIR / "extract_log_java.csv"
EXT_LOG = RQ3_DIR / "rq3_extension_log.csv"

EXT_LOG_COLS = ["timestamp", "draw_order", "role", "package_name", "safe_name",
                "repository_url", "sha_pinned", "clone_status", "extract_status",
                "scoped_to_subdir", "n_submodule_manifests", "readme_words",
                "verdict", "note"]
MONOREPO_MIN = 2

# Size floor. The own-README rule concentrates small
# single-purpose libraries, and LIWC percentages off a 17-word README are
# noise, WPS in particular is then a single sentence. A near-empty API
# surface is the mirror problem: the model was asked to document almost
# nothing, so it invented the content rather than describing this library.
# Applied to both sides of every pair; 0 disables.
MIN_README_WORDS = 50
MIN_API_WORDS = 50

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("extend")


def meets_size(readme_words: int, api_words: int,
               min_readme: int, min_api: int) -> bool:
    return readme_words >= min_readme and api_words >= min_api


def existing_clean(min_readme: int = 0, min_api: int = 0) -> set[str]:
    """Java packages already extracted that satisfy the inclusion rule,
    recomputed from the clones, not read from the audit CSV, so this
    script and the audit can never disagree about what 'clean' means."""
    latest: dict[str, dict] = {}
    with open(EXTRACT_LOG, newline="") as f:
        for r in csv.DictReader(f):
            latest[r["package_name"]] = r     # append-only log: last wins
    keep = set()
    for pkg, r in latest.items():
        if r["status"] != "ready":
            continue
        clone = RAW_DIR / "java" / r["safe_name"]
        if not clone.is_dir():
            continue
        if not meets_size(int(r["readme_word_count"] or 0),
                          int(r["api_surface_word_count"] or 0),
                          min_readme, min_api):
            continue
        if is_clean(clone, r["scoped_to_subdir"])[0]:
            keep.add(pkg)
    return keep


def is_clean(clone: Path, scoped: str) -> tuple[bool, int]:
    n_modules = len(module_dirs(clone))
    if scoped and has_readme(clone / scoped):
        return True, n_modules
    # multi_module_root() catches sbt/Gradle builds that declare their
    # modules in one root file, which leaves n_modules at 0.
    return (n_modules < MONOREPO_MIN and not multi_module_root(clone)), n_modules


def candidates(allow_reserve: bool, manifest: Path = PARENT_MANIFEST) -> list[dict]:
    m = pd.read_csv(manifest)
    used = set(pd.read_csv(USED_MANIFEST).package_name)
    attempted = {r["package_name"] for r in csv.DictReader(open(EXTRACT_LOG))}
    ok_status = {"primary_ready"} | ({"reserve_pending"} if allow_reserve else set())
    j = m[(m.ecosystem == "java")
          & (~m.package_name.isin(used | attempted))
          & (m.status.isin(ok_status))]
    # primary_ready first (pinned sha, passed every frame filter), then
    # reserves; draw_order within each, so the order stays reproducible.
    j = j.assign(_tier=(j.status != "primary_ready").astype(int))
    return j.sort_values(["_tier", "draw_order"]).to_dict("records")


def clone_candidate(row: dict, dest: Path) -> tuple[bool, str, str]:
    repo = str(row.get("repository_url") or "").strip()
    ver = str(row.get("version_pinned") or "").strip()
    sha = str(row.get("commit_sha") or "").strip()
    if sha in ("", "nan"):
        sha = ""
    if not repo.startswith(("http://", "https://", "git@")) or "github" not in repo:
        return False, "skipped_unclonable", f"repo={repo or '(empty)'}"
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    result = try_clone(repo, dest, ver)
    if not result["cloned"]:
        return False, "clone_failed", str(result.get("error", ""))[:200]
    if sha:
        import subprocess
        p = subprocess.run(["git", "checkout", "--detach", sha], cwd=dest,
                           capture_output=True, text=True)
        if p.returncode != 0:
            return True, "cloned_sha_missed", result["strategy"]
        return True, "cloned_exact", result["strategy"]
    return True, "cloned_sha_unpinned", result["strategy"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50,
                    help="total clean Java libraries wanted (existing + new)")
    ap.add_argument("--max-candidates", type=int, default=80)
    ap.add_argument("--allow-reserve", action="store_true")
    ap.add_argument("--keep-rejected", action="store_true")
    ap.add_argument("--min-readme-words", type=int, default=MIN_README_WORDS)
    ap.add_argument("--min-api-words", type=int, default=MIN_API_WORDS)
    ap.add_argument("--manifest", choices=["frame_locked", "n2000"],
                    default="frame_locked",
                    help="which frame to draw further candidates from")
    args = ap.parse_args()

    clean = existing_clean(args.min_readme_words, args.min_api_words)
    need = args.target - len(clean)
    log.info("Already clean: %d Java libraries (README>=%d words, API>=%d). "
             "Need %d more for n=%d.", len(clean), args.min_readme_words,
             args.min_api_words, need, args.target)
    if need <= 0:
        return

    manifest = (N2000_MANIFEST if args.manifest == "n2000" else PARENT_MANIFEST)
    pool = candidates(args.allow_reserve, manifest)[:args.max_candidates]
    log.info("Candidate pool: %d rows from %s (allow_reserve=%s)\n",
             len(pool), manifest.parent.name, args.allow_reserve)

    ext_exists = EXT_LOG.exists()
    ext_fh = open(EXT_LOG, "a" if ext_exists else "w", newline="", encoding="utf-8")
    ext_w = csv.DictWriter(ext_fh, fieldnames=EXT_LOG_COLS)
    if not ext_exists:
        ext_w.writeheader()
    ex_fh = open(EXTRACT_LOG, "a", newline="", encoding="utf-8")
    ex_w = csv.DictWriter(ex_fh, fieldnames=EXTRACT_LOG_COLS)

    kept = 0
    try:
        for i, row in enumerate(pool, 1):
            pkg = row["package_name"]
            sname = safe_name(pkg)
            dest = RAW_DIR / "java" / sname
            rec = {c: "" for c in EXT_LOG_COLS}
            rec.update({"timestamp": datetime.now(timezone.utc).isoformat(),
                        "draw_order": row["draw_order"], "role": row["status"],
                        "package_name": pkg, "safe_name": sname,
                        "repository_url": row.get("repository_url", "")})
            log.info("[%d/%d] %s", i, len(pool), pkg)

            ok, clone_status, note = clone_candidate(row, dest)
            rec.update({"clone_status": clone_status, "note": note,
                        "sha_pinned": clone_status == "cloned_exact"})
            if not ok:
                rec["verdict"] = "rejected"
                ext_w.writerow(rec); ext_fh.flush()
                log.info("   %s — %s", clone_status, note)
                continue

            try:
                entry = process_library(row)
            except Exception as exc:  # noqa: BLE001, one bad repo must not
                # abort the pass; same contract as the extractor's own loop.
                log.exception("   extraction crashed: %s", exc)
                rec.update({"extract_status": "crashed", "verdict": "rejected",
                            "note": str(exc)[:200]})
                ext_w.writerow(rec); ext_fh.flush()
                shutil.rmtree(dest, ignore_errors=True)
                continue

            rec.update({"extract_status": entry["status"],
                        "scoped_to_subdir": entry["scoped_to_subdir"],
                        "readme_words": entry["readme_word_count"]})

            if entry["status"] != "ready" or entry["readme_found"] != "true":
                rec["verdict"] = "rejected"
            elif not meets_size(int(entry["readme_word_count"]),
                                int(entry["api_surface_word_count"]),
                                args.min_readme_words, args.min_api_words):
                rec["verdict"] = "rejected"
                rec["extract_status"] = "below_size_floor"
            else:
                ok_clean, n_mod = is_clean(dest, entry["scoped_to_subdir"])
                rec["n_submodule_manifests"] = n_mod
                rec["verdict"] = "kept" if ok_clean else "rejected"

            if rec["verdict"] == "kept":
                ex_w.writerow(entry); ex_fh.flush()
                kept += 1
                log.info("   KEPT (%d/%d)  api_words=%d readme_words=%s",
                         kept, need, entry["api_surface_word_count"],
                         entry["readme_word_count"])
            else:
                log.info("   rejected — %s", rec["extract_status"] or rec["clone_status"])
                if not args.keep_rejected:
                    shutil.rmtree(dest, ignore_errors=True)

            ext_w.writerow(rec); ext_fh.flush()
            if kept >= need:
                break
    finally:
        ext_fh.close(); ex_fh.close()

    log.info("\n--- extension summary ---")
    log.info("kept %d of %d needed; clean Java total now %d/%d",
             kept, need, len(clean) + kept, args.target)
    if kept < need:
        log.info("Run again with a larger --max-candidates, or --allow-reserve.")


if __name__ == "__main__":
    main()
