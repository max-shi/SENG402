"""
extractor_javascript: JavaScript/TypeScript extraction rules for the unified preprocessor.

Extracts JSDoc / TSDoc comments from .js, .ts, .jsx, .tsx source files using
regex-based comment extraction (no external parser required). Mirrors the
interface expected by preprocess.py.

Exports:
    ECOSYSTEM, LIBRARIES_CSV, RAW_DIR
    discover_files(library_meta) -> Iterable[Path]
    extract_chunks(file_path, library_meta) -> list[Chunk]
"""

from __future__ import annotations

import re
import html as _html_mod
import logging
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module interface constants
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent

ECOSYSTEM = "javascript"
LIBRARIES_CSV = str(_HERE / "libraries" / "librariesJAVASCRIPT.csv")
RAW_DIR = _HERE.parent.parent / "files" / "raw" / "raw_javascript"

# ---------------------------------------------------------------------------
# Source file extensions to scan
# ---------------------------------------------------------------------------
_EXTENSIONS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}

# ---------------------------------------------------------------------------
# Comment extraction regex
# Matches /** ... */ blocks (greedy=False to get each block separately).
# ---------------------------------------------------------------------------
_JSDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Capture the name of the thing immediately following the comment
_DECL_RE = re.compile(
    r"(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:(?:class|function\*?|const|let|var|interface|type|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*))"
    r"|(?:([A-Za-z_$][A-Za-z0-9_$]*)\s*[=:]\s*(?:async\s+)?function)"
)

# ---------------------------------------------------------------------------
# JSDoc / TSDoc cleaning
# ---------------------------------------------------------------------------

_LINE_STAR_RE = re.compile(r"^\s*\*\s?")

_BLOCK_TAG_RE = re.compile(
    r"^\s*@(param|returns?|throws?|exception|see|since|deprecated|author|"
    r"version|example|memberof|typedef|callback|type|property|prop|"
    r"template|internal|private|protected|public|override|abstract|"
    r"readonly|sealed|virtual|static|description|default|module|"
    r"namespace|class|constructor|interface|enum|event|fires|listens|"
    r"emits|yield|yields)\b",
    re.IGNORECASE,
)

_INLINE_LINK_RE = re.compile(r"\{@(?:link(?:code|plain)?|tutorial)\s+([^}]*?)\}")
_INLINE_BARE_RE = re.compile(r"\{@[a-zA-Z]+[^}]*\}")
_BACKTICK_RE = re.compile(r"```.*?```|`[^`]+`", re.DOTALL)
_ANGLE_URL_RE = re.compile(r"<https?://[^>]*>")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+")
_MD_HR_RE = re.compile(r"^[-*_]{3,}\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _resolve_link(target: str) -> str:
    target = target.strip()
    if "|" in target:
        _, label = target.split("|", 1)
        return label.strip()
    parts = target.split(None, 1)
    if len(parts) > 1:
        return parts[1].strip()
    ref = parts[0].lstrip("#").replace("#", ".").split("/")[-1]
    return ref


def clean_jsdoc(raw: str) -> str:
    """Convert a raw /** ... */ JSDoc comment into clean prose."""
    if not raw:
        return ""

    lines = [_LINE_STAR_RE.sub("", line) for line in raw.splitlines()]

    description_lines: list[str] = []
    in_block_tag = False
    for line in lines:
        stripped = line.strip()
        if _BLOCK_TAG_RE.match(stripped):
            in_block_tag = True
            continue
        if in_block_tag:
            if stripped == "" or line.startswith("   "):
                continue
            else:
                in_block_tag = False
        description_lines.append(line)

    text = "\n".join(description_lines)

    text = _INLINE_LINK_RE.sub(lambda m: _resolve_link(m.group(1)), text)
    text = _INLINE_BARE_RE.sub(" ", text)
    text = _BACKTICK_RE.sub(" ", text)
    text = _ANGLE_URL_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _html_mod.unescape(text)

    lines2 = []
    for line in text.splitlines():
        line = _MD_HEADING_RE.sub("", line)
        if _MD_HR_RE.match(line.strip()):
            continue
        lines2.append(line)
    text = "\n".join(lines2)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    result_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 2:
            result_lines.append(line)

    return " ".join(result_lines)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def discover_files(library_meta: dict) -> Iterable[Path]:
    name = library_meta["name"].strip()
    source_subdir = library_meta.get("source_subdir", "").strip()
    lib_dir = RAW_DIR / name / source_subdir if source_subdir else RAW_DIR / name
    if not lib_dir.is_dir():
        log.warning("[javascript] Library directory not found: %s", lib_dir)
        return []
    files = []
    for ext in _EXTENSIONS:
        files.extend(lib_dir.rglob(f"*{ext}"))
    excluded = {"node_modules", "dist", "build", "__tests__", "test", "tests",
                "spec", "specs", "coverage", "fixtures", "mocks", "__mocks__",
                "vendor", "e2e", "benchmark", "benchmarks", "example", "examples"}
    files = [
        f for f in files
        if not any(part in excluded for part in f.parts)
        and not f.name.endswith((".min.js", ".bundle.js", ".d.ts"))
    ]
    return sorted(files)


def extract_chunks(file_path: Path, library_meta: dict) -> list[dict]:
    """Extract JSDoc comment chunks from one JS/TS source file."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read %s: %s", file_path, exc)
        return []

    name = library_meta["name"].strip()
    lib_root = RAW_DIR / name
    try:
        rel_path = str(file_path.relative_to(lib_root))
    except ValueError:
        rel_path = str(file_path)

    chunks: list[dict] = []

    for match in _JSDOC_RE.finditer(source):
        raw_comment = match.group(1)
        cleaned = clean_jsdoc(raw_comment)
        if not cleaned:
            continue

        after_comment = source[match.end():match.end() + 200].lstrip()
        decl_match = _DECL_RE.search(after_comment[:200])
        element_name = ""
        if decl_match:
            element_name = decl_match.group(1) or decl_match.group(2) or ""

        raw_lower = raw_comment.lower()
        if "@class" in raw_lower or "@interface" in raw_lower or "@enum" in raw_lower:
            section_type = "class_description"
        elif element_name and after_comment.lstrip().startswith("class"):
            section_type = "class_description"
        else:
            section_type = "member_description"

        chunks.append({
            "section_type": section_type,
            "element_id": element_name,
            "class_name": "",
            "text": cleaned,
            "text_html": re.sub(r"\s+", " ", raw_comment).strip(),
            "extra": {"javadoc_version": "n/a"},
        })

    return chunks
