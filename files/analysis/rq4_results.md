# RQ4: results (ecosystem fingerprinting from LIWC profiles, 2026-09-16)

**Question.** Can the ecosystem origin of a documentation artefact be
predicted from its 15-dimensional LIWC profile alone?

**Answer in one line.** Yes, weakly. A logistic regression on the 15 locked
dimensions reaches macro-F1 = **0.616** (95% CI on the mean 0.600–0.631)
against an empirical chance level of 0.499, reliably above chance
(permutation *p* = 0.0099, the floor achievable with 100 relabelings) but far
below the pre-specified success threshold of 0.75. RQ4's primary success
criterion is **NOT met**.

**Corpus.** `files/corpus/frame_locked_corrected/`, 400 libraries, 200
java / 200 python, all 15 locked dimensions present, no missing values.
Verified before analysis.

**Artefacts.**

| What | Where |
|---|---|
| Analysis | `src/rq4/rq4_classification.py` |
| Per-model, per-task results | `files/corpus/frame_locked_corrected/rq4_classification_results.csv` |
| Logistic coefficients | `files/corpus/frame_locked_corrected/rq4_logistic_coefficients.csv` |
| Figure | `files/analysis/figures/rq4_01_ecosystem_classification.png` |

---

## 1. What RQ4 adds to RQ1

RQ1 tests each dimension on its own and returned **0/15 passing** the
pre-specified rule (Holm *p* < 0.05 **and** |δ| ≥ 0.33), at n=200 and again
at n=1000. That is a *univariate* null. It does not by itself rule out that
the classes are separable by a *combination* of dimensions, which is what a
classifier can exploit. RQ4 is that test.

