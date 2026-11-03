"""
rq3_edit_distance: textual similarity between human and LLM documentation,
measured with normalised word-level edit distance.

Why this exists. Every RQ3 result so far rests on one instrument: LIWC-22. That
is a real single-point-of-failure, and this project has already shown twice that
LIWC can produce large, significant, replicated effects that mean nothing
(see rq3_affect_token_check.py). This script measures the same corpus with a
completely independent instrument that has no dictionary, no psycholinguistic
theory, and no register assumptions: how many word-level edits separate two
documents. If the LIWC-based conclusions survive here, they are not artefacts of
LIWC. If they do not, that is worth knowing before relying on them.

Three questions, each answering something the LIWC analysis cannot:

**Check A, Regurgitation.** For each library, how far is each generated document from
   the *real* README for that same library? A near-zero distance would indicate
   the model reproduced documentation it had memorised rather than inferring
   from the API surface. This complements the n-gram containment check in
   rq3_overlap_check.py with a measure sensitive to structure rather than to
   shared phrases.

**Check B, Model agreement.** Is d(sonnet, openai) smaller than d(human, sonnet) and
   d(human, openai) for the same library? Two independently developed models
   converging on a similar text, while both diverge from the human, is direct
   evidence of a shared machine register --- established without LIWC.

**Check C, Cross-library homogeneity.** Within one ecosystem and
   one author type, how far apart are documents about *different* libraries?
   RQ3's dispersion result (test 4) claims human documentation spans a wider
   stylistic range than LLM documentation. If true, human documents about
   different libraries should be textually further apart than LLM documents
   about different libraries. This is the same claim measured a completely
   different way.

Two design decisions that the result depends on:

* **Word-level, not character-level.** Style here is a matter of word choice
  and phrasing. Character-level distance is dominated by morphology,
  punctuation and identifier spelling, which is not the construct of interest.
  Tokens are lowercased words; punctuation is discarded.

* **Length is controlled by truncation, and this is not optional.** Normalised
  edit distance is `distance / max(len_a, len_b)`, so two documents of very
  different lengths score as distant almost by construction. In this corpus the
  human documents range from 10 to 12,789 words while the LLM documents range
  from 143 to 1,277 --- human length variance is far larger. Comparing raw
  documents would therefore "find" that human documents are more spread out
  purely as an artefact of their length distribution, which is precisely the
  claim under test. The primary analysis truncates every document to its first
  TRUNCATE_TOKENS words and drops documents shorter than that, removing the
  confound entirely. The untruncated figures are also reported, clearly marked,
  so the size of the confound is visible rather than hidden.

  Note that the length difference is itself a finding and is reported
  separately as a descriptive statistic --- it just must not be allowed to
  masquerade as a similarity result.

* **Per-document means, not raw pairs.** Each document participates in n-1
  pairs, so pairwise distances are not independent and a test over them would
  be pseudo-replicated. Each document is therefore reduced to its mean distance
  to all other documents in its group, giving one value per document, and tests
  run over those.

Outputs:
    files/corpus/rq3/rq3_edit_distance_paired.csv      per library
    files/corpus/rq3/rq3_edit_distance_homogeneity.csv per document
    files/corpus/rq3/rq3_edit_distance_summary.csv     group-level summary

Usage:
    venv/bin/python3 src/rq3/rq3_edit_distance.py
"""
from __future__ import annotations

import csv
import re
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz.distance import Levenshtein
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import cliffs_delta, cliff_magnitude, RNG_SEED  # noqa: E402

CORPUS = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries_prose.csv"
OUT_DIR = ROOT / "files" / "corpus" / "rq3"

MODELS = ["sonnet", "openai"]
ECOSYSTEMS = ["java", "python"]
SOURCES = ["human"] + MODELS

# Primary analysis truncates to this many tokens. 150 keeps 79 of 100 libraries
# with all three sources intact while removing the length confound; larger
# values lose libraries fast (K=300 keeps only 52).
TRUNCATE_TOKENS = 150

WORD_RE = re.compile(r"[A-Za-z']+")


