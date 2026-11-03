"""
apply_f7_manual_review: Interactive terminal helper for the manual
F7 pass.

Two modes:

  candidates  (default):  walk every row in f7_review_candidates.csv,
                          show the top of its extracted text plus its
                          repo URL, and prompt keep / exclude / skip.

  spotcheck   --n N:      draw N random unreviewed rows from
                          sample_manifest_final.csv (seeded so the
                          draw is reproducible), and prompt the same
                          way. This shows F7 was applied to all 400
                          rows, not only the 23 the heuristic flagged.


All decisions are written back into the WORKING manifest
(sample_manifest.csv), not the final snapshot. This matters:
finalize_confirmatory_sample.py regenerates sample_manifest_final.csv
from the working manifest on every run, so any review data that only
lived in the final snapshot would be silently wiped out on the next
reserve-promotion cycle. Writing into the working manifest makes the
decisions durable across re-finalization.

  - f7_manual_reviewed  = "true"
  - f7_manual_flag      = "ok" | "excluded_fork_mirror_stub"
  - f7_manual_note      = short free-text note (column added on first
                          run if not already present)

The script is idempotent and resumable: rows already marked
`f7_manual_reviewed == "true"` are skipped, so you can quit any time
with `q` and pick up where you left off.

Usage:
    venv/bin/python3 src/corpus/apply_f7_manual_review.py candidates \\
        [--freeze-date <name>] [--head-lines 40]

    venv/bin/python3 src/corpus/apply_f7_manual_review.py spotcheck \\
        --n 20 [--seed 402] [--freeze-date <name>] [--head-lines 40]

"""

from __future__ import annotations

import argparse
import csv
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    """Mirror finalize_confirmatory_sample.safe_name so text file paths
    can be reconstructed from the working manifest, which (unlike the
    final manifest) does not persist a text_file_path column."""
    return _SAFE_RE.sub("_", name).strip("_")


def _reset_tty() -> None:
    """Defensively restore cooked / line-buffered stdin.

    Other scripts in this project (confirmatory_cloner,
    confirmatory_preprocessor) put the tty into cbreak mode via
    pause_helper.py. If one of those crashes before its atexit
    handler runs, the terminal stays in raw mode and every input()
    call echoes ^M for Enter. Running `stty sane` at startup makes
    this script robust against a stuck tty.
    """
    if not sys.stdin.isatty():
        return
    try:
        subprocess.run(["stty", "sane"], check=False,
                       stdin=sys.stdin, timeout=2)
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

# None of these columns exist in a fresh sample_manifest.csv; they
# are added on demand so the working manifest keeps its original
# schema until the first manual review pass runs.
REVIEWED_COL = "f7_manual_reviewed"
FLAG_COL = "f7_manual_flag"
NOTE_COL = "f7_manual_note"

FLAG_OK = "ok"
FLAG_EXCLUDE = "excluded_fork_mirror_stub"


def load_manifest(path: Path) -> tuple[list[dict], list[str]]:
    with path.open() as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        fields = list(rdr.fieldnames or [])
    for col, default in ((REVIEWED_COL, "false"), (FLAG_COL, ""), (NOTE_COL, "")):
        if col not in fields:
            fields.append(col)
            for r in rows:
                r.setdefault(col, default)
    return rows, fields


