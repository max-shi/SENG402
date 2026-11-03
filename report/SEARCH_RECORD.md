# Literature search: authoritative record

**This file is the single source of truth for all search numbers.**

Frozen 2026-09-16.

---

## 1. Two searches, and how they relate

There are **two** searches. They are reported separately and must not be merged
into a single funnel.

**Primary search, May 2026, ten sources.** This is the search that produced the
included set. Its funnel:

```
~1,400 retrieved
   -> ~950   after deduplication
   ->   70   advanced to full text
   ->   25   retained
   +     6   added by citation chaining
   =    31   included
```

The arithmetic is internally consistent. Counts are approximate. Two caveats:
the Round 1 figure (~788) reproduces the retrieval reported by Sajadi et al. in
their Table 2, not an independent count; and the Round 2 figure (~200) was
annotated "estimated". Both are superseded as *measurements* by the verification
below, but the funnel itself stands as the record of how the 31 were selected.

**Verification, September 2026, Scopus only.** The same sixteen strings re-run
under one consistent field restriction, to establish that the strategy is
reproducible and to obtain exact per-string counts. Returned 1,830 records,
1,624 unique. **No screening was performed on this set**: it verifies retrieval
scale, nothing more.

**Audit, September 2026.** The included set was re-checked against the
exclusion criteria and four works were removed (see this record). **Final set: 27.**

So: `31 from the May screening, minus 4 on audit, = 27 cited`. The 1,624 is a
reproducibility figure and does not connect to 27 by any path.

---

## 2. Verified retrieval (Scopus, 16 Sep 2026)

Field: `TITLE-ABS-KEY` for every string. Filters applied inside each query:
`LANGUAGE(english)` and `DOCTYPE(ar) OR DOCTYPE(cp) OR DOCTYPE(re) OR DOCTYPE(ch)`.
No date filter at retrieval, the publication-window criterion is applied at
screening instead, so retrieval is not silently pre-filtered.

| String | Round | Area | Records |
|---|---|---|---|
| 1a | 1 | LIWC × software engineering | 7 |
| 1b | 1 | LIWC × software | 414 |
| 2a | 2 | API documentation × quality/readability | 95 |
| 2b | 2 | API documentation × developers/learning | 264 |
| 2c | 2 | Software documentation × linguistic/style | 112 |
| 3a | 3 | LLM × LIWC/psycholinguistic | 109 |
| 3b | 3 | LLM × linguistic/stylometric × detection | 546 |
| 3c | 3 | LLM × documentation × comparison | 126 |
| 4a | 4 | Developer × emotion/sentiment × LIWC | 4 |
| 4b | 4 | Sentiment analysis × SE × SO/GitHub | 60 |
| 4c | 4 | Developer communication × linguistic | 5 |
| 5a | 5 | Register variation × corpus linguistics | 45 |
| 5b | 5 | Biber × register × MD analysis | 37 |
| 5c | 5 | Register variation × programming/tech doc | 1 |
| 6a | 6 | Linguistic behaviour × OSS × social status | 2 |
| 6b | 6 | Ecosystem × community × writing style | 3 |

**By round:** R1 421 · R2 471 · R3 781 · R4 69 · R5 83 · R6 5

**Total (with overlap): 1,830**
**Unique after combining all 16 with `OR`: 1,624**
**Overlap: 206 (11.3%)**

The low overlap indicates the six rounds address largely disjoint literatures
rather than one body of work reached by six routes.

Exact queries: `search_rerun_worksheet.csv` (per string) and
`scopus_combined_query.txt` (the OR-combined query producing 1,624).

## 2a. September screening exercise (Scopus set)

The 1,624 Scopus records were put through an assisted two-pass triage
(`triage_screen.py`), which applies transparent stated
rules and records the rule that fired for every record. Output:
`triage_result.csv` (all 1,624 rows) and `triage_summary.txt`.

```
1,624  retrieved
  PASS 1, eligibility
    -   2  duplicate records (same DOI)                        [E2]
    -  84  published before 2010                               [I2]
    - 492  out-of-scope domain                                 [E4]
             clinical   281   social  142   education  34
             finance     19   other NLP 16
  = 1,046  eligible
  PASS 2, topical relevance
    - 442  no software + language signal, and no explicit
           documentation or register-theory signal
  =   604  advance to manual title-and-abstract screening
```

Pass 1 removes records that fail a stated criterion irrespective of topic;
Pass 2 removes records that are eligible but off-topic. Abstracts were included
in the export (1,620 of 1,624 carry abstract text), so this is title-*and-
abstract* screening, not title-only.

