import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LIBRARIES_CSV = "librariesJAVA.csv"
RAW_DIR = Path("raw") # <- output folder
LOG_DIR = Path("logs")
CRAWL_LOG = LOG_DIR / "crawl_log.csv" # <- log file
DELAY = 0.15         # seconds between requests
REQUEST_TIMEOUT = 15  # seconds

# Body classes that indicate a meaningful content page worth saving
CONTENT_BODY_CLASSES = {
    "class-declaration-page",
    "interface-declaration-page",
    "enum-declaration-page",
    "record-declaration-page",
    "annotation-declaration-page",
    "package-declaration-page",
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


def is_content_page(soup: BeautifulSoup) -> bool:
    """Return True only for class/interface/package detail pages."""
    body = soup.find("body")
    if not body:
        return False
    classes = set(body.get("class", []))
    return bool(classes & CONTENT_BODY_CLASSES)


def save_page(html: str, library_name: str, url: str) -> Path:
    """
    Mirror the URL path under raw/<library_name>/.
    e.g. .../com/google/common/base/Strings.html
      -> raw/guava/com/google/common/base/Strings.html
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

def crawl_library(library: dict, log_writer) -> None:
    name = library["name"].strip()
    seed_url = library["seed_url"].strip()

    log.info("=== Starting crawl: %s  seed=%s", name, seed_url)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (research-crawler/1.0)"})

    visited: set[str] = set()
    queue: list[str] = [normalise_url(seed_url)]
    saved = 0

    while queue:
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

        # ---- fetch --------------------------------------------------------
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            status = resp.status_code
        except requests.RequestException as exc:
            log.warning("FAIL  %s  %s", url, exc)
            log_writer.writerow([datetime.now().isoformat(), name, url, "ERROR", str(exc), ""])
            time.sleep(DELAY)
            continue

        log_writer.writerow([datetime.now().isoformat(), name, url, status, "", ""])

        if status != 200:
            log.warning("HTTP %s  %s", status, url)
            time.sleep(DELAY)
            continue

        # ---- parse --------------------------------------------------------
        soup = BeautifulSoup(resp.text, "html.parser")

        # Save only meaningful content pages
        if is_content_page(soup):
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

def main():
    RAW_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    libraries = load_libraries(LIBRARIES_CSV)

    with open(CRAWL_LOG, "w", newline="", encoding="utf-8") as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["timestamp", "library", "url", "status", "error", "notes"])

        java_libs = [l for l in libraries if l.get("ecosystem", "").strip().lower() == "java"]
        for library in java_libs[:3]:
            crawl_library(library, writer)
            log_file.flush()  # write progress after each library

if __name__ == "__main__":
    main()
