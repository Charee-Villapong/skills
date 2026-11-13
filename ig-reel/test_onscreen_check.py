"""onscreen_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル ig-reel の「On-screen text is a separate script」節と
Issue #40。

完了の定義:
- 全カードが6語以内であること
- 全カードが安全領域内であること（1080x1920、y は 230 以上 1440 以下、
  右 230px は空ける = x の右端は 850 以下）
- フックカード（先頭カード）がフレーム1にあること
- 違反が1つでもあれば通過せず、違反を一覧で返すこと
- 違反がなければ通過すること

実装（onscreen_check.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_onscreen_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from onscreen_check import OnScreenChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "onscreen_check.py"


def good_cards():
    return [
        {
            "text": "5 HOURS -> 20 MIN",
            "x": 40,
            "y": 300,
            "width": 400,
            "height": 80,
            "frame": 1,
        },
        {
            "text": "STEAL THIS",
            "x": 40,
            "y": 500,
            "width": 300,
            "height": 80,
            "frame": 30,
        },
    ]


def kinds(result):
    return [v["kind"] for v in result["violations"]]


class TestPassing:
    def test_good_cards_pass(self):
        result = OnScreenChecker().check(good_cards())
        assert result["ok"] is True
        assert result["violations"] == []

    def test_exactly_six_words_passes(self):
        cards = good_cards()
        cards[0]["text"] = "one two three four five six"
        assert OnScreenChecker().check(cards)["ok"] is True

    def test_boundary_positions_pass(self):
        cards = [
            {"text": "OK", "x": 0, "y": 230, "width": 850, "height": 1210, "frame": 1}
        ]
        # y=230 .. y+height=1440, x+width=850 は境界内
        assert OnScreenChecker().check(cards)["ok"] is True

    def test_thousands_separator_counts_as_one_word(self):
        cards = good_cards()
        cards[0]["text"] = "$18,000 MISTAKE"  # 2 words via reeltext.words
        assert OnScreenChecker().check(cards)["ok"] is True

    def test_result_shape(self):
        result = OnScreenChecker().check(good_cards())
        assert set(result.keys()) == {"ok", "violations", "cards_checked"}
        assert result["cards_checked"] == 2


class TestWordLimit:
    def test_seven_words_fails(self):
        cards = good_cards()
        cards[1]["text"] = "one two three four five six seven"
        result = OnScreenChecker().check(cards)
        assert result["ok"] is False
        assert "too_many_words" in kinds(result)
        v = [x for x in result["violations"] if x["kind"] == "too_many_words"][0]
        assert v["card_index"] == 1
        assert v["word_count"] == 7

    def test_custom_max_words(self):
        cards = good_cards()
        cards[0]["text"] = "one two three"
        assert OnScreenChecker(max_words=2).check(cards)["ok"] is False
        assert OnScreenChecker(max_words=3).check(cards)["ok"] is True


class TestSafeZone:
    def test_above_safe_zone_fails(self):
        cards = good_cards()
        cards[0]["y"] = 229
        result = OnScreenChecker().check(cards)
        assert result["ok"] is False
        assert "above_safe_zone" in kinds(result)

    def test_below_safe_zone_by_bottom_edge_fails(self):
        cards = good_cards()
        cards[0]["y"] = 1400
        cards[0]["height"] = 41  # bottom = 1441
        result = OnScreenChecker().check(cards)
        assert "below_safe_zone" in kinds(result)

    def test_below_safe_zone_by_y_alone_fails(self):
        cards = good_cards()
        cards[0]["y"] = 1441
        cards[0].pop("height", None)
        assert "below_safe_zone" in kinds(OnScreenChecker().check(cards))

    def test_right_clear_zone_by_right_edge_fails(self):
        cards = good_cards()
        cards[0]["x"] = 800
        cards[0]["width"] = 51  # right = 851
        assert "right_clear_zone" in kinds(OnScreenChecker().check(cards))

    def test_right_clear_zone_by_x_alone_fails(self):
        cards = good_cards()
        cards[0]["x"] = 851
        cards[0].pop("width", None)
        assert "right_clear_zone" in kinds(OnScreenChecker().check(cards))

    def test_custom_safe_values(self):
        cards = [{"text": "OK", "x": 0, "y": 100, "frame": 1}]
        assert OnScreenChecker().check(cards)["ok"] is False
        assert OnScreenChecker(safe_top=100).check(cards)["ok"] is True


class TestHookFrame:
    def test_hook_not_at_frame_one_fails(self):
        cards = good_cards()
        cards[0]["frame"] = 2
        result = OnScreenChecker().check(cards)
        assert result["ok"] is False
        assert "hook_not_at_first_frame" in kinds(result)

    def test_hook_marked_by_role_is_checked_even_if_not_first(self):
        cards = good_cards()
        cards[0]["frame"] = 5
        cards[1]["role"] = "hook"
        cards[1]["frame"] = 2
        result = OnScreenChecker().check(cards)
        # role=hook のカードも frame 1 でなければならない
        assert "hook_not_at_first_frame" in kinds(result)

    def test_hook_start_seconds_zero_passes(self):
        cards = [{"text": "HI", "x": 10, "y": 300, "start_seconds": 0}]
        assert OnScreenChecker().check(cards)["ok"] is True

    def test_hook_start_seconds_nonzero_fails(self):
        cards = [{"text": "HI", "x": 10, "y": 300, "start_seconds": 0.5}]
        assert "hook_not_at_first_frame" in kinds(OnScreenChecker().check(cards))

    def test_missing_frame_info_fails_hook_check(self):
        cards = [{"text": "HI", "x": 10, "y": 300}]
        assert "hook_not_at_first_frame" in kinds(OnScreenChecker().check(cards))

    def test_no_cards_fails(self):
        result = OnScreenChecker().check([])
        assert result["ok"] is False
        assert "no_cards" in kinds(result)


class TestMultipleViolations:
    def test_all_violations_are_listed(self):
        cards = [
            {"text": "one two three four five six seven", "x": 900, "y": 10, "frame": 3}
        ]
        result = OnScreenChecker().check(cards)
        assert result["ok"] is False
        assert set(kinds(result)) >= {
            "too_many_words",
            "above_safe_zone",
            "right_clear_zone",
            "hook_not_at_first_frame",
        }


class TestCli:
    def _run(self, tmp_path, payload, *extra):
        path = tmp_path / "cards.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), *extra],
            capture_output=True,
            text=True,
        )

    def test_cli_pass_exits_0_and_prints_json(self, tmp_path):
        proc = self._run(tmp_path, {"cards": good_cards()})
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["ok"] is True

    def test_cli_violation_exits_1(self, tmp_path):
        bad = good_cards()
        bad[0]["text"] = "one two three four five six seven"
        proc = self._run(tmp_path, {"cards": bad})
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["ok"] is False

    def test_cli_bare_list_input_accepted(self, tmp_path):
        proc = self._run(tmp_path, good_cards())
        assert proc.returncode == 0

    def test_cli_max_words_flag(self, tmp_path):
        proc = self._run(tmp_path, {"cards": good_cards()}, "--max-words", "2")
        assert proc.returncode == 1
