# Study Rules and Exclusions

The single reference for what counted, what was excluded, and where each rule lives. It records
what actually ran. Each frame's settings are in `files/corpus/<frame>/frame_metadata.json`.

## Decision rule

A category counts as a difference only if it passes **both layers**.

| Layer | Requirement | Code |
|---|---|---|
| 1. Statistics | Holm-adjusted p < 0.05 **and** \|Cliff's δ\| ≥ 0.33 | `src/common/confirmatory_liwc_stats.py` (`ALPHA`, `DELTA_THRESHOLD`) |
| 2. Validity audit | The words behind the score mean what the category is named for | `src/rq1/verify_confirmatory_liwc_dimensions.py`, `src/rq3/rq3_affect_token_check.py` |

A claim about a whole group needs at least two categories in that group passing, with the
same side higher, and compatible meanings. Anything else is reported as a single category.

0.33 is the "medium" boundary from Romano et al. (2006).

## The 15 locked categories

Locked 2026-05-20, before the main data was collected. Audit results are from
`files/analysis/construct_validity_check.md`.

| Group | Category | Audit rating |
|---|---|---|
| Affect | `emotion` | Register-shifted |
| Affect | `emo_neg` | Mixed |
| Affect | `emo_anger` | Register-shifted |
| Affect | `emo_sad` | Register-shifted |
| Affect | `Tone` | Mixed |
| Style | `BigWords` | Clean |
| Style | `WPS` | Clean |
| Style | `ipron` | Clean |
| Cognition | `tentat` | Clean |
| Cognition | `certitude` | Clean |
| Drives | `curiosity` | Mixed |
| Drives | `achieve` | Mixed |
| Drives | `risk` | Mixed |
| Action | `motion` | Register-shifted |
| Action | `conflict` | Register-shifted |

- **Clean:** the score can be read as written.
- **Mixed:** some of the score comes from words with a different meaning in code. Qualify any finding.
- **Register-shifted:** the main words mean something else in technical writing, like "arguments" counting as conflict. Can't be read at face value.

**How they were chosen:** a pilot of about 45 libraries per language screened 59 categories
using docstrings and Javadoc comments. 13 passed the rule above for Java vs Python.
`certitude` and `risk` got in on a secondary three-way rule that included JavaScript.

## Tests by research question

| Question | Test | Families (Holm, m=15 each) | Corpus | Target | Code |
|---|---|---|---|---|---|
| RQ1 | Mann-Whitney U, Cliff's δ, 2,000-resample bootstrap CI | 1 | n=200 and n=1000 per language | Decision rule | `src/common/confirmatory_liwc_stats.py`, `src/rq1/rq1_equivalence_check.py` |
| RQ2 | Share of variance between languages (η²); Kruskal-Wallis across domains | Per language | n=200 per language | Reported | `src/rq2/` |
| RQ3 test 1 | Paired Wilcoxon signed-rank, Cliff's δ | 4 (model × language) | n=50 per language | Decision rule | `src/rq3/rq3_liwc_stats.py` |
| RQ3 test 2 | Mann-Whitney U on the human-AI gap, Java vs Python | 2 (model) | n=50 per language | Decision rule | `src/rq3/rq3_liwc_stats.py` |
| RQ3 test 3 | Validity audit | n/a | n=50 per language | Layer 2 | `src/rq3/rq3_affect_token_check.py` |
| RQ3 test 4 | Brown-Forsythe on spread | 4 (model × language) | n=50 per language | Holm p < 0.05 | `src/rq3/rq3_variance_test.py` |
| RQ4 language | Logistic regression, linear SVM, random forest (300 trees), default settings. 5-fold CV × 10, 20% held out | n/a | n=200 per language | Macro-F1 ≥ 0.75 | `src/rq4/rq4_classification.py` |
| RQ4 authorship | One threshold on `BigWords`, relearned in each fold. 5-fold CV × 10 | n/a | 100 human, 200 AI | Reported | `src/rq4/rq4_detector.py` |

**Equivalence check (RQ1):** a category's whole 95% CI must lie inside ±0.33 to support "too small to matter".

**Baselines (RQ4):** shuffled labels (about 0.50) and always guessing one language (macro-F1 0.333).

The 0.75 target was set for three languages and kept after JavaScript was dropped, so it was
not moved after seeing results.

## Corpus filters

| Filter | Rule | Stage | Code |
|---|---|---|---|
| F1 | Latest release on the registry at the freeze date | Frame | `src/corpus/sample_frame.py` |
| F2 | Has a license field | Frame | `src/corpus/sample_frame.py` |
| F3 | At least 5 dependent packages | Frame | `src/corpus/sample_frame.py` (`MIN_DEPENDENTS`) |
| F4 | Repository can be cloned | Clone | `src/corpus/confirmatory_cloner.py` |
| F5 | At least 500 words after cleaning | Preprocess | `src/corpus/confirmatory_preprocessor.py` (`WORD_MIN`) |
| F6 | At least 50% of sampled paragraphs detected as English | Preprocess | `src/corpus/confirmatory_preprocessor.py` (`ENGLISH_MIN_FRACTION`) |
| F7 | Not a stub, fork or mirror | Review | `src/corpus/f7_prefilter.py`, `f7_review_candidates.py`, `apply_f7_manual_review.py`, `promote_f7_exclusions.py`; `f7_auto_filter.py` for n=1000 |
| DEDUP | Not a duplicate draw | Frame | `src/corpus/dedup_manifest.py` |

