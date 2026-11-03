# rq3

**RQ3: how does AI-written documentation differ from human-written documentation?**
Inputs come from `src/generation/` and the manual LIWC-22 step. Results go in `files/corpus/rq3/`
unless noted.

## Run order

| Step | File | What it does | Writes |
|---|---|---|---|
| 1 | `rq3_liwc_stats.py` | Test 1: paired human vs AI, per model and language. Test 2: whether that gap differs between Java and Python | `rq3_stats_test1_within_ecosystem.csv`, `rq3_stats_test2_cross_ecosystem.csv` |
| 2 | `rq3_variance_test.py` | Test 4: whether the spread of scores differs (Brown-Forsythe) | `rq3_stats_test4_variance.csv` |
| 3 | `rq3_affect_token_check.py` | Test 3: audits the emotion categories, including the word "java" scoring as sadness | `rq3_affect_token_check.csv`, `rq3_affect_token_breakdown.csv` |
| 4 | `rq3_edit_distance.py` | Measures text similarity between human and AI documents, and among documents from each author | `rq3_edit_distance_*.csv` |
| 5 | `rq3_edit_distance_sensitivity.py` | Checks that the similarity result doesn't depend on the truncation length | Prints only |
| 6 | `rq3_plots.py` | Forest and violin figures | `files/analysis/figures/rq3_*` |
| 7 | `rq3_forest_compact.py` | Column-width forest plot of the 5 clean categories | `report/figures/rq3_test1_forest_compact.png` |

## Do not rerun without care

`rq3_before_after_defect.py` compares results before and after the code-removal fix. It expects
the original corpus, but its text files and "after" scores now come from the rebuilt one, so a
rerun mixes the two and overwrites `files/analysis/rq3_before_after_defect.md`. The saved file is
the valid record of the original corpus.
