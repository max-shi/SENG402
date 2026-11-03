"""
rq3_affect_token_check: test 3 (construct-validity re-check) for RQ3,
built on the *existing* construct-validity verdicts rather than a new ad hoc
word list.

Why this design. The project already ran a construct-validity audit of all
15 committed dimensions against the RQ1/RQ2 human corpus
(files/analysis/construct_validity_check.md, via verify_liwc_dimensions.py).
It reached explicit verdicts on the three dimensions that carry the RQ3
headline finding:

    emotion  -> register-shifted (dominated by idiomatic "like":
                array-like, looks like, such as)
    emo_neg  -> mixed (real LIWC negatives, but they name *runtime errors*:
                error/errors/failed/failure/issues, not author affect)
    emo_sad  -> register-shifted ("missing argument", "lost connection":
                missing/lost/lose/losing, not author sadness)

So RQ3's Affect result lands entirely on dimensions already known to be
compromised in this register. The open question is therefore NOT "is
emo_sad valid in code docs" (already answered: no) but the sharper one:

    Is the LLM-vs-human gap on these dimensions driven by the SAME
    register-shifted tokens, or is the LLM contributing genuine affect
    vocabulary the human authors don't use?

Those two possibilities support opposite claims, so the distinction has to
be measured rather than assumed:

  (a) same tokens  -> the finding is about documentation CONTENT (the LLM
      writes far more error/failure/missing-value prose than the real
      author, especially for Java). Real, reportable, but not affect.
  (b) new tokens   -> the LLM genuinely writes in a more affect-laden
      register, and the Affect reading survives.

Method. Reuse verify_liwc_dimensions.py's curated STEMS and tokeniser
verbatim (same stems the original audit used, so verdicts are comparable),
apply them per (source x ecosystem) cell of the RQ3 corpus, and report:
  - hit rate per 100 words, human vs each model, per ecosystem
  - the token breakdown driving each cell
  - the share of each cell's hits that come from the specific tokens the
    original audit named as register-shifted

Outputs:
    files/corpus/rq3/rq3_affect_token_check.csv        (per-cell rates)
    files/corpus/rq3/rq3_affect_token_breakdown.csv    (per-token counts)

Usage:
    venv/bin/python3 src/rq3/rq3_affect_token_check.py
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from verify_liwc_dimensions import STEMS, tokenise, keyword_hits  # noqa: E402

RQ3_CSV = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries.csv"
OUT_RATES = ROOT / "files" / "corpus" / "rq3" / "rq3_affect_token_check.csv"
OUT_BREAKDOWN = ROOT / "files" / "corpus" / "rq3" / "rq3_affect_token_breakdown.csv"

AFFECT_DIMS = ["emotion", "emo_neg", "emo_sad"]
SOURCES = ["human", "sonnet", "openai"]
ECOSYSTEMS = ["java", "python"]

# The exact tokens the original audit (construct_validity_check.md) named as
# the register-shift drivers for each dimension. Tracking these specifically
# is what separates hypothesis (a) from (b) above, if the LLM's extra hits
# are concentrated here, the gap is register-shift amplification, not affect.
REGISTER_SHIFTED_TOKENS = {
    "emotion": {"like", "likes", "liked"},
    "emo_neg": {"error", "errors", "failed", "failure", "failures",
                "fail", "fails", "failing", "issue", "issues"},
    "emo_sad": {"missing", "miss", "misses", "lost", "lose", "losing"},
}

# False positives in verify_liwc_dimensions.STEMS, found by inspecting the
# per-token breakdown on this corpus rather than trusting the stem list:
#   cry\w*   -> crypto, cryptographic, cryptoprop*  (one Spring crypto
#               library alone contributed dozens of "sad"/"emotion" hits)
#   miss\w*  -> mission
#   issue\w* -> issuer (certificate/token issuer, a domain noun)
#   break\w* -> breakpoint
# These are artefacts of MY approximation, not evidence about LIWC's own
# dictionary, LIWC may or may not make the same mistake. They are dropped
# so the human-vs-LLM comparison isn't distorted by whichever cell happens
# to contain a crypto library. Excluded counts are reported separately so
# the exclusion is auditable rather than silent.
EXCLUDED_TOKEN_PREFIXES = ("crypt", "mission", "issuer", "breakpoint")


def is_false_positive(token: str) -> bool:
    return token.startswith(EXCLUDED_TOKEN_PREFIXES)


def main() -> None:
    csv.field_size_limit(sys.maxsize)
    df = pd.read_csv(RQ3_CSV)

    rate_rows = []
    breakdown_rows = []

    for dim in AFFECT_DIMS:
        stems = STEMS[dim]
        shifted = REGISTER_SHIFTED_TOKENS[dim]

        for eco in ECOSYSTEMS:
            for source in SOURCES:
                sub = df[(df["ecosystem"] == eco) & (df["source"] == source)]
                total_tokens = 0
                hits: Counter = Counter()

                for text in sub["text"]:
                    toks = tokenise(str(text))
                    total_tokens += len(toks)
                    hits.update(keyword_hits(toks, stems))

                dropped = sum(c for t, c in hits.items() if is_false_positive(t))
                hits = Counter({t: c for t, c in hits.items()
                                if not is_false_positive(t)})

                total_hits = sum(hits.values())
                shifted_hits = sum(c for t, c in hits.items() if t in shifted)

                rate_rows.append({
                    "dimension": dim,
                    "ecosystem": eco,
                    "source": source,
                    "n_docs": len(sub),
                    "total_words": total_tokens,
                    "curated_hits": total_hits,
                    "hits_per_100w": round(100 * total_hits / total_tokens, 4)
                    if total_tokens else 0.0,
                    "register_shifted_hits": shifted_hits,
                    "register_shifted_share": round(shifted_hits / total_hits, 4)
                    if total_hits else 0.0,
                    "excluded_false_positives": dropped,
                })

                for tok, count in hits.most_common(12):
                    breakdown_rows.append({
                        "dimension": dim, "ecosystem": eco, "source": source,
                        "token": tok, "count": count,
                        "share_of_cell_hits": round(count / total_hits, 4)
                        if total_hits else 0.0,
                        "is_register_shifted": tok in shifted,
                    })

    pd.DataFrame(rate_rows).to_csv(OUT_RATES, index=False)
    pd.DataFrame(breakdown_rows).to_csv(OUT_BREAKDOWN, index=False)
    print(f"Wrote {OUT_RATES}")
    print(f"Wrote {OUT_BREAKDOWN}\n")

    rates = pd.DataFrame(rate_rows)
    for dim in AFFECT_DIMS:
        print(f"=== {dim} — curated-stem hits per 100 words ===")
        piv = rates[rates["dimension"] == dim].pivot(
            index="ecosystem", columns="source", values="hits_per_100w")
        piv = piv[SOURCES]
        piv["llm_mean"] = piv[["sonnet", "openai"]].mean(axis=1)
        piv["llm_over_human"] = (piv["llm_mean"] / piv["human"]).round(2)
        print(piv.to_string())

        share = rates[rates["dimension"] == dim].pivot(
            index="ecosystem", columns="source", values="register_shifted_share")
        print(f"\n  share of those hits from the tokens the original audit "
              f"flagged as register-shifted:")
        print("  " + share[SOURCES].to_string().replace("\n", "\n  "))
        print()

    print("=== top tokens per cell (LLM cells only, Java) ===")
    bd = pd.DataFrame(breakdown_rows)
    for dim in AFFECT_DIMS:
        for source in SOURCES:
            sel = bd[(bd["dimension"] == dim) & (bd["ecosystem"] == "java")
                     & (bd["source"] == source)].head(6)
            toks = ", ".join(f"{r.token}({r.count})" for r in sel.itertuples())
            print(f"  {dim:9s} java   {source:7s}  {toks}")


if __name__ == "__main__":
    main()
