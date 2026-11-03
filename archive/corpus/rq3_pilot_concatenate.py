"""
rq3_pilot_concatenate: Side-by-side comparison docs for the RQ3 pilot.

For each pilot library (rq3_pilot_generate.PILOT_LIBRARIES), concatenates
the OpenAI output, the Claude Sonnet 5 output, and the actual human README
(files/corpus/rq3/readme_only/python/<pkg>.txt, the same README-only human
text used as the comparison target per the RQ3 plan) into one file, each section
capped at a fixed word count so no single section dominates the read.

This is a reading aid for eyeballing the pilot, not part of the analysis
pipeline, nothing here feeds the statistical tests in the RQ3 plan.

Outputs:
    files/corpus/rq3/pilot_concatenated/<safe_name>_comparison.md

Usage:
    venv/bin/python3 src/corpus/rq3_pilot_concatenate.py [--cap N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq3_pilot_generate import PILOT_LIBRARIES, safe_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PILOT_GEN_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_generation"
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only" / "python"
OUT_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_concatenated"

DEFAULT_CAP = 1000

SECTIONS = [
    ("OpenAI (gpt-5.6-terra)", "_openai.txt", PILOT_GEN_DIR),
    ("Claude (Sonnet 5)", "_sonnet.txt", PILOT_GEN_DIR),
    ("ACTUAL (human README)", ".txt", README_DIR),
]


def cap_words(text: str, cap: int) -> str:
    """Truncate at `cap` words while preserving line structure (headers,
    code fences, bullet lists), a naive text.split()/" ".join() round trip
    discards every newline, flattening the whole section into one
    paragraph regardless of the source's actual formatting."""
    total_words = len(text.split())
    if total_words <= cap:
        return text
    out_lines: list[str] = []
    words_seen = 0
    for line in text.splitlines():
        line_words = line.split()
        if words_seen + len(line_words) > cap:
            remaining = cap - words_seen
            if remaining > 0:
                out_lines.append(" ".join(line_words[:remaining]))
            break
        out_lines.append(line)
        words_seen += len(line_words)
    return "\n".join(out_lines) + f"\n\n[... truncated at {cap} words, {total_words} total]"


def build_comparison(pkg: str, cap: int) -> str:
    sname = safe_name(pkg)
    parts = [f"# {pkg} — pilot comparison\n"]
    for label, suffix, directory in SECTIONS:
        path = directory / f"{sname}{suffix}"
        if not path.exists():
            parts.append(f"## {label}\n\n[missing: {path}]\n")
            continue
        text = path.read_text(encoding="utf-8")
        parts.append(f"## {label} ({len(text.split())} words, capped at {cap})\n\n{cap_words(text, cap)}\n")
    return "\n---\n\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--libraries", nargs="*", default=None,
                     help="Subset of PILOT_LIBRARIES; default is all of them.")
    args = ap.parse_args()

    libraries = args.libraries or PILOT_LIBRARIES
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for pkg in libraries:
        doc = build_comparison(pkg, args.cap)
        out_path = OUT_DIR / f"{safe_name(pkg)}_comparison.md"
        out_path.write_text(doc, encoding="utf-8")
        print(f"{pkg} -> {out_path}")


if __name__ == "__main__":
    main()
