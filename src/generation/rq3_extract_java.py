"""
rq3_extract_java: Extract API surface + README-only text for RQ3 (Java).

Mirrors rq3_extract_python.py (see that file's docstring for the full
RQ3 design rationale, this file only notes where Java differs). For
each re-cloned Java library under files/raw/rq3/java/ (see
rq3_reclone.py), this produces two artefacts per library, both needed
by the RQ3 design:

1. API surface (files/corpus/rq3/api_surface/java/<safe_name>.txt),
   public class/interface/enum signatures only: method and constructor
   signatures, enum constants, never bodies or Javadoc (the human
   documentation surface this design exists to keep out of the LLM's
   prompt, the plan).
2. README-only human text (files/corpus/rq3/readme_only/java/<safe_name>.txt),
   same as the Python extractor, via confirmatory_preprocessor.extract_prose.

Java has no stdlib equivalent of Python's `ast` module, so signature
reconstruction uses `javalang` (pure-Python Java parser, already
installed in venv/) instead. package_name in the source manifest is a
Maven coordinate `groupId:artifactId`; scoping to the right module
directory inside a multi-module monorepo (the same problem
find_scoped_root solves for Python, see that function's docstring)
uses the artifactId, since Maven/Gradle module directories are
conventionally named after it.

Parity notes vs. the Python extractor (deliberate, not oversights):
  - Only `public` top-level types are extracted (package-private
    top-level types aren't part of the public API from outside the
    package). Interface members are implicitly public unless marked
    `private` (Java 9+ private interface methods); class/enum members
    require an explicit `public` modifier, matching Java's actual
    visibility rules where Python only had name-underscore convention.
  - Only one level of nesting: a type's own methods/constructors, not
    fields (implementation state, not callable surface) and not nested
    types (same "one level of class nesting" scope as the Python side).
  - Annotation type declarations (`@interface`) are not extracted,
    rare in this corpus and their members are default-value accessors,
    not general API surface.

Source list is files/corpus/frame_locked_corrected/sample_manifest_final.csv
(the monorepo-duplication-corrected 400, RULES.md),
filtered to ecosystem=java (read-only, never modified).

Usage:
    venv/bin/python3 src/generation/rq3_extract_java.py [--libraries START-END]
                                                      [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import javalang

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_cloner import safe_name  # noqa: E402
from confirmatory_preprocessor import (  # noqa: E402
    IGNORE_HARD,
    IGNORE_SOFT,
    extract_prose,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
)
RAW_DIR = ROOT / "files" / "raw" / "rq3"
RQ3_DIR = ROOT / "files" / "corpus" / "rq3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Same schema as extract_log_python.csv (n_public_functions here counts
# methods+constructors) so the two logs are directly comparable/mergeable.
EXTRACT_LOG_COLS = [
    "timestamp", "package_name", "ecosystem", "safe_name",
    "scoped_to_subdir", "n_source_files_parsed", "n_source_files_skipped",
    "n_public_classes", "n_public_functions",
    "api_surface_word_count", "large_surface_flag", "surface_truncated",
    "readme_found", "readme_word_count",
    "status", "reason",
]

_JAVA_SKIP_STEMS = ("package-info", "module-info")
_README_PRIORITY_EXT = [".md", ".markdown", ".adoc", ".txt", ""]


# ---------------------------------------------------------------------------
# Source-file discovery (reuses the main corpus's directory-exclusion policy)
# ---------------------------------------------------------------------------

def find_source_files(clone_dir: Path) -> list[Path]:
    """Return a stable, sorted list of the library's own .java source
    files, excludes vendor/build/test/example trees, same as the
    doc-prose finder in the main pipeline, plus package-info.java,
    module-info.java, and common test-suffix naming conventions
    (FooTest.java, FooTests.java, FooIT.java, TestFoo.java)."""
    if not clone_dir.is_dir():
        return []
    out: list[Path] = []
    for path in clone_dir.rglob("*.java"):
        parts_lower = [p.lower() for p in path.parts]
        if any(seg in IGNORE_HARD for seg in parts_lower):
            continue
        if any(seg in IGNORE_SOFT for seg in parts_lower):
            continue
        stem = path.stem
        if stem.lower() in _JAVA_SKIP_STEMS:
            continue
        if (stem.startswith("Test") or stem.endswith("Test")
                or stem.endswith("Tests") or stem.endswith("IT")
                or stem.endswith("TestCase")):
            continue
        out.append(path)
    out.sort(key=lambda p: str(p).lower())
    return out


_LARGE_SURFACE_WORDS = 20_000  # flag threshold, not a hard cap, see log column

_IGNORE_ALL = IGNORE_HARD | IGNORE_SOFT
# Maven/Gradle Scala-module convention: artifactId carries a
# cross-build suffix (e.g. `log4cats-slf4j_3`, `arrow-mtl_2.13`) that
# the on-disk module directory usually drops.
_SCALA_SUFFIX_RE = re.compile(r"_(?:\d+(?:\.\d+)*)$")


def _artifact_id(package_name: str) -> str:
    """The part of a `groupId:artifactId` Maven coordinate that
    Maven/Gradle module directories are conventionally named after."""
    return package_name.rsplit(":", 1)[-1]


def _repo_name(repository_url: str) -> str:
    """Last path segment of the repo URL, e.g.
    'https://github.com/neo4j/neo4j' -> 'neo4j'."""
    name = repository_url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name


def _candidate_dir_names(artifact: str, repo_name: str = "") -> list[str]:
    names = [artifact]
    stripped = _SCALA_SUFFIX_RE.sub("", artifact)
    if stripped != artifact:
        names.append(stripped)
    # Module directories conventionally drop a repeated product/repo-name
    # prefix (e.g. artifactId 'neo4j-schema' in repo 'neo4j/neo4j' lives
    # in a directory just called 'schema', at community/schema).
    if repo_name:
        prefix = f"{repo_name}-"
        if artifact.startswith(prefix) and len(artifact) > len(prefix):
            names.append(artifact[len(prefix):])
    return names


def _split_variants(artifact: str) -> list[Path]:
    """Path-shaped variants of a hyphenated artifactId, e.g.
    'crd-generator-apt' -> crd/generator/apt (fully split) as well as
    crd-generator/apt and crd/generator-apt (one nesting level, split at
    each hyphen in turn), real repos use all three conventions (e.g.
    fabric8io/kubernetes-client nests crd-generator-apt as
    crd-generator/apt, not a 3-way split)."""
    if "-" not in artifact:
        return []
    parts = artifact.split("-")
    variants = [Path(*parts)]
    for i in range(1, len(parts)):
        variants.append(Path("-".join(parts[:i]), "-".join(parts[i:])))
    return variants


def _pom_artifact_id(pom_path: Path) -> Optional[str]:
    """The POM's *own* artifactId (the direct child of <project>), not a
    <parent> or <dependency> artifactId, ElementTree's .find() with a
    bare (non-'.//') tag only searches immediate children, so a nested
    <parent><artifactId> is never mistaken for the module's own identity.
    Namespace-agnostic: Maven POMs almost always declare the default
    'http://maven.apache.org/POM/4.0.0' namespace, which turns every tag
    into '{that-uri}artifactId' under ElementTree, stripped here rather
    than hard-coded, since some old/generated POMs omit it entirely."""
    try:
        root = ET.parse(pom_path).getroot()
    except ET.ParseError:
        return None
    for child in root:
        tag = child.tag.rsplit("}", 1)[-1]  # strip '{namespace}' if present
        if tag == "artifactId" and child.text:
            return child.text.strip()
    return None


def _pom_scoped_candidates(clone_dir: Path, artifact: str) -> list[Path]:
    """Directories whose own pom.xml declares exactly this artifactId.
    General fix for monorepos where the module directory name doesn't
    follow the artifactId-derived naming conventions _candidate_dir_names
    /_split_variants assume (e.g. Azure/Oracle/Groovy: 'sdk/keyvault/
    azure-keyvault-secrets-spring-boot-starter' or similar layouts with
    no fixed relationship between path and coordinate), reads the build
    file's own declared identity instead of guessing it from the path."""
    out: list[Path] = []
    for pom in clone_dir.rglob("pom.xml"):
        parts_lower = [p.lower() for p in pom.parts]
        if any(seg in _IGNORE_ALL for seg in parts_lower):
            continue
        if _pom_artifact_id(pom) == artifact:
            out.append(pom.parent)
    return out


