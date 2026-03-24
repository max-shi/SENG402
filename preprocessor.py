"""
Preprocessor — API Documentation Corpus Builder

Extracts natural-language prose from raw Javadoc HTML pages and writes a
flat CSV suitable for LIWC analysis.  Handles both modern (JDK 13+) and
legacy (JDK 8–12) Javadoc layouts with ecosystem-specific extraction logic.

Usage:
    python preprocessor.py
"""

import csv
import logging
import re
from pathlib import Path

try:
    import lxml  # noqa: F401 — only needed to confirm availability
    BS_PARSER = "lxml"
except ImportError:
    BS_PARSER = "html.parser"

from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LIBRARIES_CSV = "librariesJAVA.csv"
RAW_DIR = Path("raw")
CORPUS_DIR = Path("corpus")
CORPUS_CSV = CORPUS_DIR / "corpus.csv"

CORPUS_COLUMNS = [
    "library",
    "ecosystem",
    "domain",
    "organisation",
    "javadoc_version",
    "source_file",
    "class_name",
    "section_type",
    "element_id",
    "text",
]

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


def class_name_from_title(soup: BeautifulSoup) -> str:
    """Derive the class/interface name from the page <title> tag."""
    title_tag = soup.find("title")
    if not title_tag:
        return ""
    text = title_tag.get_text(strip=True)
    # Typical patterns:
    #   "Strings (Guava: Google Core Libraries …)"  → "Strings"
    #   "java.lang.String"                           → "String"
    # Take everything before the first '(' and use the last dotted segment.
    text = text.split("(")[0].strip()
    return text.rsplit(".", 1)[-1].strip()


# ---------------------------------------------------------------------------
# Stage 1 — Stripping
# ---------------------------------------------------------------------------

# Tags to decompose entirely
DECOMPOSE_TAGS = ["header", "footer", "nav"]

# CSS selectors to decompose entirely
DECOMPOSE_SELECTORS = [
    "div.top-nav",
    "div.sub-nav",
    "div.skip-nav",
    "div.member-signature",
    "span.member-signature",
    "section.summary",
    "div#all-packages-table",
    "div.deprecation-block",
    "div.inheritance",
    "div.nav-list-search",
]

def strip_page(soup: BeautifulSoup) -> None:
    """Remove non-prose elements from the parsed tree (in-place)."""
    # Decompose named tags
    for tag_name in DECOMPOSE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Decompose by CSS selector
    for selector in DECOMPOSE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Decompose all <dt> tags (labels inside <dl> elements)
    for el in soup.find_all("dt"):
        el.decompose()

    # Replace <pre> and <code> with a single space (preserve surrounding text)
    for tag_name in ("pre", "code"):
        for el in soup.find_all(tag_name):
            el.replace_with(" ")


# ---------------------------------------------------------------------------
# Stage 2 — Version Detection
# ---------------------------------------------------------------------------

def detect_version(soup: BeautifulSoup, csv_version: str) -> str:
    """
    Auto-detect modern vs legacy Javadoc from the parsed (stripped) tree.
    Warns and overrides if the CSV disagrees.
    """
    is_modern = (
        soup.select_one("section.detail") is not None
        or soup.select_one("section#class-description") is not None
    )
    is_legacy = (
        soup.select_one("div.description") is not None
        or soup.select_one("div.details") is not None
    )

    if is_modern:
        detected = "modern"
    elif is_legacy:
        detected = "legacy"
    else:
        detected = "modern"  # default
        log.warning("Could not detect Javadoc version; defaulting to modern")

    csv_version_clean = csv_version.strip().lower() if csv_version else ""
    if csv_version_clean and csv_version_clean != detected:
        log.warning(
            "Version mismatch: CSV says '%s', auto-detected '%s' — using '%s'",
            csv_version_clean,
            detected,
            detected,
        )

    return detected


# ---------------------------------------------------------------------------
# Stage 3a — Modern Javadoc extraction
# ---------------------------------------------------------------------------

def extract_modern(soup: BeautifulSoup) -> list[dict]:
    """Extract prose chunks from a modern Javadoc page (JDK 13+)."""
    rows: list[dict] = []

    # Class description
    cls_section = soup.select_one("section#class-description")
    if cls_section:
        for block in cls_section.select("div.block"):
            rows.append({
                "section_type": "class_description",
                "element_id": "",
                "text": block.get_text(" ", strip=True),
            })

    # Package description
    pkg_section = soup.select_one("section#package-description")
    if pkg_section:
        for block in pkg_section.select("div.block"):
            rows.append({
                "section_type": "package_description",
                "element_id": "",
                "text": block.get_text(" ", strip=True),
            })

    # Member details
    for detail in soup.select("section.detail"):
        element_id = detail.get("id", "")

        for block in detail.select("div.block"):
            rows.append({
                "section_type": "member_description",
                "element_id": element_id,
                "text": block.get_text(" ", strip=True),
            })

        for notes_dl in detail.select("dl.notes"):
            for dd in notes_dl.find_all("dd"):
                rows.append({
                    "section_type": "param_return_throws",
                    "element_id": element_id,
                    "text": dd.get_text(" ", strip=True),
                })

    return rows


