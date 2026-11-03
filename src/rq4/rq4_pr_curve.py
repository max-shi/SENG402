"""
rq4_pr_curve: precision-recall and ROC curves for the RQ4 authorship rule.

Why. The reported macro-F1 describes the rule at ONE operating point
(BigWords > 34.1). It cannot show what the detector would do at a stricter or
looser cut-point, and it cannot separate "the feature ranks documents well" from
"the chosen threshold happens to sit in a good place". Sweeping the threshold and
plotting precision against recall separates the two, and summarises the first as
a single threshold-free number.

Threshold-free is the important property here. Average precision and ROC AUC
depend only on the ORDER the feature puts documents in, so unlike the macro-F1
peak they cannot be inflated by choosing a cut-point on the same rows they score.
They are therefore reported without a cross-validation caveat, while the
operating point marked on each curve carries the usual one.

Both curves are drawn because they answer different questions on an imbalanced
corpus (200 generated, 100 human). PR is sensitive to the positive-class rate and
is the more informative view of a detector's usefulness; ROC is scale-free and
comparable across corpora with different balances. Baselines differ accordingly:
a no-skill classifier sits at precision 0.667 on PR (the positive rate) but on
the diagonal for ROC.

Outputs:
    files/analysis/figures/rq4_clean_03_pr_roc.png
    report/figures/rq4_pr_roc.png
    files/analysis/rq4_pr_curve_points.csv

Usage:
    venv/bin/python3 src/rq4/rq4_pr_curve.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import pandas as pd               # noqa: E402
from sklearn.metrics import (     # noqa: E402
    average_precision_score, precision_recall_curve, roc_auc_score, roc_curve,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq4_detector import best_threshold, load_corpus  # noqa: E402

OUT = ROOT / "files" / "analysis" / "figures" / "rq4_clean_03_pr_roc.png"
REPORT_COPY = ROOT / "report" / "figures" / "rq4_pr_roc.png"
POINTS = ROOT / "files" / "analysis" / "rq4_pr_curve_points.csv"


def main() -> None:
    df = load_corpus()
    df = df.loc[:, ~df.columns.duplicated()]
    y = (df.source != "human").astype(int).to_numpy()
    score = df["BigWords"].to_numpy()

    prec, rec, pr_thr = precision_recall_curve(y, score)
    fpr, tpr, roc_thr = roc_curve(y, score)
    ap = average_precision_score(y, score)
    auc = roc_auc_score(y, score)

    thr = best_threshold(score, y)
    pred = score > thr
    op_rec = pred[y == 1].mean()
    op_prec = y[pred].mean()
    op_fpr = pred[y == 0].mean()
    baseline = y.mean()

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))

    ax = axes[0]
    ax.plot(rec, prec, color="#4C72B0", lw=2)
    ax.axhline(baseline, color="#888888", ls=":", lw=1.2)
    ax.scatter([op_rec], [op_prec], s=70, color="crimson", zorder=5,
               edgecolor="black", linewidth=0.6)
    ax.annotate(f"operating point\nBigWords > {thr:.1f}\n"
                f"P={op_prec:.2f}, R={op_rec:.2f}",
                xy=(op_rec, op_prec), xytext=(0.06, 0.12),
                textcoords="axes fraction", fontsize=8.5,
                arrowprops=dict(arrowstyle="->", lw=1, color="crimson"),
                color="crimson")
    ax.text(0.02, baseline + 0.015, f"no-skill baseline = {baseline:.2f}",
            fontsize=8, color="#555555")
    ax.set_xlabel("Recall (generated documents found)")
    ax.set_ylabel("Precision (of those flagged, share truly generated)")
    ax.set_title(f"Precision-recall   (AP = {ap:.3f})", fontsize=10)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0.55, 1.02)
    ax.grid(alpha=0.25)

    ax = axes[1]
    ax.plot(fpr, tpr, color="#55A868", lw=2)
    ax.plot([0, 1], [0, 1], color="#888888", ls=":", lw=1.2)
    ax.scatter([op_fpr], [op_rec], s=70, color="crimson", zorder=5,
               edgecolor="black", linewidth=0.6)
    ax.set_xlabel("False positive rate (human documents flagged)")
    ax.set_ylabel("True positive rate")
    ax.set_title(f"ROC   (AUC = {auc:.3f})", fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.25)

    fig.suptitle("RQ4: the BigWords rule across every threshold, not just the "
                 "chosen one", fontsize=11, y=1.00)
    fig.tight_layout()
    fig.subplots_adjust(top=0.84)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    plt.close(fig)
    REPORT_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(OUT, REPORT_COPY)

    pd.DataFrame({"threshold": np.append(pr_thr, np.nan),
                  "precision": prec, "recall": rec}).to_csv(POINTS, index=False)

    f1 = 2 * op_prec * op_rec / (op_prec + op_rec)
    print(f"Wrote {OUT}\nCopied to {REPORT_COPY}\nWrote {POINTS}\n")
    print(f"Average precision : {ap:.3f}   (no-skill {baseline:.3f})")
    print(f"ROC AUC           : {auc:.3f}   (no-skill 0.500)")
    print(f"Operating point   : threshold {thr:.2f}, precision {op_prec:.3f}, "
          f"recall {op_rec:.3f}, F1(generated) {f1:.3f}")


if __name__ == "__main__":
    main()
