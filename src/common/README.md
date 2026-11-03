# common

Code shared across stages. Other folders import from here, so changes affect everything.

| File | What it does | Reads | Writes |
|---|---|---|---|
| `confirmatory_liwc_stats.py` | Layer 1 of the decision rule. Tests the 15 categories for Java vs Python. Also defines the shared statistics, `LOCKED_DIMENSIONS`, `ALPHA`, `DELTA_THRESHOLD` and `RNG_SEED` | A frame's LIWC-22 output | `confirmatory_stats_results.csv` in that frame |
| `verify_liwc_dimensions.py` | Layer 2 on the pilot corpus: checks the words driving each category's score. Its word lists are reused by later audits | Pilot text and LIWC-22 output | `files/analysis/verify_liwc_dimensions_output.txt` |
| `confirmatory_plots.py` | Figures for the n=200 results: pilot vs main effect sizes, domain mix, RQ2 heatmap, violins. `rq3_plots.py` reuses its helpers | `frame_locked` results, pilot results | `files/analysis/figures/04`–`09` |
| `pipeline_diagram.py` | Draws the study pipeline figure | None | `report/figures/pipeline.png` |
| `frame_config.py` | Looks up a frame's settings, such as its target sample size | `frame_metadata.json` | None |
| `pause_helper.py` | Press Space to pause long-running terminal scripts | None | None |

Run the statistics for a frame:

```bash
venv/bin/python3 src/common/confirmatory_liwc_stats.py --freeze-date locked_corrected
```
