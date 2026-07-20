"""
Sanity check: for each of the 15 committed LIWC dimensions, do the words
actually driving the score in the highest-scoring libraries match the
dimension's stated semantic content?

We don't have the LIWC dictionary, so we approximate each dimension with a
hand-curated list of stems known to be in the LIWC-22 published examples
for that category. For the top-K highest-scoring libraries per (ecosystem,
dimension), we tokenise the library text and report the most frequent
tokens that match the curated stems. If the curated stems explain a
substantial share of the score, the LIWC tool is matching the kind of
words it is supposed to match.

WPS and BigWords are structural (sentence length, >6-letter word share),
not lexical, so we report a structural check instead of a keyword list.
"""

from __future__ import annotations

import contextlib
import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parents[2]
PREP_DIR = ROOT / "files/preprocess/preprocess_output_13-05-26_21-50-10"
LIWC_CSV = PREP_DIR / "LIWC-22 Results - libraries - LIWC Analysis.csv"
OUT_TXT = ROOT / "files/analysis/verify_liwc_dimensions_output.txt"



ECOSYSTEMS = {
    "java": PREP_DIR / "java/java_libraries.csv",
    "python": PREP_DIR / "python/python_libraries.csv",
    "javascript": PREP_DIR / "javascript/javascript_libraries.csv",
}

# Curated stems per dimension. Each entry is a regex that matches a stem
# as a *whole token* (anchored). These were chosen from the public LIWC-22
# example lists and from the LIWC-22 manual descriptions; they are
# representative, not exhaustive.
STEMS: dict[str, list[str]] = {
    "emotion": [
        # union of emo_pos, emo_neg, emo_anx, emo_anger, emo_sad examples
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
    "tone_neg": [
        r"bad", r"wrong", r"fail\w*", r"error\w*", r"problem\w*",
        r"issue\w*", r"hate\w*", r"sad\w*", r"angry", r"afraid",
        r"hurt\w*", r"terrible", r"awful", r"poor", r"miss\w*",
        r"lost", r"alone", r"sorry", r"deprecat\w*", r"warn\w*",
    ],
    "Tone": [  # net = tone_pos - tone_neg; we check positive stems here
        r"good", r"great", r"nice", r"happy", r"happi\w*",
        r"love\w*", r"like[ds]?", r"enjoy\w*", r"better", r"best",
        r"hope\w*", r"thank\w*", r"please\w*", r"easy", r"easier",
        r"easily", r"win\w*", r"won", r"success\w*",
    ],
    "tentat": [
        r"may", r"maybe", r"might", r"could", r"perhaps", r"possibl\w*",
        r"probabl\w*", r"seem\w*", r"appear\w*", r"likely",
        r"unlikely", r"suppose\w*", r"guess\w*", r"hope\w*",
        r"depend\w*", r"sort", r"kind",  # "kind of", "sort of"
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
        # LIWC ipron: it, this, that, these, those, something, anything, etc.
        r"it", r"its", r"this", r"that", r"these", r"those",
        r"anything", r"something", r"nothing", r"everything",
        r"anyone", r"someone", r"everyone", r"anybody",
        r"somebody", r"everybody", r"such", r"itself",
    ],
}

# Dimensions that are structural rather than lexical
STRUCTURAL = {"WPS", "BigWords"}

# The 15 committed dimensions plus side dimensions to compare
COMMITTED = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

# Which ecosystem to pick top-scoring libraries from (where the claim
# says that ecosystem is the high one).
HIGH_ECOSYSTEM = {
    "emotion": "python", "emo_neg": "python", "emo_anger": "python",
    "emo_sad": "python", "Tone": "java",
    "WPS": "java", "BigWords": "java", "ipron": "java",
    "tentat": "python", "certitude": "java",
    "curiosity": "java", "achieve": "java", "risk": "java",
    "motion": "python", "conflict": "python",
}

TOP_K = 5 # how many top libraries per dimension to inspect
# What does this even mean?


WORD_RE = re.compile(r"[A-Za-z']+")


def load_liwc():
    rows = []
    with open(LIWC_CSV) as f:
        r = csv.DictReader(f)
        for row in r:
            if row["library"].startswith("_ALL_"):
                continue
            rows.append(row)
    return rows


def load_text_index():
    idx = {}
    for eco, path in ECOSYSTEMS.items():
        with open(path) as f:
            r = csv.DictReader(f)
            for row in r:
                idx[(eco, row["library"])] = row["text"]
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


def check_lexical(dim: str, liwc_rows, text_idx):
    eco = HIGH_ECOSYSTEM[dim]
    # determine the ecosystem..
    # so.. from HIGH_ECOSYSTEM, given a DIMENSION, we find.. the corresponding.. what. what.?
    cohort = [r for r in liwc_rows if r["ecosystem"] == eco]
    cohort.sort(key=lambda r: float(r[dim]), reverse=True)
    top = cohort[:TOP_K]
    stems = STEMS[dim]
    print(f"\n## {dim}  (claim: {eco} highest; checking top {TOP_K})")
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
            f"  {r['library']:<22} liwc={score:6.3f}%  "
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


def check_structural(dim: str, liwc_rows, text_idx):
    eco = HIGH_ECOSYSTEM[dim]
    cohort = [r for r in liwc_rows if r["ecosystem"] == eco]
    cohort.sort(key=lambda r: float(r[dim]), reverse=True)
    top = cohort[:TOP_K]
    print(f"\n## {dim}  (claim: {eco} highest; structural check, top {TOP_K})")
    for r in top:
        text = text_idx[(eco, r["library"])]
        toks = tokenise(text)
        if dim == "BigWords":
            big = sum(1 for t in toks if len(t) >= 7)
            pct = 100.0 * big / max(1, len(toks))
            sample_big = Counter(t for t in toks if len(t) >= 7).most_common(8)
            print(
                f"  {r['library']:<22} liwc={float(r[dim]):6.2f}%  "
                f"my_pct_words_ge_7={pct:5.2f}%  "
                f"top long words: {', '.join(w for w,_ in sample_big)}"
            )
        elif dim == "WPS":
            sentences = re.split(r"[.!?]+\s", text)
            sentences = [s for s in sentences if s.strip()]
            wps = len(toks) / max(1, len(sentences))
            print(
                f"  {r['library']:<22} liwc_WPS={float(r[dim]):6.2f}  "
                f"my_avg_words_per_sentence={wps:5.2f}"
            )


class _Tee:
    """Write to multiple text streams simultaneously."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _run(liwc_rows, text_idx):
    print(f"# Construct-validity audit — verify_liwc_dimensions.py")
    print(f"# Run timestamp: {datetime.now().isoformat(timespec='seconds')}")
    print(f"# Source LIWC CSV: {LIWC_CSV}")
    print(f"# TOP_K (libraries inspected per dimension): {TOP_K}")
    print(f"# Committed dimensions ({len(COMMITTED)}): {', '.join(COMMITTED)}")
    print(f"# Loaded {len(liwc_rows)} library rows and {len(text_idx)} texts")
    for dim in COMMITTED:
        if dim in STRUCTURAL:
            check_structural(dim, liwc_rows, text_idx)
        else:
            check_lexical(dim, liwc_rows, text_idx)


def main():
    liwc_rows = load_liwc()
    text_idx = load_text_index()
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        with contextlib.redirect_stdout(_Tee(sys.stdout, fh)):
            _run(liwc_rows, text_idx)
    print(f"\n[output written to {OUT_TXT}]")


if __name__ == "__main__":
    main()