_MONOREPO_POM_THRESHOLD = 5  # more distinct modules than this -> presume real monorepo


def _looks_like_monorepo(clone_dir: Path) -> bool:
    """Cheap, self-contained monorepo signal: count distinct pom.xml files
    (outside IGNORE_HARD/IGNORE_SOFT trees). An ordinary single-purpose
    library has 1 (occasionally 2-4 for a small -api/-core/-impl split);
    azure-sdk-for-java and groovy-eclipse had 885 and 112 respectively
   . Doesn't need the cross-manifest repository_url-
    sharing check the Python extractor's dedup fix used, because that
    signal is 0 for Java here (no two *sampled* packages share a repo in
    this manifest) even though several individual repos are still, on
    their own, large multi-module monorepos most of whose modules were
    never sampled at all.
    """
    n = 0
    for pom in clone_dir.rglob("pom.xml"):
        parts_lower = [p.lower() for p in pom.parts]
        if any(seg in _IGNORE_ALL for seg in parts_lower):
            continue
        n += 1
        if n > _MONOREPO_POM_THRESHOLD:
            return True
    return False


def find_scoped_root(clone_dir: Path, package_name: str, repository_url: str = "") -> Optional[Path]:
    """
    Multi-module Maven/Gradle monorepos are at least as common on the
    Java side of this corpus as the Python side (e.g. neo4j/neo4j,
    fabric8io/kubernetes-client, apache/camel-quarkus), same problem
    the Python extractor's find_scoped_root solves, same approach:
    gather every name-variant candidate directory, drop anything
    inside an IGNORE_HARD/IGNORE_SOFT segment, and score the rest by
    how much real API surface they actually yield. Falls back to the
    whole clone (subject to the large-surface flag) if nothing scores
    above zero.

    Candidates come from two independent sources: (a) the original
    directory-name heuristics below, which cover the common convention
    of module-dir-name == artifactId (possibly minus a repo-name prefix
    or Scala suffix); and (b) _pom_scoped_candidates, which reads each
    pom.xml's own declared artifactId directly rather than guessing it
    from a path, needed because some monorepos (found via
    3.7M/1.9M/587K-word outliers: Azure SDK, Oracle OCI SDK,
    Groovy-Eclipse) use module layouts with no derivable relationship
    between directory name and Maven coordinate at all. Both sources
    feed the same scoring step, so a wrong or partial name-guess candidate
    never wins over a real POM match if the POM match actually contains
    parseable source.

    Returns None (rather than clone_dir) when no module could be
    confidently identified *and* the clone looks like a genuine
    multi-module monorepo (_looks_like_monorepo), see the comment above
    the two return sites for why silently substituting the whole clone
    is unsafe in that specific case, unlike the ordinary single-repo case.
    """
    artifact = _artifact_id(package_name)
    repo_name = _repo_name(repository_url) if repository_url else ""
    seen: set[str] = set()
    candidates: list[Path] = []
    for name in _candidate_dir_names(artifact, repo_name):
        for p in clone_dir.rglob(name):
            if p.is_dir() and ".git" not in p.parts and str(p) not in seen:
                seen.add(str(p))
                candidates.append(p)
    for rel in _split_variants(artifact):
        p = clone_dir / rel
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            candidates.append(p)
    for p in _pom_scoped_candidates(clone_dir, artifact):
        if str(p) not in seen:
            seen.add(str(p))
            candidates.append(p)

    valid = []
    for p in candidates:
        rel_parts = [s.lower() for s in p.relative_to(clone_dir).parts]
        if any(seg in _IGNORE_ALL for seg in rel_parts):
            continue
        # A directory nested inside a 'src/main/java' (or similar) tree
        # is a Java *package* path, not a module boundary, it can share
        # a name with the artifact purely by package-naming coincidence
        # (e.g. 'org.neo4j.kernel.api.impl.schema' ends in a directory
        # literally called 'schema', which is not the neo4j-schema
        # module). Real Maven/Gradle module roots always sit above
        # their own src/ tree, never inside one.
        if "src" in rel_parts:
            continue
        valid.append(p)

    # Falling back to the *whole clone* is only a safe substitute for "this
    # package's own module" when the clone isn't a multi-module monorepo in
    # the first place (the common case: an ordinary single-purpose repo,
    # where clone_dir already *is* the right answer). When the repo clearly
    # is a large multi-module monorepo (many pom.xml files) and no specific
    # module could be confidently identified, either because zero
    # candidates existed at all (found: azure-keyvault-secrets-
    # spring-boot-starter's artifactId appears in no pom.xml anywhere in
    # azure-sdk-for-java at all, likely a stale/imprecise repository_url
    # in the manifest, not an extraction problem) or because the one
    # candidate found has no source of its own (groovy-eclipse-batch: a
    # real module, correctly located, but it's a packaging/assembly module
    # with zero .java files), treating the whole monorepo as this
    # package's surface would hand the LLM an arbitrary, unrelated slice of
    # *other* packages' code under this package's name. That's not a size
    # problem the large-surface truncation cap can safely paper over: it's
    # a correctness problem, so it's reported as unresolved instead.
    monorepo = _looks_like_monorepo(clone_dir)

    if not valid:
        return None if monorepo else clone_dir

    def score(p: Path) -> int:
        return sum(
            1 for f in find_source_files(p) if extract_api_surface(f) is not None
        )

    best_score, best_p = max(
        ((score(p), p) for p in valid),
        key=lambda t: (t[0], -len(t[1].parts)),
    )
    if best_score > 0:
        return best_p
    return None if monorepo else clone_dir


