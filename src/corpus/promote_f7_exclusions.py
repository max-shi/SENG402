"""
promote_f7_exclusions: Close the loop after manual F7 review.

After running apply_f7_manual_review.py you may have marked some
primary_ready rows as `excluded_fork_mirror_stub`. This script:

  1. Reads sample_manifest_final.csv and counts F7 exclusions per
     ecosystem.
  2. Updates the working sample_manifest.csv:
       - Exclusion rows: status -> `primary_excluded_f7`
                          role   unchanged (still 'primary', for audit)
       - Next N reserves per ecosystem (in draw_order): role -> 'primary'
                          status -> 'primary_pending'
                          (a new promotion-source column records the
                          original excluded package name for audit)
  3. Prints the next commands to run: cloner + preprocessor +
     finalize + f7_review_candidates + apply_f7_manual_review, so you
     can iterate until 200 ready per ecosystem again.

The script is idempotent: re-running it after some promoted reserves
have already been processed only promotes MORE reserves if additional
exclusions have appeared since the last run. It never demotes an
already-promoted reserve.

Usage:
    venv/bin/python3 src/corpus/promote_f7_exclusions.py [--freeze-date <name>] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

STATUS_EXCLUDED = "primary_excluded_f7"
STATUS_PENDING = "primary_pending"
PROMO_SOURCE_COL = "f7_promotion_source"


def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open() as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        fields = list(rdr.fieldnames or [])
    return rows, fields


def save_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            for k in fields:
                r.setdefault(k, "")
            w.writerow(r)
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    final_path = frame_dir / "sample_manifest_final.csv"
    work_path = frame_dir / "sample_manifest.csv"
    for p in (final_path, work_path):
        if not p.exists():
            raise SystemExit(f"missing: {p}")

    final_rows, _ = load_csv(final_path)
    work_rows, work_fields = load_csv(work_path)

    # Ensure the audit column exists in the working manifest.
    if PROMO_SOURCE_COL not in work_fields:
        work_fields.append(PROMO_SOURCE_COL)
        for r in work_rows:
            r.setdefault(PROMO_SOURCE_COL, "")

    # 1. Collect F7 exclusions from the frozen final manifest.
    exclusions = [r for r in final_rows
                  if r.get("f7_manual_flag") == "excluded_fork_mirror_stub"]
    excl_keys = {(r["ecosystem"], r["package_name"]) for r in exclusions}
    excl_per_eco = Counter(r["ecosystem"] for r in exclusions)
    print(f"F7 exclusions in final manifest: {len(exclusions)}")
    for eco, n in sorted(excl_per_eco.items()):
        print(f"  {eco}: {n}")

    # 2. Update working manifest: mark exclusions.
    idx = {(r["ecosystem"], r["package_name"]): r for r in work_rows}
    newly_marked = 0
    for r in exclusions:
        w = idx.get((r["ecosystem"], r["package_name"]))
        if w is None:
            print(f"  !! excluded row not in working manifest: "
                  f"{r['ecosystem']} {r['package_name']}")
            continue
        if w["status"] != STATUS_EXCLUDED:
            w["status"] = STATUS_EXCLUDED
            newly_marked += 1
    print(f"Marked {newly_marked} row(s) with status={STATUS_EXCLUDED} "
          "in working manifest.")

    # 3. Count how many *more* reserves each ecosystem still needs.
    # A previous promotion run may already have moved some reserves;
    # count current primaries per ecosystem and top up to 200 +
    # exclusions_since (i.e. we always aim for 200 non-excluded primaries).
    #
    # Simpler and equivalent formulation: for each ecosystem, count how
    # many exclusions there are; how many reserves have already been
    # promoted (audit column non-empty); promote the difference.
    needed_per_eco: dict[str, int] = {}
    for eco, n_excl in excl_per_eco.items():
        already_promoted = sum(
            1 for r in work_rows
            if r["ecosystem"] == eco
            and r["role"] == "primary"
            and (r.get(PROMO_SOURCE_COL) or "")
        )
        needed_per_eco[eco] = max(0, n_excl - already_promoted)
    for eco, n in sorted(needed_per_eco.items()):
        print(f"  {eco}: need {n} fresh reserve(s) to promote")

    # 4. Promote reserves in draw_order, per ecosystem.
    reserves_by_eco: dict[str, list[dict]] = defaultdict(list)
    for r in work_rows:
        if r["role"] == "reserve" and r["status"] == "reserve_pending":
            reserves_by_eco[r["ecosystem"]].append(r)
    for eco in reserves_by_eco:
        reserves_by_eco[eco].sort(key=lambda r: int(r["draw_order"]))

    promoted = []
    # Round-robin: pair each unfulfilled exclusion with the next reserve.
    for eco, n in needed_per_eco.items():
        pool = reserves_by_eco.get(eco, [])
        if n > len(pool):
            print(f"  !! only {len(pool)} reserves available for {eco}, "
                  f"needed {n} — corpus will be short by {n - len(pool)}")
        # Which exclusions still need a replacement (i.e. no earlier
        # promoted reserve names them as source yet)?
        already_sources = {
            r.get(PROMO_SOURCE_COL, "") for r in work_rows
            if r["ecosystem"] == eco and r.get(PROMO_SOURCE_COL)
        }
        unmatched = [x for x in exclusions
                     if x["ecosystem"] == eco
                     and x["package_name"] not in already_sources]
        for reserve, exc in zip(pool[:n], unmatched[:n]):
            reserve["role"] = "primary"
            reserve["status"] = STATUS_PENDING
            reserve[PROMO_SOURCE_COL] = exc["package_name"]
            promoted.append((eco, reserve["package_name"], exc["package_name"]))

    print(f"\nPromoted {len(promoted)} reserve(s):")
    for eco, new, src in promoted:
        print(f"  {eco}: {src}  ->  {new}")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return

    save_csv(work_path, work_rows, work_fields)
    print(f"\nUpdated {work_path}")

    print("\nNext steps:")
    print(f"  1. Clone the new primaries:")
    print(f"     venv/bin/python3 src/corpus/confirmatory_cloner.py "
          f"--freeze-date {args.freeze_date}")
    print(f"  2. Preprocess them:")
    print(f"     venv/bin/python3 src/corpus/confirmatory_preprocessor.py "
          f"--freeze-date {args.freeze_date}")
    print(f"  3. Refreeze the final manifest:")
    print(f"     venv/bin/python3 src/corpus/finalize_confirmatory_sample.py "
          f"--freeze-date {args.freeze_date}")
    print(f"  4. Regenerate F7 candidates for the new rows only:")
    print(f"     venv/bin/python3 src/corpus/f7_review_candidates.py "
          f"--freeze-date {args.freeze_date}")
    print(f"     (existing manual flags on unchanged rows are preserved.)")
    print(f"  5. Review any new candidates and, if further exclusions,")
    print(f"     re-run this script.")


if __name__ == "__main__":
    main()
