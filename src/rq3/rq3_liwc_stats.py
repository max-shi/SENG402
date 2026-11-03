"""
rq3_liwc_stats: statistical pipeline for RQ3 (human vs LLM-generated
documentation), tests 1 and 2 of the RQ3 plan.

Reuses cliffs_delta / cliff_magnitude / holm_bonferroni verbatim from
confirmatory_liwc_stats.py (the RQ1/RQ2 script implementing the locked
statistical plan) rather than reimplementing them, so RQ3's effect sizes are
computed the exact same way and are directly comparable to RQ1/RQ2's.
Same decision rule too (Holm p < 0.05 AND |Cliff's delta| >= 0.33),
the RQ3 plan doesn't restate one explicitly, but nothing in the plan suggests a
different threshold, and using a different one here than everywhere else
in the report would need its own justification this doc doesn't give.

Two tests (test 3, the construct-validity re-check, is conditional on
what these two find, see the plan doc's own framing, and isn't
implemented here yet):

1. **Within-ecosystem paired test** (test 1). Per model, per
   ecosystem, per dimension: Wilcoxon signed-rank on
   Delta_i = LLM_i - human_i (paired by library), plus Cliff's delta
   comparing the LLM-score array against the human-score array (same
   pairwise-comparison definition as cliffs_delta() everywhere else in
   this project, not a different "paired" variant). Holm over m=15,
   separately per (model, ecosystem), 4 families.
2. **Cross-ecosystem comparison of the gap itself** (test 2, the
   novel one, this is what actually asks "is the LLM's deviation from
   human writing ecosystem-dependent", without leaning on RQ1's null
   baseline). Per model, per dimension: Mann-Whitney U + Cliff's delta
   comparing Delta_java against Delta_python (independent samples now,
   different libraries). Holm over m=15, separately per model, 2
   families.

**Power caveat:** The RQ3 plan's own
text says "n=200 each, comfortably powered", that assumed the original
n=200/ecosystem full-corpus design. The actual
run was later scoped down to n=50/ecosystem for cost. Power at
n=50 is real but lower than what the RQ3 plan was written assuming; results here
should be read with that in mind, not with the "comfortably powered"
framing carried over uncritically.

Inputs:
    files/corpus/rq3/LIWC-22 Results - rq3_libraries - LIWC Analysis.csv

Outputs:
    files/corpus/rq3/rq3_stats_test1_within_ecosystem.csv
    files/corpus/rq3/rq3_stats_test2_cross_ecosystem.csv

Usage:
    venv/bin/python3 src/rq3/rq3_liwc_stats.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import (  # noqa: E402
    cliffs_delta, cliff_magnitude, holm_bonferroni, bootstrap_delta_ci,
    ALPHA, DELTA_THRESHOLD, LOCKED_DIMENSIONS, RNG_SEED,
)

RQ3_DIR = ROOT / "files" / "corpus" / "rq3"

# Default to the code-stripped corpus. The original run scored documents in
# which 36-56% of the LLM word content was source code against human READMEs
# that had been code-stripped during preprocessing (see
# rq3_build_libraries_csv_prose.py); those results are superseded, not
# comparable. --raw reproduces them for the threat-to-validity write-up.
LIWC_CSV_PROSE = RQ3_DIR / "LIWC-22 Results - rq3_libraries_prose - LIWC Analysis.csv"
LIWC_CSV_RAW = RQ3_DIR / "LIWC-22 Results - rq3_libraries - LIWC Analysis.csv"

LIWC_CSV = LIWC_CSV_PROSE
OUT_TEST1 = RQ3_DIR / "rq3_stats_test1_within_ecosystem.csv"
OUT_TEST2 = RQ3_DIR / "rq3_stats_test2_cross_ecosystem.csv"

MODELS = ["sonnet", "openai"]
ECOSYSTEMS = ["python", "java"]


def load_wide() -> pd.DataFrame:
    """One row per library x ecosystem, with human_<dim> and
    <model>_<dim> columns, a wide join of the three per-library source
    rows, so paired arithmetic (Delta = llm - human) is a plain column
    subtraction, matched by library rather than by row order."""
    if not LIWC_CSV.exists():
        raise SystemExit(f"LIWC output not found: {LIWC_CSV}")
    df = pd.read_csv(LIWC_CSV)
    for col in LOCKED_DIMENSIONS:
        if col not in df.columns:
            raise SystemExit(f"locked dimension {col!r} missing from LIWC output")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    human = df[df["source"] == "human"].set_index(["library", "ecosystem"])
    wide = human[LOCKED_DIMENSIONS].add_prefix("human_")
    for model in MODELS:
        m = df[df["source"] == model].set_index(["library", "ecosystem"])
        wide = wide.join(m[LOCKED_DIMENSIONS].add_prefix(f"{model}_"), how="inner")
    wide = wide.reset_index()
    return wide


def run_test1(wide: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    rows = []
    for model in MODELS:
        for eco in ECOSYSTEMS:
            sub = wide[wide["ecosystem"] == eco]
            n = len(sub)
            fam_rows = []
            for dim in LOCKED_DIMENSIONS:
                human_vals = sub[f"human_{dim}"].to_numpy()
                llm_vals = sub[f"{model}_{dim}"].to_numpy()
                delta = llm_vals - human_vals

                if np.all(delta == 0):
                    p_wilcoxon = 1.0
                else:
                    try:
                        _, p_wilcoxon = stats.wilcoxon(delta, alternative="two-sided")
                    except ValueError:
                        # scipy raises if too few non-zero differences at this n;
                        # not expected at n=50 but don't let one dimension crash
                        # the other 14.
                        p_wilcoxon = float("nan")

                d = cliffs_delta(llm_vals, human_vals)
                ci_lo, ci_hi = bootstrap_delta_ci(llm_vals, human_vals, rng)
                fam_rows.append({
                    "model": model, "ecosystem": eco, "dimension": dim, "n": n,
                    "median_delta": float(np.median(delta)),
                    "median_human": float(np.median(human_vals)),
                    "median_llm": float(np.median(llm_vals)),
                    "cliffs_delta": d,
                    "cliffs_delta_ci_lo": ci_lo,
                    "cliffs_delta_ci_hi": ci_hi,
                    "cliff_magnitude": cliff_magnitude(d),
                    "direction": "llm_higher" if d > 0 else "human_higher",
                    "wilcoxon_p": p_wilcoxon,
                })
            pvals = [r["wilcoxon_p"] for r in fam_rows]
            adj = holm_bonferroni([0.999999 if np.isnan(p) else p for p in pvals])
            for r, a in zip(fam_rows, adj):
                r["wilcoxon_p_holm"] = a
                r["passes_test1"] = (a < ALPHA) and (abs(r["cliffs_delta"]) >= DELTA_THRESHOLD)
            rows.extend(fam_rows)
    return pd.DataFrame(rows)


def run_test2(wide: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    rows = []
    for model in MODELS:
        java = wide[wide["ecosystem"] == "java"]
        py = wide[wide["ecosystem"] == "python"]
        fam_rows = []
        for dim in LOCKED_DIMENSIONS:
            delta_java = (java[f"{model}_{dim}"] - java[f"human_{dim}"]).to_numpy()
            delta_py = (py[f"{model}_{dim}"] - py[f"human_{dim}"]).to_numpy()

            _, p_mwu = stats.mannwhitneyu(delta_java, delta_py, alternative="two-sided")
            d = cliffs_delta(delta_java, delta_py)
            ci_lo, ci_hi = bootstrap_delta_ci(delta_java, delta_py, rng)
            fam_rows.append({
                "model": model, "dimension": dim,
                "n_java": len(delta_java), "n_python": len(delta_py),
                "median_delta_java": float(np.median(delta_java)),
                "median_delta_python": float(np.median(delta_py)),
                "cliffs_delta": d,
                "cliffs_delta_ci_lo": ci_lo,
                "cliffs_delta_ci_hi": ci_hi,
                "cliff_magnitude": cliff_magnitude(d),
                "direction": "java_gap_larger" if d > 0 else "python_gap_larger",
                "mwu_p": p_mwu,
            })
        pvals = [r["mwu_p"] for r in fam_rows]
        adj = holm_bonferroni(pvals)
        for r, a in zip(fam_rows, adj):
            r["mwu_p_holm"] = a
            r["passes_test2"] = (a < ALPHA) and (abs(r["cliffs_delta"]) >= DELTA_THRESHOLD)
        rows.extend(fam_rows)
    return pd.DataFrame(rows)


def main() -> None:
    global LIWC_CSV, OUT_TEST1, OUT_TEST2
    if "--raw" in sys.argv:
        LIWC_CSV = LIWC_CSV_RAW
        OUT_TEST1 = RQ3_DIR / "rq3_stats_test1_within_ecosystem_RAW.csv"
        OUT_TEST2 = RQ3_DIR / "rq3_stats_test2_cross_ecosystem_RAW.csv"
        print("*** --raw: scoring the ORIGINAL corpus (code not stripped). "
              "Superseded; for threat-to-validity comparison only. ***\n")
    print(f"Input: {LIWC_CSV.name}\n")

    wide = load_wide()
    print(f"Loaded {len(wide)} library rows (paired human + both models): "
          f"{wide['ecosystem'].value_counts().to_dict()}")

    t1 = run_test1(wide)
    t1.to_csv(OUT_TEST1, index=False)
    print(f"\nWrote {OUT_TEST1}")

    t2 = run_test2(wide)
    t2.to_csv(OUT_TEST2, index=False)
    print(f"Wrote {OUT_TEST2}")

    print("\n=== Test 1 (within-ecosystem, LLM vs human) — passes ===")
    p1 = t1[t1["passes_test1"]]
    if p1.empty:
        print("  none")
    else:
        print(p1[["model", "ecosystem", "dimension", "cliffs_delta",
                   "cliff_magnitude", "direction", "wilcoxon_p_holm"]]
              .to_string(index=False))

    print("\n=== Test 2 (cross-ecosystem gap comparison) — passes ===")
    p2 = t2[t2["passes_test2"]]
    if p2.empty:
        print("  none")
    else:
        print(p2[["model", "dimension", "cliffs_delta", "cliff_magnitude",
                   "direction", "mwu_p_holm"]].to_string(index=False))

    print(f"\nTest 1: {len(p1)}/{len(t1)} (model,ecosystem,dimension) cells pass "
          f"(Holm p<{ALPHA} AND |delta|>={DELTA_THRESHOLD})")
    print(f"Test 2: {len(p2)}/{len(t2)} (model,dimension) cells pass")


if __name__ == "__main__":
    main()
