"""
Preprocessor (Python) — Docstring Corpus Builder

Walks cloned Python library source trees, extracts docstrings from all
modules, classes, functions, and methods using the AST, and writes a flat
CSV in the same schema as the Java corpus (corpus/corpus.csv).

Usage:
    python preprocessor_python.py
"""

import ast
import csv
import logging
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LIBRARIES_CSV = "librariesPYTHON.csv"
RAW_DIR = Path("raw_python")
CORPUS_DIR = Path("corpus")
CORPUS_CSV = CORPUS_DIR / "python_corpus.csv"
LOG_DIR = Path("logs")
PREPROCESS_LOG = LOG_DIR / "preprocess_log_python.csv"

CORPUS_COLUMNS = [
    "library",
    "ecosystem",
    "domain",
    "organisation",
    "javadoc_version",   # kept for schema compatibility; always "n/a" for Python
    "source_file",
    "class_name",
    "section_type",
    "element_id",
    "text",
    "text_html",         # not applicable for Python; stores raw docstring
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


def node_qualname(node: ast.AST, parent_name: str = "") -> str:
    """Build a qualified name like ClassName.method_name."""
    name = getattr(node, "name", "")
    if parent_name:
        return f"{parent_name}.{name}"
    return name


# ---------------------------------------------------------------------------
# Stage 1 — Text cleaning
# ---------------------------------------------------------------------------

# Sphinx-style field markers (:param x:, :type x:, :returns:, :rtype:, :raises x:, etc.)
_SPHINX_FIELD_RE = re.compile(r"^\s*:[a-zA-Z][\w ]*:")

# NumPy / Google section headers (e.g. "Parameters", "Returns", "Args", "Raises", "Notes")
_SECTION_HEADER_RE = re.compile(
    r"^\s*(Parameters|Returns|Return|Args|Arguments|Raises|Yields|"
    r"Attributes|Notes|Note|Examples?|References?|See Also|Todo)\s*$",
    re.IGNORECASE,
)

# RST section underlines (lines of only ---- or ~~~~ or ==== etc.)
_RST_UNDERLINE_RE = re.compile(r"^\s*[-=~^*+#]{3,}\s*$")

# Inline Sphinx field at end of a prose line (:param x:, :returns:, etc.)
_INLINE_SPHINX_RE = re.compile(
    r"\s*:(param|type|returns?|rtype|raises?|var|ivar|cvar)\b.*$",
    re.IGNORECASE,
)


def _strip_noise(lines: list[str]) -> list[str]:
    """
    Remove doctest blocks, Sphinx field lists, NumPy/Google section headers,
    and RST underlines from a list of (dedented) lines.
    """
    result = []
    in_doctest = False
    in_param_section = False

    for line in lines:
        stripped = line.strip()

        # --- doctest blocks: lines starting with >>> or ... continuation ---
        if stripped.startswith(">>>"):
            in_doctest = True
            continue
        if in_doctest:
            if stripped.startswith("...") or (stripped and not stripped.startswith(">>>")):
                # doctest output line or continuation — skip until blank line
                if stripped == "":
                    in_doctest = False
                continue
            else:
                in_doctest = False

        # --- RST underlines ---
        if _RST_UNDERLINE_RE.match(line):
            continue

        # --- NumPy/Google section headers ---
        if _SECTION_HEADER_RE.match(stripped):
            in_param_section = True
            continue

        # --- Sphinx field markers (:param ...:, :rtype:, etc.) ---
        if _SPHINX_FIELD_RE.match(line):
            in_param_section = True
            continue

        # --- indented continuation of a param section ---
        if in_param_section:
            if stripped == "":
                in_param_section = False
                continue
            # if indented more than normal it's still param content
            if line.startswith("    ") or line.startswith("\t"):
                continue
            else:
                in_param_section = False

        result.append(line)

    return result


def clean_docstring(raw: str) -> str:
    """
    Normalise a raw docstring to clean prose:
      1. Dedent (remove common leading whitespace)
      2. Strip doctest blocks, Sphinx/NumPy/Google param sections, RST underlines
      3. Collapse runs of spaces/tabs to a single space per line
      4. Collapse 3+ consecutive blank lines to 2
      5. Strip leading/trailing whitespace
      6. Discard lines with fewer than 2 tokens
      7. Rejoin with a single space
    """
    lines = raw.expandtabs(4).splitlines()

    # Determine common indent from non-empty lines after the first
    non_empty = [l for l in lines[1:] if l.strip()]
    if non_empty:
        indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        dedented = [lines[0]] + [l[indent:] for l in lines[1:]]
    else:
        dedented = lines

    dedented = _strip_noise(dedented)

    # Strip inline Sphinx fields trailing on the same line as prose
    # e.g. "Sends a GET request. :param \*\*kwargs: Optional arguments..."
    dedented = [_INLINE_SPHINX_RE.sub("", l) for l in dedented]

    text = "\n".join(dedented)
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
# Stage 2 — Filtering
# ---------------------------------------------------------------------------

def passes_filter(text: str) -> bool:
    """Return True if the chunk has at least 5 words."""
    return len(text.split()) >= 5


# ---------------------------------------------------------------------------
# Stage 3 — AST extraction
# ---------------------------------------------------------------------------

def extract_docstrings(source: str, source_file: str) -> list[dict]:
    """
    Parse a Python source file and extract all docstrings with metadata.

    Returns a list of dicts with keys:
        class_name, section_type, element_id, text, text_html
    """
    try:
        tree = ast.parse(source, filename=source_file)
    except SyntaxError as exc:
        log.warning("SyntaxError in %s: %s", source_file, exc)
        return []

    rows: list[dict] = []

    def _visit(node: ast.AST, parent_class: str = "") -> None:
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            # Still recurse into the node's children
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
            if parent_class:
                section_type = "member_description"
                class_name = parent_class
            else:
                section_type = "member_description"
                class_name = ""
            element_id = node_qualname(node, parent_class)

        else:
            _recurse(node, parent_class)
            return

        rows.append({
            "class_name": class_name,
            "section_type": section_type,
            "element_id": element_id,
            "text": docstring,
            "text_html": docstring,
        })

        _recurse(node, class_name if isinstance(node, ast.ClassDef) else parent_class)

    def _recurse(node: ast.AST, parent_class: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                _visit(child, parent_class)

    _visit(tree)
    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_file(
    py_path: Path,
    library: dict,
    raw_root: Path,
) -> list[dict]:
    """Process a single .py file and return corpus rows."""
    try:
        source = py_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read %s: %s", py_path, exc)
        return []

    source_file = str(py_path.relative_to(raw_root))
    raw_rows = extract_docstrings(source, source_file)

    result: list[dict] = []
    for row in raw_rows:
        cleaned = clean_docstring(row["text"])
        if not passes_filter(cleaned):
            continue
        result.append({
            "library": library["name"].strip(),
            "ecosystem": library.get("ecosystem", "").strip().lower(),
            "domain": library.get("domain", "").strip(),
            "organisation": library.get("organisation", "").strip(),
            "javadoc_version": "n/a",
            "source_file": source_file,
            "class_name": row["class_name"],
            "section_type": row["section_type"],
            "element_id": row["element_id"],
            "text": cleaned,
            "text_html": re.sub(r"\s+", " ", row.get("text_html", "")).strip(),
        })

    return result


def main() -> None:
    libraries = load_libraries(LIBRARIES_CSV)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    total_rows = 0

    with (
        open(CORPUS_CSV, "w", newline="", encoding="utf-8") as out_f,
        open(PREPROCESS_LOG, "w", newline="", encoding="utf-8") as log_f,
    ):
        writer = csv.DictWriter(out_f, fieldnames=CORPUS_COLUMNS)
        writer.writeheader()

        log_writer = csv.writer(log_f)
        log_writer.writerow([
            "timestamp", "library", "source_file", "class_name",
            "chunks_extracted", "status", "error",
        ])

        for library in libraries:
            if library.get("ecosystem", "").strip().lower() != "python":
                continue

            name = library["name"].strip()
            source_subdir = library.get("source_subdir", "").strip()
            lib_dir = RAW_DIR / name / source_subdir if source_subdir else RAW_DIR / name

            if not lib_dir.is_dir():
                log.warning("No raw directory for library '%s' — skipping (expected: %s)", name, lib_dir)
                log_writer.writerow([datetime.now().isoformat(), name, "", "", 0, "SKIP", f"no directory: {lib_dir}"])
                continue

            py_files = sorted(lib_dir.rglob("*.py"))
            log.info("Processing library '%s': %d .py files found", name, len(py_files))

            lib_rows = 0
            for py_path in py_files:
                rows = process_file(py_path, library, RAW_DIR / name)
                source_file = str(py_path.relative_to(RAW_DIR / name))

                if rows:
                    class_name = rows[0]["class_name"]
                    log_writer.writerow([
                        datetime.now().isoformat(), name, source_file, class_name,
                        len(rows), "OK", "",
                    ])
                else:
                    log_writer.writerow([
                        datetime.now().isoformat(), name, source_file, "", 0, "EMPTY", "zero rows extracted",
                    ])

                for row in rows:
                    writer.writerow(row)
                    lib_rows += 1

            log.info("Finished library '%s': %d docstring chunks extracted", name, lib_rows)
            total_rows += lib_rows
            log_f.flush()

    log.info("Corpus complete: %d total rows appended to %s", total_rows, CORPUS_CSV)


if __name__ == "__main__":
    main()
