#!/usr/bin/env python3
"""
width_check.py - 列幅と日付書式の検査。

スキル spreadsheet_cutoff_prevention の「列幅の計算（フォント11px）」
節の判定をコード化したもの。各列について、必要幅以上であることと、
日付列の書式が EXPECTED_DATE_FORMAT の通りである場合に通過とする。

計算係数の既定値は sheet-writer tool 側の Measures（正本）と同じ値で
あり、二重定義にならないよう test_width_check.py が正本との整合を
担保する。計算の意味も正本（measures.needed_width_px）に合わせる:
必要幅 = ヘッダー（太字）と全データ行の最長値の文字幅の大きい方
+ 余白 PADDING_PX、切り上げ。

使い方
  python3 width_check.py sheet.json

入力 JSON:
  {"columns": [
    {"letter": "A", "header": "日付", "values": ["2026/10/30"],
     "width_px": 108, "is_date": true, "date_formats": ["yyyy/mm/dd"]}
  ]}

- values は表示される文字列（日付は yyyy/mm/dd の表示形）で数える
- date_formats はデータ行の各セルの数値書式。is_date の列だけ検査する

出力は {"ok": bool, "violations": [{"column", "kind", "expected",
"actual", "detail"}]} で、通過なら終了コード 0、違反があれば 1。
"""

import argparse
import json
import math
import sys
import unicodedata
from pathlib import Path

FULLWIDTH_PX = 11.5
HALFWIDTH_PX = 6.3
BOLD_FULLWIDTH_PX = 12.0
BOLD_HALFWIDTH_PX = 6.6
PADDING_PX = 20
EXPECTED_DATE_FORMAT = "yyyy/mm/dd"

_FULLWIDTH_KINDS = ("W", "F")


def _char_width(char, bold):
    if unicodedata.east_asian_width(char) in _FULLWIDTH_KINDS:
        return BOLD_FULLWIDTH_PX if bold else FULLWIDTH_PX
    return BOLD_HALFWIDTH_PX if bold else HALFWIDTH_PX


def text_width_px(text, bold=False):
    """表示文字列の幅（px）。改行は含めず1セグメント分を数える。"""
    return sum(_char_width(char, bold) for char in text)


def needed_width_px(header, values):
    """列の必要幅（px、切り上げ）。

    ヘッダーは太字として数え、全データ行の最長値との大きい方に
    余白を足す。複数行の値は最長セグメントで数える。
    """
    widest = 0.0
    for segment in (header or "").split("\n"):
        widest = max(widest, text_width_px(segment, bold=True))
    for value in values:
        for segment in str(value).split("\n"):
            widest = max(widest, text_width_px(segment))
    return math.ceil(widest + PADDING_PX)


class WidthChecker:
    """列幅メタデータとセル書式を入力に、幅不足と書式違反を一覧化する。"""

    def __init__(self, expected_date_format=EXPECTED_DATE_FORMAT):
        self.expected_date_format = expected_date_format

    def check(self, payload):
        violations = []
        for column in payload.get("columns") or []:
            violations.extend(self._check_column(column))
        return {"ok": not violations, "violations": violations}

    def _check_column(self, column):
        letter = column.get("letter", "")
        violations = []
        needed = needed_width_px(column.get("header", ""), column.get("values") or [])
        actual = column.get("width_px")
        if actual is None or actual < needed:
            violations.append(
                {
                    "column": letter,
                    "kind": "width",
                    "expected": needed,
                    "actual": actual,
                    "detail": (
                        f"列 {letter} の必要幅 {needed}px が"
                        f"現在幅 {actual}px を超過"
                    ),
                }
            )
        if column.get("is_date"):
            violations.extend(self._check_date_formats(letter, column))
        return violations

    def _check_date_formats(self, letter, column):
        violations = []
        for fmt in column.get("date_formats") or []:
            if fmt == self.expected_date_format:
                continue
            violations.append(
                {
                    "column": letter,
                    "kind": "date_format",
                    "expected": self.expected_date_format,
                    "actual": fmt if fmt is not None else "未設定",
                    "detail": (
                        f"列 {letter} の日付書式 {fmt or '未設定'} が"
                        f"指定 {self.expected_date_format} と異なる"
                    ),
                }
            )
        return violations


def main(argv=None):
    parser = argparse.ArgumentParser(description="列幅と日付書式の検査。")
    parser.add_argument("input", help="入力 JSON ファイル（- で標準入力）")
    parser.add_argument("--date-format", default=None)
    args = parser.parse_args(argv)

    if args.input == "-":
        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))

    checker = WidthChecker(
        expected_date_format=args.date_format or EXPECTED_DATE_FORMAT
    )
    result = checker.check(payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
