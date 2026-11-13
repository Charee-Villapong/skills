"""story_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル ig-story の「Rules」節と「The daily shape」節。

- 1 日のフレームは 3〜7 枠
- テキストは安全領域の中だけ。1080x1920 で y=250 より上と
  y=1600 より下には置かない（ig-reel の安全領域とは別の値）
- ask（Poll・質問箱・クイズ・リンクのステッカー）は 4 枠目に置く。
  7 枠目ではない。ask のステッカーは 1 つだけ
- 1 枠目には顔か手が写っている（指定がある場合に検査）
- フレーム寸法は 1080x1920（指定がある場合に検査）

実装（story_check.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_story_check.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from story_check import StoryChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "story_check.py"


def make_frame(texts=None, **extra):
    frame = {}
    if texts is not None:
        frame["texts"] = [{"text": text, "y": y} for text, y in texts]
    frame.update(extra)
    return frame


def valid_sequence():
    """仕様を満たす 5 枠（SKILL.md の出力例が土台）。"""
    return {
        "width": 1080,
        "height": 1920,
        "frames": [
            make_frame(
                [("Third refund request this year. Same reason.", 500)],
                kind="open",
                has_face_or_hand=True,
            ),
            make_frame(
                [("the clause, highlighted", 700)],
                kind="middle",
            ),
            make_frame(
                [("Approval is a feeling. Delivery is a date.", 700)],
                kind="middle",
            ),
            make_frame(
                [("Have you been burned by a late approval?", 800)],
                kind="ask",
                sticker="poll",
            ),
            make_frame(
                [("Reply and I will send you the clause.", 800)],
                kind="close",
            ),
        ],
    }


def codes(result):
    return [v["code"] for v in result["violations"]]


def check(sequence, **kwargs):
    return StoryChecker(**kwargs).check(sequence)


# ---------------------------------------------------------------------------
# 正常系
# ---------------------------------------------------------------------------


class TestValidSequence:
    def test_valid_sequence_passes(self):
        result = check(valid_sequence())
        assert result["ok"] is True
        assert result["violations"] == []
        assert result["frame_count"] == 5

    def test_three_frames_passes(self):
        seq = valid_sequence()
        seq["frames"] = seq["frames"][:2] + seq["frames"][3:4] + seq["frames"][4:]
        # 3 枠にすると ask が 3 枠目になるため、ask のない構成で確認する
        seq["frames"] = [
            make_frame([("today", 500)], kind="open", has_face_or_hand=True),
            make_frame([("the process", 700)], kind="middle"),
            make_frame([("the outcome", 800)], kind="close"),
        ]
        assert check(seq)["ok"] is True

    def test_seven_frames_without_ask_passes(self):
        seq = valid_sequence()
        seq["frames"] = [
            make_frame([("today", 500)], kind="open", has_face_or_hand=True),
            make_frame([("one", 700)], kind="middle"),
            make_frame([("two", 700)], kind="middle"),
            make_frame([("three", 700)], kind="middle"),
            make_frame([("four", 700)], kind="middle"),
            make_frame([("five", 700)], kind="middle"),
            make_frame([("the outcome", 800)], kind="close"),
        ]
        assert check(seq)["ok"] is True

    def test_sequence_without_dimensions_passes(self):
        seq = valid_sequence()
        del seq["width"]
        del seq["height"]
        assert check(seq)["ok"] is True

    def test_text_at_safe_zone_edges_passes(self):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [{"text": "top edge", "y": 250}]
        seq["frames"][2]["texts"] = [{"text": "bottom edge", "y": 1600}]
        assert check(seq)["ok"] is True


# ---------------------------------------------------------------------------
# フレーム数
# ---------------------------------------------------------------------------


class TestFrameCount:
    def test_two_frames_is_violation(self):
        seq = valid_sequence()
        seq["frames"] = [
            make_frame([("today", 500)], kind="open", has_face_or_hand=True),
            make_frame([("the outcome", 800)], kind="close"),
        ]
        result = check(seq)
        assert result["ok"] is False
        assert "frame_count" in codes(result)

    def test_eight_frames_is_violation(self):
        seq = valid_sequence()
        extra = make_frame([("more", 700)], kind="middle")
        seq["frames"] = seq["frames"][:3] + [extra] * 3 + seq["frames"][3:]
        assert len(seq["frames"]) == 8
        result = check(seq)
        assert result["ok"] is False
        assert "frame_count" in codes(result)

    def test_empty_sequence_is_violation(self):
        result = check({"frames": []})
        assert result["ok"] is False
        assert "frame_count" in codes(result)
        assert result["frame_count"] == 0


# ---------------------------------------------------------------------------
# 安全領域
# ---------------------------------------------------------------------------


class TestSafeZone:
    def test_text_above_safe_zone_is_violation(self):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [{"text": "too high", "y": 249}]
        result = check(seq)
        assert result["ok"] is False
        assert "text_above_safe_zone" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "text_above_safe_zone"
        ]
        assert violation[0]["frame"] == 2

    def test_text_below_safe_zone_is_violation(self):
        seq = valid_sequence()
        seq["frames"][2]["texts"] = [{"text": "too low", "y": 1601}]
        result = check(seq)
        assert result["ok"] is False
        assert "text_below_safe_zone" in codes(result)
        violation = [
            v for v in result["violations"] if v["code"] == "text_below_safe_zone"
        ]
        assert violation[0]["frame"] == 3

    def test_text_bottom_edge_below_safe_zone_is_violation(self):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [
            {"text": "starts inside, ends below", "y": 1500, "y_bottom": 1700}
        ]
        result = check(seq)
        assert "text_below_safe_zone" in codes(result)

    def test_frame_level_text_y_is_checked(self):
        seq = valid_sequence()
        seq["frames"][1] = {"kind": "middle", "text_y": 100}
        result = check(seq)
        assert "text_above_safe_zone" in codes(result)

    def test_every_bad_text_is_listed(self):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [{"text": "high", "y": 10}]
        seq["frames"][4]["texts"] = [{"text": "low", "y": 1900}]
        result = check(seq)
        assert "text_above_safe_zone" in codes(result)
        assert "text_below_safe_zone" in codes(result)
        assert len(result["violations"]) >= 2


# ---------------------------------------------------------------------------
# ask の位置
# ---------------------------------------------------------------------------


class TestAskPosition:
    def test_poll_at_frame_four_passes(self):
        assert check(valid_sequence())["ok"] is True

    def test_poll_at_frame_seven_is_violation(self):
        seq = valid_sequence()
        seq["frames"] = [
            make_frame([("today", 500)], kind="open", has_face_or_hand=True),
            make_frame([("one", 700)], kind="middle"),
            make_frame([("two", 700)], kind="middle"),
            make_frame([("three", 700)], kind="middle"),
            make_frame([("four", 700)], kind="middle"),
            make_frame([("five", 700)], kind="middle"),
            make_frame([("Have you been burned?", 800)], kind="ask", sticker="poll"),
        ]
        result = check(seq)
        assert result["ok"] is False
        assert "ask_position" in codes(result)
        violation = [v for v in result["violations"] if v["code"] == "ask_position"]
        assert violation[0]["frame"] == 7

    def test_question_box_at_frame_two_is_violation(self):
        seq = valid_sequence()
        seq["frames"][1]["sticker"] = "question_box"
        seq["frames"][3]["sticker"] = None
        seq["frames"][3]["kind"] = "middle"
        result = check(seq)
        assert "ask_position" in codes(result)

    def test_quiz_and_link_are_also_asks(self):
        for sticker in ("quiz", "link"):
            seq = valid_sequence()
            seq["frames"][3]["sticker"] = sticker
            assert check(seq)["ok"] is True
            seq["frames"][3]["sticker"] = None
            seq["frames"][3]["kind"] = "middle"
            seq["frames"][4]["sticker"] = sticker
            seq["frames"][4]["kind"] = "ask"
            assert "ask_position" in codes(check(seq))

    def test_slider_is_not_an_ask(self):
        seq = valid_sequence()
        seq["frames"][3]["sticker"] = None
        seq["frames"][3]["kind"] = "middle"
        seq["frames"][4]["sticker"] = "slider"
        assert "ask_position" not in codes(check(seq))

    def test_sticker_name_variants_are_recognised(self):
        for sticker in ("Question Box", "question box", "QUESTION_BOX"):
            seq = valid_sequence()
            seq["frames"][3]["sticker"] = sticker
            assert check(seq)["ok"] is True, sticker

    def test_ask_kind_without_sticker_is_checked(self):
        seq = valid_sequence()
        seq["frames"][3]["sticker"] = None
        seq["frames"][3]["kind"] = "middle"
        seq["frames"][4]["kind"] = "ask"
        result = check(seq)
        assert "ask_position" in codes(result)

    def test_ask_with_two_stickers_is_violation(self):
        seq = valid_sequence()
        seq["frames"][3]["stickers"] = ["poll", "link"]
        del seq["frames"][3]["sticker"]
        result = check(seq)
        assert result["ok"] is False
        assert "ask_sticker_count" in codes(result)


# ---------------------------------------------------------------------------
# 1 枠目
# ---------------------------------------------------------------------------


class TestFirstFrame:
    def test_first_frame_without_face_or_hand_is_violation(self):
        seq = valid_sequence()
        seq["frames"][0]["has_face_or_hand"] = False
        result = check(seq)
        assert result["ok"] is False
        assert "first_frame_face" in codes(result)
        violation = [v for v in result["violations"] if v["code"] == "first_frame_face"]
        assert violation[0]["frame"] == 1

    def test_first_frame_unspecified_is_not_a_violation(self):
        seq = valid_sequence()
        del seq["frames"][0]["has_face_or_hand"]
        assert "first_frame_face" not in codes(check(seq))


# ---------------------------------------------------------------------------
# 寸法
# ---------------------------------------------------------------------------


class TestDimensions:
    def test_wrong_sequence_dimensions_is_violation(self):
        seq = valid_sequence()
        seq["height"] = 1350
        result = check(seq)
        assert result["ok"] is False
        assert "dimensions" in codes(result)

    def test_wrong_frame_dimensions_is_violation_with_frame_number(self):
        seq = valid_sequence()
        seq["frames"][2]["width"] = 1080
        seq["frames"][2]["height"] = 1080
        result = check(seq)
        assert "dimensions" in codes(result)
        violation = [v for v in result["violations"] if v["code"] == "dimensions"]
        assert any(v["frame"] == 3 for v in violation)


# ---------------------------------------------------------------------------
# しきい値の変数化
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_custom_safe_top(self):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [{"text": "high", "y": 200}]
        assert "text_above_safe_zone" in codes(check(seq))
        assert "text_above_safe_zone" not in codes(check(seq, safe_top=200))

    def test_custom_ask_position(self):
        seq = valid_sequence()
        assert "ask_position" in codes(check(seq, ask_position=5))

    def test_custom_max_frames_allows_eight(self):
        seq = valid_sequence()
        extra = make_frame([("more", 700)], kind="middle")
        seq["frames"] = seq["frames"][:3] + [extra] * 3 + seq["frames"][3:]
        assert len(seq["frames"]) == 8
        assert "frame_count" not in codes(check(seq, max_frames=9))


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
    def test_cli_valid_sequence_exits_zero(self, tmp_path):
        path = tmp_path / "story.json"
        path.write_text(json.dumps(valid_sequence()), encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["violations"] == []

    def test_cli_invalid_sequence_exits_one_and_lists_violations(self, tmp_path):
        seq = valid_sequence()
        seq["frames"][0]["texts"] = [{"text": "too high", "y": 100}]
        path = tmp_path / "story.json"
        path.write_text(json.dumps(seq), encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "text_above_safe_zone" in [v["code"] for v in payload["violations"]]

    def test_cli_reads_stdin_with_dash(self):
        result = run_cli("-", stdin_text=json.dumps(valid_sequence()))
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_safe_top_flag_changes_result(self, tmp_path):
        seq = valid_sequence()
        seq["frames"][1]["texts"] = [{"text": "high", "y": 200}]
        path = tmp_path / "story.json"
        path.write_text(json.dumps(seq), encoding="utf-8")
        assert run_cli(str(path)).returncode == 1
        assert run_cli(str(path), "--safe-top", "200").returncode == 0

    def test_cli_malformed_json_exits_two(self, tmp_path):
        path = tmp_path / "story.json"
        path.write_text("{not json", encoding="utf-8")
        result = run_cli(str(path))
        assert result.returncode == 2

    def test_cli_missing_file_exits_two(self, tmp_path):
        result = run_cli(str(tmp_path / "nope.json"))
        assert result.returncode == 2
