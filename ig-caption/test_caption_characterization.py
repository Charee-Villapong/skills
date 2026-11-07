"""caption.py の現状固定テスト（特性テスト）。

リファクタリング（ig系共通化 C-005／スコア集約 C-007 等）の安全網として、
現行実装の入出力をそのまま固定する。仕様の正しさを主張するものではない。
標準ライブラリのみで動く。

    python3 -m unittest test_caption_characterization -v
    # または
    python3 test_caption_characterization.py
"""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import caption  # noqa: E402


def statuses(a):
    return {c["check"]: c["status"] for c in a["checks"]}


class VisibleWindowTests(unittest.TestCase):
    def test_short_text_is_stripped_and_returned_whole(self):
        self.assertEqual(caption.visible_window("  hi  ", 125), "hi")

    def test_long_text_is_cut_mid_word_at_exact_cut(self):
        self.assertEqual(caption.visible_window("hello world", 5), "hello")
        self.assertEqual(len(caption.visible_window("a" * 300, 125)), 125)


class AnalyseTests(unittest.TestCase):
    def test_ready_like_caption_still_reviews_when_tag_in_window(self):
        a = caption.analyse(
            "I saved $5000 with this one trick. Save this post.\n\n#money #tips"
        )
        self.assertEqual(a["characters"], 64)
        self.assertEqual(a["limit"], 2200)
        self.assertEqual(a["truncate_at"], 125)
        self.assertFalse(a["truncated"])
        self.assertEqual(a["first_line_chars"], 50)
        self.assertEqual(a["hashtags"], ["#money", "#tips"])
        self.assertEqual(a["mentions"], [])
        self.assertEqual(a["links"], [])
        self.assertEqual(a["emoji"], 0)
        self.assertEqual(a["asks"], ["save this"])
        st = statuses(a)
        self.assertEqual(st["LENGTH"], "PASS")
        self.assertEqual(st["FIRST LINE"], "PASS")
        self.assertEqual(st["HOOK IS CONCRETE"], "PASS")
        self.assertEqual(st["HASHTAGS"], "PASS")
        # ハッシュタグが表示窓内にあるため WARN になり、総合は REVIEW。
        self.assertEqual(st["TAG PLACEMENT"], "WARN")
        self.assertEqual(st["ONE ASK"], "PASS")
        self.assertEqual(a["verdict"], "REVIEW")

    def test_empty_caption(self):
        a = caption.analyse("")
        self.assertEqual(a["characters"], 0)
        self.assertEqual(a["visible"], "")
        st = statuses(a)
        self.assertEqual(st["FIRST LINE"], "FAIL")
        self.assertEqual(st["HOOK IS CONCRETE"], "WARN")
        self.assertEqual(st["ONE ASK"], "WARN")
        self.assertEqual(a["verdict"], "FIX")

    def test_first_line_hashtag_fails_and_filler_warns(self):
        a = caption.analyse(
            "#viral hello world this is a test caption with no concrete thing "
            "and please follow me and save this and share this https://example.com/x"
        )
        st = statuses(a)
        self.assertEqual(st["FIRST LINE"], "FAIL")
        self.assertEqual(st["HASHTAGS"], "WARN")
        self.assertEqual(st["LINKS"], "WARN")
        self.assertEqual(st["ONE ASK"], "WARN")
        self.assertEqual(a["verdict"], "FIX")

    def test_over_length_limit_fails(self):
        a = caption.analyse("a" * 2201)
        st = statuses(a)
        self.assertEqual(st["LENGTH"], "FAIL")
        self.assertIn("1 over the limit", a["checks"][0]["detail"])
        self.assertTrue(a["truncated"])

    def test_hashtag_cap_exceeded_fails(self):
        a = caption.analyse("Hook line with 42 things.\n\n#a #b #c #d #e #f")
        st = statuses(a)
        self.assertEqual(st["HASHTAGS"], "FAIL")

    def test_search_terms_status_transitions(self):
        base = "I saved $5000 with this one trick. Save this post."
        a = caption.analyse(base, keywords=["saved", "$5000"])
        st = statuses(a)
        self.assertEqual(st["SEARCH TERMS"], "PASS")
        a2 = caption.analyse(base, keywords=["saved", "missingterm"])
        self.assertEqual(statuses(a2)["SEARCH TERMS"], "WARN")
        a3 = caption.analyse(base, keywords=["missingterm"])
        self.assertEqual(statuses(a3)["SEARCH TERMS"], "FAIL")
        # キーワード未指定なら SEARCH TERMS チェック自体が出ない。
        a4 = caption.analyse(base)
        self.assertNotIn("SEARCH TERMS", statuses(a4))

    def test_custom_cut_changes_window_and_truncation(self):
        a = caption.analyse("1234567890abcdef", cut=10)
        self.assertEqual(a["visible"], "1234567890")
        self.assertEqual(a["truncate_at"], 10)
        self.assertTrue(a["truncated"])

    def test_mentions_and_emoji_are_counted(self):
        a = caption.analyse("Hi @ana and @bob \U0001F600\U0001F600 test 42.")
        self.assertEqual(a["mentions"], ["@ana", "@bob"])
        self.assertEqual(a["emoji"], 2)


class RenderAndCliTests(unittest.TestCase):
    def test_render_mentions_verdict(self):
        a = caption.analyse("I saved $5000 with this one trick. Save this post.")
        out = io.StringIO()
        caption.render(a, out=out)
        text = out.getvalue()
        self.assertIn("CAPTION LINT", text)
        self.assertIn("VERDICT", text)

    def test_cli_json_exit_codes(self):
        script = str(Path(__file__).resolve().parent / "caption.py")
        with __import__("tempfile").NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("Short 42 hook. Save this.")
            path = fh.name
        r = subprocess.run(
            [sys.executable, script, path, "--json"],
            capture_output=True, text=True,
        )
        payload = json.loads(r.stdout)
        self.assertEqual(payload["characters"], len("Short 42 hook. Save this."))
        self.assertIn(payload["verdict"], ("READY", "REVIEW", "FIX"))
        # 終了コードは READY のときだけ 0、それ以外は 1（現行仕様）。
        self.assertEqual(r.returncode, 0 if payload["verdict"] == "READY" else 1)


if __name__ == "__main__":
    unittest.main()
