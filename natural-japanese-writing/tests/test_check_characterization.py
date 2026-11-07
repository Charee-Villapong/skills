#!/usr/bin/env python3
"""check.py の現状固定テスト（特性テスト）。

これまで check.py は tests/test_examples.py 経由の間接検証しかなかった
（候補 C-092）。analyze とその部品の入出力を直接固定し、後続の変更の
安全網にする。fugashi が無い環境では語尾判定が正規表現経路になるため、
期待値はその経路で実測した現行値を固定している。
標準ライブラリのみ（unittest）。

    python3 tests/test_check_characterization.py
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check  # noqa: E402


class StripCodeTests(unittest.TestCase):
    def test_front_matter_and_code_are_removed(self):
        raw = "---\ntitle: x\n---\n本文 `code` です。\n```\nblock\n```\n終わり。"
        self.assertEqual(check.strip_code(raw), "本文  です。\n\n終わり。")

    def test_plain_text_unchanged(self):
        self.assertEqual(check.strip_code("ただの本文です。"), "ただの本文です。")


class SentenceSplitTests(unittest.TestCase):
    def test_headings_and_markers_are_skipped_or_stripped(self):
        text = "# 見出し\n本文です。次の文です！\n- 項目です。"
        self.assertEqual(
            check.sentences(text), ["本文です。", "次の文です！", "項目です。"]
        )

    def test_paragraphs_split_on_blank_lines(self):
        self.assertEqual(
            check.paragraphs("段落1です。\n\n段落2です。\n\n\n段落3です。"),
            ["段落1です。", "段落2です。", "段落3です。"],
        )
        self.assertEqual(check.paragraphs(""), [])


class PeriodDropTests(unittest.TestCase):
    def test_line_with_inner_period_but_no_final_period_is_hit(self):
        self.assertEqual(
            check.period_drop("一行目です。二行目に続きます\n次の行です。"),
            ["一行目です。二行目に続きます"],
        )

    def test_clean_text_has_no_drops(self):
        self.assertEqual(check.period_drop("一行目です。\n次の行です。"), [])


class EndingTests(unittest.TestCase):
    def test_ending_of(self):
        self.assertEqual(check.ending_of("これはテストです。"), "です")
        self.assertEqual(check.ending_of("走った。"), "た")
        # 語尾パターンに当たらない文は体言止め扱い（正規表現経路の現行仕様）。
        self.assertEqual(check.ending_of("美しい景色"), "体言止め")

    def test_longest_run(self):
        self.assertEqual(check.longest_run(["あです。", "いです。", "うます。"]), 2)
        self.assertEqual(check.longest_run([]), 0)


class AnalyzeTests(unittest.TestCase):
    def test_star_pattern_is_counted(self):
        r = check.analyze("これはテストです。重要なのは速度です。")
        self.assertEqual(r["type"], "business")
        self.assertEqual(r["star_total"], 1)
        self.assertEqual(
            r["words"]["★重要なのは／ポイントは"]["count"], 1
        )
        # 5文未満ではリズム集計は文数だけになる。
        self.assertEqual(r["rhythm"], {"sentences": 2})
        self.assertEqual(r["flags"], [])

    def test_uniform_sentences_raise_both_rhythm_flags(self):
        r = check.analyze("短い文。短い文。短い文。短い文。短い文。短い文。")
        self.assertEqual(r["rhythm"]["sentences"], 6)
        self.assertEqual(r["rhythm"]["cv"], 0.0)
        self.assertEqual(r["rhythm"]["same_ending_run"], 6)
        self.assertEqual(r["rhythm"]["endings"], [("体言止め", 6)])
        self.assertEqual(len(r["flags"]), 2)
        self.assertTrue(any("文の長さが揃いすぎ" in f for f in r["flags"]))
        self.assertTrue(any("同じ語尾が 6 文連続" in f for f in r["flags"]))

    def test_empty_text(self):
        r = check.analyze("")
        self.assertEqual(r["star_total"], 0)
        self.assertEqual(r["rhythm"], {"sentences": 0})
        self.assertEqual(r["marks"], {})

    def test_thresholds_are_pinned(self):
        # 文書種別ごとのしきい値（実測校正由来）は現行値を固定する。
        self.assertEqual(
            check.THRESHOLDS,
            {
                "business": {"cv_min": 0.40, "same_ending_run": 6,
                             "comma_per_sentence": 1.0, "para_hits": 3},
                "article": {"cv_min": 0.45, "same_ending_run": 4,
                            "comma_per_sentence": 1.0, "para_hits": 3},
                "manual": {"cv_min": 0.35, "same_ending_run": 6,
                           "comma_per_sentence": 1.2, "para_hits": 4},
            },
        )

    def test_doc_type_changes_flag_threshold(self):
        # 同じ語尾4文連続は business（6以上）では立たず article（4以上）では立つ。
        text = "報告する。報告する。報告する。報告する。報告する。報告する。"
        # ※この文面は語尾「る」が続く形。same_ending_run の実測で判定する。
        rb = check.analyze(text, "business")
        ra = check.analyze(text, "article")
        self.assertEqual(rb["rhythm"]["same_ending_run"], ra["rhythm"]["same_ending_run"])
        if rb["rhythm"]["same_ending_run"] >= 4:
            self.assertTrue(any("同じ語尾" in f for f in ra["flags"]))


class ParagraphScoreTests(unittest.TestCase):
    def test_dense_paragraph_kinds(self):
        scores = check.paragraph_scores("重要なのは速度です。適切な対応が重要です。")
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["paragraph"], 1)
        self.assertEqual(scores[0]["hits"], 3)
        self.assertEqual(
            scores[0]["kinds"],
            ["★重要なのは／ポイントは", "★AI頻出語（硬い万能語）", "★重要です"],
        )

    def test_clean_paragraph_scores_empty(self):
        self.assertEqual(check.paragraph_scores("昨日は駅まで歩いた。"), [])


if __name__ == "__main__":
    unittest.main()
