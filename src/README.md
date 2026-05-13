# SENG402 — API Documentation Corpus Pipeline

This pipeline collects API documentation from Java and Python libraries, extracts natural-language prose from it, and produces a clean text corpus ready for LIWC analysis.

---

## Overview

```
Crawl / Clone  →  Raw files  →  Preprocess  →  LIWC input corpus
```

| Stage | Script | Input | Output |
|---|---|---|---|
| Acquire Java docs | `crawl-clone/crawler.py` | `src/libraries/librariesJAVA.csv` | `files/raw/raw_java/` |
| Acquire Python source | `crawl-clone/cloner.py` | `src/libraries/librariesPYTHON.csv` | `files/raw/raw_python/` |
| Extract & clean text | `prepressor/preprocess.py` | `files/raw/` | `files/preprocess/preprocess_output_{timestamp}/` |

---

## Step 1 — Acquire raw files

### Java (`crawler.py`)
Crawls each library's online Javadoc site and saves HTML pages locally.
Only class/interface/package detail pages are kept — index and nav pages are discarded.

```bash
python src/crawl-clone/crawler.py
```

### Python (`cloner.py`)
Clones each library's Git repository at the tagged release version.
The source `.py` files are used directly in the next step.

```bash
python src/crawl-clone/cloner.py
```

Which libraries are fetched is controlled by the CSVs in `src/libraries/`:
- `librariesJAVA.csv` — Java libraries with `seed_url` (Javadoc root)
- `librariesPYTHON.csv` — Python libraries with `repo_url` and `git_tag`

> **Tip:** Both scripts support a **pause** — press `Space` at any time to pause/resume.  
> Progress is safe to interrupt; already-saved files are skipped on re-run.

---

## Step 2 — Preprocess

Extracts prose text from the raw files (stripping code, signatures, nav elements), filters short chunks, and concatenates everything per library into a single text field ready for LIWC.

```bash
python src/prepressor/preprocess.py                  # both ecosystems
python src/prepressor/preprocess.py --lang java      # java only
python src/prepressor/preprocess.py --lang python    # python only
python src/prepressor/preprocess.py --libraries 1    # first library only
python src/prepressor/preprocess.py --libraries 2-4  # libraries 2–4
```

Output lands in a timestamped directory:
```
files/preprocess/preprocess_output_{DD-MM-YY_HH-MM-SS}/
    java/
        java_chunks.csv      # one row per extracted prose chunk
        java_libraries.csv   # one row per library (concatenated text) — LIWC input
        preprocess_java.csv  # per-file extraction log
    python/
        python_chunks.csv
        python_libraries.csv
        preprocess_python.csv
```

The `*_libraries.csv` files are the primary LIWC inputs.

---

## Re-running safely

- **Crawler/Cloner**: already-downloaded files are detected and skipped, so re-runs are safe and resume from where you left off.
- **Preprocessor**: each run creates a new timestamped output folder, so old results are never overwritten.
