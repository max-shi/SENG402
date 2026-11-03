"""
rq3_blind_spotcheck: One-off blinded human-vs-LLM reading aid.

Not part of the pipeline (no LIWC scoring, no stats), just a manual-reading
helper so a spot check of human vs. generated docs isn't biased by seeing the
real library name, or knowing in advance which document is which.

For each of the 5 pilot libraries, pairs the real human README against each
model's baseline (V0-equivalent) output, redacts occurrences of the library
name (raw name + safe_name + hyphen/underscore variants), randomly labels
the two documents "Document A"/"Document B" per pair, and writes the answer
key to a separate file so it isn't visible while reading.

Usage:
    venv/bin/python3 src/corpus/rq3_blind_spotcheck.py
"""

from __future__ import annotations

import csv
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq3_pilot_generate import safe_name, PILOT_LIBRARIES, MODELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only" / "python"
PILOT_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_generation"
OUT_DIR = ROOT / "files" / "corpus" / "rq3" / "blind_spotcheck"

random.seed(402)  # reproducible A/B assignment across reruns


def name_variants(package_name: str) -> list[str]:
    sname = safe_name(package_name)
    variants = {package_name, sname}
    for v in list(variants):
        variants.add(v.replace("-", "_"))
        variants.add(v.replace("_", "-"))
        variants.add(v.replace("-", "").replace("_", ""))
    return sorted(variants, key=len, reverse=True)  # longest first, avoid partial-match leftovers


def redact(text: str, package_name: str) -> str:
    for variant in name_variants(package_name):
        if not variant:
            continue
        text = re.sub(re.escape(variant), "[LIBRARY]", text, flags=re.IGNORECASE)
    return text


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key_path = OUT_DIR / "answer_key.csv"
    key_rows = []

    for pkg in PILOT_LIBRARIES:
        sname = safe_name(pkg)
        readme_path = README_DIR / f"{sname}.txt"
        if not readme_path.exists():
            print(f"SKIP {pkg}: no human README at {readme_path}")
            continue
        human_text = redact(readme_path.read_text(encoding="utf-8"), pkg)

        for _provider, _model, out_suffix in MODELS:
            gen_path = PILOT_DIR / f"{sname}_{out_suffix}.txt"
            if not gen_path.exists():
                continue
            gen_text = redact(gen_path.read_text(encoding="utf-8"), pkg)

            pair = [("human", human_text), (out_suffix, gen_text)]
            random.shuffle(pair)
            labels = ["Document A", "Document B"]

            out_path = OUT_DIR / f"blind_{sname}_{out_suffix}.md"
            content = f"# Blind comparison ({sname} vs. {out_suffix})\n\n---\n\n"
            for label, (_source, text) in zip(labels, pair):
                content += f"## {label}\n\n{text}\n\n---\n\n"
            out_path.write_text(content, encoding="utf-8")

            key_rows.append({
                "file": out_path.name,
                "package_name": pkg,
                "compared_against": out_suffix,
                "Document A": pair[0][0],
                "Document B": pair[1][0],
            })
            print(f"wrote {out_path.relative_to(ROOT)}")

    with open(key_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    print(f"\nAnswer key (don't open until after reading): {key_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
