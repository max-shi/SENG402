"""
sample_frame: Confirmatory corpus frame pull and seeded draw.

Implements the confirmatory sampling frame in
`RULES.md`. Runs the *frame-stage* portion
of the advance plan:

    1. Snapshot the ecosyste.ms frame for the selected registries
       (PyPI, Maven Central, and/or Hackage) on the freeze date.
    2. Apply frame-stage inclusion filters F1 (registry listing),
       F2 (license present), F3 (dependent_packages_count >= 5).
    3. Draw a seeded random sample of ~500 candidates per ecosystem
       (primary = first 200, reserve = remaining) using seed = 402.
    4. Write frame snapshots, sample manifest, and initialise the
       exclusion log.

Filters F4-F7 (docs reachable / min word count / English /
manual stub-fork-mirror review) are applied later in the pipeline by
the crawler / preprocessor / shortlist-review step, which append to
the same exclusion log.

Outputs (all under files/corpus/frame_<name>/):

    frame_python.jsonl.gz       The drawn packages only (500 per ecosystem,
                                primary + reserve), gzipped JSONL. Stored
                                rather than the full filtered frame
                                (which would be ~500MB for Maven Central)
                                to keep the artefact committable to git.
                                A reviewer wishing to draw a different
                                seed can regenerate the full frame from
                                ecosyste.ms via the endpoint and freeze
                                date recorded in frame_metadata.json.
    frame_java.jsonl.gz         Ditto.
    sample_manifest.csv         500 candidates per ecosystem, marked
                                primary/reserve, in draw order.
    exclusion_log.csv           Initialised; frame-stage exclusions
                                (F1-F3) are not individually logged
                                because the frame is enumerated with
                                a filter query, only individually
                                sampled packages that later fail
                                F4-F7 appear here.
    frame_metadata.json         Freeze date, seed, source registry
                                URLs, package counts, git commit,
                                reproducibility metadata.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests

# ---------------------------------------------------------------------------
# Configuration, locked to RULES.md
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

# ecosyste.ms registry names for the confirmatory ecosystems.
REGISTRIES = {
    "python":  "pypi.org",
    "java":    "repo1.maven.org",
    "haskell": "hackage.haskell.org",
}

# F3 threshold.
MIN_DEPENDENTS = 5

# Draw protocol.
DEFAULT_TARGET_N = 200
DEFAULT_OVERDRAW_FACTOR = 2.5   # -> ~500 candidates
DEFAULT_SEED = 402

API_BASE = "https://packages.ecosyste.ms/api/v1"
PER_PAGE = 500                  # ecosyste.ms allows up to 1000 but 500 is the sweet spot;
                                # per_page=1000 triggers 500s on deep pages under the
                                # dependent_packages_count sort. Empirically ~10s per page
                                # at per_page=500.
REQUEST_TIMEOUT = 180           # ecosyste.ms's dep-count-sorted queries can take 30-60s
RETRY_BACKOFF = [5, 15, 30, 60] # seconds between retry attempts; server needs recovery time

USER_AGENT = "seng402-corpus-frame/1.0 (research)"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get_json(session: requests.Session, url: str, params: dict) -> Any:
    """GET with retries and rate-limit awareness."""
    last_exc: Exception | None = None
    for attempt, wait in enumerate([0, *RETRY_BACKOFF]):
        if wait:
            time.sleep(wait)
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            # Respect rate-limit headers if we're getting close.
            remaining = int(resp.headers.get("x-ratelimit-remaining", "9999"))
            if remaining < 20:
                reset = int(resp.headers.get("x-ratelimit-reset", "0"))
                sleep_for = max(0, reset - int(time.time())) + 1
                log.warning("rate-limit remaining=%d, sleeping %ds", remaining, sleep_for)
                time.sleep(sleep_for)
            if resp.status_code == 429:
                # Rate-limited despite our best efforts.
                log.warning("429 from %s, backing off", url)
                continue
            if resp.status_code >= 500:
                log.warning("HTTP %s from %s, retrying", resp.status_code, url)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("attempt %d failed: %s", attempt + 1, exc)
    raise RuntimeError(f"GET {url} failed after retries: {last_exc}")


# ---------------------------------------------------------------------------
# Frame fetch
# ---------------------------------------------------------------------------

def fetch_frame(registry: str, min_dependents: int) -> Iterator[dict]:
    """
    Yield every package in `registry` whose `dependent_packages_count`
    is at least `min_dependents`.

    Uses the paginated list endpoint sorted by descending
    `dependent_packages_count`, and stops as soon as a page contains
    a package below the threshold.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    url = f"{API_BASE}/registries/{registry}/packages"
    page = 1
    total = 0
    while True:
        data = _get_json(session, url, {
            "per_page": PER_PAGE,
            "page": page,
            "sort": "dependent_packages_count",
            "order": "desc",
        })
        if not isinstance(data, list) or not data:
            log.info("[%s] page %d returned empty; stopping", registry, page)
            break

        stop = False
        for pkg in data:
            dep = pkg.get("dependent_packages_count") or 0
            if dep < min_dependents:
                stop = True
                break
            yield pkg
            total += 1

        log.info("[%s] page %d: %d packages, cumulative %d", registry, page, len(data), total)
        if stop:
            log.info("[%s] hit dependents<%d threshold; stopping", registry, min_dependents)
            break
        if len(data) < PER_PAGE:
            log.info("[%s] short page (%d<%d); reached end", registry, len(data), PER_PAGE)
            break
        page += 1


