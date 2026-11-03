"""
rq2_variance_decomposition: how does intra-ecosystem variation compare to
inter-ecosystem differences?

This answers the second clause of RQ2 directly. RQ1 asks whether ecosystems
differ; RQ2's domain-stratified analysis asks whether any apparent ecosystem
effect is really domain composition. Neither quantifies the *relative size* of
within- versus between-ecosystem variation, which is what the question actually
asks.

Method. For each locked dimension, decompose total variance into a between-
ecosystem component and a within-ecosystem component, and report
eta^2 = SS_between / SS_total. This is the proportion of all observed variation
attributable to which ecosystem a library belongs to; 1 - eta^2 is the
proportion attributable to differences between libraries within an ecosystem.

Why this framing matters. RQ1 returns a null under the pre-specified decision
rule, and a null is easy to misread as "we could not detect a difference"
(i.e. a power problem). The decomposition converts it into a positive,
quantitative statement: the between-ecosystem component is not merely
undetectable, it is a small fraction of the variation that exists. That is a
claim about effect magnitude rather than about statistical detectability, and
it does not depend on the significance threshold at all.

Corpus: the duplication-corrected confirmatory frame (n=200 per ecosystem).

Output:
    files/analysis/rq2_variance_decomposition.csv

Usage:
    venv/bin/python3 src/rq2/rq2_variance_decomposition.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import LOCKED_DIMENSIONS  # noqa: E402

LIWC_CSV = (ROOT / "files" / "corpus" / "frame_locked_corrected"
            / "LIWC-22 Results - libraries - LIWC Analysis.csv")
OUT = ROOT / "files" / "analysis" / "rq2_variance_decomposition.csv"


def main() -> None:
    df = pd.read_csv(LIWC_CSV)
    print(f"Corpus: {len(df)} libraries {df.ecosystem.value_counts().to_dict()}\n")

    rows = []
    for dim in LOCKED_DIMENSIONS:
        g = df.assign(v=pd.to_numeric(df[dim], errors="coerce")).dropna(subset=["v"])
        grand = g.v.mean()
        ss_total = ((g.v - grand) ** 2).sum()
        ss_between = sum(len(sub) * (sub.v.mean() - grand) ** 2
                         for _, sub in g.groupby("ecosystem"))
        eta2 = ss_between / ss_total if ss_total else 0.0
        sds = {eco: sub.v.std() for eco, sub in g.groupby("ecosystem")}
        rows.append({
            "dimension": dim,
            "eta2_between_ecosystem": round(float(eta2), 5),
            "pct_variance_within": round(float(100 * (1 - eta2)), 2),
            "sd_java": round(float(sds.get("java", np.nan)), 3),
            "sd_python": round(float(sds.get("python", np.nan)), 3),
            "n": len(g),
        })

    out = pd.DataFrame(rows).sort_values("eta2_between_ecosystem", ascending=False)
    out.to_csv(OUT, index=False)

    print(out.to_string(index=False))
    e = out.eta2_between_ecosystem
    print(f"\nmean eta^2 between ecosystems : {e.mean():.4f}")
    print(f"max                           : {e.max():.4f} ({out.iloc[0].dimension})")
    print(f"dimensions with eta^2 > 0.05  : {(e > 0.05).sum()}/15")
    print(f"\nOn average {100 * (1 - e.mean()):.1f}% of the variance in these dimensions")
    print("lies between libraries within an ecosystem, not between ecosystems.")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
