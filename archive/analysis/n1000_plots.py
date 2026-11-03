"""
n1000_plots: figures 7/8/8b/9 equivalents for the n=1000/ecosystem extended
sample (files/corpus/frame_n2000/), mirroring
confirmatory_cluster_viz.py and confirmatory_plots.py's figure 9, which
were built for the n=200/ecosystem confirmatory frame (frame_locked).

Differences from the n=200 versions, both driven by the same fact: this
frame has no `domain` column (domain tagging was only done for the
n=200 confirmatory frame),
  - Figure 7 (PCA): single panel colored by ecosystem only, no
    ecosystem/domain side-by-side.
  - Figure 8c (curated-6 pairs by domain) has no equivalent here, skipped
    entirely rather than produced empty/degenerate.
  - Figure 9 (violin+strip): strip dots colored by ecosystem (matching the
    violin color) instead of by domain; no domain legend. Switched from
    box+strip to violin+strip, same as
    the n=200 equivalent in confirmatory_plots.py.
  - CURATED_DIMS (the "top 6 by |Cliff's delta|" set used for figure 8b)
    is recomputed from *this* sample's own confirmatory_stats_results.csv
    rather than reusing the n=200-derived list, the two differ at n=1000
    (achieve drops out, BigWords enters), and "curated" should mean
    top-6-in-the-data-being-plotted, not a fixed list carried over from a
    different sample.

Outputs to files/analysis/figures/, suffixed _n1000 to avoid colliding
with the existing n=200 figures of the same number.

Usage:
    venv/bin/python3 src/analysis/n1000_plots.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

FRAME_DIR = ROOT / "files" / "corpus" / "frame_n2000"
LIWC_CSV = FRAME_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"
STATS_CSV = FRAME_DIR / "confirmatory_stats_results.csv"

ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77"}

LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]


def load_liwc() -> pd.DataFrame:
    df = pd.read_csv(LIWC_CSV)
    assert "domain" not in df.columns, (
        "frame_n2000 now has a domain column — this script assumed "
        "none exists; re-check whether the domain-colored variants should "
        "be added back in."
    )
    return df


def load_stats() -> pd.DataFrame:
    return pd.read_csv(STATS_CSV).set_index("dimension")


def curated_dims(stats_df: pd.DataFrame, n: int = 6) -> list[str]:
    return stats_df["cliffs_delta"].abs().sort_values(ascending=False).index[:n].tolist()


def zscore(mat: np.ndarray) -> np.ndarray:
    mu = mat.mean(axis=0, keepdims=True)
    sd = mat.std(axis=0, ddof=1, keepdims=True)
    sd[sd == 0] = 1.0
    return (mat - mu) / sd


def pca_2d(mat_z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u, s, _vt = np.linalg.svd(mat_z, full_matrices=False)
    scores = u * s
    var = (s ** 2) / (mat_z.shape[0] - 1)
    evr = var / var.sum()
    return scores[:, :2], evr[:2]


# -------------------------------------------------------------------------
# Figure 7: PCA projection, colored by ecosystem only (no domain data)
# -------------------------------------------------------------------------
def plot_pca(df: pd.DataFrame) -> None:
    numeric = df[LOCKED_DIMENSIONS].apply(pd.to_numeric, errors="coerce")
    keep = numeric.notna().all(axis=1)
    if not keep.all():
        dropped = df.loc[~keep, "library"].tolist()
        print(f"  plot_pca: dropping {len(dropped)} row(s) with a NaN locked "
              f"dimension (SVD can't handle NaN): {dropped}")
    df = df.loc[keep].copy()
    mat = numeric.loc[keep].to_numpy()
    mat_z = zscore(mat)
    scores, evr = pca_2d(mat_z)
    df["pc1"], df["pc2"] = scores[:, 0], scores[:, 1]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    for eco, color in ECO_COLORS.items():
        sub = df[df["ecosystem"] == eco]
        ax.scatter(sub["pc1"], sub["pc2"], s=10, c=color, alpha=0.5,
                   edgecolor="black", linewidth=0.15, label=f"{eco} (n={len(sub)})")
    ax.set_title("Colored by ecosystem (no domain data at this sample size)")
    ax.legend(frameon=True, loc="best")
    ax.set_xlabel(f"PC1 ({evr[0]*100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({evr[1]*100:.1f}% var)")
    ax.grid(ls=":", alpha=0.4)

    fig.suptitle("PCA of the 15 locked LIWC dimensions (n=1000/ecosystem extended sample,\n"
                 "z-scored) — n=1000 equivalent of 07_pca_projection.png",
                 fontsize=12)
    fig.tight_layout()
    out = FIG_DIR / "07_pca_projection_n1000.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}  (PC1+PC2 explain {evr.sum()*100:.1f}% of variance)")
    plt.close(fig)


# -------------------------------------------------------------------------
# Figures 8 / 8b: pairwise scatterplot matrices, colored by ecosystem
# -------------------------------------------------------------------------
def _pairs_grid_ecosystem(df: pd.DataFrame, dims: list[str], out: Path,
                          panel_size: float) -> None:
    n = len(dims)
    fig, axes = plt.subplots(n, n, figsize=(panel_size * n, panel_size * n))

    for i, dy in enumerate(dims):
        for j, dx in enumerate(dims):
            ax = axes[i, j]
            if j > i:
                ax.set_visible(False)
                continue
            if i == j:
                for eco, color in ECO_COLORS.items():
                    vals = pd.to_numeric(df.loc[df["ecosystem"] == eco, dx],
                                        errors="coerce").dropna()
                    ax.hist(vals, bins=30, color=color, alpha=0.5, density=True)
            else:
                for eco, color in ECO_COLORS.items():
                    sub = df[df["ecosystem"] == eco]
                    x = pd.to_numeric(sub[dx], errors="coerce")
                    y = pd.to_numeric(sub[dy], errors="coerce")
                    ax.scatter(x, y, s=2, c=color, alpha=0.3, linewidth=0)
            if j == 0:
                ax.set_ylabel(dy, fontsize=7)
            else:
                ax.set_yticklabels([])
            if i == n - 1:
                ax.set_xlabel(dx, fontsize=7)
            else:
                ax.set_xticklabels([])
            ax.tick_params(labelsize=5)

    handles = [plt.Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=c, markersize=6, label=e)
               for e, c in ECO_COLORS.items()]
    fig.legend(handles=handles, loc="upper right", fontsize=10,
              bbox_to_anchor=(0.99, 0.99))
    fig.suptitle("Pairwise scatterplot matrix — n=1000/ecosystem extended sample, by ecosystem",
                fontsize=13, y=1.005)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def plot_pairs(df: pd.DataFrame, dims6: list[str]) -> None:
    _pairs_grid_ecosystem(df, LOCKED_DIMENSIONS,
                          FIG_DIR / "08_pairs_full15_ecosystem_n1000.png", panel_size=1.3)
    _pairs_grid_ecosystem(df, dims6,
                          FIG_DIR / "08b_pairs_curated6_ecosystem_n1000.png", panel_size=2.0)
    # No 08c equivalent: that variant colors by domain, and this frame has none.


# -------------------------------------------------------------------------
# Figure 9: violin + strip grid, Java vs Python, all 15 locked dimensions
# -------------------------------------------------------------------------
def plot_violin_strip(df: pd.DataFrame, stats_df: pd.DataFrame) -> None:
    dims_sorted = stats_df["cliffs_delta"].abs().sort_values(ascending=False).index.tolist()

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
            y = y[~np.isnan(y)]
            x = i + rng.uniform(-0.16, 0.16, size=len(y))
            # Colored by ecosystem (matching the box), not domain, this
            # frame has no domain tags, unlike the n=200 confirmatory one.
            ax.scatter(x, y, c=ECO_COLORS[e], s=3, alpha=0.25, linewidth=0)

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

    fig.suptitle("n=1000/ecosystem extended sample: Java vs Python distributions, "
                "all 15 locked dimensions\n(ordered by |Cliff's delta| descending; "
                "dots colored by ecosystem — no domain data at this sample size)",
                fontsize=13, y=1.0)
    fig.tight_layout()
    out = FIG_DIR / "09_violin_strip_n1000.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def main() -> None:
    df = load_liwc()
    stats_df = load_stats()
    dims6 = curated_dims(stats_df)
    print(f"Loaded {len(df)} libraries from {FRAME_DIR.name}")
    print(f"Curated 6 (top |Cliff's delta| in this sample): {dims6}")
    plot_pca(df)
    plot_pairs(df, dims6)
    plot_violin_strip(df, stats_df)
    print("Done.")


if __name__ == "__main__":
    main()
