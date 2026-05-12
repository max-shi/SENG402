"""
extractor_java — Java-specific extraction rules for the unified preprocessor.

Exports the interface expected by `preprocess.py`:
    ECOSYSTEM, LIBRARIES_CSV, RAW_DIR
    discover_files(library_meta) -> Iterable[Path]
    extract_chunks(file_path, library_meta) -> list[Chunk]

A Chunk is a dict with keys:
    section_type, element_id, class_name, text, text_html, extra
where `extra` is a free-form dict of language-specific metadata
(e.g. javadoc_version) merged into the per-chunk CSV row.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

try:
    import lxml  # noqa: F401
    BS_PARSER = "lxml"
except ImportError:
    BS_PARSER = "html.parser"

from bs4 import BeautifulSoup, NavigableString, Tag

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module interface constants
# ---------------------------------------------------------------------------
ECOSYSTEM = "java"
LIBRARIES_CSV = "librariesJAVA.csv"
RAW_DIR = Path("raw")

# ---------------------------------------------------------------------------
# Stripping rules
# ---------------------------------------------------------------------------
DECOMPOSE_TAGS = ["header", "footer", "nav"]

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


def _strip_page(soup: BeautifulSoup) -> None:
    for tag_name in DECOMPOSE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()
    for selector in DECOMPOSE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()
    for el in soup.find_all("dt"):
        el.decompose()
    for el in soup.find_all("pre"):
        el.replace_with(" ")


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

def _detect_version(soup: BeautifulSoup, csv_version: str, filepath: str = "") -> str:
    is_modern = (
        soup.select_one("section.detail") is not None
        or soup.select_one("section#class-description") is not None
        or soup.select_one("section#package-description") is not None
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
        detected = "modern"
        log.warning("Could not detect Javadoc version; defaulting to modern: %s", filepath)

    csv_version_clean = csv_version.strip().lower() if csv_version else ""
    if csv_version_clean and csv_version_clean != detected:
        log.warning(
            "Version mismatch for %s: CSV says '%s', auto-detected '%s' — using '%s'",
            filepath, csv_version_clean, detected, detected,
        )
    return detected


def _class_name_from_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    if not title_tag:
        return ""
    text = title_tag.get_text(strip=True)
    text = text.split("(")[0].strip()
    return text.rsplit(".", 1)[-1].strip()


# ---------------------------------------------------------------------------
# Modern Javadoc extraction
# ---------------------------------------------------------------------------

def _extract_modern(soup: BeautifulSoup) -> list[dict]:
    rows: list[dict] = []

    cls_section = soup.select_one("section#class-description")
    if cls_section:
        for block in cls_section.select("div.block"):
            rows.append({
                "section_type": "class_description",
                "element_id": "",
                "text": block.get_text(" ", strip=True),
                "text_html": block.decode_contents(),
            })

    pkg_section = soup.select_one("section#package-description")
    if pkg_section:
        for block in pkg_section.select("div.block"):
            rows.append({
                "section_type": "package_description",
                "element_id": "",
                "text": block.get_text(" ", strip=True),
                "text_html": block.decode_contents(),
            })

    for detail in soup.select("section.detail"):
        element_id = detail.get("id", "")
        for block in detail.select("div.block"):
            rows.append({
                "section_type": "member_description",
                "element_id": element_id,
                "text": block.get_text(" ", strip=True),
                "text_html": block.decode_contents(),
            })
        for notes_dl in detail.select("dl.notes"):
            for dd in notes_dl.find_all("dd"):
                rows.append({
                    "section_type": "param_return_throws",
                    "element_id": element_id,
                    "text": dd.get_text(" ", strip=True),
                    "text_html": dd.decode_contents(),
                })
    return rows


# ---------------------------------------------------------------------------
# Legacy Javadoc extraction
# ---------------------------------------------------------------------------

def _extract_legacy(soup: BeautifulSoup) -> list[dict]:
    rows: list[dict] = []

    desc_div = soup.select_one("div.description")
    if desc_div:
        first_block = desc_div.select_one("div.block")
        if first_block:
            rows.append({
                "section_type": "class_description",
                "element_id": "",
                "text": first_block.get_text(" ", strip=True),
                "text_html": first_block.decode_contents(),
            })

    details_div = soup.select_one("div.details")
    if details_div:
        members = details_div.select(
            "ul.blockList > li.blockList, ul.blockList > li.blockListLast"
        )
        for member in members:
            anchor = member.find("a", attrs={"name": True})
            element_id = anchor["name"] if anchor else ""
            for block in member.select("div.block"):
                rows.append({
                    "section_type": "member_description",
                    "element_id": element_id,
                    "text": block.get_text(" ", strip=True),
                    "text_html": block.decode_contents(),
                })
            for dl in member.find_all("dl"):
                for dd in dl.find_all("dd"):
                    rows.append({
                        "section_type": "param_return_throws",
                        "element_id": element_id,
                        "text": dd.get_text(" ", strip=True),
                        "text_html": dd.decode_contents(),
                    })
    return rows


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def discover_files(library_meta: dict) -> Iterable[Path]:
    name = library_meta["name"].strip()
    lib_dir = RAW_DIR / name
    if not lib_dir.is_dir():
        return []
    return sorted(lib_dir.rglob("*.html"))


def extract_chunks(file_path: Path, library_meta: dict) -> list[dict]:
    """Parse one HTML file and return a list of Chunk dicts."""
    try:
        html = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.error("Cannot read %s: %s", file_path, exc)
        return []

    soup = BeautifulSoup(html, BS_PARSER)
    _strip_page(soup)

    csv_version = library_meta.get("javadoc_version", "").strip().lower()
    rel_path = str(file_path.relative_to(RAW_DIR))
    version = _detect_version(soup, csv_version, filepath=rel_path)

    if version == "legacy":
        raw_rows = _extract_legacy(soup)
    else:
        raw_rows = _extract_modern(soup)

    class_name = _class_name_from_title(soup)

    chunks: list[dict] = []
    for r in raw_rows:
        chunks.append({
            "section_type": r["section_type"],
            "element_id": r["element_id"],
            "class_name": class_name,
            "text": r["text"],
            "text_html": re.sub(r"\s+", " ", r.get("text_html", "")).strip(),
            "extra": {"javadoc_version": version},
        })
    return chunks
