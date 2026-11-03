"""
rq3_select_generation_subset: Seeded n=100/ecosystem draw for the RQ3
generation run.

**Deviation from the RQ3 plan, logged here per the
project's deviation-logging convention.** The RQ3 plan originally resolved
"full corpus reuse, no new draw" specifically to avoid reopening a
selection-bias question. That decision is being revisited, not because
it was wrong, but to trade
some of that full-corpus power for a smaller, cost-cheaper, *symmetric*
n=100/ecosystem design instead of the asymmetric 197 Python / 127 Java
ready pools (see rq3_extract_java.py's monorepo-scoping fix for
why Java's ready count is 127, not the previously-reported 160). Equal n
per ecosystem is a real methodological plus for a paired cross-ecosystem
comparison, not just a cost lever, it removes any question of whether an
observed Java-vs-Python asymmetry in the results is partly an artefact of
unequal group sizes.

This does NOT re-litigate the RQ3 plan's actual concern (a subset draw reopening
domain-selection bias): the draw below is uniform-random over each
ecosystem's already-extracted `ready` pool, with **no stratification by
domain, size, or any other covariate**, same non-stratification principle
already used for the main confirmatory frame ("the confirmatory
corpus is *not* stratified by domain at draw time"). It draws from
libraries that already successfully passed extraction, not from the raw
400, narrower population than the main frame, but the draw *within* that
population is unbiased in the same sense.

Method (mirrors sample_frame.py's seeded_draw exactly, for convention
consistency): stdlib `random.Random(seed)`, deterministic across runs and
Python versions given the same seed and same (alphabetically-sorted, not
log-file-order-dependent) input pool. Seed = 402, reused from the
project's established convention rather than a fresh one, since
there's no reason for this draw to use a different seed than every other
one in this project, reuse is a deliberate choice, not an oversight.

**Later: further scoped down to n=50/ecosystem**
(from the n=100/ecosystem decision above), purely for cost: the n=100
estimate was over budget. This is a cost-only revision, not a new methodological
call: same seed, same uniform-random no-stratification method, just a
smaller `--n`. Output file name is derived from `--n`
(`generation_subset_n{N}.csv`), so `generation_subset_n100.csv` is left
on disk as superseded history rather than overwritten, the current
authoritative file for the actual run is `generation_subset_n50.csv`.

Output: files/corpus/rq3/generation_subset_n{N}.csv, every `ready`
library in both ecosystems (324 rows total), with a `selected` column
(true for the N+N drawn, false for the remainder, which stays
available as a documented reserve pool, same shape as the main frame's exclusion
log, nothing is deleted, the non-selected libraries remain fully
extracted on disk, just not drawn for the generation spend).

Usage:
    venv/bin/python3 src/generation/rq3_select_generation_subset.py --n 50
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected"
    / "sample_manifest_final_corrected.csv"
)
EXTRACT_LOGS = {
    "python": ROOT / "files" / "corpus" / "rq3" / "extract_log_python.csv",
    "java": ROOT / "files" / "corpus" / "rq3" / "extract_log_java.csv",
}
OUT_DIR = ROOT / "files" / "corpus" / "rq3"

SEED = 402
DEFAULT_N_PER_ECOSYSTEM = 100

OUT_COLS = ["ecosystem", "package_name", "selected", "draw_seed", "draw_note"]


def canonical_names(ecosystem: str) -> set[str]:
    with open(MANIFEST) as f:
        return {
            r["package_name"] for r in csv.DictReader(f)
            if r["ecosystem"] == ecosystem
        }


def ready_pool(ecosystem: str) -> list[str]:
    """Every package_name with status=ready in the (latest-row-wins)
    extract log, restricted to the canonical 400 manifest, returned in a
    fixed alphabetical order, never log-file row order, which isn't
    guaranteed stable across re-runs and would silently change the draw."""
    names_in_manifest = canonical_names(ecosystem)
    latest: dict[str, dict] = {}
    with open(EXTRACT_LOGS[ecosystem]) as f:
        for row in csv.DictReader(f):
            latest[row["package_name"]] = row
    ready = [
        name for name, row in latest.items()
        if name in names_in_manifest and row["status"] == "ready"
    ]
    return sorted(ready)


def seeded_draw(pool: list[str], n_draw: int, seed: int) -> set[str]:
    """Same pattern as sample_frame.py's seeded_draw: stdlib
    random.Random(seed).sample over a fixed-order pool, deterministic."""
    if n_draw > len(pool):
        raise ValueError(f"draw size {n_draw} exceeds pool size {len(pool)}")
    rng = random.Random(seed)
    idx = rng.sample(range(len(pool)), k=n_draw)
    return {pool[i] for i in idx}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--n", type=int, default=DEFAULT_N_PER_ECOSYSTEM,
        help="Libraries to draw per ecosystem (default: "
             f"{DEFAULT_N_PER_ECOSYSTEM}). Output file name is derived "
             "from this value.",
    )
    args = ap.parse_args()
    n_per_ecosystem = args.n
    out_path = OUT_DIR / f"generation_subset_n{n_per_ecosystem}.csv"

    rows = []
    for eco in ("python", "java"):
        pool = ready_pool(eco)
        selected = seeded_draw(pool, n_per_ecosystem, SEED)
        print(f"{eco}: ready pool={len(pool)}, drew {len(selected)} "
              f"(seed={SEED})")
        for name in pool:
            rows.append({
                "ecosystem": eco,
                "package_name": name,
                "selected": "true" if name in selected else "false",
                "draw_seed": SEED,
                "draw_note": (
                    "uniform random, no stratification, "
                    "random.Random(seed).sample over sorted ready pool"
                ),
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(rows)

    n_selected = sum(1 for r in rows if r["selected"] == "true")
    print(f"\nwrote {len(rows)} rows ({n_selected} selected, "
          f"{len(rows) - n_selected} reserve) to {out_path}")


if __name__ == "__main__":
    main()
