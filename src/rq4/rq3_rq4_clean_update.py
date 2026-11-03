"""
rq3_rq4_clean_update: the RQ3/RQ4 numbers and figures that can be produced
from the rebuilt (clean-README) corpus WITHOUT LIWC.

Context. rq3_readme_scope_audit.py found 47/100 human READMEs
in the original RQ3 corpus were the parent repository's front page rather
than the library's own, 39/50 on the Java side. rq3_extend_java_clean.py
rebuilt the pool under an own-README rule plus a 50-word floor on both the
README and the API surface, rq3_select_clean_subset.py drew a fresh
n=50/ecosystem subset, and 158 new generations were run.

Tests 1, 2 and 4 are blocked on a manual LIWC-22 pass over the new corpus.
Everything here is LIWC-free and therefore runnable now:

  * edit-distance homogeneity (rq3_edit_distance.py's outputs, plotted)
  * 8-gram containment on all 200 new generated documents
  * the RQ4 BigWords detector, whose feature is recomputed from raw text

Old-vs-new comparisons are against the pre-rebuild corpus, kept beside the
new one as *_PRE_CLEAN_20260812.csv.

Outputs:
    files/analysis/figures/rq3_clean_01_edit_distance.png
    files/analysis/figures/rq4_clean_01_bigwords.png
    files/analysis/figures/rq4_clean_02_threshold_sweep.png
    files/analysis/rq3_rq4_clean_update.md

Usage:
    venv/bin/python3 src/rq4/rq3_rq4_clean_update.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]

from rq4_detector import (  # noqa: E402
    BIG_WORD_CHARS, RNG_SEED, features, load_corpus, best_threshold,
    cv_threshold_rule, evaluate,
)

RQ3_DIR = ROOT / "files" / "corpus" / "rq3"
FIG_DIR = ROOT / "files" / "analysis" / "figures"
OUT_MD = ROOT / "files" / "analysis" / "rq3_rq4_clean_update.md"

PROSE = RQ3_DIR / "rq3_libraries_prose.csv"
PROSE_OLD = RQ3_DIR / "rq3_libraries_prose_PRE_CLEAN_20260812.csv"
EDIT_PAIRED = RQ3_DIR / "rq3_edit_distance_paired.csv"
EDIT_HOMOG = RQ3_DIR / "rq3_edit_distance_homogeneity.csv"
OVERLAP = RQ3_DIR / "overlap_check" / "full_generation_check_results.csv"

SOURCES = ["human", "sonnet", "openai"]
COLOURS = {"human": "#4C72B0", "sonnet": "#DD8452", "openai": "#55A868"}


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------

def fig_edit_distance() -> None:
    """Per-document mean distance to the other documents in its own group:
    higher = that document sits further from its peers = more varied."""
    if not EDIT_HOMOG.exists():
        print(f"  skip edit-distance figure: {EDIT_HOMOG.name} not found")
        return
    d = pd.read_csv(EDIT_HOMOG)
    # Two measures per document; plot both rather than silently picking one
    # (an earlier version took the last column and drew Jaccard under an
    # edit-distance label).
    metrics = [("mean_dist_to_others", "normalised edit distance"),
               ("mean_jaccard_to_others", "Jaccard distance")]

    fig, axes = plt.subplots(2, 2, figsize=(10, 7.6))
    panels = [(r, c) for r in range(2) for c in range(2)]
    for (mi, (metric, mlabel)), eco in [((mi, m), e) for mi, m in enumerate(metrics)
                                        for e in ["java", "python"]]:
        ax = axes[mi][0 if eco == "java" else 1]
        sub = d[d.ecosystem == eco]
        data = [sub[sub.source == s][metric].dropna().to_numpy() for s in SOURCES]
        parts = ax.boxplot(data, tick_labels=SOURCES, widths=0.55, patch_artist=True,
                           showfliers=False, medianprops=dict(color="black"))
        for patch, s in zip(parts["boxes"], SOURCES):
            patch.set_facecolor(COLOURS[s])
            patch.set_alpha(0.55)
        rng = np.random.default_rng(RNG_SEED)
        for i, arr in enumerate(data, start=1):
            ax.scatter(rng.normal(i, 0.055, len(arr)), arr, s=9,
                       color="black", alpha=0.35, zorder=3)
        ax.set_title(f"{eco} — {mlabel}  (n = {len(data[0])} human, "
                     f"{len(data[1])} per model)", fontsize=10)
        ax.set_ylabel(f"mean {mlabel}\nto others in same group", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.suptitle("RQ3: human documents are further apart than either model's "
                 "(clean corpus, first 150 tokens)", fontsize=11, y=0.99)
    fig.subplots_adjust(top=0.90)
    out = FIG_DIR / "rq3_clean_01_edit_distance.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.name}")


def fig_bigwords(df: pd.DataFrame, threshold: float) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    for ax, eco in zip(axes, ["java", "python"]):
        sub = df[df.ecosystem == eco]
        data = [sub[sub.source == s]["BigWords"].to_numpy() for s in SOURCES]
        parts = ax.violinplot(data, showextrema=False, widths=0.85)
        for body, s in zip(parts["bodies"], SOURCES):
            body.set_facecolor(COLOURS[s])
            body.set_alpha(0.45)
        rng = np.random.default_rng(RNG_SEED)
        for i, (arr, s) in enumerate(zip(data, SOURCES), start=1):
            ax.scatter(rng.normal(i, 0.06, len(arr)), arr, s=11,
                       color=COLOURS[s], edgecolor="black", linewidth=0.3, zorder=3)
            ax.hlines(np.median(arr), i - 0.3, i + 0.3, color="black", lw=1.6, zorder=4)
        ax.axhline(threshold, color="crimson", ls="--", lw=1.3)
        ax.set_xticks([1, 2, 3])
        ax.set_xticklabels(SOURCES)
        ax.set_title(eco, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("BigWords (% of words >= 7 characters)")
    axes[1].text(3.45, threshold, f" rule: > {threshold:.1f}", color="crimson",
                 va="center", fontsize=9)
    fig.tight_layout()
    fig.suptitle("RQ4: the detector's one feature, on the clean corpus",
                 fontsize=11, y=0.99)
    fig.subplots_adjust(top=0.86)
    out = FIG_DIR / "rq4_clean_01_bigwords.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.name}")


def fig_threshold_sweep(df: pd.DataFrame, cv_f1: float) -> tuple[pd.DataFrame, float]:
    """In-sample macro-F1 across candidate cut-points. The peak here is
    optimistic by construction (it is chosen on the same rows it scores);
    the cross-validated figure is drawn alongside as the unbiased one."""
    x = df["BigWords"].to_numpy()
    y = (df.source != "human").astype(int).to_numpy()
    grid = np.quantile(x, np.linspace(0.02, 0.98, 120))
    rows = []
    for t in grid:
        pred = (x > t).astype(int)
        f1s = []
        for cls in (0, 1):
            tp = int(((pred == cls) & (y == cls)).sum())
            fp = int(((pred == cls) & (y != cls)).sum())
            fn = int(((pred != cls) & (y == cls)).sum())
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
        rows.append({"threshold": t, "macro_f1": float(np.mean(f1s))})
    sweep = pd.DataFrame(rows)
    peak = sweep.loc[sweep.macro_f1.idxmax()]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(sweep.threshold, sweep.macro_f1, color="#4C72B0", lw=1.8)
    ax.axvline(peak.threshold, color="crimson", ls="--", lw=1.2)
    ax.axhline(cv_f1, color="black", ls=":", lw=1.2)
    ax.annotate(f"in-sample peak {peak.macro_f1:.3f} at {peak.threshold:.1f}",
                xy=(peak.threshold, peak.macro_f1),
                xytext=(peak.threshold + 4.5, peak.macro_f1 - 0.12),
                fontsize=9, color="crimson",
                arrowprops=dict(arrowstyle="->", color="crimson", lw=1))
    ax.text(sweep.threshold.min() + 0.4, cv_f1 - 0.055,
            f"cross-validated {cv_f1:.3f}\n(threshold relearned per fold)",
            fontsize=9)
    ax.set_xlabel("BigWords threshold (% of words >= 7 characters)")
    ax.set_ylabel("macro-F1")
    ax.set_title("RQ4: threshold sweep, clean corpus", fontsize=11)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "rq4_clean_02_threshold_sweep.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.name}")
    return sweep, float(peak.threshold)


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

def location_spread_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for eco in ["java", "python"]:
        h = df[(df.ecosystem == eco) & (df.source == "human")]["BigWords"]
        for model in ["sonnet", "openai"]:
            l = df[(df.ecosystem == eco) & (df.source == model)]["BigWords"]
            rows.append({
                "ecosystem": eco, "model": model,
                "human_mean": round(h.mean(), 2), "human_sd": round(h.std(), 2),
                "llm_mean": round(l.mean(), 2), "llm_sd": round(l.std(), 2),
                "gap_in_human_sds": round((l.mean() - h.mean()) / h.std(), 2),
                "sd_ratio": round(l.std() / h.std(), 2),
                "llm_above_human_mean_plus_1sd":
                    f"{(l > h.mean() + h.std()).mean():.0%}",
                "human_above_own_mean_plus_1sd":
                    f"{(h > h.mean() + h.std()).mean():.0%}",
            })
    return pd.DataFrame(rows)


def error_analysis(df: pd.DataFrame, threshold: float) -> dict:
    d = df.copy()
    d["generated"] = d.source != "human"
    d["pred_generated"] = d.BigWords > threshold
    fa = d[(~d.generated) & d.pred_generated]
    miss = d[d.generated & (~d.pred_generated)]
    caught = d[d.generated & d.pred_generated]
    hit = d[(~d.generated) & (~d.pred_generated)]
    near = lambda s: int((s.BigWords - threshold).abs().le(2).sum())  # noqa: E731
    return {
        "n_false_alarms": len(fa), "n_misses": len(miss),
        "fa_median_words": int(fa.n_words.median()) if len(fa) else 0,
        "hit_median_words": int(hit.n_words.median()) if len(hit) else 0,
        "fa_median_bigwords": round(float(fa.BigWords.median()), 1) if len(fa) else 0,
        "fa_within_2pp": near(fa), "miss_within_2pp": near(miss),
        "fa_by_eco": fa.ecosystem.value_counts().to_dict(),
        "miss_by_model": miss.source.value_counts().to_dict(),
        "miss_by_eco": miss.ecosystem.value_counts().to_dict(),
        "miss_median_words": int(miss.n_words.median()) if len(miss) else 0,
        "caught_median_words": int(caught.n_words.median()) if len(caught) else 0,
        "sensitivity": round(len(caught) / max(len(caught) + len(miss), 1), 3),
        "specificity": round(len(hit) / max(len(hit) + len(fa), 1), 3),
    }


def corpus_comparison() -> pd.DataFrame:
    rows = []
    for tag, path in [("pre-clean", PROSE_OLD), ("clean", PROSE)]:
        if not path.exists():
            continue
        d = pd.read_csv(path)
        for eco in ["java", "python"]:
            for src in SOURCES:
                s = d[(d.ecosystem == eco) & (d.source == src)]
                rows.append({
                    "corpus": tag, "ecosystem": eco, "source": src, "n": len(s),
                    "median_words": int(s.n_words.median()),
                    "mean_code_share_pct": round(float(s.code_share_pct.mean()), 2),
                })
    return pd.DataFrame(rows)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_corpus()
    # load_corpus() appends its own n_words beside the CSV's, so the frame
    # carries two identically-named columns and df.n_words is a DataFrame.
    df = df.loc[:, ~df.columns.duplicated()]
    print(f"Corpus: {len(df)} documents "
          f"({(df.source == 'human').sum()} human, {(df.source != 'human').sum()} generated)\n")

    x = df["BigWords"].to_numpy()
    y = (df.source != "human").astype(int).to_numpy()
    rng = np.random.default_rng(RNG_SEED)
    res = evaluate(x, y, rng)
    thr = best_threshold(x, y)

    print("Figures:")
    fig_edit_distance()
    fig_bigwords(df, thr)
    sweep, peak_t = fig_threshold_sweep(df, res["macro_f1"])

    loc = location_spread_table(df)
    err = error_analysis(df, thr)
    cmp_tbl = corpus_comparison()

    overlap = pd.read_csv(OVERLAP) if OVERLAP.exists() else None
    paired = pd.read_csv(EDIT_PAIRED) if EDIT_PAIRED.exists() else None

    lines = ["# RQ3 / RQ4 on the clean corpus — what changed", "",
             "Generated by `src/rq4/rq3_rq4_clean_update.py`. LIWC-free; "
             "tests 1, 2 and 4 still need the manual LIWC-22 pass.", "",
             "## Corpus", "", cmp_tbl.to_markdown(index=False), ""]
    if overlap is not None:
        lines += ["## 8-gram containment (all 200 generated documents)", "",
                  f"- documents checked: **{len(overlap)}**",
                  f"- max containment: **{overlap.ngram_overlap.max():.4f}**",
                  f"- mean containment: **{overlap.ngram_overlap.mean():.5f}**",
                  f"- flagged on containment: **{int(overlap.ngram_flag.sum())}**",
                  f"- flagged on internal-path leakage: "
                  f"**{int(overlap.path_leak_flag.sum())}**", ""]
    lines += ["## RQ4 — BigWords location vs spread", "",
              loc.to_markdown(index=False), "",
              "## RQ4 — detector", "",
              f"- learned threshold (whole corpus): **BigWords > {thr:.1f}**",
              f"- cross-validated macro-F1: **{res['macro_f1']:.3f}** "
              f"(SD {res['macro_f1_sd']:.3f})",
              f"- accuracy: **{res['accuracy']:.3f}**",
              f"- permutation null: {res['permutation_null']:.3f}, "
              f"p = {res['permutation_p']:.4f}",
              f"- sensitivity {err['sensitivity']:.3f}, "
              f"specificity {err['specificity']:.3f}",
              f"- in-sample sweep peak: {sweep.macro_f1.max():.3f} at {peak_t:.1f} "
              f"(optimistic; shown only for the shape of the curve)", "",
              "### Errors", "",
              f"- false alarms: **{err['n_false_alarms']}** "
              f"(median {err['fa_median_words']} words vs "
              f"{err['hit_median_words']} for humans correctly classified; "
              f"{err['fa_within_2pp']} within 2 pp of the line; "
              f"by ecosystem {err['fa_by_eco']})",
              f"- misses: **{err['n_misses']}** "
              f"(median {err['miss_median_words']} words vs "
              f"{err['caught_median_words']} caught; "
              f"{err['miss_within_2pp']} within 2 pp; "
              f"by model {err['miss_by_model']}; by ecosystem {err['miss_by_eco']})", ""]
    if paired is not None:
        lines += ["## RQ3 — edit distance (paired, LIWC-free)", "",
                  paired.to_markdown(index=False), ""]

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT_MD}")
    print("\n" + loc.to_string(index=False))
    print("\nerrors:", err)


if __name__ == "__main__":
    main()
