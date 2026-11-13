"""carousel_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル ig-carousel の「Structure」節と「Building the files」節。

- スライドは 6〜10 枚
- 1 枚目 COVER: フックは 6 語以下、その下に約束文が 1 行ある
- 2 枚目 STAKE: なぜ大事かを書く（本文があること）
- 3 枚目〜（RECAP の前まで）: 1 枚に 1 つの考え。見出し 3〜7 語、
  その下の本文は 25 語以下
- 最後から 2 枚目 RECAP、最後 CTA の並び
- ファイル寸法は 1080x1350、文字サイズは 32px 以上（指定がある場合）

実装（carousel_check.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_carousel_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from carousel_check import CarouselChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "carousel_check.py"


def words(count, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(1, count + 1))


def make_slide(role, headline="", body="", **extra):
    slide = {"role": role, "headline": headline, "body": body}
    slide.update(extra)
    return slide


def valid_deck():
    """仕様を満たす 8 枚のデッキ（SKILL.md の出力例が土台）。"""
    return {
        "width": 1080,
        "height": 1350,
        "slides": [
            make_slide(
                "cover",
                "THE $18,000 CLAUSE",
                "One line I now put in every contract.",
            ),
            make_slide(
                "stake",
                "",
                "I approved the work and they asked for the money back.",
            ),
            make_slide(
                "content",
                "WHAT IT SAYS",
                "Payment on delivery, not on approval.",
            ),
            make_slide(
                "content",
                "WHERE IT GOES",
                "In the payment section, before the signature line.",
            ),
            make_slide(
                "content",
                "WHY IT WORKS",
                "Delivery is a date both sides can point to.",
            ),
            make_slide(
                "content",
                "WHEN IT FAILS",
                "Approval is a feeling, and feelings change later.",
            ),
            make_slide(
                "recap",
                "THE WHOLE THING",
                "Payment on delivery, not on approval. In the payment "
                "section. Because delivery is a date. Feelings change.",
            ),
            make_slide(
                "cta",
                "",
                "Comment CONTRACT and I will send the full clause.",
            ),
        ],
    }


def codes(result):
    return [v["code"] for v in result["violations"]]


def check(deck, **kwargs):
    return CarouselChecker(**kwargs).check(deck)


# ---------------------------------------------------------------------------
# 正常系
# ---------------------------------------------------------------------------


class TestValidDeck:
    def test_valid_deck_passes(self):
        result = check(valid_deck())
        assert result["ok"] is True
        assert result["violations"] == []
        assert result["slide_count"] == 8

    def test_six_slides_passes(self):
        deck = valid_deck()
        deck["slides"] = deck["slides"][:4] + deck["slides"][6:]
        assert len(deck["slides"]) == 6
        assert check(deck)["ok"] is True

    def test_ten_slides_passes(self):
        deck = valid_deck()
        extra = make_slide("content", "ONE MORE POINT", "A short body line.")
        deck["slides"] = deck["slides"][:6] + [extra, extra] + deck["slides"][6:]
        assert len(deck["slides"]) == 10
        assert check(deck)["ok"] is True

    def test_deck_without_roles_still_checks_counts_and_words(self):
        deck = valid_deck()
        for slide in deck["slides"]:
            del slide["role"]
        assert check(deck)["ok"] is True

    def test_deck_without_dimensions_passes(self):
        deck = valid_deck()
        del deck["width"]
        del deck["height"]
        assert check(deck)["ok"] is True


# ---------------------------------------------------------------------------
# 枚数
# ---------------------------------------------------------------------------


class TestSlideCount:
    def test_five_slides_is_violation(self):
        deck = valid_deck()
        deck["slides"] = deck["slides"][:3] + deck["slides"][6:]
        assert len(deck["slides"]) == 5
        result = check(deck)
        assert result["ok"] is False
        assert "slide_count" in codes(result)

    def test_eleven_slides_is_violation(self):
        deck = valid_deck()
        extra = make_slide("content", "ONE MORE POINT", "A short body line.")
        deck["slides"] = deck["slides"][:6] + [extra] * 3 + deck["slides"][6:]
        assert len(deck["slides"]) == 11
        result = check(deck)
        assert result["ok"] is False
        assert "slide_count" in codes(result)

    def test_empty_deck_is_violation(self):
        result = check({"slides": []})
        assert result["ok"] is False
        assert "slide_count" in codes(result)
        assert result["slide_count"] == 0


# ---------------------------------------------------------------------------
# カバー
# ---------------------------------------------------------------------------


class TestCover:
    def test_cover_headline_six_words_passes(self):
        deck = valid_deck()
        deck["slides"][0]["headline"] = words(6)
        assert check(deck)["ok"] is True

    def test_cover_headline_seven_words_is_violation(self):
        deck = valid_deck()
        deck["slides"][0]["headline"] = words(7)
        result = check(deck)
        assert result["ok"] is False
        assert "cover_headline_words" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "cover_headline_words"
        ]
        assert violation[0]["slide"] == 1

    def test_cover_without_promise_line_is_violation(self):
        deck = valid_deck()
        deck["slides"][0]["body"] = ""
        result = check(deck)
        assert result["ok"] is False
        assert "cover_promise_missing" in codes(result)

    def test_cover_without_body_key_is_violation(self):
        deck = valid_deck()
        del deck["slides"][0]["body"]
        result = check(deck)
        assert "cover_promise_missing" in codes(result)


# ---------------------------------------------------------------------------
# STAKE
# ---------------------------------------------------------------------------


class TestStake:
    def test_stake_without_text_is_violation(self):
        deck = valid_deck()
        deck["slides"][1]["headline"] = ""
        deck["slides"][1]["body"] = ""
        result = check(deck)
        assert result["ok"] is False
        assert "stake_text_missing" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "stake_text_missing"
        ]
        assert violation[0]["slide"] == 2


# ---------------------------------------------------------------------------
# 中面（1 枚に 1 つの考え）
# ---------------------------------------------------------------------------


class TestContentSlides:
    def test_content_headline_three_words_passes(self):
        deck = valid_deck()
        deck["slides"][2]["headline"] = words(3)
        assert check(deck)["ok"] is True

    def test_content_headline_seven_words_passes(self):
        deck = valid_deck()
        deck["slides"][2]["headline"] = words(7)
        assert check(deck)["ok"] is True

    def test_content_headline_two_words_is_violation(self):
        deck = valid_deck()
        deck["slides"][2]["headline"] = words(2)
        result = check(deck)
        assert "content_headline_words" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "content_headline_words"
        ]
        assert violation[0]["slide"] == 3

    def test_content_headline_eight_words_is_violation(self):
        deck = valid_deck()
        deck["slides"][3]["headline"] = words(8)
        result = check(deck)
        assert "content_headline_words" in codes(result)

    def test_content_body_25_words_passes(self):
        deck = valid_deck()
        deck["slides"][2]["body"] = words(25)
        assert check(deck)["ok"] is True

    def test_content_body_26_words_is_violation(self):
        deck = valid_deck()
        deck["slides"][2]["body"] = words(26)
        result = check(deck)
        assert result["ok"] is False
        assert "content_body_words" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "content_body_words"
        ]
        assert violation[0]["slide"] == 3

    def test_recap_body_is_not_limited_to_25_words(self):
        deck = valid_deck()
        deck["slides"][6]["body"] = words(40)
        result = check(deck)
        assert "content_body_words" not in codes(result)
        assert result["ok"] is True

    def test_cta_is_not_checked_as_content(self):
        deck = valid_deck()
        deck["slides"][7]["headline"] = words(2)
        deck["slides"][7]["body"] = words(30)
        result = check(deck)
        assert "content_headline_words" not in codes(result)
        assert "content_body_words" not in codes(result)


# ---------------------------------------------------------------------------
# 役割の並び
# ---------------------------------------------------------------------------


class TestRoleOrder:
    def test_first_slide_not_cover_is_violation(self):
        deck = valid_deck()
        deck["slides"][0]["role"] = "content"
        deck["slides"][2]["role"] = "cover"
        result = check(deck)
        assert "role_order" in codes(result)

    def test_second_slide_not_stake_is_violation(self):
        deck = valid_deck()
        deck["slides"][1]["role"] = "content"
        deck["slides"][2]["role"] = "stake"
        result = check(deck)
        assert "role_order" in codes(result)

    def test_last_slide_not_cta_is_violation(self):
        deck = valid_deck()
        deck["slides"][7]["role"] = "recap"
        deck["slides"][6]["role"] = "cta"
        result = check(deck)
        assert "role_order" in codes(result)

    def test_second_last_slide_not_recap_is_violation(self):
        deck = valid_deck()
        deck["slides"][6]["role"] = "content"
        deck["slides"][3]["role"] = "recap"
        result = check(deck)
        assert "role_order" in codes(result)

    def test_middle_slide_with_wrong_role_is_violation(self):
        deck = valid_deck()
        deck["slides"][4]["role"] = "cta"
        deck["slides"][7]["role"] = "content"
        result = check(deck)
        assert "role_order" in codes(result)

    def test_role_names_are_case_insensitive(self):
        deck = valid_deck()
        for slide in deck["slides"]:
            slide["role"] = slide["role"].upper()
        assert check(deck)["ok"] is True


# ---------------------------------------------------------------------------
# 寸法と文字サイズ
# ---------------------------------------------------------------------------


class TestDimensions:
    def test_deck_dimensions_1080x1350_pass(self):
        assert check(valid_deck())["ok"] is True

    def test_deck_wrong_height_is_violation(self):
        deck = valid_deck()
        deck["height"] = 1080
        result = check(deck)
        assert result["ok"] is False
        assert "dimensions" in codes(result)

    def test_deck_wrong_width_is_violation(self):
        deck = valid_deck()
        deck["width"] = 1350
        result = check(deck)
        assert "dimensions" in codes(result)

    def test_slide_wrong_dimensions_is_violation_with_slide_number(self):
        deck = valid_deck()
        deck["slides"][3]["width"] = 1080
        deck["slides"][3]["height"] = 1920
        result = check(deck)
        assert "dimensions" in codes(result)
        violation = [v for v in result["violations"] if v["code"] == "dimensions"]
        assert any(v["slide"] == 4 for v in violation)

    def test_font_size_32_passes(self):
        deck = valid_deck()
        deck["slides"][0]["font_size_px"] = 32
        assert check(deck)["ok"] is True

    def test_font_size_below_32_is_violation(self):
        deck = valid_deck()
        deck["slides"][0]["font_size_px"] = 24
        result = check(deck)
        assert result["ok"] is False
        assert "font_size" in codes(result)


# ---------------------------------------------------------------------------
# しきい値の変数化
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_custom_max_slides_allows_eleven(self):
        deck = valid_deck()
        extra = make_slide("content", "ONE MORE POINT", "A short body line.")
        deck["slides"] = deck["slides"][:6] + [extra] * 3 + deck["slides"][6:]
        assert len(deck["slides"]) == 11
        assert check(deck, max_slides=20)["ok"] is True

    def test_custom_cover_max_words(self):
        deck = valid_deck()
        deck["slides"][0]["headline"] = words(4)
        assert "cover_headline_words" in codes(check(deck, cover_max_words=3))

    def test_custom_body_max_words(self):
        deck = valid_deck()
        deck["slides"][2]["body"] = words(10)
        assert "content_body_words" in codes(check(deck, body_max_words=5))

    def test_custom_dimensions(self):
        deck = valid_deck()
        deck["width"] = 1080
        deck["height"] = 1080
        assert check(deck, width=1080, height=1080)["ok"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_cli(*args, stdin_text=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        input=stdin_text,
    )


class TestCli:
    def test_cli_valid_deck_exits_zero(self, tmp_path):
        path = tmp_path / "deck.json"
        path.write_text(json.dumps(valid_deck()), encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["violations"] == []

    def test_cli_invalid_deck_exits_one_and_lists_violations(self, tmp_path):
        deck = valid_deck()
        deck["slides"][0]["headline"] = words(9)
        path = tmp_path / "deck.json"
        path.write_text(json.dumps(deck), encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "cover_headline_words" in [v["code"] for v in payload["violations"]]

    def test_cli_reads_stdin_with_dash(self):
        result = run_cli("-", stdin_text=json.dumps(valid_deck()))
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_max_slides_flag_changes_result(self, tmp_path):
        deck = valid_deck()
        extra = make_slide("content", "ONE MORE POINT", "A short body line.")
        deck["slides"] = deck["slides"][:6] + [extra] * 3 + deck["slides"][6:]
        path = tmp_path / "deck.json"
        path.write_text(json.dumps(deck), encoding="utf-8")
        assert run_cli(str(path)).returncode == 1
        assert run_cli(str(path), "--max-slides", "20").returncode == 0

    def test_cli_malformed_json_exits_two(self, tmp_path):
        path = tmp_path / "deck.json"
        path.write_text("{not json", encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 2

    def test_cli_missing_file_exits_two(self, tmp_path):
        result = run_cli(str(tmp_path / "nope.json"))
        assert result.returncode == 2
