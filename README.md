# Psycholinguistic Style in Software Documentation

A SENG402 research project by Max Shi.

The study uses LIWC-22 to measure the writing style of library documentation, comparing
Java with Python, and human-written with LLM-generated documentation. The results are summarised below.

| Research question | Result |
|---|---|
| **RQ1** Do Java and Python documentation differ? | No: 0 of 15 categories met the decision rule |
| **RQ2** How does variation within a language compare with variation between languages? | On average, 98.8% of variance lies within languages |
| **RQ3** How does LLM documentation differ from human documentation? | More long words (both models and languages); humans more spread in all 9 significant dispersion comparisons |
| **RQ4** Can style reveal origin? | Language: best macro-F1 0.672, below the 0.75 target. Authorship: a long-words threshold reaches macro-F1 0.810 |

## Layout

Each `src/` folder has its own README listing its files, starting at [`src/README.md`](src/README.md).

| Path | Contents |
|---|---|
| `src/common/` | Shared code: statistics and the 15 locked categories, plotting, frame config |
| `src/pilot/` | Pilot stage: cloning, preprocessing, screening 59 categories  |
| `src/corpus/` | Main corpus: sampling, cloning, text extraction, filtering |
| `src/generation/` | RQ3 corpus: README and API extraction, LLM generation, contamination checks |
| `src/rq1/` to `src/rq4/` | Analysis and figures for each research question |
| `src/md/` | LLM prompt templates and development log |
| `files/analysis/` | Results and figures |
| `files/corpus/` | One folder per sampling frame: manifests, logs, LIWC-22 output, per-frame results |
| `RULES.md` | Decision rules, filters, exclusions and changes from the plan |
| `report/` | Report figures and literature search record (the written report itself isn't in this repo) |
| `tests/` | Automated tests for the core statistics and text handling |
| `archive/` | Scripts and files no longer in use (see `archive/README.md`) |

## Setup

Developed on Python 3.9.6.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # only needed for LLM generation
```

Run everything from the repository root. To run the tests:

```bash
venv/bin/python3 -m unittest discover tests
```

## Data not in this repository

| Not in git | Why | How to get it |
|---|---|---|
| Cleaned text, `libraries*.csv`, `rq3_libraries*.csv`, RQ3 `readme_only/` and `api_surface/` | Large, and contains third-party README text | Held separately by the project owner (`seng402_corpus.zip`, about 306 MB), or rebuild with the pipeline |
| Frame dumps (`frame_*.jsonl.gz`) and raw clones (`files/raw/`, about 64 GB) | Too large | Rebuild with the pipeline. Repositories change over time, so a rebuild won't be identical |

Scripts that read this data (including `rq4_detector.py`) won't run from a fresh clone
without it. Scripts that only read result or LIWC CSVs, such as `rq1_forest_plot.py`
and `rq2_variance_decomposition.py`, should.

**LIWC-22 is licensed desktop software and can't be scripted here.** Each `libraries.csv`
is loaded into LIWC-22 by hand, and its output is saved beside the input as
`LIWC-22 Results - <input name> - LIWC Analysis.csv`. The output CSVs are tracked,
so the statistics can be rerun without a licence.

## Sampling frames

| Frame | Used for |
|---|---|
| `frame_locked_corrected` | n=200 per language, duplication-corrected: RQ1, RQ2, RQ4 language classification |
| `frame_n2000` | n=1000 per language: larger RQ1 re-estimate, detector validation on other human documents |
| `frame_locked` | Original n=200 frame, before the duplication fix |
| `frame_haskell_v2` | Haskell attempt (n=85 usable), not in the main results |
| `rq3/` | Paired human and LLM corpus for RQ3 and authorship detection |

Most draws use seed 402; the n=1000 frame uses 20260721. See `RULES.md`.

## Pipeline

### 1. Build a corpus (RQ1, RQ2, RQ4)

Scripts are in `src/corpus/`, in this order ([details](src/corpus/README.md)). Most scripts take `--freeze-date`, which selects the frame.

| Step | Script |
|---|---|
| Draw the sample | `sample_frame.py` |
| Filter name-pattern junk | `f7_prefilter.py` |
| Clone repositories | `confirmatory_cloner.py` |
| Extract prose | `confirmatory_preprocessor.py` |
| Filter and review exclusions | `f7_auto_filter.py`, `f7_review_candidates.py`, `apply_f7_manual_review.py`, `promote_f7_exclusions.py` |
| Tag domains | `domain_tag_review.py` |
| Freeze the sample | `finalize_confirmatory_sample.py` |
| Build LIWC input | `build_libraries_csv.py`, then the **manual LIWC-22 step** |

`dedup_manifest.py`, `_build_dedup_check_frame.py` and `_merge_dedup_corrected_corpus.py`
are one-off scripts recording how the corrected frames were produced.

### 2. Build the RQ3 corpus

| Step | Script (`src/generation/`) |
|---|---|
| Re-clone libraries | `rq3_reclone.py` |
| Extract README and API surface | `rq3_extract_python.py`, `rq3_extract_java.py` |
| Calibrate the prompt | `rq3_pilot_generate.py`, `rq3_prompt_sensitivity.py`, `rq3_sensitivity_v4.py` |
| Audit README scope | `rq3_readme_scope_audit.py` |
| Rebuild the Java pool and draw the subset | `rq3_extend_java_clean.py`, `rq3_select_clean_subset.py` |
| Generate documentation (**costs money**; try `--dry-run` first) | `rq3_full_generate.py --env-file .env --subset-manifest files/corpus/rq3/generation_subset_clean_n50.csv` |
| Check for contamination | `rq3_overlap_check.py --full` |
| Build LIWC input | `rq3_build_libraries_csv.py`, `rq3_build_libraries_csv_prose.py`, then the **manual LIWC-22 step** |

`rq3_select_generation_subset.py` made the original draw, before the README scope defect was found.

### 3. Analyse

Run with `venv/bin/python3 src/<folder>/<script>`.

| Folder | Scripts | Main output |
|---|---|---|
| `src/rq1/` | `rq1_equivalence_check.py`, `rq1_forest_plot.py`, `n200_vs_n1000_delta.py`, `verify_confirmatory_liwc_dimensions.py` (validity audit), `haskell_vs_oo_stats.py` | `rq1_equivalence_check.csv`, `rq1_forest.png`, `files/analysis/construct_validity_check.md` |
| `src/rq2/` | `rq2_variance_decomposition.py`, `confirmatory_rq2_domain_stratified.py`, `confirmatory_rq2_matched_domain.py` | `rq2_variance_decomposition.csv` |
| `src/rq3/` | `rq3_liwc_stats.py`, `rq3_variance_test.py`, `rq3_affect_token_check.py`, `rq3_before_after_defect.py`, `rq3_edit_distance.py`, `rq3_edit_distance_sensitivity.py`, `rq3_plots.py`, `rq3_forest_compact.py` | `files/corpus/rq3/rq3_stats_*.csv` |
| `src/rq4/` | `rq4_classification.py`, `rq4_detector.py`, `rq4_detector_plot.py`, `rq4_pr_curve.py`, `rq3_rq4_clean_update.py` | `rq4_classification_results.csv`, `rq4_detector_results.csv`, `rq4_pr_roc.png` |
| `src/pilot/` | `liwc_stats.py`, `liwc_plots.py` | `files/analysis/liwc_stats_results.csv` |
| `src/common/` | `confirmatory_liwc_stats.py --freeze-date <frame>`, `verify_liwc_dimensions.py`, `confirmatory_plots.py`, `pipeline_diagram.py` | `confirmatory_stats_results.csv`, report figures |

Run `confirmatory_liwc_stats.py` first: it produces the per-frame statistics, and many analysis scripts import it for the shared statistics and the 15 locked categories.

## Known limitations

- Automated tests only cover the core statistics and text handling (`tests/`). Other quality checks are the validity audits, permutation baselines, contamination checks and fixed seeds.
- The script defaults for permutation counts have changed over time: the p = 0.0099 in the report matches a 100-permutation run.

## Further reading

- `RULES.md`: decision rules, filters and exclusions
- `report/SEARCH_RECORD.md`: literature search method and verified numbers
