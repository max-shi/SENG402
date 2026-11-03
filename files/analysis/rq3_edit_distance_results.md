# RQ3: edit-distance analysis (LIWC-independent corroboration)

Run 2026-09-16. Script: `src/rq3/rq3_edit_distance.py`.

## Why

Every RQ3 result so far rests on a single instrument, LIWC-22, and this project
has twice shown that LIWC can produce large, significant, cross-model-replicated
effects that mean nothing. This analysis re-measures the same corpus with an
instrument that has no dictionary, no psycholinguistic theory and no register
assumptions: how many word-level edits separate two documents.

Two measures are reported because they fail differently. **Edit distance** is a
sequence measure (same words in a different order score as maximally distant).
**Jaccard** ignores order and compares vocabulary sets. Where they disagree, the
disagreement is reported rather than resolved by preferring the convenient one.

## The length confound, and why it had to be controlled

Normalised edit distance is `distance / max(len_a, len_b)`, so documents of very
different lengths score as distant almost by construction. In this corpus:

| | median tokens | SD | CV | range |
|---|---|---|---|---|
| java human | 299 | 729 | **1.23** | 14–3,188 |
| java sonnet | 631 | 177 | 0.28 | 299–1,192 |
| java openai | 521 | 238 | 0.44 | 118–1,277 |
| python human | 429 | 1,857 | **2.12** | 10–12,789 |
| python sonnet | 665 | 150 | 0.22 | 245–1,016 |
| python openai | 572 | 225 | 0.37 | 143–1,266 |

Human length variance is 3–10× the models'. Comparing raw documents would have
"found" that human documents are more spread out purely as an artefact of their
length distribution, which is precisely the claim under test. **All primary
results truncate every document to its first 150 tokens** and drop documents
shorter than that, removing the confound.

The length difference is itself a real finding (**LLM output length is far more
uniform than human output length**) and is reported above as a descriptive
statistic, it is simply not allowed to masquerade as a similarity result.

## Check A: No evidence of regurgitation

Minimum distance between any generated document and the real README for the same
library is **0.840** (`pympler`, Sonnet). Nothing approaches a copy.

This corroborates the n-gram containment check in `rq3_overlap_check.py` using a
measure sensitive to structure rather than to shared phrases. Two independent
contamination checks now agree.

## Check B: The two models resemble each other more than either resembles the human

Length-controlled, n=79 libraries with all three sources ≥150 tokens.

| pair | median d | mean d |
|---|---|---|
| human ↔ sonnet | 0.973 | 0.967 |
| human ↔ openai | 0.980 | 0.977 |
| **sonnet ↔ openai** | **0.947** | **0.946** |

Paired Wilcoxon signed-rank on the per-library difference: mean difference
**−0.0262**, **p = 3.4×10⁻¹⁰**; the models are closer to each other in **64 of 79**
libraries (81%).

*Correction (2026-09-16).* This was first reported as Cliff's δ = −0.674,
Mann–Whitney p = 2.1×10⁻¹⁷. That test was wrong in two ways: it treated paired
per-library data as independent samples, and it pooled `human↔sonnet` with
`human↔openai`, which share libraries and are therefore pseudo-replicated. The
paired figures above supersede it. The direction and significance hold; the
effect size does not transfer between the two framings.

Two independently developed models, from different vendors, writing from the same
API surface, produce documents measurably closer to each other than either is to
the documentation the library's own maintainer wrote, established **without
LIWC**.

The absolute gap is small (0.026 on a scale saturating near 1.0) and the pattern
holds in 81% of libraries rather than all of them. More importantly, both models
received an identical prompt while the human wrote a structurally different
artefact, so "the models share a register" and "identical instructions produce
identical structure, and the human was doing a different task" both predict this
result. This design cannot separate them; see limitation 5.

## Check C: Human documentation is more varied, on both measures

Mean distance from each document to every other document about a *different*
library, within the same ecosystem and author type. Positive δ = human documents
further apart = more varied.

