"""profile_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-profile/SKILL.md「Then rewrite, in this order」節と Issue #46。

完了の定義（文字数と個数の範囲）:
- 名前欄の案は 3 案、各案 30 文字以内
- bio は全体で 150 文字以内
- 固定投稿（pinned）は 3 件
- ハイライトは 4〜6 件
- リンクは 1〜5 件（プラットフォーム上限 5、宛先は 1 件が原則）
- グリッドのカバーは最初の 9 件分、各カバーの文字は 4 語以内
- 違反があれば ok=False で違反を一覧化し、CLI は終了コード 1 を返す

実行方法:
    python3 -m pytest test_profile_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from profile_check import ProfileChecker, check_profile  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "profile_check.py"

VALID_PROFILE = {
    "name_options": [
        "Dana Ruiz | Proposal templates",
        "Dana Ruiz | Proposals that win",
        "Dana | Proposal template shop",
    ],
    "bio": (
        "I help freelancers win clients with proposal templates. "
        "Used by 2,000+ freelancers. Start with the free template below."
    ),
    "pinned_count": 3,
    "highlights": ["Pricing", "Results", "How it works", "About"],
    "link_count": 1,
    "grid_covers": [
        {"text": "The proposal template"},
        {"text": "Five clause mistakes"},
        {"text": "From draft to signed"},
        {"text": "Pricing without fear"},
        {"text": "The follow up email"},
        {"text": "What clients check first"},
        {"text": "Templates that win work"},
        {"text": "My exact proposal structure"},
        {"text": "Start here today"},
    ],
}


def codes(result):
    return [v["code"] for v in result["violations"]]


def variant(**changes):
    profile = dict(VALID_PROFILE)
    profile.update(changes)
    return profile


class TestValidProfile:
    def test_valid_profile_passes(self):
        result = check_profile(VALID_PROFILE)
        assert result["ok"] is True
        assert result["violations"] == []

    def test_measurements_reported(self):
        result = check_profile(VALID_PROFILE)
        m = result["measurements"]
        assert m["name_options"] == 3
        assert m["pinned"] == 3
        assert m["highlights"] == 4
        assert m["links"] == 1
        assert m["grid_covers"] == 9

    def test_checker_class_matches_function(self):
        assert ProfileChecker().check(VALID_PROFILE)["ok"] is True

    def test_list_forms_for_counts_pass(self):
        profile = variant(
            pinned=[{"id": 1}, {"id": 2}, {"id": 3}],
            links=["https://example.com"],
        )
        profile.pop("pinned_count")
        profile.pop("link_count")
        assert check_profile(profile)["ok"] is True

    def test_bio_exactly_150_chars_passes(self):
        assert check_profile(variant(bio="a" * 150))["ok"] is True

    def test_name_option_exactly_30_chars_passes(self):
        options = ["a" * 30, "b" * 10, "c" * 10]
        assert check_profile(variant(name_options=options))["ok"] is True

    def test_six_highlights_passes(self):
        highlights = ["A", "B", "C", "D", "E", "F"]
        assert check_profile(variant(highlights=highlights))["ok"] is True

    def test_five_links_passes_count_check(self):
        assert check_profile(variant(link_count=5))["ok"] is True


class TestNameField:
    def test_name_option_over_30_chars_fails(self):
        options = ["a" * 31, "b" * 10, "c" * 10]
        result = check_profile(variant(name_options=options))
        assert result["ok"] is False
        assert "name_too_long" in codes(result)

    def test_two_name_options_fails(self):
        result = check_profile(variant(name_options=["A", "B"]))
        assert "name_options_count" in codes(result)

    def test_four_name_options_fails(self):
        result = check_profile(variant(name_options=["A", "B", "C", "D"]))
        assert "name_options_count" in codes(result)


class TestBio:
    def test_bio_over_150_chars_fails(self):
        result = check_profile(variant(bio="a" * 151))
        assert result["ok"] is False
        assert "bio_too_long" in codes(result)


class TestPinned:
    def test_two_pinned_fails(self):
        result = check_profile(variant(pinned_count=2))
        assert "pinned_count" in codes(result)

    def test_four_pinned_fails(self):
        result = check_profile(variant(pinned_count=4))
        assert "pinned_count" in codes(result)


class TestHighlights:
    def test_three_highlights_fails(self):
        result = check_profile(variant(highlights=["A", "B", "C"]))
        assert "highlights_count" in codes(result)

    def test_seven_highlights_fails(self):
        result = check_profile(variant(highlights=list("ABCDEFG")))
        assert "highlights_count" in codes(result)


class TestLinks:
    def test_zero_links_fails(self):
        result = check_profile(variant(link_count=0))
        assert "link_count" in codes(result)

    def test_six_links_fails(self):
        result = check_profile(variant(link_count=6))
        assert "link_count" in codes(result)


class TestGridCovers:
    def test_eight_covers_fails(self):
        result = check_profile(variant(grid_covers=VALID_PROFILE["grid_covers"][:8]))
        assert "grid_covers_count" in codes(result)

    def test_cover_text_over_four_words_fails(self):
        covers = [dict(c) for c in VALID_PROFILE["grid_covers"]]
        covers[0] = {"text": "one two three four five"}
        result = check_profile(variant(grid_covers=covers))
        assert "cover_text_words" in codes(result)

    def test_cover_text_exactly_four_words_passes(self):
        covers = [{"text": "one two three four"}] * 9
        assert check_profile(variant(grid_covers=covers))["ok"] is True

    def test_cover_as_plain_string_passes(self):
        covers = ["one two three"] * 9
        assert check_profile(variant(grid_covers=covers))["ok"] is True


class TestMissingFields:
    def test_missing_bio_fails(self):
        profile = variant()
        del profile["bio"]
        result = check_profile(profile)
        assert result["ok"] is False
        assert "missing_field" in codes(result)

    def test_empty_profile_fails(self):
        result = check_profile({})
        assert result["ok"] is False
        assert "missing_field" in codes(result)


class TestCustomLimits:
    def test_custom_name_max_chars(self):
        checker = ProfileChecker(name_max_chars=10)
        result = checker.check(VALID_PROFILE)
        assert "name_too_long" in codes(result)

    def test_custom_bio_max_chars(self):
        checker = ProfileChecker(bio_max_chars=200)
        assert checker.check(variant(bio="a" * 180))["ok"] is True


class TestCli:
    def _run(self, tmp_path, profile, *extra):
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), *extra],
            capture_output=True,
            text=True,
        )

    def test_cli_valid_profile_exit_0(self, tmp_path):
        result = self._run(tmp_path, VALID_PROFILE)
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_invalid_profile_exit_1(self, tmp_path):
        result = self._run(tmp_path, variant(pinned_count=1))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "pinned_count" in codes(payload)

    def test_cli_name_max_chars_flag(self, tmp_path):
        result = self._run(tmp_path, VALID_PROFILE, "--name-max-chars", "10")
        assert result.returncode == 1
        assert "name_too_long" in codes(json.loads(result.stdout))