def save_manifest(path: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            # Ensure every row has every field (defensive against
            # earlier partial writes / schema drift).
            for k in fields:
                r.setdefault(k, "")
            w.writerow(r)
    tmp.replace(path)


def show_head(text_path: Path, n_lines: int) -> None:
    if not text_path.exists():
        print(f"  !! text file missing: {text_path}")
        return
    with text_path.open(errors="replace") as f:
        for i, line in enumerate(f):
            if i >= n_lines:
                print(f"  ... (truncated at {n_lines} lines) ...")
                break
            print(f"  {line.rstrip()}")


def prompt_one(row: dict, frame_dir: Path, head_lines: int,
               index: int, total: int) -> tuple[str, str] | None:
    """Return (flag, note) or None if the user chose skip/quit-later."""
    print("\n" + "=" * 78)
    print(f"[{index}/{total}]  {row['ecosystem']:6s}  {row['package_name']}")
    print(f"  repo:      {row.get('repository_url', '')}")
    print(f"  words:     {row.get('word_count_post_clean', '')}"
          f"   pages: {row.get('pages_crawled', '')}")
    reasons = row.get("reasons")
    if reasons:
        print(f"  flagged:   {reasons}")
    text_rel = row.get("text_file_path", "")
    if not text_rel:
        # Working manifest has no text_file_path column; reconstruct
        # it the same way finalize_confirmatory_sample.py does.
        sname = safe_name(row["package_name"])
        text_rel = str((frame_dir / "text" / row["ecosystem"] / f"{sname}.txt")
                       .relative_to(ROOT))
    print(f"  text file: {text_rel}")
    print("-" * 78)
    show_head(ROOT / text_rel, head_lines)
    print("-" * 78)

    while True:
        choice = input("  [k]eep / [e]xclude / [s]kip / [q]uit  > ").strip().lower()
        if choice in ("k", "keep"):
            return FLAG_OK, ""
        if choice in ("e", "exclude"):
            note = input("  short note (e.g. 'fork of foo'): ").strip()
            return FLAG_EXCLUDE, note
        if choice in ("s", "skip"):
            return None
        if choice in ("q", "quit"):
            raise KeyboardInterrupt
        print("  ?? please type k, e, s, or q")


def run_review(candidates: list[dict], manifest_rows: list[dict],
               fields: list[str], manifest_path: Path,
               frame_dir: Path, head_lines: int) -> None:
    # Index manifest by (ecosystem, package_name) for O(1) lookup.
    idx = {(r["ecosystem"], r["package_name"]): r for r in manifest_rows}

    # Skip already-reviewed candidates so re-runs pick up mid-stream.
    pending = []
    for c in candidates:
        m = idx.get((c["ecosystem"], c["package_name"]))
        if m is None:
            print(f"  !! candidate not in final manifest, skipping: "
                  f"{c['ecosystem']} {c['package_name']}")
            continue
        if (m.get("f7_manual_reviewed") or "").lower() == "true":
            continue
        # Attach any candidate-only fields (reasons) for display.
        merged = dict(m)
        merged["reasons"] = c.get("reasons", "")
        pending.append(merged)

    if not pending:
        print("Nothing left to review.")
        return

    print(f"{len(pending)} row(s) pending review. "
          "Press q at any prompt to save + quit.")

    n_kept = n_excluded = 0
    try:
        for i, merged in enumerate(pending, 1):
            res = prompt_one(merged, frame_dir, head_lines, i, len(pending))
            if res is None:
                continue
            flag, note = res
            key = (merged["ecosystem"], merged["package_name"])
            manifest_row = idx[key]
            manifest_row["f7_manual_reviewed"] = "true"
            manifest_row["f7_manual_flag"] = flag
            manifest_row[NOTE_COL] = note
            if flag == FLAG_OK:
                n_kept += 1
            else:
                n_excluded += 1
            # Persist after each decision so a crash / kill doesn't
            # lose work.
            save_manifest(manifest_path, manifest_rows, fields)
    except KeyboardInterrupt:
        print("\n[quit] saving progress...")

    save_manifest(manifest_path, manifest_rows, fields)
    print(f"\nDone. kept={n_kept}  excluded={n_excluded}  "
          f"(remaining unreviewed candidates: "
          f"{sum(1 for c in candidates if (idx[(c['ecosystem'], c['package_name'])].get('f7_manual_reviewed') or '').lower() != 'true' and (c['ecosystem'], c['package_name']) in idx)})")


def load_candidates(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def draw_spotcheck(manifest_rows: list[dict], n: int, seed: int) -> list[dict]:
    pool = [r for r in manifest_rows
            if r.get("status") == "primary_ready"
            and (r.get("f7_manual_reviewed") or "").lower() != "true"]
    rng = random.Random(seed)
    n = min(n, len(pool))
    return rng.sample(pool, n)


def main() -> None:
    _reset_tty()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["candidates", "spotcheck"])
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--head-lines", type=int, default=40,
                    help="how many lines of the extracted text to preview")
    ap.add_argument("--n", type=int, default=20,
                    help="spotcheck mode: number of random rows to draw")
    ap.add_argument("--seed", type=int, default=402,
                    help="spotcheck mode: RNG seed for reproducibility")
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"missing: {manifest_path}")

    manifest_rows, fields = load_manifest(manifest_path)

    if args.mode == "candidates":
        cand_path = frame_dir / "f7_review_candidates.csv"
        if not cand_path.exists():
            raise SystemExit(f"missing: {cand_path}\n"
                             "run f7_review_candidates.py first.")
        candidates = load_candidates(cand_path)
        print(f"Loaded {len(candidates)} candidate(s) from {cand_path.name}.")
    else:
        candidates = draw_spotcheck(manifest_rows, args.n, args.seed)
        print(f"Drew {len(candidates)} random unreviewed row(s) "
              f"(seed={args.seed}).")

    run_review(candidates, manifest_rows, fields,
               manifest_path, frame_dir, args.head_lines)


if __name__ == "__main__":
    main()
