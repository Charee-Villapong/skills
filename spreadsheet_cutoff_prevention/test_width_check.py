"""width_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル spreadsheet_cutoff_prevention の
「列幅の計算（フォント11px）」節と Issue #48、および「新規行を追加
したら」節の日付書式の規定。

- 全角1文字 ≒ 11.5px、半角1文字 ≒ 6.3px。太字は全角 12px、半角 6.6px
- セルの余白として +20px を必ず足す
- 必要幅 = 文字幅の合計 + 20px。割り切れない・際どい場合は切り上げる
- 列幅はヘッダー（太字）と全データ行の最長値の大きい方に合わせる
- 計算の対象は表示される文字列（日付は yyyy/mm/dd の表示形で数える）
- 日付書式は yyyy/mm/dd（yyyy/m/d の混入禁止）
- 係数の既定値は sheet-writer tool 側の Measures（正本）と整合すること

実装（width_check.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_width_check.py -v
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from width_check import (  # noqa: E402
    BOLD_FULLWIDTH_PX,
    BOLD_HALFWIDTH_PX,
    EXPECTED_DATE_FORMAT,
    FULLWIDTH_PX,
    HALFWIDTH_PX,
    PADDING_PX,
    WidthChecker,
    needed_width_px,
    text_width_px,
)

SCRIPT = Path(__file__).resolve().parent / "width_check.py"


class TestSheetWriterSync:
    def test_defaults_match_sheet_writer_measures(self):
        config_path = (
            Path(__file__).resolve().parents[2]
            / "sheet-writer"
            / "src"
            / "sheet_writer"
            / "config.py"
        )
        if config_path.exists():
            spec = importlib.util.spec_from_file_location(
                "sheet_writer_config", config_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            measures = module.Measures()
            assert FULLWIDTH_PX == measures.fullwidth_px
            assert HALFWIDTH_PX == measures.halfwidth_px
            assert BOLD_FULLWIDTH_PX == measures.bold_fullwidth_px
            assert BOLD_HALFWIDTH_PX == measures.bold_halfwidth_px
            assert PADDING_PX == measures.padding_px
        else:
            # sheet-writer のチェックアウトが無い環境では SKILL.md の値で担保
            assert (FULLWIDTH_PX, HALFWIDTH_PX) == (11.5, 6.3)
            assert (BOLD_FULLWIDTH_PX, BOLD_HALFWIDTH_PX) == (12.0, 6.6)
            assert PADDING_PX == 20


class TestTextWidth:
    def test_halfwidth_chars(self):
        assert text_width_px("2026/10/30") == 10 * 6.3

    def test_fullwidth_chars(self):
        assert text_width_px("日付") == 2 * 11.5

    def test_bold_widths(self):
        assert text_width_px("日付", bold=True) == 2 * 12.0
        assert text_width_px("abc", bold=True) == 3 * 6.6

    def test_mixed_period_string(self):
        # 期間列の表示形: 半角20文字 + 全角「～」1文字
        assert text_width_px("2026/09/20～2026/10/19") == 20 * 6.3 + 11.5


class TestNeededWidth:
    def test_date_column_needed_width(self):
        # 表示形 10文字 × 6.3 + 余白 20 = 83
        assert needed_width_px("日付", ["2026/10/30"]) == 83

    def test_fractional_width_is_ceiled(self):
        # 全角1文字 11.5 + 20 = 31.5 → 切り上げて 32
        assert needed_width_px("", ["あ"]) == 32

    def test_header_wins_when_longer(self):
        assert needed_width_px("使用月分ヘッダー", ["2026/10"]) == (8 * 12.0 + 20)

    def test_longest_data_value_wins(self):
        assert needed_width_px("期間", ["2026/09/20～2026/10/19", "短い"]) == 158

    def test_multiline_value_uses_longest_segment(self):
        # 最長セグメント 3文字 × 11.5 + 20 = 54.5 → 切り上げて 55
        assert needed_width_px("", ["あ\nあああ"]) == 55


class TestWidthViolations:
    def check(self, columns):
        return WidthChecker().check({"columns": columns})

    def test_sufficient_width_passes(self):
        result = self.check(
            [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 108,
                }
            ]
        )
        assert result["ok"] is True
        assert result["violations"] == []

    def test_exact_needed_width_passes(self):
        result = self.check(
            [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 83,
                }
            ]
        )
        assert result["ok"] is True

    def test_narrow_column_is_listed(self):
        result = self.check(
            [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 82,
                }
            ]
        )
        assert result["ok"] is False
        violation = result["violations"][0]
        assert violation["kind"] == "width"
        assert violation["column"] == "A"
        assert violation["expected"] == 83
        assert violation["actual"] == 82

    def test_multiple_columns_report_each_violation(self):
        result = self.check(
            [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 50,
                },
                {
                    "letter": "B",
                    "header": "期間",
                    "values": ["2026/09/20～2026/10/19"],
                    "width_px": 100,
                },
            ]
        )
        assert result["ok"] is False
        assert [v["column"] for v in result["violations"]] == ["A", "B"]


class TestDateFormat:
    def check(self, column):
        return WidthChecker().check({"columns": [column]})

    def base_date_column(self, formats):
        return {
            "letter": "A",
            "header": "日付",
            "values": ["2026/10/30"],
            "width_px": 108,
            "is_date": True,
            "date_formats": formats,
        }

    def test_expected_format_constant(self):
        assert EXPECTED_DATE_FORMAT == "yyyy/mm/dd"

    def test_correct_date_format_passes(self):
        result = self.check(self.base_date_column(["yyyy/mm/dd"]))
        assert result["ok"] is True

    def test_short_date_format_is_a_violation(self):
        result = self.check(self.base_date_column(["yyyy/m/d"]))
        assert result["ok"] is False
        violation = result["violations"][0]
        assert violation["kind"] == "date_format"
        assert violation["expected"] == "yyyy/mm/dd"
        assert violation["actual"] == "yyyy/m/d"

    def test_missing_date_format_is_a_violation(self):
        result = self.check(self.base_date_column([None]))
        assert result["ok"] is False
        assert result["violations"][0]["kind"] == "date_format"

    def test_non_date_column_formats_are_not_checked(self):
        column = self.base_date_column(["yyyy/m/d"])
        column["is_date"] = False
        result = self.check(column)
        assert result["ok"] is True


class TestCli:
    def run_cli(self, tmp_path, payload):
        path = tmp_path / "sheet.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
        )

    def test_cli_ok_exits_zero(self, tmp_path):
        payload = {
            "columns": [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 108,
                    "is_date": True,
                    "date_formats": ["yyyy/mm/dd"],
                }
            ]
        }
        result = self.run_cli(tmp_path, payload)
        assert result.returncode == 0
        assert json.loads(result.stdout)["ok"] is True

    def test_cli_violation_exits_one_and_lists(self, tmp_path):
        payload = {
            "columns": [
                {
                    "letter": "A",
                    "header": "日付",
                    "values": ["2026/10/30"],
                    "width_px": 60,
                    "is_date": True,
                    "date_formats": ["yyyy/m/d"],
                }
            ]
        }
        result = self.run_cli(tmp_path, payload)
        assert result.returncode == 1
        body = json.loads(result.stdout)
        assert body["ok"] is False
        assert len(body["violations"]) == 2
