"""
rq3_overlap_check: Contamination/overlap check for RQ3 generated docs,
per the RQ3 plan ("resolved: build the check, now
more essential" after the pilot's own contamination finding).

Two independent checks, both flagging suspected contamination, the LLM
reproducing knowledge of the real library rather than inferring purely from
the given API surface. Thresholds are decided here, calibrated against every
existing pilot + sensitivity output, before this runs on the real
400-library generation (per the RQ3 plan's explicit requirement to decide the
threshold before, not after, seeing the real results).

1. **Surface overlap**: word n-gram containment between the generated text
   and the real human README. This is the check the RQ3 plan originally specified:
   catches near-verbatim reproduction of the actual documentation.
2. **Internal-path leak**: the prompt-sensitivity check found a second,
   distinct contamination signature that (1) cannot catch: the model
   correctly naming real internal module paths (e.g. `xsdata.codegen.
   models.Class`) that appear in neither the given API surface nor the
   README, recalled from training data on the real source, not copied
   from anything this pipeline gave it. This check extracts dotted-path-
   like tokens from the generated text and flags any that match a real
   file in the actual cloned repository (files/raw/rq3/python/<library>/)
   but were absent from the given API surface. Calibration below confirms
   this catches the exact cases found by hand in the sensitivity check
   (pyspellchecker, web-fragments, xsdata) and that check (1) does not.

Usage:
    venv/bin/python3 src/generation/rq3_overlap_check.py --calibrate
        # Runs over every existing pilot + sensitivity output.
        # Writes files/corpus/rq3/overlap_check/calibration_results.csv
    venv/bin/python3 src/generation/rq3_overlap_check.py --full
        # Runs over every generated doc in files/corpus/rq3/full_generation/
        # (both ecosystems), the real 400-library x 2-model run.
        # Writes files/corpus/rq3/overlap_check/full_generation_check_results.csv
    venv/bin/python3 src/generation/rq3_overlap_check.py \\
        --library xsdata --text-file path/to/generated.txt [--ecosystem java|python]
        # Ad-hoc check of one generated file against one library.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from rq3_pilot_generate import safe_name, PILOT_LIBRARIES, MODELS  # noqa: E402
from rq3_prompt_sensitivity import SENSITIVITY_LIBRARIES, VARIANTS  # noqa: E402
from rq3_sensitivity_v4 import VARIANT as V4_VARIANT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
API_SURFACE_DIR = ROOT / "files" / "corpus" / "rq3" / "api_surface" / "python"
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only" / "python"
RAW_DIR = ROOT / "files" / "raw" / "rq3" / "python"
PILOT_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_generation"
SENSITIVITY_DIR = ROOT / "files" / "corpus" / "rq3" / "sensitivity"
OUT_DIR = ROOT / "files" / "corpus" / "rq3" / "overlap_check"

# Long word n-grams so generic phrasing doesn't register as "overlap",
# a conservative, literature-typical cutoff for near-duplicate text
# (containment fraction of long n-grams), not tuned to this corpus's
# observed range. See the calibration run: nothing generated so far comes
# close to it, which is itself informative (the RQ3 plan's originally-envisioned
# failure mode, near-verbatim README reproduction, has not actually been
# observed yet; the internal-path leak below is the failure mode that has).
NGRAM_N = 8
NGRAM_OVERLAP_THRESHOLD = 0.5

_WORD_RE = re.compile(r"[a-z0-9']+")
_DOTTED_RE = re.compile(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*){1,}\b", re.IGNORECASE)

# Real repo directories that exist on disk but aren't part of the library's
# own importable surface, would otherwise register as "internal modules"
# and produce false leak flags.
_NON_SURFACE_DIR_PARTS = {"tests", "test", "docs", "doc", "examples", "scripts",
                          "build", "dist", ".git", "venv", ".tox"}


def _word_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = _WORD_RE.findall(text.lower())
    if len(words) < n:
        return set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def ngram_containment(generated: str, reference: str, n: int = NGRAM_N) -> float:
    """Fraction of the generated text's own n-grams that also appear in the
    reference text. Directional, not symmetric Jaccard, the question is
    how much of what was GENERATED could have been lifted from the
    reference, not how similar the two texts are overall."""
    gen_grams = _word_ngrams(generated, n)
    if not gen_grams:
        return 0.0
    ref_grams = _word_ngrams(reference, n)
    return len(gen_grams & ref_grams) / len(gen_grams)


_SOURCE_GLOB = {"python": "*.py", "java": "*.java"}
_SOURCE_EXT_LEN = {"python": 3, "java": 5}  # len(".py"), len(".java")
_INIT_FILENAME = {"python": "__init__.py"}  # Java has no equivalent


def real_module_paths(repo_dir: Path, ecosystem: str = "python") -> set[str]:
    """Every real dotted module path derivable from the actual cloned
    source tree, e.g. files/raw/rq3/python/xsdata/xsdata/codegen/
    transformer.py -> {"xsdata.codegen.transformer", "codegen.transformer"},
    excluding tests/docs/build directories. Registers every trailing
    sub-path (not just the full repo-root-relative path) since generated
    text typically references the importable package path, which may
    start below the repo root, this also absorbs Java's `src/main/java/`
    -style source-root prefixes for free, without needing to special-case
    them: the real package (e.g. "com.foo.Bar") is still among the
    trailing sub-paths even though some *other* trailing sub-paths (e.g.
    "java.com.foo.Bar") are nonsense no model would ever generate.

    Java support added later: originally Python-only (glob "*.py",
    strip the extension), which meant this returned an empty set for
    every Java repo and made internal_path_leaks() silently unable to
    flag anything on the Java half of a run, found by checking, not
    assumed, when 0/100 Java rows in the first full-generation check had
    any internal_path_leaks value at all."""
    paths: set[str] = set()
    if not repo_dir.is_dir():
        return paths
    glob = _SOURCE_GLOB[ecosystem]
    ext_len = _SOURCE_EXT_LEN[ecosystem]
    init_name = _INIT_FILENAME.get(ecosystem)
    for src_file in repo_dir.rglob(glob):
        parts = list(src_file.relative_to(repo_dir).parts)
        if any(p in _NON_SURFACE_DIR_PARTS for p in parts):
            continue
        if init_name and parts[-1] == init_name:
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-ext_len]
        for start in range(len(parts)):
            sub = parts[start:]
            if len(sub) >= 2:
                paths.add(".".join(sub))
    return paths


def dotted_tokens(text: str) -> set[str]:
    return {m.group(0) for m in _DOTTED_RE.finditer(text)}


# Per-ecosystem file-header comment format: rq3_extract_python.py labels
# each block "# path/to/file.py" (see confirmatory_preprocessor reuse);
# rq3_extract_java.py labels each block "// path/to/File.java" (its own
# `blocks.append(f"// {rel}\n{block}")`, verified against that file
# directly rather than assumed, when this Java support
# was added, after finding real_module_paths() was Python-only above).
_FILECOMMENT_RE = {
    "python": re.compile(r"^#\s*([\w./-]+\.py)\s*$", re.MULTILINE),
    "java": re.compile(r"^//\s*([\w./-]+\.java)\s*$", re.MULTILINE),
}


def _strip_ext_and_init(parts: list[str], ecosystem: str) -> list[str]:
    if ecosystem == "python" and parts[-1] == "__init__.py":
        return parts[:-1]
    ext_len = _SOURCE_EXT_LEN[ecosystem]
    parts = list(parts)
    parts[-1] = parts[-1][:-ext_len]
    return parts


def surface_file_paths(api_surface: str, ecosystem: str = "python") -> set[str]:
    """Dotted-path equivalents of every file-header comment in the given
    API surface (e.g. "# web_fragments/fragment.py" ->
    "web_fragments.fragment", or "// src/main/java/com/foo/Bar.java" ->
    "com.foo.Bar" among other trailing sub-paths), including trailing
    sub-paths. The extractor labels each block with the real file's
    slash-separated path; a model turning that into the equivalent import/
    package path (slash -> dot, strip extension) is reformatting something
    it was actually given, not demonstrating memorized knowledge, so this
    must count as "in the surface" the same as a literal dotted token
    would."""
    paths: set[str] = set()
    for m in _FILECOMMENT_RE[ecosystem].finditer(api_surface):
        parts = _strip_ext_and_init(m.group(1).split("/"), ecosystem)
        for start in range(len(parts)):
            sub = parts[start:]
            if len(sub) >= 2:
                paths.add(".".join(sub))
    return paths


def surface_package_paths(api_surface: str, ecosystem: str = "python") -> set[str]:
    """Package-level (directory) dotted paths implied by the *parent
    directories* of every file-header comment in the given API surface,
    e.g. being shown 'xsdata/codegen/handlers/x.py' (or the Java analogue,
    several files under 'com/foo/codegen/handlers/') and several siblings
    already tells the reader that 'xsdata.codegen' /
    'xsdata.codegen.handlers' (or 'com.foo.codegen' / '...handlers') exist
    as real package groupings, even though no single given file is named
    exactly that.

    Found by manual spot-check (Python side): the original
    leak check flagged every generated xsdata doc for mentioning bare
    package names like `xsdata.codegen` or `xsdata.utils`, but every one
    of those packages had multiple sibling files already given in the
    surface, so naming the shared parent package is not evidence of
    anything beyond what was handed to the model. Unlike
    surface_file_paths (which only credits the exact given file), this
    credits any contiguous slice of a given file's parent-directory
    chain, since a package name can legitimately be referenced starting
    from any importable sub-level. Java support added later,
    alongside the rest of this file's Java extension."""
    packages: set[str] = set()
    for m in _FILECOMMENT_RE[ecosystem].finditer(api_surface):
        parts = _strip_ext_and_init(m.group(1).split("/"), ecosystem)
        parent_parts = parts[:-1]  # drop the leaf module itself
        for i in range(len(parent_parts)):
            for j in range(i + 2, len(parent_parts) + 1):
                packages.add(".".join(parent_parts[i:j]))
    return packages


