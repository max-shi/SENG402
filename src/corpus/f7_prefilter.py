"""
f7_prefilter: Pre-crawl F7 pass for obviously-junk name patterns.

F7 in RULES.md is "not a stub, fork, or mirror". Most of that check is
better performed post-crawl (when the actual documentation text is
available for inspection). But three name patterns are ~100% junk
without needing to look at the docs, and pre-filtering them saves
crawler bandwidth:

    1. `*-parent`, `*-bom`, `*-dependencies` (case-insensitive suffix
       match on the artifact segment), Maven metapackages that are
       just dependency-aggregators with no real code or prose.
    2. `com.ibm.websphere.appserver.features:*`, IBM WebSphere
       proprietary feature bundles.
    3. `org.webjars.bower:*`, Bower packages republished as jars;
       docs are auto-generated wrappers.

The helper runs in dry-run mode by default (prints matches only, no
changes to disk). Pass `--apply` to actually remove them from
`primary`, promote the next reserves (in draw_order) to fill the
vacated slots, and append exclusion rows to exclusion_log.csv.

Usage:
    python3 src/corpus/f7_prefilter.py [--freeze-date <name>] [--apply]
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from frame_config import load_n_target

ROOT = Path(__file__).resolve().parents[2]
N_TARGET = 200  # overridden in main() from the frame's frame_metadata.json

# Suffix patterns on the *artifact* segment of a Maven coordinate
# (i.e. the part after the last ':', or the whole name for PyPI).
METAPKG_SUFFIXES = ("-parent", "-bom", "-dependencies")

# Group prefixes for Maven coordinates ("group:artifact").
GROUP_PREFIXES = (
    "com.ibm.websphere.appserver.features:",
    "org.webjars.bower:",
)


def _artifact_of(name: str) -> str:
    """Return the artifact segment of a Maven coordinate, or name itself."""
    return name.rsplit(":", 1)[-1]


def _matches_f7_prefilter(name: str) -> str | None:
    """Return the matching rule label, or None if the name passes."""
    lower = name.lower()
    for pref in GROUP_PREFIXES:
        if lower.startswith(pref):
            return f"group-prefix:{pref}"
    art = _artifact_of(lower)
    for suf in METAPKG_SUFFIXES:
        if art.endswith(suf):
            return f"artifact-suffix:{suf}"
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--freeze-date",
        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually modify the manifest and exclusion log. "
             "Without this flag, runs in dry-run mode.",
    )
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    excl_path = frame_dir / "exclusion_log.csv"

    global N_TARGET
    N_TARGET = load_n_target(frame_dir)

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    # Identify primary rows matching the pre-filter rules.
    matched: list[tuple[dict, str]] = []
    for r in all_rows:
        if r["role"] != "primary":
            continue
        rule = _matches_f7_prefilter(r["package_name"])
        if rule is not None:
            matched.append((r, rule))

    # Report.
    by_eco = Counter(r["ecosystem"] for r, _ in matched)
    print(f"F7 pre-filter matches: {len(matched)} primary rows "
          f"({', '.join(f'{eco}={n}' for eco, n in sorted(by_eco.items()))})")
    print()
    for r, rule in matched:
        print(f"  [{r['ecosystem']:6}] draw={r['draw_order']:3}  "
              f"{r['package_name']:<70}  {rule}")

    if not matched:
        print("Nothing to do.")
        return

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to remove these from primary,")
        print("promote the next reserves in draw order to fill the vacated slots,")
        print("and append exclusion rows to exclusion_log.csv.")
        return

    # --- Apply mode -------------------------------------------------
    timestamp = datetime.now(timezone.utc).isoformat()
    matched_keys = {(r["ecosystem"], r["draw_order"]) for r, _ in matched}
    rule_by_key = {(r["ecosystem"], r["draw_order"]): rule for r, rule in matched}

    with open(excl_path) as f:
        er = csv.DictReader(f)
        excl_fieldnames = er.fieldnames
        excl_rows = list(er)

    new_rows: list[dict] = []
    ecosystems = sorted({r["ecosystem"] for r in all_rows})
    for eco in ecosystems:
        eco_rows = [r for r in all_rows if r["ecosystem"] == eco]
        eco_rows.sort(key=lambda r: int(r["draw_order"]))
        kept: list[dict] = []
        for r in eco_rows:
            key = (r["ecosystem"], r["draw_order"])
            if key in matched_keys:
                excl_rows.append({
                    "package_name": r["package_name"],
                    "ecosystem": eco,
                    "draw_order": r["draw_order"],
                    "stage": "f7-prefilter",
                    "filter_failed": "F7",
                    "evidence": rule_by_key[key],
                    "timestamp": timestamp,
                })
                continue
            kept.append(r)

        # Re-role: first N_TARGET kept rows are primary, rest are reserve.
        promoted = 0
        for i, r in enumerate(kept):
            new_role = "primary" if i < N_TARGET else "reserve"
            old_role = r["role"]
            if new_role != old_role:
                r["status"] = f"{new_role}_pending_promoted_from_{old_role}"
                promoted += 1
            else:
                r["status"] = f"{new_role}_pending"
            r["role"] = new_role
        new_rows.extend(kept)
        n_excl_this_eco = sum(1 for r, _ in matched if r["ecosystem"] == eco)
        print(f"[{eco}] excluded {n_excl_this_eco}, promoted {promoted} reserves")

    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(new_rows)
    print(f"wrote {manifest_path}  ({len(new_rows)} rows)")

    with open(excl_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=excl_fieldnames)
        w.writeheader()
        w.writerows(excl_rows)
    print(f"wrote {excl_path}  ({len(excl_rows)} rows)")

    # Verify.
    print("\n--- verify ---")
    per = Counter((r["ecosystem"], r["role"]) for r in new_rows)
    for k, v in sorted(per.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
