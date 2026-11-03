# rq2

**RQ2: how consistent is style within a language, compared with between languages?**
Run `src/common/confirmatory_liwc_stats.py` for the frame first.

| File | What it does | Reads | Writes |
|---|---|---|---|
| `rq2_variance_decomposition.py` | Splits each category's variance into between and within languages. This is the source of the 98.8% figure | `frame_locked_corrected` LIWC-22 output | `files/analysis/rq2_variance_decomposition.csv` |
| `confirmatory_rq2_domain_stratified.py` | Kruskal-Wallis across library domains, within each language | A frame's LIWC-22 output and stats | `confirmatory_rq2_domain_stratified.csv` in that frame |
| `confirmatory_rq2_matched_domain.py` | Compares Java and Python within matching domains, to test whether a different domain mix explains differences | A frame's LIWC-22 output and stats | `confirmatory_rq2_matched_domain.csv` in that frame |

The domain scripts take `--freeze-date`. `confirmatory_rq2_matched_domain.py` also takes `--min-n`.
