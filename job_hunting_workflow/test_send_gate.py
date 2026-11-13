"""send_gate.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル job_hunting_workflow の「大原則」「手順」節と Issue #47。

- 送信は必ず本人の承認後（承認記録がなければ送らない）
- 体裁チェックは、下書きを本人に見せる前と送信する直前の2回、
  日本語用3スキル（natural-japanese / natural-japanese-writing /
  stop-ai-slop-jp）で必須であり、省略しない
- 日程候補を含む送信は、Googleカレンダーの競合確認が済んでいて
  競合がない場合だけ送れる
- 欠けた記録がある送信は止め、不足項目を出す

実データには触らず、フィクスチャだけで完結させる。

実装（send_gate.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_send_gate.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from send_gate import (  # noqa: E402
    REQUIRED_FORMAT_SKILLS,
    REQUIRED_FORMAT_STAGES,
    SendGate,
)

SCRIPT = Path(__file__).resolve().parent / "send_gate.py"


def full_checks():
    return [
        {"stage": stage, "skill": skill, "passed": True}
        for stage in REQUIRED_FORMAT_STAGES
        for skill in REQUIRED_FORMAT_SKILLS
    ]


def valid_payload():
    return {
        "send_request": {
            "text": "面談の日程について返信する",
            "requires_calendar_check": False,
        },
        "approval": {"approved": True},
        "format_checks": full_checks(),
        "calendar_check": None,
    }


class TestConstants:
    def test_required_skills_are_the_three_japanese_skills(self):
        assert REQUIRED_FORMAT_SKILLS == (
            "natural-japanese",
            "natural-japanese-writing",
            "stop-ai-slop-jp",
        )

    def test_required_stages_are_before_present_and_before_send(self):
        assert REQUIRED_FORMAT_STAGES == ("before_present", "before_send")


class TestApproval:
    def test_all_records_present_allows_send(self):
        result = SendGate().validate(valid_payload())
        assert result["allowed"] is True
        assert result["missing"] == []

    def test_missing_approval_blocks(self):
        payload = valid_payload()
        payload["approval"] = None
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "approval" in result["missing"]

    def test_approval_flag_false_blocks(self):
        payload = valid_payload()
        payload["approval"] = {"approved": False}
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "approval" in result["missing"]

    def test_approval_for_different_text_blocks(self):
        payload = valid_payload()
        payload["approval"] = {"approved": True, "text": "別の文面"}
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "approval_text_mismatch" in result["missing"]


class TestFormatChecks:
    def test_missing_one_skill_at_before_send_blocks(self):
        payload = valid_payload()
        payload["format_checks"] = [
            c
            for c in payload["format_checks"]
            if not (c["stage"] == "before_send" and c["skill"] == "stop-ai-slop-jp")
        ]
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "format_check:before_send:stop-ai-slop-jp" in result["missing"]

    def test_missing_before_present_stage_blocks(self):
        payload = valid_payload()
        payload["format_checks"] = [
            c for c in payload["format_checks"] if c["stage"] != "before_present"
        ]
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert any(
            m.startswith("format_check:before_present:") for m in result["missing"]
        )

    def test_failed_check_counts_as_missing(self):
        payload = valid_payload()
        for check in payload["format_checks"]:
            if (
                check["stage"] == "before_present"
                and check["skill"] == "natural-japanese"
            ):
                check["passed"] = False
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "format_check:before_present:natural-japanese" in result["missing"]

    def test_no_format_checks_at_all_lists_all_six(self):
        payload = valid_payload()
        payload["format_checks"] = []
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        format_missing = [m for m in result["missing"] if m.startswith("format_check:")]
        assert len(format_missing) == 6


class TestCalendarCheck:
    def test_schedule_send_without_calendar_check_blocks(self):
        payload = valid_payload()
        payload["send_request"]["requires_calendar_check"] = True
        payload["calendar_check"] = None
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "calendar_check" in result["missing"]

    def test_schedule_send_with_conflict_blocks(self):
        payload = valid_payload()
        payload["send_request"]["requires_calendar_check"] = True
        payload["calendar_check"] = {
            "checked": True,
            "conflicts": ["同時間帯に家族行事がある"],
        }
        result = SendGate().validate(payload)
        assert result["allowed"] is False
        assert "calendar_conflict" in result["missing"]

    def test_schedule_send_with_clean_check_allows(self):
        payload = valid_payload()
        payload["send_request"]["requires_calendar_check"] = True
        payload["calendar_check"] = {"checked": True, "conflicts": []}
        result = SendGate().validate(payload)
        assert result["allowed"] is True

    def test_plain_send_needs_no_calendar_check(self):
        payload = valid_payload()
        assert payload["send_request"]["requires_calendar_check"] is False
        assert SendGate().validate(payload)["allowed"] is True


class TestCli:
    def run_cli(self, tmp_path, payload):
        path = tmp_path / "gate.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
        )

    def test_cli_allowed_exits_zero(self, tmp_path):
        result = self.run_cli(tmp_path, valid_payload())
        assert result.returncode == 0
        assert json.loads(result.stdout)["allowed"] is True

    def test_cli_blocked_exits_one_and_lists_missing(self, tmp_path):
        payload = valid_payload()
        payload["approval"] = None
        payload["format_checks"] = []
        result = self.run_cli(tmp_path, payload)
        assert result.returncode == 1
        body = json.loads(result.stdout)
        assert body["allowed"] is False
        assert "approval" in body["missing"]
        assert len(body["missing"]) >= 2