The result here is the interesting middle case. The multivariate signal is
**real but small**: eight dimensions in this frame carry Holm-significant
small effects (|δ| = 0.17–0.30, all below RQ1's 0.33 bar), and pooling them
buys about 12 macro-F1 points over chance. It does not buy document-level
classification. RQ1's null therefore survives RQ4 in the form that matters
for the claim: the per-dimension effects are too small to classify an
individual library's documentation, even in combination.

---

## 2. Method as run

Per the original plan, with two deviations stated below.

- **Features.** The 15 locked dimensions (`LOCKED_DIMENSIONS` imported from
  `confirmatory_liwc_stats.py`), z-scored.
- **Models.** Logistic regression (primary), linear SVM and random forest
  (robustness). Library defaults throughout, **no hyperparameter tuning was
  performed**, deliberately, so the reported number is not the maximum of a
  search.
- **Evaluation.** Stratified 5-fold CV repeated 10× (50 fold scores), seeds
  derived from `RNG_SEED = 402`. Macro-F1.
- **Baselines.** Majority-class, stratified-random, and a 100-relabeling
  permutation null.
- **Held-out split.** A stratified 20% split is reported but is not
  the headline; at n=400 it is 80 documents and far noisier than the 50-fold
  CV estimate.

**Deviation 1, scaling happens inside the CV fold.** The original plan says z-score
across the corpus; doing that before cross-validation leaks test-fold means
and SDs into training. Every model is a `Pipeline(StandardScaler, estimator)`
refit per fold. This is *stricter* than pre-specified and can only lower the
reported score, so it cannot be mistaken for tuning upward.

**Deviation 2, the domain task runs on 345 of 400 rows.** See the original plan.

---

## 3. Ecosystem classification (primary)

| Model | macro-F1 | 95% CI (mean, bootstrap) | 95% CI (across folds) | Held-out 20% |
|---|---|---|---|---|
| **Logistic regression (primary)** | **0.6155** | 0.6004 – 0.6305 | 0.515 – 0.711 | 0.612 |
| Linear SVM | 0.6098 | 0.5934 – 0.6257 | 0.510 – 0.709 | 0.600 |
| Random forest | 0.6722 | 0.6597 – 0.6850 | 0.580 – 0.759 | 0.674 |

Two intervals are given because they answer different questions. The
*across-fold* interval is the spread of individual 80-document fold scores;
the *bootstrap-on-the-mean* interval is uncertainty in the estimate and is the
one to compare against a baseline. Do not quote the wide one as uncertainty in
the mean.

All three models agree within ~6 points, and the random forest, the only
model here that can fit a non-linear boundary, is the best of them at 0.672.
That matters for the interpretation: the ceiling is not an artefact of
assuming linear separability. A flexible model given the same 15 features also
lands nowhere near 0.75.

### Baselines

| Baseline | macro-F1 | Note |
|---|---|---|
| Majority-class (constant predictor) | 0.3333 | its *accuracy* is 0.5000 |
| Stratified-random predictor | 0.5497 | the ~0.50 binary chance level, commensurable with macro-F1 |
| Permutation null (mean of 100 relabelings, logistic) | 0.4991 | SD 0.0319, 95th pct 0.5420 |

Three baselines rather than one, because "the binary baseline is 0.50" is
ambiguous for macro-F1. A constant majority-class predictor scores macro-F1
**0.333** on a balanced binary problem (F1 = 0.667 on the predicted class, 0.0
on the other) while its *accuracy* is 0.50. Quoting 0.333 alone flatters the
classifier; quoting 0.50 alone without saying which quantity it is compares an
accuracy against an F1. The permutation null (0.499) is the empirical
chance level for this exact pipeline, and it is the reference used below.

### Verdict against the success criterion

| Reference | Value | Observed 0.6155 | Verdict |
|---|---|---|---|
| Pre-specified threshold | 0.75 | below by 0.13 | **NOT MET** |
| Majority-class macro-F1 | 0.333 | CI excludes it | above |
| Stratified-random / binary chance | 0.550 | CI excludes it | above |
| Permutation null | 0.499 | *p* = 0.0099 | above chance |

**On the 0.75 threshold.** It is reported as written and as failed. It must be
read with its provenance: the original plan was drafted under a **three-ecosystem**
design (java / python / javascript), where chance macro-F1 is ~0.33 and 0.75
represents a large margin over chance. JavaScript was dropped in the original plan, so
the realised design is binary with chance ~0.50 and the same 0.75 represents a
much smaller margin. The threshold was not restated post hoc. The pre-specified criterion fails,
and it was calibrated for a design that was not run. The interpretively meaningful statement is the second
row set: the classifier is reliably above chance, by about 12 macro-F1 points,
and cannot classify individual documents.

### Confusion matrix (logistic, out-of-fold, 5-fold at seed 402)

| | pred java | pred python |
|---|---|---|
| **true java** | 123 | 77 |
| **true python** | 75 | 125 |

Symmetric: 61.5% of java and 62.5% of python documents land on the right side.
There is no asymmetry to interpret, the model is not "good at java, bad at
python"; it is uniformly mediocre. Roughly two documents in five are
misclassified in each direction.

---

## 4. Which dimensions carry the signal

Logistic coefficients on z-scored features, full-corpus refit. Negative pushes
towards **java**, positive towards **python**. `fold_sd` is the SD of that
coefficient across the 5 CV folds; `sign stable` means the sign never flipped
across folds.

| Dimension | Coefficient | Direction | fold SD | Sign stable | RQ1 δ (same frame) |
|---|---|---|---|---|---|
| emo_anger | **+0.392** | python | 0.214 | yes | −0.303 (python higher) |
| achieve | **−0.273** | java | 0.113 | yes | +0.167 (java higher) |
| emo_sad | −0.227 | java | 0.151 | yes | +0.126 |
| BigWords | −0.209 | java | 0.060 | yes | +0.174 (java higher) |
| WPS | −0.190 | java | 0.157 | yes | +0.183 (java higher) |
| ipron | +0.187 | python | 0.085 | yes | −0.191 (python higher) |
| tentat | +0.146 | python | 0.054 | yes | −0.169 (python higher) |
| certitude | −0.135 | java | 0.056 | yes | +0.044 |
| risk | +0.119 | python | 0.068 | yes | −0.013 |
| conflict | +0.114 | python | 0.200 | **no** | −0.251 (python higher) |
| emo_neg | −0.061 | java | 0.257 | **no** | −0.065 |
| motion | −0.038 | java | 0.070 | **no** | −0.029 |
| curiosity | −0.034 | java | 0.063 | **no** | +0.034 |
| emotion | +0.016 | python | 0.134 | **no** | −0.059 |
| Tone | +0.005 | python | 0.110 | **no** | +0.009 |

Two things to note.

1. **The classifier and RQ1 agree, which is a coherence check, not a new
   finding.** Every sign-stable coefficient points the same way as that
   dimension's Cliff's delta, and the coefficient ranking broadly tracks the
   |δ| ranking: six of RQ1's seven largest-|δ| dimensions (emo_anger, ipron,
   WPS, BigWords, tentat, achieve) are among the eight largest coefficients,
   the one exception being `conflict`, see the flag below. The classifier
   has not found a hidden axis; it is pooling
   the same small effects RQ1 already measured and found individually
   insufficient.
