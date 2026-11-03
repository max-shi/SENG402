"""
liwc_stats: statistical screening of LIWC-22 outputs across ecosystems.

Runs, per LIWC dimension:
  - Mann-Whitney U (Java vs Python) with Holm-Bonferroni correction
  - Cliff's delta effect size
  - Kruskal-Wallis H (three-way: Java/Python/JavaScript)
  - Dunn post-hoc pairwise tests with Holm correction

Inputs:
  CSV at LIWC_CSV with first 4 columns = library, ecosystem, domain, organisation
  and remaining columns = LIWC-22 dimensions.
  Three aggregate rows ('_ALL_JAVA', '_ALL_PYTHON', '_ALL_JAVASCRIPT') are dropped.

Outputs:
  - prints summary tables to stdout
  - writes machine-readable CSV to OUT_CSV
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
LIWC_CSV = Path(
    ROOT / "files/preprocess/"
    "preprocess_output_13-05-26_21-50-10/"
    "LIWC-22 Results - libraries - LIWC Analysis.csv"
)
OUT_CSV = ROOT / "files/analysis/liwc_stats_results.csv"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

META_COLS = ["library", "ecosystem", "domain", "organisation",
             "n_chunks", "n_words", "Segment", "WC"]

# Candidate LIWC dimensions to screen.
CANDIDATES = [
    # summary indices
    "Analytic", "Clout", "Authentic", "Tone",
    # style
    "WPS", "BigWords", "Dic",
    # pronoun / perspective
    "i", "we", "you", "shehe", "they", "ipron", "pronoun",
    # cognition / hedging
    "insight", "cause", "discrep", "tentat", "certitude", "differ",
    "cogproc", "Cognition",
    # affect
    "Affect", "tone_pos", "tone_neg",
    "emotion", "emo_pos", "emo_neg", "emo_anx", "emo_anger", "emo_sad",
    # drives
    "Drives", "affiliation", "achieve", "power",
    # social
    "Social", "socbehav", "prosocial", "polite", "conflict", "moral",
    # needs/wants
    "need", "want", "acquire", "lack", "fulfill", "reward", "risk",
    "curiosity", "allure",
    # perception
    "Perception", "attention", "motion", "space", "visual",
    # time
    "time", "focuspast", "focuspresent", "focusfuture",
]


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Non-parametric effect size in [-1, 1]; P(a>b) - P(a<b)."""
    a = np.asarray(a); b = np.asarray(b)
    n_a, n_b = len(a), len(b)
    # Vectorised pairwise comparison.
    diffs = a[:, None] - b[None, :]
    return (np.sum(diffs > 0) - np.sum(diffs < 0)) / (n_a * n_b)


