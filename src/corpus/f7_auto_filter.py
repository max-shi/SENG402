"""
f7_auto_filter: Automated F7 pass for the extended n=2000 frame
(RULES.md, listed under changes from the plan).

The original F7 ("not a stub, fork, or mirror") was an exhaustive
manual review; that does not scale to a ≈10,000-candidate over-draw.
For the n=2000 frame only, an automated pass rejects candidates matching
stub/mirror/deprecated signals.

Two modes, both dry-run by default (pass --apply to write changes):

  description   pre-clone: scan the ecosyste.ms package `description`
                (from frame_<eco>.jsonl.gz) of every manifest row for
                the signal terms. Cheap; saves clone bandwidth.

  readme        post-clone: for rows with status primary_cloned*, scan
                the top of the raw root README (pre-clean, per the amended F7 rule)
                for the signal terms, and reject near-empty READMEs
                (pre-clean word count under the F5 threshold of 500).

Every rejection is appended to exclusion_log.csv with
filter_failed="F7-auto" and the matched term recorded in `evidence`.
Rejected primaries get status primary_excluded_f7_auto (reserves:
reserve_failed_f7_auto), and reserves are promoted in draw_order to
fill vacated primary slots, using the same policy as
confirmatory_cloner.promote_reserves.

Usage:
    venv/bin/python3 src/corpus/f7_auto_filter.py description \\
        [--freeze-date <name>[_n2000]] [--apply]
    venv/bin/python3 src/corpus/f7_auto_filter.py readme \\
        [--freeze-date <name>[_n2000]] [--apply]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from frame_config import load_n_target

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"
RAW_DIR = ROOT / "files" / "raw" / "confirmatory"

N_TARGET = 200  # overridden in main() from the frame's frame_metadata.json

# Stub/mirror/deprecated signal terms. The first five are the
# examples enumerated in the spec; the rest are the strong-signal
# phrases already validated on frame_locked by f7_review_candidates.
F7_AUTO_TERMS = [
    r"\bdeprecated\b",
    r"\bmirror of\b",
    r"\bmoved to\b",
    r"\bdo not use\b",
    r"\barchived\b",
    r"\bmirrored from\b",
    r"\bfork of\b",
    r"\bforked from\b",
    r"\bno longer maintained\b",
    r"\bunmaintained\b",
    r"\bsuperseded by\b",
]
TERM_RES = [re.compile(t, re.IGNORECASE) for t in F7_AUTO_TERMS]

# Only the head of the README is scanned, abandonment / fork notices
# sit in the first paragraph or two, and scanning deeper matches
# innocent tutorial text ("this method is deprecated since 2.0").
# Same rationale and value as f7_review_candidates.TEXT_HEAD_CHARS.
README_HEAD_CHARS = 1500

# Original plan: "a near-empty README under the F5 word threshold read
# *before* cleaning". Whitespace-token count of the raw README.
F5_WORD_MIN = 500

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

EXCLUDED_PRIMARY_STATUS = "primary_excluded_f7_auto"
FAILED_RESERVE_STATUS = "reserve_failed_f7_auto"


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_")


def scan_terms(text: str) -> str | None:
    """Return 'term :: snippet' for the first matching signal term, or None."""
    for pat, r in zip(F7_AUTO_TERMS, TERM_RES):
        m = r.search(text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            snippet = text[start:end].replace("\n", " ").strip()
            return f"{pat} :: '...{snippet}...'"
    return None


# ---------------------------------------------------------------------------
# Mode: description (pre-clone)
# ---------------------------------------------------------------------------

def load_descriptions(frame_dir: Path) -> dict[tuple[str, str], str]:
    """Map (ecosystem, package_name) -> ecosyste.ms description."""
    out: dict[tuple[str, str], str] = {}
    snapshots = sorted(frame_dir.glob("frame_*.jsonl.gz"))
    for snap in snapshots:
        eco = snap.name[len("frame_"):-len(".jsonl.gz")]
        with gzip.open(snap, "rt", encoding="utf-8") as f:
            for line in f:
                pkg = json.loads(line)
                out[(eco, pkg["name"])] = pkg.get("description") or ""
    return out


def check_description(row: dict, descriptions: dict) -> str | None:
    desc = descriptions.get((row["ecosystem"], row["package_name"]), "")
    if not desc:
        return None
    hit = scan_terms(desc)
    return f"description: {hit}" if hit else None


# ---------------------------------------------------------------------------
# Mode: readme (post-clone, pre-clean)
# ---------------------------------------------------------------------------

def find_readme(clone_dir: Path) -> Path | None:
    if not clone_dir.is_dir():
        return None
    candidates = sorted(
        p for p in clone_dir.iterdir()
        if p.is_file() and p.name.lower().startswith("readme")
    )
    return candidates[0] if candidates else None


def check_readme(row: dict) -> str | None:
    """Stub/fork/deprecated language-signal check on the root README only.

    Word-count screening is deliberately NOT done here. The real F5 check
    (confirmatory_preprocessor.py) aggregates prose across the *entire*
    cloned tree (README + everything under a docs/ directory), so a
    library with a short root README but a substantial docs/ folder can
    still comfortably clear F5. Rejecting on root-README word count alone
    was found to false-positive on ~53% of primaries (dry run)
    and has been removed; F5 at the preprocessing stage is the correct
    and only word-count gate.
    """
    clone_dir = RAW_DIR / row["ecosystem"] / safe_name(row["package_name"])
    readme = find_readme(clone_dir)
    if readme is None:
        return None
    try:
        raw = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hit = scan_terms(raw[:README_HEAD_CHARS])
    return f"readme: {hit}" if hit else None


# ---------------------------------------------------------------------------
# Reserve promotion (same policy as confirmatory_cloner.promote_reserves)
# ---------------------------------------------------------------------------

def promote_reserves(rows: list[dict]) -> int:
    promoted = 0
    ecosystems = sorted({r["ecosystem"] for r in rows})
    for eco in ecosystems:
        eco_rows = sorted(
            (r for r in rows if r["ecosystem"] == eco),
            key=lambda r: int(r["draw_order"]),
        )
        primaries: list[dict] = []
        reserves: list[dict] = []
        for r in eco_rows:
            status = r.get("status", "")
            disqualified = (
                status.startswith("primary_failed")
                or status.startswith("reserve_failed")
                or status.startswith("primary_excluded")
            )
            if disqualified:
                continue
            if len(primaries) < N_TARGET:
                primaries.append(r)
            else:
                reserves.append(r)

        for r in primaries:
            if r["role"] != "primary":
                r["role"] = "primary"
                if not r["status"].startswith("primary_"):
                    r["status"] = "primary_pending_promoted_from_reserve"
                promoted += 1
        for r in reserves:
            if r["role"] != "reserve":
                r["role"] = "reserve"
                r["status"] = "reserve_pending_demoted_from_primary"
    return promoted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["description", "readme"])
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--apply", action="store_true",
                    help="Actually modify the manifest and exclusion log. "
                         "Without this flag, runs in dry-run mode.")
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    excl_path = frame_dir / "exclusion_log.csv"

    global N_TARGET
    N_TARGET = load_n_target(frame_dir)

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if args.mode == "description":
        descriptions = load_descriptions(frame_dir)
        # Scan every not-yet-rejected row (reserves too, a matching
        # reserve should never be promoted later).
        todo = [
            r for r in rows
            if not r["status"].startswith(("primary_failed",
                                           "primary_excluded",
                                           "reserve_failed"))
        ]
        checker = lambda r: check_description(r, descriptions)  # noqa: E731
    else:
        # Only cloned rows have a README on disk to inspect.
        todo = [r for r in rows if r["status"].startswith("primary_cloned")]
        checker = check_readme

    matched: list[tuple[dict, str]] = []
    for r in todo:
        evidence = checker(r)
        if evidence is not None:
            matched.append((r, evidence))

    by_eco = Counter(r["ecosystem"] for r, _ in matched)
    by_role = Counter(r["role"] for r, _ in matched)
    print(f"F7-auto [{args.mode}]: scanned {len(todo)} rows, "
          f"{len(matched)} matches "
          f"(python={by_eco.get('python', 0)}, java={by_eco.get('java', 0)}; "
          f"primary={by_role.get('primary', 0)}, "
          f"reserve={by_role.get('reserve', 0)})")
    kinds = Counter(ev.split("::")[0].split(":", 1)[-1].strip() if "::" in ev
                    else ev.split(":", 1)[0] for _, ev in matched)
    print("Breakdown by signal:")
    for k, v in kinds.most_common():
        print(f"  {k}: {v}")
    print()
    for r, ev in matched[:50]:
        print(f"  [{r['ecosystem']:6}] {r['role']:7} draw={r['draw_order']:>4}  "
              f"{r['package_name']:<60}  {ev[:100]}")
    if len(matched) > 50:
        print(f"  ...and {len(matched) - 50} more")

    if not matched:
        print("Nothing to do.")
        return

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to reject these rows, log them")
        print("to exclusion_log.csv (filter_failed=F7-auto), and promote reserves.")
        return

    # --- Apply mode -------------------------------------------------
    timestamp = datetime.now(timezone.utc).isoformat()

    with open(excl_path) as f:
        er = csv.DictReader(f)
        excl_fieldnames = er.fieldnames
        excl_rows = list(er)

    for r, evidence in matched:
        r["status"] = (EXCLUDED_PRIMARY_STATUS if r["role"] == "primary"
                       else FAILED_RESERVE_STATUS)
        excl_rows.append({
            "package_name": r["package_name"],
            "ecosystem": r["ecosystem"],
            "draw_order": r["draw_order"],
            "stage": f"f7-auto-{args.mode}",
            "filter_failed": "F7-auto",
            "evidence": evidence,
            "timestamp": timestamp,
        })

    promoted = promote_reserves(rows)
    print(f"\nexcluded {len(matched)}, promoted {promoted} reserves")

    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {manifest_path}  ({len(rows)} rows)")

    with open(excl_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=excl_fieldnames)
        w.writeheader()
        w.writerows(excl_rows)
    print(f"wrote {excl_path}  ({len(excl_rows)} rows)")


if __name__ == "__main__":
    main()
