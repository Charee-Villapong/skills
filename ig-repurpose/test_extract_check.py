"""extract_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-repurpose/SKILL.md「Extract, do not summarise」節と Issue #54。
- 抽出カテゴリは claims / numbers / stories / mechanisms / mistakes / lines
- 件数を一覧化し、合計が下限（既定 4 件）未満なら素材は薄い（thin）
- 薄い場合は週間計画へ進まず、投稿数を絞るよう促す
- 十分な場合の推奨投稿数は素材 1 本あたりの上限（既定 6 件）まで
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_check import ExtractChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "extract_check.py"

EXAMPLE_COUNTS = {
    "claims": 5,
    "numbers": 9,
    "stories": 3,
    "mechanisms": 4,
    "mistakes": 2,
    "lines": 7,
}


class TestSufficient:
    def test_skill_example_is_sufficient(self):
        r = ExtractChecker().assess(EXAMPLE_COUNTS)
        assert r["total"] == 30
        assert r["is_thin"] is False
        assert r["verdict"] == "sufficient"
        assert r["can_proceed"] is True

    def test_skill_example_recommended_posts_capped_at_six(self):
        r = ExtractChecker().assess(EXAMPLE_COUNTS)
        assert r["recommended_posts"] == 6

    def test_exactly_four_items_is_sufficient(self):
        r = ExtractChecker().assess({"claims": 4})
        assert r["total"] == 4
        assert r["is_thin"] is False
        assert r["can_proceed"] is True
        assert r["recommended_posts"] == 4

    def test_five_items_recommend_five_posts(self):
        r = ExtractChecker().assess({"claims": 3, "stories": 2})
        assert r["recommended_posts"] == 5

    def test_counts_are_normalised_with_all_categories(self):
        r = ExtractChecker().assess({"claims": 4})
        assert r["counts"]["claims"] == 4
        assert r["counts"]["numbers"] == 0
        assert r["counts"]["lines"] == 0


class TestThin:
    def test_three_items_is_thin(self):
        r = ExtractChecker().assess({"claims": 2, "lines": 1})
        assert r["total"] == 3
        assert r["is_thin"] is True
        assert r["verdict"] == "thin"
        assert r["can_proceed"] is False

    def test_thin_recommended_posts_do_not_exceed_total(self):
        r = ExtractChecker().assess({"claims": 2, "lines": 1})
        assert r["recommended_posts"] == 3

    def test_thin_message_prompts_narrowing_posts(self):
        r = ExtractChecker().assess({"claims": 1})
        assert r["message"]

    def test_zero_items_is_thin(self):
        r = ExtractChecker().assess({})
        assert r["total"] == 0
        assert r["is_thin"] is True
        assert r["recommended_posts"] == 0


class TestCustomThresholds:
    def test_custom_min_total(self):
        checker = ExtractChecker(min_total=2)
        assert checker.assess({"claims": 2})["is_thin"] is False
        assert checker.assess({"claims": 1})["is_thin"] is True

    def test_custom_max_posts(self):
        checker = ExtractChecker(max_recommended_posts=4)
        assert checker.assess(EXAMPLE_COUNTS)["recommended_posts"] == 4


class TestValidation:
    def test_negative_count_raises(self):
        try:
            ExtractChecker().assess({"claims": -1})
        except ValueError:
            pass
        else:
            raise AssertionError("negative count must raise ValueError")

    def test_unknown_category_raises(self):
        try:
            ExtractChecker().assess({"unknown": 3})
        except ValueError:
            pass
        else:
            raise AssertionError("unknown category must raise ValueError")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


class TestCli:
    def test_cli_sufficient_exit_0(self):
        result = run_cli(
            "--claims",
            "5",
            "--numbers",
            "9",
            "--stories",
            "3",
            "--mechanisms",
            "4",
            "--mistakes",
            "2",
            "--lines",
            "7",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["total"] == 30
        assert payload["is_thin"] is False
        assert payload["recommended_posts"] == 6

    def test_cli_thin_exit_1(self):
        result = run_cli("--claims", "2", "--lines", "1")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["is_thin"] is True
        assert payload["can_proceed"] is False

    def test_cli_json_input(self, tmp_path):
        path = tmp_path / "counts.json"
        path.write_text(json.dumps({"claims": 4}), encoding="utf-8")
        result = run_cli("--input", str(path))
        assert result.returncode == 0
        assert json.loads(result.stdout)["total"] == 4
