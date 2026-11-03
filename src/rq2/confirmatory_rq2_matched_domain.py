"""
confirmatory_rq2_matched_domain: the matched-domain sub-analysis
planned in advance.

Quote from the original plan: "the matched-domain sub-analysis of RQ2 is run post
hoc on domains where both ecosystems have >= 20 libraries." This is
distinct from confirmatory_rq2_domain_stratified.py, which tests
domain variation *within* each ecosystem separately. This script holds
domain constant and compares Java vs Python *directly within* each
qualifying domain, the more direct test of "is the RQ1 ecosystem
effect actually a domain effect in disguise", since domain composition
cannot confound a comparison where domain is fixed.

Qualifying domains at frame_locked (>= 20 libraries in both
ecosystems): data (java=32, python=58), misc (java=33, python=24),
build-tooling (java=25, python=30). (The original plan anticipated web/data/
testing/build-tooling pre-freeze; actual composition differs.)

Method: per qualifying domain, per locked dimension: Mann-Whitney U
(two-sided) + Cliff's delta with 95% bootstrap CI (n_boot=2000),
Holm-Bonferroni over m=15 within each domain (three separate families,
mirroring the per-ecosystem family structure already used in RQ1 and
in the within-ecosystem RQ2 script).

Inputs:
  files/corpus/frame_<freeze-date>/LIWC-22 Results - libraries - LIWC Analysis.csv

Outputs:
  files/corpus/frame_<freeze-date>/confirmatory_rq2_matched_domain.csv

Usage:
    venv/bin/python3 src/rq2/confirmatory_rq2_matched_domain.py [--freeze-date <name>] [--min-n 20]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

N_BOOT = 2000
RNG_SEED = 402
ALPHA = 0.05
DELTA_THRESHOLD = 0.33


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
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
    n_a, n_b = len(a), len(b)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        ra = rng.choice(a, size=n_a, replace=True)
        rb = rng.choice(b, size=n_b, replace=True)
        boots[i] = cliffs_delta(ra, rb)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


def holm_bonferroni(pvals: list[float]) -> list[float]:
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
    ap.add_argument("--min-n", type=int, default=20,
                    help="minimum libraries per ecosystem for a domain to qualify")
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    liwc_csv = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    rq1_csv = frame_dir / "confirmatory_stats_results.csv"
    out_csv = frame_dir / "confirmatory_rq2_matched_domain.csv"

    if not liwc_csv.exists():
        raise SystemExit(f"LIWC output not found: {liwc_csv}")

    df = pd.read_csv(liwc_csv)
    rq1 = pd.read_csv(rq1_csv).set_index("dimension") if rq1_csv.exists() else None

    counts = df.groupby(["domain", "ecosystem"]).size().unstack(fill_value=0)
    qualifying = counts[(counts.get("java", 0) >= args.min_n) &
                        (counts.get("python", 0) >= args.min_n)].index.tolist()
    print(f"Qualifying domains (>= {args.min_n} libraries in both ecosystems): "
          f"{qualifying}")
    print(counts.loc[qualifying])

    rng = np.random.default_rng(RNG_SEED)
    rows = []
    for domain in qualifying:
        sub = df[df["domain"] == domain]
        java = sub[sub["ecosystem"] == "java"]
        py = sub[sub["ecosystem"] == "python"]
        print(f"\n{domain}: n_java={len(java)} n_python={len(py)}")

        domain_rows = []
        for col in LOCKED_DIMENSIONS:
            j = pd.to_numeric(java[col], errors="coerce").dropna().to_numpy()
            p = pd.to_numeric(py[col], errors="coerce").dropna().to_numpy()

            _, p_mwu = stats.mannwhitneyu(j, p, alternative="two-sided")
            d = cliffs_delta(j, p)
            ci_lo, ci_hi = bootstrap_delta_ci(j, p, rng)

            domain_rows.append({
                "domain": domain,
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

        holm = holm_bonferroni([r["MWU_p"] for r in domain_rows])
        for r, ph in zip(domain_rows, holm):
            r["MWU_p_holm"] = ph
            r["passes_matched_rule"] = (ph < ALPHA) and (abs(r["cliffs_delta"]) >= DELTA_THRESHOLD)
        rows.extend(domain_rows)

    res = pd.DataFrame(rows)

    if rq1 is not None:
        res["rq1_delta_all_domains"] = res["dimension"].map(
            lambda d: rq1.loc[d, "cliffs_delta"] if d in rq1.index else np.nan)
        res["rq1_passes_layer1"] = res["dimension"].map(
            lambda d: bool(rq1.loc[d, "passes_layer1"]) if d in rq1.index else False)

    res = res.sort_values(["domain", "cliffs_delta"], key=lambda s: s.abs() if s.name == "cliffs_delta" else s,
                          ascending=[True, False])
    res.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    print(f"\n=== Matched-domain sub-analysis (Holm over m={len(LOCKED_DIMENSIONS)} per domain) ===")
    display_cols = ["domain", "dimension", "median_java", "median_python",
                     "cliffs_delta", "cliff_magnitude", "direction",
                     "MWU_p_holm", "passes_matched_rule"]
    for domain in qualifying:
        sub = res[res["domain"] == domain][display_cols].copy()
        for c in ("median_java", "median_python", "cliffs_delta"):
            sub[c] = sub[c].apply(lambda v: f"{v:.3f}")
        sub["MWU_p_holm"] = sub["MWU_p_holm"].apply(lambda v: f"{v:.4g}")
        print(f"\n--- {domain} ---")
        print(sub.to_string(index=False))

    n_pass = int(res["passes_matched_rule"].sum())
    print(f"\n{n_pass} / {len(res)} (domain, dimension) cells pass the matched-domain "
          f"rule (Holm p < {ALPHA} AND |delta| >= {DELTA_THRESHOLD}).")


if __name__ == "__main__":
    main()