def find_top_level_readme(clone_dir: Path) -> Optional[Path]:
    """The single top-level README, what a human reader (and the
    LLM's generated equivalent) would be compared against, not every
    README in every submodule."""
    candidates = [
        p for p in clone_dir.iterdir()
        if p.is_file() and p.stem.lower().startswith("readme")
    ]
    if not candidates:
        return None

    def rank(p: Path) -> int:
        try:
            return _README_PRIORITY_EXT.index(p.suffix.lower())
        except ValueError:
            return len(_README_PRIORITY_EXT)

    candidates.sort(key=rank)
    return candidates[0]


# ---------------------------------------------------------------------------
# Signature reconstruction (no bodies, no Javadoc)
# ---------------------------------------------------------------------------

def _type_to_str(t) -> str:
    if t is None:
        return "void"
    if isinstance(t, javalang.tree.BasicType):
        base = t.name
    else:
        base = t.name
        sub_type = getattr(t, "sub_type", None)
        if sub_type is not None:
            base = f"{base}.{_type_to_str(sub_type)}"
        args = getattr(t, "arguments", None)
        if args:
            base += "<" + ", ".join(_type_argument_to_str(a) for a in args) + ">"
    dims = getattr(t, "dimensions", None) or []
    return base + "[]" * len(dims)


