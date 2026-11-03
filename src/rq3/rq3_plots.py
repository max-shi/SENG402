"""
rq3_plots: visualisations for the RQ3 (human vs LLM-generated docs)
statistical results, in the same visual language as the existing figures
in this project, not just "similar colors," but the same chart *types*.

1. rq3_01_test2_forest.png / rq3_01b_test1_forest.png, forest plots
   (point = sample Cliff's delta, horizontal bar = bootstrap 95% CI),
   directly mirroring liwc_plots.py's _draw_forest(), same dotted
   magnitude-threshold gridlines (0.147/0.33/0.474), same solid zero
   line, same bold-label-for-passing convention. Went through two
   worse designs first (a dumbbell chart color-coded by a pass/fail
   flag with no visible threshold, then a bar chart with a shaded
   threshold band) before checking what this project's own existing
   effect-size figure (02_forest_cliffs_delta.png) actually looks like
   and matching that instead of inventing a third style, worth noting
   for next time: check for an existing precedent before designing a
   new chart type.
2. rq3_02_violin_strip_<model>.png, mirrors 09_violin_strip_confirmatory
   .png's per-dimension violin+strip grid: dots colored by *domain*
   (same DOMAIN_COLORS, same legend), not by ecosystem, an earlier
   version colored dots to match their own violin, which added no
   information and made the chart look flatter than the RQ1/RQ2
   original. Each panel compares 4 groups (human-java, llm-java,
   human-python, llm-python) instead of 2 (java, python).

Inputs:
    files/corpus/rq3/LIWC-22 Results - rq3_libraries - LIWC Analysis.csv
    files/corpus/rq3/rq3_stats_test1_within_ecosystem.csv
    files/corpus/rq3/rq3_stats_test2_cross_ecosystem.csv

Outputs (files/analysis/figures/, rq3_-prefixed to stay distinguishable
from the RQ1/RQ2 sequence they otherwise number alongside):
    rq3_01_test2_forest.png
    rq3_01b_test1_forest.png
    rq3_02_violin_strip_sonnet.png
    rq3_02_violin_strip_openai.png

Usage:
    venv/bin/python3 src/rq3/rq3_plots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import LOCKED_DIMENSIONS, DELTA_THRESHOLD  # noqa: E402
from confirmatory_plots import ECO_COLORS, DOMAIN_COLORS  # noqa: E402

# Same three magnitude boundaries as liwc_plots._draw_forest (negligible
# /small/medium/large per Romano et al. 2006), the dotted gridlines
# every forest plot in this project uses, not a shaded box.
MAGNITUDE_THRESHOLDS = (0.147, 0.33, 0.474)


def _bold_yticklabels(ax, bold_set: set[str]) -> None:
    """Set y-tick label font weight directly on the Text objects rather
    than wrapping labels in matplotlib mathtext ($\\bf{...}$), the
    mathtext route (the original liwc_plots._draw_forest's approach)
    silently misrenders any label containing an underscore, since
    mathtext reads '_' as its subscript operator: 'emo_sad' inside
    $\\bf{}$ renders as "emo" with a subscripted "s" followed by "ad",
    not as bold "emo_sad". Half the locked dimensions have underscores
    (emo_neg, emo_anger, emo_sad), so this isn't an edge case here."""
    for label in ax.get_yticklabels():
        if label.get_text() in bold_set:
            label.set_fontweight("bold")

FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

RQ3_DIR = ROOT / "files" / "corpus" / "rq3"
LIWC_CSV = RQ3_DIR / "LIWC-22 Results - rq3_libraries_prose - LIWC Analysis.csv"
TEST1_CSV = RQ3_DIR / "rq3_stats_test1_within_ecosystem.csv"
TEST2_CSV = RQ3_DIR / "rq3_stats_test2_cross_ecosystem.csv"

MODELS = ["sonnet", "openai"]
MODEL_LABELS = {"sonnet": "Claude Sonnet 5", "openai": "GPT-5.6-terra"}
ECO_ORDER = ["java", "python"]

# Same ColorBrewer Dark2 family as ECO_COLORS (java=#d95f02, python=#1b9e77),
# extended with its next two hues so the whole figure set stays visually
# one system rather than switching palettes between chart types.
MODEL_COLORS = {"sonnet": "#7570b3", "openai": "#e7298a"}


# -------------------------------------------------------------------------
# Figure 1: test 2, forest plot of Cliff's delta (Delta_java vs
# Delta_python), one panel per model. Direct analog of
# liwc_plots._draw_forest / 02_forest_cliffs_delta.png.
# -------------------------------------------------------------------------
def plot_test2_forest() -> None:
    df = pd.read_csv(TEST2_CSV)

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 0.34 * len(LOCKED_DIMENSIONS) + 1.8))

    for ax, model in zip(axes, MODELS):
        sub = df[df["model"] == model].set_index("dimension").loc[LOCKED_DIMENSIONS]
        sub = sub.loc[sub["cliffs_delta"].sort_values().index]
        ys = np.arange(len(sub))

        for y, (dim, r) in zip(ys, sub.iterrows()):
            colour = ECO_COLORS["java"] if r["cliffs_delta"] > 0 else ECO_COLORS["python"]
            ax.plot([r["cliffs_delta_ci_lo"], r["cliffs_delta_ci_hi"]], [y, y],
                    color=colour, lw=1.5)
            ax.plot(r["cliffs_delta"], y, "o", color=colour, markersize=7,
                    markeredgecolor="black", markeredgewidth=0.5)

        for thr in MAGNITUDE_THRESHOLDS:
            ax.axvline(thr, ls=":", color="grey", lw=0.6)
            ax.axvline(-thr, ls=":", color="grey", lw=0.6)
        ax.axvline(0, color="black", lw=0.6)

        ax.set_yticks(ys)
        labels = sub.index.tolist()
        passing = set(sub.index[sub["passes_test2"]])
        ax.set_yticklabels(labels)
        _bold_yticklabels(ax, passing)
        ax.set_xlabel("Cliff's $\\delta$\n(negative = Python gap larger, "
                      "positive = Java gap larger)")
        ax.set_xlim(-1.05, 1.05)
        ax.set_title(MODEL_LABELS[model], fontsize=12)

    # tight_layout() is called *before* suptitle exists, then the top
    # margin is trimmed by hand with subplots_adjust, calling
    # tight_layout(rect=...) with a suptitle already attached makes it
    # auto-reserve its own (generous) padding for that suptitle on top of
    # whatever the rect asks for, so the two reservations stack and blow
    # out the space between the title and the panels.
    fig.tight_layout()
    fig.suptitle(
        "RQ3 test 2 — is the LLM-vs-human gap itself ecosystem-dependent?\n"
        "points = sample $\\delta$ comparing $\\Delta_{java}$ vs $\\Delta_{python}$, "
        "bars = bootstrap 95% CI, n_boot=2000  (bold = passes test 2)",
        fontsize=12.5, y=0.99)
    fig.subplots_adjust(top=0.88)
    out = FIG_DIR / "rq3_01_test2_forest.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figure 1b: test 1, forest plot of Cliff's delta (LLM vs human), one