2. **No coefficient is large.** The biggest is 0.39 on a z-scored feature: a
   one-SD change in `emo_anger` moves the log-odds by 0.39, i.e. the odds by a
   factor of 1.5. Spread over 15 such weak terms, this is exactly the profile
   of a weak-but-real multivariate signal, and it is why the score sits near
   0.62 rather than near either 0.50 or 0.75.

`conflict` deserves a flag: it has the second-largest RQ1 effect (δ = −0.251)
but an unstable coefficient (sign flips across folds, fold SD 0.200 against a
point estimate of 0.114). This is collinearity with `emo_anger`, not absence
of effect, the two dimensions overlap heavily in LIWC's dictionary, so the
model can put the weight on either. Do not read the small `conflict`
coefficient as "conflict does not matter".

Caveat inherited from RQ3's construct-validity work
(`files/analysis/construct_validity_check.md`): `emotion`, `emo_neg` and
`emo_sad` were found to be unreliable on *LLM-generated* documents, where they
collapsed into an artefact of code tokens. That finding concerned the RQ3
corpus, not this one, this corpus is human documentation, code-stripped by
the same preprocessor, but given `emo_anger` is the single largest
coefficient here, what `emo_anger` is picking up in this corpus matters for
interpretation. That check has
not been run for RQ4.

---

## 5. Domain vs ecosystem (confound test)

| Model | ecosystem macro-F1 (2 classes) | domain macro-F1 (9 classes) |
|---|---|---|
| Logistic regression | 0.6155 | 0.1260 |
| Linear SVM | 0.6098 | 0.1272 |
| Random forest | 0.6722 | 0.1547 |

**Domain does not beat ecosystem.** On the raw comparison the original plan specifies,
domain classification is far worse (0.126 vs 0.616 for the primary model), so
the clause "if domain classification achieves higher macro-F1 … RQ1's claims
weaken further" does **not** trigger.

The raw comparison is however not apples-to-apples, macro-F1's scale depends
on the number of classes, and the two tasks have 2 and 9. The comparable
quantity is lift over each task's own permutation null:

| Model | ecosystem lift | domain lift |
|---|---|---|
| Logistic regression | +0.116 (0.616 vs 0.499) | +0.033 (0.126 vs 0.093) |
| Linear SVM | +0.112 | +0.039 |
| Random forest | +0.172 | +0.068 |

Ecosystem is the stronger predictor on both readings, by roughly 2.5–3.5×
lift. The domain signal is weak and, for the primary model, not clearly
distinguishable from its own null (*p* = 0.0594; the SVM and RF reach
*p* = 0.0099). So the LIWC profile carries somewhat more ecosystem
information than domain information, which is the direction favourable to
RQ1, though at an absolute level too low for either to be usable.

**This conclusion is provisional.** See the original plan.

---

## 6. Problem found: incomplete domain labels in this frame

**55 of the 400 rows in `frame_locked_corrected` carry no `domain` tag**
(13.8%), and the gap is ecosystem-skewed: **44 java, 11 python**.

- The pre-dedup `frame_locked` has all 400 rows tagged.
- The gap traces to the dedup correction itself. Per that frame's
  `frame_metadata.json` (`_dedup_check_note`), rows whose `repository_url` was
  shared by more than one of the original 400 were re-cloned and re-processed
  with monorepo subpackage scoping on 2026-08-05. Domain tags were evidently
  not re-derived for those rows,
  `sample_manifest_final_corrected.csv` has the same 55 nulls in `domain_tag`.
- Every domain count is lower than in the pre-dedup frame (e.g. networking
  39 → 25), consistent with tags being lost rather than libraries removed.

Handling: the domain task runs on the **345 tagged rows only**. Nothing was
pooled or dropped on top of that, all 9 tagged domains have n ≥ 17, so the
pre-specified n < 10 pooling rule never triggers; the script asserts
this at runtime rather than assuming it. The script prints a DATA GAP block
and records the coverage and its skew in the `note` column of every output
row.

**Impact.**

- **Ecosystem task (RQ4 primary): unaffected.** It uses all 400 rows; the
  ecosystem label is complete.
- **Domain confound test: provisional.** 13.8% of rows are excluded and the
  exclusion is 80% java. If the untagged java libraries differ systematically
  from the tagged ones, the domain model is being evaluated on a non-random
  subsample.

**The domain comparison covers 345 of 400 libraries.** The same gap
affects any RQ2 result computed on this frame: `pandas.groupby` drops null
keys silently, so an RQ2 re-run here would exclude the same 55 rows without
saying so.

