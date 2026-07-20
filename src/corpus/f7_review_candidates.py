"""
f7_review_candidates — Surface candidates for manual F7 review.

Post-crawl F7 (§7.6.4) requires human judgement to identify stubs,
forks, and mirrors that automated pre-filters missed. Reading all 400
docs manually is impractical, so this helper applies simple heuristics
to the extracted text and surfaces likely-suspects for human review.

Heuristics (each independently flags a row):
    1. Strong-signal phrases at the top of the doc: "fork of", "mirror
       of", "no longer maintained", "this project is archived", etc.
    2. word_count_post_clean is in the F5-adjacent range (500-800)
       AND text has < 2 doc files. (Barely-passing thin-content libs.)

An earlier version also checked repo-owner vs package-namespace
mismatch, but this heuristic proved far too noisy (canonical mappings
like `com.google.*` -> `github.com/googleapis/*` are common) and was
dropped.

The output is a CSV of candidates; you review each and mark
`f7_manual_flag` in sample_manifest_final.csv either 'ok' or
'excluded_fork_mirror_stub' with an evidence note.

Usage:
    venv/bin/python3 src/corpus/f7_review_candidates.py [--freeze-date YYYYMMDD]
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

# Strong-signal phrases only. These are the exact wordings maintainers
# use to declare abandonment / fork / mirror status; each has very few
# innocent uses. Softer signals ("deprecated", "please use", "use X
# instead") were dropped as they match too many tutorial passages.
SUSPICIOUS_PHRASES = [
    r"\bfork of\b",
    r"\bforked from\b",
    r"\bmirror of\b",
    r"\bmirrored from\b",
    r"\bno longer maintained\b",
    r"\bunmaintained\b",
    r"\bsuperseded by\b",
    r"\bthis (project|package|repository|library|module) is (deprecated|archived|abandoned|no longer)\b",
    r"\bthis (project|package|repository|library|module) has (moved|been moved)\b",
    r"\bhas moved to\b",
]
PHRASE_RES = [re.compile(p, re.IGNORECASE) for p in SUSPICIOUS_PHRASES]

# Only check the very top of each doc — abandonment / fork notices are
# always in the first paragraph or two. 1500 chars ~= 250 words ~= first
# 2 short paragraphs. Reduces false positives from example code that
# happens to mention forks/mirrors deeper in the docs.
TEXT_HEAD_CHARS = 1500


def check_phrases(text: str) -> list[str]:
    head = text[:TEXT_HEAD_CHARS]
    hits: list[str] = []
    for pat, r in zip(SUSPICIOUS_PHRASES, PHRASE_RES):
        m = r.search(head)
        if m:
            # Grab a short surrounding snippet for reviewer context.
            start = max(0, m.start() - 40)
            end = min(len(head), m.end() + 40)
            snippet = head[start:end].replace("\n", " ").strip()
            hits.append(f"{pat} :: '...{snippet}...'")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    final_path = frame_dir / "sample_manifest_final.csv"
    if not final_path.exists():
        raise SystemExit(f"run finalize_confirmatory_sample.py first: "
                         f"{final_path} not found")
    out_path = frame_dir / "f7_review_candidates.csv"

    with open(final_path) as f:
        rows = list(csv.DictReader(f))

    candidates: list[dict] = []
    for r in rows:
        reasons: list[str] = []

        # 1. Phrase check
        text_path = ROOT / r["text_file_path"]
        text = ""
        if text_path.is_file():
            try:
                text = text_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        phrase_hits = check_phrases(text) if text else []
        if phrase_hits:
            reasons.append(f"suspicious_phrases: {' | '.join(phrase_hits[:2])}")

        # 2. Thin content
        wc = int(r.get("word_count_post_clean") or 0)
        pages = int(r.get("pages_crawled") or 0)
        if 500 <= wc <= 800 and pages <= 2:
            reasons.append(f"thin_content: words={wc}, pages={pages}")

        if reasons:
            candidates.append({
                "ecosystem": r["ecosystem"],
                "package_name": r["package_name"],
                "repository_url": r.get("repository_url", ""),
                "word_count_post_clean": wc,
                "text_file_path": r["text_file_path"],
                "reasons": " ; ".join(reasons),
            })

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(candidates[0].keys())
                           if candidates else
                           ["ecosystem", "package_name", "repository_url",
                            "word_count_post_clean", "text_file_path",
                            "reasons"])
        w.writeheader()
        w.writerows(candidates)

    print(f"Wrote {len(candidates)} F7 review candidates to {out_path}")

    # Break down by heuristic for the summary.
    from collections import Counter
    kinds = Counter()
    for c in candidates:
        for r in c["reasons"].split(" ; "):
            kinds[r.split(":", 1)[0]] += 1
    print("Breakdown by heuristic:")
    for k, v in kinds.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
