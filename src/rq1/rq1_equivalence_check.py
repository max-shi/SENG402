"""
rq1_equivalence_check: is RQ1's null *evidence of absence*, or only absence of
evidence?

The distinction. Observing |delta| < 0.33 with a non-significant Holm-adjusted p
establishes only that qualifying evidence was not found; a genuinely small effect
and an underpowered test produce the same output. The stronger claim requires the
confidence interval itself to lie inside the equivalence region: if even the most
extreme value consistent with the data is below the threshold, the effect is
demonstrably smaller than the size pre-specified as meaningful.

This reads existing output. No new data, no re-scoring. The bootstrap CIs were
computed by confirmatory_liwc_stats.py in July because the locked plan specified
them; this script only checks containment. That is the point worth noting, the
pre-specified plan happened to produce exactly what equivalence testing needs,
months before the question was asked.

Two qualifications, both carried into the output:

* DELTA_THRESHOLD (0.33) was pre-specified as a *detection* threshold, not as an
  equivalence margin. Reusing it is defensible, same number, same meaning of
  "an effect worth caring about", but it is a reuse, not a bound set in advance
  for this purpose.
* Conventional TOST at alpha=0.05 corresponds to checking a 90% interval. The
  stored CIs are 95%, so every verdict here is more conservative than the
  convention requires. Nothing is overstated by using them.

Usage:
    venv/bin/python3 src/rq1/rq1_equivalence_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import DELTA_THRESHOLD  # noqa: E402

FRAMES = [
    ("n=1000 per ecosystem", "frame_n2000"),
    ("n=200 dedup-corrected", "frame_locked_corrected"),
    ("n=200 original", "frame_locked"),
]
OUT = ROOT / "files" / "analysis" / "rq1_equivalence_check.csv"


def main() -> None:
    T = DELTA_THRESHOLD
    print(f"Equivalence region: [-{T}, +{T}]  (pre-specified detection threshold,")
    print("reused as the smallest effect size of interest)\n")

    rows = []
    for label, frame in FRAMES:
        path = ROOT / "files" / "corpus" / frame / "confirmatory_stats_results.csv"
        if not path.exists():
            print(f"{label}: results file not found, skipped")
            continue
        df = pd.read_csv(path)
        lo = next(c for c in df.columns if "ci_lo" in c)
        hi = next(c for c in df.columns if "ci_hi" in c)

        df["ci_inside_region"] = (df[lo] > -T) & (df[hi] < T)
        n_in = int(df.ci_inside_region.sum())
        print(f"{label:24s}  {n_in}/{len(df)} dimensions with the whole 95% CI inside")
        for _, r in df[~df.ci_inside_region].iterrows():
            print(f"      outside: {r.dimension:11s} "
                  f"delta={r.cliffs_delta:+.3f}  CI=[{r[lo]:+.3f}, {r[hi]:+.3f}]")
        for _, r in df.iterrows():
            rows.append({
                "frame": label, "dimension": r.dimension,
                "cliffs_delta": round(float(r.cliffs_delta), 4),
                "ci_lo": round(float(r[lo]), 4), "ci_hi": round(float(r[hi]), 4),
                "ci_inside_equivalence_region": bool(r.ci_inside_region),
            })
        print()

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Wrote {OUT}")
    print("\nReading: a dimension whose entire interval sits inside the region has a")
    print("demonstrably small effect. One whose interval crosses a bound is")
    print("inconclusive - neither a qualifying effect nor provably absent.")


if __name__ == "__main__":
    main()
