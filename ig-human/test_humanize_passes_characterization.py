"""humanize.py の各パス（C-005 / C-084 の共通部品候補）の現状固定テスト。

既存 test_detect_characterization.py 内の HumanizeTests が固定していない
範囲を補う: pass_invisible の space 化・範囲指定・残存 Cf の掃除、
pass_typographic の en ダッシュ3形態と残りの置換表、pass_lexical の
最長一致・削除エントリ・後片付け（スプライス昇格を含む）、
scan_structures / restore_capitals / CLI の入出力。
実データには触れず、一時ディレクトリと同梱 slop.json のみを使う。
標準ライブラリのみ。

    python3 test_humanize_passes_characterization.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import humanize  # noqa: E402

LEX = json.loads((HERE / "slop.json").read_text(encoding="utf-8"))


class CodepointSpecTests(unittest.TestCase):
    def test_single_and_range(self):
        self.assertEqual(humanize._cp("U+200B"), 0x200B)
        self.assertEqual(
            humanize._cp("U+E0000-U+E007F"), (0xE0000, 0xE007F)
        )


class PassInvisibleTests(unittest.TestCase):
    def test_nbsp_becomes_space_not_delete(self):
        out, hits = humanize.pass_invisible("a\u00a0b", LEX)
        self.assertEqual(out, "a b")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["action"], "space")
        self.assertIn("NO-BREAK SPACE", hits[0]["name"])

    def test_tag_range_characters_are_deleted(self):
        out, hits = humanize.pass_invisible("a\U000e0041b", LEX)
        self.assertEqual(out, "ab")
        self.assertEqual(len(hits), 1)
        self.assertIn("TAG CHARACTERS", hits[0]["name"])

    def test_stray_format_char_not_in_lexicon_is_deleted(self):
        # U+2064 は語彙に無いが Cf カテゴリなので残存掃除で消える。
        out, hits = humanize.pass_invisible("a\u2064b", LEX)
        self.assertEqual(out, "ab")
        self.assertEqual(hits[0]["name"], "other invisible format chars")

    def test_bom_is_deleted(self):
        out, hits = humanize.pass_invisible("\ufeffhello", LEX)
        self.assertEqual(out, "hello")
        self.assertEqual(len(hits), 1)


class PassTypographicTests(unittest.TestCase):
    def test_en_dash_between_digits_becomes_hyphen(self):
        out, _ = humanize.pass_typographic("5–10", LEX)
        self.assertEqual(out, "5-10")

    def test_spaced_en_dash_becomes_comma(self):
        out, _ = humanize.pass_typographic("word – word", LEX)
        self.assertEqual(out, "word, word")

    def test_bare_en_dash_becomes_hyphen(self):
        out, _ = humanize.pass_typographic("a–b", LEX)
        self.assertEqual(out, "a-b")

    def test_remaining_table_entries(self):
        out, hits = humanize.pass_typographic("it’s ‘fine’ • item … end", LEX)
        self.assertEqual(out, "it's 'fine' - item ... end")
        self.assertEqual(len(hits), 4)

    def test_prime_middle_dot_arrow(self):
        out, _ = humanize.pass_typographic("a′b c·d e→f", LEX)
        self.assertEqual(out, "a'b c-d e->f")


class PassLexicalTests(unittest.TestCase):
    def test_longest_phrase_wins_over_word(self):
        out, hits = humanize.pass_lexical(
            "We delve into the data and Delve deeper still.", LEX
        )
        self.assertEqual(out, "We look at the data and Look deeper still.")
        self.assertEqual([h["find"] for h in hits], ["delve into", "delve"])

    def test_case_preserved_for_all_caps_forms(self):
        out, hits = humanize.pass_lexical(
            "This robust tool is Robust and ROBUST.", LEX
        )
        self.assertEqual(out, "This solid tool is Solid and SOLID.")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["count"], 3)

    def test_deletion_entry_removes_word_and_cleans_up(self):
        out, hits = humanize.pass_lexical(
            "This is notably good and notably fast.", LEX
        )
        self.assertEqual(out, "This is good and fast.")
        self.assertEqual(hits[0]["replace"], "(deleted)")
        self.assertEqual(hits[0]["count"], 2)

    def test_deletion_at_sentence_start_leaves_lowercase(self):
        # 大文字化の復旧は humanize() 側の restore_capitals の仕事で、
        # pass_lexical 単体では文頭が小文字のまま残る（現状の分担を固定）。
        out, _ = humanize.pass_lexical("Notably, the plan worked well today.", LEX)
        self.assertEqual(out, "the plan worked well today.")

    def test_cleanup_runs_even_without_hits(self):
        out, hits = humanize.pass_lexical("Hello  world.\n\n\n\nNext line.", LEX)
        self.assertEqual(out, "Hello world.\n\nNext line.")
        self.assertEqual(hits, [])

    def test_comma_splice_is_promoted_to_full_stop(self):
        out, _ = humanize.pass_lexical("It is important, also, it is proof.", LEX)
        self.assertEqual(out, "It is important. Also, it is proof.")


class ScanStructuresTests(unittest.TestCase):
    def test_triad_and_uniform_length_flagged(self):
        flags = humanize.scan_structures(
            "One, two, and three.\n"
            "Short one here now please. Another short one here please. "
            "Yet another short one here.",
            LEX,
        )
        names = [f["name"] for f in flags]
        self.assertTrue(any("Rule-of-three triad" in n for n in names))
        uniform = next(f for f in flags if f["name"].startswith("Uniform"))
        self.assertEqual(uniform["count"], 4)

    def test_clean_text_has_no_flags(self):
        self.assertEqual(
            humanize.scan_structures(
                "Completely ordinary sentence about my shop in March.", LEX
            ),
            [],
        )


class RestoreCapitalsTests(unittest.TestCase):
    def test_majority_capitalised_original_fixes_lowercase(self):
        self.assertEqual(
            humanize.restore_capitals(
                "Hello world. This is fine.", "hello world. this is fine."
            ),
            "Hello world. This is fine.",
        )

    def test_lowercase_voice_is_left_alone(self):
        text = "hello world. this is fine."
        self.assertEqual(humanize.restore_capitals(text, text), text)

    def test_no_sentence_starts_leaves_text(self):
        self.assertEqual(
            humanize.restore_capitals("123 456", "abc def"), "abc def"
        )


class HumanizeEndToEndTests(unittest.TestCase):
    def test_url_is_never_rewritten(self):
        out, report = humanize.humanize(
            "Check https://example.com/delve—now for details\u200b "
            "— we delve into it…",
            LEX,
        )
        self.assertEqual(
            out,
            "Check https://example.com/delve—now for details, "
            "we look at it...\n",
        )
        self.assertEqual(len(report["invisible"]), 1)
        self.assertEqual(len(report["typographic"]), 2)
        self.assertEqual(len(report["lexical"]), 1)

    def test_empty_input_becomes_single_newline(self):
        out, _ = humanize.humanize("", LEX)
        self.assertEqual(out, "\n")
        out2, _ = humanize.humanize("   ", LEX)
        self.assertEqual(out2, "\n")


class CliTests(unittest.TestCase):
    SCRIPT = str(HERE / "humanize.py")

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "raw.txt"
            src.write_text("Hello world — delve into it…\n", encoding="utf-8")
            r = subprocess.run(
                [sys.executable, self.SCRIPT, str(src), "--json"],
                capture_output=True, text=True,
            )
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["text"], "Hello world, look at it...\n")
        self.assertEqual(
            [h["find"] for h in payload["report"]["lexical"]], ["delve into"]
        )

    def test_out_file_writes_cleaned_text(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "raw.txt"
            dst = Path(td) / "clean.txt"
            src.write_text("Plain draft here.\n", encoding="utf-8")
            r = subprocess.run(
                [sys.executable, self.SCRIPT, str(src), "-o", str(dst)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0)
            self.assertEqual(dst.read_text(encoding="utf-8"), "Plain draft here.\n")


if __name__ == "__main__":
    unittest.main()
