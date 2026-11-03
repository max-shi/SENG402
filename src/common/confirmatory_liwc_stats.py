"""
confirmatory_liwc_stats: Layer 1 (detectability) re-test of the 15 locked
LIWC-22 dimensions on the confirmatory corpus.

Per RULES.md:
  - Java vs Python only (JavaScript dropped from the confirmatory phase)
  - Only the 15 locked dimensions (locked), m=15
  - Mann-Whitney U (two-sided) + Cliff's delta with 95% percentile bootstrap CI
    (n_boot=2000)
  - Holm-Bonferroni correction over m=15
  - Layer 1 decision rule: Holm-adjusted p < 0.05 AND |delta| >= 0.33

Inputs:
  files/corpus/frame_<freeze-date>/LIWC-22 Results - libraries - LIWC Analysis.csv

Outputs:
  files/corpus/frame_<freeze-date>/confirmatory_stats_results.csv

Usage:
    venv/bin/python3 src/common/confirmatory_liwc_stats.py [--freeze-date <name>]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

# The 15 dimensions locked (RULES.md).
LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

N_BOOT = 2000
RNG_SEED = 402  # reused from the sampling-frame seed for reproducibility
ALPHA = 0.05
DELTA_THRESHOLD = 0.33


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Non-parametric effect size in [-1, 1]; P(a>b) - P(a<b)."""
    a = np.asarray(a); b = np.asarray(b)
    diffs = a[:, None] - b[None, :]
    return (np.sum(diffs > 0) - np.sum(diffs < 0)) / (len(a) * len(b))


def cliff_magnitude(d: float) -> str:
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def bootstrap_delta_ci(a: np.ndarray, b: np.ndarray, rng: np.random.Generator,
                        n_boot: int = N_BOOT) -> tuple[float, float]:
    """95% percentile bootstrap CI for Cliff's delta."""
    n_a, n_b = len(a), len(b)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        ra = rng.choice(a, size=n_a, replace=True)
        rb = rng.choice(b, size=n_b, replace=True)
        boots[i] = cliffs_delta(ra, rb)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date", default="locked")
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    liwc_csv = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    out_csv = frame_dir / "confirmatory_stats_results.csv"

    if not liwc_csv.exists():
        raise SystemExit(f"LIWC output not found: {liwc_csv}")

    df = pd.read_csv(liwc_csv)
    print(f"Loaded {len(df)} libraries: {df['ecosystem'].value_counts().to_dict()}")

    java = df[df["ecosystem"] == "java"]
    py = df[df["ecosystem"] == "python"]
    print(f"n_java={len(java)}  n_python={len(py)}")

    rng = np.random.default_rng(RNG_SEED)

    rows = []
    for col in LOCKED_DIMENSIONS:
        if col not in df.columns:
            raise SystemExit(f"locked dimension {col!r} missing from LIWC output")
        j = pd.to_numeric(java[col], errors="coerce").dropna().to_numpy()
        p = pd.to_numeric(py[col], errors="coerce").dropna().to_numpy()

        _, p_mwu = stats.mannwhitneyu(j, p, alternative="two-sided")
        d = cliffs_delta(j, p)
        ci_lo, ci_hi = bootstrap_delta_ci(j, p, rng)

        rows.append({
            "dimension": col,
            "n_java": len(j),
            "n_python": len(p),
            "median_java": float(np.median(j)),
            "median_python": float(np.median(p)),
            "cliffs_delta": d,
            "cliffs_delta_ci_lo": ci_lo,
            "cliffs_delta_ci_hi": ci_hi,
            "cliff_magnitude": cliff_magnitude(d),
            "direction": "java_higher" if d > 0 else "python_higher",
            "MWU_p": p_mwu,
        })

    res = pd.DataFrame(rows)
    res["MWU_p_holm"] = holm_bonferroni(res["MWU_p"].tolist())
    res["passes_layer1"] = (
        (res["MWU_p_holm"] < ALPHA) & (res["cliffs_delta"].abs() >= DELTA_THRESHOLD)
    )

    res = res.sort_values("cliffs_delta", key=lambda s: s.abs(), ascending=False)
    res.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    print(f"\n=== Layer 1 — confirmatory Java vs Python (m={len(LOCKED_DIMENSIONS)}, Holm) ===")
    display_cols = ["dimension", "median_java", "median_python",
                     "cliffs_delta", "cliffs_delta_ci_lo", "cliffs_delta_ci_hi",
                     "cliff_magnitude", "direction", "MWU_p", "MWU_p_holm",
                     "passes_layer1"]
    sub = res[display_cols].copy()
    for c in ("median_java", "median_python", "cliffs_delta",
              "cliffs_delta_ci_lo", "cliffs_delta_ci_hi"):
        sub[c] = sub[c].apply(lambda v: f"{v:.3f}")
    for c in ("MWU_p", "MWU_p_holm"):
        sub[c] = sub[c].apply(lambda v: f"{v:.4g}")
    print(sub.to_string(index=False))

    n_pass = int(res["passes_layer1"].sum())
    print(f"\n{n_pass} / {len(res)} locked dimensions pass Layer 1 "
          f"(Holm p < {ALPHA} AND |delta| >= {DELTA_THRESHOLD}).")


if __name__ == "__main__":
    main()