def tokens(text: str, limit: int | None = None) -> list[str]:
    t = [w.lower() for w in WORD_RE.findall(str(text))]
    return t[:limit] if limit else t


def dist(a: list[str], b: list[str]) -> float:
    """Normalised word-level edit distance in [0, 1]. 0 = identical."""
    return Levenshtein.normalized_distance(a, b)


def jaccard_dist(a: list[str], b: list[str]) -> float:
    """Vocabulary-only distance: 1 - |A and B| / |A or B| over token SETS.

    Reported alongside edit distance because the two fail differently. Edit
    distance is a *sequence* measure: two documents using identical vocabulary
    in a different order score as maximally distant. On this corpus it
    saturates near 1.0 for every pair, so it orders documents reliably but its
    absolute values carry little information. Jaccard ignores order entirely
    and sits lower (0.87-0.90), making it the more sensitive of the two for
    vocabulary-level similarity. Where they disagree, that disagreement is
    reported rather than resolved by preferring whichever is convenient.
    """
    A, B = set(a), set(b)
    return 1 - len(A & B) / len(A | B) if (A or B) else 0.0


def load() -> pd.DataFrame:
    csv.field_size_limit(sys.maxsize)
    df = pd.read_csv(CORPUS)
    df["tok_full"] = df["text"].map(lambda t: tokens(t))
    df["tok_trunc"] = df["text"].map(lambda t: tokens(t, TRUNCATE_TOKENS))
    df["n_tok"] = df["tok_full"].map(len)
    return df


def paired_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Checks A and B: regurgitation, and model-vs-model agreement, per library."""
    rows = []
    for (lib, eco), g in df.groupby(["library", "ecosystem"]):
        by = {r["source"]: r for _, r in g.iterrows()}
        if set(by) != set(SOURCES):
            continue
        long_enough = all(by[s]["n_tok"] >= TRUNCATE_TOKENS for s in SOURCES)
        rec = {"library": lib, "ecosystem": eco, "length_controlled": long_enough}
        for a, b in [("human", "sonnet"), ("human", "openai"), ("sonnet", "openai")]:
            rec[f"d_{a}_{b}"] = round(dist(by[a]["tok_trunc"], by[b]["tok_trunc"]), 4)
            rec[f"d_{a}_{b}_full"] = round(dist(by[a]["tok_full"], by[b]["tok_full"]), 4)
        rows.append(rec)
    return pd.DataFrame(rows)


def homogeneity_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Check C: mean distance from each document to every other document about a
    DIFFERENT library, within the same ecosystem and author type."""
    rows = []
    for eco in ECOSYSTEMS:
        for src in SOURCES:
            g = df[(df.ecosystem == eco) & (df.source == src)]
            g = g[g.n_tok >= TRUNCATE_TOKENS]
            docs = list(g.itertuples())
            n = len(docs)
            if n < 3:
                continue
            D = np.zeros((n, n))
            J = np.zeros((n, n))
            for i, j in combinations(range(n), 2):
                D[i, j] = D[j, i] = dist(docs[i].tok_trunc, docs[j].tok_trunc)
                J[i, j] = J[j, i] = jaccard_dist(docs[i].tok_trunc, docs[j].tok_trunc)
            for i, doc in enumerate(docs):
                rows.append({
                    "library": doc.library, "ecosystem": eco, "source": src,
                    "n_in_group": n,
                    "mean_dist_to_others": round(float(np.delete(D[i], i).mean()), 4),
                    "mean_jaccard_to_others": round(float(np.delete(J[i], i).mean()), 4),
                })
    return pd.DataFrame(rows)


