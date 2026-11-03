# Development log

Running record of analysis and engineering events that are not captured by
the original plan and formal results
or by the per-analysis result files. Newest first.

Pointers to where detail lives:
- RQ3 results and the corpus-normalisation defect: `files/analysis/rq3_results_20260813.md`
- Construct-validity verdicts: `files/analysis/construct_validity_check.md`
- RQ4 results: `files/analysis/rq4_results.md`

## 2026-09-16: RQ4 built and run

`src/rq4/rq4_classification.py`. Corpus: `frame_locked_corrected`
(n=400, 200/200). Features: the 15 locked dimensions. Stratified 5-fold CV
repeated 10x, seeds from from `RNG_SEED=402`.

**Ecosystem classification (primary)**

| Model | macro-F1 | permutation null | p |
|---|---|---|---|
| Logistic regression | 0.616 | 0.499 | 0.0099 |
| Linear SVM | 0.610 | 0.498 | 0.0099 |
| Random forest | 0.672 | 0.500 | 0.0099 |

Pre-specified criterion (macro-F1 >= 0.75) **not met**: reported as written
and as failed, with the note that it was calibrated under the 3-ecosystem
design that was never run (chance ~0.33 there, ~0.50 here).

Not a flat null: a real but small multivariate signal, reliably above chance by
~12 macro-F1 points. It is coherent with RQ1 rather than contradicting it. The
top coefficients are RQ1's largest-|delta| dimensions; every sign-stable
coefficient agrees in direction with its Cliff's delta; none exceeds 0.40 on
z-scored features. Random forest at 0.672 shows the ceiling is not an artefact
of assuming linear separability. Reading: no single dimension separates the
ecosystems, and combining all fifteen still reaches only ~62%.

**Domain confound test**: domain macro-F1 0.126 (9 classes) vs
ecosystem 0.616, so the clause does not trigger; domain is not the stronger
predictor. Holds on lift-over-own-null too (+0.116 vs +0.033 logistic).

**Two CIs, both in the results CSV.** Across-fold CI [0.515, 0.711] (fold
spread) vs bootstrap-of-the-mean CI [0.600, 0.631] (precision of the estimate).
They answer different questions. Quote the second; know the first exists,
because it only just clears the null.

**Stated deviation.** The original plan specifies z-scoring across the corpus, which leaks
fold statistics into training. Used `Pipeline(StandardScaler, estimator)` refit
per fold instead, strictly more conservative, can only lower the score.
Documented in the script rather than changed silently.

**Environment change.** `scikit-learn 1.6.1` (+ joblib, threadpoolctl)
installed into the venv; it was absent. No requirements file exists to update.
numpy 2.0.2 emits spurious matmul overflow warnings from lbfgs; four solvers
were checked and all agree to 4 d.p., so these are BLAS FP-flag artefacts and
are filtered with that justification recorded in the docstring.

## 2026-08-19: RQ3 corpus-normalisation defect found and corrected

Human READMEs had code stripped during extraction; LLM output did not. 36-56%
of each LLM document was source code against 0.8-2.4% human. The entire Affect
headline was `import java.util.*` lines scored as sadness (r=0.854 between the
count of "java" and the emo_sad word count). Re-ran LIWC on code-stripped text;
`emo_sad` for Java fell 4.148% -> 0.024%, `WPS` reversed direction, `BigWords`
survived unchanged. Full account: `files/analysis/rq3_results_20260813.md`.

**Lesson worth carrying:** nothing in the statistics flagged it. The artefact
was large, Holm-corrected, and replicated across two independent models.
Cross-model replication increased false confidence, because both models share
the habit that caused it.
