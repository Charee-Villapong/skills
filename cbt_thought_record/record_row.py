#!/usr/bin/env python3
"""
record_row.py - 思考記録の保存行を保存前に検証する。

スキル cbt_thought_record の「Record and review」節の判定をコード化した
もの。保存予定の1行について、次の3点を満たす場合だけ保存可とする。

- 列の揃い: 列は COLUMNS の13列ちょうどであること
- 名称付き書式: 気分（前）・気分（後）は「感情の名称＋パーセント」で
  書くこと（例: 不安 80%）。1セルに複数の気分がある場合は
  「、」区切りで並べ、各要素が同じ書式であること
- 範囲内: 気分の強さは MOOD_MIN_PERCENT 〜 MOOD_MAX_PERCENT
  （既定 0〜100、手順ステップ2・7の定義）の範囲内であること

天気・気温・湿度は確認できない場合は空欄が正であり、検証対象にしない。

使い方
  python3 record_row.py row.json

入力 JSON は {"row": [13要素の配列]} または
{"record": {列名: 値}} のどちらか。
出力は {"ok": bool, "errors": [{"column", "kind", "detail"}]} で、
保存可なら終了コード 0、不可なら 1 を返す。
"""

import argparse
import json
import re
import sys
from pathlib import Path

COLUMNS = [
    "日付",
    "曜日",
    "天気",
    "気温",
    "湿度",
    "状況",
    "気分（前）",
    "自動思考",
    "認知のゆがみ",
    "根拠",
    "反証・別の視点",
    "バランス思考",
    "気分（後）",
]

MOOD_COLUMNS = ("気分（前）", "気分（後）")
MOOD_MIN_PERCENT = 0.0
MOOD_MAX_PERCENT = 100.0

# 「名称 数値%」の1要素。名称と数値の間は空白（半角・全角）1つ以上。
_MOOD_ENTRY = re.compile(r"^(?P<name>\S.*?)\s+(?P<value>-?\d+(?:\.\d+)?)%$")
_MOOD_SEPARATORS = re.compile(r"[、,／/\n]")


class RecordRowValidator:
    """保存予定の思考記録1行の書式を検証する。"""

    def __init__(
        self,
        mood_min_percent=MOOD_MIN_PERCENT,
        mood_max_percent=MOOD_MAX_PERCENT,
    ):
        self.mood_min_percent = mood_min_percent
        self.mood_max_percent = mood_max_percent

    def validate_record(self, record):
        """列名→値の辞書を COLUMNS の順に直してから検証する。"""
        missing = [name for name in COLUMNS if name not in record]
        if missing:
            return {
                "ok": False,
                "errors": [
                    {
                        "column": name,
                        "kind": "column_count",
                        "detail": f"列 {name} が欠けている",
                    }
                    for name in missing
                ],
            }
        row = [record[name] for name in COLUMNS]
        return self.validate_row(row)

    def validate_row(self, row):
        """13列の配列を検証し、{"ok", "errors"} を返す。"""
        errors = []
        if len(row) != len(COLUMNS):
            errors.append(
                {
                    "column": "",
                    "kind": "column_count",
                    "detail": (
                        f"列数が {len(row)} で、必要列数 {len(COLUMNS)} と異なる"
                    ),
                }
            )
            return {"ok": False, "errors": errors}
        for column in MOOD_COLUMNS:
            value = row[COLUMNS.index(column)]
            errors.extend(self._validate_mood(column, value))
        return {"ok": not errors, "errors": errors}

    def _validate_mood(self, column, value):
        errors = []
        text = "" if value is None else str(value)
        if text.strip() == "":
            errors.append(
                {
                    "column": column,
                    "kind": "mood_format",
                    "detail": f"{column} が空である",
                }
            )
            return errors
        for entry in _MOOD_SEPARATORS.split(text):
            entry = entry.strip()
            if entry == "":
                continue
            match = _MOOD_ENTRY.match(entry)
            if match is None:
                errors.append(
                    {
                        "column": column,
                        "kind": "mood_format",
                        "detail": (
                            f"{column} の「{entry}」が" "「名称 数値%」の書式でない"
                        ),
                    }
                )
                continue
            number = float(match.group("value"))
            if not self.mood_min_percent <= number <= self.mood_max_percent:
                errors.append(
                    {
                        "column": column,
                        "kind": "mood_range",
                        "detail": (
                            f"{column} の値 {match.group('value')}% が"
                            f"範囲 {self.mood_min_percent:g}〜"
                            f"{self.mood_max_percent:g}% の外である"
                        ),
                    }
                )
        return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="思考記録の保存行の書式を検証する。")
    parser.add_argument("input", help="入力 JSON ファイル（- で標準入力）")
    parser.add_argument("--mood-min", type=float, default=None)
    parser.add_argument("--mood-max", type=float, default=None)
    args = parser.parse_args(argv)

    if args.input == "-":
        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))

    validator = RecordRowValidator(
        mood_min_percent=(
            args.mood_min if args.mood_min is not None else MOOD_MIN_PERCENT
        ),
        mood_max_percent=(
            args.mood_max if args.mood_max is not None else MOOD_MAX_PERCENT
        ),
    )
    if "record" in payload:
        result = validator.validate_record(payload["record"])
    else:
        result = validator.validate_row(payload["row"])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
