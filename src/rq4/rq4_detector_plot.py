"""
rq4_detector_plot: the RQ4 authorship detector in one figure.

The detector is a single cut-point on a single feature (rq4_detector.py:
BigWords > 34.5% => generated), so the clearest way to show it is the feature's
own distributions with that line drawn, rather than a bar chart of macro-F1
that hides where the errors come from.

Panel A: the three distributions the rule has to separate, human READMEs,
generated READMEs, and the external human corpus the rule was never fitted to
(RQ1/RQ2 frame, n=400, full crawled documentation rather than READMEs). Every
external-corpus document to the right of the line is a false positive, so the
panel shows in-corpus separation and out-of-sample specificity together. Violin
+ strip, matching rq3_plots.py / confirmatory_plots.py, with ECO_COLORS reserved
for ecosystems elsewhere in the project and deliberately not reused here: these
groups are sources, not ecosystems.

Panel B: macro-F1 under the three README-scope subsets of
rq3_readme_scope_audit.py, against the permutation null. This is the robustness
claim, in the previous corpus, 29 of 100 human READMEs were graded a severe
mismatch and 10 partial, and the rule improves rather than degrades when they are removed. Error
bars are SD over the 10 CV repeats.

Inputs:
    files/corpus/rq3/rq3_libraries_prose.csv
    files/corpus/frame_locked/libraries.csv
    files/analysis/rq4_detector_validation.csv   (rq4_detector.py --validate)

Outputs:
    files/analysis/figures/rq4_02_detector_bigwords.png

Usage:
    venv/bin/python3 src/rq4/rq4_detector_plot.py
"""
from __future__ import annotations

import csv as _csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq4_detector import (  # noqa: E402
    EXTERNAL_HUMAN, OUT_VALIDATION, best_threshold, features, load_corpus,
)

FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUT = FIG_DIR / "rq4_02_detector_bigwords.png"

HUMAN_C, GEN_C, EXT_C = "#4c72b0", "#c44e52", "#8c8c8c"
RNG = np.random.default_rng(402)


def panel_a(ax, df: pd.DataFrame, ext: pd.DataFrame, thr: float) -> None:
    groups = [
        ("Human README\n(this corpus)", df[df.source == "human"].BigWords.to_numpy(), HUMAN_C),
        ("Generated README\n(2 models)", df[df.source != "human"].BigWords.to_numpy(), GEN_C),
        ("Human docs\n(external, n=400)", ext.BigWords.to_numpy(), EXT_C),
    ]
    parts = ax.violinplot([g[1] for g in groups], positions=range(len(groups)),
                          widths=0.75, showextrema=False)
    for body, (_, _, colour) in zip(parts["bodies"], groups):
        body.set_facecolor(colour)
        body.set_alpha(0.30)
        body.set_edgecolor(colour)

    for i, (_, vals, colour) in enumerate(groups):
        jitter = RNG.uniform(-0.11, 0.11, len(vals))
        ax.scatter(i + jitter, vals, s=7, color=colour, alpha=0.45, linewidths=0)
        ax.hlines(np.median(vals), i - 0.28, i + 0.28, color=colour, lw=2.2, zorder=3)

    ax.axhline(thr, color="black", lw=1.4, ls="--", zorder=4)
    # Blended transform: x in axes fraction so the label can't fall outside the
    # data range and be clipped, y pinned to the threshold in data units.
    ax.text(0.985, thr + 0.4, f"decision threshold  BigWords > {thr:.1f}%",
            transform=ax.get_yaxis_transform(), ha="right", va="bottom",
            fontsize=8.5, zorder=5)

    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups], fontsize=9)
    ax.set_ylabel("BigWords (% of words with 7+ characters)")
    ax.set_title("A. What the rule separates", fontsize=10, loc="left")
    ax.grid(axis="y", ls=":", alpha=0.4)
    ax.set_axisbelow(True)

    # Error counts, stated on the figure rather than left to the caption.
    for i, (_, vals, _) in enumerate(groups):
        wrong = (vals <= thr).sum() if i == 1 else (vals > thr).sum()
        ax.annotate(f"{wrong}/{len(vals)} on the wrong side",
                    xy=(i, ax.get_ylim()[0]), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=8, color="#444444")


def panel_b(ax, val: pd.DataFrame) -> None:
    s = val[val.check == "readme_scope"]
    x = np.arange(len(s))
    ax.bar(x, s.macro_f1, yerr=s.macro_f1_sd, width=0.55, color="#4c72b0",
           alpha=0.85, capsize=4, zorder=3)
    ax.axhline(float(s.permutation_null.mean()), color="#c44e52", lw=1.3, ls="--", zorder=4)
    ax.annotate("permutation null", xy=(len(s) - 0.5, float(s.permutation_null.mean())),
                xytext=(0, 4), textcoords="offset points", ha="right",
                fontsize=8.5, color="#c44e52")

    for xi, (f1, n, nh, ng) in enumerate(zip(s.macro_f1, s.n, s.n_human, s.n_generated)):
        ax.annotate(f"{f1:.3f}", xy=(xi, f1), xytext=(0, 7), textcoords="offset points",
                    ha="center", fontsize=9, fontweight="bold")
        ax.annotate(f"n={int(n)}\n({int(nh)}h/{int(ng)}g)", xy=(xi, 0.02),
                    ha="center", va="bottom", fontsize=8, color="#444444")

    ax.set_xticks(x)
    ax.set_xticklabels(s.subset, fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("macro-F1 (5-fold CV x 10 repeats)")
    ax.set_title("B. Robustness to README-scope contamination", fontsize=10, loc="left")
    ax.grid(axis="y", ls=":", alpha=0.4)
    ax.set_axisbelow(True)


def main() -> None:
    if not OUT_VALIDATION.exists():
        raise SystemExit(f"{OUT_VALIDATION} not found — run "
                         "rq4_detector.py --validate first")
    _csv.field_size_limit(sys.maxsize)

    df = load_corpus()
    thr = best_threshold(df.BigWords.to_numpy(), df.is_generated.to_numpy())
    ext = pd.read_csv(EXTERNAL_HUMAN)
    ext["BigWords"] = [features(t)["BigWords"] for t in ext.text]
    val = pd.read_csv(OUT_VALIDATION)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4),
                             gridspec_kw={"width_ratios": [1.35, 1]})
    panel_a(axes[0], df, ext, thr)
    panel_b(axes[1], val)
    fig.tight_layout()
    fig.suptitle("RQ4 — authorship detection from one feature", fontsize=12, y=0.99)
    fig.subplots_adjust(top=0.89)
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
