"""未検証だった本体モジュール群の現状固定テスト（特性テスト）。

候補 C-091／C-009 の対象のうち、形態素解析（sudachipy）なしで決定的に
動く公開関数の入出力を固定する。sudachi 必須の経路（lint の形態素系
検出器、terms.build_term_inventory、semantic、calibrate 等）は対象外で、
それらは所見として報告側に残す。
リファクタリング（lint.py 分割 C-002 等）の安全網。標準ライブラリのみ。

    python3 dev/test_uncovered_characterization.py
    # 既存テストと同じく skills/natural-japanese/scripts を正とする。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))

import lint  # noqa: E402
import newfacts  # noqa: E402
import outline  # noqa: E402
import paragraphs  # noqa: E402
import terms  # noqa: E402
import textcore  # noqa: E402


class ParagraphsSplitUnitsTests(unittest.TestCase):
    TEXT = (
        "# 見出しです\n"
        "\n"
        "本文の段落です。続きです。\n"
        "\n"
        "- 項目1です\n"
        "- 項目2です\n"
        "\n"
        "| 列1 | 列2 |\n"
        "|---|---|\n"
        "| a | b |\n"
        "\n"
        "```\n"
        "コード日本語\n"
        "```\n"
    )

    def test_kinds_lines_and_numbering(self):
        units = paragraphs.split_units(self.TEXT)
        self.assertEqual(
            [(u["no"], u["line"], u["kind"]) for u in units],
            [
                (1, 1, "見出し"),
                (2, 3, "段落"),
                (3, 5, "箇条書き"),
                (4, 6, "箇条書き"),
                (5, 8, "表"),
            ],
        )
        self.assertEqual(units[1]["text"], "本文の段落です。続きです。")

    def test_empty_and_non_japanese_yield_nothing(self):
        self.assertEqual(paragraphs.split_units(""), [])
        self.assertEqual(paragraphs.split_units("English only text."), [])

    def test_render_header(self):
        units = paragraphs.split_units("# 見出しです\n")
        rendered = paragraphs.render(units, "test.md")
        self.assertTrue(rendered.startswith("# test.md の段落ごとの確認"))
        self.assertIn("## 1(1行目、見出し)", rendered)


class TextcorePureTests(unittest.TestCase):
    def test_mask_html_comments_same_length(self):
        src = "前<!-- コメント\n複数行 -->後"
        masked = textcore.mask_html_comments(src)
        self.assertEqual(len(masked), len(src))
        self.assertEqual(masked.count("\n"), 1)
        self.assertTrue(masked.startswith("前"))
        self.assertTrue(masked.endswith("後"))
        self.assertNotIn("コメント", masked)

    def test_iter_lines_and_find_line_no(self):
        lines = textcore.iter_lines_with_no("a\n\nb")
        self.assertEqual(lines, [(1, "a"), (2, ""), (3, "b")])
        self.assertEqual(textcore.find_line_no([(1, "foo"), (2, "bar foo")], "bar"), 2)

    def test_split_sentences_with_lines(self):
        got = textcore.split_sentences_with_lines(
            [(1, "本文です。次の文です。")], {1: "本文です。次の文です。"}
        )
        self.assertEqual(got, [(1, "本文です", "本文です"), (1, "次の文です", "次の文です")])

    def test_heading_level_and_text(self):
        self.assertEqual(textcore._heading_level_and_text("### タイトル"), (3, "タイトル"))

    def test_finding_to_dict_normalizes_related_lines(self):
        f = textcore.Finding(
            line=3, category="x", excerpt="e", severity="warn",
            related_lines=[5, 3, 5],
        )
        self.assertEqual(f.related_lines, [3, 5])
        d = f.to_dict()
        # status が無い通常実行ではキーを省く（現行仕様）。
        self.assertNotIn("status", d)
        self.assertNotIn("hint", d)
        self.assertEqual(d["related_lines"], [3, 5])

    def test_strip_trailing_symbols_with_fake_morphemes(self):
        class M:
            def __init__(self, pos):
                self._pos = pos

            def part_of_speech(self):
                return (self._pos,)

        ms = [M("名詞"), M("補助記号"), M("空白")]
        self.assertEqual(textcore.strip_trailing_symbols(ms), ms[:1])
        self.assertEqual(textcore.strip_trailing_symbols([]), [])


class NewfactsPureTests(unittest.TestCase):
    def test_norm_folds_width_and_case(self):
        self.assertEqual(newfacts.norm("ＡＢＣ　１２３"), "abc 123")

    def test_bare_number(self):
        self.assertEqual(newfacts.bare_number("12.5件"), "12.5")
        self.assertEqual(newfacts.bare_number("abc"), "")

    def test_locate_is_norm_insensitive(self):
        got = newfacts.locate("一行目\nTarget 語です\n三行目", "target")
        self.assertEqual(got, [(2, "Target 語です")])
        self.assertEqual(newfacts.locate("一行目", "target"), [])


class TermsPureTests(unittest.TestCase):
    def test_is_katakana_token(self):
        self.assertTrue(terms._is_katakana_token("テスト"))
        self.assertFalse(terms._is_katakana_token("テストa"))
        self.assertFalse(terms._is_katakana_token("漢字"))
        self.assertFalse(terms._is_katakana_token(""))

    def test_gloss_hint_context(self):
        context, hint = terms._term_context_and_gloss_hint(
            "API", 1, "APIとは仕組みです", {1: 0}
        )
        self.assertEqual(context, "APIとは仕組みです")
        self.assertTrue(hint)


class OutlineTests(unittest.TestCase):
    def test_build_outline_kinds(self):
        got = outline.build_outline("# 見出し\n\n本文です。次の文です。\n\n- 項目A\n- 項目B\n")
        self.assertEqual(
            got,
            [
                {"line": 1, "kind": "heading", "level": 1, "text": "見出し"},
                {"line": 3, "kind": "lead", "level": None, "text": "本文です。"},
                {"line": 5, "kind": "bullets", "level": None, "text": "(箇条書き 2 項目)"},
            ],
        )

    def test_build_outline_empty(self):
        self.assertEqual(outline.build_outline(""), [])


class LintPureDetectorTests(unittest.TestCase):
    """sudachi を使わない表層検出器だけを固定する（検出器単位の安全網）。"""

    def test_forbidden_phrase_matches_each_occurrence(self):
        lines = [(1, "ポイントは二つある。もう一つのポイントは速さだ。")]
        found = lint.detect_forbidden_phrases(lines)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(f.category == "forbidden_phrase" for f in found))
        self.assertTrue(all(f.line == 1 for f in found))

    def test_forbidden_phrase_part_of_longer_word_not_matched(self):
        lines = [(1, "クラスターエンドポイントは更新も参照もできる。")]
        self.assertEqual(lint.detect_forbidden_phrases(lines), [])

    def test_translationese_patterns(self):
        hit = lint.detect_translationese([(1, "それは成功と言えるだろう。")])
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0].category, "translationese")
        self.assertEqual(hit[0].severity, "info")
        self.assertEqual(
            lint.detect_translationese([(1, "普通の文です。")]), []
        )

    def test_low_sentence_length_variance(self):
        uniform = [(1, "あ" * 10, "あ" * 10)] * 6
        found = lint.detect_low_sentence_length_variance(uniform)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "low_sentence_variance")
        self.assertIn("変動係数=0.000", found[0].excerpt)
        varied = [
            (1, "あ" * n, "あ" * n) for n in (5, 50, 8, 40, 12, 30)
        ]
        self.assertEqual(lint.detect_low_sentence_length_variance(varied), [])
        # 最低文数未満では判定しない。
        self.assertEqual(lint.detect_low_sentence_length_variance(uniform[:3]), [])

    def test_sentence_in_paren(self):
        found = lint.detect_sentence_in_paren(
            "本文です（これは補足の文です。読み飛ばされます）。\n次の文です。"
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "sentence_in_paren")
        self.assertEqual(found[0].line, 1)
        self.assertEqual(lint.detect_sentence_in_paren("本文です（補足）。"), [])

    def test_antithesis_below_threshold_is_quiet(self):
        lines = [(1, "速さではなく正確さが大事だ。")]
        self.assertEqual(lint.detect_antithesis_repetition(lines), [])


if __name__ == "__main__":
    unittest.main()
