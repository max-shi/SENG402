"""
crawler: Java Javadoc Site Crawler

Crawls each Java library's online Javadoc site and saves class/interface/package
detail pages as HTML under files/raw/raw_java/<library_name>/.

Usage:
    python crawler.py                    # crawl all libraries
    python crawler.py --libraries 1      # first library only
    python crawler.py --libraries 3-10   # libraries 3 through 10 (1-indexed)

Press Space at any time to pause/resume. Already-saved pages are skipped on re-run.
"""

import argparse
import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pause_helper import PauseController

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
LIBRARIES_CSV = str(_HERE.parent / "libraries" / "librariesJAVA.csv")
RAW_DIR = _HERE.parent.parent / "files" / "raw" / "raw_java"  # <- output folder
LOG_DIR = _HERE.parent.parent / "files" / "raw" / "raw_java" / "logs"
CRAWL_LOG = LOG_DIR / "crawl_log.csv"  # <- log file
DELAY = 0.15           # seconds between requests
REQUEST_TIMEOUT = 30   # seconds per attempt
RETRIES = 3            # total fetch attempts before giving up on a URL
BACKOFF = [2, 5, 10]   # seconds to wait before retry attempt 2, 3, ...

# Body classes that indicate a meaningful content page worth saving
# (modern Javadoc, JDK 13+)
CONTENT_BODY_CLASSES = {
    "class-declaration-page",
    "interface-declaration-page",
    "enum-declaration-page",
    "record-declaration-page",
    "annotation-declaration-page",
    "package-declaration-page",
}

