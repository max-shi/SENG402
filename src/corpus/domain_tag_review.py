"""
domain_tag_review: Interactive domain tagging for the confirmatory
corpus.

For each of the 400 primary_ready rows, gathers evidence in the
preference order specified by the spec:

    1. PyPI `Topic ::` classifiers (Python only; from the frozen frame
       snapshot's `metadata.classifiers`)
    2. ecosyste.ms `keywords_array`
    3. package `description`
    4. first paragraph of the extracted README text

...scores each of the 9 fixed-vocabulary domains via a keyword
heuristic, and proposes the highest-scoring domain. You confirm the
proposal (Enter) or override with a single letter. Every decision
(proposed or overridden) and the evidence source that drove it are
written back into sample_manifest.csv's `domain_tag` /
`domain_tag_source` columns, the working manifest is the source of
truth (see apply_f7_manual_review.py's docstring for why: the final
manifest is a derived snapshot that finalize_confirmatory_sample.py
regenerates from the working manifest on every run).

Domain vocabulary (single-letter override keys in parens):
    web (w), data (d), testing (t), build-tooling (b),
    serialisation (s), networking (n), security (c), ui (u), misc (m)

The script is idempotent and resumable: rows already tagged
(domain_tag non-empty) are skipped. Quit any time with `q`.

Usage:
    venv/bin/python3 src/corpus/domain_tag_review.py --freeze-date <name> [--head-lines 8]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "files" / "corpus"

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip("_")


def _reset_tty() -> None:
    if not sys.stdin.isatty():
        return
    try:
        subprocess.run(["stty", "sane"], check=False,
                       stdin=sys.stdin, timeout=2)
    except Exception:
        pass


DOMAINS = [
    "web", "data", "testing", "build-tooling", "serialisation",
    "networking", "security", "ui", "misc",
]

KEY_TO_DOMAIN = {
    "w": "web", "d": "data", "t": "testing", "b": "build-tooling",
    "s": "serialisation", "n": "networking", "c": "security",
    "u": "ui", "m": "misc",
}

# Keyword heuristic. Matched case-insensitively as whole words against
# combined evidence text. Not exhaustive by design, it only needs to
# produce a reasonable *proposal*; the human makes the final call.
KEYWORDS: dict[str, list[str]] = {
    "web": [
        "web", "http", "https", "rest", "restful", "api", "server",
        "client", "framework", "servlet", "router", "routing",
        "websocket", "url", "request", "response", "html", "cgi",
        "wsgi", "asgi", "endpoint", "middleware",
    ],
    "data": [
        "data", "numpy", "pandas", "dataframe", "machine learning",
        "ml", "statistics", "statistical", "tensor", "array",
        "scientific", "analysis", "dataset", "model", "regression",
        "classification", "neural", "deep learning", "sklearn",
        "matrix", "linear algebra", "computation", "computing",
        "algorithm", "numeric", "science",
    ],
    "testing": [
        "test", "testing", "mock", "mocking", "assert", "assertion",
        "fixture", "junit", "pytest", "spec", "specification",
        "unittest", "coverage", "stub", "test-driven", "tdd",
    ],
    "build-tooling": [
        "build", "package", "packaging", "plugin", "cli",
        "command-line", "command line", "lint", "linter", "linting",
        "format", "formatter", "gradle", "maven", "setuptools",
        "compiler", "compile", "bundler", "bundle", "scaffold",
        "generator", "task runner", "devtools", "dev tool",
    ],
    "serialisation": [
        "json", "xml", "yaml", "yml", "protobuf", "serial",
        "serialize", "serialization", "serialise", "serialisation",
        "orm", "marshall", "marshal", "codec", "encode", "decode",
        "parser", "parsing", "schema", "csv",
    ],
    "networking": [
        "socket", "network", "networking", "tcp", "udp", "grpc",
        "messaging", "message queue", "queue", "distributed",
        "rpc", "protocol", "p2p", "peer-to-peer", "cluster",
        "kafka", "amqp", "mqtt",
    ],
    "security": [
        "crypto", "cryptography", "cryptographic", "auth",
        "authentication", "authorization", "hash", "hashing",
        "security", "secure", "ssl", "tls", "oauth", "jwt",
        "encrypt", "encryption", "decrypt", "certificate", "cipher",
        "password", "vulnerability",
    ],
    "ui": [
        "gui", "plot", "plotting", "visual", "visualization",
        "visualisation", "chart", "charting", "widget", "ui",
        "user interface", "graphic", "graphics", "swing", "tkinter",
        "render", "rendering", "canvas", "theme", "css", "component",
        "frontend", "front-end",
    ],
}

_WORD_RE_CACHE: dict[str, re.Pattern] = {}


def _word_re(kw: str) -> re.Pattern:
    pat = _WORD_RE_CACHE.get(kw)
    if pat is None:
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(kw) +
                          r"(?![A-Za-z0-9])", re.IGNORECASE)
        _WORD_RE_CACHE[kw] = pat
    return pat


def score_domains(text: str) -> list[tuple[str, int]]:
    scores = []
    for domain, kws in KEYWORDS.items():
        n = sum(1 for kw in kws if _word_re(kw).search(text))
        scores.append((domain, n))
    scores.sort(key=lambda t: -t[1])
    return scores


def load_frame_index(frame_dir: Path, ecosystem: str) -> dict[str, dict]:
    path = frame_dir / f"frame_{ecosystem}.jsonl.gz"
    idx: dict[str, dict] = {}
    if not path.exists():
        return idx
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            idx[rec["name"]] = rec
    return idx


def gather_evidence(row: dict, frame_rec: dict | None,
                     frame_dir: Path) -> tuple[str, str]:
    """
    Return (combined_text_for_scoring, source_label) using the
    preference order from the original plan. combined_text always includes all
    available sources (more signal for the heuristic); source_label
    names the *highest-preference* source that was non-empty, for the
    manifest's domain_tag_source column.
    """
    parts: list[str] = []
    source = "none"

    if frame_rec:
        classifiers = ((frame_rec.get("metadata") or {}).get("classifiers")
                       or [])
        topic_classifiers = [c for c in classifiers if c.startswith("Topic ::")]
        if topic_classifiers:
            parts.append(" ".join(topic_classifiers))
            source = "pypi_classifiers"

        keywords = frame_rec.get("keywords_array") or []
        if keywords:
            parts.append(" ".join(keywords))
            if source == "none":
                source = "keywords"

        desc = frame_rec.get("description") or ""
        if desc:
            parts.append(desc)
            if source == "none":
                source = "description"

    # README first paragraph fallback (always included as extra signal).
    sname = safe_name(row["package_name"])
    text_path = frame_dir / "text" / row["ecosystem"] / f"{sname}.txt"
    if text_path.is_file():
        try:
            head = text_path.read_text(encoding="utf-8", errors="replace")
            # First non-empty paragraph, capped.
            for para in head.split("\n\n"):
                para = para.strip()
                if len(para) > 20:
                    parts.append(para[:500])
                    if source == "none":
                        source = "readme"
                    break
        except OSError:
            pass

    return " \n".join(parts), source


def load_manifest(path: Path) -> tuple[list[dict], list[str]]:
    with path.open() as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        fields = list(rdr.fieldnames or [])
    for col in ("domain_tag", "domain_tag_source", "domain_tag_verified"):
        if col not in fields:
            fields.append(col)
            for r in rows:
                r.setdefault(col, "")
    return rows, fields


def save_manifest(path: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            for k in fields:
                r.setdefault(k, "")
            w.writerow(r)
    tmp.replace(path)


def prompt_one(row: dict, evidence_text: str, evidence_source: str,
               proposed: str, index: int, total: int) -> tuple[str, str] | None:
    """Return (domain, source_label) or None if skipped/quit-later."""
    print("\n" + "=" * 78)
    print(f"[{index}/{total}]  {row['ecosystem']:6s}  {row['package_name']}")
    snippet = evidence_text.strip().replace("\n", " ")
    if len(snippet) > 300:
        snippet = snippet[:300] + "..."
    print(f"  evidence ({evidence_source}): {snippet}")
    print(f"  proposed: {proposed}")
    print("-" * 78)

    keys = "/".join(f"[{k}]{d}" for k, d in KEY_TO_DOMAIN.items())
    while True:
        choice = input(f"  Enter=accept '{proposed}'  {keys}  "
                       f"[s]kip  [q]uit  > ").strip().lower()
        if choice == "":
            return proposed, evidence_source
        if choice in KEY_TO_DOMAIN:
            return KEY_TO_DOMAIN[choice], "manual_override"
        if choice in ("s", "skip"):
            return None
        if choice in ("q", "quit"):
            raise KeyboardInterrupt
        print("  ?? Enter to accept, a letter key to override, "
              "'s' to skip, 'q' to quit")


def prompt_spotcheck(row: dict, evidence_text: str, evidence_source: str,
                     index: int, total: int) -> tuple[str, str] | None:
    """Return (domain, disposition) or None if skipped/quit-later.
    disposition is 'confirmed' or 'manual_override'."""
    current = row.get("domain_tag") or "misc"
    print("\n" + "=" * 78)
    print(f"[{index}/{total}]  {row['ecosystem']:6s}  {row['package_name']}")
    snippet = evidence_text.strip().replace("\n", " ")
    if len(snippet) > 300:
        snippet = snippet[:300] + "..."
    print(f"  evidence ({evidence_source}): {snippet}")
    print(f"  current tag: {current}")
    print("-" * 78)

    keys = "/".join(f"[{k}]{d}" for k, d in KEY_TO_DOMAIN.items())
    while True:
        choice = input(f"  Enter=confirm '{current}'  {keys}  "
                       f"[skip]  [q]uit  > ").strip().lower()
        if choice == "":
            return current, "confirmed"
        if choice in KEY_TO_DOMAIN:
            return KEY_TO_DOMAIN[choice], "manual_override"
        if choice == "skip":
            return None
        if choice in ("q", "quit"):
            raise KeyboardInterrupt
        print("  ?? Enter to confirm, a letter key to override, "
              "'skip' to skip, 'q' to quit")


def run_spotcheck(args) -> None:
    _reset_tty()
    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"missing: {manifest_path}")

    rows, fields = load_manifest(manifest_path)
    frame_idx = {
        "python": load_frame_index(frame_dir, "python"),
        "java": load_frame_index(frame_dir, "java"),
    }

    pool = [r for r in rows
            if r.get("status") == "primary_ready"
            and (r.get("domain_tag") or "").strip()
            and (r.get("domain_tag_verified") or "").lower() != "true"]
    import random
    rng = random.Random(args.seed)
    n = min(args.n, len(pool))
    sample = rng.sample(pool, n)
    print(f"Drew {n} random unverified row(s) (seed={args.seed}). "
          f"Press q at any prompt to save + quit.")

    n_confirmed = 0
    n_overridden = 0
    try:
        for i, row in enumerate(sample, 1):
            frame_rec = frame_idx.get(row["ecosystem"], {}).get(row["package_name"])
            evidence_text, source = gather_evidence(row, frame_rec, frame_dir)
            try:
                res = prompt_spotcheck(row, evidence_text, source, i, n)
            except KeyboardInterrupt:
                print("\n[quit] saving progress...")
                break
            if res is None:
                continue
            domain, disposition = res
            row["domain_tag"] = domain
            row["domain_tag_verified"] = "true"
            if disposition == "manual_override":
                row["domain_tag_source"] = "manual_override"
                n_overridden += 1
            else:
                n_confirmed += 1
    finally:
        save_manifest(manifest_path, rows, fields)

    print(f"\nDone. confirmed={n_confirmed}  overridden={n_overridden}")


def dump_evidence(args) -> None:
    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"missing: {manifest_path}")
    rows, _fields = load_manifest(manifest_path)
    frame_idx = {
        "python": load_frame_index(frame_dir, "python"),
        "java": load_frame_index(frame_dir, "java"),
    }
    todo = [r for r in rows
            if r.get("status") == "primary_ready"
            and not (r.get("domain_tag") or "").strip()]
    out_rows = []
    for r in todo:
        frame_rec = frame_idx.get(r["ecosystem"], {}).get(r["package_name"])
        evidence_text, source = gather_evidence(r, frame_rec, frame_dir)
        scores = score_domains(evidence_text)
        top_domain, top_score = scores[0]
        heuristic_proposal = top_domain if top_score > 0 else "misc"
        out_rows.append({
            "ecosystem": r["ecosystem"],
            "package_name": r["package_name"],
            "evidence_source": source,
            "evidence": evidence_text.replace("\n", " ")[:600],
            "heuristic_proposal": heuristic_proposal,
        })
    out_path = frame_dir / "domain_tag_evidence.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {len(out_rows)} row(s) of evidence to {out_path}")


def apply_tags(args) -> None:
    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    tags_path = frame_dir / "domain_tag_decisions.csv"
    if not tags_path.exists():
        raise SystemExit(f"missing: {tags_path}")
    rows, fields = load_manifest(manifest_path)
    idx = {(r["ecosystem"], r["package_name"]): r for r in rows}
    with open(tags_path) as f:
        decisions = list(csv.DictReader(f))
    n = 0
    bad_domain = 0
    for d in decisions:
        key = (d["ecosystem"], d["package_name"])
        r = idx.get(key)
        if r is None:
            print(f"  !! not found in manifest: {key}")
            continue
        domain = d["domain_tag"].strip()
        if domain not in DOMAINS:
            print(f"  !! invalid domain '{domain}' for {key}")
            bad_domain += 1
            continue
        r["domain_tag"] = domain
        n += 1
    save_manifest(manifest_path, rows, fields)
    print(f"Applied {n} tag(s) ({bad_domain} invalid, skipped).")
    remaining = sum(1 for r in rows
                    if r.get("status") == "primary_ready"
                    and not (r.get("domain_tag") or "").strip())
    print(f"Remaining untagged primary_ready rows: {remaining}")


def main() -> None:
    _reset_tty()
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date",
                    default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--head-lines", type=int, default=8)
    ap.add_argument("--dump-evidence", action="store_true",
                    help="Write domain_tag_evidence.csv for all "
                         "untagged rows and exit (no interactive prompts).")
    ap.add_argument("--apply-tags", action="store_true",
                    help="Read domain_tag_decisions.csv "
                         "(ecosystem,package_name,domain_tag) "
                         "and write into the working manifest, then exit.")
    ap.add_argument("--spotcheck", action="store_true",
                    help="Interactively verify a random sample of already-"
                         "tagged rows (confirm/override), marking each "
                         "domain_tag_verified=true.")
    ap.add_argument("--n", type=int, default=30,
                    help="spotcheck mode: number of random rows to draw")
    ap.add_argument("--seed", type=int, default=402,
                    help="spotcheck mode: RNG seed for reproducibility")
    args = ap.parse_args()

    if args.dump_evidence:
        dump_evidence(args)
        return
    if args.apply_tags:
        apply_tags(args)
        return
    if args.spotcheck:
        run_spotcheck(args)
        return

    frame_dir = CORPUS_DIR / f"frame_{args.freeze_date}"
    manifest_path = frame_dir / "sample_manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"missing: {manifest_path}")

    rows, fields = load_manifest(manifest_path)
    frame_idx = {
        "python": load_frame_index(frame_dir, "python"),
        "java": load_frame_index(frame_dir, "java"),
    }

    todo = [r for r in rows
            if r.get("status") == "primary_ready"
            and not (r.get("domain_tag") or "").strip()]
    total_ready = sum(1 for r in rows if r.get("status") == "primary_ready")
    print(f"{len(todo)}/{total_ready} primary_ready row(s) need domain tags. "
          f"Press q at any prompt to save + quit.")

    n_done = 0
    try:
        for i, row in enumerate(todo, 1):
            frame_rec = frame_idx.get(row["ecosystem"], {}).get(row["package_name"])
            evidence_text, source = gather_evidence(row, frame_rec, frame_dir)
            scores = score_domains(evidence_text)
            top_domain, top_score = scores[0]
            proposed = top_domain if top_score > 0 else "misc"

            try:
                res = prompt_one(row, evidence_text, source, proposed,
                                 i, len(todo))
            except KeyboardInterrupt:
                print("\n[quit] saving progress...")
                break

            if res is None:
                continue
            domain, src_label = res
            row["domain_tag"] = domain
            row["domain_tag_source"] = src_label
            n_done += 1
    finally:
        save_manifest(manifest_path, rows, fields)

    remaining = sum(1 for r in rows
                    if r.get("status") == "primary_ready"
                    and not (r.get("domain_tag") or "").strip())
    print(f"\nDone. tagged={n_done}  (remaining untagged: {remaining})")

    if remaining == 0:
        from collections import Counter
        c = Counter((r["ecosystem"], r["domain_tag"]) for r in rows
                    if r.get("status") == "primary_ready")
        print("\n--- domain distribution ---")
        for (eco, dom), n in sorted(c.items()):
            print(f"  {eco:6s} {dom:15s} {n}")


if __name__ == "__main__":
    main()
