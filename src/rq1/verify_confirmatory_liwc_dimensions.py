"""
verify_confirmatory_liwc_dimensions: Layer 2 (construct validity) re-check
on the confirmatory corpus.

Re-runs the pilot's verify_liwc_dimensions.py token-driver audit, but on the
confirmatory corpus's libraries.csv + LIWC output, and using the *direction*
each dimension actually took in the confirmatory Layer-1 test (not the
pilot's direction, which flipped for several dimensions, e.g. emo_sad and
ipron). Per Layer 2 in RULES.md: a dimension whose driver
tokens change between pilot and confirmatory is treated as exploratory.

Inputs:
  files/corpus/frame_<freeze-date>/libraries.csv
  files/corpus/frame_<freeze-date>/LIWC-22 Results - libraries - LIWC Analysis.csv
  files/corpus/frame_<freeze-date>/confirmatory_stats_results.csv  (for direction)

Outputs:
  files/corpus/frame_<freeze-date>/verify_confirmatory_liwc_dimensions_output.txt

Usage:
    venv/bin/python3 src/rq1/verify_confirmatory_liwc_dimensions.py [--freeze-date <name>] [--dims emo_anger,conflict]
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]

# Same curated stem lists as the pilot's verify_liwc_dimensions.py.
STEMS: dict[str, list[str]] = {
    "emotion": [
        r"love\w*", r"happy", r"happi\w*", r"glad", r"enjoy\w*",
        r"like[ds]?", r"good", r"great", r"nice", r"hope\w*",
        r"hate\w*", r"sad\w*", r"cry\w*", r"angry", r"anger",
        r"afraid", r"fear\w*", r"worried", r"worry\w*",
        r"hurt\w*", r"upset", r"frustrat\w*",
    ],
    "emo_neg": [
        r"bad", r"wrong", r"fail\w*", r"error\w*", r"problem\w*",
        r"issue\w*", r"broken", r"break\w*", r"crash\w*",
        r"hate\w*", r"sad\w*", r"cry\w*", r"angry", r"anger",
        r"afraid", r"fear\w*", r"worried", r"worry\w*",
        r"hurt\w*", r"upset", r"frustrat\w*", r"terrible",
        r"awful", r"horrible", r"nasty", r"poor",
    ],
    "emo_anger": [
        r"angry", r"anger", r"mad", r"hate\w*", r"annoy\w*",
        r"fight\w*", r"attack\w*", r"kill\w*", r"destroy\w*",
        r"violent\w*", r"hostile\w*", r"aggress\w*", r"rage\w*",
        r"fury", r"furious", r"war", r"battle\w*",
    ],
    "emo_sad": [
        r"sad\w*", r"cry\w*", r"cried", r"miss\w*", r"lost",
        r"lose", r"losing", r"alone", r"lonely", r"grief",
        r"sorry", r"regret\w*", r"unhappy", r"depress\w*",
        r"disappoint\w*", r"abandon\w*", r"die[ds]?", r"dying",
        r"dead", r"death\w*",
    ],
    "Tone": [
        r"good", r"great", r"nice", r"happy", r"happi\w*",
        r"love\w*", r"like[ds]?", r"enjoy\w*", r"better", r"best",
        r"hope\w*", r"thank\w*", r"please\w*", r"easy", r"easier",
        r"easily", r"win\w*", r"won", r"success\w*",
    ],
    "tentat": [
        r"may", r"maybe", r"might", r"could", r"perhaps", r"possibl\w*",
        r"probabl\w*", r"seem\w*", r"appear\w*", r"likely",
        r"unlikely", r"suppose\w*", r"guess\w*", r"hope\w*",
        r"depend\w*", r"sort", r"kind",
        r"some", r"someone", r"something", r"somewhat",
    ],
    "certitude": [
        r"really", r"actually", r"definite\w*", r"always", r"never",
        r"certain\w*", r"sure", r"truly?", r"obvious\w*", r"clearly",
        r"of course", r"indeed", r"in fact", r"undoubted\w*",
        r"absolutely", r"completely",
    ],
    "curiosity": [
        r"curious\w*", r"wonder\w*", r"interest\w*", r"explor\w*",
        r"discover\w*", r"investigat\w*", r"search\w*", r"seek\w*",
        r"ask\w*", r"question\w*", r"why", r"how",
        r"learn\w*", r"study\w*", r"research\w*", r"examine\w*",
    ],
    "achieve": [
        r"achiev\w*", r"goal\w*", r"success\w*", r"win\w*", r"won",
        r"complet\w*", r"finish\w*", r"accomplish\w*", r"reach\w*",
        r"earn\w*", r"gain\w*", r"build\w*", r"built", r"create\w*",
        r"made", r"make[sr]?", r"making", r"work\w*", r"effort\w*",
        r"try\w*", r"tries", r"tried", r"deliver\w*",
        r"produce\w*", r"perform\w*", r"obtain\w*",
    ],
    "risk": [
        r"risk\w*", r"danger\w*", r"warn\w*", r"caution\w*",
        r"unsafe", r"safe\w*", r"safety", r"secur\w*", r"vulner\w*",
        r"threat\w*", r"hazard\w*", r"prevent\w*", r"protect\w*",
        r"avoid\w*", r"problem\w*", r"issue\w*", r"fail\w*",
        r"error\w*", r"crash\w*", r"corrupt\w*",
    ],
    "motion": [
        r"go", r"goes", r"going", r"went", r"gone", r"come\w*",
        r"came", r"move\w*", r"moving", r"run\w*", r"ran",
        r"walk\w*", r"travel\w*", r"send\w*", r"sent", r"return\w*",
        r"arriv\w*", r"leave[sr]?", r"left", r"bring\w*", r"brought",
        r"pass\w*", r"reach\w*", r"flow\w*", r"transfer\w*",
        r"push\w*", r"pull\w*", r"carry\w*", r"carried",
    ],
    "conflict": [
        r"fight\w*", r"attack\w*", r"war", r"battle\w*",
        r"argu\w*", r"disagree\w*", r"oppos\w*", r"against",
        r"conflict\w*", r"versus", r"vs", r"defeat\w*",
        r"struggle\w*", r"resist\w*", r"refuse\w*", r"reject\w*",
        r"deny\w*", r"break\w*", r"broke\w*", r"violat\w*",
        r"protest\w*",
    ],
    "ipron": [
        r"it", r"its", r"this", r"that", r"these", r"those",
        r"anything", r"something", r"nothing", r"everything",
        r"anyone", r"someone", r"everyone", r"anybody",
        r"somebody", r"everybody", r"such", r"itself",
    ],
}

STRUCTURAL = {"WPS", "BigWords"}

ALL_DIMS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

TOP_K = 5

WORD_RE = re.compile(r"[A-Za-z']+")


def load_direction(frame_dir: Path) -> dict[str, str]:
    """dimension -> 'java' or 'python', taken from the actual confirmatory result."""
    path = frame_dir / "confirmatory_stats_results.csv"
    direction = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            direction[row["dimension"]] = (
                "java" if row["direction"] == "java_higher" else "python"
            )
    return direction


def load_liwc(frame_dir: Path) -> list[dict]:
    path = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_text_index(frame_dir: Path) -> dict[tuple[str, str], str]:
    path = frame_dir / "libraries.csv"
    idx = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            idx[(row["ecosystem"], row["library"])] = row["text"]
    return idx


def tokenise(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(text)]


def keyword_hits(tokens: list[str], stems: list[str]) -> Counter:
    compiled = [re.compile("^(?:" + s + ")$", re.IGNORECASE) for s in stems]
    hits: Counter = Counter()
    for tok in tokens:
        for pat in compiled:
            if pat.match(tok):
                hits[tok] += 1
                break
    return hits


def check_lexical(dim: str, eco: str, liwc_rows, text_idx):
    cohort = [r for r in liwc_rows if r["ecosystem"] == eco]
    cohort.sort(key=lambda r: float(r[dim]), reverse=True)
    top = cohort[:TOP_K]
    stems = STEMS[dim]
    print(f"\n## {dim}  (confirmatory direction: {eco} highest; checking top {TOP_K})")
    aggregate_hits: Counter = Counter()
    agg_words = 0
    for r in top:
        text = text_idx[(eco, r["library"])]
        toks = tokenise(text)
        hits = keyword_hits(toks, stems)
        score = float(r[dim])
        n_hits = sum(hits.values())
        pct = 100.0 * n_hits / max(1, len(toks))
        top_words = ", ".join(f"{w}:{c}" for w, c in hits.most_common(8))
        print(
            f"  {r['library']:<32} liwc={score:6.3f}%  "
            f"keyword_hits={n_hits:5d} ({pct:5.2f}% of tokens)  "
            f"top: {top_words}"
        )
        aggregate_hits.update(hits)
        agg_words += len(toks)
    agg_pct = 100.0 * sum(aggregate_hits.values()) / max(1, agg_words)
    print(
        f"  -- aggregate: {sum(aggregate_hits.values())} hits in {agg_words} "
        f"tokens ({agg_pct:.2f}%); curated overlap with LIWC score "
        f"avg = {sum(float(r[dim]) for r in top)/len(top):.3f}%"
    )
    print(
        "  -- most common matching tokens overall: "
        + ", ".join(f"{w}:{c}" for w, c in aggregate_hits.most_common(15))
    )


def check_structural(dim: str, eco: str, liwc_rows, text_idx):
    cohort = [r for r in liwc_rows if r["ecosystem"] == eco]
    cohort.sort(key=lambda r: float(r[dim]), reverse=True)
    top = cohort[:TOP_K]
    print(f"\n## {dim}  (confirmatory direction: {eco} highest; structural check, top {TOP_K})")
    for r in top:
        text = text_idx[(eco, r["library"])]
        toks = tokenise(text)
        if dim == "BigWords":
            big = sum(1 for t in toks if len(t) >= 7)
            pct = 100.0 * big / max(1, len(toks))
            sample_big = Counter(t for t in toks if len(t) >= 7).most_common(8)
            print(
                f"  {r['library']:<32} liwc={float(r[dim]):6.2f}%  "
                f"my_pct_words_ge_7={pct:5.2f}%  "
                f"top long words: {', '.join(w for w,_ in sample_big)}"
            )
        elif dim == "WPS":
            sentences = re.split(r"[.!?]+\s", text)
            sentences = [s for s in sentences if s.strip()]
            wps = len(toks) / max(1, len(sentences))
            print(
                f"  {r['library']:<32} liwc_WPS={float(r[dim]):6.2f}  "
                f"my_avg_words_per_sentence={wps:5.2f}"
            )


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _run(dims: list[str], liwc_rows, text_idx, direction):
    print("# Construct-validity audit (Layer 2) — confirmatory corpus")
    print(f"# Run timestamp: {datetime.now().isoformat(timespec='seconds')}")
    print(f"# Dimensions checked ({len(dims)}): {', '.join(dims)}")
    print(f"# Loaded {len(liwc_rows)} library rows and {len(text_idx)} texts")
    for dim in dims:
        eco = direction[dim]
        if dim in STRUCTURAL:
            check_structural(dim, eco, liwc_rows, text_idx)
        else:
            check_lexical(dim, eco, liwc_rows, text_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date", default="locked")
    ap.add_argument("--dims", default=None,
                     help="comma-separated subset of dimensions; default = all 15")
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    out_txt = frame_dir / "verify_confirmatory_liwc_dimensions_output.txt"

    dims = args.dims.split(",") if args.dims else ALL_DIMS
    for d in dims:
        if d not in STEMS and d not in STRUCTURAL:
            raise SystemExit(f"unknown dimension: {d!r}")

    direction = load_direction(frame_dir)
    liwc_rows = load_liwc(frame_dir)
    text_idx = load_text_index(frame_dir)

    with open(out_txt, "w", encoding="utf-8") as fh:
        with contextlib.redirect_stdout(_Tee(sys.stdout, fh)):
            _run(dims, liwc_rows, text_idx, direction)
    print(f"\n[output written to {out_txt}]")


if __name__ == "__main__":
    main()
