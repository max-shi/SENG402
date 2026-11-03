"""
rq4_detector: can a documentation text be identified as model-generated from
surface language features alone?

Motivation. The ecosystem-classification framing of RQ4 reaches macro-F1 ~0.67
against a 0.50 chance level: a real but weak signal, and one that is hard to
inspect because it is distributed across fifteen dimensions. RQ3 found a much
larger effect on a single dimension -- generated documentation uses markedly
longer words than the documentation a library's own maintainers wrote (Cliff's
delta 0.64-0.87, large, in all four model x ecosystem strata). That suggests a
far more tractable target, and one a reader can verify by hand.

Two design choices make this a *tool* rather than another classifier:

* **No LIWC dependency.** `BigWords` (percentage of words with >= 7 characters)
  and `WPS` (words per sentence) are structural counts, not dictionary lookups.
  Both are recomputed here directly from text and validated against LIWC's own
  values on the same corpus. LIWC-22 is licensed desktop software that cannot be
  scripted, so a detector that needs it is not usable by anyone else; one built
  on word counting is.

* **Thresholds are learned inside the cross-validation loop, never on the full
  data.** A cut-point chosen by scanning all candidates on the same rows it is
  then scored against is optimistic, and that optimism is invisible in the
  output. Each fold here learns its own cut-point from the training rows only.

A rejected hyporeport, recorded because the result is informative. The initial
proposal was the inverse: since human documentation is more *dispersed*
(rq3_variance_test.py), perhaps a document whose every dimension sits near the
middle of the human distribution is machine-written. Scored as a detector this
reaches macro-F1 0.31 -- worse than chance, because it is backwards. Two
reasons. Z-scoring against a distribution divides its width out, so ~32% of
that distribution's own members exceed 1 SD regardless of how wide it is; and
variance is a property of a *set*, so a single document, having one value per
dimension, has none to measure. What actually separates the groups is location,
not spread: generated documents sit 1.2-2.0 human SDs *above* the human mean on
`BigWords`, i.e. further into the tail rather than nearer the centre. The
inverse rule is reported alongside the working one so the contrast is visible.

**Scope of the claim.** Per the information-asymmetry qualification in the RQ3
write-up, the two conditions differ in author *and* in available information
(project knowledge and adoption goals vs. API signatures alone). This therefore
detects documentation produced under the signatures-only condition, not
model-authored text in general, and will not transfer unchanged to text
generated with fuller context or a different prompt.

**External validation** (`--validate`). The headline number above is
cross-validated but still within one corpus, one genre and one prompt. Three
checks address that, all on data already collected, no new generation:

1. *Corpus quality.* rq3_readme_scope_audit.py flagged 47/100 human READMEs
   in the previous corpus as coming from the root of a multi-package repo (the
   module had no README, so the extractor fell back to the clone root). Hand
   grading rated 29 severe, 10 partial and 8 benign.
   The rule is re-evaluated with those excluded, and with the borderline tier
   excluded as well. If the detector depended on that artefact, removing it
   should hurt.
2. *Prompt robustness.* files/corpus/rq3/sensitivity/ holds generations under
   five prompt variants (anonymised library name, length cap, paraphrased
   instructions, explicit disclaimer). None were in training. Scored at the
   fixed threshold, so this is recall out of sample.
3. *Genre robustness.* The RQ1/RQ2 corpus (frame_locked, n=400) is human
   documentation of a different kind, full crawled documentation sites, not
   READMEs. Every flag there is a false positive, so this measures specificity
   on text the rule was never fitted to. Caveat: "human" is an assumption about
   documentation collected in 2026, not a verified label; any model-assisted
   text in it makes the measured false-positive rate an overestimate.

Usage:
    venv/bin/python3 src/rq4/rq4_detector.py            # evaluate
    venv/bin/python3 src/rq4/rq4_detector.py --validate # external checks
    venv/bin/python3 src/rq4/rq4_detector.py --score FILE ...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import RNG_SEED  # noqa: E402

CORPUS = ROOT / "files" / "corpus" / "rq3" / "rq3_libraries_prose.csv"
LIWC = ROOT / "files" / "corpus" / "rq3" / "LIWC-22 Results - rq3_libraries_prose - LIWC Analysis.csv"
OUT = ROOT / "files" / "analysis" / "rq4_detector_results.csv"

# --validate inputs
AUDIT = ROOT / "files" / "corpus" / "rq3" / "rq3_readme_scope_audit.csv"
SENSITIVITY_DIR = ROOT / "files" / "corpus" / "rq3" / "sensitivity"
PILOT_DIR = ROOT / "files" / "corpus" / "rq3" / "pilot_generation"
README_DIR = ROOT / "files" / "corpus" / "rq3" / "readme_only"
EXTERNAL_HUMAN = ROOT / "files" / "corpus" / "frame_locked" / "libraries.csv"
EXTERNAL_HUMAN_N2000 = (ROOT / "files" / "corpus" / "frame_n2000"
                        / "libraries.csv")
OUT_VALIDATION = ROOT / "files" / "analysis" / "rq4_detector_validation.csv"

# Tiers from rq3_readme_scope_audit.py, worst first. 'partial' = root README of
# a focused single-product repo; 'severe' = README of an unrelated or much
# larger project.
CLEAN_TIERS = ("ok", "benign")
BORDERLINE_TIERS = CLEAN_TIERS + ("partial",)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENT_RE = re.compile(r"[.!?]+(?:\s|$)")
BIG_WORD_CHARS = 7
N_FOLDS, N_REPEATS, N_PERMUTATIONS = 5, 10, 100
# Candidate cut-points are quantiles rather than every unique value: the
# macro-F1 surface over a threshold is piecewise-constant and smooth at this
# resolution, and the full scan made the permutation loop impractically slow.
N_THRESHOLD_CANDIDATES = 60


def features(text: str) -> dict[str, float]:
    """BigWords and WPS, computed from text without LIWC."""
    words = WORD_RE.findall(str(text))
    n = len(words)
    if not n:
        return {"BigWords": 0.0, "WPS": 0.0, "n_words": 0}
    sentences = max(1, len(SENT_RE.findall(str(text))))
    return {
        "BigWords": 100.0 * sum(1 for w in words if len(w) >= BIG_WORD_CHARS) / n,
        "WPS": n / sentences,
        "n_words": n,
    }


def best_threshold(x: np.ndarray, y: np.ndarray) -> float:
    """Cut-point maximising macro-F1 on the rows given. Training use only."""
    cands = np.unique(np.quantile(x, np.linspace(0.02, 0.98, N_THRESHOLD_CANDIDATES)))
    best, best_f1 = cands[0], -1.0
    for t in cands:
        f1 = f1_score(y, (x > t).astype(int), average="macro", zero_division=0)
        if f1 > best_f1:
            best, best_f1 = t, f1
    return float(best)


def cv_threshold_rule(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    """Out-of-fold predictions; each fold's threshold learned on its train rows."""
    pred = np.zeros(len(y), dtype=int)
    for tr, te in StratifiedKFold(N_FOLDS, shuffle=True, random_state=seed).split(x.reshape(-1, 1), y):
        pred[te] = (x[te] > best_threshold(x[tr], y[tr])).astype(int)
    return pred


