"""hookscore.py のスコア調整値（C-007 / C-087）の現状固定テスト。

既存 test_hookscore_characterization.py が代表入力の総合スコアを固定して
いるのに対し、本ファイルは各チェックの調整値そのもの（段階・減点・重み）が
効いた計算結果を境界ケースで固定する。共通化・定数化で値が動いたら落ちる。
仕様の正しさを主張するものではない。標準ライブラリのみ。

    python3 test_hookscore_scoring_values_characterization.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hookscore  # noqa: E402

FILLER = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]


def hook_with_payload_at(index):
    return " ".join(FILLER[:index] + ["wrong"] + FILLER[index:index + 2])


class LengthStepTests(unittest.TestCase):
    """LENGTH: 5-12語=100、下は不足1語ごとに-20、上は超過1語ごとに-11、
    60字超で-12（現行の調整値）。"""

    def test_short_side_steps(self):
        self.assertEqual(hookscore.check_length(" ".join(["ab"] * 4))[0], 80)
        self.assertEqual(hookscore.check_length(" ".join(["ab"] * 1))[0], 20)

    def test_long_side_steps_without_char_penalty(self):
        # "ab" x n は 3n-1 字。n<=20 は60字以下なので語数減点だけが効く。
        self.assertEqual(hookscore.check_length(" ".join(["ab"] * 13))[0], 89)
        self.assertEqual(hookscore.check_length(" ".join(["ab"] * 14))[0], 78)
        self.assertEqual(hookscore.check_length(" ".join(["ab"] * 15))[0], 67)

    def test_char_over_60_penalty_is_12(self):
        text = " ".join(["abcdefghij"] * 7)  # 7語・76字: 語数は理想域、字数減点のみ
        score, detail = hookscore.check_length(text)
        self.assertEqual(score, 88.0)
        self.assertIn("76 chars", detail)

    def test_spoken_seconds_use_2_75_words_per_second(self):
        _, detail = hookscore.check_length(" ".join(["ab"] * 11))
        self.assertIn("~4.0s spoken", detail)


class SpecificityStepTests(unittest.TestCase):
    """SPECIFICITY: ヒット0=15、以降 45 + ヒット数 x 30（上限100）。"""

    def test_steps(self):
        self.assertEqual(hookscore.check_specificity("plain vague words here")[0], 15.0)
        self.assertEqual(hookscore.check_specificity("I have five dogs now")[0], 75)
        # 2ヒットで 45+60=105 -> 100 に丸められる。
        self.assertEqual(hookscore.check_specificity("twenty dollars saved here")[0], 100.0)

    def test_spoken_number_and_money_word_each_count(self):
        score, detail = hookscore.check_specificity("twenty dollars saved here")
        self.assertIn("2 concrete marker(s): twenty, dollars", detail)

    def test_many_numbers_cap_at_100(self):
        self.assertEqual(hookscore.check_specificity("42 43 44 45 46")[0], 100.0)


class StakesStepTests(unittest.TestCase):
    """STAKES: マーカー0種=20、1種=70、2種以上=100。同一語の繰り返しは1種。"""

    def test_steps(self):
        self.assertEqual(hookscore.check_stakes("calm plain statement here")[0], 20.0)
        self.assertEqual(hookscore.check_stakes("this is wrong")[0], 70.0)
        self.assertEqual(hookscore.check_stakes("wrong and lost")[0], 100.0)

    def test_repeated_marker_counts_once(self):
        self.assertEqual(hookscore.check_stakes("wrong wrong wrong")[0], 70.0)

    def test_price_counts_as_one_extra_marker(self):
        self.assertEqual(hookscore.check_stakes("$5 off today deal")[0], 70.0)
        self.assertEqual(hookscore.check_stakes("wrong $5")[0], 100.0)


class FrontloadStepTests(unittest.TestCase):
    """FRONTLOAD: ペイロード位置 1-4語目=100、5-7語目=70、8語目以降=40、
    なし=30。弱い書き出しは一律-30。"""

    def test_position_steps(self):
        self.assertEqual(hookscore.check_frontload(hook_with_payload_at(3))[0], 100.0)
        self.assertEqual(hookscore.check_frontload(hook_with_payload_at(4))[0], 70.0)
        self.assertEqual(hookscore.check_frontload(hook_with_payload_at(6))[0], 70.0)
        self.assertEqual(hookscore.check_frontload(hook_with_payload_at(7))[0], 40.0)

    def test_no_payload_is_30(self):
        score, detail = hookscore.check_frontload(
            "plain calm quiet gentle soft words here now"
        )
        self.assertEqual(score, 30.0)
        self.assertEqual(detail, "no payload word anywhere in the line")

    def test_weak_opener_subtracts_30(self):
        score, detail = hookscore.check_frontload(
            "So alpha bravo charlie delta echo foxtrot wrong"
        )
        self.assertEqual(score, 10.0)  # 40 - 30
        self.assertIn('weak opener "so"', detail)

    def test_you_opener_also_hits_weak_opener_yo(self):
        # 現状の癖: "you" 始まりは弱い書き出し "yo" に前方一致して -30 される。
        score, detail = hookscore.check_frontload("You lost your only contract")
        self.assertEqual(score, 70.0)
        self.assertIn('weak opener "yo"', detail)


class AddressTierTests(unittest.TestCase):
    def test_all_four_tiers(self):
        self.assertEqual(hookscore.check_address("your move now friend")[0], 100.0)
        self.assertEqual(hookscore.check_address("Stop doing this wrong thing")[0], 90.0)
        self.assertEqual(hookscore.check_address("we did this thing together")[0], 70.0)
        self.assertEqual(hookscore.check_address("The contract was lost")[0], 35.0)


class OverallFormulaTests(unittest.TestCase):
    """総合: 平均 x 0.6 + 最低 x 0.4 - フラグ x 15。判定は STRONG に
    総合70以上・最低55以上・フラグなしの3条件が要る（現行値）。"""

    def test_one_flag_costs_exactly_15(self):
        _, plain, _, flags_plain = hookscore.run("You lost $5000 on this")
        _, flagged, _, flags = hookscore.run("You lost $5000 on this \U0001F600")
        self.assertEqual(flags_plain, [])
        self.assertEqual(len(flags), 1)
        self.assertAlmostEqual(plain - flagged, 15.0)

    def test_two_flags_stack(self):
        _, overall, verdict, flags = hookscore.run("Stop scrolling #tag")
        self.assertEqual(len(flags), 2)
        self.assertAlmostEqual(round(overall, 1), 16.2)
        self.assertEqual(verdict, "WEAK")

    def test_strong_blocked_by_low_minimum(self):
        # 総合は50を超えるが最低チェック（SPECIFICITY 15）が55未満なので OK 止まり。
        results, overall, verdict, _ = hookscore.run(
            "You wrong lost cut paid free secret truth"
        )
        self.assertEqual(results["SPECIFICITY"][0], 15.0)
        self.assertAlmostEqual(round(overall, 1), 52.2)
        self.assertEqual(verdict, "OK")

    def test_strong_blocked_by_flag(self):
        _, overall, verdict, flags = hookscore.run(
            "You lost $5000 doing this wrong \U0001F600"
        )
        self.assertEqual(len(flags), 1)
        self.assertAlmostEqual(round(overall, 1), 66.4)
        self.assertEqual(verdict, "OK")


class DealbreakerTests(unittest.TestCase):
    """DEALBREAKERS 5種の発火条件を1つずつ固定する。"""

    CASES = {
        "stop scrolling": "Stop scrolling now friend",
        "Video preamble": "In this video I show stuff",
        "Greeting": "hey there friend watch",
        "Hashtag in the hook": "watch this #tag now",
        "Emoji in the hook": "watch this \U0001F600 now",
    }

    def test_each_dealbreaker_fires_alone(self):
        for fragment, text in self.CASES.items():
            with self.subTest(fragment=fragment):
                _, _, _, flags = hookscore.run(text)
                self.assertEqual(len(flags), 1)
                self.assertIn(fragment, flags[0])

    def test_preamble_variant_im_going_to_show_you(self):
        _, _, _, flags = hookscore.run("I'm going to show you how")
        self.assertEqual(len(flags), 1)
        self.assertIn("Video preamble", flags[0])


class CliTests(unittest.TestCase):
    SCRIPT = str(HERE / "hookscore.py")

    def run_cli(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            input=stdin, capture_output=True, text=True,
        )

    def test_json_single_hook_is_object_and_exit_0_even_when_weak(self):
        r = self.run_cli("--hook", "Hey guys welcome", "--json")
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["verdict"], "WEAK")
        self.assertEqual(payload["weakest"], "FRONTLOAD")

    def test_json_multiple_hooks_is_list_in_input_order(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("Hey guys welcome to my channel today\n")
            fh.write("I lost $18,000 on one missing contract.\n")
            path = fh.name
        r = self.run_cli(path, "--json")
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertIsInstance(payload, list)
        # --json では入力順のまま（ランキング並び替えは表示モードだけ）。
        self.assertEqual([p["verdict"] for p in payload], ["WEAK", "STRONG"])

    def test_empty_input_exits_2(self):
        r = self.run_cli("-", stdin="")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing to score", r.stderr)

    def test_text_mode_exit_code_follows_best_score(self):
        r = self.run_cli("--hook", "Hey guys welcome to my channel today")
        self.assertEqual(r.returncode, 1)
        r2 = self.run_cli("--hook", "I lost $18,000 on one missing contract.")
        self.assertEqual(r2.returncode, 0)


if __name__ == "__main__":
    unittest.main()
