"""
n200_vs_n1000_delta: direct comparison of Cliff's delta at the n=200/eco
confirmatory sample (frame_locked) vs the n=1000/eco extended sample
(frame_n2000), for all 15 locked dimensions.

Same dumbbell-chart idea as confirmatory_plots.py's figure 04 (pilot vs
confirmatory), one level further out: confirmatory vs extended. Built for
a meeting, to show directly "same 15 dimensions
fail at both sample sizes, and the one dimension that passed Layer 1 at
n=200 (emo_anger) drops below the practical-significance threshold once
measured more precisely" rather than requiring two separate tables to be
compared by eye.

Also writes a plain-text/markdown table with the same numbers
(n200_vs_n1000_delta_table.md), since a table is easier to read numbers
off of out loud than a chart.

Outputs:
    files/analysis/figures/10_n200_vs_n1000_delta.png
    files/analysis/n200_vs_n1000_delta_table.md

Usage:
    venv/bin/python3 src/rq1/n200_vs_n1000_delta.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "files" / "analysis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

N200_STATS = ROOT / "files" / "corpus" / "frame_locked" / "confirmatory_stats_results.csv"
N1000_STATS = ROOT / "files" / "corpus" / "frame_n2000" / "confirmatory_stats_results.csv"
TABLE_OUT = ROOT / "files" / "analysis" / "n200_vs_n1000_delta_table.md"

DELTA_THRESHOLD = 0.33


def load() -> pd.DataFrame:
    n200 = pd.read_csv(N200_STATS).set_index("dimension")
    n1000 = pd.read_csv(N1000_STATS).set_index("dimension")
    df = pd.DataFrame({
        "n200_delta": n200["cliffs_delta"],
        "n200_passes": n200["passes_layer1"],
        "n200_p_holm": n200["MWU_p_holm"],
        "n1000_delta": n1000["cliffs_delta"],
        "n1000_passes": n1000["passes_layer1"],
        "n1000_p_holm": n1000["MWU_p_holm"],
    })
    df["shrank"] = df["n1000_delta"].abs() < df["n200_delta"].abs()
    return df.sort_values("n200_delta", key=lambda s: s.abs(), ascending=True)


def plot(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(df) + 1.5))
    ys = np.arange(len(df))

    for y, r in zip(ys, df.itertuples()):
        ax.plot([r.n200_delta, r.n1000_delta], [y, y],
                color="grey", lw=1.2, zorder=1)
        n200_color = "#d62728" if r.n200_passes else "#7f7f7f"
        ax.plot(r.n200_delta, y, "o", color=n200_color, markersize=8,
                markeredgecolor="black", markeredgewidth=0.5, zorder=2,
                label="n=200/eco confirmatory" if y == ys[-1] else None)
        n1000_color = "#d62728" if r.n1000_passes else "#1f77b4"
        ax.plot(r.n1000_delta, y, "o", color=n1000_color, markersize=9,
                markeredgecolor="black", markeredgewidth=0.5, zorder=3,
                label="n=1000/eco extended" if y == ys[-1] else None)

    for thr in (DELTA_THRESHOLD, -DELTA_THRESHOLD):
        ax.axvline(thr, ls=":", color="grey", lw=0.8)
    ax.axvline(0, color="black", lw=0.6)

    ax.set_yticks(ys)
    ax.set_yticklabels(df.index)
    ax.set_xlabel("Cliff's $\\delta$  (negative = Python higher, positive = Java higher)")
    ax.set_xlim(-0.42, 0.42)
    ax.set_title("n=200 confirmatory vs n=1000 extended: Cliff's $\\delta$ per locked dimension\n"
                 "(grey/blue = fails Layer 1, red = passes Layer 1; dotted lines = "
                 "$|\\delta|=0.33$ practical-significance threshold)")
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    ax.grid(axis="y", ls=":", alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "10_n200_vs_n1000_delta.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"  wrote {out}")
    plt.close(fig)


def write_table(df: pd.DataFrame) -> None:
    df = df.sort_values("n200_delta", key=lambda s: s.abs(), ascending=False)
    lines = [
        "# n=200 confirmatory vs n=1000 extended — Cliff's delta by dimension",
        "",
        "Sorted by |delta| at n=200, descending. `pass?` = passes Layer 1 "
        "(Holm p<0.05 AND |delta|>=0.33). Only `emo_anger` ever passes, and "
        "only at n=200 — it fails at n=1000 despite an extremely small "
        "p-value, because its effect size drops below the practical-"
        "significance threshold once measured more precisely.",
        "",
        "| dimension | n=200 δ | n=200 pass? | n=200 Holm p | n=1000 δ | n=1000 pass? | n=1000 Holm p |",
        "|---|---:|:---:|---:|---:|:---:|---:|",
    ]
    for dim, r in df.iterrows():
        lines.append(
            f"| {dim} | {r.n200_delta:+.3f} | {'YES' if r.n200_passes else 'no'} | "
            f"{r.n200_p_holm:.2e} | {r.n1000_delta:+.3f} | "
            f"{'YES' if r.n1000_passes else 'no'} | {r.n1000_p_holm:.2e} |"
        )
    TABLE_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {TABLE_OUT}")


def main() -> None:
    df = load()
    plot(df)
    write_table(df)
    print("Done.")


if __name__ == "__main__":
    main()
