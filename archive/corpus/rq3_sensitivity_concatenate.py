"""
rq3_sensitivity_concatenate: Side-by-side comparison docs for the RQ3
prompt-sensitivity check.

For each sensitivity library (rq3_prompt_sensitivity.SENSITIVITY_LIBRARIES),
concatenates the actual human README followed by all 4 variants x 2 models
(8 sections) from the sensitivity run, each capped at a fixed word count,
so the effect of each prompt manipulation can be read at a glance.

Reading aid only, same status as rq3_pilot_concatenate.py, nothing here
feeds the statistical pipeline in the RQ3 plan.

Outputs:
    files/corpus/rq3/sensitivity_concatenated/<safe_name>_sensitivity.md

Usage:
    venv/bin/python3 src/corpus/rq3_sensitivity_concatenate.py [--cap N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq3_prompt_sensitivity import SENSITIVITY_LIBRARIES, VARIANTS, MODELS  # noqa: E402
from rq3_pilot_generate import safe_name  # noqa: E402
from rq3_pilot_concatenate import cap_words  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SENSITIVITY_DIR = ROOT / "files" / "corpus" / "rq3" / "sensitivity"
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only" / "python"
OUT_DIR = ROOT / "files" / "corpus" / "rq3" / "sensitivity_concatenated"

DEFAULT_CAP = 300


def build_comparison(pkg: str, cap: int) -> str:
    sname = safe_name(pkg)
    parts = [f"# {pkg} — prompt sensitivity comparison\n"]

    readme_path = README_DIR / f"{sname}.txt"
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
        parts.append(
            f"## ACTUAL (human README) ({len(text.split())} words, capped at {cap})\n\n"
            f"{cap_words(text, cap)}\n"
        )
    else:
        parts.append(f"## ACTUAL (human README)\n\n[missing: {readme_path}]\n")

    for variant in VARIANTS:
        for provider, model, out_suffix in MODELS:
            path = SENSITIVITY_DIR / f"{sname}_{variant}_{out_suffix}.txt"
            label = f"{variant} ({out_suffix})"
            if not path.exists():
                parts.append(f"## {label}\n\n[missing: {path}]\n")
                continue
            text = path.read_text(encoding="utf-8")
            parts.append(
                f"## {label} ({len(text.split())} words, capped at {cap})\n\n"
                f"{cap_words(text, cap)}\n"
            )

    return "\n---\n\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for pkg in SENSITIVITY_LIBRARIES:
        doc = build_comparison(pkg, args.cap)
        out_path = OUT_DIR / f"{safe_name(pkg)}_sensitivity.md"
        out_path.write_text(doc, encoding="utf-8")
        print(f"{pkg} -> {out_path}")


if __name__ == "__main__":
    main()
