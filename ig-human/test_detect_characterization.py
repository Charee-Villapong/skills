"""ig-human（detect.py / humanize.py）の現状固定テスト（特性テスト）。

リファクタリング（ig系共通化 C-005／C-084、数値二重管理 C-088）の安全網。
detect.run は語彙ファイル slop.json を読み込んだ結果に依存するため、
リポジトリ同梱の実ファイルをそのまま使う（現行の配布形態どおり）。
標準ライブラリのみ。

    python3 test_detect_characterization.py
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import detect  # noqa: E402
import humanize  # noqa: E402

LEX = json.loads((HERE / "slop.json").read_text(encoding="utf-8"))

LONG_TEXT = (
    "I saved $5000 last month at my little bakery on Fifth Street. "
    "It was not easy at all, and honestly I nearly gave up twice in March. "
    "Here is exactly how I did it, step by step, with real receipts and numbers. "
    "You do not need a big team or a fancy tool to copy this approach today."
)


class DetectHelperTests(unittest.TestCase):
    def test_clamp_and_scale(self):
        self.assertEqual(detect.clamp(-1), 0.0)
        self.assertEqual(detect.clamp(101), 100.0)
        self.assertEqual(detect.scale(5, 10, 0), 50.0)
        # human == machine のときは中点 50 を返す（現行仕様）。
        self.assertEqual(detect.scale(5, 5, 5), 50.0)

    def test_words_and_sentences(self):
        self.assertEqual(
            detect.words("Hello, world! It's me"), ["Hello", "world", "It's", "me"]
        )
        # 3語以下の断片は文として数えない。
        self.assertEqual(
            detect.sentences("One two three. Four five six! Short."),
            ["One two three.", "Four five six!"],
        )

    def test_bar(self):
        self.assertEqual(detect.bar(62.0), "#" * 15 + "." * 9)


class DetectCheckTests(unittest.TestCase):
    def test_short_text_is_neutral_50(self):
        self.assertEqual(
            detect.check_burstiness("One two three four."),
            (50.0, "too short to judge"),
        )
        self.assertEqual(
            detect.check_specificity("I saved $5000 in March with Ana."),
            (50.0, "too short to judge"),
        )

    def test_specificity_long_text(self):
        score, detail = detect.check_specificity(LONG_TEXT)
        self.assertEqual(score, 100.0)
        self.assertIn("4 concrete markers", detail)

    def test_slop_density(self):
        score, detail = detect.check_slop(
            "This is a game changer and a deep dive into synergy.", LEX
        )
        self.assertEqual(score, 0.0)
        self.assertIn("2 stock terms", detail)
        self.assertEqual(detect.check_slop("", LEX), (50.0, "empty"))
        score2, _ = detect.check_slop(
            "I saved money at my shop in March with Ana and Tom helping.", LEX
        )
        self.assertEqual(score2, 100.0)

    def test_fingerprint(self):
        score, detail = detect.check_fingerprint("Plain text with no marks at all here.")
        self.assertEqual(score, 100.0)
        self.assertIn("0 em dash", detail)
        score2, detail2 = detect.check_fingerprint("Wait — really… “yes”")
        self.assertEqual(score2, 0.0)
        self.assertIn("1 em dash, 2 curly quote, 1 ellipsis", detail2)

    def test_voice_long_text(self):
        score, detail = detect.check_voice(LONG_TEXT, LEX)
        self.assertEqual(score, 65.0)
        self.assertIn("0 structural tell", detail)


class DetectRunTests(unittest.TestCase):
    def test_empty_text(self):
        results, overall, verdict = detect.run("", LEX)
        self.assertEqual(list(results), detect.CHECKS)
        self.assertEqual(results["SLOP DENSITY"], (50.0, "empty"))
        self.assertAlmostEqual(overall, 56.0)
        self.assertEqual(verdict, "REVIEW")

    def test_long_text_exact(self):
        results, overall, verdict = detect.run(LONG_TEXT, LEX)
        self.assertEqual(
            {k: v[0] for k, v in results.items()},
            {
                "BURSTINESS": 0.0,
                "SPECIFICITY": 100.0,
                "SLOP DENSITY": 100.0,
                "FINGERPRINT": 100.0,
                "VOICE": 65.0,
            },
        )
        self.assertAlmostEqual(round(overall, 1), 43.8)
        self.assertEqual(verdict, "FLAGGED")


class HumanizeTests(unittest.TestCase):
    def test_load_lexicon_shape(self):
        lex = humanize.load_lexicon()
        for key in ("invisible", "typographic", "words", "phrases", "structures"):
            self.assertIn(key, lex)

    def test_url_protect_restore_roundtrip(self):
        text = "See https://example.com/a and www.example.org now"
        protected, stash = humanize.protect_urls(text)
        self.assertEqual(stash, ["https://example.com/a", "www.example.org"])
        self.assertNotIn("example.com", protected)
        self.assertEqual(humanize.restore_urls(protected, stash), text)

    def test_pass_invisible_deletes_zero_width(self):
        out, hits = humanize.pass_invisible("a\u200bb", LEX)
        self.assertEqual(out, "ab")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["action"], "delete")

    def test_pass_typographic(self):
        out, hits = humanize.pass_typographic("a—b “x”", LEX)
        self.assertEqual(out, 'a, b "x"')
        self.assertEqual(len(hits), 3)

    def test_match_case(self):
        self.assertEqual(humanize._match_case("Hello", "world"), "World")
        self.assertEqual(humanize._match_case("HELLO", "world"), "WORLD")
        self.assertEqual(humanize._match_case("hello", "World"), "World")

    def test_humanize_end_to_end(self):
        out, report = humanize.humanize(
            "Hello world — this is a plain simple draft… really.", LEX
        )
        self.assertEqual(out, "Hello world, this is a plain simple draft... Really.\n")
        names = [h["name"] for h in report["typographic"]]
        self.assertTrue(any("EM DASH" in n for n in names))
        self.assertTrue(any("ELLIPSIS" in n for n in names))
        self.assertEqual(report["invisible"], [])
        self.assertEqual(report["lexical"], [])


if __name__ == "__main__":
    unittest.main()
