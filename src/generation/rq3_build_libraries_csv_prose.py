"""
rq3_build_libraries_csv_prose: rebuild the RQ3 LIWC input with the LLM
output normalised the SAME way the human corpus already was.

Why this exists
---------------
The original rq3_libraries.csv compared two corpora that had not been
through the same preprocessing:

  * Human READMEs were extracted via confirmatory_preprocessor.extract_prose
    (rq3_extract_java.py:616, rq3_extract_python.py), which routes markdown
    through _md_to_text -> _html_to_text, and _html_to_text decomposes
    <code>, <pre>, <script>, <style>, <nav>, <footer>, <aside>, <form> and
    <figure>. Fenced code blocks and inline code are therefore removed.

  * LLM output was written straight from the API response to disk and read
    back verbatim. No normalisation at all.

Measured consequence on the original CSV:

    corpus            code share of word content
    java   human                    0.8 %
    python human                    2.4 %
    java   sonnet                  36.3 %
    java   openai                  53.1 %
    python sonnet                  40.7 %
    python openai                  55.6 %

So roughly half of every "document" LIWC scored on the LLM side was source
code, imports, signatures, camelCase identifiers, against ~1-2% on the
human side. Every dimension is affected, but two consequences are concrete:

  1. The Affect artefact is code. 93% of the "java" tokens in GPT's Java
     documents sit inside code blocks (`import java.util.List;`). The
     emo_sad/emo_neg/emotion effect that RQ3 originally reported as its
     headline is import statements being scored as sadness, not a property
     of the model's prose.
  2. Test 2 was confounded independently of that. Stripping code moves the
     BigWords gap by different amounts per ecosystem (Java +12.6 -> +6.6 pp,
     Python +3.7 -> +5.4 pp), and test 2 compares exactly those gaps.

This script therefore applies _md_to_text to the generated documents so both
sides of the comparison receive identical treatment. It reuses the
preprocessor's own function rather than reimplementing a fence-stripping
regex: matching the human pipeline is the entire point, and a hand-rolled
regex would silently diverge from it (inline `code` spans, HTML blocks,
indented code, tables).

Human rows are passed through unchanged, they are already the output of
extract_prose, and re-running the markdown converter over already-extracted
plain text would be a second, asymmetric transformation.

Output is written to a NEW file. The original is left in place on purpose:
the raw-vs-stripped comparison is itself a reportable threat-to-validity
result, so both versions need to remain inspectable.

Output:
    files/corpus/rq3/rq3_libraries_prose.csv

Usage:
    venv/bin/python3 src/generation/rq3_build_libraries_csv_prose.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_preprocessor import _md_to_text  # noqa: E402

IN_PATH = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries.csv"
OUT_PATH = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries_prose.csv"

OUT_COLS = ["library", "ecosystem", "domain", "source",
            "n_words", "n_words_raw", "code_share_pct", "text"]

WORD_RE = re.compile(r"[A-Za-z']+")

# Documents this short after code removal can't support a stable percentage
# on sparse dimensions (a single match moves emo_sad by whole points at
# n=50 words). Flagged, not dropped, dropping one source breaks the paired
# design for that library across all three sources.
SHORT_DOC_WORDS = 100


def n_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def main() -> None:
    csv.field_size_limit(sys.maxsize)

    with open(IN_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows: list[dict] = []
    short: list[str] = []
    empty: list[str] = []

    for r in rows:
        raw = r["text"]
        raw_n = n_words(raw)

        if r["source"] == "human":
            # Already extract_prose output; leave alone (see module docstring).
            text = raw
        else:
            text = _md_to_text(raw)

        n = n_words(text)
        if n == 0:
            empty.append(f'{r["ecosystem"]}/{r["library"]}/{r["source"]}')
            continue
        if n < SHORT_DOC_WORDS:
            short.append(f'{r["ecosystem"]}/{r["library"]}/{r["source"]} ({n}w)')

        out_rows.append({
            "library": r["library"],
            "ecosystem": r["ecosystem"],
            "domain": r["domain"],
            "source": r["source"],
            "n_words": n,
            "n_words_raw": raw_n,
            "code_share_pct": round(100 * (raw_n - n) / raw_n, 2) if raw_n else 0.0,
            "text": text,
        })

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {OUT_PATH}\n")

    # --- report, per (ecosystem, source) ---
    print(f"{'eco':8s}{'source':9s}{'n':>4s}{'mean_raw_w':>12s}"
          f"{'mean_prose_w':>14s}{'mean_code_share':>17s}")
    for eco in ("java", "python"):
        for src in ("human", "sonnet", "openai"):
            sel = [r for r in out_rows
                   if r["ecosystem"] == eco and r["source"] == src]
            if not sel:
                continue
            mr = sum(r["n_words_raw"] for r in sel) / len(sel)
            mp = sum(r["n_words"] for r in sel) / len(sel)
            mc = sum(r["code_share_pct"] for r in sel) / len(sel)
            print(f"{eco:8s}{src:9s}{len(sel):4d}{mr:12.0f}{mp:14.0f}{mc:16.1f}%")

    # --- pairing integrity: LIWC input is only usable if all three
    # sources survive for a library, otherwise Delta can't be formed ---
    keys: dict[tuple[str, str], set[str]] = {}
    for r in out_rows:
        keys.setdefault((r["library"], r["ecosystem"]), set()).add(r["source"])
    incomplete = {k: v for k, v in keys.items()
                  if v != {"human", "sonnet", "openai"}}
    print(f"\nLibraries with all three sources intact: "
          f"{len(keys) - len(incomplete)}/{len(keys)}")
    if incomplete:
        print("  INCOMPLETE (breaks pairing — fix before running LIWC):")
        for (lib, eco), have in incomplete.items():
            print(f"    {eco}/{lib}: only {sorted(have)}")

    if empty:
        print(f"\nDropped {len(empty)} rows that were empty after code removal:")
        for e in empty:
            print(f"    {e}")

    if short:
        print(f"\n{len(short)} rows under {SHORT_DOC_WORDS} words after code "
              f"removal (kept, but percentage-based dimensions are unstable "
              f"at this length — worth reporting as a limitation):")
        for s in short[:20]:
            print(f"    {s}")
        if len(short) > 20:
            print(f"    ... and {len(short) - 20} more")


if __name__ == "__main__":
    main()
