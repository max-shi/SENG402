"""
rq3_edit_distance_sensitivity: does the homogeneity result depend on the
truncation length?

rq3_edit_distance.py truncates every document to TRUNCATE_TOKENS=150 words
and drops anything shorter, which removes the length confound (LLM documents
are much longer, and longer documents drift apart on edit distance for
trivial reasons). But on this corpus *every* dropped document is human, no
generated document is under 150 tokens, so the primary analysis discards the
shortest quarter of the human side and nothing from either model.

That is exactly the shape of a selection effect that could manufacture the
"humans are more varied" result, so this sweeps K downward, trading length
control for coverage, and reports Cliff's delta at each step. At K=60 all 50
Python and 48/50 Java human documents are retained.

Usage:
    venv/bin/python3 src/rq3/rq3_edit_distance_sensitivity.py
"""
import sys
from pathlib import Path
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
import numpy as np, pandas as pd
from itertools import combinations
from scipy import stats
import rq3_edit_distance as ed
from confirmatory_liwc_stats import cliffs_delta

df = ed.load()
for K in [150, 120, 100, 80, 60]:
    ed.TRUNCATE_TOKENS = K
    df["tok_trunc"] = df["text"].map(lambda t: ed.tokens(t, K))
    out = []
    for eco in ed.ECOSYSTEMS:
        g_by_src = {}
        for src in ed.SOURCES:
            g = df[(df.ecosystem == eco) & (df.source == src)]
            g = g[g.n_tok >= K]
            docs = list(g.itertuples()); n = len(docs)
            D = np.zeros((n, n))
            for i, j in combinations(range(n), 2):
                D[i, j] = D[j, i] = ed.dist(docs[i].tok_trunc, docs[j].tok_trunc)
            g_by_src[src] = (np.array([np.delete(D[i], i).mean() for i in range(n)]), n)
        h, nh = g_by_src["human"]
        for m in ["sonnet", "openai"]:
            l, nl = g_by_src[m]
            d = cliffs_delta(h, l)
            p = stats.mannwhitneyu(h, l, alternative="two-sided").pvalue
            out.append(f"{eco:7s} vs {m:7s} n_h={nh:2d} delta={d:+.3f} p={p:.2e}")
    print(f"--- K={K} (human docs kept: java/python) ---")
    print("\n".join("  " + o for o in out))