# ---------------------------------------------------------------------------
# Stage 3b — Legacy Javadoc extraction
# ---------------------------------------------------------------------------

def extract_legacy(soup: BeautifulSoup) -> list[dict]:
    """Extract prose chunks from a legacy Javadoc page (JDK 8–12)."""
    rows: list[dict] = []

    # Class description — only the FIRST div.block inside div.description
    desc_div = soup.select_one("div.description")
    if desc_div:
        first_block = desc_div.select_one("div.block")
        if first_block:
            rows.append({
                "section_type": "class_description",
                "element_id": "",
                "text": first_block.get_text(" ", strip=True),
            })

    # Member details
    details_div = soup.select_one("div.details")
    if details_div:
        members = details_div.select(
            "ul.blockList > li.blockList, ul.blockList > li.blockListLast"
        )
        for member in members:
            # Find the <a name="..."> anchor for element_id
            anchor = member.find("a", attrs={"name": True})
            element_id = anchor["name"] if anchor else ""

            for block in member.select("div.block"):
                rows.append({
                    "section_type": "member_description",
                    "element_id": element_id,
                    "text": block.get_text(" ", strip=True),
                })

            for dl in member.find_all("dl"):
                for dd in dl.find_all("dd"):
                    rows.append({
                        "section_type": "param_return_throws",
                        "element_id": element_id,
                        "text": dd.get_text(" ", strip=True),
                    })

    return rows


# ---------------------------------------------------------------------------
# Stage 4 — Text Cleaning
# ---------------------------------------------------------------------------

def clean_text(raw: str) -> str:
    """Clean extracted prose text."""
    # 1. Collapse runs of spaces and tabs into a single space
    text = re.sub(r"[ \t]+", " ", raw)
    # 2. Collapse three or more consecutive newlines into two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 3. Strip leading and trailing whitespace
    text = text.strip()
    # 4. Split into lines, strip each, discard lines with fewer than 2 tokens
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 2:
            lines.append(line)
    # 5. Rejoin remaining lines with a single space
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Stage 5 — Filtering
# ---------------------------------------------------------------------------

def passes_filter(text: str) -> bool:
    """Return True if the chunk has at least 5 words."""
    return len(text.split()) >= 5


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_file(
    html_path: Path,
    library: dict,
    raw_root: Path,
) -> list[dict]:
    """Process a single HTML file and return corpus rows."""
    try:
        html = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.error("Cannot read %s: %s", html_path, exc)
        return []

    soup = BeautifulSoup(html, BS_PARSER)

    # Stage 1 — Strip
    strip_page(soup)

    # Stage 2 — Detect version
    csv_version = library.get("javadoc_version", "").strip().lower()
    version = detect_version(soup, csv_version)

    # Stage 3 — Extract
    if version == "legacy":
        raw_rows = extract_legacy(soup)
    else:
        raw_rows = extract_modern(soup)

    class_name = class_name_from_title(soup)
    source_file = str(html_path.relative_to(raw_root))

    # Stage 4 & 5 — Clean and filter
    result: list[dict] = []
    for row in raw_rows:
        cleaned = clean_text(row["text"])
        if not passes_filter(cleaned):
            continue
        result.append({
            "library": library["name"].strip(),
            "ecosystem": library.get("ecosystem", "").strip().lower(),
            "domain": library.get("domain", "").strip(),
            "organisation": library.get("organisation", "").strip(),
            "javadoc_version": version,
            "source_file": source_file,
            "class_name": class_name,
            "section_type": row["section_type"],
            "element_id": row["element_id"],
            "text": cleaned,
        })

    return result


def main() -> None:
    libraries = load_libraries(LIBRARIES_CSV)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = 0

    with open(CORPUS_CSV, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=CORPUS_COLUMNS)
        writer.writeheader()

        for library in libraries:
            ecosystem = library.get("ecosystem", "").strip().lower()
            if ecosystem != "java":
                continue

            name = library["name"].strip()
            lib_dir = RAW_DIR / name

            if not lib_dir.is_dir():
                log.warning("No raw directory for library '%s' — skipping", name)
                continue

            html_files = sorted(lib_dir.rglob("*.html"))
            log.info(
                "Processing library '%s': %d HTML files found", name, len(html_files)
            )

            lib_rows = 0
            for html_path in html_files:
                rows = process_file(html_path, library, RAW_DIR)
                if not rows:
                    log.warning("Zero rows extracted from %s", html_path)
                for row in rows:
                    writer.writerow(row)
                    lib_rows += 1

            log.info(
                "Finished library '%s': %d text chunks extracted", name, lib_rows
            )
            total_rows += lib_rows

    log.info("Corpus complete: %d total rows written to %s", total_rows, CORPUS_CSV)


if __name__ == "__main__":
    main()
