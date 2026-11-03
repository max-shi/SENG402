"""
rq3_sensitivity_v4: V4 "explicit disclaimer" prompt variant.

Follow-up to the earlier sensitivity test (V0-V3), directly per
feedback: "possibly being more directed in the prompt (to make
the bias explicit, rather than an unknown)". V0-V3 showed anonymizing the
library name doesn't stop contamination (the leak comes from the API
surface itself, not the name field), this variant tests the other lever
suggested: telling the model outright that it may already know the
library, and instructing it not to rely on that.

Standalone rather than folded into rq3_prompt_sensitivity.py's main(), which
regenerates all 4 existing variants unconditionally on every run (no
resume/skip logic), running it again here would silently re-spend on the
24 already-done V0-V3 calls for no reason. This reuses the same libraries,
models, and logging convention and appends to the same sensitivity_log.csv.

Usage:
    venv/bin/python3 src/generation/rq3_sensitivity_v4.py --env-file .env
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import openai

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq3_pilot_generate import safe_name, load_env_file, call_model, PROMPT_TEMPLATE  # noqa: E402
from rq3_prompt_sensitivity import SENSITIVITY_LIBRARIES, MODELS, API_SURFACE_DIR, OUT_DIR  # noqa: E402

VARIANT = "V4_explicit_disclaimer"

DISCLAIMER_ADDENDUM = (
    "\n\nImportant: you may already be familiar with this library from your "
    "training data. Do not rely on any prior knowledge of it, and do not "
    "let it influence your answer. Base your answer strictly and only on "
    "the API surface given above — do not mention, reference, or invent any "
    "internal file paths, module names, or implementation details that are "
    "not explicitly shown in the signatures above."
)


def build_prompt(package_name: str, ecosystem: str, api_surface: str) -> str:
    base = (
        PROMPT_TEMPLATE
        .replace("{package_name}", package_name)
        .replace("{ecosystem}", ecosystem)
        .replace("{api_surface}", api_surface)
    )
    return base + DISCLAIMER_ADDENDUM


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, default=None)
    args = ap.parse_args()

    if args.env_file:
        if not args.env_file.exists():
            raise SystemExit(f"--env-file not found: {args.env_file}")
        load_env_file(args.env_file)

    claude_client = anthropic.Anthropic()
    openai_client = openai.OpenAI()

    log_path = OUT_DIR / "sensitivity_log.csv"
    log_cols = [
        "timestamp", "package_name", "variant", "provider", "model",
        "status_or_stop_reason", "input_tokens", "output_tokens",
        "output_word_count", "params_note", "error",
    ]
    log_fh = open(log_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=log_cols)

    for pkg in SENSITIVITY_LIBRARIES:
        sname = safe_name(pkg)
        surface_path = API_SURFACE_DIR / f"{sname}.txt"
        if not surface_path.exists():
            print(f"SKIP {pkg}: no api_surface file at {surface_path}")
            continue
        api_surface = surface_path.read_text(encoding="utf-8")
        prompt = build_prompt(pkg, "python", api_surface)
        print(f"=== {pkg} ({VARIANT}) ===")

        for provider, model, out_suffix in MODELS:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "package_name": pkg, "variant": VARIANT, "provider": provider,
                "model": "", "status_or_stop_reason": "",
                "input_tokens": "", "output_tokens": "",
                "output_word_count": 0, "params_note": "", "error": "",
            }
            try:
                text, meta = call_model(provider, model, prompt, claude_client, openai_client)
                out_path = OUT_DIR / f"{sname}_{VARIANT}_{out_suffix}.txt"
                out_path.write_text(text, encoding="utf-8")
                entry["model"] = meta.get("model", "")
                entry["status_or_stop_reason"] = meta.get("stop_reason") or meta.get("status", "")
                entry["input_tokens"] = meta.get("input_tokens", "")
                entry["output_tokens"] = meta.get("output_tokens", "")
                entry["output_word_count"] = len(text.split())
                entry["params_note"] = meta.get("params_note", "")
                print(f"  {out_suffix}: {entry['output_word_count']} words -> {out_path.name}")
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)[:500]
                print(f"  {out_suffix}: FAILED - {exc}")
            writer.writerow(entry)
            log_fh.flush()

    log_fh.close()
    print(f"\nDone. Appended to {log_path}")


if __name__ == "__main__":
    main()
