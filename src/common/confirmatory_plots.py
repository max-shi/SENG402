"""
confirmatory_plots: visualisations for the confirmatory-phase
update.

1. Pilot vs confirmatory Cliff's delta, dumbbell/slope chart per locked
   dimension, visualises the Layer 1 shrinkage story directly.
2. Domain composition per ecosystem, grouped horizontal bar chart from the
   frozen confirmatory manifest.
3. RQ2 eta^2_H heat-map, dimension x ecosystem, from the domain-stratified
   gatekeeper results.
4. Violin + strip grid, Java vs Python, all 15 locked dimensions, the direct
   per-dimension distribution comparison Layer 1 actually tests, added
   after a discussion that pairwise 2D
   scatter plots (confirmatory_cluster_viz.py) answer a different
   question (joint/multivariate structure) than "does the distribution
   itself look different", which this figure answers directly. Switched
   from box+strip to violin+strip (a violin
   shows the actual density shape, e.g. multimodality, that a box's
   five-number summary hides).

Outputs to files/analysis/figures/, continuing the 01-03 numbering used by
liwc_plots.py.

Usage:
    venv/bin/python3 src/common/confirmatory_plots.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

FRAME_DIR = ROOT / "files" / "corpus" / "frame_locked"
PILOT_STATS_CSV = ROOT / "files" / "analysis" / "liwc_stats_results.csv"
CONFIRM_STATS_CSV = FRAME_DIR / "confirmatory_stats_results.csv"
LIBRARIES_CSV = FRAME_DIR / "libraries.csv"
RQ2_CSV = FRAME_DIR / "confirmatory_rq2_domain_stratified.csv"
LIWC_CSV = FRAME_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"

ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77"}

# Fixed categorical order (assigned once, never cycled/reassigned by rank),
# replaces the previous tab20-based scheme, whose alternating dark/light
# shade pairs per hue made adjacent domains hard to tell apart.
# 8 colour-blind-safe hues, plus one neutral gray reserved for "misc" specifically: a fully
# saturated 9th hue can't pass CVD separation at 9 simultaneous categories
# regardless of which hue is picked (validated via
# a pairwise colour-separation check, fails past ~3 slots by
# design, a documented ceiling, not an oversight here). Figures where domain
# identity is the actual point (fig 07/08c) additionally use marker shape as
# a secondary encoding so identity never rests on hue alone.
DOMAIN_COLORS = {
    "build-tooling": "#2a78d6",
    "data":          "#eb6834",
    "networking":    "#1baf7a",
    "security":      "#eda100",
    "serialisation": "#e87ba4",
    "testing":       "#008300",
    "ui":            "#4a3aa7",
    "web":           "#e34948",
    "misc":          "#5a5a5a",
}

LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

DELTA_THRESHOLD = 0.33


# -------------------------------------------------------------------------
# Figure 1: pilot vs confirmatory delta (shrinkage dumbbell chart)
# -------------------------------------------------------------------------
def plot_pilot_vs_confirmatory() -> None:
    pilot = pd.read_csv(PILOT_STATS_CSV).set_index("metric")["cliffs_d_J_vs_P"]
    confirm = pd.read_csv(CONFIRM_STATS_CSV).set_index("dimension")

    rows = []
    for dim in LOCKED_DIMENSIONS:
        rows.append({
            "dimension": dim,
            "pilot_delta": pilot.loc[dim],
            "confirm_delta": confirm.loc[dim, "cliffs_delta"],
            "passes_layer1": bool(confirm.loc[dim, "passes_layer1"]),
        })
    df = pd.DataFrame(rows).sort_values("pilot_delta", key=lambda s: s.abs(),
                                         ascending=True)

    fig, ax = plt.subplots(figsize=(9, 0.42 * len(df) + 1.5))
    ys = np.arange(len(df))

    for y, r in zip(ys, df.itertuples()):
        ax.plot([r.pilot_delta, r.confirm_delta], [y, y],
                color="grey", lw=1.2, zorder=1)
        ax.plot(r.pilot_delta, y, "o", color="#7f7f7f", markersize=8,
                markeredgecolor="black", markeredgewidth=0.5, zorder=2,
                label="pilot (n≈45/eco)" if y == ys[-1] else None)
        confirm_color = "#d62728" if r.passes_layer1 else "#1f77b4"
        ax.plot(r.confirm_delta, y, "o", color=confirm_color, markersize=9,
                markeredgecolor="black", markeredgewidth=0.5, zorder=3,
                label="confirmatory (n=200/eco)" if y == ys[-1] else None)

    for thr in (DELTA_THRESHOLD, -DELTA_THRESHOLD):
        ax.axvline(thr, ls=":", color="grey", lw=0.8)
    ax.axvline(0, color="black", lw=0.6)

    ax.set_yticks(ys)
    ax.set_yticklabels(df["dimension"])
    ax.set_xlabel("Cliff's $\\delta$  (negative = Python higher, positive = Java higher)")
    ax.set_xlim(-0.85, 0.85)
    ax.set_title("Layer 1 shrinkage: pilot vs confirmatory Cliff's $\\delta$\n"
                 "(grey = pilot, red = confirmatory pass, blue = confirmatory fail; "
                 "dotted lines = $|\\delta|=0.33$ threshold)")
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    ax.grid(axis="y", ls=":", alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "04_pilot_vs_confirmatory_delta.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figure 2: domain composition per ecosystem
# -------------------------------------------------------------------------
def plot_domain_composition() -> None:
    df = pd.read_csv(LIBRARIES_CSV, usecols=["ecosystem", "domain"])
    counts = df.groupby(["domain", "ecosystem"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=["java", "python"], fill_value=0)
    # Order domains by total descending.
    counts = counts.loc[counts.sum(axis=1).sort_values(ascending=True).index]

    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(counts))
    height = 0.38
    ax.barh(y + height / 2, counts["java"], height=height,
            color=ECO_COLORS["java"], label=f"Java (n={counts['java'].sum()})",
            edgecolor="black", linewidth=0.4)
    ax.barh(y - height / 2, counts["python"], height=height,
            color=ECO_COLORS["python"], label=f"Python (n={counts['python'].sum()})",
            edgecolor="black", linewidth=0.4)

    for yi, (j, p) in zip(y, zip(counts["java"], counts["python"])):
        ax.text(j + 1, yi + height / 2, str(j), va="center", fontsize=8)
        ax.text(p + 1, yi - height / 2, str(p), va="center", fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(counts.index)
    ax.set_xlabel("Libraries")
    ax.set_title("Domain composition of the confirmatory corpus\n"
                 "(frame_locked, 200 libraries/ecosystem, not stratified at draw time)")
    ax.legend(loc="lower right", frameon=True)
    ax.grid(axis="x", ls=":", alpha=0.4)
    fig.tight_layout()
    out = FIG_DIR / "05_domain_composition.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figure 3: RQ2 eta^2_H heat-map (dimension x ecosystem)
# -------------------------------------------------------------------------
def plot_rq2_heatmap() -> None:
    df = pd.read_csv(RQ2_CSV)
    pivot = df.pivot(index="dimension", columns="ecosystem", values="eta2_H")
    pivot = pivot.reindex(columns=["java", "python"])
    pivot = pivot.reindex(pivot.max(axis=1).sort_values(ascending=True).index)
    sig = df.pivot(index="dimension", columns="ecosystem",
                    values="domain_effect_significant").reindex(pivot.index)
    sig = sig.reindex(columns=["java", "python"])

    fig, ax = plt.subplots(figsize=(5, 0.4 * len(pivot) + 1.5))
    im = ax.imshow(pivot.values, cmap="YlOrRd", vmin=0, vmax=0.15, aspect="auto")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            is_sig = bool(sig.values[i, j])
            txt = f"{val:.3f}" + ("*" if is_sig else "")
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=9, fontweight="bold" if is_sig else "normal",
                    color="black" if val < 0.09 else "white")

    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels([c.capitalize() for c in pivot.columns])
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index)
    ax.set_title("RQ2: within-ecosystem domain effect ($\\eta^2_H$)\n"
                 "per locked dimension (* = Holm $p<0.05$ and $\\eta^2_H \\geq 0.06$)")
    fig.colorbar(im, ax=ax, label="$\\eta^2_H$", fraction=0.046, pad=0.04)
    fig.tight_layout()
    out = FIG_DIR / "06_rq2_eta2_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figure 4: violin + strip grid, Java vs Python, all 15 locked dimensions
# -------------------------------------------------------------------------
def plot_violin_strip_confirmatory() -> None:
    df = pd.read_csv(LIWC_CSV)
    stats_df = pd.read_csv(CONFIRM_STATS_CSV).set_index("dimension")

    dims_sorted = stats_df["cliffs_delta"].abs().sort_values(ascending=False).index.tolist()

    domains = sorted(df["domain"].dropna().unique())
    domain_colors = {d: DOMAIN_COLORS.get(d, "grey") for d in domains}

    ncols = 3
    nrows = int(np.ceil(len(dims_sorted) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 3.4 * nrows))
    axes = np.atleast_2d(axes).ravel()
    rng = np.random.default_rng(0)
    eco_order = ["java", "python"]

    for ax, dim in zip(axes, dims_sorted):
        vals_by_eco = [pd.to_numeric(df.loc[df["ecosystem"] == e, dim],
                                     errors="coerce").dropna().to_numpy()
                       for e in eco_order]
        parts = ax.violinplot(vals_by_eco, positions=range(len(eco_order)),
                              widths=0.7, showmedians=True, showextrema=False)
        for body, e in zip(parts["bodies"], eco_order):
            body.set_facecolor(ECO_COLORS[e])
            body.set_alpha(0.25)
            body.set_edgecolor(ECO_COLORS[e])
            body.set_linewidth(1.0)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(1.2)

        for i, e in enumerate(eco_order):
            sub = df[df["ecosystem"] == e]
            y = pd.to_numeric(sub[dim], errors="coerce").to_numpy()
            mask = ~np.isnan(y)
            y = y[mask]
            x = i + rng.uniform(-0.16, 0.16, size=len(y))
            d_list = sub["domain"].to_numpy()[mask]
            cols = [domain_colors.get(d, "grey") for d in d_list]
            ax.scatter(x, y, c=cols, s=14, edgecolor="black",
                      linewidth=0.25, alpha=0.8)

        ax.set_xticks(range(len(eco_order)))
        ax.set_xticklabels(eco_order)
        passes = bool(stats_df.loc[dim, "passes_layer1"])
        delta = stats_df.loc[dim, "cliffs_delta"]
        title_color = "#d62728" if passes else "black"
        weight = "bold" if passes else "normal"
        tag = "PASSES L1" if passes else "fails L1"
        ax.set_title(f"{dim}  (δ={delta:+.2f}, {tag})",
                    color=title_color, fontweight=weight, fontsize=10)
        ax.grid(axis="y", ls=":", alpha=0.4)

    for ax in axes[len(dims_sorted):]:
        ax.set_visible(False)

    fig.suptitle("Confirmatory corpus: Java vs Python distributions, all 15 locked dimensions\n"
                "(ordered by |Cliff's delta| descending; dots colored by domain; "
                "red/bold = passes Layer 1)", fontsize=13, y=1.0)
    fig.tight_layout()

    handles = [mpatches.Patch(color=domain_colors[d], label=d) for d in domains]
    legend_ncol = 5
    legend_rows = int(np.ceil(len(domains) / legend_ncol))
    fig_h = 3.4 * nrows
    fig.subplots_adjust(bottom=(0.6 + 0.25 * legend_rows) / fig_h)
    fig.legend(handles=handles, loc="lower center", ncol=legend_ncol,
              bbox_to_anchor=(0.5, 0.0), fontsize=8, frameon=False)

    out = FIG_DIR / "09_violin_strip_confirmatory.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def main() -> None:
    print("Generating confirmatory-phase figures:")
    plot_pilot_vs_confirmatory()
    plot_domain_composition()
    plot_rq2_heatmap()
    plot_violin_strip_confirmatory()
    print("Done.")


if __name__ == "__main__":
    main()
