# Related-work search protocol

A documented, reproducible search rather than a full systematic literature review.
Re-running it should give roughly the same set.

---

## 1. Why four threads

The project sits at an intersection, so a single keyword string will not cover it.
Four threads, each justified by what it has to rule in or out:

| # | Thread | Why this thread exists |
|---|---|---|
| T1 | Psycholinguistic / LIWC analysis of software-engineering text | Establishes the instrument and its prior use in SE. Must surface any existing validity evidence on technical registers, this is where the project's own contribution lands. |
| T2 | Documentation quality, style, readability | Establishes what is already known about documentation *as writing*, and whether ecosystem-level style has been examined before. |
| T3 | LLM-generated documentation and developer perception | Establishes whether anyone has compared generated vs. human documentation for the *same* artefact, which is RQ3's design. |
| T4 | Empirical method: pre-registration, construct validity in SE research | Justifies the pre-registered design as an established practice rather than a personal preference. |


---

## 2. Sources

- **Scopus** (via UC library), primary, best cross-publisher coverage
- **ACM Digital Library**: ICSE/FSE/ASE/CHI venues
- **IEEE Xplore**: ICSE/ICSME/SANER
- **Google Scholar**: forward citation chasing only, not primary search

Justification to state: Scopus for breadth and deduplication across publishers;
ACM and IEEE because the relevant venues are published there; Scholar restricted to
citation chasing because its result set is unstable and cannot be reproduced.

---

## 3. Search strings

Paste these directly. Adjust field prefixes per database.

**T1, psycholinguistics in SE**
```
( "LIWC" OR "psycholinguistic" OR "linguistic inquiry and word count" )
AND ( "software" OR "developer" OR "open source" OR "software engineering" )
```

**T2, documentation style/quality**
```
( "API documentation" OR "software documentation" OR "README" )
AND ( "readability" OR "writing style" OR "linguistic" OR "quality" OR "comprehension" )
```

**T3, generated documentation**
```
( "large language model" OR "LLM" OR "ChatGPT" OR "GPT-4" OR "Copilot" )
AND ( "documentation generation" OR "API documentation" OR "README"
      OR "generated documentation" )
```

**T4, method**
```
( "pre-registration" OR "preregistered" OR "registered report"
  OR "construct validity" )
AND ( "empirical software engineering" OR "software engineering research" )
```

Record for each: the **exact string**, the **database**, the **date run**, and the
**number of hits**.

---

## 4. Inclusion criteria (with rationale)

| ID | Criterion | Rationale |
|---|---|---|
| **I1** | Peer-reviewed conference or journal paper, or a thesis. | Ensures a minimum methodological bar; excludes blog posts and vendor material. |
| **I2** | Published 2010 or later (T3: 2022 or later). | 2010 is Tausczik & Pennebaker's LIWC validation paper, the anchor for the modern dictionaries; earlier psycholinguistic work uses superseded category sets. For T3, pre-2022 generation work predates instruction-tuned models and is not comparable to the systems studied here. |
| **I3** | Studies text produced by or for software developers. | The project's central finding is that register determines instrument validity, so results on news or social-media corpora cannot be assumed to transfer. |
| **I4** | Reports an empirical measurement of text properties, or generates and evaluates documentation. | The contribution here is measurement; position papers without data cannot be compared on method. |

## 5. Exclusion criteria (with rationale)

| ID | Criterion | Rationale |
|---|---|---|
| **E1** | Studies of code comments, commit messages, or issue threads where the text is not prose documentation. | These registers differ so sharply in length and structure that instrument behaviour does not transfer, a claim this project substantiates directly. |
| **E2** | Sentiment-analysis tool-building papers, unless they report validity evidence on technical text. | The project uses a fixed, licensed instrument, so tool-comparison work is relevant only for its validity findings, not its tooling. |
| **E3** | Not in English. | No translation capacity. |
| **E4** | Under 4 pages, or no method section. | Method cannot be assessed. |
| **E5** | Duplicate or extended version of an already-included paper. | Keep the most complete version only. |

---

## 6. Screening process

Counts are recorded at each stage.

1. **Identification.** Run all four strings across the three primary databases.
   Export results. Deduplicate.
2. **Title/abstract screen.** Apply I1–I4 and E1–E5 on title and abstract alone.
   Log a reason code for every exclusion.
3. **Full-text screen.** Read the survivors. Apply the same criteria against the
   full text. Log reasons.
4. **Snowballing.** For each included paper: scan its reference list (backward) and
   its Scholar citations (forward). Apply the same criteria. Additions are logged
   separately from those found by the strings.
