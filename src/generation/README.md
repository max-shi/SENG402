# generation

Builds the paired human and AI corpus used for RQ3 and RQ4 authorship. Results go in
`files/corpus/rq3/`, and clones go in `files/raw/rq3/`. The rules are in
[`RULES.md`](../../RULES.md). **Scripts that call the models cost money and need API keys in `.env`.**

## Run order

| Step | File | What it does | Writes |
|---|---|---|---|
| 1 | `rq3_reclone.py` | Re-clones the libraries at their recorded versions | `files/raw/rq3/`, `reclone_log.csv` |
| 2 | `rq3_extract_python.py`, `rq3_extract_java.py` | Extracts each library's API signatures for the model, and its README as the human text | `api_surface/`, `readme_only/`, `extract_log_*.csv` |
| 3 | `rq3_select_generation_subset.py` | Original seeded draw of libraries to generate, since replaced by step 7 | `generation_subset_n*.csv` |
| 4 | `rq3_full_generate.py` | **Paid.** Generates a README per library with each model. Try `--dry-run` first | `full_generation/` |
| 5 | `rq3_readme_scope_audit.py` | Checks whether each human README belongs to its library. Hand grades are kept in `rq3_readme_scope_tiers.csv` | `rq3_readme_scope_audit.csv` |
| 6 | `rq3_extend_java_clean.py` | Tops the Java pool back up with libraries that have their own README | `rq3_extension_log.csv` |
| 7 | `rq3_select_clean_subset.py` | Draws the final 50 per language from the clean pool | `generation_subset_clean_n50.csv` |
| 8 | `rq3_full_generate.py --subset-manifest` | **Paid.** Generates documents for libraries new to the subset | `full_generation/` |
| 9 | `rq3_overlap_check.py --full` | Checks AI output for copied text and leaked internal paths | `overlap_check/` |
| 10 | `rq3_build_libraries_csv.py` | Combines human and AI texts, with code still in the AI text | `rq3_libraries.csv` |
| 11 | `rq3_build_libraries_csv_prose.py` | Cleans AI text the same way as human text. This is the corrected input | `rq3_libraries_prose.csv` |

After step 11, run `rq3_libraries_prose.csv` through LIWC-22 by hand, and save the output beside it.

## Calibration scripts

These settled the prompt and models before the full run. `rq3_full_generate.py` and
`rq3_overlap_check.py` import from them, so they aren't dead code.

| File | What it does | Writes |
|---|---|---|
| `rq3_pilot_generate.py` | **Paid.** Trial run on 5 libraries, to pick the models. Defines shared model calls | `pilot_generation/` |
| `rq3_prompt_sensitivity.py` | **Paid.** Tests prompt variants V0–V3 on a few libraries | `sensitivity/` |
| `rq3_sensitivity_v4.py` | **Paid.** Tests the explicit-disclaimer variant V4 | `sensitivity/` |
