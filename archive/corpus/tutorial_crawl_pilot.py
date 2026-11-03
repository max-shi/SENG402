"""
tutorial_crawl_pilot: Feasibility pilot for crawling deployed Python
docs sites (Sphinx/Read the Docs, mostly) to build a tutorial-genre
bucket, matched per-library against the README already on file (the
"overview" genre). Python-only, per the docs_url_recon.py finding that
Java's docs_url field is universally dead (points to a defunct
appdoc.app).

For each candidate (from docs_url_recon_results.csv, classification in
{readthedocs, other_sphinx, github_pages, other_docusaurus}):
  1. Fetch the landing page, collect same-host links.
  2. Keep links whose URL path or link text matches a tutorial signal
     (tutorial(s), guide(s), quickstart, getting-started, walkthrough,
     howto), same signal set as the git-based pilot, applied to
     online pages instead of repo paths.
  3. Fetch up to MAX_PAGES matching pages (bounded crawl, this is a
     feasibility pilot, not a full site crawl), extract prose the same
     way confirmatory_preprocessor.py does for HTML (BeautifulSoup,
     strip code/nav/script/etc.), concatenate, apply the same F5
     (>=500 words) / F6 (English) filters.
  4. Compare against the existing README-only text for the same
     library (extracted from the already-cloned repo).

No LIWC scoring yet, this only exists to size the real yield before
committing to a full crawl + write-out step.

Usage:
    venv/bin/python3 src/corpus/tutorial_crawl_pilot.py
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from confirmatory_preprocessor import (  # noqa: E402
    apply_word_cap, english_fraction, safe_name, WORD_MIN, ENGLISH_MIN_FRACTION,
)

ROOT = Path(__file__).resolve().parents[2]
RECON_CSV = ROOT / "files" / "corpus" / "docs_url_recon_results.csv"
CLONE_ROOT = ROOT / "files" / "raw" / "confirmatory"
OUT_CSV = ROOT / "files" / "corpus" / "tutorial_crawl_pilot_results.csv"

USER_AGENT = "seng402-corpus-frame/1.0 (research)"
TIMEOUT = 12
MAX_PAGES = 8       # bounded crawl per library for this pilot
PAGE_DELAY = 0.5    # politeness delay between pages on the same site

TUTORIAL_SIGNALS = {"tutorial", "tutorials", "guide", "guides", "quickstart",
                    "quick-start", "getting-started", "getting_started",
                    "walkthrough", "howto", "how-to"}

READTHEDOCS_CLASSES = {"readthedocs", "other_sphinx", "github_pages", "other_docusaurus"}


def _matches_tutorial_signal(url: str, link_text: str) -> bool:
    path_segs = [s.lower() for s in urlparse(url).path.split("/") if s]
    if any(seg.replace(".html", "") in TUTORIAL_SIGNALS for seg in path_segs):
        return True
    text_low = link_text.lower()
    return any(sig.replace("-", " ") in text_low or sig in text_low
              for sig in TUTORIAL_SIGNALS)


def _html_to_prose(html_str: str) -> str:
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup(["code", "pre", "script", "style", "nav", "footer",
                     "aside", "form", "figure", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n\s*(?:\n\s*)+", "\n\n", text)
    return text.strip()


def find_tutorial_pages(landing_url: str, session: requests.Session) -> list[str]:
    try:
        resp = session.get(landing_url, headers={"User-Agent": USER_AGENT},
                           timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    host = urlparse(landing_url).netloc
    matched: list[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(landing_url, a["href"]).split("#")[0]
        if urlparse(href).netloc != host or href in seen:
            continue
        seen.add(href)
        if _matches_tutorial_signal(href, a.get_text() or ""):
            matched.append(href)
    return matched[:MAX_PAGES]


def crawl_tutorial_bucket(landing_url: str, session: requests.Session) -> tuple[int, bool, bool, int]:
    pages = find_tutorial_pages(landing_url, session)
    chunks = []
    for url in pages:
        time.sleep(PAGE_DELAY)
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        prose = _html_to_prose(resp.text)
        if prose:
            chunks.append(prose)
    if not chunks:
        return 0, False, False, len(pages)
    combined = "\n\n".join(chunks)
    _, wc, _ = apply_word_cap(combined)
    f5 = wc >= WORD_MIN
    en_frac, _ = english_fraction(combined)
    f6 = en_frac >= ENGLISH_MIN_FRACTION
    return wc, f5, f6, len(pages)


def readme_word_count(package_name: str) -> int:
    sname = safe_name(package_name)
    clone_dir = CLONE_ROOT / "python" / sname
    if not clone_dir.is_dir():
        return -1  # not cloned locally
    for name in clone_dir.iterdir():
        if name.is_file() and name.stem.lower().startswith("readme"):
            from confirmatory_preprocessor import extract_prose
            text = extract_prose(name)
            return len(text.split())
    return 0


def main() -> None:
    with open(RECON_CSV) as f:
        recon_rows = list(csv.DictReader(f))
    candidates = [r for r in recon_rows
                 if r["ecosystem"] == "python" and r["classification"] in READTHEDOCS_CLASSES]
    print(f"{len(candidates)} candidate Python libraries with a real docs site.")

    session = requests.Session()
    results = []
    for i, r in enumerate(candidates, 1):
        pkg = r["package_name"]
        print(f"[{i}/{len(candidates)}] {pkg}  ({r['final_url']})")
        tut_wc, tut_f5, tut_f6, n_pages = crawl_tutorial_bucket(r["final_url"], session)
        readme_wc = readme_word_count(pkg)
        matched_ready = tut_f5 and tut_f6 and readme_wc >= WORD_MIN
        print(f"   tutorial pages tried={n_pages} words={tut_wc} f5={tut_f5} f6={tut_f6}  "
              f"| readme_words={readme_wc}  matched_ready={matched_ready}")
        results.append({
            "package_name": pkg, "docs_url": r["final_url"],
            "n_tutorial_pages_tried": n_pages,
            "tutorial_words": tut_wc, "tutorial_f5": tut_f5, "tutorial_f6": tut_f6,
            "readme_words": readme_wc, "matched_ready": matched_ready,
        })

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    n_tut_ready = sum(1 for r in results if r["tutorial_f5"] and r["tutorial_f6"])
    n_readme_missing_local = sum(1 for r in results if r["readme_words"] == -1)
    n_matched = sum(1 for r in results if r["matched_ready"])
    print(f"\nChecked {len(results)} candidates.")
    print(f"  tutorial bucket ready (>=500 words, EN): {n_tut_ready}")
    print(f"  README not on disk locally (would need clone): {n_readme_missing_local}")
    print(f"  matched-pair ready: {n_matched}")
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
