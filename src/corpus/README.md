# corpus

Builds the main corpus used for RQ1, RQ2 and RQ4 language classification. Results go in
`files/corpus/frame_<freeze-date>/`, and most scripts take `--freeze-date`. The filter
definitions (F1–F7) are in [`RULES.md`](../../RULES.md).

## Run order

| Step | File | What it does | Writes |
|---|---|---|---|
| 1 | `sample_frame.py` | Pulls the package list, applies F1–F3, makes the seeded draw with reserves | `frame_*.jsonl.gz`, `sample_manifest.csv`, `exclusion_log.csv`, `frame_metadata.json` |
| 2 | `f7_prefilter.py` | Removes obvious junk by name pattern, such as `-dependencies`. Add `--apply` to write | Manifest, exclusion log |
| 3 | `confirmatory_cloner.py` | Clones each library (F4) and promotes reserves on failure | `files/raw/confirmatory/`, `clone_log.csv` |
| 4 | `confirmatory_preprocessor.py` | Extracts prose from READMEs and docs, applies F5 and F6, and promotes reserves | `text/`, `preprocess_log.csv` |
| 5 | `f7_auto_filter.py` | Larger frame only: automated F7 on descriptions and READMEs | Manifest, exclusion log |
| 6 | `finalize_confirmatory_sample.py` | Freezes the ready libraries | `sample_manifest_final.csv`, `summary_stats.csv` |
| 7 | `f7_review_candidates.py` | Lists libraries worth checking by hand | `f7_review_candidates.csv` |
| 8 | `apply_f7_manual_review.py` | Interactive review of those candidates | Exclusion log |
| 9 | `promote_f7_exclusions.py` | Applies review decisions and promotes replacements | Manifests, exclusion log |
| 10 | `domain_tag_review.py` | Tags each library's domain, with a spot check | `domain_tag_evidence.csv`, `domain_tag_decisions.csv`, manifest |
| 11 | `build_libraries_csv.py` | Combines the final texts into the LIWC-22 input | `libraries.csv` |

Steps 3 and 4 form a loop: when reserves are promoted, run both again.

After step 11, load `libraries.csv` into LIWC-22 by hand, and save the output in the same folder as
`LIWC-22 Results - libraries - LIWC Analysis.csv`.

## One-off scripts

These record how specific corrections were made. They don't need running for a new frame.

| File | What it did |
|---|---|
| `dedup_manifest.py` | Removed duplicate draws caused by unstable API sorting |
| `_build_dedup_check_frame.py` | Created `frame_locked_corrected` by resetting libraries that shared a repo |
| `_merge_dedup_corrected_corpus.py` | Merged 339 unchanged and 61 rescoped texts into the corrected corpus of 400 |
