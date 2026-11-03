"""
haskell_vs_oo_stats: FP-vs-OO paradigm contrast: Haskell vs. pooled
Java+Python, on the same 15 locked LIWC dimensions and decision rule as
confirmatory_liwc_stats.py.

Java and Python are pooled into a single "OO/imperative" comparison
group. This is justified specifically because RQ1's own confirmatory
result (and the duplicate-fix robustness check) found no detectable
difference between Java and Python on any of these 15 dimensions,
pooling them doesn't average over a real internal difference, so it
doesn't introduce a hidden confound into the Haskell contrast.

Inputs:
  files/corpus/frame_locked_corrected/LIWC-22 Results - libraries - LIWC Analysis.csv
      (the corrected, duplicate-free Java+Python corpus)
  files/corpus/frame_haskell_v2/LIWC-22 Results - libraries - LIWC Analysis.csv
      (the Haskell corpus, n=85, population-ceiling-limited)

Outputs:
  files/corpus/frame_haskell_v2/haskell_vs_oo_stats_results.csv

Usage:
    venv/bin/python3 src/rq1/haskell_vs_oo_stats.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import (  # noqa: E402
    LOCKED_DIMENSIONS, N_BOOT, RNG_SEED, ALPHA, DELTA_THRESHOLD,
    cliffs_delta, cliff_magnitude, bootstrap_delta_ci, holm_bonferroni,
)

OO_CSV = ROOT / "files" / "corpus" / "frame_locked_corrected" / "LIWC-22 Results - libraries - LIWC Analysis.csv"
FP_CSV = ROOT / "files" / "corpus" / "frame_haskell_v2" / "LIWC-22 Results - libraries - LIWC Analysis.csv"
OUT_CSV = ROOT / "files" / "corpus" / "frame_haskell_v2" / "haskell_vs_oo_stats_results.csv"


def main() -> None:
    if not OO_CSV.exists():
        raise SystemExit(f"OO (Java+Python) LIWC output not found: {OO_CSV}")
    if not FP_CSV.exists():
        raise SystemExit(f"Haskell LIWC output not found: {FP_CSV}")

    oo = pd.read_csv(OO_CSV)
    fp = pd.read_csv(FP_CSV)
    print(f"OO pool: {oo['ecosystem'].value_counts().to_dict()}")
    print(f"FP pool: {fp['ecosystem'].value_counts().to_dict()}")
    print(f"n_oo={len(oo)}  n_fp={len(fp)}")

    rng = np.random.default_rng(RNG_SEED)

    rows = []
    for col in LOCKED_DIMENSIONS:
        if col not in oo.columns or col not in fp.columns:
            raise SystemExit(f"locked dimension {col!r} missing from one of the LIWC outputs")
        o = pd.to_numeric(oo[col], errors="coerce").dropna().to_numpy()
        h = pd.to_numeric(fp[col], errors="coerce").dropna().to_numpy()

        _, p_mwu = stats.mannwhitneyu(h, o, alternative="two-sided")
        d = cliffs_delta(h, o)  # positive = haskell higher
        ci_lo, ci_hi = bootstrap_delta_ci(h, o, rng)

        rows.append({
            "dimension": col,
            "n_haskell": len(h),
            "n_oo": len(o),
            "median_haskell": float(np.median(h)),
            "median_oo": float(np.median(o)),
            "cliffs_delta": d,
            "cliffs_delta_ci_lo": ci_lo,
            "cliffs_delta_ci_hi": ci_hi,
            "cliff_magnitude": cliff_magnitude(d),
            "direction": "haskell_higher" if d > 0 else "oo_higher",
            "MWU_p": p_mwu,
        })

    res = pd.DataFrame(rows)
    res["MWU_p_holm"] = holm_bonferroni(res["MWU_p"].tolist())
    res["passes_layer1"] = (
        (res["MWU_p_holm"] < ALPHA) & (res["cliffs_delta"].abs() >= DELTA_THRESHOLD)
    )

    res = res.sort_values("cliffs_delta", key=lambda s: s.abs(), ascending=False)
    res.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}")

    print(f"\n=== Layer 1 — Haskell (FP) vs pooled Java+Python (OO), m={len(LOCKED_DIMENSIONS)}, Holm ===")
    display_cols = ["dimension", "median_haskell", "median_oo",
                     "cliffs_delta", "cliffs_delta_ci_lo", "cliffs_delta_ci_hi",
                     "cliff_magnitude", "direction", "MWU_p", "MWU_p_holm",
                     "passes_layer1"]
    sub = res[display_cols].copy()
    for c in ("median_haskell", "median_oo", "cliffs_delta",
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
