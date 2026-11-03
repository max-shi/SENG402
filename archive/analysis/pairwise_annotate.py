"""
pairwise_annotate: interactive CLI tool to visually inspect every
pairwise combination of the 15 locked LIWC dimensions and record a
one-line synopsis for each, added
to visually check for cluster/spread structure the
significance tables don't show.

For each of the 105 unique pairs (15 choose 2), pops up a scatter plot
of all 400 confirmatory libraries (colored by ecosystem), then prompts
in the terminal for a typed synopsis (e.g. "no spread", "some spread",
"java clusters top-right"). Press Enter to save the note and advance to
the next pair. Progress is saved after every pair, so the tool can be
safely interrupted (Ctrl-C, or typing 'q') and resumed later,
already-annotated pairs are skipped on the next run.

Requires a local display (run directly in a terminal on your machine,
not headless), uses matplotlib's interactive "macosx" backend.

Inputs:
  files/corpus/frame_<freeze-date>/LIWC-22 Results - libraries - LIWC Analysis.csv

Outputs (appended to incrementally):
  files/corpus/frame_<freeze-date>/pairwise_annotations.csv

Usage:
    venv/bin/python3 src/analysis/pairwise_annotate.py [--freeze-date <name>] [--restart]

Controls at each prompt:
    <type a synopsis> + Enter  , save the note, advance to next pair
    <blank> + Enter             , save an empty note, advance
    q + Enter                   , quit; progress already saved
"""
from __future__ import annotations

import argparse
import csv
from itertools import combinations
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

LOCKED_DIMENSIONS = [
    "emotion", "emo_neg", "emo_anger", "emo_sad", "Tone",
    "WPS", "BigWords", "ipron",
    "tentat", "certitude",
    "curiosity", "achieve", "risk",
    "motion", "conflict",
]

ECO_COLORS = {"java": "#d95f02", "python": "#1b9e77"}
FIELDNAMES = ["pair_index", "dim_x", "dim_y", "synopsis"]


def load_data(freeze_date: str) -> pd.DataFrame:
    frame_dir = ROOT / "files" / "corpus" / f"frame_{freeze_date}"
    liwc_csv = frame_dir / "LIWC-22 Results - libraries - LIWC Analysis.csv"
    if not liwc_csv.exists():
        raise SystemExit(f"LIWC output not found: {liwc_csv}")
    return pd.read_csv(liwc_csv)


def load_existing(out_csv: Path) -> dict[tuple[str, str], str]:
    if not out_csv.exists():
        return {}
    done = {}
    with open(out_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            done[(row["dim_x"], row["dim_y"])] = row["synopsis"]
    return done


def append_row(out_csv: Path, row: dict, write_header: bool) -> None:
    with open(out_csv, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-date", default="locked")
    ap.add_argument("--restart", action="store_true",
                    help="ignore any existing annotations and start from pair 1")
    args = ap.parse_args()

    frame_dir = ROOT / "files" / "corpus" / f"frame_{args.freeze_date}"
    out_csv = frame_dir / "pairwise_annotations.csv"

    df = load_data(args.freeze_date)
    pairs = list(combinations(LOCKED_DIMENSIONS, 2))
    print(f"{len(pairs)} pairs total (15 locked dimensions, all unique combinations).")

    done = {} if args.restart else load_existing(out_csv)
    if done:
        print(f"Resuming: {len(done)} pairs already annotated in {out_csv}")
    write_header = args.restart or not out_csv.exists()

    plt.ion()
    fig, ax = plt.subplots(figsize=(7.5, 6.5))

    try:
        for idx, (dx, dy) in enumerate(pairs, start=1):
            if (dx, dy) in done:
                continue

            ax.clear()
            for eco, color in ECO_COLORS.items():
                sub = df[df["ecosystem"] == eco]
                x = pd.to_numeric(sub[dx], errors="coerce")
                y = pd.to_numeric(sub[dy], errors="coerce")
                ax.scatter(x, y, s=24, c=color, alpha=0.65,
                          edgecolor="black", linewidth=0.3, label=eco)
            ax.set_xlabel(dx)
            ax.set_ylabel(dy)
            ax.set_title(f"Pair {idx}/{len(pairs)}: {dx}  vs  {dy}")
            ax.legend(loc="best")
            ax.grid(ls=":", alpha=0.4)
            fig.tight_layout()
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.1)

            prompt = f"[{idx}/{len(pairs)}] {dx} vs {dy} — synopsis ('q' to quit): "
            try:
                synopsis = input(prompt)
            except EOFError:
                print("\nNo input stream (EOF). Quitting. Progress saved.")
                break
            if synopsis.strip().lower() == "q":
                print("Quitting. Progress saved.")
                break

            append_row(out_csv, {
                "pair_index": idx, "dim_x": dx, "dim_y": dy, "synopsis": synopsis,
            }, write_header)
            write_header = False
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved.")
    finally:
        plt.close(fig)

    n_total = len(load_existing(out_csv))
    print(f"\n{n_total} / {len(pairs)} pairs annotated so far.")
    print(f"Annotations saved to {out_csv}")


if __name__ == "__main__":
    main()