def main() -> None:
    df = load()
    print(f"Loaded {len(df)} documents. Truncation K={TRUNCATE_TOKENS} tokens.\n")

    # --- descriptive: the length difference, reported separately
    print("=== Document length (tokens) — a finding in its own right ===")
    for eco in ECOSYSTEMS:
        for src in SOURCES:
            v = df[(df.ecosystem == eco) & (df.source == src)].n_tok
            print(f"  {eco:7s} {src:7s} median={int(v.median()):5d}  "
                  f"SD={v.std():7.1f}  CV={v.std()/v.mean():.2f}  range={v.min()}-{v.max()}")

    paired = paired_analysis(df)
    paired.to_csv(OUT_DIR / "rq3_edit_distance_paired.csv", index=False)
    lc = paired[paired.length_controlled]
    print(f"\n=== Checks A/B: paired, same library (length-controlled n={len(lc)}) ===")
    print(f"{'pair':22s}{'median d':>10s}{'mean d':>9s}{'min d':>8s}")
    for c in ["d_human_sonnet", "d_human_openai", "d_sonnet_openai"]:
        v = lc[c]
        print(f"  {c[2:]:20s}{v.median():10.3f}{v.mean():9.3f}{v.min():8.3f}")

    hs, ho, so = lc.d_human_sonnet, lc.d_human_openai, lc.d_sonnet_openai
    human_llm = pd.concat([hs, ho])
    d_eff = cliffs_delta(so.to_numpy(), human_llm.to_numpy())
    _, p = stats.mannwhitneyu(so, human_llm, alternative="two-sided")
    print(f"\n  model-model vs human-model: Cliff's delta={d_eff:+.3f} "
          f"({cliff_magnitude(d_eff)}), MWU p={p:.3e}")
    print("  (negative delta = the two models are closer to each other than to the human)")

    print(f"\n  closest generated-to-human pairs (possible regurgitation):")
    for _, r in lc.nsmallest(5, "d_human_sonnet")[["library", "ecosystem", "d_human_sonnet"]].iterrows():
        print(f"    sonnet  {r.ecosystem:7s} {r.library[:44]:46s} d={r.d_human_sonnet:.3f}")
    for _, r in lc.nsmallest(5, "d_human_openai")[["library", "ecosystem", "d_human_openai"]].iterrows():
        print(f"    openai  {r.ecosystem:7s} {r.library[:44]:46s} d={r.d_human_openai:.3f}")

    hom = homogeneity_analysis(df)
    hom.to_csv(OUT_DIR / "rq3_edit_distance_homogeneity.csv", index=False)
    print(f"\n=== Check C: cross-library homogeneity (length-controlled) ===")
    print("  mean edit distance from each document to others about DIFFERENT libraries")
    print(f"\n{'eco':9s}{'source':9s}{'n':>4s}{'median':>9s}{'mean':>8s}{'SD':>8s}")
    summ = []
    for eco in ECOSYSTEMS:
        for src in SOURCES:
            v = hom[(hom.ecosystem == eco) & (hom.source == src)].mean_dist_to_others
            if v.empty:
                continue
            print(f"  {eco:7s}  {src:7s}{len(v):4d}{v.median():9.3f}{v.mean():8.3f}{v.std():8.3f}")
            summ.append({"ecosystem": eco, "source": src, "n": len(v),
                         "median": round(v.median(), 4), "mean": round(v.mean(), 4),
                         "sd": round(v.std(), 4)})
    pd.DataFrame(summ).to_csv(OUT_DIR / "rq3_edit_distance_summary.csv", index=False)

    print("\n  human vs each model, per ecosystem, on BOTH measures:")
    print("  (positive delta = human documents are further apart = more varied)")
    for col, label in [("mean_dist_to_others", "edit"), ("mean_jaccard_to_others", "jaccard")]:
        print(f"\n    -- {label} --")
        for eco in ECOSYSTEMS:
            h = hom[(hom.ecosystem == eco) & (hom.source == "human")][col].to_numpy()
            for m in MODELS:
                l = hom[(hom.ecosystem == eco) & (hom.source == m)][col].to_numpy()
                d_e = cliffs_delta(h, l)
                _, pv = stats.mannwhitneyu(h, l, alternative="two-sided")
                sig = "SIG" if pv < 0.05 and abs(d_e) >= 0.33 else "ns "
                print(f"    {eco:7s} human vs {m:7s}: {h.mean():.3f} vs {l.mean():.3f}  "
                      f"delta={d_e:+.3f} ({cliff_magnitude(d_e):10s}) p={pv:.2e}  {sig}")

    print(f"\nWrote 3 CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
