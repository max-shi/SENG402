"""
cloner: Library Source Acquirer (Python & Java)

Clones each library's source repository at a pinned git tag into
``files/raw/raw_<lang>/<library_name>/``. Replaces both the old Python-only
cloner and the Java Javadoc HTML crawler, the new pipeline extracts prose
directly from source for both languages.

Usage:
    python cloner.py                          # clone all libraries, both langs
    python cloner.py --lang python            # python only
    python cloner.py --lang java              # java only
    python cloner.py --lang java --libraries 1
    python cloner.py --lang python --libraries 3-10

Both CSVs must share the columns:
    name, ecosystem, repo_url, git_tag, source_subdir, ...

Press Space at any time to pause/resume between libraries.
Already-cloned repos are updated to the correct tag on re-run.
"""

import argparse
import csv
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from pause_helper import PauseController

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
LIB_DIR = _HERE / "libraries"
FILES_ROOT = _HERE.parent.parent / "files" / "raw"

# Per-language source layout. Add a new ecosystem here and the rest of the
# script picks it up automatically.
ECOSYSTEMS = {
    "python": {
        "csv":     LIB_DIR / "librariesPYTHON.csv",
        "raw_dir": FILES_ROOT / "raw_python",
    },
    "java": {
        "csv":     LIB_DIR / "librariesJAVA.csv",
        "raw_dir": FILES_ROOT / "raw_java",
    },
    "javascript": {
        "csv":     LIB_DIR / "librariesJAVASCRIPT.csv",
        "raw_dir": FILES_ROOT / "raw_javascript",
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_libraries(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        return list(reader)


def run(cmd: list[str], cwd: Optional[Path] = None) -> tuple[int, str]:
    """Run a subprocess, return (returncode, combined output)."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


# ---------------------------------------------------------------------------
# Core cloner
# ---------------------------------------------------------------------------

def clone_library(library: dict, raw_dir: Path, log_writer) -> None:
    name = library["name"].strip()
    repo_url = library["repo_url"].strip()
    git_tag = library.get("git_tag", "").strip()
    dest = raw_dir / name

    log.info("=== %s  tag=%s", name, git_tag or "HEAD")

    # ---- already cloned ---------------------------------------------------
    if dest.is_dir():
        log.info("  EXISTS — updating to tag %s", git_tag)
        if git_tag:
            code, out = run(["git", "fetch", "--tags"], cwd=dest)
            if code != 0:
                log.warning("  fetch failed: %s", out)
            code, out = run(["git", "checkout", git_tag], cwd=dest)
            status = "UPDATED" if code == 0 else "CHECKOUT_FAIL"
        else:
            code, out = run(["git", "pull"], cwd=dest)
            status = "UPDATED" if code == 0 else "PULL_FAIL"

        log_writer.writerow([datetime.now().isoformat(), name, repo_url, git_tag, status, out[:200]])
        log.info("  %s", status)
        return

    # ---- fresh clone ------------------------------------------------------
    dest.parent.mkdir(parents=True, exist_ok=True)

    clone_cmd = ["git", "clone", "--depth", "1"]
    if git_tag:
        clone_cmd += ["--branch", git_tag]
    clone_cmd += [repo_url, str(dest)]

    log.info("  Cloning %s ...", repo_url)
    code, out = run(clone_cmd)

    if code == 0:
        status = "CLONED"
        log.info("  CLONED → %s", dest)
    else:
        status = "FAIL"
        log.error("  FAIL: %s", out)

    log_writer.writerow([datetime.now().isoformat(), name, repo_url, git_tag, status, out[:200]])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_library_range(value: str) -> tuple[int, int]:
    if "-" in value:
        parts = value.split("-", 1)
        return int(parts[0]), int(parts[1])
    n = int(value)
    return n, n


def run_ecosystem(lang: str, lib_range: Optional[str], pause: PauseController) -> None:
    cfg = ECOSYSTEMS[lang]
    csv_path: Path = cfg["csv"]
    raw_dir: Path = cfg["raw_dir"]
    log_dir = raw_dir / "logs"
    clone_log = log_dir / "clone_log.csv"

    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    libraries = load_libraries(str(csv_path))
    libraries = [l for l in libraries
                 if l.get("ecosystem", "").strip().lower() == lang]

    if lib_range:
        start, end = parse_library_range(lib_range)
        libraries = libraries[start - 1:end]
        log.info("[%s] restricting to libraries %d–%d (%d total)",
                 lang, start, end, len(libraries))

    if not libraries:
        log.warning("[%s] no libraries to clone", lang)
        return

    with open(clone_log, "w", newline="", encoding="utf-8") as log_f:
        writer = csv.writer(log_f)
        writer.writerow(["timestamp", "library", "repo_url", "git_tag",
                         "status", "output"])
        for library in libraries:
            pause.check()
            clone_library(library, raw_dir, writer)
            log_f.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clone library source repos into files/raw/raw_<lang>/"
    )
    parser.add_argument(
        "--lang",
        choices=[*ECOSYSTEMS.keys(), "all"],
        default="all",
        help="Which ecosystem to clone (default: all).",
    )
    parser.add_argument(
        "--libraries",
        help="Library or range to clone, e.g. '1' or '3-10' (1-indexed). "
             "Applied within each --lang selection. Default: all.",
    )
    args = parser.parse_args()

    targets = list(ECOSYSTEMS) if args.lang == "all" else [args.lang]

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume between libraries.")

    try:
        for lang in targets:
            run_ecosystem(lang, args.libraries, pause)
    finally:
        pause.stop()


if __name__ == "__main__":
    main()
