"""
Tests for the study's core statistics and text handling, using hand-worked answers.

Basically checking that what our code depends upon (the rules, et cetera) DO indeed work

- Cliffs Delta
- Holm Correction
- Locked Settings (decision rule, order + cap)
- Text handling

Note: There are NO tests for the full pipeline (needs LIWC)

Run from the repo root:
    venv/bin/python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path[:0] = [str(p) for p in SRC.iterdir() if p.is_dir()]

from confirmatory_liwc_stats import (  # noqa: E402
    ALPHA, DELTA_THRESHOLD, LOCKED_DIMENSIONS, cliffs_delta, holm_bonferroni,
)
from confirmatory_preprocessor import (  # noqa: E402
    WORD_MIN, apply_word_cap, extract_prose, find_prose_files,
)


class CliffsDelta(unittest.TestCase):
    def test_worked_example(self):
        # 6 wins and 3 losses out of 9 pairs.
        self.assertAlmostEqual(cliffs_delta(np.array([3, 5, 7]), np.array([2, 4, 6])), 1 / 3)

    def test_complete_separation(self):
        self.assertEqual(cliffs_delta(np.array([4, 5]), np.array([1, 2])), 1)
        self.assertEqual(cliffs_delta(np.array([1, 2]), np.array([4, 5])), -1)

    def test_identical_groups_are_zero(self):
        self.assertEqual(cliffs_delta(np.array([1, 2, 3]), np.array([1, 2, 3])), 0)

    def test_ties_count_as_neither(self):
        # 1 win, 1 tie, 1 tie, 1 loss.
        self.assertEqual(cliffs_delta(np.array([0, 1]), np.array([0, 1])), 0)
        self.assertEqual(cliffs_delta(np.array([0, 0, 1]), np.array([0])), 1 / 3)

    def test_swapping_groups_flips_sign(self):
        a, b = np.array([1, 4, 9]), np.array([2, 3, 8])
        self.assertAlmostEqual(cliffs_delta(a, b), -cliffs_delta(b, a))


class HolmBonferroni(unittest.TestCase):
    def test_worked_example(self):
        # Sorted p × (m - rank): 0.01×3, 0.02×2, 0.03×1, kept non-decreasing.
        np.testing.assert_allclose(holm_bonferroni([0.01, 0.02, 0.03]), [0.03, 0.04, 0.04])

    def test_keeps_input_order(self):
        np.testing.assert_allclose(holm_bonferroni([0.03, 0.01, 0.02]), [0.04, 0.03, 0.04])

    def test_capped_at_one(self):
        np.testing.assert_allclose(holm_bonferroni([0.9, 0.8]), [1.0, 1.0])


class LockedSettings(unittest.TestCase):
    def test_decision_rule(self):
        self.assertEqual((ALPHA, DELTA_THRESHOLD), (0.05, 0.33))

    def test_fifteen_unique_categories(self):
        self.assertEqual(len(LOCKED_DIMENSIONS), 15)
        self.assertEqual(len(set(LOCKED_DIMENSIONS)), 15)

    def test_word_minimum(self):
        self.assertEqual(WORD_MIN, 500)


class TextHandling(unittest.TestCase):
    def test_word_cap_keeps_first_words(self):
        text, n, capped = apply_word_cap("a b c d", cap=2)
        self.assertEqual((text, n, capped), ("a b", 2, True))

    def test_word_cap_leaves_short_text(self):
        self.assertEqual(apply_word_cap("a b", cap=5), ("a b", 2, False))

    def test_code_blocks_are_removed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "README.md"
            p.write_text("Some real prose.\n\n```python\nimport secret_code\n```\n", encoding="utf-8")
            out = extract_prose(p)
        self.assertIn("real prose", out)
        self.assertNotIn("secret_code", out)

    def test_only_readmes_and_docs_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            for name in ("README.md", "docs/guide.md", "CHANGELOG.md", "main.py"):
                (root / name).write_text("x", encoding="utf-8")
            kept = {p.relative_to(root).as_posix() for p in find_prose_files(root)}
        self.assertEqual(kept, {"README.md", "docs/guide.md"})


if __name__ == "__main__":
    unittest.main()
