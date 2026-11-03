# rq1

**RQ1: do Java and Python documentation differ?** The tests themselves are in
`src/common/confirmatory_liwc_stats.py`; run that first for each frame.

| File | What it does | Reads | Writes |
|---|---|---|---|
| `rq1_forest_plot.py` | Forest plot of all 15 categories at n=1000, with the equivalence band | `frame_n2000` stats | `files/analysis/figures/rq1_confirmatory_forest.png`, `report/figures/rq1_forest.png` |
| `rq1_equivalence_check.py` | Checks whether each category's whole CI lies inside ±0.33, meaning "too small to matter", not just "not detected" | Stats from both frames | `files/analysis/rq1_equivalence_check.csv` |
| `n200_vs_n1000_delta.py` | Compares effect sizes between the two sample sizes | Stats from `frame_locked` and `frame_n2000` | `files/analysis/figures/10_n200_vs_n1000_delta.png`, `files/analysis/n200_vs_n1000_delta_table.md` |
| `verify_confirmatory_liwc_dimensions.py` | Layer 2 audit: which words drive the scores in the main corpus. Needs the frame's `libraries.csv`, which isn't in git | A frame's text, LIWC-22 output and stats | `verify_confirmatory_liwc_dimensions_output.txt` in that frame |
| `haskell_vs_oo_stats.py` | Exploratory: Haskell vs pooled Java and Python. Not in the main results | Corrected corpus and Haskell LIWC-22 output | `frame_haskell_v2/haskell_vs_oo_stats_results.csv` |