| measure | ecosystem | model | human | LLM | Cliff's δ | p | verdict |
|---|---|---|---|---|---|---|---|
| edit | java | sonnet | 0.988 | 0.984 | +0.553 large | 8.3×10⁻⁶ | **sig** |
| edit | java | openai | 0.988 | 0.976 | +0.940 large | 4.7×10⁻¹⁴ | **sig** |
| edit | python | sonnet | 0.987 | 0.977 | +0.803 large | 5.3×10⁻¹¹ | **sig** |
| edit | python | openai | 0.987 | 0.973 | +0.927 large | 4.6×10⁻¹⁴ | **sig** |
| jaccard | java | sonnet | 0.902 | 0.886 | +0.606 large | 1.0×10⁻⁶ | **sig** |
| jaccard | java | openai | 0.902 | 0.878 | +0.792 large | 2.1×10⁻¹⁰ | **sig** |
| jaccard | python | sonnet | 0.903 | 0.897 | +0.175 small | 0.15 | ns |
| jaccard | python | openai | 0.903 | 0.882 | +0.711 large | 7.4×10⁻⁹ | **sig** |

**7 of 8 cells significant; all 8 point the same direction.** The one failure
(python/sonnet under Jaccard) is the same cell that was weakest under edit
distance, so the two measures agree about where the effect is strongest and
where it is marginal.

This independently corroborates RQ3 test 4 (Brown–Forsythe on LIWC dimensions,
6 of 7 significant cells showing humans more spread) using an instrument that
shares nothing with LIWC.

## Relationship to the earlier n-gram containment check

The contamination check in `rq3_overlap_check.py` used **8-word n-gram
containment**: it extracts every overlapping 8-word sequence from the generated
document and reports what fraction of them also occur in the real README, with a
flag threshold of 0.5. It is deliberately *directional*, it asks "how much of
what was generated could have been lifted from the reference", not "how similar
are these two texts".

For its actual purpose, catching near-verbatim reproduction, that design is
sound, and this analysis confirms its verdict: nothing was copied. But it is a
weak instrument for the broader question of *similarity*, for four reasons:

1. **All-or-nothing at phrase level.** An exact 8-word match is a high bar. A
   document that paraphrases the README closely, substitutes synonyms, or
   reorders clauses scores near zero, indistinguishable from a document with no
   relationship to the reference at all. The measure cannot separate "unrelated"
   from "closely paraphrased".
2. **Threshold-based rather than graded.** It answers "above 0.5?" It does not
   rank documents by how similar they are, so it cannot be used to compare
   groups, only to flag individuals.
3. **Asymmetric by design.** Useful for the lifting question, but it means the
   quantity is not a distance and cannot be used for the homogeneity comparisons
   in Checks B and C.
4. **It never fired on the failure mode it was built for.** The script's own
   comments record that no generated document came close to the threshold. What
   it did flag was internal-path leakage, a separate check, and even that
   needed manual adjudication (20/200 raw, falling to 3/200 once matches
   resolving to sibling modules inside shared monorepos were excluded).

Edit distance is the better instrument for this question because it is
**continuous, symmetric, and whole-document**. It degrades gracefully: a close
paraphrase scores lower than an unrelated document, where n-gram containment
scores both at approximately zero. That gradation is what makes Checks B and C
possible at all, neither comparison can be expressed in terms of containment.

The two tests should therefore be read as complementary rather than as one
superseding the other. Containment answers "was anything lifted verbatim?"
(no). Edit distance answers "how far apart are these documents, and does that
distance differ systematically between authors?" (yes). They agree on the only
question both can address, there is no evidence of regurgitation, which is
worth more than either verdict alone, since they would fail in different ways.

## Robustness: does the 150-token cutoff drive the results?

No. Sweeping the truncation length from 100 to 300 tokens leaves both findings
intact, with the effect shrinking smoothly as more text is included but never
reversing or losing significance.

