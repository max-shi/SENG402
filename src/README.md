# Source code

Each folder has its own README listing what each file does. Run scripts from the repo root:
`venv/bin/python3 src/<folder>/<script>.py`

| Folder | Purpose | Results used for |
|---|---|---|
| [`pilot/`](pilot/README.md) | Screen 59 LIWC-22 categories down to a shortlist | Choosing the 15 categories |
| [`corpus/`](corpus/README.md) | Sample libraries, clone them, extract and filter text | RQ1, RQ2, RQ4 language |
| [`generation/`](generation/README.md) | Build the human and AI document pairs | RQ3, RQ4 authorship |
| [`common/`](common/README.md) | Shared statistics, helpers and figures | Everything |
| [`rq1/`](rq1/README.md) | Java vs Python, and the validity audit | RQ1 |
| [`rq2/`](rq2/README.md) | Variation within and between languages | RQ2 |
| [`rq3/`](rq3/README.md) | Human vs AI documentation | RQ3 |
| [`rq4/`](rq4/README.md) | Classifiers and the AI detector | RQ4 |
| [`md/`](md/README.md) | LLM prompts and the development log | RQ3 |

Scripts find the project root from their own location, so they must stay exactly one folder
below `src/`. Each adds all of the `src/` folders to its import path, so script names must stay
unique. See [`RULES.md`](../RULES.md) for the rules these scripts apply.

**Data flow:**

```
pilot → the 15 categories
corpus → libraries.csv → LIWC-22 (manual) → rq1, rq2, rq4 language
generation → rq3_libraries_prose.csv → LIWC-22 (manual) → rq3, rq4 authorship
```