# ---------------------------------------------------------------------------
# Frame-stage filters (F1-F3)
# ---------------------------------------------------------------------------

def passes_frame_filters(pkg: dict, min_dependents: int) -> tuple[bool, str]:
    """
    Return (passes, reason). `reason` is one of `F1`, `F2`, `F3`, `OK`.

    F1: latest_release_number is non-empty (has at least one release).
    F2: licenses field is non-null.
    F3: dependent_packages_count >= min_dependents.

    F3 is already enforced by the sort-and-stop in fetch_frame, but we
    re-check defensively here.
    """
    if not pkg.get("latest_release_number"):
        return False, "F1"
    if not pkg.get("licenses") and not pkg.get("normalized_licenses"):
        return False, "F2"
    if (pkg.get("dependent_packages_count") or 0) < min_dependents:
        return False, "F3"
    return True, "OK"


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------

def seeded_draw(pool: list[dict], n_draw: int, seed: int) -> list[int]:
    """
    Return the indices of `n_draw` packages drawn without replacement
    from `pool`, using a deterministic Python stdlib Mersenne-Twister
    generator. Reproducible across runs and Python versions given the
    same seed and same input pool ordering.
    """
    if n_draw > len(pool):
        raise ValueError(f"draw size {n_draw} exceeds pool size {len(pool)}")
    rng = random.Random(seed)
    return rng.sample(range(len(pool)), k=n_draw)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

MANIFEST_COLS = [
    "draw_order", "role", "ecosystem", "package_name",
    "registry_url", "docs_url", "repository_url",
    "version_pinned", "first_release_date",
    "dependent_packages_count", "license_spdx",
    # Fields to be filled in downstream stages:
    "domain_tag", "domain_tag_source",
    "word_count_post_clean", "pages_crawled", "word_capped",
    "status",  # `primary_pending`, `primary_retained`, `primary_excluded`, `reserve_pending`, `reserve_retained`
]

EXCLUSION_COLS = [
    "package_name", "ecosystem", "draw_order",
    "stage", "filter_failed", "evidence", "timestamp",
]


def _license_spdx(pkg: dict) -> str:
    """Prefer normalized_licenses if available; fall back to licenses string."""
    norm = pkg.get("normalized_licenses") or []
    if norm:
        return ",".join(norm)
    return pkg.get("licenses") or ""


def _docs_url(pkg: dict) -> str:
    return pkg.get("documentation_url") or pkg.get("homepage") or ""


def write_frame_snapshot(out_dir: Path, ecosystem: str, packages: list[dict]) -> Path:
    """
    Persist the drawn packages' full ecosyste.ms records to a gzipped
    JSONL file. Only the drawn subset (primary + reserve) is written,
    not the entire filtered frame, so the file remains committable.
    """
    path = out_dir / f"frame_{ecosystem}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for pkg in packages:
            fh.write(json.dumps(pkg, ensure_ascii=False))
            fh.write("\n")
    log.info("wrote %s (%d drawn packages)", path, len(packages))
    return path


DOMAIN_COLS = ("domain_tag", "domain_tag_source")


def build_manifest_rows(
    ecosystem: str, drawn: list[dict], n_target: int,
    include_domain_cols: bool = True,
) -> list[dict]:
    rows = []
    for i, pkg in enumerate(drawn):
        rows.append({
            "draw_order": i,
            "role": "primary" if i < n_target else "reserve",
            "ecosystem": ecosystem,
            "package_name": pkg["name"],
            "registry_url": pkg.get("registry_url") or "",
            "docs_url": _docs_url(pkg),
            "repository_url": pkg.get("repository_url") or "",
            "version_pinned": pkg.get("latest_release_number") or "",
            "first_release_date": pkg.get("first_release_published_at") or "",
            "dependent_packages_count": pkg.get("dependent_packages_count") or 0,
            "license_spdx": _license_spdx(pkg),
            "domain_tag": "",
            "domain_tag_source": "",
            "word_count_post_clean": "",
            "pages_crawled": "",
            "word_capped": "",
            "status": "primary_pending" if i < n_target else "reserve_pending",
        })
    if not include_domain_cols:
        for r in rows:
            for col in DOMAIN_COLS:
                del r[col]
    return rows


def write_manifest(out_dir: Path, rows: list[dict],
                   include_domain_cols: bool = True) -> Path:
    path = out_dir / "sample_manifest.csv"
    cols = MANIFEST_COLS if include_domain_cols else [
        c for c in MANIFEST_COLS if c not in DOMAIN_COLS]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %s (%d rows)", path, len(rows))
    return path


