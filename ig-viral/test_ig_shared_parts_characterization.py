"""ig系モジュール間の共通部品の複製・不一致（C-005 / C-084）の現状固定テスト。

ig-caption / ig-reel(beats, hookscore) / ig-human(detect) / ig-viral(swipe) に
複製されている部品（words / WORD_RE / CONCRETE_RE / HASHTAG_RE / clamp / bar）に
ついて、現在の一致・不一致をそのまま固定する。共通部品へ集約する改修で
挙動が動いたら落ちる。仕様の正しさを主張するものではない。
標準ライブラリのみ。

    python3 test_ig_shared_parts_characterization.py
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


caption = load("shared_caption", "ig-caption/caption.py")
beats = load("shared_beats", "ig-reel/beats.py")
hookscore = load("shared_hookscore", "ig-reel/hookscore.py")
detect = load("shared_detect", "ig-human/detect.py")

sys.path.insert(0, str(ROOT / "ig-viral"))
import swipe  # noqa: E402

SAMPLES = [
    "I lost $18,000 on one missing contract.",
    "It's a test, isn't it? 100% real.",
    "don't stop believin' now",
    "Plain words only here",
    "$5 and 42 more things in 2026",
]


class WordsDuplicationTests(unittest.TestCase):
    def test_beats_and_hookscore_words_are_identical(self):
        # WORD_RE もカンマ除去の前処理も複製同士で完全に一致（現状）。
        self.assertEqual(beats.WORD_RE.pattern, hookscore.WORD_RE.pattern)
        for s in SAMPLES:
            with self.subTest(s=s):
                self.assertEqual(beats.words(s), hookscore.words(s))

    def test_swipe_shares_pattern_but_not_comma_stripping(self):
        # 不一致の固定: swipe は同じ WORD_RE を使うがカンマ除去をしないため、
        # "$18,000" が "$18" と "000" に割れる（beats/hookscore は1語）。
        self.assertEqual(swipe.WORD_RE.pattern, beats.WORD_RE.pattern)
        self.assertEqual(beats.words("$18,000 deal"), ["$18000", "deal"])
        self.assertEqual(
            swipe.WORD_RE.findall("$18,000 deal"), ["$18", "000", "deal"]
        )

    def test_detect_words_drops_digits_and_money(self):
        # 不一致の固定: detect の WORD_RE は英字と ' のみ。
        self.assertEqual(detect.WORD_RE.pattern, r"[A-Za-z']+")
        self.assertEqual(
            detect.words("$5 and 42 more things in 2026"),
            ["and", "more", "things", "in"],
        )
        self.assertEqual(
            beats.words("$5 and 42 more things in 2026"),
            ["$5", "and", "42", "more", "things", "in", "2026"],
        )


class ConcreteRegexDuplicationTests(unittest.TestCase):
    def test_caption_and_beats_concrete_re_are_identical(self):
        self.assertEqual(caption.CONCRETE_RE.pattern, beats.CONCRETE_RE.pattern)
        for s in SAMPLES:
            with self.subTest(s=s):
                self.assertEqual(
                    caption.CONCRETE_RE.findall(s), beats.CONCRETE_RE.findall(s)
                )

    def test_thousands_separator_quirk_is_shared(self):
        # 現状の癖も一致: "$18,000" は "$1" と "000" に割れて数えられる。
        self.assertEqual(caption.CONCRETE_RE.findall("$18,000"), ["$1", "000"])
        self.assertEqual(beats.CONCRETE_RE.findall("$18,000"), ["$1", "000"])


class HashtagRegexDifferenceTests(unittest.TestCase):
    def test_caption_captures_tag_hookscore_captures_with_space(self):
        # 不一致の固定: caption はグループでタグのみ、hookscore は
        # 前置空白込みでマッチ全体を返す形。
        text = "say #tag now"
        self.assertEqual(caption.HASHTAG_RE.findall(text), ["#tag"])
        self.assertEqual(hookscore.HASHTAG_RE.findall(text), [" #tag"])


class ClampAndBarTests(unittest.TestCase):
    def test_clamp_copies_agree(self):
        for value in (-10, 0, 42.5, 100, 250):
            with self.subTest(value=value):
                self.assertEqual(hookscore.clamp(value), detect.clamp(value))

    def test_bar_copies_agree(self):
        for score in (0, 37.5, 62.0, 100):
            with self.subTest(score=score):
                self.assertEqual(hookscore.bar(score), detect.bar(score))


class SwipeHookscoreCouplingTests(unittest.TestCase):
    def test_swipe_uses_hookscore_run_for_scores(self):
        # swipe.analyse の hook_score は hookscore.run の総合そのもの（現行結合）。
        self.assertIsNotNone(swipe.score_hook)
        hook = "How I made $10k in 30 days"
        rows = [
            {
                "account": "acc",
                "followers": 1000,
                "median": None,
                "views": 5000,
                "hook": hook,
            }
        ]
        a = swipe.analyse(rows, swipe.load_formulas(str(ROOT / "ig-reel" / "hooks.json")))
        _, overall, verdict, _ = hookscore.run(hook)
        self.assertEqual(a["reels"][0]["hook_score"], round(overall, 1))
        self.assertEqual(a["reels"][0]["hook_verdict"], verdict)


if __name__ == "__main__":
    unittest.main()
