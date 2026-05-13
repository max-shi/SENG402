"""
cloner — Python Library Source Acquirer

Clones Python library repositories at a specified git tag into
files/raw/raw_python/<library_name>/, mirroring the role that crawler.py
plays for Java Javadoc HTML.

Usage:
    python cloner.py                    # clone all libraries
    python cloner.py --libraries 1      # first library only
    python cloner.py --libraries 3-10   # libraries 3 through 10 (1-indexed)

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

from pause_helper import PauseController

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
LIBRARIES_CSV = str(_HERE.parent / "libraries" / "librariesPYTHON.csv")
RAW_DIR = _HERE.parent.parent / "files" / "raw" / "raw_python"
LOG_DIR = _HERE.parent.parent / "files" / "raw" / "raw_python" / "logs"
CLONE_LOG = LOG_DIR / "clone_log.csv"

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

def clone_library(library: dict, log_writer) -> None:
    name = library["name"].strip()
    repo_url = library["repo_url"].strip()
    git_tag = library.get("git_tag", "").strip()
    dest = RAW_DIR / name

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone Python library repos into raw_python/")
    parser.add_argument(
        "--libraries",
        help="Library or range to clone, e.g. '1' or '3-10' (1-indexed). Default: all.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    libraries = load_libraries(LIBRARIES_CSV)

    python_libs = [l for l in libraries if l.get("ecosystem", "").strip().lower() == "python"]

    if args.libraries:
        start, end = parse_library_range(args.libraries)
        python_libs = python_libs[start - 1:end]
        log.info("Restricting to libraries %d–%d (%d total)", start, end, len(python_libs))

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume between libraries.")

    with open(CLONE_LOG, "w", newline="", encoding="utf-8") as log_f:
        writer = csv.writer(log_f)
        writer.writerow(["timestamp", "library", "repo_url", "git_tag", "status", "output"])

        for library in python_libs:
            pause.check()
            clone_library(library, writer)
            log_f.flush()

    pause.stop()


if __name__ == "__main__":
    main()
