# rq4

**RQ4: can style alone reveal where a document came from?** There are two tasks: its language, and
whether AI wrote it.

| File | What it does | Reads | Writes |
|---|---|---|---|
| `rq4_classification.py` | Language task: three classifiers on the 15 category scores, compared with shuffled labels. Takes a few minutes; `--permutations` sets the shuffle count | `frame_locked_corrected` LIWC-22 output | `rq4_classification_results.csv`, `rq4_logistic_coefficients.csv` in that frame; `files/analysis/figures/rq4_01_ecosystem_classification.png` |
| `rq4_detector.py` | Authorship task: a threshold on one feature. See the modes below | `files/corpus/rq3/` text and LIWC-22 output | `files/analysis/rq4_detector_results.csv` |
| `rq4_detector_plot.py` | Detector figure, using the `--validate` results | Corpus text, validation results | `files/analysis/figures/rq4_02_detector_bigwords.png` |
| `rq4_pr_curve.py` | Precision-recall and ROC curves for the detector | Corpus text | `files/analysis/rq4_pr_curve_points.csv`, `files/analysis/figures/rq4_clean_03_pr_roc.png`, `report/figures/rq4_pr_roc.png` |
| `rq3_rq4_clean_update.py` | Numbers and figures from the rebuilt corpus that don't need LIWC-22: similarity, containment, detector | Corpus text, RQ3 similarity results | `files/analysis/rq3_rq4_clean_update.md`, `files/analysis/figures/rq3_clean_01_*`, `rq4_clean_01_*`, `rq4_clean_02_*` |

## Detector modes

```bash
venv/bin/python3 src/rq4/rq4_detector.py                  # evaluate
venv/bin/python3 src/rq4/rq4_detector.py --validate       # checks on data outside the training corpus
venv/bin/python3 src/rq4/rq4_detector.py --score FILE ... # score your own documents; writes nothing
```

The README-scope rows from `--validate` no longer test anything, because of the corpus rebuild.
See [`RULES.md`](../../RULES.md).
