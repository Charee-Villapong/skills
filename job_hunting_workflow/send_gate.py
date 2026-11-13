#!/usr/bin/env python3
"""
send_gate.py - 送信前の承認と体裁チェックのゲート。

スキル job_hunting_workflow の「大原則」「手順」節の判定をコード化した
もの。送信要求について、次の記録がすべてそろう場合だけ送信可とする。

- 承認記録: 本人が承認済みであること。承認時に文面が記録されている
  場合は、送信要求の文面と一致すること
- 体裁チェック記録: 提示前（before_present）と送信直前（before_send）
  の2回について、日本語用3スキル REQUIRED_FORMAT_SKILLS の
  チェックがすべて合格していること
- カレンダー競合確認: 日程候補を含む送信
  （send_request.requires_calendar_check が true）では、競合確認が
  済み、未解決の競合がないこと

欠けた記録がある送信は止め、不足項目を一覧で返す。実データには
触らず、入力 JSON の記録だけを見る。

使い方
  python3 send_gate.py gate.json

入力 JSON:
  {
    "send_request": {"text": "...", "requires_calendar_check": false},
    "approval": {"approved": true, "text": "..."} または null,
    "format_checks": [{"stage": "...", "skill": "...", "passed": true}],
    "calendar_check": {"checked": true, "conflicts": []} または null
  }

出力は {"allowed": bool, "missing": [不足項目]} で、送信可なら
終了コード 0、不可なら 1 を返す。
"""

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FORMAT_SKILLS = (
    "natural-japanese",
    "natural-japanese-writing",
    "stop-ai-slop-jp",
)
REQUIRED_FORMAT_STAGES = ("before_present", "before_send")


class SendGate:
    """送信に必要な記録がそろっているかを判定するゲート。"""

    def __init__(
        self,
        required_skills=REQUIRED_FORMAT_SKILLS,
        required_stages=REQUIRED_FORMAT_STAGES,
    ):
        self.required_skills = tuple(required_skills)
        self.required_stages = tuple(required_stages)

    def validate(self, payload):
        """入力 dict を判定し、{"allowed", "missing"} を返す。"""
        missing = []
        request = payload.get("send_request") or {}
        missing.extend(self._check_approval(payload.get("approval"), request))
        missing.extend(self._check_format(payload.get("format_checks") or []))
        missing.extend(self._check_calendar(request, payload.get("calendar_check")))
        return {"allowed": not missing, "missing": missing}

    def _check_approval(self, approval, request):
        if not approval or approval.get("approved") is not True:
            return ["approval"]
        approved_text = approval.get("text")
        if approved_text is not None and approved_text != request.get("text"):
            return ["approval_text_mismatch"]
        return []

    def _check_format(self, format_checks):
        passed = {
            (check.get("stage"), check.get("skill"))
            for check in format_checks
            if check.get("passed") is True
        }
        missing = []
        for stage in self.required_stages:
            for skill in self.required_skills:
                if (stage, skill) not in passed:
                    missing.append(f"format_check:{stage}:{skill}")
        return missing

    def _check_calendar(self, request, calendar_check):
        if request.get("requires_calendar_check") is not True:
            return []
        if not calendar_check or calendar_check.get("checked") is not True:
            return ["calendar_check"]
        if calendar_check.get("conflicts"):
            return ["calendar_conflict"]
        return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="送信前の承認と体裁チェックのゲート。")
    parser.add_argument("input", help="入力 JSON ファイル（- で標準入力）")
    args = parser.parse_args(argv)

    if args.input == "-":
        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))

    result = SendGate().validate(payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
