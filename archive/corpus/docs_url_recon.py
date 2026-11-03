"""
docs_url_recon: Cheap reconnaissance pass over the locked 400-library
sample's `docs_url` field: does it resolve, and what kind of site is it?
No scraping/extraction yet, this only exists to size the ceiling before
deciding whether a real online-docs crawler is worth building, and to
check whether coverage is lopsided by ecosystem (a real bias risk if so).

Classification (by final URL after redirects, then light content sniff):
    no_docs_url      , docs_url field was empty
    same_as_repo     , docs_url just points at the GitHub repo itself
    unreachable      , request failed (timeout/DNS/connection error)
    http_error_<code>, resolved but non-2xx
    readthedocs      , readthedocs.io/.org
    github_pages     , *.github.io
    javadoc_io       , javadoc.io (Java auto-generated reference)
    other_sphinx     , resolves, generator meta tag suggests Sphinx
    other_mkdocs     , resolves, signs of MkDocs
    other_docusaurus , resolves, signs of Docusaurus
    other            , resolves, none of the above recognized

Usage:
    venv/bin/python3 src/corpus/docs_url_recon.py
"""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "files" / "corpus" / "frame_locked_corrected" / "sample_manifest_final.csv"
OUT_CSV = ROOT / "files" / "corpus" / "docs_url_recon_results.csv"

USER_AGENT = "seng402-corpus-frame/1.0 (research)"
TIMEOUT = 12
MAX_WORKERS = 20
SNIFF_BYTES = 20_000  # only need the <head> region for generator meta tags


def classify(package_name: str, ecosystem: str, docs_url: str, repo_url: str) -> dict:
    result = {"package_name": package_name, "ecosystem": ecosystem,
              "docs_url": docs_url, "final_url": "", "http_status": "",
              "classification": ""}

    if not docs_url:
        result["classification"] = "no_docs_url"
        return result

    if repo_url and docs_url.rstrip("/") == repo_url.rstrip("/"):
        result["classification"] = "same_as_repo"
        result["final_url"] = docs_url
        return result

    try:
        resp = requests.get(
            docs_url, headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT, allow_redirects=True, stream=True,
        )
        body = resp.raw.read(SNIFF_BYTES, decode_content=True)
        try:
            text = body.decode(resp.encoding or "utf-8", errors="replace")
        except (LookupError, TypeError):
            text = body.decode("utf-8", errors="replace")
        resp.close()
    except requests.RequestException as exc:
        result["classification"] = "unreachable"
        result["http_status"] = type(exc).__name__
        return result

    result["final_url"] = resp.url
    result["http_status"] = str(resp.status_code)

    if not (200 <= resp.status_code < 300):
        result["classification"] = f"http_error_{resp.status_code}"
        return result

    host = urlparse(resp.url).netloc.lower()
    low = text.lower()

    if "readthedocs" in host:
        result["classification"] = "readthedocs"
    elif host.endswith("github.io"):
        result["classification"] = "github_pages"
    elif "javadoc.io" in host:
        result["classification"] = "javadoc_io"
    elif "github.com" in host:
        result["classification"] = "same_as_repo"
    elif "sphinx" in low or 'name="generator" content="sphinx' in low:
        result["classification"] = "other_sphinx"
    elif "mkdocs" in low:
        result["classification"] = "other_mkdocs"
    elif "docusaurus" in low:
        result["classification"] = "other_docusaurus"
    else:
        result["classification"] = "other"

    return result


def main() -> None:
    with open(MANIFEST) as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} libraries in the locked sample.")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(classify, r["package_name"], r["ecosystem"],
                       r.get("docs_url", ""), r.get("repository_url", "")): r
            for r in rows
        }
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % 50 == 0:
                print(f"  ...{done}/{len(rows)}")

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {OUT_CSV}")

    from collections import Counter
    print("\n=== Overall ===")
    for cls, n in Counter(r["classification"] for r in results).most_common():
        print(f"  {cls:20s} {n:4d}")

    for eco in sorted({r["ecosystem"] for r in results}):
        print(f"\n=== {eco} ===")
        eco_results = [r for r in results if r["ecosystem"] == eco]
        for cls, n in Counter(r["classification"] for r in eco_results).most_common():
            print(f"  {cls:20s} {n:4d}")


if __name__ == "__main__":
    main()
