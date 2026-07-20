"""
confirmatory_cloner — Acquire source for the confirmatory sample via git clone.

Reads files/corpus/frame_YYYYMMDD/sample_manifest.csv (§7.6). For each
primary row it attempts:

    git clone --depth 1 --branch <tag> <repository_url>
        into  files/raw/confirmatory/<ecosystem>/<safe_name>/

The tag is derived from `version_pinned` with several format fallbacks,
tried in order until one succeeds. If none succeed the default branch
HEAD is used and the fallback is noted in the clone log.

Repositories that cannot be cloned (URL empty / non-git-URL / clone
failure) are logged as F4 exclusions and reserves are promoted (in
draw_order) to fill vacated primary slots. Newly promoted primaries
are then processed in a follow-up pass; the loop repeats until either
no new failures occur or the reserve pool is exhausted.

The manifest is updated with:
    status           primary_cloned | primary_failed_f4 | reserve_pending | ...
    pages_crawled    number of documentation-bearing files found in the clone
                     (README*, files under docs/**, doc/**, *.md, *.rst)
    commit_sha       resolved commit SHA of the cloned working tree
    (existing        columns retained; word_count_post_clean and word_capped
     columns)        remain empty here — the preprocessor fills them.

Outputs:

    files/raw/confirmatory/{python,java}/<pkg>/     # git clones
    files/corpus/frame_YYYYMMDD/clone_log.csv       # per-library outcome
    files/corpus/frame_YYYYMMDD/exclusion_log.csv   # appended
    files/corpus/frame_YYYYMMDD/sample_manifest.csv # updated in-place

Usage:
    python3 src/corpus/confirmatory_cloner.py [--freeze-date YYYYMMDD]
                                              [--lang java|python|all]
                                              [--libraries START-END]
                                              [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Reuse the pilot's pause helper. It lives in the sibling crawl-clone dir
# rather than in this package, so we splice its path onto sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawl-clone"))
from pause_helper import PauseController  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"
RAW_DIR = ROOT / "files" / "raw" / "confirmatory"

N_TARGET = 200
CLONE_TIMEOUT_SEC = 300           # 5 min per clone
GIT_HOSTS_ALLOW = (
    "github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "gitee.com",
    "sourceforge.net",
)
# Substrings that reliably indicate the URL isn't a plain git repo.
GIT_URL_REJECT_SUBSTRINGS = (
    "svn.", "/svn/", "?p=",       # SVN / gitweb interfaces
    "gitbox.apache.org",          # Apache's gitweb (browser URL, not clone URL)
    "wiki.", "/wiki/",            # wikis
    "readthedocs.io", "readthedocs.org",
    "appdoc.app",                 # Javadoc aggregator
    "central.sonatype.com",       # Maven Central browse page
    "pypi.org",                   # PyPI project page
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL / tag / name helpers
# ---------------------------------------------------------------------------

def is_clonable_url(url: str) -> bool:
    """Cheap heuristic: could this URL plausibly be cloned by `git clone`?"""
    if not url or url.strip().lower() in {"", "private", "none"}:
        return False
    u = url.strip().lower()
    if not (u.startswith("http://") or u.startswith("https://") or u.startswith("git@")):
        return False
    for bad in GIT_URL_REJECT_SUBSTRINGS:
        if bad in u:
            return False
    # Whitelisted hosts always pass; other .git URLs also pass.
    if any(host in u for host in GIT_HOSTS_ALLOW):
        return True
    if u.endswith(".git"):
        return True
    # Unknown host without .git: likely not cloneable. Reject conservatively.
    return False


def tag_candidates(version: str) -> list[str]:
    """
    Return an ordered list of git-tag strings to try for `version`.
    Common conventions: v1.2.3, 1.2.3, release-1.2.3, release/1.2.3,
    v1.2.3-release. Empty version returns an empty list (default branch
    only).
    """
    v = (version or "").strip()
    if not v:
        return []
    cand = [f"v{v}", v, f"release-{v}", f"release/{v}", f"{v}-release"]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in cand:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    """Filesystem-safe rendering of a package name."""
    return _SAFE_RE.sub("_", name).strip("_")


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Optional[Path] = None,
         timeout: int = CLONE_TIMEOUT_SEC) -> tuple[int, str]:
    """
    Run a git command, return (returncode, combined output).

    Auth prompts are disabled (GIT_TERMINAL_PROMPT=0, GIT_ASKPASS,
    SSH_ASKPASS) so private / deleted / auth-required repos fail
    immediately instead of hanging on stdin. Subprocess.timeout with
    Popen so the git process group is terminated on timeout.
    """
    import os
    import signal
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "/bin/echo"
    env["SSH_ASKPASS"] = "/bin/echo"
    env["DISPLAY"] = ""
    # Also stop git from using the credential helper (which can prompt via
    # keychain on macOS).
    args_with_config = ["-c", "credential.helper=", *args]

    try:
        proc = subprocess.Popen(
            ["git", *args_with_config],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,   # new process group so we can kill it
        )
        try:
            out, err = proc.communicate(timeout=timeout)
            return proc.returncode, (out + err).strip()
        except subprocess.TimeoutExpired:
            # Kill the whole process group (git may spawn helpers).
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                out, err = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                out, err = "", ""
            return 124, f"timeout after {timeout}s; killed"
    except FileNotFoundError:
        return 127, "git executable not found"


def try_clone(repo_url: str, dest: Path, version: str) -> dict:
    """
    Attempt to clone `repo_url` into `dest`, first trying each tag
    candidate derived from `version`, then falling back to the default
    branch.

    Returns a dict with keys:
        cloned       bool
        tag_used     str | None       (None means default branch HEAD)
        strategy     'tag' | 'default-branch' | 'failed'
        error        str              (empty on success)
        attempts     list[str]        (tags tried, in order)
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Skip if already cloned; the existing clone stands.
    if dest.is_dir() and (dest / ".git").is_dir():
        return {
            "cloned": True, "tag_used": "existing",
            "strategy": "existing", "error": "",
            "attempts": [],
        }

    attempts: list[str] = []

    # 1. Tagged clones.
    for tag in tag_candidates(version):
        attempts.append(tag)
        code, out = _git([
            "clone", "--depth", "1", "--single-branch",
            "--branch", tag, repo_url, str(dest),
        ])
        if code == 0 and (dest / ".git").is_dir():
            return {
                "cloned": True, "tag_used": tag,
                "strategy": "tag", "error": "",
                "attempts": attempts,
            }
        # Clean up partial clone before trying next candidate.
        _rmtree_if_exists(dest)

    # 2. Default-branch fallback.
    code, out = _git([
        "clone", "--depth", "1", "--single-branch",
        repo_url, str(dest),
    ])
    if code == 0 and (dest / ".git").is_dir():
        return {
            "cloned": True, "tag_used": None,
            "strategy": "default-branch", "error": "",
            "attempts": attempts,
        }
    _rmtree_if_exists(dest)

    return {
        "cloned": False, "tag_used": None,
        "strategy": "failed", "error": out[:400],
        "attempts": attempts,
    }


