"""follow_up_guard.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-dm/SKILL.md「Follow-ups」節と Issue #39（要ガード）。
- フォローアップは 2 回まで。それ以上は送信不可で、終了を出す
- 1 回目は +4 日、新しい内容を加える。"just bumping this" は禁止
- 2 回目（最後）は +10 日、終了を伝える close-the-loop
- 送信履歴（状態）を入力として判定し、上限到達時の試行は止める
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from follow_up_guard import FollowUpGuard  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "follow_up_guard.py"


class TestInitialState:
    def test_initial_count_zero_and_can_send(self):
        guard = FollowUpGuard()
        assert guard.follow_up_count() == 0
        assert guard.can_send() is True

    def test_first_follow_up_due_day_is_4(self):
        assert FollowUpGuard().next_due_day() == 4

    def test_first_follow_up_is_not_final(self):
        assert FollowUpGuard().is_next_final() is False


class TestRecording:
    def test_first_follow_up_allowed(self):
        guard = FollowUpGuard()
        result = guard.record_follow_up(day_offset=4, text="New data on this.")
        assert result["decision"] == "allow"
        assert result["follow_up_count"] == 1
        assert guard.can_send() is True

    def test_second_follow_up_due_day_is_10_and_is_final(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data on this.")
        assert guard.next_due_day() == 10
        assert guard.is_next_final() is True

    def test_second_follow_up_allowed(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data on this.")
        result = guard.record_follow_up(
            day_offset=10, text="I will stop here, thanks for reading."
        )
        assert result["decision"] == "allow"
        assert result["follow_up_count"] == 2

    def test_third_follow_up_is_stopped_and_not_counted(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data on this.")
        guard.record_follow_up(day_offset=10, text="Closing the loop here.")
        result = guard.record_follow_up(day_offset=14, text="One more try.")
        assert result["decision"] == "stop_limit_reached"
        assert result["follow_up_count"] == 2
        assert guard.follow_up_count() == 2
        assert guard.can_send() is False
        assert guard.next_due_day() is None

    def test_stop_result_says_to_stop(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data.")
        guard.record_follow_up(day_offset=10, text="Closing the loop.")
        result = guard.record_follow_up(day_offset=14, text="Again.")
        assert "stop" in result["message"].lower()


class TestScheduleGuard:
    def test_first_follow_up_before_day_4_is_blocked(self):
        guard = FollowUpGuard()
        result = guard.record_follow_up(day_offset=2, text="New data.")
        assert result["decision"] == "blocked_too_early"
        assert guard.follow_up_count() == 0

    def test_second_follow_up_before_day_10_is_blocked(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data.")
        result = guard.record_follow_up(day_offset=7, text="Closing the loop.")
        assert result["decision"] == "blocked_too_early"
        assert guard.follow_up_count() == 1

    def test_can_send_on_day(self):
        guard = FollowUpGuard()
        assert guard.can_send_on_day(3) is False
        assert guard.can_send_on_day(4) is True


class TestBannedPhrase:
    def test_just_bumping_this_is_blocked_and_not_counted(self):
        guard = FollowUpGuard()
        result = guard.record_follow_up(day_offset=5, text="Just bumping this.")
        assert result["decision"] == "blocked_banned_phrase"
        assert guard.follow_up_count() == 0


class TestCustomLimit:
    def test_max_follow_ups_1(self):
        guard = FollowUpGuard(max_follow_ups=1)
        guard.record_follow_up(day_offset=4, text="New data.")
        assert guard.can_send() is False
        result = guard.record_follow_up(day_offset=10, text="More.")
        assert result["decision"] == "stop_limit_reached"


class TestHistoryAndPersistence:
    def test_from_history_list(self):
        guard = FollowUpGuard.from_history([{"day_offset": 4}, {"day_offset": 10}])
        assert guard.follow_up_count() == 2
        assert guard.can_send() is False

    def test_dict_roundtrip(self):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data.")
        restored = FollowUpGuard.from_dict(guard.to_dict())
        assert restored.follow_up_count() == 1
        assert restored.next_due_day() == 10

    def test_save_load_roundtrip(self, tmp_path):
        guard = FollowUpGuard()
        guard.record_follow_up(day_offset=4, text="New data.")
        path = str(tmp_path / "state.json")
        guard.save(path)
        restored = FollowUpGuard.load(path)
        assert restored.follow_up_count() == 1
        assert restored.can_send() is True


def run_cli(state, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state", str(state), *args],
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_cli_check_initial(self, tmp_path):
        result = run_cli(tmp_path / "s.json", "check")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["can_send"] is True
        assert payload["follow_up_count"] == 0
        assert payload["next_due_day"] == 4

    def test_cli_send_flow_until_stop(self, tmp_path):
        state = tmp_path / "s.json"
        first = run_cli(state, "send", "--day-offset", "4", "--text", "New data.")
        assert first.returncode == 0
        assert json.loads(first.stdout)["decision"] == "allow"
        second = run_cli(
            state, "send", "--day-offset", "10", "--text", "Closing the loop."
        )
        assert second.returncode == 0
        third = run_cli(state, "send", "--day-offset", "14", "--text", "Again.")
        assert third.returncode == 1
        assert json.loads(third.stdout)["decision"] == "stop_limit_reached"
        check = run_cli(state, "check")
        assert json.loads(check.stdout)["can_send"] is False

    def test_cli_send_too_early_is_blocked(self, tmp_path):
        result = run_cli(
            tmp_path / "s.json", "send", "--day-offset", "1", "--text", "New data."
        )
        assert result.returncode == 1
        assert json.loads(result.stdout)["decision"] == "blocked_too_early"
