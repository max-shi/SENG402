"""
genre_split_pilot: Feasibility pilot for a tutorial-vs-reference genre
contrast (matched pairs, same library both genres), reusing whatever of
the locked confirmatory corpus is already cloned locally rather than
re-cloning anything yet.

For each already-cloned library, splits its already-discovered prose
files (find_prose_files, from confirmatory_preprocessor.py, this
already restricts to README* + docs/**-tree files, so no new file
discovery logic needed) into two buckets by path-segment signal:
tutorial-like (tutorial(s), guide(s), quickstart, getting-started,
walkthrough, howto) vs reference-like (api, reference, apidocs). The
README itself is excluded from both buckets, it's a third "overview"
genre, not part of this specific contrast. Applies the same F5 (>=500
words) and F6 (English) filters as the main pipeline to each bucket
independently. A library is "matched-pair ready" iff BOTH buckets pass.

This is a pilot, not a final run: only libraries whose clone directory
already exists on disk (files/raw/confirmatory/<eco>/<safe_name>/) are
checked, to get a realistic yield estimate before deciding whether
re-cloning the rest of the locked 400 is worth it.

Usage:
    venv/bin/python3 src/corpus/genre_split_pilot.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from confirmatory_preprocessor import (  # noqa: E402
    find_prose_files, extract_prose, apply_word_cap, english_fraction,
    safe_name, WORD_MIN, ENGLISH_MIN_FRACTION,
)

ROOT = Path(__file__).resolve().parents[2]
CLONE_ROOT = ROOT / "files" / "raw" / "confirmatory"
MANIFEST = ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
OUT_CSV = ROOT / "files" / "corpus" / "genre_split_pilot_results.csv"

TUTORIAL_SIGNALS = {"tutorial", "tutorials", "guide", "guides", "quickstart",
                    "quick-start", "getting-started", "getting_started",
                    "walkthrough", "howto", "how-to"}
REFERENCE_SIGNALS = {"api", "reference", "references", "apidocs", "api-docs"}


def classify_genre(path: Path, clone_dir: Path) -> str | None:
    """tutorial | reference | None, based on any path segment (relative
    to clone_dir, excluding the filename itself) matching a signal set.
    The README itself is never classified into either bucket."""
    if path.stem.lower().startswith("readme"):
        return None
    parts = [p.lower() for p in path.relative_to(clone_dir).parts[:-1]]
    if any(p in TUTORIAL_SIGNALS for p in parts):
        return "tutorial"
    if any(p in REFERENCE_SIGNALS for p in parts):
        return "reference"
    return None


def score_bucket(paths: list[Path]) -> tuple[int, bool, bool]:
    """(word_count, passes_f5, passes_f6) for the concatenated prose of
    `paths`."""
    chunks = [extract_prose(p) for p in paths]
    chunks = [c for c in chunks if c]
    if not chunks:
        return 0, False, False
    combined = "\n\n".join(chunks)
    _, wc, _ = apply_word_cap(combined)
    f5 = wc >= WORD_MIN
    en_frac, _ = english_fraction(combined)
    f6 = en_frac >= ENGLISH_MIN_FRACTION
    return wc, f5, f6


def main() -> None:
    with open(MANIFEST) as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} libraries in the corrected locked manifest.")

    results = []
    n_on_disk = 0
    for r in rows:
        eco = r["ecosystem"]
        sname = safe_name(r["package_name"])
        clone_dir = CLONE_ROOT / eco / sname
        if not clone_dir.is_dir():
            continue
        n_on_disk += 1

        files = find_prose_files(clone_dir)
        tut_files = [p for p in files if classify_genre(p, clone_dir) == "tutorial"]
        ref_files = [p for p in files if classify_genre(p, clone_dir) == "reference"]

        tut_wc, tut_f5, tut_f6 = score_bucket(tut_files)
        ref_wc, ref_f5, ref_f6 = score_bucket(ref_files)
        matched_ready = tut_f5 and tut_f6 and ref_f5 and ref_f6

        results.append({
            "package_name": r["package_name"], "ecosystem": eco,
            "n_tutorial_files": len(tut_files), "tutorial_words": tut_wc,
            "tutorial_ready": tut_f5 and tut_f6,
            "n_reference_files": len(ref_files), "reference_words": ref_wc,
            "reference_ready": ref_f5 and ref_f6,
            "matched_ready": matched_ready,
        })

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    n_tut_ready = sum(1 for r in results if r["tutorial_ready"])
    n_ref_ready = sum(1 for r in results if r["reference_ready"])
    n_matched = sum(1 for r in results if r["matched_ready"])
    print(f"\nChecked {n_on_disk} libraries with a clone already on disk "
          f"(of {len(rows)} in the locked sample).")
    print(f"  tutorial bucket >=500 words + EN: {n_tut_ready}")
    print(f"  reference bucket >=500 words + EN: {n_ref_ready}")
    print(f"  BOTH (matched-pair ready): {n_matched}")
    print(f"\nWrote {OUT_CSV}")

    if n_matched:
        print("\nMatched-ready libraries:")
        for r in results:
            if r["matched_ready"]:
                print(f"  {r['ecosystem']:6s} {r['package_name']:50s} "
                      f"tut={r['tutorial_words']:6d}w ref={r['reference_words']:6d}w")


if __name__ == "__main__":
    main()
