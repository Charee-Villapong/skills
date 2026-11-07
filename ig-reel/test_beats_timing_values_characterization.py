"""beats.py のタイミング数値（C-086 / C-087 / C-088）の現状固定テスト。

既存 test_beats_characterization.py が固定していない範囲を補う:
- 定数 HOOK_WINDOW 3.0 / MAX_BEAT 4.0 / ABSTRACT_RUN 3 と既定 165 wpm
  （C-088: SKILL.md の "165 wpm" 記載との二重管理）
- analyse() の境界: フック窓ちょうど3.0秒は旗が立たない、抽象ランは
  ちょうど3ビートで1回だけ注記、target の許容幅 ±10% の内外
- split_beats() の分割条件（単文は長くても割れない、という現状の癖を含む）
標準ライブラリのみ。

    python3 test_beats_timing_values_characterization.py
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import beats  # noqa: E402

SCRIPT = (
    "I lost $18,000 on one contract.\n"
    "Then I fixed the process.\n"
    "Save this for later."
)


class DoubleManagedConstantsTests(unittest.TestCase):
    def test_timing_constants(self):
        self.assertEqual(beats.HOOK_WINDOW, 3.0)
        self.assertEqual(beats.MAX_BEAT, 4.0)
        self.assertEqual(beats.ABSTRACT_RUN, 3)

    def test_default_wpm_matches_skill_md(self):
        a = beats.analyse(SCRIPT)
        self.assertEqual(a["wpm"], 165)
        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("165 wpm", skill)


class DurationBoundaryTests(unittest.TestCase):
    def test_exact_duration_at_custom_wpm(self):
        # 100 wpm = 5語でちょうど3.0秒。HOOK_WINDOW ちょうどでは旗は立たない。
        a = beats.analyse("one two three four five.", wpm=100)
        self.assertEqual(a["total_seconds"], 3.0)
        self.assertEqual(a["beats"][0]["dur"], 3.0)
        self.assertEqual(a["beats"][0]["flags"], [])

    def test_duration_scales_with_wpm(self):
        a = beats.analyse("one two three four five six seven.", wpm=200)
        self.assertAlmostEqual(a["total_seconds"], 2.1)

    def test_hook_over_window_note_suggests_word_count(self):
        long_hook = " ".join(["word"] * 12) + "."
        a = beats.analyse(long_hook + "\nShort line here.")
        note = next(n for n in a["notes"] if n.startswith("Beat 1 takes"))
        # 3.0秒 x 2.75語/秒 = 8語以下、という現在の換算。
        self.assertIn("Cut it to 8 words or fewer", note)

    def test_first_beat_without_concrete_note(self):
        a = beats.analyse(
            "Some vague opening thought here.\nI saved $5000 in March."
        )
        self.assertTrue(
            any(n.startswith("Beat 1 has no number") for n in a["notes"])
        )

    def test_long_non_first_beat_flag_and_note(self):
        a = beats.analyse("I saved $5000 today.\n" + " ".join(["word"] * 12) + ".")
        self.assertEqual(a["beats"][1]["flags"], ["4.4s on one beat"])
        self.assertTrue(any("Beat(s) 2 run past 4s" in n for n in a["notes"]))


class LabelTests(unittest.TestCase):
    def test_beats_ending_inside_hook_window_are_all_hook(self):
        a = beats.analyse(
            "Short one.\nShort two.\nShort three.\n"
            "Longer closing line with several more words in it here."
        )
        self.assertEqual(
            [r["label"] for r in a["beats"]], ["HOOK", "HOOK", "HOOK", "CTA"]
        )

    def test_no_mid_when_half_point_falls_on_boundary_gap(self):
        # 合計が短く全ビートが窓内/末尾で埋まる場合は MID が付かない。
        a = beats.analyse("Short one.\nShort two.")
        self.assertEqual([r["label"] for r in a["beats"]], ["HOOK", "HOOK/CTA"])


class AbstractRunTests(unittest.TestCase):
    VAGUE = "Some vague opening thought here."

    def notes_for(self, k):
        a = beats.analyse("\n".join([self.VAGUE] * k))
        return [n for n in a["notes"] if "nothing concrete" in n]

    def test_two_in_a_row_is_not_noted(self):
        self.assertEqual(self.notes_for(2), [])

    def test_three_in_a_row_is_noted_once_with_range(self):
        notes = self.notes_for(3)
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("Beats 1-3 have nothing concrete"))

    def test_longer_run_still_noted_once(self):
        self.assertEqual(len(self.notes_for(6)), 1)


class TargetTests(unittest.TestCase):
    def test_under_target_note_counts_words_to_add(self):
        a = beats.analyse(SCRIPT, target=30)
        note = next(n for n in a["notes"] if "under target" in n)
        self.assertIn("24.5s under target. Either add 67 words", note)

    def test_within_ten_percent_is_on_target(self):
        # 合計5.45秒。target=5 は差0.45 <= 0.5（10%）で on target。
        a = beats.analyse(SCRIPT, target=5)
        self.assertTrue(any("on target" in n for n in a["notes"]))

    def test_over_target_note(self):
        a = beats.analyse(SCRIPT, target=4)
        note = next(n for n in a["notes"] if "over target" in n)
        self.assertIn("over target. Cut about", note)


class SplitBeatsTests(unittest.TestCase):
    WPS = 165 / 60.0

    def test_single_sentence_line_is_never_split(self):
        # 現状の癖: 文が1つだけの長い行は、6秒を超えても分割されない。
        line = " ".join("w%d" % i for i in range(23)) + "."
        self.assertEqual(len(beats.split_beats(line, self.WPS)), 1)

    def test_two_sentence_line_splits_at_sentence_boundary(self):
        line = " ".join(["a"] * 10) + ". " + " ".join(["b"] * 10) + "."
        rows = beats.split_beats(line, self.WPS)
        self.assertEqual([len(beats.words(r)) for r in rows], [10, 10])

    def test_blank_lines_are_ignored(self):
        self.assertEqual(
            beats.split_beats("\n\nhi there friend\n\n", self.WPS),
            ["hi there friend"],
        )


class CliTests(unittest.TestCase):
    SCRIPT_PATH = str(HERE / "beats.py")

    def test_empty_script_exits_2(self):
        r = subprocess.run(
            [sys.executable, self.SCRIPT_PATH, "-"],
            input="", capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("empty script", r.stderr)

    def test_json_shape(self):
        r = subprocess.run(
            [sys.executable, self.SCRIPT_PATH, "-", "--json"],
            input="Short script line.\n", capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["total_words"], 3)
        self.assertEqual(payload["beats"][0]["label"], "HOOK/CTA")


if __name__ == "__main__":
    unittest.main()
