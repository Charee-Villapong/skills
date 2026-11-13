"""plan_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-plan/SKILL.md「What to post」節と Issue #45。

完了の定義:
- 週の投稿数は 4〜5 件
- リールは 3 件以上
- 同一種別が連続しない（back to back の禁止）
- 種別ごとの個数: Proof 1/週、Teach 1〜2/週、Opinion 1/週、
  Story 1/隔週（週では 0〜1）、Offer 1/隔週（週では 0〜1）
- 種別ごとの形式: Proof=Reel、Teach=Reel|Carousel、Opinion=Reel、
  Story=Reel、Offer=Carousel|Stories
- 違反があれば ok=False で違反を一覧化し、CLI は終了コード 1 を返す

実行方法:
    python3 -m pytest test_plan_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_check import WeeklyPlanChecker, check_plan  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "plan_check.py"


def post(type_, format_):
    return {"type": type_, "format": format_}


# SKILL.md の Output 例（TUE Proof/Reel, THU Teach/Carousel,
# FRI Opinion/Reel, SUN Story/Reel）= 4件・リール3件で通過するはず。
VALID_PLAN = {
    "posts": [
        post("Proof", "Reel"),
        post("Teach", "Carousel"),
        post("Opinion", "Reel"),
        post("Story", "Reel"),
    ]
}

VALID_PLAN_5 = {
    "posts": [
        post("Proof", "Reel"),
        post("Teach", "Reel"),
        post("Opinion", "Reel"),
        post("Teach", "Carousel"),
        post("Offer", "Carousel"),
    ]
}


def codes(result):
    return [v["code"] for v in result["violations"]]


class TestValidPlans:
    def test_output_example_plan_passes(self):
        result = check_plan(VALID_PLAN)
        assert result["ok"] is True
        assert result["violations"] == []

    def test_five_post_plan_with_offer_passes(self):
        result = check_plan(VALID_PLAN_5)
        assert result["ok"] is True

    def test_counts_reported(self):
        result = check_plan(VALID_PLAN)
        assert result["counts"]["total"] == 4
        assert result["counts"]["reels"] == 3
        assert result["counts"]["by_type"]["Proof"] == 1
        assert result["counts"]["by_type"]["Teach"] == 1

    def test_type_and_format_are_case_insensitive(self):
        plan = {
            "posts": [
                post("proof", "reel"),
                post("TEACH", "carousel"),
                post("Opinion", "REEL"),
                post("story", "Reel"),
            ]
        }
        assert check_plan(plan)["ok"] is True

    def test_checker_class_matches_function(self):
        checker = WeeklyPlanChecker()
        assert checker.check(VALID_PLAN)["ok"] is True


class TestTotalAndReels:
    def test_three_posts_fails_total(self):
        plan = {"posts": VALID_PLAN["posts"][:3]}
        result = check_plan(plan)
        assert result["ok"] is False
        assert "total_posts" in codes(result)

    def test_six_posts_fails_total(self):
        plan = {"posts": VALID_PLAN_5["posts"] + [post("Story", "Reel")]}
        result = check_plan(plan)
        assert result["ok"] is False
        assert "total_posts" in codes(result)

    def test_empty_plan_fails(self):
        result = check_plan({"posts": []})
        assert result["ok"] is False
        assert "total_posts" in codes(result)

    def test_two_reels_fails_min_reels(self):
        plan = {
            "posts": [
                post("Teach", "Carousel"),
                post("Proof", "Reel"),
                post("Teach", "Carousel"),
                post("Offer", "Carousel"),
            ]
        }
        result = check_plan(plan)
        assert result["ok"] is False
        assert "min_reels" in codes(result)


class TestConsecutive:
    def test_same_type_back_to_back_fails(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Reel"),
                post("Teach", "Carousel"),
                post("Opinion", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert result["ok"] is False
        assert "consecutive_same_type" in codes(result)

    def test_same_type_separated_passes(self):
        assert check_plan(VALID_PLAN_5)["ok"] is True


class TestPerTypeCounts:
    def test_missing_proof_fails(self):
        plan = {
            "posts": [
                post("Teach", "Reel"),
                post("Opinion", "Reel"),
                post("Teach", "Carousel"),
                post("Story", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "type_count" in codes(result)

    def test_two_proof_fails(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Reel"),
                post("Proof", "Reel"),
                post("Opinion", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "type_count" in codes(result)

    def test_three_teach_fails(self):
        plan = {
            "posts": [
                post("Teach", "Reel"),
                post("Proof", "Reel"),
                post("Teach", "Carousel"),
                post("Opinion", "Reel"),
                post("Teach", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "type_count" in codes(result)

    def test_two_story_in_one_week_fails(self):
        plan = {
            "posts": [
                post("Story", "Reel"),
                post("Proof", "Reel"),
                post("Story", "Reel"),
                post("Opinion", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "type_count" in codes(result)

    def test_two_offer_in_one_week_fails(self):
        plan = {
            "posts": [
                post("Offer", "Carousel"),
                post("Proof", "Reel"),
                post("Offer", "Carousel"),
                post("Opinion", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "type_count" in codes(result)

    def test_unknown_type_fails(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Reel"),
                post("Opinion", "Reel"),
                post("Meme", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert result["ok"] is False
        assert "unknown_type" in codes(result)


class TestPerTypeFormats:
    def test_proof_must_be_reel(self):
        plan = {
            "posts": [
                post("Proof", "Carousel"),
                post("Teach", "Reel"),
                post("Opinion", "Reel"),
                post("Story", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "format_for_type" in codes(result)

    def test_teach_reel_or_carousel_only(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Stories"),
                post("Opinion", "Reel"),
                post("Story", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "format_for_type" in codes(result)

    def test_offer_carousel_or_stories_only(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Reel"),
                post("Opinion", "Reel"),
                post("Offer", "Reel"),
            ]
        }
        result = check_plan(plan)
        assert "format_for_type" in codes(result)

    def test_offer_stories_format_passes_format_check(self):
        plan = {
            "posts": [
                post("Proof", "Reel"),
                post("Teach", "Reel"),
                post("Opinion", "Reel"),
                post("Offer", "Stories"),
            ]
        }
        assert check_plan(plan)["ok"] is True


class TestCustomLimits:
    def test_custom_min_posts(self):
        checker = WeeklyPlanChecker(min_posts=3, max_posts=3)
        plan = {"posts": VALID_PLAN["posts"][:3]}
        result = checker.check(plan)
        assert "total_posts" not in codes(result)

    def test_custom_min_reels(self):
        checker = WeeklyPlanChecker(min_reels=4)
        result = checker.check(VALID_PLAN)
        assert "min_reels" in codes(result)


class TestCli:
    def _run(self, tmp_path, plan, *extra):
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), *extra],
            capture_output=True,
            text=True,
        )

    def test_cli_valid_plan_exit_0(self, tmp_path):
        result = self._run(tmp_path, VALID_PLAN)
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_invalid_plan_exit_1_with_violations(self, tmp_path):
        result = self._run(tmp_path, {"posts": []})
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["violations"]

    def test_cli_min_reels_flag(self, tmp_path):
        result = self._run(tmp_path, VALID_PLAN, "--min-reels", "4")
        assert result.returncode == 1
        assert "min_reels" in codes(json.loads(result.stdout))
