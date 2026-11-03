"""
pilot_docs_compare: compare the original pilot (docstrings and Javadoc) with
the rerun built from READMEs and docs folders.

Before LIWC-22 is run, this reports what can be computed from the raw text:
corpus size and a long-words share. Once the LIWC-22 output is saved as
    files/preprocess/pilot_docs_rerun/LIWC-22 Results - libraries - LIWC Analysis.csv
it also reruns the pilot's exact screening and compares all categories.

Outputs:
    files/preprocess/pilot_docs_rerun/liwc_stats_results.csv
    files/analysis/pilot_docs_comparison.csv
    files/analysis/pilot_docs_comparison.md

Usage:
    venv/bin/python3 src/pilot/pilot_docs_compare.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
import liwc_stats  # noqa: E402
from confirmatory_liwc_stats import LOCKED_DIMENSIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "files" / "preprocess" / "preprocess_output_13-05-26_21-50-10"
PILOT_TEXT = PILOT_DIR / "libraries.csv"
PILOT_LIWC = PILOT_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"
PILOT_STATS = ROOT / "files" / "analysis" / "liwc_stats_results.csv"
RERUN_DIR = ROOT / "files" / "preprocess" / "pilot_docs_rerun"
RERUN_TEXT = RERUN_DIR / "libraries.csv"
RERUN_LIWC = RERUN_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"
RERUN_STATS = RERUN_DIR / "liwc_stats_results.csv"
OUT_CSV = ROOT / "files" / "analysis" / "pilot_docs_comparison.csv"
OUT_MD = ROOT / "files" / "analysis" / "pilot_docs_comparison.md"
MAIN_STATS = ROOT / "files" / "corpus" / "frame_n2000" / "confirmatory_stats_results.csv"
ALPHA, MIN_DELTA = 0.05, 0.33
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def long_word_share(text: str) -> float:
    tokens = TOKEN_RE.findall(str(text))
    return 100 * sum(len(t) >= 7 for t in tokens) / len(tokens) if tokens else np.nan


def load_text(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[~df["library"].astype(str).str.startswith("_ALL_")].copy()
    df["ecosystem"] = df["ecosystem"].str.lower()
    df["long_words"] = df["text"].map(long_word_share)
    return df


def preview() -> list[str]:
    pilot, rerun = load_text(PILOT_TEXT), load_text(RERUN_TEXT)
    out = ["## Without LIWC-22", "",
           "Long words is my own count of words with 7 or more letters, not LIWC-22's score.", "",
           "| Language | Pilot libraries | Rerun libraries | Pilot median words | Rerun median words | Pilot median long words | Rerun median long words |",
           "|---|---|---|---|---|---|---|"]
    for eco in ("java", "python"):
        p, r = pilot[pilot.ecosystem == eco], rerun[rerun.ecosystem == eco]
        out.append(f"| {eco} | {len(p)} | {len(r)} | {p.n_words.median():,.0f} | {r.n_words.median():,.0f} "
                   f"| {p.long_words.median():.1f}% | {r.long_words.median():.1f}% |")
    j, py = {}, {}
    for name, df in (("Pilot", pilot), ("Rerun", rerun)):
        a = df[df.ecosystem == "java"].long_words.dropna().to_numpy()
        b = df[df.ecosystem == "python"].long_words.dropna().to_numpy()
        j[name] = liwc_stats.cliffs_delta(a, b)
        py[name] = stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
    out += ["", "| Java vs Python, long words | Cliff's delta | Unadjusted p |", "|---|---|---|"]
    out += [f"| {k} | {j[k]:+.3f} | {py[k]:.3g} |" for k in j]
    merged = pilot.merge(rerun, on=["library", "ecosystem"], suffixes=("_pilot", "_rerun"))
    r = stats.spearmanr(merged.long_words_pilot, merged.long_words_rerun, nan_policy="omit")
    out += ["", f"On the {len(merged)} libraries in both corpora, the long-words Spearman correlation "
                f"between docstrings and docs is {r.statistic:.2f}."]
    return out


def passes(df: pd.DataFrame) -> pd.Series:
    return (df["MWU_p_J_vs_P_holm"] < ALPHA) & (df["cliffs_d_J_vs_P"].abs() >= MIN_DELTA)


def java_vs_python(path: Path) -> pd.DataFrame:
    # Same test, effect size and Holm family as liwc_stats, without JavaScript.
    df = pd.read_csv(path)
    df["ecosystem"] = df["ecosystem"].str.lower()
    rows = []
    for col in liwc_stats.CANDIDATES:
        if col not in df.columns:
            continue
        v = pd.to_numeric(df[col], errors="coerce")
        j = v[df.ecosystem == "java"].dropna().to_numpy()
        p = v[df.ecosystem == "python"].dropna().to_numpy()
        rows.append({"metric": col, "median_java": np.median(j), "median_python": np.median(p),
                     "MWU_p_J_vs_P": stats.mannwhitneyu(j, p, alternative="two-sided").pvalue,
                     "cliffs_d_J_vs_P": liwc_stats.cliffs_delta(j, p)})
    res = pd.DataFrame(rows)
    res["MWU_p_J_vs_P_holm"] = liwc_stats.holm_bonferroni(res["MWU_p_J_vs_P"].tolist())
    return res


def against_main(t: pd.DataFrame) -> list[str]:
    # Docstring deltas are inflated by selection: these 15 were chosen on them.
    main = pd.read_csv(MAIN_STATS).set_index("dimension")["cliffs_delta"]
    j = t[t.locked_15].join(main.rename("main"))
    same = (np.sign(j.delta_docstrings) == np.sign(j.delta_docs)).sum()
    flips = j.index[np.sign(j.delta_docstrings) != np.sign(j.delta_docs)]
    binom = stats.binomtest(int(same), len(j), 0.5).pvalue
    out = ["", "## Locked 15, against the main study", "",
           f"Docstrings and docs point the same way on **{same} of {len(j)}** "
           f"(two-sided sign test against chance: p = {binom:.2f}). "
           f"Changed direction: {', '.join(flips)}.", "",
           "Main study: n=1000 per language. The 15 were chosen using the docstring effects, "
           "so selection inflates those; the docs effects don't have that bias.", "",
           "| Pilot text | Median abs. delta | Rank correlation with main | Same direction as main | Mean abs. gap to main |",
           "|---|---|---|---|---|"]
    for name, col in (("Docstrings", "delta_docstrings"), ("Docs", "delta_docs")):
        out.append(f"| {name} | {j[col].abs().median():.3f} | {stats.spearmanr(j[col], j.main).statistic:.2f} "
                   f"| {(np.sign(j[col]) == np.sign(j.main)).sum()} of {len(j)} | {(j[col] - j.main).abs().mean():.3f} |")
    out += ["", f"Main study median abs. delta: {j.main.abs().median():.3f}.", "",
            "| Category | Docstrings | Docs | Main | Docstrings and docs agree |", "|---|---|---|---|---|"]
    for m, r in j.sort_values("main").iterrows():
        agree = "yes" if np.sign(r.delta_docstrings) == np.sign(r.delta_docs) else ""
        out.append(f"| {m} | {r.delta_docstrings:+.3f} | {r.delta_docs:+.3f} | {r.main:+.3f} | {agree} |")
    return out


def compare() -> list[str]:
    java_vs_python(RERUN_LIWC).to_csv(RERUN_STATS, index=False)
    a = pd.read_csv(PILOT_STATS).set_index("metric")
    b = pd.read_csv(RERUN_STATS).set_index("metric")
    t = pd.DataFrame({
        "delta_docstrings": a["cliffs_d_J_vs_P"], "holm_p_docstrings": a["MWU_p_J_vs_P_holm"],
        "passes_docstrings": passes(a), "delta_docs": b["cliffs_d_J_vs_P"],
        "holm_p_docs": b["MWU_p_J_vs_P_holm"], "passes_docs": passes(b),
    }).dropna(subset=["delta_docstrings", "delta_docs"])
    t["passes_docstrings"] = t["passes_docstrings"].astype(bool)
    t["passes_docs"] = t["passes_docs"].astype(bool)
    t["locked_15"] = t.index.isin(LOCKED_DIMENSIONS)
    t = t.sort_values("delta_docstrings", key=np.abs, ascending=False)
    t.to_csv(OUT_CSV)
    both = t[t.passes_docstrings & t.passes_docs]
    only_a = t[t.passes_docstrings & ~t.passes_docs]
    only_b = t[~t.passes_docstrings & t.passes_docs]
    sign = (np.sign(t.delta_docstrings) == np.sign(t.delta_docs)).mean()
    rho = stats.spearmanr(t.delta_docstrings, t.delta_docs).statistic
    out = ["## With LIWC-22", "",
           f"Java vs Python rule: Holm p < {ALPHA} and |delta| >= {MIN_DELTA}, across {len(t)} categories.", "",
           f"- Pass on docstrings: **{int(t.passes_docstrings.sum())}**",
           f"- Pass on docs: **{int(t.passes_docs.sum())}**",
           f"- Pass on both: **{len(both)}**: {', '.join(both.index) or 'none'}",
           f"- Docstrings only: {', '.join(only_a.index) or 'none'}",
           f"- Docs only: {', '.join(only_b.index) or 'none'}",
           f"- Same direction: {sign:.0%} of categories. Spearman correlation of the deltas: {rho:.2f}.", "",
           "| Category | Locked 15 | Delta, docstrings | Pass | Delta, docs | Pass |", "|---|---|---|---|---|---|"]
    for m, r in t[t.locked_15 | t.passes_docs].iterrows():
        out.append(f"| {m} | {'yes' if r.locked_15 else ''} | {r.delta_docstrings:+.3f} | {'yes' if r.passes_docstrings else ''} "
                   f"| {r.delta_docs:+.3f} | {'yes' if r.passes_docs else ''} |")
    return out + against_main(t)


def main() -> None:
    lines = ["# Pilot: docstrings vs READMEs and docs", "",
             "Generated by `src/pilot/pilot_docs_compare.py`. Same libraries and pinned tags; "
             "the rerun uses the main study's extraction and filters.", ""]
    lines += preview()
    if RERUN_LIWC.exists():
        lines += [""] + compare()
    else:
        lines += ["", f"LIWC-22 output not found yet: `{RERUN_LIWC.relative_to(ROOT)}`"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
