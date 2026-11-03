"""
rq3_select_clean_subset: seeded n=50/ecosystem draw over the *clean* pool,
replacing generation_subset_n50.csv for the re-run of RQ3.

Why a new draw. rq3_readme_scope_audit.py found that 39/50
Java and 8/50 Python human READMEs in the original subset are the parent
repository's front page rather than the library's own, because both
extractors fall back to the clone-root README when the scoped module has
none. rq3_extend_java_clean.py then topped the Java clean pool back up to
50 by continuing the draw into frame_locked's reserves and, once those
ran dry, into frame_n2000. This script draws the generation
subset from that corrected pool.

Inclusion rules, both applied to corpus structure only and blind to every
LIWC score (see the two scripts above for the reasoning):

  1. the scoped module has its own README, or the repository is a genuine
     single-package repo (so the root README *is* the library's)
  2. README >= 50 words and API surface >= 50 words, LIWC percentages off
     a 17-word README are noise, and a near-empty API surface means the
     model invented rather than described

Draw. Same convention as rq3_select_generation_subset.py: stdlib
random.Random(402).sample over the alphabetically-sorted clean pool, no
stratification by domain, size or anything else. Where the clean pool is
exactly n (Java, 50/50), the "draw" is the whole pool and the seed is
irrelevant, recorded anyway so the two subsets are described the same way.

Cost note. Libraries already generated under the old subset keep their
generations; only the newcomers need API calls. The script prints that
split so the spend is known before rq3_full_generate.py runs.

Outputs:
    files/corpus/rq3/generation_subset_clean_n50.csv

Usage:
    venv/bin/python3 src/generation/rq3_select_clean_subset.py
    venv/bin/python3 src/generation/rq3_select_clean_subset.py --n 50
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]

from rq3_readme_scope_audit import (  # noqa: E402
    RAW_DIR, RQ3_DIR, has_readme, module_dirs, multi_module_root, MONOREPO_MIN,
)

SEED = 402
MIN_README_WORDS = 50
MIN_API_WORDS = 50
OUT_COLS = ["ecosystem", "package_name", "selected", "already_generated",
            "readme_words", "api_words", "draw_seed", "draw_note"]


def clean_pool(eco: str) -> list[tuple[str, int, int]]:
    latest: dict[str, dict] = {}
    with open(RQ3_DIR / f"extract_log_{eco}.csv", newline="") as f:
        for r in csv.DictReader(f):
            latest[r["package_name"]] = r      # append-only log: last wins

    pool = []
    for pkg, r in latest.items():
        if r["status"] != "ready" or r["readme_found"] != "true":
            continue
        rm = int(r["readme_word_count"] or 0)
        api = int(r["api_surface_word_count"] or 0)
        if rm < MIN_README_WORDS or api < MIN_API_WORDS:
            continue
        clone = RAW_DIR / eco / r["safe_name"]
        if not clone.is_dir():
            continue
        scoped = r["scoped_to_subdir"]
        own = bool(scoped) and has_readme(clone / scoped)
        single = (len(module_dirs(clone)) < MONOREPO_MIN
                  and not multi_module_root(clone))
        if own or single:
            pool.append((pkg, rm, api))
    return sorted(pool)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    generated = set(pd.read_csv(RQ3_DIR / "rq3_libraries_prose.csv")
                    .query("source == 'human'").library)

    rows = []
    for eco in ("java", "python"):
        pool = clean_pool(eco)
        names = [p for p, _, _ in pool]
        if len(names) < args.n:
            raise SystemExit(
                f"{eco}: clean pool is {len(names)}, need {args.n} — "
                f"run rq3_extend_java_clean.py to top it up first")
        chosen = set(random.Random(SEED).sample(names, args.n))
        n_new = sum(1 for p in chosen if p not in generated)
        print(f"{eco:7s} clean pool {len(names):3d} -> drew {args.n} "
              f"({args.n - n_new} already generated, {n_new} new, "
              f"{n_new * 2} API calls)")
        for pkg, rm, api in pool:
            rows.append({
                "ecosystem": eco, "package_name": pkg,
                "selected": str(pkg in chosen).lower(),
                "already_generated": str(pkg in generated).lower(),
                "readme_words": rm, "api_words": api, "draw_seed": SEED,
                "draw_note": ("whole clean pool, no draw needed"
                              if len(names) == args.n else
                              "uniform random, no stratification, "
                              "random.Random(seed).sample over sorted clean pool"),
            })

    out = RQ3_DIR / f"generation_subset_clean_n{args.n}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(rows)
    total_new = sum(1 for r in rows
                    if r["selected"] == "true" and r["already_generated"] == "false")
    print(f"\nWrote {out}")
    print(f"Total new generations: {total_new} libraries x 2 models "
          f"= {total_new * 2} API calls")


if __name__ == "__main__":
    main()