---

## 7. Summary

> A logistic regression on the 15 locked LIWC dimensions classifies a library
> by ecosystem with macro-F1 = 0.616 (95% CI 0.600–0.631, stratified 5-fold CV
> repeated 10×), against a majority-class baseline of 0.333 (accuracy 0.50), a
> stratified-random baseline of 0.550, and a permutation null of 0.499
> (empirical *p* = 0.0099, 100 relabelings). The pre-specified success
> threshold of macro-F1 ≥ 0.75 is not met; that threshold was calibrated under
> a three-ecosystem design, and the realised design is binary. Linear SVM
> (0.610) and random forest (0.672) agree, so the ceiling is not an artefact
> of assuming linear separability. The confusion matrix is symmetric, 123/200
> java and 125/200 python correctly classified, so roughly two documents in
> five are misclassified in each direction. The dominant features are
> `emo_anger` (→ python), `achieve`, `emo_sad`, `BigWords` and `WPS` (→ java),
> each with a coefficient below 0.40 on z-scored features and each pointing in
> the direction of its RQ1 Cliff's delta. A domain-classification model on the
> same features reaches macro-F1 = 0.126 over 9 classes (lift +0.033 over its
> own null, against +0.116 for ecosystem), so domain is *not* the stronger
> predictor and the original plan confound clause does not trigger, provisionally,
> as 55/400 rows lack domain tags in this frame.
>
> RQ4 therefore confirms RQ1 multivariately: the per-dimension effects are
> real but small (eight dimensions at |δ| = 0.17–0.30, none reaching the 0.33
> bar), and combining all fifteen still leaves individual documents
> unclassifiable at any practically useful rate.

---

# Appendix: related literature (added 2026-09-16)

Added after the analysis, from a targeted search on how these findings sit
against published work. Not part of the pre-specified plan; recorded here so
the connections are not lost.

## 1. The dispersion finding replicates a Nature Human Behaviour result

**Sourati et al. (2026), "The shrinking landscape of linguistic diversity in the
age of large language models", Nature Human Behaviour.**
DOI 10.1038/s41562-026-02550-0 · preprint arXiv:2502.11266

Three studies, seven datasets, **over 880,000 texts**. Finding: LLMs
"homogenize writing styles, reducing writing-complexity variance by a
statistically significant **21--50%** across datasets and models (p <= .05)",
amplifying dominant patterns while suppressing others, "conformity over
individuality".

**Our RQ3 test 4:** on hedging (`tentat`) the LLM standard deviation is ~55% of
the human corpus's, i.e. roughly a **45% variance reduction**: inside their
range. Six of seven significant dispersion cells show the human corpus more
spread.

Why this matters: their corpora are social media, news and scientific writing.
Ours is library documentation, a different genre, a different instrument
(LIWC-22 on 15 pre-specified dimensions), a paired within-library design, and
an independent sample. So this is a **replication in a technical register**,
which is a stronger claim than a standalone finding. Cited in the report
Discussion as `\cite{sourati2026}`.

## 2. Direction of the formality finding is the established pattern

Multiple studies report LLM text as more formal and more structured, and human
text as more variable in length with greater vocabulary variety and "more
scattered sentence length distributions".

- **`BigWords` (LLM higher, large effect, 4/4 families)** matches the
  formality direction.
- **`WPS` (human higher, 3/4)** matches the sentence-length-variability
  observation, and note this only emerged *after* the code-stripping
  correction; the raw corpus had it backwards.

Sources seen: *Human or GenAI? Characterizing the Linguistic Differences...*
(ACM Web Science 2025, doi 10.1145/3720554.3735864); *A linguistic comparison
between human- and AI-generated content* (iScience, S2589-0042(26)00351-2);
*Contrasting Linguistic Patterns in Human and LLM-Generated News Text* (PMC11422446).

## 3. The gap survives, and is now sharper

The software-engineering literature on LLM documentation evaluates **quality**,
readability, accuracy, comprehensibility, and generally reports LLM docs as
*better* on those axes (e.g. *Can Developers Prompt?*, arXiv:2408.00686;
*Generative AI for Technical Writing*, NoDaLiDa 2025). It asks *is it better?*

The linguistics literature measures **homogenisation** on general prose. It asks
*how is it written?*

Neither joins the two on software documentation under a paired design with a
pre-specified instrument. That intersection remains this project's contribution.

**A sharper framing for the Discussion:** if documentation style narrows the way
general writing has, while the SE literature simultaneously reports
LLM-generated documentation as more readable, the trade-off becomes explicit,
measurably more readable, measurably less diverse.

