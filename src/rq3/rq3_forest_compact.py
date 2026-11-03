"""
rq3_forest_compact: column-width version of the RQ3 test 1 forest plot for
the report body: only the five construct-clean dimensions of Table I, no
in-figure title (the LaTeX caption carries it), drawn at the IEEE column
width (3.5 in) so fonts render at their true size instead of being scaled
down. The full 15-dimension figure from rq3_plots.py stays in the appendix.

Outputs:
    report/figures/rq3_test1_forest_compact.png

Usage:
    venv/bin/python3 src/rq3/rq3_forest_compact.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq3_plots import (  # noqa: E402
    TEST1_CSV, MODELS, MODEL_LABELS, MODEL_COLORS, ECO_ORDER,
    MAGNITUDE_THRESHOLDS, _bold_yticklabels,
)

OUT = ROOT / "report" / "figures" / "rq3_test1_forest_compact.png"

# Table I order, top to bottom.
CLEAN_DIMS = ["BigWords", "WPS", "ipron", "certitude", "tentat"]


def main() -> None:
    df = pd.read_csv(TEST1_CSV)
    plt.rcParams.update({"font.size": 7})

    fig, axes = plt.subplots(1, 2, figsize=(3.5, 1.75), sharey=True)
    ys = np.arange(len(CLEAN_DIMS))[::-1]
    offset = 0.15
    passed = set()

    for ax, eco in zip(axes, ECO_ORDER):
        sub = df[df.ecosystem == eco].set_index(["dimension", "model"])
        for model, off in zip(MODELS, (offset, -offset)):
            for y, dim in zip(ys, CLEAN_DIMS):
                r = sub.loc[(dim, model)]
                ax.plot([r.cliffs_delta_ci_lo, r.cliffs_delta_ci_hi], [y + off] * 2,
                        color=MODEL_COLORS[model], lw=1)
                ax.plot(r.cliffs_delta, y + off, "o", color=MODEL_COLORS[model],
                        markersize=3.5, markeredgecolor="black", markeredgewidth=0.3,
                        label=MODEL_LABELS[model] if y == ys[0] else None)
                if r.passes_test1:
                    passed.add(dim)
        for thr in MAGNITUDE_THRESHOLDS:
            ax.axvline(thr, ls=":", color="grey", lw=0.4)
            ax.axvline(-thr, ls=":", color="grey", lw=0.4)
        ax.axvline(0, color="black", lw=0.5)
        ax.set_xlim(-1.05, 1.05)
        ax.set_xticks([-1, -0.5, 0, 0.5, 1])
        ax.set_title(eco.capitalize(), fontsize=7, pad=2)
        ax.set_yticks(ys)
        ax.set_yticklabels(CLEAN_DIMS)
        ax.tick_params(length=2, pad=1.5)

    # Bold = clears the decision rule in at least one family (as in Table I).
    _bold_yticklabels(axes[0], passed)

    fig.supxlabel("Cliff's $\\delta$ (negative = human higher)", fontsize=7, y=0.02)
    # Python panel's top-left is empty (BigWords sits at the far right).
    h, l = axes[0].get_legend_handles_labels()
    axes[1].legend(h, ["Sonnet 5", "GPT-5.6"], loc="upper left", ncol=1, fontsize=5.5,
                   frameon=True, framealpha=0.9, handletextpad=0.1,
                   borderpad=0.25, labelspacing=0.15, borderaxespad=0.2)
    fig.tight_layout(pad=0.3, w_pad=0.6)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
