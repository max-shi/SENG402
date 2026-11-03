"""
triage_screen.py: assisted title/abstract screening of a Scopus export.

This does NOT make inclusion decisions. It applies three transparent,
pre-stated rules so that hand screening is spent on records where judgement is
actually required, and it records the rule that fired for every record so the
resulting funnel is auditable and reconstructible.

Stage 1, publication window (criterion I2). Records published before 2010 are
    excluded. 2010 is the Tausczik & Pennebaker LIWC validation paper, the
    anchor for the modern dictionaries; earlier work uses superseded category
    sets. This criterion is applied here rather than at retrieval so that the
    retrieval count is not silently pre-filtered.

Stage 2, hard out-of-scope domains. Clinical, education, social-media,
    general-NLP and finance corpora. A record matching one of these is excluded
    UNLESS it also carries an explicit software-documentation signal, which
    rescues genuine SE papers that merely mention such a corpus.

Stage 3, relevance. The project sits at the intersection of software
    engineering and language analysis, so a record must connect the two, or
    carry an explicit documentation or register-theory signal.

Everything surviving all three goes to `manual` and must be read. The excluded
buckets are suggestions; final decisions are in the `final_decision` column.

Usage:
    venv/bin/python3 report/triage_screen.py <scopus_export.csv>
Outputs:
    report/triage_result.csv    one row per record: bucket, rule, decision slot
    report/triage_summary.txt   counts, for the funnel
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

MIN_YEAR = 2010

HARD = [
    ("clinical",  r"\b(patient|clinical|therap\w*|depress\w*|suicid\w*|ptsd|mental health|psychiatr\w*|nurs\w*|cancer|covid|dementia|autis\w*|hearing aid|medical record|diagnos\w*|healthcare|health care)\b"),
    ("education", r"\b(student essay|classroom|pedagog\w*|l2 learner|language learning|second language|exam)\b"),
    ("social",    r"\b(twitter|tweet|facebook|instagram|tiktok|reddit|youtube|political speech|election|misinformation|fake news|hate speech)\b"),
    ("other_nlp", r"\b(machine translation|speech recognition|image caption|named entity|low-resource language|dialect)\b"),
    ("finance",   r"\b(stock|financial disclosure|earnings call|fraud|accounting)\b"),
]

SE = re.compile(r"\b(software|developer|programmer|source code|api|librar(y|ies)|github|stack overflow|open.?source|programming|readme|repositor\w*|code review|commit message|bug report)\b", re.I)
LING = re.compile(r"\b(liwc|psycholinguist\w*|linguistic\w*|readability|writing style|stylometr\w*|register|discourse|corpus linguistic\w*|sentiment|emotion|lexical|text analysis)\b", re.I)
DOC = re.compile(r"\b(software documentation|api documentation|readme|technical writing|docstring|documentation quality)\b", re.I)
REG = re.compile(r"\b(register variation|multi-?dimensional analysis|biber)\b", re.I)


def field(row: dict, *names: str) -> str:
    for n in names:
        for k in row:
            if k and k.strip().lower() == n:
                return row[k] or ""
    return ""


def classify(title: str, abstract: str, year: str) -> tuple[str, str]:
    hay = f"{title} {abstract}".lower()
    try:
        yr = int(str(year).strip()[:4])
    except (ValueError, TypeError):
        yr = 0
    if yr and yr < MIN_YEAR:
        return "exclude_year", f"pre-{MIN_YEAR} (I2)"
    has_doc = bool(DOC.search(hay))
    hard = next((n for n, p in HARD if re.search(p, hay, re.I)), None)
    if hard and not has_doc:
        return "exclude_scope", hard
    relevant = (SE.search(hay) and LING.search(hay)) or has_doc or REG.search(hay)
    if not relevant:
        return "exclude_scope", "no software+language signal"
    return "manual", ""


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: triage_screen.py <scopus_export.csv>")
    src = Path(sys.argv[1])
    out_dir = Path(__file__).resolve().parent
    csv.field_size_limit(10 ** 7)

    rows: list[dict] = []
    seen_doi: set[str] = set()
    with open(src, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            title = field(r, "title", "document title")
            abstract = field(r, "abstract")
            doi = field(r, "doi").strip().lower()
            year = field(r, "year")
            if doi and doi in seen_doi:
                bucket, rule = "duplicate", "doi seen earlier"
            else:
                if doi:
                    seen_doi.add(doi)
                bucket, rule = classify(title, abstract, year)
            rows.append({"title": title, "year": year, "doi": doi,
                         "source": field(r, "source title"),
                         "bucket": bucket, "rule": rule,
                         "final_decision": "", "note": ""})

    with open(out_dir / "triage_result.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["title", "year", "doi", "source",
                                          "bucket", "rule", "final_decision", "note"])
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["bucket"] for r in rows)
    manual = c["manual"]
    lines = [
        f"Source file    : {src.name}",
        f"Records in     : {len(rows)}",
        "",
        "FUNNEL",
        f"  retrieved            {len(rows)}",
        f"  - duplicate (DOI)    {c['duplicate']}",
        f"  - pre-{MIN_YEAR} (I2)      {c['exclude_year']}",
        f"  - out of scope       {c['exclude_scope']}",
        f"  = to manual screen   {manual}",
        "",
        "Out-of-scope rules fired:",
    ]
    rc = Counter(r["rule"] for r in rows if r["bucket"] == "exclude_scope")
    lines += [f"  {k:28s} {v}" for k, v in rc.most_common()]
    lines += ["",
              "The excluded buckets are suggestions. Final decisions are in the",
              "`final_decision` column of triage_result.csv."]
    txt = "\n".join(lines)
    (out_dir / "triage_summary.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