# panel per ecosystem, both models shown on each panel (grouped forest
# plot: two offset point+CI rows per dimension). This is where "human"
# is actually visible: 0 on this chart literally means "matches the real
# human author".
# -------------------------------------------------------------------------
def plot_test1_forest() -> None:
    df = pd.read_csv(TEST1_CSV)

    fig, axes = plt.subplots(1, 2, figsize=(10, 0.5 * len(LOCKED_DIMENSIONS) + 1.8))
    row_offset = 0.16

    for ax, eco in zip(axes, ECO_ORDER):
        sub = df[df["ecosystem"] == eco]
        wide = sub.pivot(
            index="dimension", columns="model",
            values=["cliffs_delta", "cliffs_delta_ci_lo", "cliffs_delta_ci_hi", "passes_test1"]
        ).loc[LOCKED_DIMENSIONS]
        order = wide["cliffs_delta"].abs().max(axis=1).sort_values().index
        wide = wide.loc[order]
        ys = np.arange(len(wide))

        for model, offset in zip(MODELS, (row_offset, -row_offset)):
            d = wide[("cliffs_delta", model)]
            lo = wide[("cliffs_delta_ci_lo", model)]
            hi = wide[("cliffs_delta_ci_hi", model)]
            for y, dv, lov, hiv in zip(ys, d, lo, hi):
                ax.plot([lov, hiv], [y + offset, y + offset],
                        color=MODEL_COLORS[model], lw=1.5)
            ax.plot(d, ys + offset, "o", color=MODEL_COLORS[model], markersize=6.5,
                    markeredgecolor="black", markeredgewidth=0.5,
                    label=MODEL_LABELS[model], linestyle="")

        for thr in MAGNITUDE_THRESHOLDS:
            ax.axvline(thr, ls=":", color="grey", lw=0.6)
            ax.axvline(-thr, ls=":", color="grey", lw=0.6)
        ax.axvline(0, color="black", lw=0.6)
        ax.text(0, len(wide) - 0.4, " = human", fontsize=8, style="italic", va="bottom")

        any_pass = wide["passes_test1"].any(axis=1)
        ax.set_yticks(ys)
        ax.set_yticklabels(list(wide.index))
        _bold_yticklabels(ax, set(wide.index[any_pass]))
        ax.set_xlabel("Cliff's $\\delta$  (negative = human higher, positive = LLM higher)")
        ax.set_xlim(-1.05, 1.05)
        ax.set_title(eco.capitalize(), fontsize=12)
        ax.legend(loc="lower right", frameon=True, fontsize=8)

    # Same tight_layout()-then-subplots_adjust ordering as
    # plot_test2_forest(), for the same reason (see comment there).
    fig.tight_layout()
    fig.suptitle(
        "RQ3 test 1 — does the LLM write differently from the real human author?\n"
        "points = sample $\\delta$, bars = bootstrap 95% CI, n_boot=2000  "
        "(bold = passes test 1 for at least one model)", fontsize=12.5, y=0.99)
    fig.subplots_adjust(top=0.89)
    out = FIG_DIR / "rq3_01b_test1_forest.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figure 2: violin + strip grid, human vs LLM x java vs python, all 15
