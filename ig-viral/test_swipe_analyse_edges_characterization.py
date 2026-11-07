"""swipe.py analyse() / read_rows() の未固定範囲の現状固定テスト。

既存 test_swipe_characterization.py が固定していない範囲を補う:
- baseline の優先順位（median > followers、median=0 は followers へ）
- baseline 0 の行は outlier None で末尾に並ぶ
- read_rows() の癖（コメント行・空行の読み飛ばし、カンマ区切り数値、
  "1.2k" のような表記は数字だけ拾って 12 になる、列不足行の脱落）
- top_formulas は上位1/3だけの集計、to_markdown() の書式
- load_formulas() の classify_order 欠落時のフォールバック
標準ライブラリのみ。入力ファイルは一時ファイルに限る。

    python3 test_swipe_analyse_edges_characterization.py
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import swipe  # noqa: E402

HOOKS_JSON = HERE / ".." / "ig-reel" / "hooks.json"
FORMULAS = swipe.load_formulas(str(HOOKS_JSON))


def row(account, followers, views, hook, median=None):
    return {
        "account": account,
        "followers": followers,
        "median": median,
        "views": views,
        "hook": hook,
    }


def write_tsv(content):
    fh = tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", delete=False, encoding="utf-8"
    )
    fh.write(content)
    fh.close()
    return fh.name


class BaselinePriorityTests(unittest.TestCase):
    def test_median_beats_followers(self):
        a = swipe.analyse(
            [row("a", 100000, 5000, "How I made $10k in 30 days", median=1000)],
            FORMULAS,
        )
        self.assertEqual(a["baseline"], "account median")
        self.assertEqual(a["reels"][0]["baseline"], 1000)
        self.assertEqual(a["reels"][0]["outlier"], 5.0)

    def test_zero_median_falls_back_to_followers(self):
        a = swipe.analyse([row("a", 200, 1000, "some hook text", median=0)], FORMULAS)
        self.assertEqual(a["reels"][0]["baseline"], 200)
        self.assertEqual(a["reels"][0]["outlier"], 5.0)

    def test_zero_baseline_gives_none_outlier_and_sorts_last(self):
        a = swipe.analyse(
            [
                row("zero", 0, 5000, "x hook here"),
                row("base", 100, 500, "y hook here"),
            ],
            FORMULAS,
        )
        self.assertEqual([r["account"] for r in a["reels"]], ["base", "zero"])
        self.assertIsNone(a["reels"][1]["outlier"])


class ReadRowsEdgeTests(unittest.TestCase):
    def test_comments_blanks_and_comma_numbers(self):
        path = write_tsv(
            "# comment line\n"
            "\n"
            "account\tfollowers\tmedian\tviews\thook\n"
            "acc\t48,000\t11,000\t412,000\tnobody tells you your first 30 flop\n"
        )
        rows = swipe.read_rows(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "account": "acc",
                "followers": 48000,
                "median": 11000,
                "views": 412000,
                "hook": "nobody tells you your first 30 flop",
            },
        )

    def test_empty_hook_and_short_rows_are_dropped(self):
        path = write_tsv(
            "account\tfollowers\tmedian\tviews\thook\n"
            "acc2\t1000\t\t200\t\n"
            "short\t500\n"
        )
        self.assertEqual(swipe.read_rows(path), [])

    def test_junk_in_views_keeps_only_digits(self):
        # 現状の癖: "1.2k" は数字だけ拾われて 12 として読まれる。
        path = write_tsv("acc\t1000\t1.2k\tSome hook text\n")
        rows = swipe.read_rows(path)
        self.assertEqual(rows[0]["views"], 12)

    def test_empty_file_gives_no_rows(self):
        self.assertEqual(swipe.read_rows(write_tsv("")), [])


class TopFormulasTests(unittest.TestCase):
    def test_top_formulas_counts_only_top_third(self):
        hooks = [
            "POV: you finally quit your job",
            "POV: you finally quit your job",
            "How I made $10k in 30 days",
            "How I made $10k in 30 days",
            "Plain day in my life",
            "Plain day in my life",
        ]
        rows = [
            row("a%d" % i, 100, 1000 - i * 100, hk) for i, hk in enumerate(hooks)
        ]
        a = swipe.analyse(rows, FORMULAS)
        self.assertEqual(a["n"], 6)
        self.assertEqual(a["top_formulas"], [("Negative Command", 2)])
        self.assertEqual(a["unclassified"], 4)
        self.assertEqual(a["top_words"], 6)
        self.assertEqual(a["bottom_words"], 5)
        # フック分類と hookscore の連携（現行の結合）もここで固定する。
        self.assertEqual(a["top_hook_score"], 52.2)


class MarkdownTests(unittest.TestCase):
    def test_header_and_row_format(self):
        a = swipe.analyse(
            [row("acc", 100, 1000, "POV: you finally quit your job")], FORMULAS
        )
        md = swipe.to_markdown(a)
        lines = md.splitlines()
        self.assertEqual(lines[0], "# Swipe file")
        self.assertEqual(lines[2], "1 reels across 1 accounts. "
                                   "Ranked by multiple over follower count.")
        self.assertIn("## 10.0x  Negative Command  (acc)", lines)
        self.assertIn("- views: 1,000  baseline: 100", lines)

    def test_missing_outlier_renders_question_mark(self):
        a = swipe.analyse([row("zero", 0, 100, "some hook")], FORMULAS)
        md = swipe.to_markdown(a)
        self.assertIn("## ?  unclassified  (zero)", md.splitlines())

    def test_render_smoke(self):
        a = swipe.analyse(
            [row("acc", 100, 1000, "POV: you finally quit your job")], FORMULAS
        )
        out = io.StringIO()
        swipe.render(a, out=out)
        text = out.getvalue()
        self.assertIn("SWIPE FILE", text)
        self.assertIn("WHAT IS WORKING IN THIS BATCH", text)
        self.assertIn("top third by outlier:", text)


class LoadFormulasFallbackTests(unittest.TestCase):
    def test_malformed_json_returns_none(self):
        path = write_tsv("{not json")
        self.assertIsNone(swipe.load_formulas(path))

    def test_missing_classify_order_falls_back_to_sorted_ids(self):
        data = {
            "hooks": [
                {"id": 9, "name": "Nine", "match": "nine"},
                {"id": 3, "name": "Three", "match": "three"},
            ]
        }
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(data, fh)
            path = fh.name
        formulas = swipe.load_formulas(path)
        self.assertEqual([f[0] for f in formulas], [3, 9])

    def test_classify_uses_order_not_id_order(self):
        # 実 hooks.json の classify_order は id 順ではなく、
        # 先頭は Cost Confession(1) の次が The Statistic(23)（現状固定）。
        self.assertEqual([f[0] for f in FORMULAS[:2]], [1, 23])


if __name__ == "__main__":
    unittest.main()
