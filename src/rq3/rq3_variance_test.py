"""
rq3_variance_test: is the *spread* of LIWC scores different between human
and LLM documentation? (Not the location shift that tests 1 and 2 measure.)

Motivation. The violin grids show human and LLM distributions with visibly
different widths, in addition to different medians. Tests 1 and 2 are
location tests (Wilcoxon / Mann-Whitney on medians and on Delta); neither
says anything about dispersion. This script tests dispersion directly, so
any claim about "spread" is a measured result rather than a read off a
violin plot.

Design decisions, and why:

* **Brown-Forsythe, not Levene's-on-the-mean, not Bartlett's.**
  Brown-Forsythe is Levene's test centred on the *median* rather than the
  mean. LIWC dimension scores here are strongly right-skewed with hard
  floors at zero (many dimensions have median 0.00), which is exactly the
  regime where mean-centred Levene's and especially Bartlett's inflate
  type-I error. Median-centring is the robust variant, and it is the one
  consistent with this project's non-parametric convention everywhere else
  (Wilcoxon / Mann-Whitney / Cliff's delta).

* **Within ecosystem, never pooled.** Pooling Java and Python before
  measuring spread would manufacture bimodality on any dimension where the
  two ecosystems differ in location, which is precisely the set of
  dimensions RQ3 test 2 flagged. A pooled "LLM is more spread out" result
  on those dimensions would be an artefact of the ecosystem gap, not a
  fact about within-ecosystem dispersion.

* **Both raw SD ratio and coefficient of variation.** A dimension where the
  LLM scores 10x higher on average will usually also show a larger absolute
  SD without being "more variable" in any interesting sense. The CV ratio
  (SD/mean) is reported alongside so scale-driven differences are visible
  rather than being mistaken for dispersion differences. IQR ratio is
  reported too as a fully rank-based check.

* **Holm-Bonferroni within each (model, ecosystem) family, m=15.** Same
  correction and alpha as tests 1 and 2, so the decision rule is
  consistent across the whole RQ3 analysis.

Caveat carried into the output. `emotion`, `emo_neg` and `emo_sad` are
known-invalid in this corpus (see rq3_affect_token_check.py and
files/analysis/construct_validity_check.md): on LLM documents they
collapse to a single measurement dominated by the token "java". Any
dispersion result on those three dimensions describes the dispersion of
that artefact, not of affective language, and is flagged accordingly in
the output rather than being silently reported alongside valid dimensions.

Outputs:
    files/corpus/rq3/rq3_stats_test4_variance.csv

Usage:
    venv/bin/python3 src/rq3/rq3_variance_test.py
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
    holm_bonferroni, ALPHA, LOCKED_DIMENSIONS,
)

LIWC_CSV = ROOT / "files" / "corpus" / "rq3" / "LIWC-22 Results - rq3_libraries_prose - LIWC Analysis.csv"
OUT = ROOT / "files" / "corpus" / "rq3" / "rq3_stats_test4_variance.csv"

MODELS = ["sonnet", "openai"]
ECOSYSTEMS = ["java", "python"]

# Flagged by the construct-validity work: on LLM docs these collapse into
# one artefact measurement. Reported, but never interpreted as affect.
INVALID_DIMS = {"emotion", "emo_neg", "emo_sad"}


def main() -> None:
    df = pd.read_csv(LIWC_CSV)
    for col in LOCKED_DIMENSIONS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    rows = []
    for model in MODELS:
        for eco in ECOSYSTEMS:
            fam = []
            for dim in LOCKED_DIMENSIONS:
                h = df[(df.ecosystem == eco) & (df.source == "human")][dim].to_numpy()
                l = df[(df.ecosystem == eco) & (df.source == model)][dim].to_numpy()

                # Brown-Forsythe == Levene centred on the median
                try:
                    stat, p = stats.levene(h, l, center="median")
                except ValueError:
                    stat, p = float("nan"), float("nan")

                sd_h, sd_l = h.std(ddof=1), l.std(ddof=1)
                iqr_h = np.subtract(*np.percentile(h, [75, 25]))
                iqr_l = np.subtract(*np.percentile(l, [75, 25]))
                cv_h = sd_h / h.mean() if h.mean() else np.nan
                cv_l = sd_l / l.mean() if l.mean() else np.nan

                fam.append({
                    "model": model, "ecosystem": eco, "dimension": dim,
                    "n_per_group": len(h),
                    "sd_human": round(float(sd_h), 4),
                    "sd_llm": round(float(sd_l), 4),
                    "sd_ratio_llm_over_human": round(float(sd_l / sd_h), 3)
                    if sd_h else np.nan,
                    "iqr_human": round(float(iqr_h), 4),
                    "iqr_llm": round(float(iqr_l), 4),
                    "cv_human": round(float(cv_h), 3),
                    "cv_llm": round(float(cv_l), 3),
                    "cv_ratio_llm_over_human": round(float(cv_l / cv_h), 3)
                    if cv_h and not np.isnan(cv_h) else np.nan,
                    "more_spread": "llm" if sd_l > sd_h else "human",
                    "brown_forsythe_p": p,
                    "construct_valid": dim not in INVALID_DIMS,
                })

            adj = holm_bonferroni([1.0 if np.isnan(r["brown_forsythe_p"])
                                   else r["brown_forsythe_p"] for r in fam])
            for r, a in zip(fam, adj):
                r["brown_forsythe_p_holm"] = a
                r["significant"] = a < ALPHA
            rows.extend(fam)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"Wrote {OUT}\n")

    valid = out[out.construct_valid]
    print("=== Significant dispersion differences (construct-valid dims only) ===")
    sig = valid[valid.significant]
    if sig.empty:
        print("  none")
    else:
        print(sig[["model", "ecosystem", "dimension", "sd_human", "sd_llm",
                   "sd_ratio_llm_over_human", "cv_ratio_llm_over_human",
                   "more_spread", "brown_forsythe_p_holm"]].to_string(index=False))

    print("\n=== Direction tally, construct-valid dimensions only (12 dims x 4 families) ===")
    for model in MODELS:
        for eco in ECOSYSTEMS:
            s = valid[(valid.model == model) & (valid.ecosystem == eco)]
            ss = s[s.significant]
            print(f"  {model:7s} {eco:7s}  significant: {len(ss):2d}/12   "
                  f"of those, LLM more spread: {(ss.more_spread=='llm').sum():2d}, "
                  f"human more spread: {(ss.more_spread=='human').sum():2d}")

    print("\n=== Flagged dims (construct-invalid — dispersion of an artefact) ===")
    inv = out[(~out.construct_valid) & (out.significant)]
    print(f"  {len(inv)}/24 cells significant; not interpretable as affect.")


if __name__ == "__main__":
    main()
