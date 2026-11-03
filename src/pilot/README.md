# Pilot pipeline

This is the pilot stage only. For the main study, see the [root README](../../README.md).

The pilot used a small set of libraries to screen 59 LIWC-22 categories, which
produced the shortlist of 15 categories locked for the main study.

```
Clone source  ->  Extract code comments  ->  LIWC-22 (manual)  ->  Screening statistics
```

| Stage | Script | Input | Output |
|---|---|---|---|
| Clone repositories at a pinned tag | `cloner.py` | `libraries/libraries<LANG>.csv` | `files/raw/raw_<lang>/` |
| Extract docstrings and Javadoc comments from source | `preprocess.py`, using `extractor_<lang>.py` | `files/raw/` | `files/preprocess/preprocess_output_<timestamp>/` |
| Screen categories | `liwc_stats.py` | LIWC-22 output CSV | `files/analysis/liwc_stats_results.csv` |
| Plot the screening | `liwc_plots.py` | Screening results | `files/analysis/figures/01`–`03` |

Run from the repository root:

```bash
venv/bin/python3 src/pilot/cloner.py --lang java          # or python; omit --lang for all
venv/bin/python3 src/pilot/preprocess.py --lang java      # omit --lang for all
venv/bin/python3 src/pilot/preprocess.py --libraries 2-4  # libraries 2 to 4 only
```

`cloner.py` also accepts `--libraries`. Press Space to pause or resume.

The `*_libraries.csv` files in each preprocess output folder are the LIWC-22 inputs. LIWC-22
is run by hand, and `liwc_stats.py` and `liwc_plots.py` read the output from
`preprocess_output_13-05-26_21-50-10/`, the run used for the pilot's results.

JavaScript was in the pilot but was dropped from the main study. An early Javadoc crawler
was replaced by cloning, so both languages are extracted from source the same way. It's in
`archive/pilot/`.

Re-running is safe: existing clones are updated to the pinned tag, and each preprocess run
writes to a new timestamped folder.

## Files

| File | What it does |
|---|---|
| `cloner.py` | Clones each library at its pinned tag |
| `preprocess.py` | Runs the extractors, filters short chunks and combines text per library |
| `extractor_java.py` | Pulls Javadoc comments from `.java` files |
| `extractor_python.py` | Pulls docstrings from `.py` files |
| `extractor_javascript.py` | JavaScript and TypeScript version |
| `liwc_stats.py` | Screens the categories across languages. `pilot_docs_compare.py` reuses its statistics |
| `liwc_plots.py` | Plots the screening results |
| `libraries/` | The pilot's library lists, with repo URLs and pinned tags |

## Rerun on READMEs and docs

An exploratory check added after the study. It isn't part of the locked analysis.

| File | What it does | Writes |
|---|---|---|
| `pilot_docs_rerun.py` | Clones the Java and Python libraries at the same tags, and applies the main study's extraction and filters | `files/raw/pilot_docs/`, `files/preprocess/pilot_docs_rerun/` |
| `pilot_docs_compare.py` | Compares docstrings with docs, and with the main study. Needs the manual LIWC-22 output saved in `files/preprocess/pilot_docs_rerun/` for the full comparison | `files/analysis/pilot_docs_comparison.md`, `.csv` |
