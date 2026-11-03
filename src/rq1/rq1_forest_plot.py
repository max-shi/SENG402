"""
rq1_forest_plot: the RQ1 confirmatory forest, with the equivalence region drawn.

Why this exists. report/figures/rq1_forest.png was a renamed copy of
02_forest_cliffs_delta.png, the May pilot screening figure: 13 shortlisted
dimensions at |delta| = 0.4-0.6, which is what a *pilot* selects for. Dropping it
into the report beside the sentence "no dimension clears |delta| >= 0.33" would
have contradicted the text in the most visible way available, since almost every
interval in it sits past the threshold.

This plots the confirmatory result instead: all 15 locked dimensions at
n=1000/ecosystem, ordered by effect size, with the pre-specified decision
threshold and the equivalence region both marked. The figure then carries RQ1's
two claims at once -- nothing reaches the threshold (Layer 1), and 14/15
intervals lie wholly inside the equivalence region (evidence of absence rather
than absence of evidence). emo_anger, the one exception on both counts, is
labelled as such.

Outputs:
    files/analysis/figures/rq1_confirmatory_forest.png
    report/figures/rq1_forest.png   (same image, overwriting the pilot copy)

Usage:
    venv/bin/python3 src/rq1/rq1_forest_plot.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import pandas as pd               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATS = (ROOT / "files" / "corpus" / "frame_n2000"
         / "confirmatory_stats_results.csv")
OUT = ROOT / "files" / "analysis" / "figures" / "rq1_confirmatory_forest.png"
REPORT_COPY = ROOT / "report" / "figures" / "rq1_forest.png"

THRESHOLD = 0.33


def main() -> None:
    d = pd.read_csv(STATS).sort_values("cliffs_delta").reset_index(drop=True)
    n = int(d.n_java.iloc[0])

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.axvspan(-THRESHOLD, THRESHOLD, color="#4C72B0", alpha=0.08, zorder=0)
    for x in (-THRESHOLD, THRESHOLD):
        ax.axvline(x, color="#4C72B0", ls="--", lw=1.2, zorder=1)
    ax.axvline(0, color="black", lw=1.0, zorder=1)

    for i, r in d.iterrows():
        # Inside the equivalence region = the interval itself supports "no
        # effect of the pre-specified size", not merely a failure to detect one.
        contained = (r.cliffs_delta_ci_lo >= -THRESHOLD
                     and r.cliffs_delta_ci_hi <= THRESHOLD)
        colour = "#4C72B0" if contained else "#C44E52"
        ax.plot([r.cliffs_delta_ci_lo, r.cliffs_delta_ci_hi], [i, i],
                color=colour, lw=2.0, solid_capstyle="round", zorder=3)
        ax.scatter(r.cliffs_delta, i, s=42, color=colour, edgecolor="black",
                   linewidth=0.5, zorder=4)

    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d.dimension, fontsize=9)
    ax.set_ylim(-0.8, len(d) - 0.2)
    ax.set_xlim(-0.75, 0.75)
    ax.set_xlabel(r"Cliff's $\delta$   (negative = Python higher, "
                  "positive = Java higher)", fontsize=9)
    ax.set_title(f"RQ1: Java vs Python, all 15 locked dimensions "
                 f"($n={n:,}$/ecosystem)\n"
                 r"shaded = equivalence region $|\delta| < 0.33$; "
                 "red = interval not contained", fontsize=10)
    ax.grid(axis="x", alpha=0.25)
    n_contained = int(((d.cliffs_delta_ci_lo >= -THRESHOLD)
                       & (d.cliffs_delta_ci_hi <= THRESHOLD)).sum())
    # Top-left: the only corner with no interval in it (the largest negative
    # effect, emo_anger, sits on the bottom row).
    ax.text(0.015, 0.97, f"{n_contained}/15 intervals wholly inside the "
            f"equivalence region\n0/15 reach the decision threshold",
            transform=ax.transAxes, fontsize=8.5, va="top",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#999999", lw=0.6))

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    plt.close(fig)
    REPORT_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(OUT, REPORT_COPY)
    print(f"Wrote {OUT}\nCopied to {REPORT_COPY}")
    print(f"{n_contained}/15 intervals contained; "
          f"{int((d.cliffs_delta.abs() >= THRESHOLD).sum())}/15 reach |delta| >= {THRESHOLD}")


if __name__ == "__main__":
    main()
