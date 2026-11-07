"""beats.py の現状固定テスト（特性テスト）。

リファクタリング（ig系共通化 C-005／数値集約 C-007・C-088）の安全網。
タイミング換算（165 wpm 既定）やラベル付けの現行挙動を固定する。
標準ライブラリのみ。

    python3 test_beats_characterization.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import beats  # noqa: E402


class HelperTests(unittest.TestCase):
    def test_words_thousands_separator(self):
        self.assertEqual(beats.words("$18,000 deal"), ["$18000", "deal"])

    def test_pretty_restores_separator(self):
        self.assertEqual(beats.pretty("18000"), "18,000")
        self.assertEqual(beats.pretty("500"), "500")

    def test_timecode(self):
        self.assertEqual(beats.tc(0), "0:00.0")
        self.assertEqual(beats.tc(65.3), "1:05.3")
        self.assertEqual(beats.tc(9.94), "0:09.9")


class AnalyseTests(unittest.TestCase):
    SCRIPT = (
        "I lost $18,000 on one contract.\n"
        "Then I fixed the process.\n"
        "Save this for later."
    )

    def test_empty_script_returns_none(self):
        self.assertIsNone(beats.analyse(""))
        self.assertIsNone(beats.analyse("   \n\n"))

    def test_three_beat_sheet_exact(self):
        a = beats.analyse(self.SCRIPT)
        self.assertEqual(a["wpm"], 165)
        self.assertIsNone(a["target"])
        self.assertEqual(a["total_words"], 15)
        self.assertAlmostEqual(a["total_seconds"], 5.45)
        rows = a["beats"]
        self.assertEqual([r["n"] for r in rows], [1, 2, 3])
        self.assertEqual([r["words"] for r in rows], [6, 5, 4])
        self.assertEqual([r["label"] for r in rows], ["HOOK", "MID", "CTA"])
        self.assertEqual(rows[0]["concrete"], 2)
        self.assertEqual(rows[0]["start"], 0.0)
        self.assertAlmostEqual(rows[1]["start"], 2.18)
        # ループなしの注記だけが付く。
        self.assertEqual(len(a["notes"]), 1)
        self.assertTrue(a["notes"][0].startswith("No loop."))

    def test_single_line_is_hook_cta(self):
        a = beats.analyse("Save this contract trick for later.")
        self.assertEqual(len(a["beats"]), 1)
        self.assertEqual(a["beats"][0]["label"], "HOOK/CTA")

    def test_long_hook_is_flagged(self):
        long_hook = " ".join(["word"] * 12) + "."
        a = beats.analyse(long_hook + "\nShort line here.")
        self.assertTrue(a["beats"][0]["flags"])
        self.assertTrue(any("Beat 1 takes" in n for n in a["notes"]))

    def test_abstract_run_is_noted(self):
        script = "\n".join(
            [
                "Some vague opening thought here.",
                "Another general remark follows now.",
                "More general remarks keep coming.",
                "Final vague closing remark here.",
            ]
        )
        a = beats.analyse(script)
        self.assertTrue(any("nothing concrete" in n for n in a["notes"]))

    def test_loop_is_detected(self):
        a = beats.analyse(
            "Contract mistakes cost money.\n"
            "Some middle detail goes here.\n"
            "That contract mistake again."
        )
        self.assertTrue(any(n.startswith("Loops:") for n in a["notes"]))

    def test_target_within_tolerance(self):
        a = beats.analyse(self.SCRIPT, target=5.5)
        self.assertTrue(any("on target" in n for n in a["notes"]))

    def test_target_over(self):
        a = beats.analyse(self.SCRIPT, target=3)
        self.assertTrue(any("over target" in n for n in a["notes"]))

    def test_wpm_changes_duration(self):
        slow = beats.analyse(self.SCRIPT, wpm=100)
        fast = beats.analyse(self.SCRIPT, wpm=200)
        self.assertGreater(slow["total_seconds"], fast["total_seconds"])

    def test_long_line_is_split_into_beats(self):
        line = (
            "First part has five words here. Second part also has five words. "
            "Third part again five words total. Fourth part has five words here. "
            "Fifth part also has five words."
        )
        rows = beats.split_beats(line, 165 / 60.0)
        self.assertGreater(len(rows), 1)
        # 分割しても単語の並びは失われない。
        self.assertEqual(
            [w for r in rows for w in beats.words(r)], beats.words(line)
        )


if __name__ == "__main__":
    unittest.main()