# locked dimensions, one file per model. Direct analog of
# confirmatory_plots.plot_violin_strip_confirmatory().
# -------------------------------------------------------------------------
def plot_violin_strip(model: str) -> None:
    liwc = pd.read_csv(LIWC_CSV)
    t1 = pd.read_csv(TEST1_CSV)
    t1_model = t1[t1["model"] == model].set_index(["ecosystem", "dimension"])

    # Sort panels by the larger of the two ecosystems' |Cliff's delta| for
    # this model, same "most-interesting-first" ordering principle as
    # confirmatory_plots' dims_sorted.
    max_abs_delta = (
        t1_model["cliffs_delta"].abs().groupby(level="dimension").max()
    )
    dims_sorted = max_abs_delta.sort_values(ascending=False).index.tolist()

    groups = [("human", "java"), (model, "java"),
              ("human", "python"), (model, "python")]
    group_labels = ["human\n(java)", "LLM\n(java)", "human\n(python)", "LLM\n(python)"]

    ncols = 3
    nrows = int(np.ceil(len(dims_sorted) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 3.6 * nrows))
    axes = np.atleast_2d(axes).ravel()
    rng = np.random.default_rng(0)

    for ax, dim in zip(axes, dims_sorted):
        vals_by_group = []
        for source, eco in groups:
            mask = (liwc["source"] == source) & (liwc["ecosystem"] == eco)
            vals_by_group.append(
                pd.to_numeric(liwc.loc[mask, dim], errors="coerce").dropna().to_numpy()
            )

        parts = ax.violinplot(vals_by_group, positions=range(len(groups)),
                               widths=0.7, showmedians=True, showextrema=False)
        for body, (source, eco) in zip(parts["bodies"], groups):
            body.set_facecolor(ECO_COLORS[eco])
            body.set_alpha(0.55 if source == "human" else 0.20)
            body.set_edgecolor(ECO_COLORS[eco])
            body.set_linewidth(1.0)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(1.2)

        for i, (vals, (source, eco)) in enumerate(zip(vals_by_group, groups)):
            x = i + rng.uniform(-0.16, 0.16, size=len(vals))
            ax.scatter(x, vals, c=ECO_COLORS[eco], s=14, edgecolor="black",
                       linewidth=0.25, alpha=0.85 if source == "human" else 0.5)

        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(group_labels, fontsize=8)

        java_pass = bool(t1_model.loc[("java", dim), "passes_test1"]) if ("java", dim) in t1_model.index else False
        py_pass = bool(t1_model.loc[("python", dim), "passes_test1"]) if ("python", dim) in t1_model.index else False
        any_pass = java_pass or py_pass
        title_color = "#d62728" if any_pass else "black"
        weight = "bold" if any_pass else "normal"
        tag = f"java:{'PASS' if java_pass else 'fail'}  python:{'PASS' if py_pass else 'fail'}"
        ax.set_title(f"{dim}  ({tag})", color=title_color, fontweight=weight, fontsize=9.5)
        ax.grid(axis="y", ls=":", alpha=0.4)

    for ax in axes[len(dims_sorted):]:
        ax.set_visible(False)

    fig.suptitle(
        f"RQ3 test 1 — human vs {MODEL_LABELS[model]}, all 15 locked dimensions\n"
        "(darker fill = human, lighter = LLM; red/bold title = passes test 1 "
        "in that ecosystem; ordered by max |Cliff's $\\delta$| descending)",
        fontsize=13, y=1.0)
    fig.tight_layout()

    handles = [mpatches.Patch(color=ECO_COLORS[e], label=e) for e in ECO_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, -0.01), fontsize=9, frameon=False)

    out = FIG_DIR / f"rq3_02_violin_strip_{model}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# The four dimensions RQ3's argument rests on: BigWords carries the location
