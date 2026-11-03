"""
pilot_docs_rerun: rebuild the pilot corpus from READMEs and docs folders.

The original pilot measured docstrings and Javadoc comments. This clones the
same libraries at the same pinned tags, then applies the main study's prose
extraction and word and language filters, so the two kinds of text can be
compared. Java and Python only. Nothing from the original pilot run is changed.

Outputs:
    files/raw/pilot_docs/<ecosystem>/<library>/
    files/preprocess/pilot_docs_rerun/libraries.csv  (LIWC-22 input)
    files/preprocess/pilot_docs_rerun/build_log.csv

Usage:
    venv/bin/python3 src/pilot/pilot_docs_rerun.py [--workers 6] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_preprocessor import (  # noqa: E402
    ENGLISH_MIN_FRACTION, WORD_CAP, WORD_MIN, apply_word_cap, english_fraction,
    extract_prose, find_prose_files, safe_name,
)

ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = Path(__file__).resolve().parent / "libraries"
CLONE_ROOT = ROOT / "files" / "raw" / "pilot_docs"
OUT_DIR = ROOT / "files" / "preprocess" / "pilot_docs_rerun"
CLONE_TIMEOUT_S = 1800


def load_libraries() -> list[dict]:
    libs = []
    for name in ("librariesJAVA.csv", "librariesPYTHON.csv"):
        with open(LIB_DIR / name, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, skipinitialspace=True):
                row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if row.get("name") and row.get("repo_url"):
                    row["ecosystem"] = row["ecosystem"].lower()
                    libs.append(row)
    return libs


def clone(lib: dict) -> dict:
    dest = CLONE_ROOT / lib["ecosystem"] / safe_name(lib["name"])
    if (dest / ".git").is_dir():
        return {"clone": "existing", "dest": dest}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    cmd = ["git", "clone", "--quiet", "--depth", "1"]
    if lib["git_tag"]:
        cmd += ["--branch", lib["git_tag"]]
    cmd += [lib["repo_url"], str(dest)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        return {"clone": "timeout", "dest": dest}
    if r.returncode:
        shutil.rmtree(dest, ignore_errors=True)
        return {"clone": "failed: " + r.stderr.strip().splitlines()[-1][:160], "dest": dest}
    return {"clone": "cloned", "dest": dest}


def build(lib: dict, cloned: dict) -> tuple[dict, dict | None]:
    log = {"library": lib["name"], "ecosystem": lib["ecosystem"], "git_tag": lib["git_tag"],
           "clone": cloned["clone"], "n_files": 0, "n_words": 0, "word_capped": False,
           "english_fraction": "", "status": "clone_failed"}
    if not cloned["clone"] in ("cloned", "existing"):
        return log, None
    files = find_prose_files(cloned["dest"])
    log["n_files"] = len(files)
    chunks, running = [], 0
    # Same early stop as the main study's preprocessor.
    for path in files:
        text = extract_prose(path)
        if text:
            chunks.append(text)
            running += len(text.split())
            if running > WORD_CAP * 2:
                break
    text, words, capped = apply_word_cap("\n\n".join(chunks))
    log.update(n_words=words, word_capped=capped)
    if words < WORD_MIN:
        log["status"] = "excluded_under_500_words"
        return log, None
    frac, _ = english_fraction(text)
    log["english_fraction"] = round(frac, 3)
    if frac < ENGLISH_MIN_FRACTION:
        log["status"] = "excluded_not_english"
        return log, None
    log["status"] = "included"
    row = {"library": lib["name"], "ecosystem": lib["ecosystem"], "domain": lib.get("domain", ""),
           "organisation": lib.get("organisation", ""), "n_files": len(files),
           "n_words": words, "text": text}
    return log, row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="First N libraries only, for testing.")
    args = ap.parse_args()

    libs = load_libraries()
    if args.limit:
        libs = libs[:args.limit]
    print(f"{len(libs)} libraries: "
          f"{pd.Series([l['ecosystem'] for l in libs]).value_counts().to_dict()}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        cloned = list(pool.map(clone, libs))

    logs, rows = [], []
    for i, (lib, c) in enumerate(zip(libs, cloned), 1):
        log, row = build(lib, c)
        logs.append(log)
        if row:
            rows.append(row)
        print(f"[{i}/{len(libs)}] {lib['ecosystem']}/{lib['name']}: {log['status']} "
              f"({log['n_files']} files, {log['n_words']} words) {log['clone'][:80]}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(logs).to_csv(OUT_DIR / "build_log.csv", index=False)
    pd.DataFrame(rows).to_csv(OUT_DIR / "libraries.csv", index=False)
    summary = pd.DataFrame(logs).groupby(["ecosystem", "status"]).size()
    print("\n" + summary.to_string())
    print(f"\nWrote {OUT_DIR / 'libraries.csv'}")


if __name__ == "__main__":
    main()
