"""comment_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-comment/SKILL.md「Rules」節と Issue #38。
- コメントは 1〜3 文
- 書き出し禁止: "Great post" / "Love this" / "So true" / "This 👏" /
  "Needed this today" / 作成者のファーストネーム＋感嘆符
- 絵文字のみのコメント禁止、絵文字で始めるコメント禁止
- 売り込み禁止: リンクと "check out my page"
違反は一覧化され、ok は違反ゼロのときだけ True。意味判定（リールの
言い換え・複数アイデア・具体性）はコード化対象外でテストしない。
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comment_check import CommentChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "comment_check.py"


def codes(result):
    return [v["code"] for v in result["violations"]]


class TestValidComments:
    def test_one_sentence_passes(self):
        r = CommentChecker().check("We raised ours 40% last March.")
        assert r["ok"] is True
        assert r["sentence_count"] == 1
        assert r["violations"] == []

    def test_two_sentences_from_skill_example_pass(self):
        text = (
            "We raised ours 40% last March and lost exactly one client. "
            "Took eight months to stop being scared of it."
        )
        r = CommentChecker().check(text)
        assert r["ok"] is True
        assert r["sentence_count"] == 2

    def test_three_sentences_pass(self):
        r = CommentChecker().check("One point. Second point. Third point?")
        assert r["ok"] is True
        assert r["sentence_count"] == 3

    def test_no_terminal_punctuation_counts_as_one_sentence(self):
        r = CommentChecker().check("This holds until the team grows")
        assert r["ok"] is True
        assert r["sentence_count"] == 1

    def test_emoji_inside_comment_is_allowed(self):
        r = CommentChecker().check("We tried this last year 👏 and it worked.")
        assert r["ok"] is True


class TestSentenceCount:
    def test_four_sentences_fail(self):
        r = CommentChecker().check("One. Two. Three. Four.")
        assert r["ok"] is False
        assert r["sentence_count"] == 4
        assert "too_many_sentences" in codes(r)

    def test_empty_comment_fails(self):
        r = CommentChecker().check("   ")
        assert r["ok"] is False
        assert r["sentence_count"] == 0
        assert "empty_comment" in codes(r)

    def test_custom_max_sentences(self):
        checker = CommentChecker(max_sentences=2)
        assert checker.check("One. Two.")["ok"] is True
        assert "too_many_sentences" in codes(checker.check("One. Two. Three."))


class TestBannedOpenings:
    def test_each_default_banned_opening_fails(self):
        checker = CommentChecker()
        for opening in [
            "Great post, thanks for sharing this.",
            "Love this so much.",
            "So true, we see this too.",
            "This 👏 is exactly right.",
            "Needed this today, thank you.",
        ]:
            r = checker.check(opening)
            assert r["ok"] is False, opening
            assert "banned_opening" in codes(r), opening

    def test_banned_opening_is_case_insensitive(self):
        r = CommentChecker().check("great post! Really helpful.")
        assert "banned_opening" in codes(r)

    def test_banned_phrase_not_at_opening_is_allowed(self):
        r = CommentChecker().check("We keep saying so true pricing matters.")
        # 文頭でなければ禁止書き出しには当たらない（少なくともその違反は無い）
        assert "banned_opening" not in codes(r)

    def test_creator_first_name_with_exclamation_fails(self):
        r = CommentChecker().check(
            "Alex! This changed how we price.", creator_name="Alex"
        )
        assert r["ok"] is False
        assert "creator_name_opening" in codes(r)

    def test_creator_name_without_exclamation_is_allowed(self):
        r = CommentChecker().check("Alex makes a fair point here.", creator_name="Alex")
        assert "creator_name_opening" not in codes(r)

    def test_creator_name_check_skipped_without_name(self):
        r = CommentChecker().check("Alex! This changed how we price.")
        assert "creator_name_opening" not in codes(r)


class TestEmojiRules:
    def test_emoji_only_comment_fails(self):
        r = CommentChecker().check("👏👏🔥")
        assert r["ok"] is False
        assert "emoji_only" in codes(r)

    def test_emoji_first_character_fails(self):
        r = CommentChecker().check("👏 We tried this and it worked.")
        assert r["ok"] is False
        assert "emoji_first_character" in codes(r)


class TestPitching:
    def test_link_fails(self):
        for text in [
            "We use a tool for this: https://example.com/tool",
            "Details at www.example.com for anyone interested.",
        ]:
            r = CommentChecker().check(text)
            assert "pitching_link" in codes(r), text

    def test_check_out_my_page_fails(self):
        r = CommentChecker().check("Check out my page for more on this.")
        assert "pitching_phrase" in codes(r)


class TestMultipleViolations:
    def test_violations_are_listed_together(self):
        r = CommentChecker().check("Great post! One. Two. Three. Four.")
        assert r["ok"] is False
        assert "banned_opening" in codes(r)
        assert "too_many_sentences" in codes(r)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


class TestCli:
    def test_cli_valid_comment_exit_0_and_json(self):
        result = run_cli("We raised ours 40% last March.")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["sentence_count"] == 1

    def test_cli_violation_exit_1_and_json(self):
        result = run_cli("Great post! One. Two. Three. Four.")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["violations"]

    def test_cli_creator_name_flag(self):
        result = run_cli("--creator-name", "Alex", "Alex! Good point.")
        assert result.returncode == 1
        assert "creator_name_opening" in codes(json.loads(result.stdout))

    def test_cli_max_sentences_flag(self):
        result = run_cli("--max-sentences", "1", "One. Two.")
        assert result.returncode == 1
        assert "too_many_sentences" in codes(json.loads(result.stdout))
