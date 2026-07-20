"""
confirmatory_rq2_domain_stratified — RQ2, the sampling-side gatekeeper for RQ1.

Per methods_and_results.md §8.2.3: within each ecosystem (Java, Python;
JavaScript is dropped from the confirmatory phase, §7.6.7), group libraries
by their domain tag and run Kruskal-Wallis across domains on each of the 15
locked dimensions. Domains with n<3 in an ecosystem are pooled into "other"
before testing. H is converted to the rank-based effect size eta^2_H, and
Holm-Bonferroni is applied over m=15 separately within each ecosystem.

A derived confound matrix cross-tabulates RQ1's per-dimension Cliff's delta
(between ecosystems, from confirmatory_stats_results.csv) against RQ2's
eta^2_H (within ecosystem, domain). A cell is flagged "possibly confounded"
when |delta| >= 0.33 AND eta^2_H >= 0.06 in either ecosystem for that
dimension (§8.2.4).

Inputs:
  files/corpus/frame_<freeze-date>/LIWC-22 Results - libraries - LIWC Analysis.csv
  files/corpus/frame_<freeze-date>/confirmatory_stats_results.csv

Outputs:
  files/corpus/frame_<freeze-date>/confirmatory_rq2_domain_stratified.csv

Usage:
    venv/bin/python3 src/analysis/confirmatory_rq2_domain_stratified.py [--freeze-date YYYYMMDD]
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

MIN_DOMAIN_N = 3
ALPHA = 0.05
DELTA_CONFOUND_THRESHOLD = 0.33
ETA2_CONFOUND_THRESHOLD = 0.06


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


def pooled_domain_series(df_eco: pd.DataFrame) -> pd.Series:
    """Domain labels with any domain of size < MIN_DOMAIN_N pooled into 'other'."""
    counts = df_eco["domain"].value_counts()
    small = set(counts[counts < MIN_DOMAIN_N].index)
    if not small:
        return df_eco["domain"]
    return df_eco["domain"].where(~df_eco["domain"].isin(small), "other")


def eta_squared_h(h: float, k: int, n: int) -> float:
    """Rank-based effect size for Kruskal-Wallis, bounded in [0, 1]."""
    if n - k <= 0:
        return float("nan")
    return max(0.0, (h - k + 1) / (n - k))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date", default="20260712")
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    liwc_csv = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    rq1_csv = frame_dir / "confirmatory_stats_results.csv"
    out_csv = frame_dir / "confirmatory_rq2_domain_stratified.csv"

    if not liwc_csv.exists():
        raise SystemExit(f"LIWC output not found: {liwc_csv}")
    if not rq1_csv.exists():
        raise SystemExit(f"RQ1 results not found: {rq1_csv} (run confirmatory_liwc_stats.py first)")

    df = pd.read_csv(liwc_csv)
    rq1 = pd.read_csv(rq1_csv).set_index("dimension")

    rows = []
    for eco in ("java", "python"):
        df_eco = df[df["ecosystem"] == eco].copy()
        df_eco["domain_pooled"] = pooled_domain_series(df_eco)
        domain_counts = df_eco["domain_pooled"].value_counts().to_dict()
        print(f"{eco}: {len(df_eco)} libraries, domains = {domain_counts}")

        pvals_this_eco = []
        eco_rows = []
        for dim in LOCKED_DIMENSIONS:
            groups = {
                dom: pd.to_numeric(g[dim], errors="coerce").dropna().to_numpy()
                for dom, g in df_eco.groupby("domain_pooled")
            }
            groups = {d: v for d, v in groups.items() if len(v) > 0}
            if len(groups) < 2:
                print(f"  skipping {dim!r}: fewer than 2 domain groups")
                continue

            h, p = stats.kruskal(*groups.values())
            k = len(groups)
            n = sum(len(v) for v in groups.values())
            eta2 = eta_squared_h(h, k, n)

            eco_rows.append({
                "ecosystem": eco,
                "dimension": dim,
                "n_domains": k,
                "n_libraries": n,
                "H": h,
                "KW_p": p,
                "eta2_H": eta2,
            })
            pvals_this_eco.append(p)

        holm = holm_bonferroni([r["KW_p"] for r in eco_rows])
        for r, ph in zip(eco_rows, holm):
            r["KW_p_holm"] = ph
        rows.extend(eco_rows)

    res = pd.DataFrame(rows)

    # Confound matrix: join RQ1's |delta| onto each (dimension, ecosystem) row.
    res["rq1_abs_delta"] = res["dimension"].map(lambda d: abs(rq1.loc[d, "cliffs_delta"]))
    res["rq1_direction"] = res["dimension"].map(lambda d: rq1.loc[d, "direction"])
    res["domain_effect_significant"] = (res["KW_p_holm"] < ALPHA) & (res["eta2_H"] >= ETA2_CONFOUND_THRESHOLD)
    res["possibly_confounded"] = (
        (res["rq1_abs_delta"] >= DELTA_CONFOUND_THRESHOLD) & res["domain_effect_significant"]
    )

    res = res.sort_values(["ecosystem", "eta2_H"], ascending=[True, False])
    res.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    print(f"\n=== RQ2 — within-ecosystem domain-stratified effect sizes (m={len(LOCKED_DIMENSIONS)} per ecosystem, Holm) ===")
    display_cols = ["ecosystem", "dimension", "n_domains", "n_libraries",
                     "H", "KW_p", "KW_p_holm", "eta2_H",
                     "rq1_abs_delta", "domain_effect_significant", "possibly_confounded"]
    sub = res[display_cols].copy()
    for c in ("H", "eta2_H", "rq1_abs_delta"):
        sub[c] = sub[c].apply(lambda v: f"{v:.3f}")
    for c in ("KW_p", "KW_p_holm"):
        sub[c] = sub[c].apply(lambda v: f"{v:.4g}")
    print(sub.to_string(index=False))

    n_sig = int(res["domain_effect_significant"].sum())
    n_confound = int(res["possibly_confounded"].sum())
    print(f"\n{n_sig} / {len(res)} (ecosystem, dimension) cells show a significant "
          f"within-ecosystem domain effect (Holm p < {ALPHA} AND eta2_H >= {ETA2_CONFOUND_THRESHOLD}).")
    print(f"{n_confound} cells are flagged as possibly confounding an RQ1 finding "
          f"(also |delta| >= {DELTA_CONFOUND_THRESHOLD} on that dimension).")


if __name__ == "__main__":
    main()
