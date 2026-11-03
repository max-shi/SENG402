"""
rq3_full_generate: Full 400-library x 2-model generation step for RQ3.

**A real run costs money**, across up to 400 libraries x 2 models.
--dry-run makes no API calls. An early contamination rate of 31/34 (91%)
was a bug in the overlap checker; corrected calibration found 1/40 (2.5%).

Reuses safe_name/load_env_file/call_model/PROMPT_TEMPLATE from
rq3_pilot_generate.py, same pattern rq3_prompt_sensitivity.py already
uses. Same fixed prompt template (locked), same two models
(Claude Sonnet 5 + GPT-5.6-terra; see rq3_pilot_generate's
docstring for why Sonnet 5 gets no temperature/thinking params while
GPT-5.6-terra gets temperature=0), same 8192-token output cap.

For each library with a successfully-extracted API surface
(files/corpus/rq3/api_surface/<ecosystem>/<safe_name>.txt, from
rq3_extract_python.py / rq3_extract_java.py; libraries with no such
file, e.g. the 3 pure-C/Rust Python packages, confirmed non-Java-source
packages, or confirmed-unresolvable monorepos, see rq3_extract_java.py's
docstring, are logged as skipped, not retried, since there is
nothing to prompt from), calls both models once each. Already-generated
(library, model) pairs are skipped on rerun unless --force is passed, so
an interrupted run (rate limits, a crash partway through) can resume
without re-spending on libraries already done. Transient failures get a
few retries with backoff before being logged as failed, some individual
rate-limit/network blips are expected at this call volume and shouldn't
need a manual rerun of the whole batch.

**Corpus size (revised): 324 ready (197 Python + 127 Java) after correcting a
Java-extractor monorepo-scoping bug that had inflated the ready count to
a bogus 160. It was further scoped to a seeded,
documented n=100/ecosystem subset for cost and cross-ecosystem symmetry
see rq3_select_generation_subset.py and --subset-manifest below,
making the real run 200 libraries x 2 models = 400 calls, not 800.**

Outputs:
    files/corpus/rq3/full_generation/<ecosystem>/<safe_name>_<out_suffix>.txt
    files/corpus/rq3/full_generation/full_generation_log.csv

Usage:
    venv/bin/python3 src/generation/rq3_full_generate.py --dry-run
    venv/bin/python3 src/generation/rq3_full_generate.py --env-file .env
        [--ecosystem python|java|all] [--libraries START-END] [--limit N]
        [--subset-manifest files/corpus/rq3/generation_subset_n100.csv]
        [--force]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import openai

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_cloner import safe_name  # noqa: E402
from rq3_pilot_generate import (  # noqa: E402
    call_model, load_env_file, PROMPT_TEMPLATE,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
)
API_SURFACE_ROOT = ROOT / "files" / "corpus" / "rq3" / "api_surface"
OUT_ROOT = ROOT / "files" / "corpus" / "rq3" / "full_generation"

MODELS = [
    ("anthropic", "claude-sonnet-5", "sonnet"),
    ("openai", "gpt-5.6-terra", "openai"),
]

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 5

LOG_COLS = [
    "timestamp", "package_name", "ecosystem", "safe_name", "provider", "model",
    "status_or_stop_reason", "input_tokens", "output_tokens",
    "output_word_count", "params_note", "attempts", "error",
]


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


def load_rows(ecosystems: list[str], manifest: Path = SOURCE_MANIFEST) -> list[dict]:
    with open(manifest) as f:
        return [r for r in csv.DictReader(f) if r["ecosystem"] in ecosystems]


def load_subset_names(subset_manifest: Path) -> set[str]:
    """package_names marked selected=true in a
    rq3_select_generation_subset.py-style manifest. Opt-in only, the
    default (no --subset-manifest) still runs the full ready corpus,
    unchanged."""
    with open(subset_manifest) as f:
        return {
            r["package_name"] for r in csv.DictReader(f)
            if r["selected"] == "true"
        }


def call_with_retries(
    provider: str, model: str, prompt: str,
    claude_client: anthropic.Anthropic, openai_client: openai.OpenAI,
) -> tuple[str, dict, int]:
    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text, meta = call_model(provider, model, prompt, claude_client, openai_client)
            return text, meta, attempt
        except Exception as exc:  # noqa: BLE001, one failed call must not
            # abort the other ~800; retried a few times for transient
            # rate-limit/network errors, then given up on and logged.
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SEC * attempt)
    raise last_exc


def parse_range(value: str) -> tuple[int, int]:
    if "-" in value:
        a, b = value.split("-", 1)
        return int(a), int(b)
    n = int(value)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--ecosystem", choices=["python", "java", "all"], default="all")
    ap.add_argument(
        "--libraries", help="Range within the filtered set, e.g. '1-50' (1-indexed)."
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--subset-manifest", type=Path, default=None,
        help=(
            "Restrict to package_names marked selected=true in a "
            "rq3_select_generation_subset.py-style CSV (e.g. "
            "files/corpus/rq3/generation_subset_n100.csv). Omit to run "
            "the full ready corpus (default, unchanged behavior)."
        ),
    )
    ap.add_argument(
        "--source-manifest", type=Path, default=SOURCE_MANIFEST,
        help=(
            "Manifest supplying (package_name, ecosystem) rows. Defaults to "
            "the original 400-library frame. The clean re-draw "
            "spans three frames, so its own subset CSV is passed here as "
            "well as to --subset-manifest."
        ),
    )
    ap.add_argument(
        "--force", action="store_true",
        help="Regenerate even if an output file already exists.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="List what would be generated; no API calls, no cost.",
    )
    args = ap.parse_args()

    claude_client: anthropic.Anthropic | None = None
    openai_client: openai.OpenAI | None = None
    if not args.dry_run:
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

    if not args.source_manifest.exists():
        raise SystemExit(f"source manifest not found: {args.source_manifest}")

    ecosystems = ["python", "java"] if args.ecosystem == "all" else [args.ecosystem]
    rows = load_rows(ecosystems, args.source_manifest)

    if args.subset_manifest:
        if not args.subset_manifest.exists():
            raise SystemExit(f"--subset-manifest not found: {args.subset_manifest}")
        selected_names = load_subset_names(args.subset_manifest)
        rows = [r for r in rows if r["package_name"] in selected_names]
        print(f"--subset-manifest applied: {len(rows)} libraries "
              f"selected from {args.subset_manifest}")

    if args.libraries:
        start, end = parse_range(args.libraries)
        rows = rows[start - 1:end]
    if args.limit > 0:
        rows = rows[:args.limit]

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = OUT_ROOT / "full_generation_log.csv"
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=LOG_COLS)
    if not log_exists:
        writer.writeheader()

    n_planned = n_skipped_no_surface = n_skipped_exists = 0
    n_done = n_failed = 0
    try:
        for i, row in enumerate(rows, 1):
            pkg, eco = row["package_name"], row["ecosystem"]
            sname = safe_name(pkg)
            surface_path = API_SURFACE_ROOT / eco / f"{sname}.txt"
            if not surface_path.exists():
                n_skipped_no_surface += 1
                continue
            api_surface = surface_path.read_text(encoding="utf-8")
            prompt = build_prompt(pkg, eco, api_surface)
            out_dir = OUT_ROOT / eco

            for provider, model, out_suffix in MODELS:
                out_path = out_dir / f"{sname}_{out_suffix}.txt"
                n_planned += 1
                if out_path.exists() and not args.force:
                    n_skipped_exists += 1
                    continue

                if args.dry_run:
                    print(f"[{i}/{len(rows)}] would generate: "
                          f"{out_path.relative_to(ROOT)}")
                    continue

                out_dir.mkdir(parents=True, exist_ok=True)
                entry = {col: "" for col in LOG_COLS}
                entry.update({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "package_name": pkg, "ecosystem": eco, "safe_name": sname,
                    "provider": provider, "output_word_count": 0, "attempts": 0,
                })
                print(f"[{i}/{len(rows)}] {pkg} ({eco}) -> {out_suffix}")
                try:
                    text, meta, attempts = call_with_retries(
                        provider, model, prompt, claude_client, openai_client,
                    )
                    out_path.write_text(text, encoding="utf-8")
                    entry["model"] = meta.get("model", "")
                    entry["status_or_stop_reason"] = (
                        meta.get("stop_reason") or meta.get("status", "")
                    )
                    entry["input_tokens"] = meta.get("input_tokens", "")
                    entry["output_tokens"] = meta.get("output_tokens", "")
                    entry["output_word_count"] = len(text.split())
                    entry["params_note"] = meta.get("params_note", "")
                    entry["attempts"] = attempts
                    n_done += 1
                except Exception as exc:  # noqa: BLE001, one failed
                    # library/model pair must not abort the other ~800.
                    entry["error"] = str(exc)[:500]
                    entry["attempts"] = MAX_ATTEMPTS
                    n_failed += 1
                    print(f"  FAILED: {exc}")
                writer.writerow(entry)
                log_fh.flush()
    finally:
        log_fh.close()

    print("\n--- full generation summary ---")
    print(f"  planned calls:            {n_planned}")
    print(f"  skipped (no api_surface): {n_skipped_no_surface} libraries")
    print(f"  skipped (already exists): {n_skipped_exists}")
    if not args.dry_run:
        print(f"  generated:                {n_done}")
        print(f"  failed:                   {n_failed}")


if __name__ == "__main__":
    main()
