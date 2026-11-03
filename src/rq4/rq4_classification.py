"""
rq4_classification: can a classifier recover the ecosystem origin of a library's
documentation from its 15-dimensional LIWC profile alone?

RQ1 tests each dimension on its own. This tests whether a combination of them
separates the languages. Models use library defaults, so the score isn't the
product of a search.

Design:

* **Scaling happens inside each CV fold**, so no test-fold information leaks.
* **Logistic regression is primary.** SVM and random forest are checks, and the
  forest is the one model that can find a non-linear boundary.
* **RepeatedStratifiedKFold(5, 10)** gives 50 fold scores, so one split can't
  decide the result. Both a fold-spread CI and a bootstrap CI of the mean are saved.
* **Three baselines:** majority-class macro-F1 (0.333, accuracy 0.50), stratified
  random, and a permutation null. Use --permutations to set the shuffle count. The
  smallest possible p is 1 / (n + 1), so 100 shuffles give a floor of 0.0099.
* **The 0.75 target** was written for three languages. It is reported as written.
* **The domain task** runs on the 345 of 400 rows with domain tags, and is provisional.
* **Spurious numpy matmul warnings** are filtered. Under numpy 2.0.2, lbfgs logistic
  fits emit overflow warnings from `X @ weights`, but all the solvers tested return
  macro-F1 = 0.6187 with finite coefficients, so this isn't a convergence failure.
* **The held-out 20% split** is reported but isn't the headline, as 80 documents
  are too noisy next to a 50-fold estimate.

Inputs:
  files/corpus/frame_locked_corrected/
      LIWC-22 Results - libraries - LIWC Analysis.csv

Outputs:
  files/corpus/frame_locked_corrected/rq4_classification_results.csv
  files/analysis/figures/rq4_01_ecosystem_classification.png

Usage:
    venv/bin/python3 src/rq4/rq4_classification.py [--freeze-date locked_corrected]
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import (
    RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict,
    cross_val_score, train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

# See the "spurious numpy matmul warnings" note in the module docstring: the
# four solvers agree to 4 d.p., so these flags carry no information and would
# otherwise drown the output.
warnings.filterwarnings("ignore", message=".*encountered in matmul.*",
                        category=RuntimeWarning)

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(p) for p in Path(__file__).resolve().parents[1].iterdir() if p.is_dir()]
from confirmatory_liwc_stats import LOCKED_DIMENSIONS, RNG_SEED  # noqa: E402

FIG_DIR = ROOT / "files" / "analysis" / "figures"

# Shared with confirmatory_plots.py so figures across the report agree.
ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77"}

N_SPLITS = 5
N_REPEATS = 10
N_PERMUTATIONS = 499   # Override with --permutations N.
                      # >=499 keeps the empirical p-value off its resolution
                      # floor: with n_perm=100 the smallest attainable p is
                      # 1/101 ~ 0.0099, which is exactly what the first run
                      # reported. 999 is the conventional figure; 499 gives
                      # a floor of 0.002 at roughly half the cost.

N_BOOT = 2000
HOLDOUT_FRAC = 0.20
MIN_STRATUM = 10          # original plan's pooling rule for the domain task
TARGET_THRESHOLD = 0.75   # RULES.md, written under the 3-ecosystem design


def build_models() -> dict[str, Pipeline]:
    """Primary + two robustness models, each with fold-internal scaling."""
    return {
        "logistic_regression": Pipeline([
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=5000, random_state=RNG_SEED)),
        ]),
        "linear_svm": Pipeline([
            ("scale", StandardScaler()),
            ("clf", LinearSVC(max_iter=20000, dual="auto", random_state=RNG_SEED)),
        ]),
        "random_forest": Pipeline([
            ("scale", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=300, n_jobs=-1,
                                           random_state=RNG_SEED)),
        ]),
    }


def macro_f1_cv(model, X: np.ndarray, y: np.ndarray, seed: int,
                n_repeats: int = N_REPEATS) -> np.ndarray:
    """Per-fold macro-F1 over stratified k-fold repeated `n_repeats` times."""
    cv = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=n_repeats,
                                 random_state=seed)
    return cross_val_score(model, X, y, cv=cv, scoring="f1_macro", n_jobs=1)


def bootstrap_mean_ci(scores: np.ndarray, rng: np.random.Generator,
                      n_boot: int = N_BOOT) -> tuple[float, float]:
    """95% percentile bootstrap CI for the mean of the fold scores."""
    idx = rng.integers(0, len(scores), size=(n_boot, len(scores)))
    means = scores[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


_N_PERM = N_PERMUTATIONS   # set from --permutations in main()


def resolve_n_permutations() -> int:
    """Permutation count, overridable with `--permutations N`.

    Kept as a run-time choice because the cost is linear in this number and
    dominates the whole analysis: 499 is enough to move the empirical
    p-value off its resolution floor, 999 is the conventional figure, and
    100 (the original run) pins p at 1/101.
    """
    return _N_PERM


def permutation_null(model, X: np.ndarray, y: np.ndarray,
                     rng: np.random.Generator,
                     n_perm: int = N_PERMUTATIONS) -> np.ndarray:
    """Mean CV macro-F1 under `n_perm` independent label shuffles.

    One (non-repeated) 5-fold pass per permutation: the quantity being
    estimated is the *distribution* of the statistic under the null, and
    spending 10 repeats per permutation would buy precision on each draw
    at the cost of draws, which is the wrong trade for a tail probability.
    """
    out = np.empty(n_perm)
    t0 = time.time()
    for i in range(n_perm):
        # Progress to stderr: a permutation run at n_perm>=499 takes long
        # enough that a silent process is indistinguishable from a hung one.
        if n_perm >= 200 and i and i % 50 == 0:
            rate = (time.time() - t0) / i
            print(f"      permutation {i}/{n_perm} "
                  f"(~{rate * (n_perm - i) / 60:.1f} min remaining)",
                  file=sys.stderr, flush=True)
        y_perm = rng.permutation(y)
        out[i] = macro_f1_cv(model, X, y_perm, seed=RNG_SEED + 1000 + i,
                             n_repeats=1).mean()
    return out


def run_task(task: str, X: np.ndarray, y: np.ndarray, labels: list[str],
             rng: np.random.Generator, note: str = "") -> tuple[list[dict], dict]:
    """Full RQ4 protocol for one label set. Returns (result rows, extras)."""
    print(f"\n=== Task: {task}  (n={len(y)}, {len(labels)} classes) ===")
    rows: list[dict] = []
    extras: dict = {}

    # ---- baselines, all under the same CV scheme ------------------------
    majority = DummyClassifier(strategy="most_frequent")
    majority_f1 = float(macro_f1_cv(majority, X, y, seed=RNG_SEED).mean())
    majority_acc = float(cross_val_score(
        majority, X, y,
        cv=RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS,
                                   random_state=RNG_SEED),
        scoring="accuracy").mean())
    stratified = DummyClassifier(strategy="stratified", random_state=RNG_SEED)
    stratified_f1 = float(macro_f1_cv(stratified, X, y, seed=RNG_SEED).mean())
    print(f"  baseline  majority-class : macro-F1 = {majority_f1:.4f} "
          f"(accuracy = {majority_acc:.4f})")
    print(f"  baseline  stratified-rand: macro-F1 = {stratified_f1:.4f}")

    for name, model in build_models().items():
        scores = macro_f1_cv(model, X, y, seed=RNG_SEED)
        mean = float(scores.mean())
        fold_lo, fold_hi = (float(v) for v in np.percentile(scores, [2.5, 97.5]))
        boot_lo, boot_hi = bootstrap_mean_ci(scores, rng)

        # pre-specified held-out split, reported but not headline
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=HOLDOUT_FRAC, stratify=y, random_state=RNG_SEED)
        model.fit(X_tr, y_tr)
        holdout_f1 = float(f1_score(y_te, model.predict(X_te),
                                    average="macro", zero_division=0))

        null = permutation_null(model, X, y, rng, n_perm=resolve_n_permutations())
        p_emp = float((1 + np.sum(null >= mean)) / (1 + len(null)))

        print(f"  {name:22s} macro-F1 = {mean:.4f}  "
              f"[fold 95% {fold_lo:.3f}-{fold_hi:.3f}] "
              f"[boot-mean 95% {boot_lo:.3f}-{boot_hi:.3f}]  "
              f"holdout={holdout_f1:.3f}  perm-null mean={null.mean():.4f}  "
              f"p={p_emp:.4f}")

        rows.append({
            "task": task,
            "model": name,
            "n": len(y),
            "n_classes": len(labels),
            "macro_f1_cv_mean": round(mean, 4),
            "macro_f1_cv_sd": round(float(scores.std(ddof=1)), 4),
            "macro_f1_fold_ci_lo": round(fold_lo, 4),
            "macro_f1_fold_ci_hi": round(fold_hi, 4),
            "macro_f1_boot_mean_ci_lo": round(boot_lo, 4),
            "macro_f1_boot_mean_ci_hi": round(boot_hi, 4),
            "macro_f1_holdout_20pct": round(holdout_f1, 4),
            "majority_baseline_macro_f1": round(majority_f1, 4),
            "majority_baseline_accuracy": round(majority_acc, 4),
            "stratified_random_baseline_macro_f1": round(stratified_f1, 4),
            "permutation_null_mean": round(float(null.mean()), 4),
            "permutation_null_sd": round(float(null.std(ddof=1)), 4),
            "permutation_null_p95": round(float(np.percentile(null, 95)), 4),
            "permutation_p_value": round(p_emp, 4),
            # The only cross-task-comparable quantity: macro-F1's scale depends
            # on the number of classes, so 0.62 (2 classes) and 0.13 (9 classes)
            # cannot be compared raw. Lift over each task's own empirical chance
            # level can be.
            "lift_over_permutation_null": round(mean - float(null.mean()), 4),
            "n_permutations": len(null),
            "meets_target_0.75": bool(mean >= TARGET_THRESHOLD),
            "beats_majority_baseline_ci": bool(boot_lo > majority_f1),
            "beats_stratified_baseline_ci": bool(boot_lo > stratified_f1),
            "note": note,
        })

        if name == "logistic_regression":
            extras["perm_null"] = null
            extras["fold_scores"] = scores
            extras["majority_f1"] = majority_f1
            extras["observed_f1"] = mean

            # out-of-fold confusion matrix from one clean 5-fold pass
            cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True,
                                 random_state=RNG_SEED)
            y_pred = cross_val_predict(model, X, y, cv=cv)
            extras["confusion"] = confusion_matrix(y, y_pred, labels=labels)
            extras["labels"] = labels

            # coefficients: full-corpus refit (reportable) + fold stability
            model.fit(X, y)
            coefs = model.named_steps["clf"].coef_
            extras["coefs"] = coefs
            fold_coefs = []
            for tr, _ in cv.split(X, y):
                m = build_models()["logistic_regression"]
                m.fit(X[tr], y[tr])
                fold_coefs.append(m.named_steps["clf"].coef_)
            extras["fold_coefs"] = np.array(fold_coefs)

    return rows, extras


def coefficient_table(extras: dict) -> pd.DataFrame:
    """Logistic coefficients on z-scored features, sorted by |coef|."""
    coefs = extras["coefs"]
    fold = extras["fold_coefs"]
    labels = extras["labels"]
    recs = []
    for r in range(coefs.shape[0]):
        cls = labels[1] if coefs.shape[0] == 1 else labels[r]
        for j, dim in enumerate(LOCKED_DIMENSIONS):
            recs.append({
                "class_positive": cls,
                "dimension": dim,
                "coefficient": round(float(coefs[r, j]), 4),
                "abs_coefficient": round(abs(float(coefs[r, j])), 4),
                "fold_sd": round(float(fold[:, r, j].std(ddof=1)), 4),
                "sign_stable_across_folds": bool(
                    np.all(np.sign(fold[:, r, j]) == np.sign(coefs[r, j]))),
            })
    return (pd.DataFrame(recs)
            .sort_values("abs_coefficient", ascending=False)
            .reset_index(drop=True))


def make_figure(extras: dict, coef_df: pd.DataFrame, out_path: Path) -> None:
    """Three panels: permutation null, confusion matrix, coefficients."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))

    # --- permutation null vs observed ---------------------------------
    ax = axes[0]
    null = extras["perm_null"]
    ax.hist(null, bins=24, color="#b0b0b0", edgecolor="white",
            label=f"permutation null (n={len(null)})")
    ax.axvline(extras["observed_f1"], color=ECO_COLORS["java"], lw=2.2,
               label=f"observed = {extras['observed_f1']:.3f}")
    ax.axvline(extras["majority_f1"], color="#333333", ls="--", lw=1.6,
               label=f"majority baseline = {extras['majority_f1']:.3f}")
    ax.axvline(TARGET_THRESHOLD, color=ECO_COLORS["python"], ls=":", lw=1.8,
               label=f"target = {TARGET_THRESHOLD:.2f}\n(set under 3-class design)")
    ax.set_xlabel("macro-F1")
    ax.set_ylabel("permutations")
    ax.set_title("A. Observed vs permutation null\n(logistic, ecosystem)",
                 fontsize=10)
    ax.legend(fontsize=7, loc="upper right")

    # --- confusion matrix ---------------------------------------------
    ax = axes[1]
    cm = extras["confusion"]
    labels = extras["labels"]
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=cm.max())
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() * 0.6 else "black",
                    fontsize=11)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("B. Out-of-fold confusion matrix\n(logistic, ecosystem)",
                 fontsize=10)

    # --- coefficients ---------------------------------------------------
    ax = axes[2]
    d = coef_df.sort_values("coefficient")
    # Colour by the class the coefficient pushes towards, matching the axis
    # label below: negative -> labels[0] (java), positive -> labels[1] (python).
    neg_color = ECO_COLORS.get(extras["labels"][0], "#d95f02")
    pos_color = ECO_COLORS.get(extras["labels"][1], "#1b9e77")
    colors = [neg_color if c < 0 else pos_color for c in d["coefficient"]]
    ax.barh(d["dimension"], d["coefficient"], color=colors,
            xerr=d["fold_sd"], error_kw=dict(ecolor="#555555", lw=0.8))
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel(f"logistic coefficient (z-scored features)\n"
                  f"negative -> {extras['labels'][0]},  positive -> {extras['labels'][1]}")
    ax.set_title("C. Coefficients, full-corpus refit\n(bars: SD across 5 folds)",
                 fontsize=10)
    ax.tick_params(axis="y", labelsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    print(f"\nWrote {out_path}")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date", default="locked_corrected")
    ap.add_argument("--permutations", type=int, default=N_PERMUTATIONS,
                    help="permutation-null draws; cost is linear in this and "
                         "dominates the run (100 pins p at 1/101; 499 gives a "
                         "floor of 0.002; 999 is the conventional figure)")
    args = ap.parse_args()
    global _N_PERM
    _N_PERM = args.permutations

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    liwc_csv = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    out_csv = frame_dir / "rq4_classification_results.csv"
    if not liwc_csv.exists():
        raise SystemExit(f"LIWC output not found: {liwc_csv}")

    df = pd.read_csv(liwc_csv)
    print(f"Loaded {len(df)} libraries from {liwc_csv.name}")
    print(f"  ecosystem: {df['ecosystem'].value_counts().to_dict()}")
    print(f"  domain:    {df['domain'].value_counts().to_dict()}")

    missing = [d for d in LOCKED_DIMENSIONS if d not in df.columns]
    if missing:
        raise SystemExit(f"locked dimensions missing from LIWC output: {missing}")

    feat = df[LOCKED_DIMENSIONS].apply(pd.to_numeric, errors="coerce")
    if feat.isna().any().any():
        bad = feat.columns[feat.isna().any()].tolist()
        raise SystemExit(f"non-numeric / missing values in dimensions: {bad}")
    X = feat.to_numpy(dtype=float)

    if df["ecosystem"].isna().any():
        raise SystemExit("ecosystem label missing on some rows — stop and fix")

    # ---- domain label coverage: a gap in this frame, stated not hidden ---
    dom_missing = int(df["domain"].isna().sum())
    dom_note = ""
    if dom_missing:
        skew = df[df["domain"].isna()]["ecosystem"].value_counts().to_dict()
        dom_note = (f"domain task run on {len(df) - dom_missing}/{len(df)} rows; "
                    f"{dom_missing} rows have no domain tag in this frame "
                    f"(missing by ecosystem: {skew})")
        print("\n" + "!" * 72)
        print("DATA GAP — domain labels are incomplete in this frame")
        print(f"  {dom_missing}/{len(df)} rows carry no domain tag "
              f"({100 * dom_missing / len(df):.1f}%).")
        print(f"  Missing rows by ecosystem: {skew}  <- NOT balanced.")
        print("  frame_locked (pre-dedup) has all 400 rows tagged; the")
        print("  re-clone/re-scope step that produced this frame did not")
        print("  re-derive domain tags for the rows it touched.")
        print("  The ecosystem task (RQ4 primary) is UNAFFECTED.")
        print("  The domain confound test runs on the tagged subset")
        print("  only and its comparison to ecosystem is PROVISIONAL until")
        print("  the tags are regenerated.")
        print("!" * 72)

    dom_df = df[df["domain"].notna()]
    X_dom = dom_df[LOCKED_DIMENSIONS].to_numpy(dtype=float)

    # Domain pooling rule: assert rather than assume.
    dom_counts = dom_df["domain"].value_counts()
    small = dom_counts[dom_counts < MIN_STRATUM]
    if len(small):
        raise SystemExit(
            f"domain strata below n={MIN_STRATUM} present ({small.to_dict()}); "
            "the pre-specified pooling rule needs a decision before this runs")
    print(f"\n  all {len(dom_counts)} tagged domain strata have n >= {MIN_STRATUM} "
          f"(min = {dom_counts.min()}, '{dom_counts.idxmin()}') — "
          "no pooling or dropping applied")

    rng = np.random.default_rng(RNG_SEED)

    eco_labels = sorted(df["ecosystem"].unique())
    eco_rows, eco_extras = run_task("ecosystem", X,
                                    df["ecosystem"].to_numpy(), eco_labels, rng,
                                    note="all 400 rows")

    dom_labels = sorted(dom_df["domain"].unique())
    dom_rows, _ = run_task("domain", X_dom, dom_df["domain"].to_numpy(),
                           dom_labels, rng, note=dom_note or "all rows tagged")

    res = pd.DataFrame(eco_rows + dom_rows)
    res.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    coef_df = coefficient_table(eco_extras)
    print("\n=== Logistic coefficients, ecosystem task (z-scored features) ===")
    print(coef_df.to_string(index=False))

    coef_csv = frame_dir / "rq4_logistic_coefficients.csv"
    coef_df.to_csv(coef_csv, index=False)
    print(f"Wrote {coef_csv}")

    print("\n=== Out-of-fold confusion matrix (logistic, ecosystem) ===")
    print(pd.DataFrame(eco_extras["confusion"],
                       index=[f"true_{l}" for l in eco_labels],
                       columns=[f"pred_{l}" for l in eco_labels]).to_string())

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    make_figure(eco_extras, coef_df,
                FIG_DIR / "rq4_01_ecosystem_classification.png")

    # ---- verdict --------------------------------------------------------
    eco_primary = res[(res.task == "ecosystem") &
                      (res.model == "logistic_regression")].iloc[0]
    dom_primary = res[(res.task == "domain") &
                      (res.model == "logistic_regression")].iloc[0]
    print("\n=== RQ4 verdict ===")
    print(f"  ecosystem macro-F1 = {eco_primary.macro_f1_cv_mean:.4f} "
          f"(95% CI on mean {eco_primary['macro_f1_boot_mean_ci_lo']:.4f}-"
          f"{eco_primary['macro_f1_boot_mean_ci_hi']:.4f})")
    print(f"  vs target threshold {TARGET_THRESHOLD:.2f} "
          f"(set under the 3-ecosystem design, before JavaScript was dropped): "
          f"{'MET' if eco_primary['meets_target_0.75'] else 'NOT MET'}")
    print(f"  vs majority-class baseline macro-F1 "
          f"{eco_primary['majority_baseline_macro_f1']:.4f} "
          f"(its accuracy = {eco_primary['majority_baseline_accuracy']:.4f}): "
          f"{'above (CI excludes it)' if eco_primary['beats_majority_baseline_ci'] else 'not separated'}")
    print(f"  vs stratified-random baseline macro-F1 "
          f"{eco_primary['stratified_random_baseline_macro_f1']:.4f} "
          "(the ~0.50 binary chance level, commensurable with macro-F1): "
          f"{'above (CI excludes it)' if eco_primary['beats_stratified_baseline_ci'] else 'not separated'}")
    print(f"  permutation p = {eco_primary['permutation_p_value']:.4f} "
          f"({eco_primary['n_permutations']} relabelings)")
    print(f"  domain macro-F1 = {dom_primary.macro_f1_cv_mean:.4f} "
          f"({dom_primary.n_classes} classes, n={dom_primary.n}) — "
          f"{'HIGHER' if dom_primary.macro_f1_cv_mean > eco_primary.macro_f1_cv_mean else 'NOT higher'} "
          "than ecosystem (confound test)")
    if dom_missing:
        print(f"  [provisional] {dom_note}")


if __name__ == "__main__":
    main()
