"""
confirmatory_cluster_viz: visual inspection of the confirmatory LIWC
feature space, added: the
significance tables don't show whether there's visible cluster structure
that a Kruskal-Wallis/Holm summary could miss.

1. PCA projection (2D) of all 400 libraries in the 15-locked-dimension
   LIWC space, colored once by ecosystem and once by domain.
2. Full pairwise scatterplot matrix over all 15 locked dimensions
   (lower triangle + diagonal histograms), colored by ecosystem.
3. Curated pairwise scatterplot matrix over the 6 dimensions with the
   largest confirmatory |Cliff's delta| (emo_anger, conflict, achieve,
   WPS, emo_sad, tentat), colored by ecosystem and, separately, by
   domain.

No seaborn/sklearn dependency, PCA via numpy SVD, pairs grid via
matplotlib subplots, consistent with the rest of this codebase.

Outputs to files/analysis/figures/, continuing the 01-06 numbering.

Usage:
    venv/bin/python3 src/analysis/confirmatory_cluster_viz.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

FRAME_DIR = ROOT / "files" / "corpus" / "frame_locked"
LIWC_CSV = FRAME_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"

ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77"}

# Fixed categorical order (assigned once, never cycled/reassigned by rank),
# replaces the previous tab20-based scheme, whose alternating dark/light
# shade pairs per hue made adjacent domains hard to tell apart.
# 8 colour-blind-safe hues, plus one neutral gray reserved for "misc" specifically: a fully
# saturated 9th hue can't pass CVD separation at 9 simultaneous categories
# regardless of which hue is picked (validated via
# a pairwise colour-separation check, fails past ~3 slots by
# design, a documented ceiling, not an oversight here). Both figures below
# additionally encode domain by marker shape, since color alone can't safely
# carry identity across 9 categories, the actual point of these two figures.
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
DOMAIN_MARKERS = {
    "build-tooling": "o",
    "data":          "s",
    "networking":    "^",
    "security":      "D",
    "serialisation": "v",
    "testing":       "P",
    "ui":            "X",
    "web":           "*",
    "misc":          "h",
}

LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

# Top 6 by |confirmatory Cliff's delta| (confirmatory_stats_results.csv).
CURATED_DIMS = ["emo_anger", "conflict", "achieve", "WPS", "emo_sad", "tentat"]


def load_data() -> pd.DataFrame:
    df = pd.read_csv(LIWC_CSV)
    return df


def zscore(mat: np.ndarray) -> np.ndarray:
    mu = mat.mean(axis=0, keepdims=True)
    sd = mat.std(axis=0, ddof=1, keepdims=True)
    sd[sd == 0] = 1.0
    return (mat - mu) / sd


def pca_2d(mat_z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (scores[:, :2], explained_variance_ratio[:2])."""
    u, s, _vt = np.linalg.svd(mat_z, full_matrices=False)
    scores = u * s
    var = (s ** 2) / (mat_z.shape[0] - 1)
    evr = var / var.sum()
    return scores[:, :2], evr[:2]


# -------------------------------------------------------------------------
# Figure: PCA projection, colored by ecosystem and by domain
# -------------------------------------------------------------------------
def plot_pca(df: pd.DataFrame) -> None:
    mat = df[LOCKED_DIMENSIONS].apply(pd.to_numeric, errors="coerce").to_numpy()
    mat_z = zscore(mat)
    scores, evr = pca_2d(mat_z)
    df = df.copy()
    df["pc1"], df["pc2"] = scores[:, 0], scores[:, 1]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    ax = axes[0]
    for eco, color in ECO_COLORS.items():
        sub = df[df["ecosystem"] == eco]
        ax.scatter(sub["pc1"], sub["pc2"], s=22, c=color, alpha=0.7,
                   edgecolor="black", linewidth=0.3, label=f"{eco} (n={len(sub)})")
    ax.set_title("Colored by ecosystem")
    ax.legend(frameon=True, loc="best")

    ax = axes[1]
    domains = sorted(df["domain"].dropna().unique())
    for d in domains:
        sub = df[df["domain"] == d]
        ax.scatter(sub["pc1"], sub["pc2"], s=26, c=DOMAIN_COLORS.get(d, "grey"),
                   marker=DOMAIN_MARKERS.get(d, "o"), alpha=0.7,
                   edgecolor="black", linewidth=0.3, label=d)
    ax.set_title("Colored + shaped by domain")
    ax.legend(frameon=True, loc="best", fontsize=7, ncol=1)

    for ax in axes:
        ax.set_xlabel(f"PC1 ({evr[0]*100:.1f}% var)")
        ax.set_ylabel(f"PC2 ({evr[1]*100:.1f}% var)")
        ax.grid(ls=":", alpha=0.4)

    fig.suptitle("PCA of the 15 locked LIWC dimensions (400 libraries, z-scored)\n"
                 "requested to visually check for cluster structure beyond the KW/Holm summary tables",
                 fontsize=12)
    fig.tight_layout()
    out = FIG_DIR / "07_pca_projection.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}  (PC1+PC2 explain {evr.sum()*100:.1f}% of variance)")
    plt.close(fig)