**Text kept:** `README*` plus `docs/`, `doc/` and `documentation/` folders, with code blocks,
tags and boilerplate stripped. Changelogs, licenses and contributing guides are skipped.
Each library is capped at its first 100,000 words.

**Deliberately not used:** stars, downloads, "top N", recent commits, or hand-picking for
quality. These would skew the mix of library types or select on what's being measured.

## What was excluded

Counts come from each frame's `exclusion_log.csv`, which records library, stage, filter,
evidence and time. Excluded libraries were replaced from reserves in draw order.

| Stage and filter | `frame_locked_corrected` | `frame_n2000` |
|---|---|---|
| Clone, F4 | 138 | 595 |
| Preprocess, F5 | 294 | 893 |
| Preprocess, F6 | 5 | 29 |
| F7 prefilter | 2 | |
| F7 automated (description and README) | | 121 |
| Frame dedup | 7 | |

Totals: 446 and 1,638 rows. In the n=1000 log, 101 of the F4 rows record a git authentication
error ("Invalid username or token"). GitHub returns that for private or deleted repos, so these
are repos that couldn't be accessed, not a judgement on their documentation.

`frame_locked` was locked on 2026-07-12, before its main analysis was run.

| Frame | Final sample | Seed | Use |
|---|---|---|---|
| `frame_locked` | 200 per language | 402 | Original main frame, before the duplicate fix |
| `frame_locked_corrected` | 200 per language | 402 | Corrected frame: RQ1, RQ2, RQ4 language |
| `frame_n2000` | 1000 per language (planned 2000) | 20260721 | Larger RQ1 re-estimate, detector validation |
| `frame_haskell_v2` | 85 usable | 402 | Exploratory only |
| `rq3/` | 50 per language | 402 | RQ3, RQ4 authorship |

**Duplicate fix:** 29 of the 400 libraries (18 Java, 11 Python) had text identical to another
library, because repos with several packages were read from the root. Each package is now
scoped to its own folder (`find_scoped_root`).

## RQ3 corpus rules

**Human text:** the README only, with code removed, so it's comparable with a generated README.

**Inclusion:** both rules use repo structure and length only, never LIWC scores. They were
added after the original corpus had been analysed, so they're a documented post-hoc correction.

1. The module has its own README, or the repo holds a single package.
2. README and API surface each have at least 50 words.

These were added after an audit found 47 of the original 100 human READMEs came from the root
of a repo with several packages (39 Java, 8 Python). `src/generation/rq3_readme_scope_audit.py`
counts a repo as having several packages at 2 or more build manifests. Those 47 were then
graded by hand (`files/corpus/rq3/rq3_readme_scope_tiers.csv`):

| Grade | Meaning | Java | Python | Total |
|---|---|---|---|---|
| Severe | README describes an unrelated or much larger project | 25 | 4 | 29 |
| Partial | README of a focused project, with the module one part of it | 8 | 2 | 10 |
| Benign | The module is effectively the library | 6 | 2 | 8 |

The audit covers the original 100. Only 21 of its libraries are in the rebuilt corpus, all
graded ok, so the README-scope rows in `files/analysis/rq4_detector_validation.csv` are the
same 63 documents three times and don't test anything.

**Draw:** `random.Random(402)` over the sorted clean pool, with no stratification. The Java
pool was exactly 50, so all of it was used, and it spans two frames
(`src/generation/rq3_select_clean_subset.py`, `rq3_extend_java_clean.py`).

**Generation:** `src/generation/rq3_full_generate.py`

| Setting | Value |
|---|---|
| Models | `claude-sonnet-5` (no temperature set), `gpt-5.6-terra` (temperature 0) |
| Input | Library name, language, public API signatures. No docstrings, comments or real README |
| Prompt | `src/md/prompt_template.md`, fixed across libraries |
| Output limit | 8,192 tokens |
| Cleaning | Same extraction as the human text |

**Contamination check:** `src/generation/rq3_overlap_check.py` flags 8-word n-gram containment
of 0.5 or more against the real README, and internal file paths that weren't in the API surface.

**Detector rule:** `BigWords` above 34.1% means generated. It's learned from the corpus, and
recalculated inside each fold during evaluation.

## Pilot rerun on docs

An exploratory check added after the study, and not part of the locked analysis. It uses the
pilot's Java and Python libraries at the same pinned tags, with the F5 and F6 rules above
(`src/pilot/pilot_docs_rerun.py`, `pilot_docs_compare.py`). Results are in
`files/analysis/pilot_docs_comparison.md`.

## Changes from the plan

| Change | Why |
|---|---|
| Confirmatory stage added | The pilot showed 13 of 15 passing, which couldn't be interpreted on its own |
| Pilot used docstrings; main study used READMEs and docs | Docstrings were hard to parse out effectively; documentation files were cleaner and easier to extract |
| Crawling replaced by cloning | Same extraction for both languages |
| JavaScript dropped | 49 pilot libraries were too few for a matched analysis, and a third language roughly doubled the cost. Dropped before the main data was drawn |
| Haskell tried, not used | Only 85 usable libraries |
| n=2000 frame reduced to 1000 per language | Disk space and clone failures |
| F7 automated for the larger frame | Manual review of about 10,000 candidates wasn't feasible |
| RQ3 reduced from 400 libraries to 50 per language | Cost |
| RQ3 corpus redrawn | README scope audit |
| RQ2's sweep of the other 44 categories dropped | No committed category had met the rule |