def internal_path_leaks(generated: str, api_surface: str, repo_dir: Path,
                         ecosystem: str = "python") -> set[str]:
    """Dotted-path tokens in the generated text that (a) correspond to a
    real file in the actual cloned repository, and (b) do not appear
    anywhere in the given API surface, and (c) aren't just a package-level
    grouping already implied by given sibling files, real internal
    structure the model could only know from training data, not from the
    input it was actually given or trivially inferable from it."""
    real_paths = real_module_paths(repo_dir, ecosystem)
    if not real_paths:
        return set()
    gen_tokens = dotted_tokens(generated)
    surface_tokens = (
        dotted_tokens(api_surface)
        | surface_file_paths(api_surface, ecosystem)
        | surface_package_paths(api_surface, ecosystem)
    )
    return {t for t in gen_tokens if t in real_paths} - surface_tokens


def check_one(library: str, generated_path: Path, variant: str = "",
              ecosystem: str = "python") -> dict:
    sname = safe_name(library)
    generated = generated_path.read_text(encoding="utf-8")
    api_surface_dir = ROOT / "files" / "corpus" / "rq3" / "api_surface" / ecosystem
    readme_dir = ROOT / "files" / "corpus" / "rq3" / "readme_only" / ecosystem
    raw_dir = ROOT / "files" / "raw" / "rq3" / ecosystem

    api_surface_path = api_surface_dir / f"{sname}.txt"
    readme_path = readme_dir / f"{sname}.txt"
    # Use the safe_name'd clone dir, not the raw package_name, the two
    # diverge for every Java package (groupId:artifactId -> a colon,
    # which safe_name() maps to '_'; the clone dir on disk uses the
    # safe_name form). This was silently masked for Python: the small
    # pilot set's library names all happened to equal their own
    # safe_name(), so raw_dir / library and raw_dir / sname were always
    # the same path there. Found while adding Java support
    # above, by checking why repo_dir.is_dir() was false even after
    # fixing real_module_paths()'s glob, not assumed.
    repo_dir = raw_dir / sname

    api_surface = api_surface_path.read_text(encoding="utf-8") if api_surface_path.exists() else ""
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    overlap = ngram_containment(generated, readme) if readme else 0.0
    leaks = internal_path_leaks(generated, api_surface, repo_dir, ecosystem)

    return {
        "library": library,
        "ecosystem": ecosystem,
        "variant": variant,
        "file": generated_path.name,
        "ngram_overlap": round(overlap, 4),
        "ngram_flag": overlap >= NGRAM_OVERLAP_THRESHOLD,
        "internal_path_leaks": "; ".join(sorted(leaks)),
        "path_leak_flag": len(leaks) > 0,
    }