The automated buckets are triage, not decisions. Manual screening of the 604 is
recorded in the `final_decision` column of `triage_result.csv`.

**Status: the 604 have not yet been hand-screened.** Until they are, no
downstream count from this exercise may be reported.

## 2b. Relationship to the included set: IMPORTANT

**Only 9 of the 27 included works appear anywhere in the Scopus 1,624.**
(Corrected 2026-10-08 from 10: `biber2019` was listed as present, but its bib
`doi` field is a placeholder string and no title in the 1,624 matches it.)
Verified by DOI and normalised-title matching against the report's bibliography.

Present in the Scopus set: `sajadi2026`, `calefato2018`, `han2024`,
`uddin2015`, `robillard2011`, `meng2020`, `sandler2024`, `novielli2014`, `arya2024b`.

The other 18 are absent for straightforward reasons:

| Reason | Works |
|---|---|
| Not indexed by Scopus (technical report, thesis, or book) | `boyd2022`, `pennebaker2015`, `moser2009`, `cassee2023`, `biber1988` |
| Indexed, but not retrieved by these sixteen strings (e.g. LIWC methodology papers with no software content) | `tausczik2010`, `biber2016`, `biber2019`, `novielli2018`, `novielli2019`, `novielli2019b`, `serebrenik2023`, `meng2019`, `tang2023`, `uddin2021`, `kabir2024`, `vasilescu2013` |

**Consequence.** The Scopus funnel and the included set are two different
exercises. The 27 came from a ten-source search plus citation chaining,
including books, theses and technical reports that Scopus does not index. The
Scopus run covers one database and the sixteen strings only.

**`1,624 -> 604 -> 27` is not a single funnel.** Eighteen
of the 27 were never in the 1,624. The accurate structure is the one in this record:
the May search produced the 31 (audited to 27), and the September Scopus
exercise is a separate, reproducible verification of retrieval and screening
scale. Reporting them as one pipeline would describe a process that did not
occur.

## 3. Sparse results: the gap, quantified

These are the most argumentatively useful numbers in the search. They convert
"no prior work does this" from an assertion into a measurement.

| String | Intersection | Records |
|---|---|---|
| 5c | register variation × programming / technical documentation | **1** |
| 6a | linguistic behaviour × open source × social status | **2** |
| 6b | ecosystem × community × writing style | **3** |
| 4a | developer × emotion/sentiment × LIWC | **4** |
| 4c | developer communication × linguistic × empirical | **5** |
| 1a | LIWC × "software engineering" | **7** |

## 4. Corrections applied

1. **String 5c precedence bug.** Originally written
   `"register variation" AND "programming" OR "technical documentation"`.
   Because `AND` binds more tightly than `OR`, this matched any document
   mentioning technical documentation rather than the intended intersection.
   Corrected to `"register variation" AND ("programming" OR "technical
   documentation")`, which returns 1 record. The corrected form is what is
   reported. Report this as a corrected deviation, not silently.

2. **Round 1 provenance.** The original protocol recorded ~788 for Round 1,
   annotated "from Sajadi et al. 2026, Table 2". That is *their* multi-database
   SMS retrieval, not ours. Our own Scopus retrieval for 1a/1b is 7 and 414.
   Cite theirs separately as the replication target; never merge the two.

3. **Round 2 estimate.** The original ~200 was annotated "estimated from
   ACM+IEEE+Springer". Superseded by the verified 471.

## 5. Included set: 31 → 27

| Paper | Action | Reason |
|---|---|---|
| P29 | dropped | Self-declared duplicate of P07 (criterion **E2**) |
| P15 Arya et al., *The software documentor mindset* | dropped | arXiv preprint only (criterion **E5**) |
| P19 *A survey on LLM-generated text detection* | dropped | No usable author list recorded; arXiv version only (**E5**) |
| P20 *Distinguishing AI-generated and human-written text…* | dropped | Author list recorded as "Unidentified"; venue "published online" (**E5**) |

**Final: 27 works included through the search.**

One citation was also corrected: the sentence on documentation contributors'
motivations originally cited P15 (the preprint) but describes P31, *Why people
contribute software documentation* (CHASE 2024, peer-reviewed). Corrected to P31.

## 6. Files

| File | Contents |
|---|---|
| `SEARCH_RECORD.md` | **This file.** Authoritative numbers. |
| `search_rerun_worksheet.csv` | 16 queries with verified counts and run date. |
| `scopus_combined_query.txt` | The OR-combined query returning 1,624. |
| `related_work_protocol.md` | Design rationale for the four/six-thread structure and criteria. |
| `scopus_howto.md` | Reproduction instructions. |
