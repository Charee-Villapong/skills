"""caption.py analyse() の未固定分岐と二重管理数値の現状固定テスト。

既存 test_caption_characterization.py が固定していない範囲を補う:
- analyse() の各チェックの分岐（FIRST LINE の WARN、HASHTAGS の上限到達時
  WARN、TAG PLACEMENT の below-fold PASS、EMOJI 密度の境界、ASKS 8種全パターン）
- C-088: 手順（SKILL.md）とコードで二重管理されている数値
  （LIMIT 2200 / TRUNCATE 125 / HASHTAG_LIMIT 5）の現在値の一致

仕様の正しさを主張するものではない。標準ライブラリのみ。

    python3 test_caption_analyse_branches_characterization.py
"""

import io
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import caption  # noqa: E402


def check(a, name):
    return next(c for c in a["checks"] if c["check"] == name)


class DoubleManagedConstantsTests(unittest.TestCase):
    """C-088: コード側の定数と SKILL.md 側の記載が現状一致していることを固定。"""

    def test_constant_values(self):
        self.assertEqual(caption.LIMIT, 2200)
        self.assertEqual(caption.TRUNCATE, 125)
        self.assertEqual(caption.HASHTAG_LIMIT, 5)

    def test_skill_md_states_the_same_numbers(self):
        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("first 125 characters", skill)
        self.assertIn("2,200 characters", skill)
        self.assertIn("capped hashtags at five per post", skill)

    def test_analyse_reports_constants_back(self):
        a = caption.analyse("Hook 42 here.")
        self.assertEqual(a["limit"], 2200)
        self.assertEqual(a["truncate_at"], 125)


class LengthAndTruncationBoundaryTests(unittest.TestCase):
    def test_exactly_at_limit_passes(self):
        a = caption.analyse("a" * 2200)
        c = check(a, "LENGTH")
        self.assertEqual(c["status"], "PASS")
        self.assertEqual(c["detail"], "2200 / 2200 characters")

    def test_truncation_boundary(self):
        self.assertFalse(caption.analyse("a" * 125)["truncated"])
        self.assertTrue(caption.analyse("a" * 126)["truncated"])


class FirstLineBranchTests(unittest.TestCase):
    def test_first_line_longer_than_cut_warns(self):
        a = caption.analyse("x " * 70 + "\nBody 42 here. Save this.")
        c = check(a, "FIRST LINE")
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(
            c["detail"],
            "139 characters, so it gets cut at 125 mid-thought. "
            "Fine if the cut is a cliffhanger, bad if it is a subordinate clause",
        )

    def test_first_line_mention_fails(self):
        a = caption.analyse("@ana leads this caption 42. Save this.")
        c = check(a, "FIRST LINE")
        self.assertEqual(c["status"], "FAIL")
        self.assertTrue(c["detail"].startswith("opens on a hashtag or a mention"))
        self.assertEqual(a["verdict"], "FIX")


class HashtagBranchTests(unittest.TestCase):
    HOOK = "Hook with 42 things here.\n\n"

    def test_at_cap_with_filler_warns(self):
        a = caption.analyse(self.HOOK + "#a #b #c #d #viral")
        c = check(a, "HASHTAGS")
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(
            c["detail"],
            "5 tags, at the cap, and 1 of them generic. Spend the five on topics",
        )

    def test_at_cap_without_filler_passes(self):
        a = caption.analyse(self.HOOK + "#a #b #c #d #e")
        c = check(a, "HASHTAGS")
        self.assertEqual(c["status"], "PASS")
        self.assertEqual(c["detail"], "5 tag(s): #a #b #c #d #e")

    def test_below_cap_with_filler_warns_with_names(self):
        a = caption.analyse(self.HOOK + "#viral #fyp")
        c = check(a, "HASHTAGS")
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(
            c["detail"],
            "2 tags, 2 of them generic (#viral, #fyp). Those describe nothing",
        )

    def test_filler_matching_is_case_insensitive(self):
        a = caption.analyse(self.HOOK + "#VIRAL")
        self.assertEqual(a["hashtags"], ["#VIRAL"])
        self.assertEqual(check(a, "HASHTAGS")["status"], "WARN")


