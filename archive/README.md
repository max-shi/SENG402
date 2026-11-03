# Archive

Files no longer part of the study's pipeline. Kept for history, not maintained.

| Path | What it is | Why it was archived |
|---|---|---|
| `clean_raw.py` | Deleted cloned source trees | Pilot-era utility; points at an old `raw_python/` path. Deletes files, so don't run it casually |
| `liwc_stats_results.csv` | Pilot results | Identical copy of `files/analysis/liwc_stats_results.csv` |
| `corpus/genre_split_pilot.py`, `corpus/docs_url_recon.py`, `corpus/tutorial_crawl_pilot.py` | Tutorial vs reference genre split | Abandoned line of work |
| `corpus/rq3_pilot_concatenate.py`, `corpus/rq3_sensitivity_concatenate.py`, `corpus/rq3_blind_spotcheck.py` | Side-by-side reading aids for the RQ3 pilot | One-off manual checks; nothing depends on them |
| `analysis/pairwise_annotate.py` | Interactive plot annotation tool | One-off manual exploration |
| `analysis/confirmatory_cluster_viz.py`, `analysis/n1000_plots.py` | Exploratory PCA and pairs plots | Figures not used in the report |
| `pilot/crawler.py` | Javadoc site crawler | Replaced by cloning source before the pilot results were produced |
| `misc/` | Hour sheets | Project admin, not code |

Scripts keep their original folder depth, so project-root paths still resolve.
Some import modules that stayed in `src/`, and some hardcoded folders have moved since (for example, `crawler.py` looks for `libraries/` beside its old location). To try one, from the repo root:

```bash
PYTHONPATH=src/common:src/corpus:src/generation:src/rq3:src/rq4 venv/bin/python3 archive/corpus/genre_split_pilot.py
```

These have only been checked to compile since the move.