def init_exclusion_log(out_dir: Path) -> Path:
    path = out_dir / "exclusion_log.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=EXCLUSION_COLS)
        w.writeheader()
    log.info("initialised %s", path)
    return path


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def write_metadata(
    out_dir: Path, freeze_date: str, seed: int,
    n_target: int, n_draw: int, min_dependents: int,
    frame_counts: dict[str, int],
) -> Path:
    meta = {
        "freeze_date": freeze_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "n_target_per_ecosystem": n_target,
        "n_draw_per_ecosystem": n_draw,
        "min_dependents": min_dependents,
        "registries": REGISTRIES,
        "api_base": API_BASE,
        "frame_counts_after_F1_F3": frame_counts,
        "git_commit": _git_commit(),
        "spec_reference": "RULES.md",
    }
    path = out_dir / "frame_metadata.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    log.info("wrote %s", path)
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_for_ecosystem(
    ecosystem: str, registry: str, out_dir: Path,
    n_target: int, n_draw: int, min_dependents: int, seed: int,
    include_domain_cols: bool = True,
) -> tuple[int, list[dict]]:
    """Fetch frame, filter, draw, and return (frame_size, manifest_rows)."""
    log.info("=== %s (registry=%s) ===", ecosystem, registry)

    # Dedupe by package name during collection. The ecosyste.ms API's sort
    # by dependent_packages_count is not stable across ties (many packages
    # share the same dep count), so pagination can surface the same package
    # on two consecutive pages. Without this dedup, the draw would sample
    # duplicates.
    seen_names: set[str] = set()
    frame: list[dict] = []
    dup_count = 0
    for pkg in fetch_frame(registry, min_dependents):
        ok, _reason = passes_frame_filters(pkg, min_dependents)
        if not ok:
            continue
        name = pkg["name"]
        if name in seen_names:
            dup_count += 1
            continue
        seen_names.add(name)
        frame.append(pkg)

    log.info(
        "[%s] frame after F1-F3 (deduped): %d packages (%d duplicates dropped)",
        ecosystem, len(frame), dup_count,
    )

    if len(frame) < n_draw:
        raise RuntimeError(
            f"[{ecosystem}] frame size {len(frame)} < required draw size {n_draw}. "
            f"Lower MIN_DEPENDENTS or reduce over-draw factor."
        )

    # Deterministic draw. Sort by name first for stable ordering across runs.
    frame.sort(key=lambda p: p["name"])
    indices = seeded_draw(frame, n_draw, seed)
    drawn = [frame[i] for i in indices]

    # Persist only the drawn subset (see write_frame_snapshot docstring).
    write_frame_snapshot(out_dir, ecosystem, drawn)

    rows = build_manifest_rows(ecosystem, drawn, n_target,
                               include_domain_cols=include_domain_cols)
    return len(frame), rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Confirmatory-corpus frame pull and seeded draw"
    )
    parser.add_argument(
        "--freeze-date", default=datetime.now(timezone.utc).strftime("%Y%m%d"),
        help="Freeze date YYYYMMDD (default: today, UTC). Determines output dir.",
    )
    parser.add_argument("--n-target", type=int, default=DEFAULT_TARGET_N)
    parser.add_argument(
        "--overdraw", type=float, default=DEFAULT_OVERDRAW_FACTOR,
        help="Multiplicative factor over n-target for the draw size (default 2.5).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--min-dependents", type=int, default=MIN_DEPENDENTS)
    parser.add_argument(
        "--ecosystems", nargs="+", default=list(REGISTRIES.keys()),
        choices=list(REGISTRIES.keys()),
        help="Which ecosystems to process.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Override output directory (default: files/corpus/frame_<freeze-date>/).",
    )
    parser.add_argument(
        "--no-domain-cols", action="store_true",
        help="Omit domain_tag/domain_tag_source manifest columns "
             "(7.8.5: the n=2000 extended frame carries no domain tags).",
    )
    args = parser.parse_args()

    n_draw = int(round(args.n_target * args.overdraw))
    out_dir = args.out_dir or (CORPUS_DIR / f"frame_{args.freeze_date}")
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("freeze_date=%s seed=%d n_target=%d n_draw=%d min_dependents=%d",
             args.freeze_date, args.seed, args.n_target, n_draw, args.min_dependents)
    log.info("output: %s", out_dir)

    all_rows: list[dict] = []
    frame_counts: dict[str, int] = {}
    for eco in args.ecosystems:
        registry = REGISTRIES[eco]
        size, rows = run_for_ecosystem(
            eco, registry, out_dir,
            args.n_target, n_draw, args.min_dependents, args.seed,
            include_domain_cols=not args.no_domain_cols,
        )
        frame_counts[eco] = size
        all_rows.extend(rows)

    write_manifest(out_dir, all_rows,
                   include_domain_cols=not args.no_domain_cols)
    init_exclusion_log(out_dir)
    write_metadata(
        out_dir, args.freeze_date, args.seed,
        args.n_target, n_draw, args.min_dependents,
        frame_counts,
    )

    log.info("done. manifest: %s", out_dir / "sample_manifest.csv")


if __name__ == "__main__":
    sys.exit(main())