def _rmtree_if_exists(path: Path) -> None:
    if path.exists():
        # Use git clean-friendly rm; shutil handles read-only files.
        import shutil, stat
        def _onerror(func, p, exc_info):
            try:
                Path(p).chmod(stat.S_IWRITE)
                func(p)
            except Exception:
                pass
        shutil.rmtree(path, onerror=_onerror)


def commit_sha(dest: Path) -> str:
    code, out = _git(["rev-parse", "HEAD"], cwd=dest, timeout=15)
    return out if code == 0 else ""


# ---------------------------------------------------------------------------
# Doc-file counting (for manifest `pages_crawled`)
# ---------------------------------------------------------------------------

_DOC_EXT = {".md", ".rst", ".txt", ".adoc", ".asciidoc"}
_DOC_DIR_NAMES = {"docs", "doc", "documentation"}


def count_doc_files(clone_dir: Path) -> int:
    """Count README* and doc-bearing files inside `clone_dir`."""
    if not clone_dir.is_dir():
        return 0
    n = 0
    for path in clone_dir.rglob("*"):
        # Skip .git contents.
        if ".git" in path.parts:
            continue
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.startswith("readme"):
            n += 1
            continue
        # Files under a docs/ (or doc/, documentation/) directory, any depth.
        parts_lower = [p.lower() for p in path.parts]
        if any(d in parts_lower for d in _DOC_DIR_NAMES):
            if path.suffix.lower() in _DOC_EXT or name == "index.rst":
                n += 1
                continue
    return n


