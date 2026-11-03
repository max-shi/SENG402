"""
rq3_extract_python: Extract API surface + README-only text for RQ3 (Python).

For each re-cloned Python library under files/raw/rq3/python/ (see
rq3_reclone.py), this produces two artefacts per library, both needed
by the RQ3 design:

1. API surface (files/corpus/rq3/api_surface/python/<safe_name>.txt),
   public class/function signatures only, reconstructed via static
   `ast` parsing. Docstrings and implementation bodies are never
   included: they *are* the human documentation surface this design
   exists to keep out of the LLM's prompt (the plan).
2. README-only human text (files/corpus/rq3/readme_only/python/<safe_name>.txt),
   just the top-level README, cleaned with the same extraction pipeline
   used for the main corpus (confirmatory_preprocessor.extract_prose),
   for a fair length/genre-matched comparison against the LLM's
   generated README (the full RQ1/RQ2 corpus text includes the
   whole docs/ tree, which no single LLM call is being asked to
   reproduce).

Source list is files/corpus/frame_locked_corrected/sample_manifest_final.csv
(the monorepo-duplication-corrected 400, RULES.md),
filtered to ecosystem=python (read-only, never modified).

Usage:
    venv/bin/python3 src/generation/rq3_extract_python.py [--libraries START-END]
                                                       [--limit N]
"""

from __future__ import annotations

import argparse
import ast
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_cloner import safe_name  # noqa: E402
from confirmatory_preprocessor import (  # noqa: E402
    IGNORE_HARD,
    IGNORE_SOFT,
    extract_prose,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
)
RAW_DIR = ROOT / "files" / "raw" / "rq3"
RQ3_DIR = ROOT / "files" / "corpus" / "rq3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

EXTRACT_LOG_COLS = [
    "timestamp", "package_name", "ecosystem", "safe_name",
    "scoped_to_subdir", "n_source_files_parsed", "n_source_files_skipped",
    "n_public_classes", "n_public_functions",
    "api_surface_word_count", "large_surface_flag",
    "readme_found", "readme_word_count",
    "status", "reason",
]

_PY_SKIP_STEMS = ("setup", "conftest")
_README_PRIORITY_EXT = [".md", ".markdown", ".rst", ".txt", ""]


# ---------------------------------------------------------------------------
# Source-file discovery (reuses the main corpus's directory-exclusion policy)
# ---------------------------------------------------------------------------

def find_source_files(clone_dir: Path) -> list[Path]:
    """Return a stable, sorted list of the library's own .py source files,
    excludes vendor/build/test/example trees, same as the doc-prose finder
    in the main pipeline, plus setup.py/conftest.py/test_*.py/*_test.py."""
    if not clone_dir.is_dir():
        return []
    out: list[Path] = []
    for path in clone_dir.rglob("*.py"):
        parts_lower = [p.lower() for p in path.parts]
        if any(seg in IGNORE_HARD for seg in parts_lower):
            continue
        if any(seg in IGNORE_SOFT for seg in parts_lower):
            continue
        stem_lower = path.stem.lower()
        if stem_lower in _PY_SKIP_STEMS:
            continue
        if stem_lower.startswith("test_") or stem_lower.endswith("_test"):
            continue
        out.append(path)
    out.sort(key=lambda p: str(p).lower())
    return out


_LARGE_SURFACE_WORDS = 20_000  # flag threshold, not a hard cap, see log column


_IGNORE_ALL = IGNORE_HARD | IGNORE_SOFT
_AIRFLOW_PROVIDER_PREFIX = "apache-airflow-providers-"


def _candidate_dir_names(package_name: str) -> list[str]:
    """Directory-name variants worth searching for, one per monorepo
    naming convention observed in this corpus. Exact name (Azure/GCP
    Python SDK monorepos place each package in a dir named exactly like
    the PyPI distribution) and the Airflow convention (the
    'apache-airflow-providers-' prefix is dropped, e.g. the
    apache-airflow-providers-docker distribution lives at
    providers/docker, not providers/apache-airflow-providers-docker)."""
    names = [package_name]
    if package_name.startswith(_AIRFLOW_PROVIDER_PREFIX):
        names.append(package_name[len(_AIRFLOW_PROVIDER_PREFIX):])
    return names


def _split_variants(package_name: str) -> list[Path]:
    """Path-shaped variants, e.g. 'moat-kv' -> moat/kv, some namespace
    packages (the moat family) split a hyphenated PyPI name across
    nested directories rather than using it as a single dir name."""
    if "-" not in package_name:
        return []
    return [Path(*package_name.split("-"))]


