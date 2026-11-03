"""
rq3_readme_scope_audit: which of the 100 human READMEs in the RQ3 corpus
actually belong to the library they are paired with?

Why. Both extractors pick the human README as: a README inside the scoped
module directory if one exists, otherwise the README at the clone root
(rq3_extract_java.py / rq3_extract_python.py, `find_top_level_readme`
fallback). For a single-package repo the root README *is* the library's
README. For a monorepo it is the parent project's front page, e.g.
odoo14-addon-sale-exception was paired with OCA/sale-workflow's addon
table, and ph-oton-audit with the ph-oton umbrella README. Found while
chasing WPS outliers; this script measures how widespread it is.

Re-derives the README choice from the local clones (files/raw/rq3/) and the
latest extract-log row, rather than trusting the logs alone, then
classifies each library:

  own_module      README found inside the scoped module directory
  root_single     README at clone root, repo holds one package  -> fine
  root_monorepo   README at clone root, repo holds several packages
                  -> parent README, mismatched to the library

"Holds several packages" = at least MONOREPO_MIN build manifests below the
root (pom.xml, build.gradle[.kts], setup.py, pyproject.toml, setup.cfg,
__manifest__.py for Odoo addons), ignoring test/example/doc paths. The
manifest count and whether the root README names the package are both
written out, so borderline calls can be checked by hand.

Outputs:
    files/corpus/rq3/rq3_readme_scope_audit.csv

Usage:
    venv/bin/python3 src/generation/rq3_readme_scope_audit.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RQ3_DIR = ROOT / "files" / "corpus" / "rq3"
RAW_DIR = ROOT / "files" / "raw" / "rq3"
LIB_CSV = RQ3_DIR / "rq3_libraries_prose.csv"
OUT = RQ3_DIR / "rq3_readme_scope_audit.csv"
# Hand grading of the root_monorepo cases, kept in its own file so that
# re-running this script cannot silently discard it (it did once).
# severe  = README describes an unrelated or much larger project
# partial = root README of a focused project, module is one component of it
# anything flagged root_monorepo and absent here is 'benign' (the module is
# effectively the library); anything not flagged is 'ok'.
TIERS = RQ3_DIR / "rq3_readme_scope_tiers.csv"

MANIFESTS = {"pom.xml", "build.gradle", "build.gradle.kts", "setup.py",
             "pyproject.toml", "setup.cfg", "__manifest__.py"}
IGNORE = {"test", "tests", "testing", "example", "examples", "sample",
          "samples", "doc", "docs", "benchmark", "benchmarks", "demo",
          "testdata", "fixtures", "node_modules", ".git"}
MONOREPO_MIN = 2


def latest_log_rows() -> dict[tuple[str, str], dict]:
    rows = {}
    for eco in ("java", "python"):
        with open(RQ3_DIR / f"extract_log_{eco}.csv", newline="") as f:
            for r in csv.DictReader(f):
                rows[(eco, r["package_name"])] = r   # append-only: last wins
    return rows


def has_readme(d: Path) -> bool:
    return d.is_dir() and any(p.is_file() and p.stem.lower().startswith("readme")
                              for p in d.iterdir())


def multi_module_root(clone: Path) -> bool:
    """True if the ROOT build file declares sub-projects.

    Counting per-directory manifests only catches Maven-style layouts, where
    every module carries its own pom.xml. An sbt or Gradle multi-project
    build declares its modules in one root file and leaves the module
    directories bare, so `module_dirs` returns 0 for them and a genuine
    monorepo looks like a single-package repo, geotrellis-s3 and
    geotrellis-vector were both accepted that way before this check existed
   , each paired with the umbrella GeoTrellis README.
    """
    checks = [
        ("pom.xml", "<modules>"),
        ("settings.gradle", "include"),
        ("settings.gradle.kts", "include"),
    ]
    for name, marker in checks:
        p = clone / name
        if p.is_file() and marker in p.read_text(encoding="utf-8", errors="replace"):
            return True
    sbt = clone / "build.sbt"
    if sbt.is_file():
        text = sbt.read_text(encoding="utf-8", errors="replace")
        # "lazy val x = project" / "= Project(", more than one means a
        # multi-project build rather than a single library with a root alias.
        if text.count("= project") + text.count("= Project(") >= 2:
            return True
    return False


def module_dirs(clone: Path) -> set[Path]:
    """Directories below the root that carry their own build manifest."""
    found = set()
    for p in clone.rglob("*"):
        if p.name in MANIFESTS and p.is_file() and p.parent != clone:
            rel = [s.lower() for s in p.relative_to(clone).parts[:-1]]
            if not any(s in IGNORE for s in rel):
                found.add(p.parent)
    return found


def short_name(pkg: str) -> str:
    name = pkg.split(":")[-1]
    return name.removeprefix("odoo14-addon-").replace("-", "_").lower()


def main() -> None:
    libs = (pd.read_csv(LIB_CSV)
              .query("source == 'human'")[["library", "ecosystem", "text"]])
    logs = latest_log_rows()

    out = []
    for _, lib in libs.iterrows():
        eco, pkg = lib.ecosystem, lib.library
        log = logs[(eco, pkg)]
        clone = RAW_DIR / eco / log["safe_name"]
        scoped = log["scoped_to_subdir"]
        scoped_dir = clone / scoped if scoped else clone

        n_modules = len(module_dirs(clone))
        multi_root = multi_module_root(clone)
        if scoped and has_readme(scoped_dir):
            source, verdict = scoped, "own_module"
        else:
            source = "."
            verdict = ("root_monorepo"
                       if (n_modules >= MONOREPO_MIN or multi_root)
                       else "root_single")

        text = lib.text.lower()
        sn = short_name(pkg)
        out.append({
            "ecosystem": eco, "library": pkg, "scoped_to_subdir": scoped,
            "readme_from": source, "n_submodule_manifests": n_modules,
            "readme_mentions_name": sn in text.replace("-", "_"),
            "multi_module_root": multi_root,
            "readme_words": len(lib.text.split()),
            "verdict": verdict,
        })

    df = pd.DataFrame(out).sort_values(["verdict", "ecosystem", "library"])

    hand = (pd.read_csv(TIERS).set_index("library").tier
            if TIERS.exists() else pd.Series(dtype=str))
    df["tier"] = [hand.get(lib, "benign") if v == "root_monorepo" else "ok"
                  for lib, v in zip(df.library, df.verdict)]
    ungraded = df[(df.verdict == "root_monorepo") & (df.tier == "benign")]
    if len(ungraded):
        print(f"{len(ungraded)} root_monorepo librar{'y' if len(ungraded) == 1 else 'ies'} "
              f"not in {TIERS.name} — defaulted to 'benign', check by hand:")
        for lib in ungraded.library:
            print(f"  {lib}")
        print()

    df.to_csv(OUT, index=False)
    print(f"Wrote {OUT}\n")
    print(pd.crosstab(df.verdict, df.ecosystem, margins=True), "\n")
    print(df[df.verdict == "root_monorepo"]
          [["ecosystem", "library", "scoped_to_subdir",
            "n_submodule_manifests", "readme_mentions_name", "readme_words"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