class TagPlacementBranchTests(unittest.TestCase):
    def test_tags_below_the_fold_pass(self):
        body = (
            "I saved $5000 doing this one simple thing. "
            "More detail follows here in this second sentence now. "
            "And even more explanation to push the tags well below the "
            "visible fold of the feed view."
        )
        a = caption.analyse(body + "\n\n#money #tips")
        self.assertTrue(a["truncated"])
        c = check(a, "TAG PLACEMENT")
        self.assertEqual(c["status"], "PASS")
        self.assertEqual(c["detail"], "tags are below the fold")


class LinkBranchTests(unittest.TestCase):
    def test_link_variants_all_warn(self):
        for text in (
            "see www.example.com now 42",
            "visit example.io/path today 42",
            "go to https://x.co/a 42",
        ):
            with self.subTest(text=text):
                a = caption.analyse(text)
                self.assertEqual(len(a["links"]), 1)
                self.assertEqual(check(a, "LINKS")["status"], "WARN")

    def test_bare_domain_without_path_is_not_a_link(self):
        a = caption.analyse("no links here at all 42")
        self.assertEqual(a["links"], [])
        self.assertEqual(check(a, "LINKS")["status"], "PASS")


class EmojiDensityBoundaryTests(unittest.TestCase):
    """EMOJI は密度 > 4 / 100字 で WARN。境界の現在値を固定する。"""

    def test_density_just_over_4_warns(self):
        a = caption.analyse("a" * 23 + "\U0001F600")
        c = check(a, "EMOJI")
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(
            c["detail"], "1 emoji, 4.2 per 100 characters - reads as decoration"
        )

    def test_density_exactly_4_passes(self):
        a = caption.analyse("a" * 24 + "\U0001F600")
        c = check(a, "EMOJI")
        self.assertEqual(c["status"], "PASS")
        self.assertEqual(c["detail"], "1 emoji, 4.0 per 100 characters")


class AskPatternTests(unittest.TestCase):
    """ASKS 8パターンの名称対応（現行の検出結果）を全種固定する。"""

    SAMPLES = {
        "comment a keyword": "Please comment the word GROWTH below 42",
        "DM me": "DM me for the details 42",
        "save this": "Save it for later 42",
        "share this": "Share it with a friend 42",
        "follow": "Follow for more tips 42",
        "link in bio": "Link in my bio 42",
        "swipe or tap": "Swipe through to see 42",
        "answer a question": "Tell me your pick 42",
    }

    def test_each_ask_pattern(self):
        for name, text in self.SAMPLES.items():
            with self.subTest(ask=name):
                self.assertEqual(caption.analyse(text)["asks"], [name])

    def test_multiple_asks_detail_lists_both(self):
        a = caption.analyse("Save this and share this 42.")
        c = check(a, "ONE ASK")
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(
            c["detail"],
            "2 asks (save this, share this). Two asks is the same as none",
        )


class SearchTermsWindowTests(unittest.TestCase):
    def test_keyword_present_but_outside_window(self):
        a = caption.analyse("a" * 130 + " alpha", keywords=["alpha"])
        c = check(a, "SEARCH TERMS")
        self.assertEqual(c["status"], "PASS")
        self.assertEqual(c["detail"], "1/1 present, 0 in the visible window")

    def test_blank_keywords_are_dropped(self):
        a = caption.analyse("Hook 42 here.", keywords=["", "  "])
        self.assertNotIn("SEARCH TERMS", [c["check"] for c in a["checks"]])


class RenderBoxTests(unittest.TestCase):
    def test_not_truncated_tail(self):
        out = io.StringIO()
        caption.render_box("short", False, out=out)
        self.assertIn("(whole caption fits)", out.getvalue())

    def test_truncated_tail(self):
        out = io.StringIO()
        caption.render_box("x" * 200, True, out=out)
        self.assertIn("... more", out.getvalue())

    def test_box_shows_at_most_eight_content_lines(self):
        long = "\n".join("line %d " % i + "word " * 10 for i in range(12))
        out = io.StringIO()
        caption.render_box(long, False, out=out)
        rows = [l for l in out.getvalue().splitlines() if l.startswith("  |")]
        self.assertEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main()