| K | libraries | d(model,model) | d(human,model) | diff | paired p | human more spread |
|---|---|---|---|---|---|---|
| 100 | 86 | 0.9321 | 0.9660 | −0.0340 | 6.8×10⁻¹¹ | 4/4 |
| 150 | 79 | 0.9457 | 0.9719 | −0.0262 | 2.9×10⁻¹⁰ | 4/4 |
| 200 | 68 | 0.9506 | 0.9748 | −0.0242 | 4.1×10⁻⁹ | 4/4 |
| 250 | 60 | 0.9531 | 0.9751 | −0.0219 | 6.8×10⁻⁸ | 4/4 |
| 300 | 52 | 0.9551 | 0.9760 | −0.0209 | 2.2×10⁻⁸ | 4/4 |

This addresses the choice of cutoff *value* only. Two related concerns are not
resolved by it: every K still samples document **openings** (limitation 6), and
every K still drops the shortest documents, which are disproportionately human,
86 libraries survive at K=100 but only 52 at K=300 (limitation 2). Testing those
would require random-window sampling and a length-invariant measure such as
TF-IDF cosine over untruncated text.

## Limitations

1. **Edit distance saturates.** Every pair scores 0.97–0.99, so the measure
   orders documents reliably but its absolute values carry little information,
   differences are ~0.01 on a [0,1] scale. Cliff's δ is rank-based and therefore
   still valid, but the *practical* magnitude should not be overstated. Jaccard
   sits lower (0.87–0.90) and is the better-scaled of the two.
2. **Truncation drops the shortest documents**, and those are disproportionately
   human: 39/50 java and 41/50 python human documents survive the 150-token
   floor, versus 49–50/50 for every model group. The dropped documents are the
   terse ones, which are plausibly among the most distinctive. The effect is
   more likely understated than overstated by this, but it is a selection effect
   and is not corrected.
3. **Pairwise distances are not independent**: each document appears in n−1
   pairs. Each document is therefore reduced to its mean distance to all others
   before testing, giving one value per document. This mitigates but does not
   fully eliminate pseudo-replication.
4. Tokens are lowercased alphabetic words; punctuation, numbers and code
   identifiers containing digits are discarded.
5. **Convergence may be prompt-induced rather than intrinsic.** Both models
   received the same fixed prompt template, which asks for an introduction, an
   overview of the main classes, and usage examples. Some of the similarity
   measured in Checks B and C is therefore plausibly structural similarity imposed by
   the instruction, not a property of how these models write. The human authors
   had no such constraint. The defensible claim is that *LLM documentation
   generated under a fixed prompt* converges on a narrow register, not that
   LLMs converge inherently. Since real-world generated documentation is also
   prompt-driven, the narrower claim remains the practically relevant one, but
   it is the narrower claim. This is the same underlying issue as the task
   asymmetry recorded in `rq3_results_20260813.md` section 7, surfacing in a
   second, independent measure.
6. **Truncation samples document openings, not representative passages.** The
   first 150 tokens of a README is title, badges and a one-line description; the
   first 150 tokens of a generated document is its introduction. These are
   different sections of different document types, so the comparison is strictly
   of openings rather than of whole documents. Random-window sampling would
   remove this position bias, and a length-invariant measure (e.g. TF-IDF
   cosine) would avoid truncation altogether while retaining all 300 documents.

## Bottom line

The claim "LLM documentation converges on a narrower register than human
documentation" no longer rests on LIWC alone. It is reproduced by a measure with
no dictionary and no theory, on the same corpus, in 7 of 8 cells, plus the
stronger and cleaner Check B result that two independent models resemble each other
more than either resembles the human author.

## Outputs

| File | Contents |
|---|---|
| `files/corpus/rq3/rq3_edit_distance_paired.csv` | per library: all three pairwise distances, truncated and full |
| `files/corpus/rq3/rq3_edit_distance_homogeneity.csv` | per document: mean edit and Jaccard distance to others |
| `files/corpus/rq3/rq3_edit_distance_summary.csv` | group-level summary |