def find_scoped_root(clone_dir: Path, package_name: str) -> Path:
    """
    Some sampled libraries are published from a shared monorepo rather
    than their own repo (confirmed via sample_manifest_final.csv: 25
    repository_urls are shared by >1 sampled package, e.g. the Azure and
    Google Cloud Python SDK monorepos, apache/airflow, apache/camel-quarkus).
    Walking the whole clone for those pulls in every *other* package's
    code too, extraction on the unscoped clone produced 68,114 "public
    classes" for azure-mgmt-authorization, which is obviously not that
    package's own API surface.

    A single exact-name directory match isn't enough: a repo can contain
    more than one directory named after the package for unrelated
    reasons. mcap's monorepo has both python/mcap (the real package) and
    testdata/mcap (fixture files); the naive "first match by shallowest
    path" picked testdata/mcap depending on filesystem traversal order,
    which is also self-defeating since anything under a testdata/ path
    is excluded by IGNORE_SOFT regardless of where the scoped root sits.
    So: gather every name-variant candidate (including known
    conventions, see _candidate_dir_names/_split_variants), drop any
    that live inside an IGNORE_HARD/IGNORE_SOFT segment, and score the
    rest by how much real API surface they actually yield. If nothing
    scores above zero (no matching directory exists, e.g. pygame's
    Python sources live in src_py with no directory literally named
    "pygame" containing usable code), fall back to the whole clone,
    still subject to the large-surface flag, so a genuinely-unscoped
    monorepo doesn't pass silently.
    """
    seen: set[str] = set()
    candidates: list[Path] = []
    for name in _candidate_dir_names(package_name):
        for p in clone_dir.rglob(name):
            if p.is_dir() and ".git" not in p.parts and str(p) not in seen:
                seen.add(str(p))
                candidates.append(p)
    for rel in _split_variants(package_name):
        p = clone_dir / rel
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            candidates.append(p)

    valid = []
    for p in candidates:
        rel_parts = [s.lower() for s in p.relative_to(clone_dir).parts]
        if any(seg in _IGNORE_ALL for seg in rel_parts):
            continue
        valid.append(p)

    if not valid:
        return clone_dir

    def score(p: Path) -> int:
        return sum(
            1 for f in find_source_files(p) if extract_api_surface(f) is not None
        )

    best_score, best_p = max(
        ((score(p), p) for p in valid),
        key=lambda t: (t[0], -len(t[1].parts)),
    )
    return best_p if best_score > 0 else clone_dir


def find_top_level_readme(clone_dir: Path) -> Optional[Path]:
    """The single top-level README, what a human reader (and the LLM's
    generated equivalent) would be compared against, not every README in
    every subdirectory."""
    candidates = [
        p for p in clone_dir.iterdir()
        if p.is_file() and p.stem.lower().startswith("readme")
    ]
    if not candidates:
        return None

    def rank(p: Path) -> int:
        try:
            return _README_PRIORITY_EXT.index(p.suffix.lower())
        except ValueError:
            return len(_README_PRIORITY_EXT)

    candidates.sort(key=rank)
    return candidates[0]


# ---------------------------------------------------------------------------
# Signature reconstruction (no docstrings, no bodies)
# ---------------------------------------------------------------------------

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def _fmt_arg(arg: ast.arg) -> str:
    s = arg.arg
    if arg.annotation is not None:
        s += f": {_unparse(arg.annotation)}"
    return s


def format_signature(fn: FunctionNode) -> str:
    args = fn.args
    parts: list[str] = []

    combined = list(args.posonlyargs) + list(args.args)
    default_offset = len(combined) - len(args.defaults)
    for i, a in enumerate(combined):
        s = _fmt_arg(a)
        if i >= default_offset:
            s += f"={_unparse(args.defaults[i - default_offset])}"
        parts.append(s)
        if args.posonlyargs and i == len(args.posonlyargs) - 1:
            parts.append("/")

    if args.vararg:
        parts.append(f"*{_fmt_arg(args.vararg)}")
    elif args.kwonlyargs:
        parts.append("*")

    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        s = _fmt_arg(a)
        if d is not None:
            s += f"={_unparse(d)}"
        parts.append(s)

    if args.kwarg:
        parts.append(f"**{_fmt_arg(args.kwarg)}")

    prefix = "async " if isinstance(fn, ast.AsyncFunctionDef) else ""
    sig = f"{prefix}def {fn.name}({', '.join(parts)})"
    if fn.returns is not None:
        sig += f" -> {_unparse(fn.returns)}"
    return sig + ":"


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def extract_api_surface(py_path: Path) -> Optional[str]:
    """Return the public class/function signatures in `py_path` (one
    level of class nesting), or None if the file has no public surface
    or fails to parse (syntax errors, Python-2-only files, etc.)."""
    try:
        src = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (SyntaxError, ValueError, OSError):
        # OSError covers broken symlinks (rglob lists them, but the
        # target doesn't resolve, seen in moat-kv's vendored tree) and
        # any other unreadable file; both are skip-worthy, not fatal.
        return None

    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(node.name):
            lines.append(format_signature(node))
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            bases = ", ".join(_unparse(b) for b in node.bases)
            lines.append(f"class {node.name}({bases}):" if bases else f"class {node.name}:")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(sub.name):
                    lines.append("    " + format_signature(sub))

    return "\n".join(lines) if lines else None


# ---------------------------------------------------------------------------
# Per-library processing
# ---------------------------------------------------------------------------