def _type_argument_to_str(a) -> str:
    if a is None or a.type is None:
        return "?"
    inner = _type_to_str(a.type)
    if a.pattern_type == "extends":
        return f"? extends {inner}"
    if a.pattern_type == "super":
        return f"? super {inner}"
    return inner


def _format_type_params(type_params) -> str:
    if not type_params:
        return ""
    parts = []
    for tp in type_params:
        s = tp.name
        if tp.extends:
            s += " extends " + " & ".join(_type_to_str(e) for e in tp.extends)
        parts.append(s)
    return "<" + ", ".join(parts) + "> "


def _format_param(p) -> str:
    t = _type_to_str(p.type)
    if p.varargs:
        t += "..."
    return f"{t} {p.name}"


_SHOWN_MODIFIERS = ("static", "final", "abstract", "synchronized",
                     "native", "default")


def _is_public_member(modifiers: set, implicitly_public: bool) -> bool:
    if "private" in modifiers:
        return False
    if implicitly_public:
        return True
    return "public" in modifiers


def _format_member_signature(m, implicitly_public: bool) -> Optional[str]:
    mods = m.modifiers or set()
    if not _is_public_member(mods, implicitly_public):
        return None
    shown = ["public"] + [mod for mod in _SHOWN_MODIFIERS if mod in mods]
    prefix = " ".join(shown) + " "
    type_params = _format_type_params(getattr(m, "type_parameters", None))
    is_ctor = isinstance(m, javalang.tree.ConstructorDeclaration)
    ret = "" if is_ctor else _type_to_str(m.return_type) + " "
    params = ", ".join(_format_param(p) for p in (m.parameters or []))
    throws = (" throws " + ", ".join(m.throws)) if getattr(m, "throws", None) else ""
    return f"{prefix}{type_params}{ret}{m.name}({params}){throws};"