def load_corpus() -> pd.DataFrame:
    """The RQ3 corpus with the two LIWC-free features attached."""
    import csv as _csv
    _csv.field_size_limit(sys.maxsize)
    df = pd.read_csv(CORPUS)
    feats = pd.DataFrame([features(t) for t in df.text])
    df = pd.concat([df.reset_index(drop=True), feats], axis=1)
    df["is_generated"] = (df.source != "human").astype(int)
    return df


def evaluate(x: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> dict:
    """Repeated CV of the threshold rule, plus its permutation null."""
    f1s, accs = [], []
    for rep in range(N_REPEATS):
        p = cv_threshold_rule(x, y, RNG_SEED + rep)
        f1s.append(f1_score(y, p, average="macro"))
        accs.append(accuracy_score(y, p))
    null = [f1_score(rng.permutation(y), cv_threshold_rule(x, y, RNG_SEED), average="macro")
            for _ in range(N_PERMUTATIONS)]
    thr = best_threshold(x, y)
    cm = confusion_matrix(y, (x > thr).astype(int))
    return {
        "n": len(y), "n_human": int((y == 0).sum()), "n_generated": int((y == 1).sum()),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "macro_f1_sd": round(float(np.std(f1s)), 4),
        "accuracy": round(float(np.mean(accs)), 4),
        "permutation_null": round(float(np.mean(null)), 4),
        "permutation_p": round((1 + sum(n >= np.mean(f1s) for n in null)) / (N_PERMUTATIONS + 1), 4),
        "threshold": round(float(thr), 2),
        "human_correct": int(cm[0][0]), "generated_correct": int(cm[1][1]),
    }


def main() -> None:
    if "--score" in sys.argv:
        score_files(sys.argv[sys.argv.index("--score") + 1:])
        return
    if "--validate" in sys.argv:
        validate()
        return

    df = load_corpus()

    print(f"Corpus: {len(df)} documents "
          f"({(df.is_generated == 0).sum()} human, {(df.is_generated == 1).sum()} generated)\n")

    # --- validate the LIWC-free feature against LIWC itself
    liwc = pd.read_csv(LIWC)[["library", "ecosystem", "source", "BigWords", "WPS"]]
    m = df.merge(liwc, on=["library", "ecosystem", "source"], suffixes=("_mine", "_liwc"))
    print("Feature validation against LIWC-22 on the same documents:")
    for f in ("BigWords", "WPS"):
        diff = (m[f"{f}_mine"] - m[f"{f}_liwc"]).abs()
        print(f"  {f:9s} r = {m[f'{f}_mine'].corr(m[f'{f}_liwc']):.3f}   "
              f"mean |difference| = {diff.mean():.2f}   max = {diff.max():.2f}")

    y = df.is_generated.to_numpy()
    rng = np.random.default_rng(RNG_SEED)
    rows = []

    print(f"\nEvaluation: {N_FOLDS}-fold CV repeated {N_REPEATS}x, "
          f"threshold learned per fold on training rows only.\n")
    for feat in ("BigWords", "WPS"):
        x = df[feat].to_numpy()
        f1s, accs, thrs = [], [], []
        for rep in range(N_REPEATS):
            p = cv_threshold_rule(x, y, RNG_SEED + rep)
            f1s.append(f1_score(y, p, average="macro"))
            accs.append(accuracy_score(y, p))
            thrs.append(best_threshold(x, y))
        null = [f1_score(rng.permutation(y), cv_threshold_rule(x, y, RNG_SEED), average="macro")
                for _ in range(N_PERMUTATIONS)]
        p_val = (1 + sum(n >= np.mean(f1s) for n in null)) / (N_PERMUTATIONS + 1)
        print(f"  {feat:9s} macro-F1 {np.mean(f1s):.3f} (SD {np.std(f1s):.3f})   "
              f"acc {np.mean(accs):.3f}   permutation null {np.mean(null):.3f}   p = {p_val:.4f}")
        rows.append({"rule": f"{feat} threshold", "macro_f1": round(float(np.mean(f1s)), 4),
                     "macro_f1_sd": round(float(np.std(f1s)), 4),
                     "accuracy": round(float(np.mean(accs)), 4),
                     "permutation_null": round(float(np.mean(null)), 4),
                     "permutation_p": round(p_val, 4),
                     "typical_threshold": round(float(np.median(thrs)), 2)})

    # --- the rejected inverse hypothesis, scored for the record
    inv = inverse_rule(df)
    rows.append(inv)
    print(f"\n  {'centrality':9s} macro-F1 {inv['macro_f1']:.3f}   acc {inv['accuracy']:.3f}"
          f"   <- the rejected 'all dimensions within 1 SD => generated' rule")

    thr = float(np.median([best_threshold(df.BigWords.to_numpy(), y)]))
    print(f"\nConfusion matrix, BigWords > {thr:.1f} (rows actual, cols predicted):")
    cm = confusion_matrix(y, (df.BigWords > thr).astype(int))
    print(f"            pred human  pred generated")
    print(f"  human   {cm[0][0]:10d}{cm[0][1]:16d}")
    print(f"  generated{cm[1][0]:9d}{cm[1][1]:16d}")

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nWrote {OUT}")


def _stripped_bigwords(path: Path) -> float:
    """BigWords on the same footing as the scored corpus.

    The held-out generations on disk are raw model output, code blocks and
    all, while the corpus the rule was fitted on had code removed from both
    sides (rq3_build_libraries_csv_prose.py). Scoring them raw would inflate
    BigWords with identifiers and camelCase, which is the exact mistake the
    prose rebuild existed to fix, so the same _md_to_text pass is
    applied here before the feature is computed.
    """
    from confirmatory_preprocessor import _md_to_text  # noqa: PLC0415
    return features(_md_to_text(path.read_text(errors="ignore")))["BigWords"]


def validate() -> None:
    """Three external checks on the BigWords rule, see the module docstring."""
    df = load_corpus()
    rng = np.random.default_rng(RNG_SEED)
    rows = []

    # --- 1. corpus quality: does the rule depend on the mismatched READMEs?
    print("=== 1. README-scope sensitivity (rq3_readme_scope_audit.py tiers) ===")
    if not AUDIT.exists():
        print(f"  {AUDIT.name} not found — run src/generation/rq3_readme_scope_audit.py first\n")
    else:
        audit = pd.read_csv(AUDIT)
        if "tier" not in audit.columns:
            audit["tier"] = np.where(audit.verdict == "root_monorepo", "severe", "ok")
        tiers = audit[["library", "tier"]]
        tagged = df.merge(tiers, on="library", how="left")
        coverage = tagged.tier.notna().mean()
        # After the rebuild the corpus is clean by construction and
        # the audit covers the *previous* sample, so a low overlap means this
        # check no longer applies rather than that the rule failed.
        print(f"  audit covers {coverage:.0%} of the current corpus")
        subsets = [("all documents", set(tagged.tier.dropna().unique())),
                   ("severe excluded", set(BORDERLINE_TIERS)),
                   ("clean only", set(CLEAN_TIERS))]
        for label, keep in subsets:
            s = tagged[tagged.tier.isin(keep)]
            r = evaluate(s.BigWords.to_numpy(), s.is_generated.to_numpy(), rng)
            rows.append({"check": "readme_scope", "subset": label, **r})
            print(f"  {label:16s} n={r['n']:3d} ({r['n_human']}h/{r['n_generated']}g)  "
                  f"macro-F1 {r['macro_f1']:.3f} (SD {r['macro_f1_sd']:.3f})  "
                  f"acc {r['accuracy']:.3f}  threshold {r['threshold']:.1f}  "
                  f"p = {r['permutation_p']:.4f}")
        print()

    # Held-out checks score at the threshold the full corpus learns, rather than
    # refitting: the point is whether *this* rule transfers, not whether some
    # rule could be fitted to each new set.
    thr = best_threshold(df.BigWords.to_numpy(), df.is_generated.to_numpy())
    print(f"Held-out checks below use the corpus threshold, BigWords > {thr:.1f}\n")

    # --- 2. prompt robustness: recall on generations from other prompts
    print("=== 2. Prompt-variant generations (held out, recall) ===")
    variants: dict[str, list[float]] = {}
    for path in sorted(SENSITIVITY_DIR.glob("*.txt")):
        m = re.match(r"(.+?)_(V\d_[a-z_]+)_(openai|sonnet)\.txt$", path.name)
        if m:
            variants.setdefault(m.group(2), []).append(_stripped_bigwords(path))
    if not variants:
        print(f"  no generations found in {SENSITIVITY_DIR}\n")
    else:
        for name, vals in sorted(variants.items()):
            flagged = sum(v > thr for v in vals)
            rows.append({"check": "prompt_variant", "subset": name, "n": len(vals),
                         "n_generated": len(vals), "generated_correct": flagged,
                         "threshold": round(thr, 2),
                         "mean_bigwords": round(float(np.mean(vals)), 2)})
            print(f"  {name:24s} flagged {flagged}/{len(vals)}   "
                  f"mean BigWords {np.mean(vals):.1f}")
        pilot = [_stripped_bigwords(p) for p in sorted(PILOT_DIR.glob("*.txt"))
                 if p.suffix == ".txt" and p.name.endswith(("_openai.txt", "_sonnet.txt"))]
        if pilot:
            n_flag_p = sum(v > thr for v in pilot)
            rows.append({"check": "prompt_variant", "subset": "pilot run",
                         "n": len(pilot), "n_generated": len(pilot),
                         "generated_correct": n_flag_p, "threshold": round(thr, 2),
                         "mean_bigwords": round(float(np.mean(pilot)), 2)})
            print(f"  {'pilot run':24s} flagged {n_flag_p}/{len(pilot)}   "
                  f"mean BigWords {np.mean(pilot):.1f}")

        # Human control: the real READMEs of the same libraries, so the
        # variant recall above has something on the other side of the line.
        libs = {re.match(r"(.+?)_V\d", p.name).group(1)
                for p in SENSITIVITY_DIR.glob("*.txt") if re.match(r"(.+?)_V\d", p.name)}
        ctrl = [features((README_DIR / "python" / f"{lib}.txt").read_text(errors="ignore"))["BigWords"]
                for lib in sorted(libs) if (README_DIR / "python" / f"{lib}.txt").exists()]
        if ctrl:
            n_flag_c = sum(v > thr for v in ctrl)
            rows.append({"check": "prompt_variant", "subset": "human control (same libraries)",
                         "n": len(ctrl), "n_human": len(ctrl),
                         "human_correct": len(ctrl) - n_flag_c, "threshold": round(thr, 2),
                         "mean_bigwords": round(float(np.mean(ctrl)), 2)})
            print(f"  {'human control':24s} flagged {n_flag_c}/{len(ctrl)} "
                  f"(false alarms)   mean BigWords {np.mean(ctrl):.1f}")

        allv = [v for vals in variants.values() for v in vals]
        n_flag = sum(v > thr for v in allv)
        rows.append({"check": "prompt_variant", "subset": "all variants", "n": len(allv),
                     "n_generated": len(allv), "generated_correct": n_flag,
                     "threshold": round(thr, 2),
                     "mean_bigwords": round(float(np.mean(allv)), 2)})
        print(f"  {'all variants':24s} flagged {n_flag}/{len(allv)} "
              f"= {n_flag / len(allv):.1%} recall\n")

    # --- 3. genre robustness: false positives on human documentation sites
    print("=== 3. External human corpus (RQ1/RQ2 frame — crawled docs, not READMEs) ===")
    if not EXTERNAL_HUMAN.exists():
        print(f"  {EXTERNAL_HUMAN} not found\n")
    else:
        import csv as _csv
        _csv.field_size_limit(sys.maxsize)
        frames = [("n=400 frame", EXTERNAL_HUMAN)]
        if EXTERNAL_HUMAN_N2000.exists():
            frames.append(("n=2000 frame", EXTERNAL_HUMAN_N2000))
        ext = pd.concat([pd.read_csv(f).assign(frame=name) for name, f in frames],
                        ignore_index=True)
        ext["BigWords"] = [features(t)["BigWords"] for t in ext.text]
        groups = ([("all", ext)]
                  + [(f, ext[ext.frame == f]) for f in ext.frame.unique()]
                  + [(e, ext[ext.ecosystem == e]) for e in sorted(ext.ecosystem.unique())])
        for label, sub in groups:
            fp = int((sub.BigWords > thr).sum())
            rows.append({"check": "external_human", "subset": label, "n": len(sub),
                         "n_human": len(sub), "human_correct": len(sub) - fp,
                         "threshold": round(thr, 2),
                         "mean_bigwords": round(float(sub.BigWords.mean()), 2)})
            print(f"  {label:8s} n={len(sub):3d}  mean BigWords {sub.BigWords.mean():.1f}  "
                  f"false positives {fp}/{len(sub)} = {fp / len(sub):.1%}  "
                  f"(specificity {1 - fp / len(sub):.1%})")
        print("  Note: 'human' is an assumption about 2026 documentation, not a "
              "verified label;\n  model-assisted text there inflates this "
              "false-positive rate rather than deflating it.\n")

    pd.DataFrame(rows).to_csv(OUT_VALIDATION, index=False)
    print(f"Wrote {OUT_VALIDATION}")


def inverse_rule(df: pd.DataFrame) -> dict:
    """Score the rejected hypothesis: every dimension within 1 SD => generated."""
    dims = ["BigWords", "WPS"]
    preds, ys = [], []
    for eco in df.ecosystem.unique():
        H = df[(df.ecosystem == eco) & (df.source == "human")]
        for _, r in df[df.ecosystem == eco].iterrows():
            ref = H[H.library != r.library] if r.source == "human" else H
            z = [abs((r[c] - ref[c].mean()) / ref[c].std()) for c in dims]
            preds.append(int(max(z) <= 1))
            ys.append(int(r.source != "human"))
    return {"rule": "centrality (rejected)",
            "macro_f1": round(f1_score(ys, preds, average="macro"), 4),
            "macro_f1_sd": None,
            "accuracy": round(accuracy_score(ys, preds), 4),
            "permutation_null": None, "permutation_p": None, "typical_threshold": None}


def score_files(paths: list[str]) -> None:
    """Classify documents given as files, showing the evidence."""
    import csv as _csv
    _csv.field_size_limit(sys.maxsize)
    df = pd.read_csv(CORPUS)
    f = pd.DataFrame([features(t) for t in df.text])
    y = (df.source != "human").astype(int).to_numpy()
    thr = best_threshold(f.BigWords.to_numpy(), y)
    human = f.BigWords[y == 0]
    print(f"Threshold learned from the corpus: BigWords > {thr:.1f}")
    print(f"Human reference: mean {human.mean():.1f}, SD {human.std():.1f}\n")
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"  {p}: not found"); continue
        s = features(path.read_text(errors="ignore"))
        z = (s["BigWords"] - human.mean()) / human.std()
        verdict = "GENERATED" if s["BigWords"] > thr else "human"
        print(f"  {path.name}")
        print(f"     BigWords {s['BigWords']:.1f}%  ({z:+.2f} SD vs human)   "
              f"WPS {s['WPS']:.1f}   {s['n_words']} words")
        print(f"     -> {verdict}")
        if s["n_words"] < 100:
            print("     (under 100 words; percentage features are unstable here)")


if __name__ == "__main__":
    main()
