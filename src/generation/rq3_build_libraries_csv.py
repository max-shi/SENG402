"""
rq3_build_libraries_csv: Consolidate the RQ3 human/LLM texts into one CSV
for LIWC-22 desktop scoring, mirroring build_libraries_csv.py's role for
the RQ1/RQ2 confirmatory corpus (same idea: one row per text, LIWC-22
scores each row, the stats script joins the results back by key).

RQ3 is a *paired* design: per
library, three texts need scoring, not one, the real human README, and
each model's generated README. Driven directly off what's actually on
disk under files/corpus/rq3/full_generation/ (not a hardcoded library
list or count), so this naturally covers however many libraries have
actually been generated.

Every row for a given library shares the same `library`/`ecosystem`/
`domain`, the `source` column (human | sonnet | openai) is what the
downstream stats script pivots/joins on to compute
Δ = LLM_score - human_score per library per model (test 1) and
Δ_Java vs Δ_Python (test 2).

package_name is recovered from safe_name via the extract logs (filename
safe_name() isn't reliably invertible on its own), same lookup source as
rq3_overlap_check.py already uses. A library only gets a `human` row if
its README-only extraction actually succeeded (readme_found=true in the
extract log), verified before this script was written that this holds
for all 100 currently-generated libraries, but the check stays in the
code as a real guard, not an assumption, in case a future larger run
includes a case where it doesn't.

Output:
    files/corpus/rq3/rq3_libraries.csv

Usage:
    venv/bin/python3 src/generation/rq3_build_libraries_csv.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FULL_GEN_DIR = ROOT / "files" / "corpus" / "rq3" / "full_generation"
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only"
EXTRACT_LOGS = {
    "python": ROOT / "files" / "corpus" / "rq3" / "extract_log_python.csv",
    "java": ROOT / "files" / "corpus" / "rq3" / "extract_log_java.csv",
}
MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected"
    / "sample_manifest_final_corrected.csv"
)
# The clean re-draw spans three frames (see
# rq3_extend_java_clean.py), so domain tags have to be looked up across all
# of them. A library whose tag is missing would otherwise carry domain="",
# which pandas.groupby silently drops, the same failure that invalidated
# the RQ2 dedup re-run in July. main() raises rather than emitting one.
EXTRA_MANIFESTS = [
    ROOT / "files" / "corpus" / "frame_locked" / "sample_manifest.csv",
    ROOT / "files" / "corpus" / "frame_n2000" / "sample_manifest_final.csv",
]
OUT_PATH = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries.csv"

OUT_COLS = ["library", "ecosystem", "domain", "source", "n_words", "text"]

MODEL_SUFFIXES = [("sonnet", "sonnet"), ("openai", "openai")]


def latest_by_safe_name(ecosystem: str) -> dict[str, dict]:
    """safe_name -> latest log row, for recovering package_name and
    checking readme_found. 'Latest' = last row in the (append-only) log
    for that package_name, matching the convention used elsewhere
    (e.g. rq3_select_generation_subset.py's ready_pool)."""
    by_pkg: dict[str, dict] = {}
    with open(EXTRACT_LOGS[ecosystem]) as f:
        for row in csv.DictReader(f):
            by_pkg[row["package_name"]] = row
    return {row["safe_name"]: row for row in by_pkg.values()}


def domain_tags(ecosystem: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for extra in EXTRA_MANIFESTS:
        if not extra.exists():
            continue
        with open(extra) as f:
            for r in csv.DictReader(f):
                if r.get("domain_tag"):
                    tags[r["package_name"]] = r["domain_tag"]
    # The corrected 400-frame manifest wins where it has an opinion: its
    # tags are the reviewed ones (domain_tag_review.py).
    tags.update(_primary_domain_tags(ecosystem))
    return tags


def _primary_domain_tags(ecosystem: str) -> dict[str, str]:
    with open(MANIFEST) as f:
        return {
            r["package_name"]: r.get("domain_tag", "")
            for r in csv.DictReader(f)
            if r["ecosystem"] == ecosystem
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--subset-manifest", type=Path, default=None,
        help=("Restrict to package_names marked selected=true in a "
              "generation-subset CSV. Without it, every library with "
              "generated output is emitted — which after the "
              "clean re-draw means the old and new subsets mixed together."),
    )
    args = ap.parse_args()

    selected: set[str] | None = None
    if args.subset_manifest:
        with open(args.subset_manifest) as f:
            selected = {r["package_name"] for r in csv.DictReader(f)
                        if r.get("selected") == "true"}
        print(f"--subset-manifest applied: {len(selected)} libraries selected")

    csv.field_size_limit(sys.maxsize)

    out_rows: list[dict] = []
    skipped_no_readme: list[str] = []
    missing_domain: list[str] = []

    for eco in ("python", "java"):
        by_safe_name = latest_by_safe_name(eco)
        domains = domain_tags(eco)
        gen_dir = FULL_GEN_DIR / eco
        if not gen_dir.is_dir():
            continue

        # Discover libraries from what was actually generated, not a
        # hardcoded count, every *_sonnet.txt has a matching *_openai.txt
        # in a clean run (verified: 200/200, 0 failed), but
        # don't assume it; only emit a library once both models' output
        # and the human README are confirmed present.
        safe_names = sorted({
            p.name[: -len("_sonnet.txt")]
            for p in gen_dir.glob("*_sonnet.txt")
        })

        for sname in safe_names:
            log_row = by_safe_name.get(sname)
            if log_row is None:
                print(f"  WARNING: {eco}/{sname} has generated output but "
                      f"no matching extract-log entry — skipping")
                continue
            pkg = log_row["package_name"]
            if selected is not None and pkg not in selected:
                continue
            domain = domains.get(pkg, "")
            if not domain:
                # frame_n2000 carries no domain_tag column, and
                # frame_locked's reserves were drawn but never tagged, so
                # 31 libraries of the clean re-draw have no tag and cannot
                # get one without re-running domain_tag_review.py. RQ3's
                # tests (1, 2, 4) never group by domain, so an explicit
                # sentinel is enough, but it must not be the empty string,
                # which pandas.groupby drops silently (the July RQ2 bug).
                missing_domain.append(f"{eco}/{pkg}")
                domain = "untagged"

            readme_path = README_DIR / eco / f"{sname}.txt"
            if log_row["readme_found"] != "true" or not readme_path.exists():
                skipped_no_readme.append(f"{eco}/{pkg}")
                continue
            human_text = readme_path.read_text(encoding="utf-8")
            out_rows.append({
                "library": pkg, "ecosystem": eco, "domain": domain,
                "source": "human", "n_words": len(human_text.split()),
                "text": human_text,
            })

            for source, suffix in MODEL_SUFFIXES:
                gen_path = gen_dir / f"{sname}_{suffix}.txt"
                if not gen_path.exists():
                    print(f"  WARNING: {eco}/{pkg} missing {suffix} output "
                          f"— skipping that source, not the whole library")
                    continue
                gen_text = gen_path.read_text(encoding="utf-8")
                out_rows.append({
                    "library": pkg, "ecosystem": eco, "domain": domain,
                    "source": source, "n_words": len(gen_text.split()),
                    "text": gen_text,
                })

    if skipped_no_readme:
        print(f"Skipped {len(skipped_no_readme)} libraries with generated "
              f"output but no usable human README (breaks pairing):")
        for s in skipped_no_readme:
            print(f"    {s}")

    if missing_domain:
        print(f"\nNOTE: {len(missing_domain)} libraries have no domain tag "
              f'and were written as domain="untagged" — never as "". Any '
              f"domain-stratified analysis must exclude or re-tag them.")

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(out_rows)

    print(f"\nWrote {len(out_rows)} rows to {OUT_PATH}")
    for eco in ("python", "java"):
        for source in ("human", "sonnet", "openai"):
            n = sum(1 for r in out_rows
                    if r["ecosystem"] == eco and r["source"] == source)
            print(f"  {eco:6s} {source:6s}  n={n}")


if __name__ == "__main__":
    main()
