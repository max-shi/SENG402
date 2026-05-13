"""
extractor_python — Python-specific extraction rules for the unified preprocessor.

Exports the same interface as extractor_java:
    ECOSYSTEM, LIBRARIES_CSV, RAW_DIR
    discover_files(library_meta) -> Iterable[Path]
    extract_chunks(file_path, library_meta) -> list[Chunk]
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module interface constants
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent

ECOSYSTEM = "python"
LIBRARIES_CSV = str(_HERE.parent / "libraries" / "librariesPYTHON.csv")
RAW_DIR = _HERE.parent.parent / "files" / "raw" / "raw_python"

# ---------------------------------------------------------------------------
# Docstring noise stripping
# ---------------------------------------------------------------------------
_SPHINX_FIELD_RE = re.compile(r"^\s*:[a-zA-Z][\w ]*:")
_SECTION_HEADER_RE = re.compile(
    r"^\s*(Parameters|Returns|Return|Args|Arguments|Raises|Yields|"
    r"Attributes|Notes|Note|Examples?|References?|See Also|Todo)\s*$",
    re.IGNORECASE,
)
_RST_UNDERLINE_RE = re.compile(r"^\s*[-=~^*+#]{3,}\s*$")
_INLINE_SPHINX_RE = re.compile(
    r"\s*:(param|type|returns?|rtype|raises?|var|ivar|cvar)\b.*$",
    re.IGNORECASE,
)

# Inline markup that produces noise for LIWC
# :class:`Foo`, :meth:`bar`, :func:`baz`, :attr:`x`, :exc:`E`, :data:`d`, etc.
_RST_ROLE_RE = re.compile(r":[a-zA-Z]+:`[^`]*`")
# Plain backtick spans: `foo` or ``foo``
_BACKTICK_RE = re.compile(r"``?[^`]+``?")
# Angle-bracket URLs: <https://...>
_ANGLE_URL_RE = re.compile(r"<https?://[^>]*>")


def _strip_noise(lines: list[str]) -> list[str]:
    result = []
    in_doctest = False
    in_param_section = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(">>>"):
            in_doctest = True
            continue
        if in_doctest:
            if stripped.startswith("...") or (stripped and not stripped.startswith(">>>")):
                if stripped == "":
                    in_doctest = False
                continue
            else:
                in_doctest = False

        if _RST_UNDERLINE_RE.match(line):
            continue

        if _SECTION_HEADER_RE.match(stripped):
            in_param_section = True
            continue

        if _SPHINX_FIELD_RE.match(line):
            in_param_section = True
            continue

        if in_param_section:
            if stripped == "":
                in_param_section = False
                continue
            if line.startswith("    ") or line.startswith("\t"):
                continue
            else:
                in_param_section = False

        result.append(line)

    return result


def _clean_docstring(raw: str) -> str:
    lines = raw.expandtabs(4).splitlines()

    non_empty = [l for l in lines[1:] if l.strip()]
    if non_empty:
        indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        dedented = [lines[0]] + [l[indent:] for l in lines[1:]]
    else:
        dedented = lines

    dedented = _strip_noise(dedented)
    dedented = [_INLINE_SPHINX_RE.sub("", l) for l in dedented]

    text = "\n".join(dedented)
    text = _RST_ROLE_RE.sub("", text)
    text = _BACKTICK_RE.sub("", text)
    text = _ANGLE_URL_RE.sub("", text)
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
# AST extraction
# ---------------------------------------------------------------------------

def _qualname(node: ast.AST, parent_name: str = "") -> str:
    name = getattr(node, "name", "")
    if parent_name:
        return f"{parent_name}.{name}"
    return name


def _extract_docstrings(source: str, source_file: str) -> list[dict]:
    try:
        tree = ast.parse(source, filename=source_file)
    except SyntaxError as exc:
        log.warning("SyntaxError in %s: %s", source_file, exc)
        return []

    rows: list[dict] = []

    def _visit(node: ast.AST, parent_class: str = "") -> None:
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            _recurse(node, parent_class)
            return

        name = getattr(node, "name", "")
        if isinstance(node, ast.Module):
            section_type = "module_description"
            element_id = ""
            class_name = ""
        elif isinstance(node, ast.ClassDef):
            section_type = "class_description"
            element_id = name
            class_name = name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            section_type = "member_description"
            class_name = parent_class if parent_class else ""
            element_id = _qualname(node, parent_class)
        else:
            _recurse(node, parent_class)
            return

        rows.append({
            "class_name": class_name,
            "section_type": section_type,
            "element_id": element_id,
            "raw_doc": docstring,
        })
        _recurse(node, class_name if isinstance(node, ast.ClassDef) else parent_class)

    def _recurse(node: ast.AST, parent_class: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef, ast.Module)):
                _visit(child, parent_class)

    _visit(tree)
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
    return sorted(lib_dir.rglob("*.py"))


def extract_chunks(file_path: Path, library_meta: dict) -> list[dict]:
    """Parse one .py file and return a list of Chunk dicts (with pre-cleaned text)."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read %s: %s", file_path, exc)
        return []

    name = library_meta["name"].strip()
    lib_root = RAW_DIR / name
    rel_path = str(file_path.relative_to(lib_root))
    raw_rows = _extract_docstrings(source, rel_path)

    chunks: list[dict] = []
    for r in raw_rows:
        cleaned = _clean_docstring(r["raw_doc"])
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
