"""
rq3_pilot_generate: Small-sample pilot of the RQ3 generation step.

Before committing to a model/tier for the full 400-library run, this generates documentation for a handful of
already-extracted Python libraries with Claude Sonnet 5 and OpenAI's
GPT-5.6-terra, so the outputs can be eyeballed side by side.

Uses the fixed prompt template in src/md/prompt_template.md (read here as
PROMPT_TEMPLATE, keep the two in sync; the .md file is the citable/appendix
copy, this is the executable copy).

Models (pilot choice, Opus 4.8 excluded from this run):
    Anthropic: claude-sonnet-5. Rejects `temperature` (400, non-default
    sampling params are rejected on Sonnet 5) and runs adaptive thinking by
    default when `thinking` is omitted, both `thinking` and `temperature`
    are left out entirely. This means the plan's original "temperature=0"
    decision cannot be applied to this model as written; this is a
    deviation, logged here and in the plan doc rather than silently worked
    around.
    OpenAI: gpt-5.6-terra ($2.50/$15 per 1M tokens, the mid-tier cost-
    saving option, chosen over the pricing-matched gpt-5.6-sol
    comparator). Responses API. temperature=0 is attempted first since
    GPT-5.6 does accept it; on a 400 mentioning temperature, retried
    without it (logged either way).

Requires ANTHROPIC_API_KEY and OPENAI_API_KEY in the environment, or in a
.env file passed via --env-file.

Output cap: 8192 tokens for both providers. The original 4096 truncated
`xsdata` (the largest pilot library, 7,301-word API surface) mid-sentence
on gpt-5.6-terra, caught via `status: incomplete` + `output_tokens: 4096`
in the log, not from an exception. 400-library libraries can be larger
still (the RQ3 plan's `large_surface_flag` set), so this cap will need
revisiting again once those are in scope.

Outputs:
    files/corpus/rq3/pilot_generation/<safe_name>_<out_suffix>.txt
    files/corpus/rq3/pilot_generation/pilot_log.csv

Usage:
    venv/bin/python3 src/generation/rq3_pilot_generate.py [--env-file PATH]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import openai

ROOT = Path(__file__).resolve().parents[2]
API_SURFACE_DIR = ROOT / "files" / "corpus" / "rq3" / "api_surface" / "python"
PILOT_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_generation"
PROMPT_TEMPLATE_MD = ROOT / "src" / "md" / "prompt_template.md"

# (provider, model_id, out_suffix)
MODELS = [
    ("anthropic", "claude-sonnet-5", "sonnet"),
    ("openai", "gpt-5.6-terra", "openai"),
]

# Spans the observed API-surface-size distribution (10th/30th/50th/70th/90th
# percentile among the 197 "ready" Python libraries) so the pilot isn't
# accidentally biased toward one size regime.
PILOT_LIBRARIES = [
    "web-fragments",
    "pyspellchecker",
    "trame-vuetify",
    "py7zr",
    "xsdata",
]

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_")


def load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE loader, only ANTHROPIC_API_KEY/OPENAI_API_KEY are
    needed here, so a manual parser avoids adding a python-dotenv dependency
    for one call site. Does not overwrite variables already set."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_prompt_template() -> str:
    text = PROMPT_TEMPLATE_MD.read_text(encoding="utf-8")
    # Extract the fenced block between the first '```\nYou are writing' and
    # the *real* closing fence, so this script and the citable .md copy can
    # never silently drift apart. The template contains a nested ``` block
    # around {api_surface} (for visual quoting in the .md file), so the
    # closing fence must be the LAST fence marker in the file, not the
    # first one found by a forward search, a forward search finds the
    # inner fence and truncates the template right before the API surface
    # placeholder ever gets substituted in. This assumes nothing follows
    # the true closing fence in the file.
    start = text.index("```\nYou are writing")
    start = text.index("\n", start) + 1
    end = text.rindex("\n```")
    return text[start:end]


PROMPT_TEMPLATE = load_prompt_template()


def build_prompt(package_name: str, ecosystem: str, api_surface: str) -> str:
    # Plain substitution, not str.format(): API surfaces can contain
    # literal braces (e.g. xsdata.txt has a default value '{xsdata}Root'),
    # which str.format() would misparse as format fields and error on.
    return (
        PROMPT_TEMPLATE
        .replace("{package_name}", package_name)
        .replace("{ecosystem}", ecosystem)
        .replace("{api_surface}", api_surface)
    )


def call_claude(client: anthropic.Anthropic, model: str, prompt: str) -> tuple[str, dict]:
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    meta = {
        "model": response.model,
        "stop_reason": response.stop_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "params_note": "no temperature (rejected on this model); no thinking param set",
    }
    return text, meta


def call_openai(client: openai.OpenAI, model: str, prompt: str) -> tuple[str, dict]:
    params_note = "temperature=0, reasoning.effort=low"
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": "low"},
            max_output_tokens=8192,
            temperature=0,
        )
    except openai.BadRequestError as exc:
        if "temperature" not in str(exc).lower():
            raise
        params_note = "reasoning.effort=low (temperature rejected by API, retried without it)"
        response = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": "low"},
            max_output_tokens=8192,
        )
    meta = {
        "model": response.model,
        "status": response.status,
        "params_note": params_note,
    }
    if response.usage is not None:
        meta["input_tokens"] = response.usage.input_tokens
        meta["output_tokens"] = response.usage.output_tokens
    return response.output_text, meta


def call_model(
    provider: str,
    model: str,
    prompt: str,
    claude_client: anthropic.Anthropic,
    openai_client: openai.OpenAI,
) -> tuple[str, dict]:
    if provider == "anthropic":
        return call_claude(claude_client, model, prompt)
    if provider == "openai":
        return call_openai(openai_client, model, prompt)
    raise ValueError(f"unknown provider: {provider}")


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

    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = PILOT_DIR / "pilot_log.csv"
    log_cols = [
        "timestamp", "package_name", "provider", "model", "status_or_stop_reason",
        "input_tokens", "output_tokens", "output_word_count", "params_note", "error",
    ]
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=log_cols)
    if not log_exists:
        writer.writeheader()

    for pkg in PILOT_LIBRARIES:
        sname = safe_name(pkg)
        surface_path = API_SURFACE_DIR / f"{sname}.txt"
        if not surface_path.exists():
            print(f"SKIP {pkg}: no api_surface file at {surface_path}")
            continue
        api_surface = surface_path.read_text(encoding="utf-8")
        prompt = build_prompt(pkg, "python", api_surface)
        print(f"=== {pkg} (api_surface {len(api_surface.split())} words) ===")

        for provider, model, out_suffix in MODELS:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "package_name": pkg, "provider": provider,
                "model": "", "status_or_stop_reason": "",
                "input_tokens": "", "output_tokens": "",
                "output_word_count": 0, "params_note": "", "error": "",
            }
            try:
                text, meta = call_model(provider, model, prompt, claude_client, openai_client)
                out_path = PILOT_DIR / f"{sname}_{out_suffix}.txt"
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
    print(f"\nDone. Log at {log_path}")


if __name__ == "__main__":
    main()