# ---------------------------------------------------------------------------
# Manifest / exclusion-log I/O
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[list[str], list[dict]]:
    with open(path) as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def save_manifest(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    # Ensure required columns present.
    for col in ("commit_sha",):
        if col not in fieldnames:
            fieldnames.append(col)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def load_exclusion_log(path: Path) -> tuple[list[str], list[dict]]:
    with open(path) as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def save_exclusion_log(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Reserve promotion
# ---------------------------------------------------------------------------

def promote_reserves(rows: list[dict]) -> int:
    """
    In-place: for each ecosystem, ensure the first N_TARGET rows in
    draw_order (whose status is not `primary_failed_*`) are `role=primary`;
    the rest are `role=reserve`. Returns the number of promotions applied.
    """
    promoted = 0
    for eco in ("python", "java"):
        eco_rows = sorted(
            (r for r in rows if r["ecosystem"] == eco),
            key=lambda r: int(r["draw_order"]),
        )
        # A row is "eligible" for a primary slot if it hasn't failed.
        primaries: list[dict] = []
        reserves: list[dict] = []
        for r in eco_rows:
            status = r.get("status", "")
            # A row is disqualified if it has failed any filter (F4-F6)
            # or been manually excluded post-crawl (F7). Any of these
            # statuses means the row cannot occupy a primary slot and
            # a reserve must be promoted in its place.
            disqualified = (
                status.startswith("primary_failed")
                or status.startswith("reserve_failed")
                or status.startswith("primary_excluded")
            )
            if disqualified:
                continue  # excluded — leave status as-is
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
# Main processing
# ---------------------------------------------------------------------------

def process_primaries(
    rows: list[dict],
    excl_rows: list[dict],
    log_writer: csv.DictWriter,
    ecosystems: Iterable[str],
    pause: PauseController,
    lib_range: Optional[tuple[int, int]] = None,
    dry_run: bool = False,
) -> int:
    """
    Process all rows currently marked `role=primary, status=primary_pending*`.
    Returns the number of new F4 exclusions logged this pass.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    new_failures = 0

    # Snapshot the primary set NOW so promotion during the pass doesn't
    # cause us to skip newly promoted rows (we'll pick them up in the next
    # outer-loop iteration).
    to_process = [
        r for r in rows
        if r["ecosystem"] in ecosystems
        and r["role"] == "primary"
        and r["status"].startswith("primary_pending")
    ]

    if lib_range is not None:
        start, end = lib_range
        to_process = to_process[start - 1:end]

    total = len(to_process)
    log.info("processing %d primaries in this pass (ecosystems=%s)",
             total, ",".join(ecosystems))

    for i, row in enumerate(to_process, 1):
        pause.check()
        pkg = row["package_name"]
        eco = row["ecosystem"]
        repo = row.get("repository_url", "").strip()
        ver = row.get("version_pinned", "").strip()

        log.info("[%d/%d] %s  (%s)  repo=%s  version=%s",
                 i, total, pkg, eco, repo or "(none)", ver or "(none)")

        # F4 pre-flight: URL must be clonable.
        if not is_clonable_url(repo):
            reason = "non-git-url" if repo else "empty-repository_url"
            log.warning("  SKIP: %s  (%s)", reason, repo or "")
            row["status"] = "primary_failed_f4"
            excl_rows.append({
                "package_name": pkg, "ecosystem": eco,
                "draw_order": row["draw_order"],
                "stage": "clone", "filter_failed": "F4",
                "evidence": f"repository_url={repo or '(empty)'}: {reason}",
                "timestamp": timestamp,
            })
            log_writer.writerow({
                "timestamp": timestamp, "package_name": pkg, "ecosystem": eco,
                "repository_url": repo, "version_pinned": ver,
                "strategy": "skip", "tag_used": "", "commit_sha": "",
                "doc_file_count": 0, "status": "F4_skip",
                "error": reason, "attempts": "",
            })
            new_failures += 1
            continue

        dest = RAW_DIR / eco / safe_name(pkg)

        if dry_run:
            log.info("  [dry-run] would clone → %s", dest)
            continue

        result = try_clone(repo, dest, ver)

        if not result["cloned"]:
            log.warning("  FAILED: %s  attempts=%s",
                        result["error"], ",".join(result["attempts"]))
            row["status"] = "primary_failed_f4"
            excl_rows.append({
                "package_name": pkg, "ecosystem": eco,
                "draw_order": row["draw_order"],
                "stage": "clone", "filter_failed": "F4",
                "evidence": f"git-clone failed: {result['error'][:200]}",
                "timestamp": timestamp,
            })
            log_writer.writerow({
                "timestamp": timestamp, "package_name": pkg, "ecosystem": eco,
                "repository_url": repo, "version_pinned": ver,
                "strategy": result["strategy"],
                "tag_used": result["tag_used"] or "",
                "commit_sha": "", "doc_file_count": 0,
                "status": "F4_clone_failed", "error": result["error"][:400],
                "attempts": ",".join(result["attempts"]),
            })
            new_failures += 1
            continue

        # Success.
        sha = commit_sha(dest)
        n_docs = count_doc_files(dest)
        row["commit_sha"] = sha
        row["pages_crawled"] = str(n_docs)
        row["status"] = "primary_cloned"
        if result["strategy"] == "default-branch":
            row["status"] = "primary_cloned_default_branch"
        log.info("  OK  strategy=%s  tag=%s  sha=%s  docs=%d",
                 result["strategy"], result["tag_used"] or "-",
                 sha[:10] or "-", n_docs)
        log_writer.writerow({
            "timestamp": timestamp, "package_name": pkg, "ecosystem": eco,
            "repository_url": repo, "version_pinned": ver,
            "strategy": result["strategy"],
            "tag_used": result["tag_used"] or "",
            "commit_sha": sha, "doc_file_count": n_docs,
            "status": "cloned", "error": "",
            "attempts": ",".join(result["attempts"]),
        })

    return new_failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

CLONE_LOG_COLS = [
    "timestamp", "package_name", "ecosystem",
    "repository_url", "version_pinned",
    "strategy", "tag_used", "commit_sha", "doc_file_count",
    "status", "error", "attempts",
]


def parse_range(value: str) -> tuple[int, int]:
    if "-" in value:
        a, b = value.split("-", 1)
        return int(a), int(b)
    n = int(value)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--lang", choices=["java", "python", "all"], default="all")
    ap.add_argument("--libraries",
                    help="Range within this pass, e.g. '1-10' (1-indexed).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be cloned; make no changes.")
    ap.add_argument("--max-passes", type=int, default=5,
                    help="Maximum promotion-and-retry passes.")
    args = ap.parse_args()

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    excl_path = frame_dir / "exclusion_log.csv"
    clone_log_path = frame_dir / "clone_log.csv"

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = load_manifest(manifest_path)
    excl_fields, excl_rows = load_exclusion_log(excl_path)

    # Ensure commit_sha column exists in manifest.
    if "commit_sha" not in fieldnames:
        fieldnames.append("commit_sha")
        for r in rows:
            r.setdefault("commit_sha", "")

    ecosystems = ["java", "python"] if args.lang == "all" else [args.lang]
    lib_range = parse_range(args.libraries) if args.libraries else None

    # Open the clone log in append mode across passes.
    clone_log_exists = clone_log_path.exists()
    clone_log_fh = open(clone_log_path, "a" if clone_log_exists else "w",
                        newline="", encoding="utf-8")
    clone_writer = csv.DictWriter(clone_log_fh, fieldnames=CLONE_LOG_COLS)
    if not clone_log_exists:
        clone_writer.writeheader()

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume between clones. Press 'q' or Ctrl-C to abort.")

    try:
        # Top up primary slots from reserves BEFORE the first pass.
        # Needed when the manifest has vacant slots at startup — e.g.
        # after promote_f7_exclusions.py has marked rows as
        # primary_excluded_f7 without filling their positions, or when
        # a prior run failed to promote enough reserves.
        pre_promoted = promote_reserves(rows)
        if pre_promoted:
            log.info("startup: promoted %d reserve(s) to fill vacant "
                     "primary slots", pre_promoted)
            if not args.dry_run:
                save_manifest(manifest_path, fieldnames, rows)

        for pass_i in range(1, args.max_passes + 1):
            log.info("=== pass %d ===", pass_i)
            n_new = process_primaries(
                rows, excl_rows, clone_writer,
                ecosystems=ecosystems, pause=pause, lib_range=lib_range,
                dry_run=args.dry_run,
            )
            clone_log_fh.flush()

            if args.dry_run:
                break

            if n_new == 0:
                log.info("no new failures this pass; stopping")
                break

            promoted = promote_reserves(rows)
            log.info("pass %d: %d new F4 failures, %d reserves promoted",
                     pass_i, n_new, promoted)
            if promoted == 0:
                log.warning("no reserves left to promote; stopping")
                break

            # Persist intermediate state at each pass boundary.
            if not args.dry_run:
                save_manifest(manifest_path, fieldnames, rows)
                save_exclusion_log(excl_path, excl_fields, excl_rows)
    finally:
        clone_log_fh.close()
        pause.stop()

    if not args.dry_run:
        save_manifest(manifest_path, fieldnames, rows)
        save_exclusion_log(excl_path, excl_fields, excl_rows)

    # Report.
    from collections import Counter
    status_counts = Counter((r["ecosystem"], r["status"]) for r in rows)
    print("\n--- final status counts ---")
    for k, v in sorted(status_counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
