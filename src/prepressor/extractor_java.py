"""
extractor_java — Java-specific extraction rules for the unified preprocessor.

Parses `.java` sources cloned into ``files/raw/raw_java/<library>/`` and
extracts the Javadoc comment attached to each type / method / constructor /
field declaration. Mirrors the role of `extractor_python.py` (which uses
`ast`); here we use the `javalang` parser, which exposes each AST node's
preceding Javadoc as ``node.documentation``.

Exports the interface expected by `preprocess.py`:
    ECOSYSTEM, LIBRARIES_CSV, RAW_DIR
    discover_files(library_meta) -> Iterable[Path]
    extract_chunks(file_path, library_meta) -> list[Chunk]

Requires: ``pip install javalang``
"""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from typing import Iterable, Optional

try:
    import javalang  # type: ignore
    from javalang.tree import (
        ClassDeclaration, InterfaceDeclaration, EnumDeclaration,
        AnnotationDeclaration, MethodDeclaration, ConstructorDeclaration,
        FieldDeclaration,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "extractor_java requires the `javalang` package. "
        "Install with: pip install javalang"
    ) from exc

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module interface constants
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent

ECOSYSTEM = "java"
LIBRARIES_CSV = str(_HERE.parent / "libraries" / "librariesJAVA.csv")
RAW_DIR = _HERE.parent.parent / "files" / "raw" / "raw_java"

# ---------------------------------------------------------------------------
# Javadoc cleaning
# ---------------------------------------------------------------------------

# Block-tag lines we always drop (along with their indented continuations).
# These are metadata, not prose.
_BLOCK_TAG_RE = re.compile(
    r"^\s*@(param|return|throws|exception|see|since|deprecated|author|"
    r"version|serial|serialField|serialData|hidden|apiNote|implNote|"
    r"implSpec|category|spec|provides|uses)\b",
    re.IGNORECASE,
)

# Strip the "/**" opener and "*/" closer.
_OPEN_RE = re.compile(r"^\s*/\*\*+")
_CLOSE_RE = re.compile(r"\*+/\s*$")
# Each subsequent line typically starts with " * " — drop that prefix.
_LINE_STAR_RE = re.compile(r"^\s*\*\s?")

# Inline tags: {@code X}, {@link Pkg.Cls#m}, {@linkplain ...}, {@literal X},
# {@value ...}, {@docRoot}, {@inheritDoc}.
_INLINE_CODE_RE = re.compile(r"\{@code\s+([^{}]*?)\}", re.DOTALL)
_INLINE_LITERAL_RE = re.compile(r"\{@literal\s+([^{}]*?)\}", re.DOTALL)
_INLINE_LINK_RE = re.compile(
    r"\{@(?:link|linkplain)\s+([^{}]*?)\}", re.DOTALL
)
_INLINE_VALUE_RE = re.compile(r"\{@value\s+([^{}]*?)\}", re.DOTALL)
_INLINE_BARE_RE = re.compile(r"\{@(?:docRoot|inheritDoc)\s*\}")

# <pre>...</pre> blocks are code samples — drop them entirely.
_PRE_BLOCK_RE = re.compile(r"<pre\b[^>]*>.*?</pre>", re.IGNORECASE | re.DOTALL)
# <code>...</code> inline — keep contents, drop tags.
_CODE_BLOCK_RE = re.compile(r"<code\b[^>]*>(.*?)</code>",
                            re.IGNORECASE | re.DOTALL)
# Any remaining HTML tag — drop tags, keep text.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _resolve_link(target: str) -> str:
    """Render a {@link X#y label} target as a readable identifier."""
    target = target.strip()
    # If a label is given (e.g. "Foo#bar the bar"), take what's before the
    # first whitespace as the reference, then the rest is human label.
    parts = target.split(None, 1)
    ref = parts[0]
    label = parts[1] if len(parts) > 1 else ""
    # "Foo#bar" -> "Foo.bar";  "#bar" -> "bar";  "Foo" -> "Foo".
    ref = ref.lstrip("#").replace("#", ".")
    return label if label else ref


