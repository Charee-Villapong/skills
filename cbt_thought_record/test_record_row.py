"""record_row.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル cbt_thought_record の「Record and review」節と
Issue #36。

- 保存は1記録1行、列は 日付, 曜日, 天気, 気温, 湿度, 状況, 気分（前）,
  自動思考, 認知のゆがみ, 根拠, 反証・別の視点, バランス思考, 気分（後）
  の13列で揃っていること
- 気分は「感情の名称＋パーセント」で書く（例: 不安 80%）
- 気分の強さは 0〜100% の範囲内であること（手順ステップ2・7の定義）
- 不備があれば保存不可とし、不備箇所を一覧で出すこと

実装（record_row.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_record_row.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_row import COLUMNS, RecordRowValidator  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "record_row.py"

VALID_ROW = [
    "2026/11/14",
    "土",
    "晴れ",
    "18℃",
    "55%",
    "会議で意見を言えなかった",
    "不安 80%",
    "自分はダメだと思った",
    "レッテル貼り",
    "発言の機会は他にもあった",
    "準備不足が原因で能力の問題ではない",
    "準備すれば発言できる",
    "不安 40%",
]


def kinds(result):
    return [e["kind"] for e in result["errors"]]


class TestColumns:
    def test_columns_match_skill_order(self):
        assert COLUMNS == [
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


class TestValidRow:
    def test_valid_row_passes(self):
        result = RecordRowValidator().validate_row(VALID_ROW)
        assert result["ok"] is True
        assert result["errors"] == []

    def test_weather_columns_may_be_blank(self):
        row = list(VALID_ROW)
        row[2] = row[3] = row[4] = ""
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is True

    def test_mood_boundaries_zero_and_hundred_pass(self):
        row = list(VALID_ROW)
        row[6] = "不安 0%"
        row[12] = "落胆 100%"
        assert RecordRowValidator().validate_row(row)["ok"] is True

    def test_multiple_moods_in_one_cell_pass(self):
        row = list(VALID_ROW)
        row[6] = "不安 80%、焦り 60%"
        assert RecordRowValidator().validate_row(row)["ok"] is True


class TestColumnCount:
    def test_too_few_columns_fail(self):
        result = RecordRowValidator().validate_row(VALID_ROW[:-1])
        assert result["ok"] is False
        assert "column_count" in kinds(result)

    def test_too_many_columns_fail(self):
        result = RecordRowValidator().validate_row(VALID_ROW + ["余分"])
        assert result["ok"] is False
        assert "column_count" in kinds(result)


class TestMoodFormat:
    def test_mood_without_percentage_fails(self):
        row = list(VALID_ROW)
        row[6] = "不安"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert "mood_format" in kinds(result)

    def test_mood_without_name_fails(self):
        row = list(VALID_ROW)
        row[12] = "40%"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert "mood_format" in kinds(result)

    def test_mood_missing_space_between_name_and_value_fails(self):
        row = list(VALID_ROW)
        row[6] = "不安80%"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert "mood_format" in kinds(result)

    def test_empty_mood_fails(self):
        row = list(VALID_ROW)
        row[6] = ""
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert result["errors"] != []

    def test_one_bad_entry_among_multiple_fails(self):
        row = list(VALID_ROW)
        row[6] = "不安 80%、焦り"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert "mood_format" in kinds(result)

    def test_error_names_the_mood_column(self):
        row = list(VALID_ROW)
        row[12] = "40"
        result = RecordRowValidator().validate_row(row)
        assert any(e["column"] == "気分（後）" for e in result["errors"])


class TestMoodRange:
    def test_mood_over_100_fails(self):
        row = list(VALID_ROW)
        row[6] = "不安 120%"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert "mood_range" in kinds(result)

    def test_negative_mood_fails(self):
        row = list(VALID_ROW)
        row[12] = "不安 -5%"
        result = RecordRowValidator().validate_row(row)
        assert result["ok"] is False
        assert result["errors"] != []


class TestRecordDictInput:
    def test_record_dict_in_any_key_order_passes(self):
        record = dict(zip(COLUMNS, VALID_ROW))
        shuffled = dict(reversed(list(record.items())))
        result = RecordRowValidator().validate_record(shuffled)
        assert result["ok"] is True

    def test_record_dict_missing_column_fails(self):
        record = dict(zip(COLUMNS, VALID_ROW))
        del record["気分（後）"]
        result = RecordRowValidator().validate_record(record)
        assert result["ok"] is False
        assert "column_count" in kinds(result)


class TestCli:
    def run_cli(self, tmp_path, payload):
        path = tmp_path / "row.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
        )

    def test_cli_valid_row_exits_zero(self, tmp_path):
        result = self.run_cli(tmp_path, {"row": VALID_ROW})
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_invalid_row_exits_one_and_lists_errors(self, tmp_path):
        row = list(VALID_ROW)
        row[6] = "不安 120%"
        result = self.run_cli(tmp_path, {"row": row})
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["errors"] != []

    def test_cli_accepts_record_object(self, tmp_path):
        record = dict(zip(COLUMNS, VALID_ROW))
        result = self.run_cli(tmp_path, {"record": record})
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True
