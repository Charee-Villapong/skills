"""detect.py のスコア換算値（C-006 / C-007）の現状固定テスト。

既存 test_detect_characterization.py が固定していない範囲を補う:
- scale() の換算アンカー（human->100 / machine->0 / 中点->50）
- BURSTINESS / SPECIFICITY / FINGERPRINT / VOICE の境界と重み
  （VOICE の 0.35 / 0.35 / 0.30、構造テル1件 -22 相当、均一箇条書き -12）
- 総合の重み（平均 x 0.6 + 最低 x 0.4）と PASS 判定
  （総合70以上 かつ 最低55以上）の両条件。SKILL.md 記載との二重管理も固定。
標準ライブラリのみ。同梱 slop.json の実ファイルを使う。

    python3 test_detect_scoring_values_characterization.py
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import detect  # noqa: E402

LEX = json.loads((HERE / "slop.json").read_text(encoding="utf-8"))

PASS_TEXT = (
    "It hurt bad. "
    "I saved $5000 last month at my little bakery on Fifth Street in March "
    "with Ana helping me count every receipt by hand. "
    "Twice I nearly quit. "
    "You don't need a big team or a fancy tool, and I can show you my "
    "notebook if you want proof of every single sale we made that month."
)

# 総合は70を超えるが BURSTINESS が50（文3つで判定不能）で最低55未満。
MIN_BLOCKED_TEXT = (
    "I saved $5000 last month at my bakery on Fifth Street in March! "
    "It hurt. Honestly I nearly gave up twice, and I don't mind saying so "
    "here today. Here is exactly how I did it, step by step, with real "
    "receipts, real numbers, and a notebook I kept by the till every "
    "morning before we opened the doors for customers."
)


class ScaleAnchorTests(unittest.TestCase):
    def test_anchors(self):
        self.assertEqual(detect.scale(0.70, human=0.70, machine=0.22), 100.0)
        self.assertEqual(detect.scale(0.22, human=0.70, machine=0.22), 0.0)
        self.assertAlmostEqual(detect.scale(0.46, human=0.70, machine=0.22), 50.0)
        self.assertEqual(detect.scale(6.0, human=6.0, machine=0.5), 100.0)
        self.assertEqual(detect.scale(0.5, human=6.0, machine=0.5), 0.0)


class BurstinessTests(unittest.TestCase):
    def test_even_sentences_score_0(self):
        text = " ".join(["One two three four five six seven."] * 5)
        score, detail = detect.check_burstiness(text)
        self.assertEqual(score, 0.0)
        self.assertIn("variation 0.00 across 5 sentences", detail)

    def test_varied_sentences_score(self):
        text = (
            "One two three four five. Short one here now. "
            "This sentence is quite a bit longer than the others in this "
            "little sample text indeed. Tiny bit here. "
            "Another medium length sentence follows right after this one "
            "for good measure."
        )
        score, _ = detect.check_burstiness(text)
        self.assertAlmostEqual(score, 86.95, places=1)

    def test_three_sentences_is_too_short_to_judge(self):
        self.assertEqual(
            detect.check_burstiness(
                "One two three four. Five six seven eight. Nine ten eleven twelve."
            ),
            (50.0, "too short to judge"),
        )


class SpecificityBoundaryTests(unittest.TestCase):
    def test_exactly_25_words_is_judged(self):
        # 単語数カウントは英字のみ（数字自体は単語に数えない）ため、
        # 25語 + 数字1件で密度 4.0/100語 -> scale(4.0, 6.0, 0.5) = 63.6。
        text = " ".join(["word"] * 25) + " 5000"
        score, detail = detect.check_specificity(text)
        self.assertAlmostEqual(score, 63.64, places=1)
        self.assertIn("1 concrete markers, 4.0 per 100 words", detail)

    def test_no_markers_scores_0(self):
        score, _ = detect.check_specificity(" ".join(["word"] * 26))
        self.assertEqual(score, 0.0)

    def test_repeated_proper_name_counts_once(self):
        text = "word " * 30 + "John met John in March"
        score, detail = detect.check_specificity(text)
        self.assertAlmostEqual(round(score, 1), 94.8)
        self.assertIn("2 concrete markers", detail)


class FingerprintWeightTests(unittest.TestCase):
    """FINGERPRINT の重み: 不可視 x4 / emダッシュ x2 / 他 x1、1000字あたり
    12 で 0 点になる換算を、長い文での実スコアで固定する。"""

    def test_em_dash_weight_in_long_text(self):
        score, _ = detect.check_fingerprint("x" * 1000 + "—")
        self.assertAlmostEqual(round(score, 1), 83.3)

    def test_invisible_char_weight_in_long_text(self):
        score, _ = detect.check_fingerprint("x" * 1000 + "\u200b")
        self.assertAlmostEqual(round(score, 1), 66.7)

    def test_curly_quote_weight_in_long_text(self):
        score, _ = detect.check_fingerprint("x" * 1000 + "’")
        self.assertAlmostEqual(round(score, 1), 91.7)

    def test_combined_detail_counts(self):
        _, detail = detect.check_fingerprint("x" * 100 + "—" + "’’" + "…")
        self.assertIn("1 em dash, 2 curly quote, 1 ellipsis", detail)


class SlopLexiconFormTests(unittest.TestCase):
    def test_hyphenated_form_hits_space_form_does_not(self):
        # 現状の語彙は "game-changer"（ハイフン形）のみで、
        # スペース形 "game changer" はヒットしない（語彙側の癖を固定）。
        score, detail = detect.check_slop("A game-changer and a deep dive.", LEX)
        self.assertEqual(score, 0.0)
        self.assertIn("2 stock terms", detail)
        score2, _ = detect.check_slop("A game changer indeed for us.", LEX)
        self.assertEqual(score2, 100.0)

    def test_words_only_text_still_counts_as_nonempty(self):
        self.assertEqual(detect.check_slop("123 456", LEX), (50.0, "empty"))


class VoiceWeightTests(unittest.TestCase):
    BASE = "I saved money at my shop and I don't regret it at all. " * 3

    def test_no_contractions_no_pronouns_leaves_only_tell_term(self):
        text = (
            "The committee reviewed the quarterly figures and the regional "
            "managers approved the proposed budget without any further "
            "discussion or amendments whatsoever today. "
        ) * 2
        score, detail = detect.check_voice(text, LEX)
        # 0.35 x 0 + 0.35 x 0 + 0.30 x 100 = 30。
        self.assertEqual(score, 30.0)
        self.assertIn("0.0 contractions, 0.0 personal pronouns", detail)

    def test_structural_tell_is_named_and_costs(self):
        text = (
            "We should not only save money but also spend time wisely with "
            "family and friends every single week of the year. "
            + self.BASE
        )
        score, detail = detect.check_voice(text, LEX)
        self.assertAlmostEqual(round(score, 1), 93.4)
        self.assertIn("1 structural tell(s) [not-only]", detail)

    def test_uniform_bullets_cost_12(self):
        plain_score, _ = detect.check_voice(self.BASE, LEX)
        self.assertEqual(plain_score, 100.0)
        text = self.BASE + (
            "\n- one two three four\n- five six seven eight"
            "\n- nine ten eleven twelve"
        )
        score, detail = detect.check_voice(text, LEX)
        self.assertEqual(score, 88.0)
        self.assertIn("[uniform-bullets]", detail)


class VerdictGateTests(unittest.TestCase):
    def test_pass_text_exact(self):
        results, overall, verdict = detect.run(PASS_TEXT, LEX)
        self.assertEqual(
            {k: round(v[0], 1) for k, v in results.items()},
            {
                "BURSTINESS": 100.0,
                "SPECIFICITY": 100.0,
                "SLOP DENSITY": 100.0,
                "FINGERPRINT": 100.0,
                "VOICE": 85.1,
            },
        )
        self.assertAlmostEqual(round(overall, 1), 92.3)
        self.assertEqual(verdict, "PASS")

    def test_overall_over_70_but_min_under_55_is_review(self):
        results, overall, verdict = detect.run(MIN_BLOCKED_TEXT, LEX)
        self.assertGreaterEqual(overall, 70)
        self.assertEqual(results["BURSTINESS"][0], 50.0)
        self.assertEqual(verdict, "REVIEW")

    def test_verdict_weights_match_skill_md(self):
        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("weights the mean at 60%", skill)
        self.assertIn("weakest single check** at 40%", skill)
        self.assertIn("PASS needs an overall of 70+", skill)
        self.assertIn("below 55", skill)


if __name__ == "__main__":
    unittest.main()