def clean_javadoc(raw: str) -> str:
    """Convert a raw /** ... */ Javadoc comment into clean prose."""
    if not raw:
        return ""

    text = raw
    # Strip the comment delimiters.
    text = _OPEN_RE.sub("", text, count=1)
    text = _CLOSE_RE.sub("", text, count=1)

    # Per-line: strip leading " * ".
    lines = [_LINE_STAR_RE.sub("", line) for line in text.splitlines()]

    # Drop every line from the first block-tag (@param, @return, ...)
    # onward — those are metadata and their indented continuations.
    description_lines: list[str] = []
    for line in lines:
        if _BLOCK_TAG_RE.match(line):
            break
        description_lines.append(line)
    text = "\n".join(description_lines)

    # Drop <pre>...</pre> code samples wholesale (before unwrapping <code>).
    text = _PRE_BLOCK_RE.sub(" ", text)

    # Inline tags → readable text.
    text = _INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = _INLINE_LITERAL_RE.sub(lambda m: m.group(1), text)
    text = _INLINE_VALUE_RE.sub(lambda m: m.group(1), text)
    text = _INLINE_LINK_RE.sub(lambda m: _resolve_link(m.group(1)), text)
    text = _INLINE_BARE_RE.sub(" ", text)

    # <code>...</code> → keep contents.
    text = _CODE_BLOCK_RE.sub(lambda m: m.group(1), text)
    # Remaining HTML tags → drop.
    text = _HTML_TAG_RE.sub(" ", text)

    # HTML entities → real characters.
    text = html.unescape(text)

    # Collapse whitespace and discard near-empty lines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    result_lines: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 2:
            result_lines.append(line)

    return " ".join(result_lines)


# ---------------------------------------------------------------------------
# AST walk
# ---------------------------------------------------------------------------

_TYPE_NODES = (
    ClassDeclaration, InterfaceDeclaration,
    EnumDeclaration, AnnotationDeclaration,
)


def _members_of(type_node) -> list:
    """Return the declarations inside a type's body (best-effort)."""
    return list(getattr(type_node, "body", []) or [])


def _walk_type(type_node, parent: str, source_file: str) -> list[dict]:
    """Recursively yield raw chunk dicts (text still raw javadoc) for one type."""
    rows: list[dict] = []
    name = getattr(type_node, "name", "") or ""
    qual = f"{parent}.{name}" if parent else name

    doc = getattr(type_node, "documentation", None)
    if doc:
        rows.append({
            "section_type": "class_description",
            "element_id": qual,
            "class_name": qual,
            "raw_doc": doc,
        })

    for member in _members_of(type_node):
        m_doc: Optional[str] = getattr(member, "documentation", None)

        if isinstance(member, _TYPE_NODES):
            # Nested type — recurse.
            rows.extend(_walk_type(member, qual, source_file))
            continue

        if not m_doc:
            continue

        if isinstance(member, (MethodDeclaration, ConstructorDeclaration)):
            m_name = getattr(member, "name", "") or ""
            rows.append({
                "section_type": "member_description",
                "element_id": f"{qual}.{m_name}",
                "class_name": qual,
                "raw_doc": m_doc,
            })
        elif isinstance(member, FieldDeclaration):
            # A FieldDeclaration can declare multiple variables; use the first
            # for element_id (rare to have docs on multi-var declarations).
            decls = getattr(member, "declarators", []) or []
            f_name = decls[0].name if decls else ""
            rows.append({
                "section_type": "field_description",
                "element_id": f"{qual}.{f_name}" if f_name else qual,
                "class_name": qual,
                "raw_doc": m_doc,
            })
        # Other member kinds (e.g. enum constants without their own javadoc)
        # are skipped.

    return rows


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def discover_files(library_meta: dict) -> Iterable[Path]:
    name = library_meta["name"].strip()
    source_subdir = library_meta.get("source_subdir", "").strip()
    lib_dir = RAW_DIR / name / source_subdir if source_subdir else RAW_DIR / name
    if not lib_dir.is_dir():
        return []
    return sorted(lib_dir.rglob("*.java"))


def extract_chunks(file_path: Path, library_meta: dict) -> list[dict]:
    """Parse one .java file and return Chunk dicts (with cleaned text)."""
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

    try:
        tree = javalang.parse.parse(source)
    except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError) as exc:
        description = getattr(exc, "description", None) or str(exc) or type(exc).__name__
        at = getattr(exc, "at", None)
        position = f" at position {at}" if at is not None else ""
        log.warning("Parse error in %s (%s): %s%s",
                    rel_path, type(exc).__name__, description, position)
        return []
    except Exception as exc:  # noqa: BLE001 — javalang occasionally throws odd errors
        log.warning("Unexpected parse failure in %s (%s): %s",
                    rel_path, type(exc).__name__, exc or repr(exc))
        return []

    raw_rows: list[dict] = []
    for type_node in (tree.types or []):
        if isinstance(type_node, _TYPE_NODES):
            raw_rows.extend(_walk_type(type_node, parent="", source_file=rel_path))

    chunks: list[dict] = []
    for r in raw_rows:
        cleaned = clean_javadoc(r["raw_doc"])
        if not cleaned:
            continue
        chunks.append({
            "section_type": r["section_type"],
            "element_id": r["element_id"],
            "class_name": r["class_name"],
            "text": cleaned,
            "text_html": re.sub(r"\s+", " ", r["raw_doc"]).strip(),
            "extra": {"javadoc_version": "n/a"},
        })
    return chunks
