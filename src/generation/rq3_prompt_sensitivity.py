"""
rq3_prompt_sensitivity: Prompt-wording/design sensitivity check for RQ3.

Requested before locking
prompt_template.md for the full 400-library run: generate the same small
set of libraries under a few deliberately-varied prompts to see how much
the output actually changes. Also operationalizes the contamination worry
raised in the pilot findings, does
giving the model the real library name let it recall memorized training-
data knowledge rather than infer purely from the bare signatures?

Variants (each built from the same libraries x models as the pilot):
    V0_baseline   , prompt_template.md, unchanged.
    V1_anon_name  , same template, package_name replaced with a generic
                     placeholder instead of the real library name.
    V2_length_cap , V0 plus one appended sentence instructing an
                     approximate word target.
    V3_paraphrase , prompt_template_variant_paraphrase.md: same semantic
                     instructions, reworded.

Qualitative/exploratory check, same status as the original pilot, nothing
here feeds the statistical pipeline in the RQ3 plan.

Requires ANTHROPIC_API_KEY and OPENAI_API_KEY in the environment, or in a
.env file passed via --env-file.

Outputs:
    files/corpus/rq3/sensitivity/<safe_name>_<variant>_<out_suffix>.txt
    files/corpus/rq3/sensitivity/sensitivity_log.csv

Usage:
    venv/bin/python3 src/generation/rq3_prompt_sensitivity.py --env-file .env
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import openai

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq3_pilot_generate import (  # noqa: E402
    safe_name, load_env_file, call_model, PROMPT_TEMPLATE,
)

ROOT = Path(__file__).resolve().parents[2]
API_SURFACE_DIR = ROOT / "files" / "corpus" / "rq3" / "api_surface" / "python"
OUT_DIR = ROOT / "files" / "corpus" / "rq3" / "sensitivity"
PARAPHRASE_MD = ROOT / "src" / "md" / "prompt_template_variant_paraphrase.md"

MODELS = [
    ("anthropic", "claude-sonnet-5", "sonnet"),
    ("openai", "gpt-5.6-terra", "openai"),
]

# The two strongest "model already knows this library" signals from the
# original pilot, plus one larger/more obscure contrast case.
SENSITIVITY_LIBRARIES = ["pyspellchecker", "web-fragments", "xsdata"]

ANON_NAME = "sample-project"
LENGTH_ADDENDUM = "\n\nKeep the README to approximately 500 words."

VARIANTS = ["V0_baseline", "V1_anon_name", "V2_length_cap", "V3_paraphrase"]


def load_paraphrase_template() -> str:
    text = PARAPHRASE_MD.read_text(encoding="utf-8")
    # Same last-fence-marker convention as rq3_pilot_generate.load_prompt_template:
    # the file has a nested ``` fence around {api_surface}, so the true
    # closing fence is the LAST one in the file, not the first found by a
    # forward search.
    start = text.index("```\nImagine you are")
    start = text.index("\n", start) + 1
    end = text.rindex("\n```")
    return text[start:end]


PARAPHRASE_TEMPLATE = load_paraphrase_template()


def _substitute(template: str, package_name: str, ecosystem: str, api_surface: str) -> str:
    # .replace(), not .format(): API surfaces can contain literal braces
    # (e.g. xsdata.txt has a default value '{xsdata}Root').
    return (
        template
        .replace("{package_name}", package_name)
        .replace("{ecosystem}", ecosystem)
        .replace("{api_surface}", api_surface)
    )


def build_variant_prompt(variant: str, package_name: str, ecosystem: str, api_surface: str) -> str:
    if variant == "V0_baseline":
        return _substitute(PROMPT_TEMPLATE, package_name, ecosystem, api_surface)
    if variant == "V1_anon_name":
        return _substitute(PROMPT_TEMPLATE, ANON_NAME, ecosystem, api_surface)
    if variant == "V2_length_cap":
        return _substitute(PROMPT_TEMPLATE, package_name, ecosystem, api_surface) + LENGTH_ADDENDUM
    if variant == "V3_paraphrase":
        return _substitute(PARAPHRASE_TEMPLATE, package_name, ecosystem, api_surface)
    raise ValueError(f"unknown variant: {variant}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, default=None)
    args = ap.parse_args()

    if args.env_file:
        if not args.env_file.exists():
            raise SystemExit(f"--env-file not found: {args.env_file}")
        load_env_file(args.env_file)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set (env or --env-file)")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set (env or --env-file)")

    claude_client = anthropic.Anthropic()
    openai_client = openai.OpenAI()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "sensitivity_log.csv"
    log_cols = [
        "timestamp", "package_name", "variant", "provider", "model",
        "status_or_stop_reason", "input_tokens", "output_tokens",
        "output_word_count", "params_note", "error",
    ]
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=log_cols)
    if not log_exists:
        writer.writeheader()

    for pkg in SENSITIVITY_LIBRARIES:
        sname = safe_name(pkg)
        surface_path = API_SURFACE_DIR / f"{sname}.txt"
        if not surface_path.exists():
            print(f"SKIP {pkg}: no api_surface file at {surface_path}")
            continue
        api_surface = surface_path.read_text(encoding="utf-8")
        print(f"=== {pkg} (api_surface {len(api_surface.split())} words) ===")

        for variant in VARIANTS:
            prompt = build_variant_prompt(variant, pkg, "python", api_surface)

            for provider, model, out_suffix in MODELS:
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "package_name": pkg, "variant": variant, "provider": provider,
                    "model": "", "status_or_stop_reason": "",
                    "input_tokens": "", "output_tokens": "",
                    "output_word_count": 0, "params_note": "", "error": "",
                }
                try:
                    text, meta = call_model(provider, model, prompt, claude_client, openai_client)
                    out_path = OUT_DIR / f"{sname}_{variant}_{out_suffix}.txt"
                    out_path.write_text(text, encoding="utf-8")
                    entry["model"] = meta.get("model", "")
                    entry["status_or_stop_reason"] = meta.get("stop_reason") or meta.get("status", "")
                    entry["input_tokens"] = meta.get("input_tokens", "")
                    entry["output_tokens"] = meta.get("output_tokens", "")
                    entry["output_word_count"] = len(text.split())
                    entry["params_note"] = meta.get("params_note", "")
                    print(f"  {variant}/{out_suffix}: {entry['output_word_count']} words -> {out_path.name}")
                except Exception as exc:  # noqa: BLE001
                    entry["error"] = str(exc)[:500]
                    print(f"  {variant}/{out_suffix}: FAILED - {exc}")
                writer.writerow(entry)
                log_fh.flush()

    log_fh.close()
    print(f"\nDone. Log at {log_path}")


if __name__ == "__main__":
    main()
