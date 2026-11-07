"""hookscore.py の現状固定テスト（特性テスト）。

リファクタリング（ig系共通化 C-005／スコア値の集約 C-007）の安全網。
スコアは実測校正由来のため、代表入力に対する現行スコアをそのまま固定する。
標準ライブラリのみ。

    python3 test_hookscore_characterization.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hookscore  # noqa: E402


class WordsAndHelpersTests(unittest.TestCase):
    def test_words_treats_thousands_separator_as_one_word(self):
        self.assertEqual(
            hookscore.words("I lost $18,000 on one missing contract."),
            ["I", "lost", "$18000", "on", "one", "missing", "contract"],
        )

    def test_words_empty(self):
        self.assertEqual(hookscore.words(""), [])

    def test_clamp_bounds(self):
        self.assertEqual(hookscore.clamp(-5), 0.0)
        self.assertEqual(hookscore.clamp(150), 100.0)
        self.assertEqual(hookscore.clamp(42), 42)

    def test_bar(self):
        self.assertEqual(hookscore.bar(0), "." * 24)
        self.assertEqual(hookscore.bar(100), "#" * 24)
        self.assertEqual(hookscore.bar(50), "#" * 12 + "." * 12)


class CheckTests(unittest.TestCase):
    def test_length_ideal_range_scores_100(self):
        score, detail = hookscore.check_length("one two three four five six seven")
        self.assertEqual(score, 100.0)
        self.assertIn("7 words", detail)

    def test_length_empty_scores_0(self):
        score, _ = hookscore.check_length("")
        self.assertEqual(score, 0.0)

    def test_length_very_long_is_penalised(self):
        score, _ = hookscore.check_length(" ".join(["word"] * 30))
        self.assertLess(score, 50.0)

    def test_specificity_no_markers(self):
        score, detail = hookscore.check_specificity("a plain vague statement here")
        self.assertEqual(score, 15.0)
        self.assertIn("0 concrete marker", detail)

    def test_specificity_money_number(self):
        score, _ = hookscore.check_specificity("I lost $18,000 on one contract")
        self.assertGreaterEqual(score, 75.0)

    def test_stakes_levels(self):
        self.assertEqual(hookscore.check_stakes("a plain calm statement")[0], 20.0)
        self.assertEqual(
            hookscore.check_stakes("Stop doing this wrong thing now")[0], 100.0
        )

    def test_frontload_empty(self):
        self.assertEqual(hookscore.check_frontload(""), (0.0, "empty"))

    def test_frontload_weak_opener_penalty(self):
        score, detail = hookscore.check_frontload(
            "So basically this plain thing happened eventually"
        )
        self.assertIn("weak opener", detail)
        self.assertLessEqual(score, 40.0)

    def test_address_variants(self):
        self.assertEqual(
            hookscore.check_address("You are doing this wrong")[0], 100.0
        )
        self.assertEqual(
            hookscore.check_address("Stop doing this wrong thing")[0], 90.0
        )
        self.assertEqual(
            hookscore.check_address("I lost my contract last week")[0], 70.0
        )
        self.assertEqual(
            hookscore.check_address("The contract was lost last week")[0], 35.0
        )


class RunTests(unittest.TestCase):
    def test_strong_hook_exact_scores(self):
        results, overall, verdict, flags = hookscore.run(
            "I lost $18,000 on one missing contract."
        )
        self.assertEqual(
            {k: v[0] for k, v in results.items()},
            {
                "LENGTH": 100.0,
                "SPECIFICITY": 75,
                "STAKES": 100.0,
                "FRONTLOAD": 100.0,
                "ADDRESS": 70.0,
            },
        )
        self.assertAlmostEqual(round(overall, 1), 81.4)
        self.assertEqual(verdict, "STRONG")
        self.assertEqual(flags, [])

    def test_greeting_hook_is_weak_and_flagged(self):
        _, overall, verdict, flags = hookscore.run(
            "Hey guys welcome to my channel today"
        )
        self.assertAlmostEqual(round(overall, 1), 9.6)
        self.assertEqual(verdict, "WEAK")
        self.assertEqual(
            flags, ["Greeting. Nobody came to the feed to be greeted."]
        )

    def test_imperative_hook_is_ok(self):
        _, overall, verdict, flags = hookscore.run("Stop doing this wrong thing now")
        self.assertAlmostEqual(round(overall, 1), 54.6)
        self.assertEqual(verdict, "OK")
        self.assertEqual(flags, [])

    def test_empty_hook(self):
        _, overall, verdict, _ = hookscore.run("")
        self.assertAlmostEqual(round(overall, 1), 8.4)
        self.assertEqual(verdict, "WEAK")

    def test_dealbreakers(self):
        _, _, _, flags = hookscore.run("Stop scrolling and watch this #hook \U0001F600")
        self.assertTrue(any("stop scrolling" in f for f in flags))
        self.assertTrue(any("Hashtag" in f for f in flags))
        self.assertTrue(any("Emoji" in f for f in flags))

    def test_check_keys_are_stable(self):
        results, _, _, _ = hookscore.run("anything at all here now")
        self.assertEqual(list(results), hookscore.CHECKS)


if __name__ == "__main__":
    unittest.main()
