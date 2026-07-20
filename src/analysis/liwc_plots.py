"""
liwc_plots — generate the three visualisations for the LIWC screening:

1. Volcano plot: Cliff's delta (J vs P) on x, -log10(Holm-MWU-p) on y, for all
   screened LIWC dimensions. Quadrants and thresholds shown.

2. Forest plot: Cliff's delta with bootstrap 95% CIs for the shortlisted
   dimensions (Tier 1 + Tier 2), ranked by |delta|.

3. Boxplot + strip grid: one small-multiple per Tier-1 dimension, three
   ecosystems side by side, individual libraries shown as dots coloured by
   domain.

Outputs to files/analysis/figures/.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats

LIWC_CSV = Path(
    "/Users/max/Documents/SENG402/SENG402/files/preprocess/"
    "preprocess_output_13-05-26_21-50-10/"
    "LIWC-22 Results - libraries - LIWC Analysis.csv"
)
STATS_CSV = Path(
    "/Users/max/Documents/SENG402/SENG402/files/analysis/liwc_stats_results.csv"
)
FIG_DIR = Path("/Users/max/Documents/SENG402/SENG402/files/analysis/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)

TIER1 = ["emotion", "emo_neg", "emo_anger", "emo_sad",
         "WPS", "BigWords", "curiosity", "achieve", "conflict"]
TIER2 = ["tentat", "Tone", "motion", "ipron"]
SHORTLIST = TIER1 + TIER2
SUMMARY_VARS = ["Analytic", "Clout", "Authentic", "Tone"]

ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77", "javascript": "#7570b3"}
ECO_ORDER = ["java", "python", "javascript"]


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    diffs = a[:, None] - b[None, :]
    return (np.sum(diffs > 0) - np.sum(diffs < 0)) / (len(a) * len(b))


def bootstrap_cliffs_ci(a: np.ndarray, b: np.ndarray,
                       n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        aa = rng.choice(a, size=len(a), replace=True)
        bb = rng.choice(b, size=len(b), replace=True)
        deltas[i] = cliffs_delta(aa, bb)
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(LIWC_CSV)
    df = df[~df["library"].str.startswith("_ALL_")].copy()
    stats_df = pd.read_csv(STATS_CSV)
    return df, stats_df


# -------------------------------------------------------------------------
# Plot 1: volcano
# -------------------------------------------------------------------------
def plot_volcano(stats_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    x = stats_df["cliffs_d_J_vs_P"]
    p = stats_df["MWU_p_J_vs_P_holm"].clip(lower=1e-7)
    y = -np.log10(p)
    passes = (p < 0.05) & (x.abs() >= 0.33)

    ax.scatter(x[~passes], y[~passes], s=40, c="lightgrey",
               edgecolor="grey", linewidth=0.5, label="not significant / trivial")
    ax.scatter(x[passes], y[passes], s=70, c="#d62728",
               edgecolor="black", linewidth=0.6, label="passes decision rule")

    for _, row in stats_df.iterrows():
        d, pv = row["cliffs_d_J_vs_P"], row["MWU_p_J_vs_P_holm"]
        if pv < 0.05 and abs(d) >= 0.33:
            ax.annotate(row["metric"], (d, -np.log10(max(pv, 1e-7))),
                        fontsize=8, xytext=(4, 2), textcoords="offset points")

    # Always label the four LIWC summary variables, even if they fail the rule.
    summary_rows = stats_df[stats_df["metric"].isin(SUMMARY_VARS)]
    ax.scatter(summary_rows["cliffs_d_J_vs_P"],
               -np.log10(summary_rows["MWU_p_J_vs_P_holm"].clip(lower=1e-7)),
               s=120, facecolor="none", edgecolor="#1f77b4", linewidth=1.6,
               label="LIWC summary indices", zorder=5)
    for _, row in summary_rows.iterrows():
        d = row["cliffs_d_J_vs_P"]
        pv = row["MWU_p_J_vs_P_holm"]
        ax.annotate(row["metric"], (d, -np.log10(max(pv, 1e-7))),
                    fontsize=9, color="#1f77b4",
                    xytext=(6, -10), textcoords="offset points",
                    fontweight="bold")

    # Thresholds
    ax.axhline(-np.log10(0.05), ls="--", color="grey", lw=0.8)
    ax.axvline(0.33, ls="--", color="grey", lw=0.8)
    ax.axvline(-0.33, ls="--", color="grey", lw=0.8)
    ax.axvline(0, color="black", lw=0.5)
    ymax = ax.get_ylim()[1]
    ax.text(0.34, ymax * 0.05, "Java higher",
            ha="left", fontsize=9, color="grey")
    ax.text(-0.34, ymax * 0.05, "Python higher",
            ha="right", fontsize=9, color="grey")

    ax.set_xlabel("Cliff's $\\delta$ (Java vs Python)")
    ax.set_ylabel(r"$-\log_{10}$(Holm-adjusted Mann-Whitney $p$)")
    ax.set_title("LIWC dimension screening: effect size vs significance\n"
                 "(Java vs Python, n=42 vs 45, 59 dimensions tested)")
    ax.legend(loc="upper left", frameon=True)
    ax.set_xlim(-0.85, 0.85)
    fig.tight_layout()
    out = FIG_DIR / "01_volcano_J_vs_P.png"
    fig.savefig(out, dpi=200)
    print(f"  wrote {out}")
    plt.close(fig)


# -------------------------------------------------------------------------
# Plot 2: forest plot of Cliff's delta with bootstrap CIs
# -------------------------------------------------------------------------
def _forest_rows(df: pd.DataFrame, metrics: list[str]) -> list[tuple]:
    java = df[df["ecosystem"] == "java"]
    py = df[df["ecosystem"] == "python"]
    rows = []
    for m in metrics:
        if m not in df.columns:
            continue
        j = pd.to_numeric(java[m], errors="coerce").dropna().to_numpy()
        p = pd.to_numeric(py[m], errors="coerce").dropna().to_numpy()
        if len(j) < 5 or len(p) < 5:
            continue
        d = cliffs_delta(j, p)
        lo, hi = bootstrap_cliffs_ci(j, p)
        rows.append((m, d, lo, hi))
    rows.sort(key=lambda r: r[1])
    return rows


def _draw_forest(rows: list[tuple], title: str, out: Path,
                 highlight: set[str] | None = None) -> None:
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(rows) + 1.5))
    ys = np.arange(len(rows))
    for y, (m, d, lo, hi) in zip(ys, rows):
        colour = "#d95f02" if d > 0 else "#1b9e77"
        lw_bar = 2.5 if (highlight and m in highlight) else 1.5
        ms = 9 if (highlight and m in highlight) else 6
        ax.plot([lo, hi], [y, y], color=colour, lw=lw_bar)
        ax.plot(d, y, "o", color=colour, markersize=ms,
                markeredgecolor="black", markeredgewidth=0.5)

    for thr in (0.147, 0.33, 0.474):
        ax.axvline(thr, ls=":", color="grey", lw=0.6)
        ax.axvline(-thr, ls=":", color="grey", lw=0.6)
    ax.axvline(0, color="black", lw=0.6)

    ax.set_yticks(ys)
    labels = [r[0] for r in rows]
    if highlight:
        ax.set_yticklabels([f"$\\bf{{{lab}}}$" if lab in highlight else lab
                            for lab in labels])
    else:
        ax.set_yticklabels(labels)
    ax.set_xlabel("Cliff's $\\delta$  (negative = Python higher, positive = Java higher)")
    ax.set_xlim(-1.05, 1.05)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def plot_forest(df: pd.DataFrame, stats_df: pd.DataFrame) -> None:
    # 02: shortlist only.
    rows = _forest_rows(df, SHORTLIST)
    _draw_forest(
        rows,
        title=("Effect sizes for shortlisted LIWC dimensions\n"
               "(Java vs Python; points = sample $\\delta$, bars = bootstrap 95% CI, n_boot=2000)"),
        out=FIG_DIR / "02_forest_cliffs_delta.png",
    )
    # 02b: all screened metrics, ordered by delta, shortlist bolded.
    all_metrics = stats_df["metric"].tolist()
    rows_all = _forest_rows(df, all_metrics)
    _draw_forest(
        rows_all,
        title=("Effect sizes for all screened LIWC dimensions\n"
               "(Java vs Python; bold labels = passes decision rule; "
               "$|\\delta| \\geq 0.33$ and Holm-$p < 0.05$)"),
        out=FIG_DIR / "02b_forest_all.png",
        highlight=set(SHORTLIST),
    )


# -------------------------------------------------------------------------
# Plot 3: boxplot + strip grid for Tier 1
# -------------------------------------------------------------------------
def _draw_box_strip_grid(df: pd.DataFrame, metrics: list[str],
                        title: str, out: Path,
                        ncols: int = 3, panel_w: float = 4.2,
                        panel_h: float = 3.2) -> None:
    nrows = int(np.ceil(len(metrics) / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(panel_w * ncols, panel_h * nrows))
    axes = np.atleast_2d(axes).ravel()

    rng = np.random.default_rng(0)
    has_domain = "domain" in df.columns
    if has_domain:
        domains = sorted(df["domain"].dropna().unique())
        cmap = plt.colormaps["tab20"]
        domain_colors = {d: cmap(i % 20) for i, d in enumerate(domains)}

    for ax, metric in zip(axes, metrics):
        vals_by_eco = [pd.to_numeric(df.loc[df["ecosystem"] == e, metric],
                                     errors="coerce").dropna().to_numpy()
                       for e in ECO_ORDER]
        bp = ax.boxplot(vals_by_eco, positions=range(len(ECO_ORDER)),
                        widths=0.55, showfliers=False, patch_artist=True)
        for patch, e in zip(bp["boxes"], ECO_ORDER):
            patch.set_facecolor(ECO_COLORS[e])
            patch.set_alpha(0.25)
            patch.set_edgecolor(ECO_COLORS[e])
        for median in bp["medians"]:
            median.set_color("black")

        # strip with jitter
        for i, e in enumerate(ECO_ORDER):
            sub = df[df["ecosystem"] == e]
            y = pd.to_numeric(sub[metric], errors="coerce").to_numpy()
            mask = ~np.isnan(y)
            y = y[mask]
            x = i + rng.uniform(-0.18, 0.18, size=len(y))
            if has_domain:
                d_list = sub["domain"].to_numpy()[mask]
                cols = [domain_colors.get(d, "grey") for d in d_list]
            else:
                cols = ECO_COLORS[e]
            ax.scatter(x, y, c=cols, s=18, edgecolor="black",
                       linewidth=0.3, alpha=0.85)

        ax.set_xticks(range(len(ECO_ORDER)))
        ax.set_xticklabels(ECO_ORDER)
        ax.set_title(metric)
        ax.grid(axis="y", ls=":", alpha=0.4)

    for ax in axes[len(metrics):]:
        ax.set_visible(False)

    fig.suptitle(title, fontsize=13, y=1.0)
    fig.tight_layout()

    if has_domain:
        handles = [mpatches.Patch(color=domain_colors[d], label=d)
                   for d in domains]
        legend_ncol = 6
        legend_rows = int(np.ceil(len(domains) / legend_ncol))
        # Allocate bottom space proportional to figure height.
        fig_h = panel_h * nrows
        fig.subplots_adjust(bottom=(0.6 + 0.25 * legend_rows) / fig_h)
        fig.legend(handles=handles, loc="lower center", ncol=legend_ncol,
                   bbox_to_anchor=(0.5, 0.0), fontsize=8, frameon=False)

    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def plot_box_strip_grid(df: pd.DataFrame, stats_df: pd.DataFrame) -> None:
    # 03: Tier 1 only.
    _draw_box_strip_grid(
        df, TIER1,
        title="Tier 1 LIWC dimensions: per-library distributions by ecosystem",
        out=FIG_DIR / "03_box_strip_tier1.png",
        ncols=3, panel_w=4.2, panel_h=3.2,
    )
    # 03b: all screened metrics ordered by |delta J vs P| descending.
    stats_sorted = stats_df.assign(
        abs_d=stats_df["cliffs_d_J_vs_P"].abs()
    ).sort_values("abs_d", ascending=False)
    all_metrics = [m for m in stats_sorted["metric"].tolist() if m in df.columns]
    _draw_box_strip_grid(
        df, all_metrics,
        title=("All screened LIWC dimensions: per-library distributions by ecosystem\n"
               "(ordered by $|$Cliff's $\\delta|$, J vs P, descending)"),
        out=FIG_DIR / "03b_box_strip_all.png",
        ncols=4, panel_w=3.6, panel_h=2.6,
    )


def main() -> None:
    df, stats_df = load_data()
    print(f"Libraries loaded: {len(df)}")
    print("Generating figures:")
    plot_volcano(stats_df)
    plot_forest(df, stats_df)
    plot_box_strip_grid(df, stats_df)
    print("Done.")


if __name__ == "__main__":
    main()