def run_calibration() -> list[dict]:
    rows: list[dict] = []

    for pkg in PILOT_LIBRARIES:
        sname = safe_name(pkg)
        for _provider, _model, out_suffix in MODELS:
            path = PILOT_DIR / f"{sname}_{out_suffix}.txt"
            if path.exists():
                rows.append(check_one(pkg, path, variant=f"pilot_{out_suffix}"))

    for pkg in SENSITIVITY_LIBRARIES:
        sname = safe_name(pkg)
        for variant in VARIANTS + [V4_VARIANT]:
            for _provider, _model, out_suffix in MODELS:
                path = SENSITIVITY_DIR / f"{sname}_{variant}_{out_suffix}.txt"
                if path.exists():
                    rows.append(check_one(pkg, path, variant=f"{variant}_{out_suffix}"))

    return rows


FULL_GEN_DIR = ROOT / "files" / "corpus" / "rq3" / "full_generation"
FULL_GEN_MANIFEST = (
    ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
)


def run_full_check(manifest: Path = FULL_GEN_MANIFEST,
                   selected_only: bool = False) -> list[dict]:
    """Check every generated doc under files/corpus/rq3/full_generation/
    (both ecosystems), the real 400-library x 2-model run, not just the
    pilot + sensitivity libraries run_calibration() covers."""
    if not manifest.exists():
        raise SystemExit(f"manifest not found: {manifest}")
    with open(manifest) as f:
        pkgs = [(r["package_name"], r["ecosystem"]) for r in csv.DictReader(f)
                if not selected_only or r.get("selected") == "true"]

    rows: list[dict] = []
    for pkg, eco in pkgs:
        sname = safe_name(pkg)
        for _provider, _model, out_suffix in MODELS:
            path = FULL_GEN_DIR / eco / f"{sname}_{out_suffix}.txt"
            if path.exists():
                rows.append(check_one(pkg, path, variant=out_suffix, ecosystem=eco))
    return rows