_TYPE_KEYWORD = {
    javalang.tree.ClassDeclaration: "class",
    javalang.tree.InterfaceDeclaration: "interface",
    javalang.tree.EnumDeclaration: "enum",
}


def _format_type_header(t) -> str:
    keyword = _TYPE_KEYWORD[type(t)]
    type_params = _format_type_params(getattr(t, "type_parameters", None))
    header = f"public {keyword} {type_params}{t.name}".replace("  ", " ")
    extends = getattr(t, "extends", None)
    if extends is not None:
        variants = extends if isinstance(extends, list) else [extends]
        header += " extends " + ", ".join(_type_to_str(e) for e in variants)
    implements = getattr(t, "implements", None)
    if implements:
        header += " implements " + ", ".join(_type_to_str(i) for i in implements)
    return header + " {"


def _members_of(t) -> list:
    if isinstance(t, javalang.tree.EnumDeclaration):
        return t.body.declarations or []
    return t.body or []


def _format_type_block(t) -> Optional[str]:
    if "public" not in (t.modifiers or set()):
        return None

    implicitly_public = isinstance(t, javalang.tree.InterfaceDeclaration)
    body_lines: list[str] = []

    if isinstance(t, javalang.tree.EnumDeclaration):
        constants = [c.name for c in (t.body.constants or [])]
        if constants:
            body_lines.append("    " + ", ".join(constants) + ";")

    for m in _members_of(t):
        if isinstance(m, (javalang.tree.MethodDeclaration,
                          javalang.tree.ConstructorDeclaration)):
            sig = _format_member_signature(m, implicitly_public)
            if sig is not None:
                body_lines.append("    " + sig)
        # FieldDeclaration and nested TypeDeclaration are intentionally
        # skipped, parity with the Python extractor's "one level of
        # nesting, methods/classes only" scope (see module docstring).

    if not body_lines:
        return None  # a public type with zero public members isn't
        # part of the callable API surface either.

    return "\n".join([_format_type_header(t), *body_lines, "}"])