# shift (test 1, 4/4), and WPS / ipron / tentat carry the dispersion result
# (test 4, all nine significant cells). The full 15-dimension grids above stay
# in the appendix; this is the column-width version for the body.
COMPACT_DIMS = ["BigWords", "WPS", "ipron", "tentat"]
HUMAN_COLOR = "#555555"


def plot_violin_compact() -> None:
    """Human vs both models on four dimensions, both ecosystems, one figure.

    Drawn at its final printed size (IEEE column width, 3.5in) so it can be
    included at \\columnwidth without rescaling and the fonts stay legible.
    Ecosystems are kept side by side rather than pooled: pooling would put two
    differently-located distributions in one violin and make spread look larger
    than it is within either ecosystem.
    """
    liwc = pd.read_csv(LIWC_CSV)
    sources = [("human", "H", HUMAN_COLOR), ("sonnet", "S", MODEL_COLORS["sonnet"]),
               ("openai", "G", MODEL_COLORS["openai"])]
    gap = 0.6
    positions, groups = [], []
    for e_i, eco in enumerate(["java", "python"]):
        for s_i, (src, short, col) in enumerate(sources):
            positions.append(e_i * (len(sources) + gap) + s_i)
            groups.append((eco, src, short, col))

    plt.rcParams.update({"font.size": 7})
    fig, axes = plt.subplots(2, 2, figsize=(3.5, 3.4))
    rng = np.random.default_rng(0)
    for ax, dim in zip(axes.ravel(), COMPACT_DIMS):
        data = []
        for eco, src, _, _ in groups:
            m = (liwc["ecosystem"] == eco) & (liwc["source"] == src)
            data.append(pd.to_numeric(liwc.loc[m, dim], errors="coerce").dropna().to_numpy())
        parts = ax.violinplot(data, positions=positions, widths=0.8,
                              showmedians=True, showextrema=False)
        for body, (_, src, _, col) in zip(parts["bodies"], groups):
            body.set_facecolor(col)
            body.set_edgecolor(col)
            body.set_alpha(0.45 if src == "human" else 0.30)
            body.set_linewidth(0.6)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(0.9)
        for pos, vals, (_, _, _, col) in zip(positions, data, groups):
            ax.scatter(pos + rng.uniform(-0.14, 0.14, len(vals)), vals, s=1.6,
                       c=col, alpha=0.7, linewidths=0)
        ax.set_xticks(positions)
        ax.set_xticklabels([g[2] for g in groups], fontsize=6)
        for e_i, eco in enumerate(["Java", "Python"]):
            centre = e_i * (len(sources) + gap) + (len(sources) - 1) / 2
            ax.text(centre, -0.12, eco, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=6.5)
        ax.set_title(dim, fontsize=7.5, pad=2)
        ax.tick_params(axis="y", labelsize=6, length=2)
        ax.tick_params(axis="x", length=0, pad=1.5)
        ax.grid(axis="y", ls=":", alpha=0.4, lw=0.5)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    fig.tight_layout(h_pad=1.6, w_pad=0.8)
    out = FIG_DIR / "rq3_03_violin_compact.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    plt.rcParams.update(plt.rcParamsDefault)
    print(f"  wrote {out}")


def main() -> None:
    print("Generating RQ3 figures:")
    plot_test2_forest()
    plot_test1_forest()
    for model in MODELS:
        plot_violin_strip(model)
    plot_violin_compact()
    print("Done.")


if __name__ == "__main__":
    main()