def process_library(row: dict) -> dict:
    pkg = row["package_name"]
    eco = "python"
    sname = safe_name(pkg)
    clone_dir = RAW_DIR / eco / sname

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_name": pkg, "ecosystem": eco, "safe_name": sname,
        "scoped_to_subdir": "", "n_source_files_parsed": 0,
        "n_source_files_skipped": 0,
        "n_public_classes": 0, "n_public_functions": 0,
        "api_surface_word_count": 0, "large_surface_flag": "false",
        "readme_found": "false",
        "readme_word_count": 0, "status": "", "reason": "",
    }

    if not clone_dir.is_dir():
        entry["status"] = "clone_missing"
        entry["reason"] = f"clone dir not found: {clone_dir}"
        return entry

    scoped_root = find_scoped_root(clone_dir, pkg)
    if scoped_root != clone_dir:
        entry["scoped_to_subdir"] = str(scoped_root.relative_to(clone_dir))

    blocks: list[str] = []
    n_parsed = n_skipped = n_classes = n_funcs = 0
    for path in find_source_files(scoped_root):
        block = extract_api_surface(path)
        if block is None:
            n_skipped += 1
            continue
        n_parsed += 1
        rel = path.relative_to(clone_dir)
        blocks.append(f"# {rel}\n{block}")
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("class "):
                n_classes += 1
            elif stripped.startswith("def ") or stripped.startswith("async def "):
                n_funcs += 1

    entry["n_source_files_parsed"] = n_parsed
    entry["n_source_files_skipped"] = n_skipped
    entry["n_public_classes"] = n_classes
    entry["n_public_functions"] = n_funcs

    if not blocks:
        entry["status"] = "no_api_surface"
        entry["reason"] = "no parseable public signatures found"
        return entry

    api_text = "\n\n".join(blocks)
    api_dir = RQ3_DIR / "api_surface" / eco
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / f"{sname}.txt").write_text(api_text, encoding="utf-8")
    word_count = len(api_text.split())
    entry["api_surface_word_count"] = word_count
    if word_count > _LARGE_SURFACE_WORDS:
        entry["large_surface_flag"] = "true"

    # Prefer a README inside the scoped subdirectory (the correct choice
    # for a genuine monorepo, where each package folder usually has its
    # own README distinct from the monorepo's front-page README) and
    # fall back to the repo root otherwise (the correct choice for an
    # ordinary single-package repo using the "src/<pkg>/" layout, where
    # `scoped_root` is just that inner source directory and has no
    # README of its own, the real one is at clone_dir).
    readme_path = find_top_level_readme(scoped_root)
    if readme_path is None and scoped_root != clone_dir:
        readme_path = find_top_level_readme(clone_dir)
    if readme_path is not None:
        readme_text = extract_prose(readme_path)
        if readme_text.strip():
            entry["readme_found"] = "true"
            entry["readme_word_count"] = len(readme_text.split())
            readme_dir = RQ3_DIR / "readme_only" / eco
            readme_dir.mkdir(parents=True, exist_ok=True)
            (readme_dir / f"{sname}.txt").write_text(readme_text, encoding="utf-8")

    entry["status"] = "ready"
    return entry


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_range(value: str) -> tuple[int, int]:
    if "-" in value:
        a, b = value.split("-", 1)
        return int(a), int(b)
    n = int(value)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--libraries", help="Range within this pass, e.g. '1-10' (1-indexed)."
    )
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not SOURCE_MANIFEST.exists():
        raise SystemExit(f"source manifest not found: {SOURCE_MANIFEST}")

    with open(SOURCE_MANIFEST) as f:
        rows = [r for r in csv.DictReader(f) if r["ecosystem"] == "python"]

    if args.libraries:
        start, end = parse_range(args.libraries)
        rows = rows[start - 1:end]
    if args.limit > 0:
        rows = rows[:args.limit]

    RQ3_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RQ3_DIR / "extract_log_python.csv"
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=EXTRACT_LOG_COLS)
    if not log_exists:
        writer.writeheader()

    counts: dict[str, int] = {}
    try:
        for i, row in enumerate(rows, 1):
            log.info("[%d/%d] %s", i, len(rows), row["package_name"])
            try:
                entry = process_library(row)
            except Exception as exc:  # noqa: BLE001, one bad repo must not
                # abort the other 199 (this is exactly how the previous run
                # died on moat-kv's broken symlink; that specific cause is
                # now fixed, but nothing guarantees it's the last one).
                log.exception("  CRASHED on %s: %s", row["package_name"], exc)
                entry = {col: "" for col in EXTRACT_LOG_COLS}
                entry.update({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "package_name": row["package_name"], "ecosystem": "python",
                    "safe_name": safe_name(row["package_name"]),
                    "status": "crashed", "reason": str(exc)[:300],
                })
            writer.writerow(entry)
            log_fh.flush()
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            log.info(
                "  -> %s  classes=%d funcs=%d api_words=%d readme_words=%s",
                entry["status"], entry["n_public_classes"],
                entry["n_public_functions"], entry["api_surface_word_count"],
                entry["readme_word_count"] if entry["readme_found"] == "true" else "-",
            )
    finally:
        log_fh.close()

    print("\n--- extract summary ---")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