def cliff_magnitude(d: float) -> str:
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def holm_bonferroni(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni step-down correction."""
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    running_max = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * pvals[idx]
        running_max = max(running_max, val)
        adj[idx] = min(running_max, 1.0)
    return adj.tolist()


def dunn_posthoc(groups: dict[str, np.ndarray]) -> dict[tuple[str, str], float]:
    """Dunn's post-hoc test using ranks of pooled samples.

    Returns raw (uncorrected) two-sided p-values per pair.
    """
    names = list(groups.keys())
    all_vals = np.concatenate([groups[n] for n in names])
    ranks = stats.rankdata(all_vals)
    # mean rank per group
    idx = 0
    mean_ranks, sizes = {}, {}
    for n in names:
        sz = len(groups[n])
        mean_ranks[n] = ranks[idx:idx + sz].mean()
        sizes[n] = sz
        idx += sz
    N = len(all_vals)
    # tie correction
    _, counts = np.unique(all_vals, return_counts=True)
    tie_term = (counts ** 3 - counts).sum()
    var = (N * (N + 1) - tie_term / (N - 1)) / 12.0
    out = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            se = np.sqrt(var * (1 / sizes[a] + 1 / sizes[b]))
            z = (mean_ranks[a] - mean_ranks[b]) / se
            p = 2 * (1 - stats.norm.cdf(abs(z)))
            out[(a, b)] = p
    return out


def main() -> None:
    df = pd.read_csv(LIWC_CSV)
    # Drop aggregate rows.
    df = df[~df["library"].str.startswith("_ALL_")].copy()
    print(f"Loaded {len(df)} libraries: "
          f"{df['ecosystem'].value_counts().to_dict()}")

    java = df[df["ecosystem"] == "java"]
    py = df[df["ecosystem"] == "python"]
    js = df[df["ecosystem"] == "javascript"]

    rows = []
    for col in CANDIDATES:
        if col not in df.columns:
            print(f"  skipping {col!r}: column not present")
            continue
        j = pd.to_numeric(java[col], errors="coerce").dropna().to_numpy()
        p = pd.to_numeric(py[col], errors="coerce").dropna().to_numpy()
        s = pd.to_numeric(js[col], errors="coerce").dropna().to_numpy()
        if min(len(j), len(p), len(s)) < 5:
            continue

        # Two-group J vs P
        u_jp, p_jp = stats.mannwhitneyu(j, p, alternative="two-sided")
        d_jp = cliffs_delta(j, p)
        # Two-group J vs JS and P vs JS for context
        u_jjs, p_jjs = stats.mannwhitneyu(j, s, alternative="two-sided")
        d_jjs = cliffs_delta(j, s)
        u_pjs, p_pjs = stats.mannwhitneyu(p, s, alternative="two-sided")
        d_pjs = cliffs_delta(p, s)
        # Three-way Kruskal-Wallis
        h, p_kw = stats.kruskal(j, p, s)
        # Dunn post-hoc (raw p-values; Holm corrected across the three pairs)
        dunn = dunn_posthoc({"java": j, "python": p, "javascript": s})

        rows.append({
            "metric": col,
            "median_java": float(np.median(j)),
            "median_python": float(np.median(p)),
            "median_js": float(np.median(s)),
            "iqr_java": float(np.subtract(*np.percentile(j, [75, 25]))),
            "iqr_python": float(np.subtract(*np.percentile(p, [75, 25]))),
            "iqr_js": float(np.subtract(*np.percentile(s, [75, 25]))),
            "MWU_p_J_vs_P": p_jp,
            "cliffs_d_J_vs_P": d_jp,
            "cliff_mag_J_vs_P": cliff_magnitude(d_jp),
            "MWU_p_J_vs_JS": p_jjs,
            "cliffs_d_J_vs_JS": d_jjs,
            "MWU_p_P_vs_JS": p_pjs,
            "cliffs_d_P_vs_JS": d_pjs,
            "KW_H": h,
            "KW_p": p_kw,
            "dunn_p_J_P": dunn[("java", "python")],
            "dunn_p_J_JS": dunn[("java", "javascript")],
            "dunn_p_P_JS": dunn[("python", "javascript")],
        })

    res = pd.DataFrame(rows)

    # Holm correction across the candidate family for each test of interest.
    res["MWU_p_J_vs_P_holm"] = holm_bonferroni(res["MWU_p_J_vs_P"].tolist())
    res["KW_p_holm"] = holm_bonferroni(res["KW_p"].tolist())

    res.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}")

    # Pretty print: top hits J vs P
    print("\n=== Java vs Python (sorted by Holm-adjusted MWU p-value) ===")
    cols = ["metric", "median_java", "median_python",
            "cliffs_d_J_vs_P", "cliff_mag_J_vs_P",
            "MWU_p_J_vs_P", "MWU_p_J_vs_P_holm"]
    sub = res.sort_values("MWU_p_J_vs_P_holm")[cols].copy()
    for c in ("MWU_p_J_vs_P", "MWU_p_J_vs_P_holm"):
        sub[c] = sub[c].apply(lambda v: f"{v:.4g}")
    for c in ("median_java", "median_python", "cliffs_d_J_vs_P"):
        sub[c] = sub[c].apply(lambda v: f"{v:.3f}")
    print(sub.to_string(index=False))

    # Three-way summary
    print("\n=== Three-way Kruskal-Wallis (sorted by Holm-adjusted KW p) ===")
    cols = ["metric", "median_java", "median_python", "median_js",
            "KW_H", "KW_p", "KW_p_holm",
            "dunn_p_J_P", "dunn_p_J_JS", "dunn_p_P_JS"]
    sub = res.sort_values("KW_p_holm")[cols].copy()
    for c in ("KW_p", "KW_p_holm", "dunn_p_J_P", "dunn_p_J_JS", "dunn_p_P_JS"):
        sub[c] = sub[c].apply(lambda v: f"{v:.4g}")
    for c in ("median_java", "median_python", "median_js", "KW_H"):
        sub[c] = sub[c].apply(lambda v: f"{v:.3f}")
    print(sub.to_string(index=False))


if __name__ == "__main__":
    main()