# -------------------------------------------------------------------------
# Pairwise scatterplot matrix (manual, no seaborn)
# -------------------------------------------------------------------------
def _pairs_grid_ecosystem(df: pd.DataFrame, dims: list[str], out: Path,
                          panel_size: float = 1.3) -> None:
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
                    ax.hist(vals, bins=20, color=color, alpha=0.5, density=True)
            else:
                for eco, color in ECO_COLORS.items():
                    sub = df[df["ecosystem"] == eco]
                    x = pd.to_numeric(sub[dx], errors="coerce")
                    y = pd.to_numeric(sub[dy], errors="coerce")
                    ax.scatter(x, y, s=4, c=color, alpha=0.5, linewidth=0)
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
    fig.suptitle("Pairwise scatterplot matrix — locked LIWC dimensions, by ecosystem",
                fontsize=13, y=1.005)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def _pairs_grid_domain(df: pd.DataFrame, dims: list[str], out: Path,
                       panel_size: float = 1.9) -> None:
    n = len(dims)
    fig, axes = plt.subplots(n, n, figsize=(panel_size * n, panel_size * n))
    domains = sorted(df["domain"].dropna().unique())

    for i, dy in enumerate(dims):
        for j, dx in enumerate(dims):
            ax = axes[i, j]
            if j > i:
                ax.set_visible(False)
                continue
            if i == j:
                vals = pd.to_numeric(df[dx], errors="coerce").dropna()
                ax.hist(vals, bins=20, color="grey", alpha=0.6, density=True)
            else:
                for d in domains:
                    sub = df[df["domain"] == d]
                    x = pd.to_numeric(sub[dx], errors="coerce")
                    y = pd.to_numeric(sub[dy], errors="coerce")
                    ax.scatter(x, y, s=10, c=DOMAIN_COLORS.get(d, "grey"),
                              marker=DOMAIN_MARKERS.get(d, "o"), alpha=0.6, linewidth=0)
            if j == 0:
                ax.set_ylabel(dy, fontsize=8)
            else:
                ax.set_yticklabels([])
            if i == n - 1:
                ax.set_xlabel(dx, fontsize=8)
            else:
                ax.set_xticklabels([])
            ax.tick_params(labelsize=6)

    handles = [plt.Line2D([0], [0], marker=DOMAIN_MARKERS.get(d, "o"), color="w",
                          markerfacecolor=DOMAIN_COLORS.get(d, "grey"), markersize=7, label=d)
               for d in domains]
    fig.legend(handles=handles, loc="upper right", fontsize=8,
              bbox_to_anchor=(0.99, 0.99))
    fig.suptitle("Pairwise scatterplot matrix — top-6 dimensions by |confirmatory delta|, by domain\n"
                "(both ecosystems pooled)", fontsize=12, y=1.01)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def plot_pairs(df: pd.DataFrame) -> None:
    _pairs_grid_ecosystem(df, LOCKED_DIMENSIONS,
                          FIG_DIR / "08_pairs_full15_ecosystem.png", panel_size=1.3)
    _pairs_grid_ecosystem(df, CURATED_DIMS,
                          FIG_DIR / "08b_pairs_curated6_ecosystem.png", panel_size=2.0)
    _pairs_grid_domain(df, CURATED_DIMS,
                       FIG_DIR / "08c_pairs_curated6_domain.png", panel_size=2.0)


def main() -> None:
    df = load_data()
    print(f"Loaded {len(df)} libraries")
    plot_pca(df)
    plot_pairs(df)
    print("Done.")


if __name__ == "__main__":
    main()