# Filenames produced by Javadoc that are NEVER content pages (used as a
# negative filter for the legacy detector, which can't rely on body classes).
LEGACY_NON_CONTENT_BASENAMES = {
    "index.html", "overview-summary.html", "overview-tree.html",
    "overview-frame.html", "allclasses-frame.html", "allclasses-noframe.html",
    "allclasses.html", "allclasses-index.html", "allpackages-index.html",
    "constant-values.html", "deprecated-list.html", "help-doc.html",
    "serialized-form.html", "package-tree.html", "package-frame.html",
    "package-use.html", "package-search-index.html", "type-search-index.html",
    "member-search-index.html", "tag-search-index.html",
    "index-all.html", "search.html",
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


def normalise_url(url: str) -> str:
    """Strip fragment so #anchor variants map to the same page."""
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def is_in_scope(url: str, seed_url: str) -> bool:
    """
    Accept a URL only if it shares the same scheme+host and its path
    starts with the seed path prefix. This keeps the crawler inside
    the library's doc tree and off external sites.
    """
    seed = urlparse(seed_url)
    candidate = urlparse(url)
    return (
        candidate.scheme in ("http", "https")
        and candidate.netloc == seed.netloc
        and candidate.path.startswith(seed.path.rsplit("/", 1)[0])
    )


def is_content_page(soup: BeautifulSoup, url: str = "") -> bool:
    """Return True only for class/interface/package detail pages.

    Modern Javadoc (JDK 13+) marks the <body> with a class such as
    ``class-declaration-page``, that path is unambiguous. Legacy Javadoc
    (JDK 8–12) has no semantic body class, so we fall back to structural
    markers used by the legacy template (``div.description`` for class /
    interface / enum pages, ``div.contentContainer`` + the page being a
    package-summary for packages), while explicitly rejecting the well-
    known non-content filenames (``index.html``, ``allclasses-*.html``,
    etc.).
    """
    body = soup.find("body")
    if not body:
        return False

    classes = set(body.get("class", []))
    if classes & CONTENT_BODY_CLASSES:
        return True

    # ---- legacy fallback --------------------------------------------------
    basename = urlparse(url).path.rsplit("/", 1)[-1] if url else ""
    if basename in LEGACY_NON_CONTENT_BASENAMES:
        return False

    # Class / interface / enum / annotation detail pages
    if soup.select_one("div.description") and soup.select_one("div.details"):
        return True

    # Package summary pages (legacy uses package-summary.html with
    # div.contentContainer + a div.header containing the package name)
    if basename == "package-summary.html" and soup.select_one("div.contentContainer"):
        return True

    return False


def save_page(html: str, library_name: str, url: str) -> Path:
    """
    Mirror the URL path under files/raw/raw_java/<library_name>/.
    e.g. .../com/google/common/base/Strings.html
      -> files/raw/raw_java/guava/com/google/common/base/Strings.html
    """
    parsed = urlparse(url)
    # Strip the leading slash so Path doesn't treat it as absolute
    relative = parsed.path.lstrip("/")
    dest = RAW_DIR / library_name / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Core crawler
# ---------------------------------------------------------------------------

def crawl_library(library: dict, log_writer, pause: PauseController) -> None:
    name = library["name"].strip()
    seed_url = library["seed_url"].strip()

    log.info("=== Starting crawl: %s  seed=%s", name, seed_url)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (research-crawler/1.0)"})

    visited: set[str] = set()
    queue: list[str] = [normalise_url(seed_url)]
    saved = 0

    while queue:
        pause.check()
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        # ---- skip if already saved ----------------------------------------
        parsed_check = urlparse(url)
        dest_check = RAW_DIR / name / parsed_check.path.lstrip("/")
        if dest_check.is_file():
            log.info("  SKIP (exists)  %s", dest_check)
            continue

        # ---- fetch (with retries) ----------------------------------------
        resp = None
        last_exc: Exception | None = None
        for attempt in range(RETRIES):
            try:
                resp = session.get(url, timeout=REQUEST_TIMEOUT)
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < RETRIES - 1:
                    wait = BACKOFF[attempt] if attempt < len(BACKOFF) else BACKOFF[-1]
                    log.info("  retry %d/%d in %ds  %s  (%s)",
                             attempt + 2, RETRIES, wait, url, exc)
                    time.sleep(wait)
                else:
                    log.warning("FAIL after %d attempts  %s  %s",
                                RETRIES, url, exc)

        if resp is None:
            log_writer.writerow([
                datetime.now().isoformat(), name, url, "ERROR",
                str(last_exc), f"gave up after {RETRIES} attempts",
            ])
            time.sleep(DELAY)
            continue

        status = resp.status_code

        log_writer.writerow([datetime.now().isoformat(), name, url, status, "", ""])

        if status != 200:
            log.warning("HTTP %s  %s", status, url)
            time.sleep(DELAY)
            continue

        # ---- parse --------------------------------------------------------
        soup = BeautifulSoup(resp.text, "html.parser")

        # Save only meaningful content pages
        if is_content_page(soup, url):
            dest = save_page(resp.text, name, url)
            saved += 1
            log.info("  SAVE [%4d]  %s", saved, dest)

        # ---- discover links -----------------------------------------------
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            abs_url = normalise_url(urljoin(url, href))

            if (
                abs_url not in visited
                and abs_url not in queue
                and abs_url.endswith(".html")
                and is_in_scope(abs_url, seed_url)
            ):
                queue.append(abs_url)

        time.sleep(DELAY)

    log.info("=== Done: %s  visited=%d  saved=%d", name, len(visited), saved)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_library_range(value: str) -> tuple[int, int]:
    if "-" in value:
        parts = value.split("-", 1)
        return int(parts[0]), int(parts[1])
    n = int(value)
    return n, n


def main():
    parser = argparse.ArgumentParser(description="Crawl Java Javadoc sites into raw_java/")
    parser.add_argument(
        "--libraries",
        help="Library or range to crawl, e.g. '1' or '3-10' (1-indexed). Default: all.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    libraries = load_libraries(LIBRARIES_CSV)

    java_libs = [l for l in libraries if l.get("ecosystem", "").strip().lower() == "java"]

    if args.libraries:
        start, end = parse_library_range(args.libraries)
        java_libs = java_libs[start - 1:end]
        log.info("Restricting to libraries %d–%d (%d total)", start, end, len(java_libs))

    pause = PauseController()
    pause.start()
    log.info("Press Space to pause/resume.")

    with open(CRAWL_LOG, "w", newline="", encoding="utf-8") as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["timestamp", "library", "url", "status", "error", "notes"])

        for library in java_libs:
            crawl_library(library, writer, pause)
            log_file.flush()  # write progress after each library

    pause.stop()

if __name__ == "__main__":
    main()
