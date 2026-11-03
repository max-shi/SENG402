"""Pipeline diagram for the report (Study Design section).

Writes report/figures/pipeline.png at IEEE single-column width.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "figures" / "pipeline.png"

MAIN = "#e8eef7"
BRANCH = "#fbeee0"
EDGE = "#33415c"


def box(ax, x, y, w, h, title, sub, fill):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                                fc=fill, ec=EDGE, lw=0.7))
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=5.0, weight="bold")
    ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=4.3, linespacing=1.1)


def arrow(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", lw=0.7, color=EDGE, mutation_scale=6))


def main() -> None:
    fig, ax = plt.subplots(figsize=(3.5, 1.75), dpi=300)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    w, h, gap = 0.164, 0.30, 0.045
    y = 0.62
    xs = [0.005 + i * (w + gap) for i in range(5)]
    main_boxes = [
        ("1. Frame", "ecosyste.ms\nPyPI, Maven"),
        ("2. Acquire", "git clone\nper library"),
        ("3. Extract", "README, docs/\ncode removed"),
        ("4. Score", "LIWC-22\n(manual CSV)"),
        ("5. Analyse", "Python stats,\nclassifiers"),
    ]
    for x, (t, s) in zip(xs, main_boxes):
        box(ax, x, y, w, h, t, s, MAIN)
    for i in range(4):
        arrow(ax, xs[i] + w, y + h / 2, xs[i + 1], y + h / 2)

    # RQ3 branch: API surface -> LLM generation -> same extraction -> scoring
    yb = 0.10
    box(ax, xs[1], yb, w, h, "API surface", "public signatures\n(RQ3)", BRANCH)
    box(ax, xs[2], yb, w, h, "Generate", "Sonnet 5,\nGPT-5.6-terra", BRANCH)
    arrow(ax, xs[1] + w / 2, y, xs[1] + w / 2, yb + h)            # acquire -> API surface
    arrow(ax, xs[1] + w, yb + h / 2, xs[2], yb + h / 2)           # API -> generate
    ax.plot([xs[2] + w, xs[3] + w / 2], [yb + h / 2, yb + h / 2], color=EDGE, lw=0.7)
    arrow(ax, xs[3] + w / 2, yb + h / 2, xs[3] + w / 2, y)        # up into score
    ax.text(xs[3] + w / 2 + 0.012, yb + h / 2 + 0.13, "same\nextraction", fontsize=4.0,
            ha="left", va="center", style="italic")

    ax.text(xs[4] + w / 2, yb + h / 2, "RQ1\u2013RQ4\nresults", ha="center", va="center",
            fontsize=4.8)
    arrow(ax, xs[4] + w / 2, y, xs[4] + w / 2, yb + h * 0.85)

    fig.savefig(OUT, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