## 4. Not yet checked

- Whether anyone has classified software artefacts by **ecosystem** from text
  features (the RQ4 question). No direct precedent found in this search; not
  searched exhaustively.
- Whether the 21--50% variance figure is computed on a metric comparable to a
  standard-deviation ratio on LIWC dimensions. The directions agree and the
  magnitudes are close, but the underlying measures differ, so the comparison
  is consistent in direction and magnitude, not a like-for-like replication.

---

# Appendix B: interpretation corrections (2026-09-17)

Two corrections and one calibration point, from a follow-up literature check.

## B1. CORRECTION: "strengthens RQ1" was an overclaim

An earlier framing in this project described RQ4 as *closing a hole in RQ1* and
*strengthening* the univariate null. **That framing was wrong.**

A multivariate classifier can detect structure that no univariate test shows,
because it exploits joint dependencies across features, this is precisely why
Ojala and Garriga~[ojala2010] define a *second* permutation test (permuting
features within class) to detect exactly that. A weak multivariate result is
therefore **not logically entailed by** univariate nulls, and does not confirm
them. The reverse also holds: a strong multivariate classifier built on
individually weak features is a well-documented phenomenon.

**Correct framing, convergent, not confirmatory.** The two analyses bound the
effect from two directions:

- the univariate tests bound **per-dimension** effects below |delta| = 0.33
- the classifier bounds the **aggregate** signal below practical usefulness

Suggested wording:

> Rather than treating the classifier and the univariate tests as mutually
> confirming, we interpret them as converging evidence: the univariate analysis
> bounds per-dimension effects below |delta| = 0.33, while the multivariate
> classifier bounds the aggregate signal below practical usefulness. A
> multivariate model can in principle exploit joint feature dependencies that
> univariate tests cannot detect (Ojala and Garriga, 2010), so the two results
> are consistent rather than mutually confirmatory.

## B2. Calibration: is 0.616 "weak but real" or "essentially nothing"?

The stylometry literature gives a defensible yardstick, and it supports
**weak but real**. Binary discrimination with genuinely stylistic (function-word)
features typically reaches **77-95%** accuracy, and specialised methods
higher still. Against that scale 0.616 is far below the threshold stylometry
treats as reliable discrimination. That literature has established vocabulary
for exactly this regime, "markedly better than random but not sufficient for
definitive statements"; "significantly above baseline" yet at "a level where
practical usability is no longer realistic"~[luyckx2011].

**Important framing point.** Published stylometry accuracies are **not a
benchmark for this number**. They solve an easier and differently-featured
problem: identifying *authors*, using content-bearing or code-structural
features. This study deliberately uses content-reduced LIWC dimensions to
predict *ecosystem*. State that explicitly rather than inviting the comparison.

Separately, LIWC-as-features is known to be a low-ceiling signal outside SE
too: LIWC-only classifiers routinely land in roughly the 0.55-0.78 band and are
consistently beaten by lexical or n-gram features on the same data. 0.616 sits
at the low end of that documented band, consistent with a target that is only
weakly encoded *in style* as opposed to *in content*.

## B3. Permutation count raised from 100 to 999

The first run used 100 relabelings, for which the smallest attainable p-value
under the add-one estimator is 1/101 = 0.0099, exactly what was reported. That
value is therefore at the resolution floor and says nothing about how far below
0.05 the true p lies. Re-run at 999 (Edgington's guidance, standard practice),
giving a floor of 1/1000.

## B4. Baselines

All three are reported, because "chance macro-F1" is ambiguous for this metric:

| Reference | Value | What it is |
|---|---|---|
| Majority-class (ZeroR) | 0.333 | the degenerate floor; conventional SE baseline |
| Stratified random | 0.550 | |
| **Permutation null mean** | **0.499** | the empirical chance level for this pipeline |

The permutation null is the primary reference, because it is generated by the
same pipeline, CV scheme and class balance, with only the label-feature
association destroyed. Note the majority-class macro-F1 is **0.333**, not 0.50,
its *accuracy* is 0.50. A reader assuming "chance macro-F1 = 0.5" is wrong about
which baseline they are looking at.

## B5. The pre-specified threshold does not transfer across class counts

0.75 was pre-specified under a 3-ecosystem design. It is not met for the binary
task (0.616-0.672). It doesn't carry to the 9-class domain task, because macro-F1's
chance level and ceiling shift with class count. The domain result is judged against
its own permutation null (0.126 vs 0.093: above chance, negligible in magnitude).
