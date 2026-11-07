"""swipe.py の現状固定テスト（特性テスト）。

リファクタリング（ig系共通化 C-005／C-084）の安全網。分類は同梱ではなく
ig-reel/hooks.json の実データに依存する現行形態のまま固定する。
analyse は ig-reel/hookscore を import できる配置でのみスコアが付く点も含む。
標準ライブラリのみ。

    python3 test_swipe_characterization.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import swipe  # noqa: E402

HOOKS_JSON = HERE / ".." / "ig-reel" / "hooks.json"


class LoadAndClassifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulas = swipe.load_formulas(str(HOOKS_JSON))

    def test_load_formulas_from_real_hooks_json(self):
        self.assertIsNotNone(self.formulas)
        self.assertEqual(len(self.formulas), 26)
        fid, name, _ = self.formulas[0]
        self.assertEqual((fid, name), (1, "Cost Confession"))

    def test_load_formulas_missing_file_returns_none(self):
        self.assertIsNone(swipe.load_formulas("/nonexistent/hooks.json"))

    def test_classify_hit_and_miss(self):
        self.assertEqual(
            swipe.classify("POV: you finally quit your job", self.formulas),
            (2, "Negative Command"),
        )
        self.assertEqual(
            swipe.classify("zzzz qqq", self.formulas), (None, "unclassified")
        )

    def test_classify_without_formulas(self):
        self.assertEqual(swipe.classify("x", None), (None, "unclassified"))
        self.assertEqual(swipe.classify("x", []), (None, "unclassified"))


class ReadRowsTests(unittest.TestCase):
    def _write(self, content):
        fh = tempfile.NamedTemporaryFile(
            "w", suffix=".tsv", delete=False, encoding="utf-8"
        )
        fh.write(content)
        fh.close()
        return fh.name

    def test_headerless_rows_use_default_columns(self):
        path = self._write(
            "acc\t1000\t5000\tHow I made $10k in 30 days\n"
            "acc2\t2000\t100\tPlain day in my life\n"
        )
        rows = swipe.read_rows(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0],
            {
                "account": "acc",
                "followers": 1000,
                "views": 5000,
                "hook": "How I made $10k in 30 days",
                "median": None,
            },
        )

    def test_header_rows(self):
        path = self._write(
            "account\tfollowers\tviews\thook\n"
            "acc\t1000\t5000\tHow I made $10k in 30 days\n"
        )
        rows = swipe.read_rows(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], 5000)

    def test_zero_view_rows_are_dropped(self):
        path = self._write("acc\t1000\t0\tSome hook text here\n")
        self.assertEqual(swipe.read_rows(path), [])


class AnalyseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulas = swipe.load_formulas(str(HOOKS_JSON))

    def test_analyse_empty(self):
        a = swipe.analyse([], self.formulas)
        self.assertEqual(a["n"], 0)
        self.assertEqual(a["baseline"], "follower count")
        self.assertEqual(a["reels"], [])
        self.assertIsNone(a["top_hook_score"])

    def test_analyse_outlier_ranking_and_scores(self):
        rows = [
            {"account": "acc", "followers": 1000, "views": 5000,
             "hook": "How I made $10k in 30 days", "median": None},
            {"account": "acc2", "followers": 2000, "views": 100,
             "hook": "Plain day in my life", "median": None},
            {"account": "acc3", "followers": 500, "views": 9000,
             "hook": "How I made $10k in 30 days", "median": None},
        ]
        a = swipe.analyse([dict(r) for r in rows], self.formulas)
        self.assertEqual(a["n"], 3)
        self.assertEqual(a["accounts"], 3)
        # outlier（views / followers）の降順。
        self.assertEqual([r["account"] for r in a["reels"]], ["acc3", "acc", "acc2"])
        self.assertEqual(a["reels"][0]["outlier"], 18.0)
        self.assertEqual(a["unclassified"], 3)
        # hookscore が import できる配置ではスコアが付く（現行の結合を固定）。
        self.assertEqual(a["top_hook_score"], 80.8)
        self.assertEqual(a["bottom_hook_score"], 34.2)


if __name__ == "__main__":
    unittest.main()