def _write_and_report(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    flagged = [r for r in rows if r["ngram_flag"] or r["path_leak_flag"]]
    print(f"Checked {len(rows)} generated docs. {len(flagged)} flagged "
          f"({len(flagged) / len(rows):.1%}).")
    print(f"Max ngram_overlap observed: {max(r['ngram_overlap'] for r in rows):.4f} "
          f"(threshold {NGRAM_OVERLAP_THRESHOLD})")
    for r in flagged:
        print(f"  FLAGGED  {r.get('ecosystem', ''):8s} {r['library']:30s} {r['variant']:20s} "
              f"ngram={r['ngram_overlap']:.3f}  leaks=[{r['internal_path_leaks']}]")
    print(f"\nWrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true",
                    help="Run over every existing pilot + sensitivity output.")
    ap.add_argument("--full", action="store_true",
                    help="Run over every generated doc in files/corpus/rq3/full_generation/ "
                         "(both ecosystems) — the real 400-library x 2-model run.")
    ap.add_argument("--manifest", type=Path, default=FULL_GEN_MANIFEST,
                    help=("Manifest supplying the libraries to check. The "
                          "clean re-draw spans three frames, so "
                          "its subset CSV is passed here; rows are filtered "
                          "to selected=true when that column exists."))
    ap.add_argument("--library", help="Ad-hoc mode: library name (matches files/raw/rq3/<eco>/<name>).")
    ap.add_argument("--text-file", type=Path, help="Ad-hoc mode: path to a generated text file.")
    ap.add_argument("--ecosystem", default="python",
                    help="Ad-hoc mode only: ecosystem for --library/--text-file (default python).")
    args = ap.parse_args()

    if args.calibrate:
        rows = run_calibration()
        _write_and_report(rows, OUT_DIR / "calibration_results.csv")
        return

    if args.full:
        rows = run_full_check(args.manifest, selected_only=True)
        _write_and_report(rows, OUT_DIR / "full_generation_check_results.csv")
        return

    if args.library and args.text_file:
        row = check_one(args.library, args.text_file, ecosystem=args.ecosystem)
        print(row)
        return

    ap.error("pass --calibrate, --full, or both --library and --text-file")


if __name__ == "__main__":
    main()