def extract_api_surface(java_path: Path) -> Optional[str]:
    """Return the public type signatures in `java_path`, or None if the
    file has no public surface or fails to parse (syntax the parser
    doesn't support, encoding issues, module-info.java slipping past
    the stem filter, etc.)."""
    try:
        src = java_path.read_text(encoding="utf-8", errors="replace")
        tree = javalang.parse.parse(src)
    except Exception:
        # javalang raises its own JavaSyntaxError/LexerError subclasses
        # (not stdlib SyntaxError) for anything it can't parse; a
        # RecursionError is also possible on pathologically nested
        # generics. All are skip-worthy for one file, not fatal for the
        # library, matches the Python extractor's per-file contract.
        return None

    blocks = [
        block for t in tree.types
        if (block := _format_type_block(t)) is not None
    ]
    return "\n\n".join(blocks) if blocks else None


# ---------------------------------------------------------------------------
# Per-library processing
# ---------------------------------------------------------------------------

def process_library(row: dict) -> dict:
    pkg = row["package_name"]
    eco = "java"
    sname = safe_name(pkg)
    clone_dir = RAW_DIR / eco / sname

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_name": pkg, "ecosystem": eco, "safe_name": sname,
        "scoped_to_subdir": "", "n_source_files_parsed": 0,
        "n_source_files_skipped": 0,
        "n_public_classes": 0, "n_public_functions": 0,
        "api_surface_word_count": 0, "large_surface_flag": "false",
        "surface_truncated": "false",
        "readme_found": "false",
        "readme_word_count": 0, "status": "", "reason": "",
    }

    if not clone_dir.is_dir():
        entry["status"] = "clone_missing"
        entry["reason"] = f"clone dir not found: {clone_dir}"
        return entry

    scoped_root = find_scoped_root(clone_dir, pkg, row.get("repository_url", ""))
    if scoped_root is None:
        # Confirmed multi-module monorepo, no module for this specific
        # artifactId could be identified. Deliberately does NOT fall back
        # to reading anything from clone_dir, for a real monorepo, the
        # root README describes the whole project, not this one package,
        # so it would be just as mismatched as the API surface would be.
        # Both sides of the pair are reported unresolved together, rather
        # than silently mixing a real README with a wrong-scope surface
        # (or vice versa).
        entry["status"] = "no_api_surface"
        entry["reason"] = (
            "repository is a multi-module monorepo and no module matching "
            "this artifactId could be identified (not falling back to the "
            "whole clone: would attribute unrelated modules' code to this "
            "package)"
        )
        return entry
    if scoped_root != clone_dir:
        entry["scoped_to_subdir"] = str(scoped_root.relative_to(clone_dir))

    blocks: list[str] = []
    n_parsed = n_skipped = n_types = n_members = 0
    for path in find_source_files(scoped_root):
        block = extract_api_surface(path)
        if block is None:
            n_skipped += 1
            continue
        n_parsed += 1
        rel = path.relative_to(clone_dir)
        blocks.append(f"// {rel}\n{block}")
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith(("public class ", "public interface ",
                                     "public enum ")):
                n_types += 1
            elif stripped.endswith(";") and "(" in stripped:
                n_members += 1

    entry["n_source_files_parsed"] = n_parsed
    entry["n_source_files_skipped"] = n_skipped
    entry["n_public_classes"] = n_types
    entry["n_public_functions"] = n_members

    # README search runs unconditionally, before the no-API-surface check
    # below, the two are independent artefacts (a repo can have zero
    # parseable Java yet a perfectly good README: Scala/Kotlin source,
    # or a Maven BOM with no code at all). Previously this block sat
    # after an early `return` on empty `blocks`, so readme_found was
    # silently false for every no_api_surface library even when a real
    # README existed (found auditing the 40 no_api_surface
    # cases: guvnor-inbox-api and net.openhft:assertions-disabled both
    # have real top-level READMEs that were never even searched for).
    # Same monorepo-vs-single-repo fallback logic as the Python
    # extractor: prefer a README inside the scoped module directory,
    # fall back to the repo root if the module has none of its own.
    readme_path = find_top_level_readme(scoped_root)
    if readme_path is None and scoped_root != clone_dir:
        readme_path = find_top_level_readme(clone_dir)
    if readme_path is not None:
        readme_text = extract_prose(readme_path)
        if readme_text.strip():
            entry["readme_found"] = "true"
            entry["readme_word_count"] = len(readme_text.split())
            readme_dir = RQ3_DIR / "readme_only" / eco
            readme_dir.mkdir(parents=True, exist_ok=True)
            (readme_dir / f"{sname}.txt").write_text(readme_text, encoding="utf-8")

    if not blocks:
        entry["status"] = "no_api_surface"
        entry["reason"] = "no parseable public signatures found"
        return entry

    # Backstop cap for libraries that are
    # genuinely this large even after correct POM-based scoping, not
    # expected to fire often now that find_scoped_root reads pom.xml
    # directly, but still needed for real single-module libraries with
    # an unusually big surface (the Java analogue of tensorflow/boto on
    # the Python side). Truncates at whole-block (whole-file) boundaries,
    # never mid-signature; blocks are already in a stable sorted order
    # (find_source_files), so the kept prefix is deterministic.
    full_word_count = sum(len(b.split()) for b in blocks)
    if full_word_count > _LARGE_SURFACE_WORDS:
        entry["large_surface_flag"] = "true"
        entry["surface_truncated"] = "true"
        kept: list[str] = []
        kept_words = 0
        for b in blocks:
            b_words = len(b.split())
            if kept and kept_words + b_words > _LARGE_SURFACE_WORDS:
                break
            kept.append(b)
            kept_words += b_words
        blocks = kept

    api_text = "\n\n".join(blocks)
    api_dir = RQ3_DIR / "api_surface" / eco
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / f"{sname}.txt").write_text(api_text, encoding="utf-8")
    entry["api_surface_word_count"] = len(api_text.split())

    entry["status"] = "ready"
    return entry


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_range(value: str) -> tuple[int, int]:
    if "-" in value:
        a, b = value.split("-", 1)
        return int(a), int(b)
    n = int(value)
    return n, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--libraries", help="Range within this pass, e.g. '1-10' (1-indexed)."
    )
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not SOURCE_MANIFEST.exists():
        raise SystemExit(f"source manifest not found: {SOURCE_MANIFEST}")

    with open(SOURCE_MANIFEST) as f:
        rows = [r for r in csv.DictReader(f) if r["ecosystem"] == "java"]

    if args.libraries:
        start, end = parse_range(args.libraries)
        rows = rows[start - 1:end]
    if args.limit > 0:
        rows = rows[:args.limit]

    RQ3_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RQ3_DIR / "extract_log_java.csv"
    log_exists = log_path.exists()
    log_fh = open(log_path, "a" if log_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_fh, fieldnames=EXTRACT_LOG_COLS)
    if not log_exists:
        writer.writeheader()

    counts: dict[str, int] = {}
    try:
        for i, row in enumerate(rows, 1):
            log.info("[%d/%d] %s", i, len(rows), row["package_name"])
            try:
                entry = process_library(row)
            except Exception as exc:  # noqa: BLE001, one bad repo must not
                # abort the other 199 (mirrors the Python extractor's
                # per-library crash isolation).
                log.exception("  CRASHED on %s: %s", row["package_name"], exc)
                entry = {col: "" for col in EXTRACT_LOG_COLS}
                entry.update({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "package_name": row["package_name"], "ecosystem": "java",
                    "safe_name": safe_name(row["package_name"]),
                    "status": "crashed", "reason": str(exc)[:300],
                })
            writer.writerow(entry)
            log_fh.flush()
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            log.info(
                "  -> %s  types=%d members=%d api_words=%d readme_words=%s",
                entry["status"], entry["n_public_classes"],
                entry["n_public_functions"], entry["api_surface_word_count"],
                entry["readme_word_count"] if entry["readme_found"] == "true" else "-",
            )
    finally:
        log_fh.close()

    print("\n--- extract summary ---")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
