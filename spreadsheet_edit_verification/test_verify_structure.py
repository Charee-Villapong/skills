"""verify_structure.py の仕様テスト（実装に先行して書いたテスト）。

仕様（完了の定義）だけから書いている。実装の都合ではなく、スキル
spreadsheet_edit_verification の「Verify before you report」節と
API 契約が期待する振る舞いを固定する。

- 構造変更の後にもう一度タブを読み、変更前に記録した集計位置・
  数式範囲と 1 つずつ照合する
- 列を隠した後は各グラフがデータを表示し続けているか確認する
  （グラフの参照列が隠れていたら不可）
- 照合が通った後でのみ報告する。照合中に復元した項目があれば
  報告で名指しする（= restored をそのまま返す）

実行方法:
    python3 -m pytest test_verify_structure.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_structure  # noqa: E402

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def base_snapshot():
    """正常系の基準になるスナップショット（毎回新しい dict を返す）。"""
    return {
        "summaries": [
            {"name": "合計", "cell": "B10", "formula": "=SUM(B2:B9)"},
            {"name": "平均", "cell": "B11", "formula": "=AVERAGE(B2:B9)"},
        ],
        "formula_ranges": [
            {"range": "B2:B9", "formula": "=A2*C2"},
            {"range": "D2:D9", "formula": "=A2*2"},
        ],
        "charts": [
            {"name": "売上グラフ", "source_columns": ["A", "B"]},
            {"name": "推移グラフ", "source_columns": ["A", "D"]},
        ],
        "hidden_columns": [],
    }


def empty_snapshot():
    return {
        "summaries": [],
        "formula_ranges": [],
        "charts": [],
        "hidden_columns": [],
    }


def kinds(result):
    return [m["kind"] for m in result["mismatches"]]


def mismatches_of(result, kind):
    return [m for m in result["mismatches"] if m["kind"] == kind]


# ---------------------------------------------------------------------------
# 正常系
# ---------------------------------------------------------------------------


class TestIdenticalSnapshots:
    def test_identical_snapshots_are_ok(self):
        result = verify_structure.verify(base_snapshot(), base_snapshot())
        assert result["ok"] is True
        assert result["mismatches"] == []

    def test_empty_snapshots_are_ok(self):
        result = verify_structure.verify(empty_snapshot(), empty_snapshot())
        assert result["ok"] is True
        assert result["mismatches"] == []

    def test_hidden_columns_may_be_omitted(self):
        # hidden_columns は任意（既定は空）。無くても照合できること。
        before = base_snapshot()
        after = base_snapshot()
        del before["hidden_columns"]
        del after["hidden_columns"]
        result = verify_structure.verify(before, after)
        assert result["ok"] is True
        assert result["mismatches"] == []

    def test_result_shape(self):
        result = verify_structure.verify(base_snapshot(), base_snapshot())
        assert set(result.keys()) == {"ok", "mismatches", "restored"}
        assert isinstance(result["ok"], bool)
        assert isinstance(result["mismatches"], list)
        assert isinstance(result["restored"], list)


class TestRestoredPassthrough:
    def test_restored_none_returns_empty_list(self):
        result = verify_structure.verify(base_snapshot(), base_snapshot())
        assert result["restored"] == []

    def test_restored_explicit_none_returns_empty_list(self):
        result = verify_structure.verify(
            base_snapshot(), base_snapshot(), restored=None
        )
        assert result["restored"] == []

    def test_restored_is_returned_verbatim(self):
        restored = ["合計", "B2:B9"]
        result = verify_structure.verify(
            base_snapshot(), base_snapshot(), restored=restored
        )
        assert result["restored"] == ["合計", "B2:B9"]

    def test_restored_empty_list_is_returned_as_empty(self):
        result = verify_structure.verify(base_snapshot(), base_snapshot(), restored=[])
        assert result["restored"] == []

    def test_restored_is_returned_even_when_mismatches_exist(self):
        after = base_snapshot()
        after["summaries"] = after["summaries"][:1]
        result = verify_structure.verify(base_snapshot(), after, restored=["平均"])
        assert result["ok"] is False
        assert result["restored"] == ["平均"]


class TestChartSourceOrderAndHiddenUnrelated:
    def test_chart_source_columns_order_does_not_matter(self):
        # source_columns は集合として比較する。順序違いは正常。
        after = base_snapshot()
        after["charts"][0]["source_columns"] = ["B", "A"]
        after["charts"][1]["source_columns"] = ["D", "A"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is True
        assert result["mismatches"] == []

    def test_hidden_column_not_referenced_by_any_chart_is_ok(self):
        after = base_snapshot()
        after["hidden_columns"] = ["Z"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is True
        assert result["mismatches"] == []

    def test_hidden_columns_in_before_only_do_not_trigger(self):
        # 非表示の判定は after に対して行う。before だけにあっても不可にしない。
        before = base_snapshot()
        before["hidden_columns"] = ["B"]
        after = base_snapshot()
        after["hidden_columns"] = []
        result = verify_structure.verify(before, after)
        assert mismatches_of(result, "chart_source_hidden") == []
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# 異常系: 集計（summaries） kind 1〜4
# ---------------------------------------------------------------------------


class TestSummaryMismatches:
    def test_summary_missing(self):
        after = base_snapshot()
        after["summaries"] = [s for s in after["summaries"] if s["name"] != "平均"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "summary_missing")
        assert len(found) == 1
        assert found[0]["key"] == "平均"

    def test_summary_added(self):
        after = base_snapshot()
        after["summaries"].append(
            {"name": "最大", "cell": "B12", "formula": "=MAX(B2:B9)"}
        )
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "summary_added")
        assert len(found) == 1
        assert found[0]["key"] == "最大"

    def test_summary_moved(self):
        after = base_snapshot()
        after["summaries"][0]["cell"] = "B15"
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "summary_moved")
        assert len(found) == 1
        assert found[0]["key"] == "合計"
        # 位置だけの変化では数式変化を併発しない。
        assert mismatches_of(result, "summary_formula_changed") == []

    def test_summary_formula_changed(self):
        after = base_snapshot()
        after["summaries"][0]["formula"] = "=SUM(B2:B8)"
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "summary_formula_changed")
        assert len(found) == 1
        assert found[0]["key"] == "合計"
        # 数式だけの変化では移動を併発しない。
        assert mismatches_of(result, "summary_moved") == []

    def test_summary_moved_and_formula_changed_are_both_reported(self):
        after = base_snapshot()
        after["summaries"][0]["cell"] = "C10"
        after["summaries"][0]["formula"] = "=SUM(C2:C9)"
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        assert len(mismatches_of(result, "summary_moved")) == 1
        assert len(mismatches_of(result, "summary_formula_changed")) == 1


# ---------------------------------------------------------------------------
# 異常系: 数式範囲（formula_ranges） kind 5〜7
# ---------------------------------------------------------------------------


class TestRangeMismatches:
    def test_range_missing(self):
        after = base_snapshot()
        after["formula_ranges"] = [
            r for r in after["formula_ranges"] if r["range"] != "D2:D9"
        ]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "range_missing")
        assert len(found) == 1
        assert found[0]["key"] == "D2:D9"

    def test_range_added(self):
        after = base_snapshot()
        after["formula_ranges"].append({"range": "E2:E9", "formula": "=A2*3"})
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "range_added")
        assert len(found) == 1
        assert found[0]["key"] == "E2:E9"

    def test_range_formula_changed(self):
        after = base_snapshot()
        after["formula_ranges"][0]["formula"] = "=A2*C3"
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "range_formula_changed")
        assert len(found) == 1
        assert found[0]["key"] == "B2:B9"
        # 同じ range が残っているので欠落・追加にはならない。
        assert mismatches_of(result, "range_missing") == []
        assert mismatches_of(result, "range_added") == []


# ---------------------------------------------------------------------------
# 異常系: グラフ（charts） kind 8〜11
# ---------------------------------------------------------------------------


class TestChartMismatches:
    def test_chart_missing(self):
        after = base_snapshot()
        after["charts"] = [c for c in after["charts"] if c["name"] != "推移グラフ"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_missing")
        assert len(found) == 1
        assert found[0]["key"] == "推移グラフ"

    def test_chart_added(self):
        after = base_snapshot()
        after["charts"].append({"name": "新規グラフ", "source_columns": ["A", "E"]})
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_added")
        assert len(found) == 1
        assert found[0]["key"] == "新規グラフ"

    def test_chart_source_changed_by_added_column(self):
        after = base_snapshot()
        after["charts"][0]["source_columns"] = ["A", "B", "C"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_source_changed")
        assert len(found) == 1
        assert found[0]["key"] == "売上グラフ"

    def test_chart_source_changed_by_removed_column(self):
        after = base_snapshot()
        after["charts"][0]["source_columns"] = ["A"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_source_changed")
        assert len(found) == 1
        assert found[0]["key"] == "売上グラフ"

    def test_chart_source_changed_by_replaced_column(self):
        after = base_snapshot()
        after["charts"][0]["source_columns"] = ["A", "C"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        assert len(mismatches_of(result, "chart_source_changed")) == 1

    def test_chart_source_hidden(self):
        after = base_snapshot()
        after["hidden_columns"] = ["B"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_source_hidden")
        assert len(found) >= 1
        assert {m["key"] for m in found} == {"売上グラフ"}

    def test_chart_source_hidden_when_one_of_many_columns_hidden(self):
        # 参照列のいずれか 1 つでも隠れていたら不可。
        after = base_snapshot()
        after["hidden_columns"] = ["D"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_source_hidden")
        assert len(found) >= 1
        assert {m["key"] for m in found} == {"推移グラフ"}

    def test_chart_source_hidden_for_multiple_charts(self):
        # 同じ列を参照する複数グラフはそれぞれ名指しされる。
        after = base_snapshot()
        after["hidden_columns"] = ["A"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        found = mismatches_of(result, "chart_source_hidden")
        assert {m["key"] for m in found} == {"売上グラフ", "推移グラフ"}


# ---------------------------------------------------------------------------
# 複数の不一致・ok と mismatches の対応・mismatch の形
# ---------------------------------------------------------------------------


class TestMultipleMismatchesAndOkCorrespondence:
    def test_multiple_mismatches_are_returned_together(self):
        after = base_snapshot()
        # 集計の移動 + 数式範囲の欠落 + グラフ参照列の変化を同時に起こす。
        after["summaries"][0]["cell"] = "B20"
        after["formula_ranges"] = after["formula_ranges"][:1]
        after["charts"][1]["source_columns"] = ["A", "E"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["ok"] is False
        assert set(kinds(result)) == {
            "summary_moved",
            "range_missing",
            "chart_source_changed",
        }
        assert len(result["mismatches"]) == 3

    def test_ok_is_true_only_when_mismatches_is_empty(self):
        ok_result = verify_structure.verify(base_snapshot(), base_snapshot())
        assert ok_result["mismatches"] == []
        assert ok_result["ok"] is True

        after = base_snapshot()
        after["summaries"][1]["formula"] = "=AVERAGE(B2:B8)"
        ng_result = verify_structure.verify(base_snapshot(), after)
        assert ng_result["mismatches"] != []
        assert ng_result["ok"] is False

    def test_every_mismatch_has_kind_key_and_detail(self):
        after = base_snapshot()
        after["summaries"] = after["summaries"][:1]
        after["hidden_columns"] = ["A"]
        result = verify_structure.verify(base_snapshot(), after)
        assert result["mismatches"] != []
        for mismatch in result["mismatches"]:
            assert set(mismatch.keys()) == {"kind", "key", "detail"}
            assert isinstance(mismatch["kind"], str)
            assert mismatch["kind"] != ""
            assert isinstance(mismatch["key"], str)
            assert mismatch["key"] != ""
            assert isinstance(mismatch["detail"], str)
            assert mismatch["detail"] != ""


# ---------------------------------------------------------------------------
# CLI: 終了コードと標準出力 JSON
# ---------------------------------------------------------------------------


def _run_cli(tmp_path, payload):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    script = Path(__file__).resolve().parent / "verify_structure.py"
    return subprocess.run(
        [sys.executable, str(script), str(input_path)],
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_cli_ok_exits_zero_and_outputs_json(self, tmp_path):
        payload = {"before": base_snapshot(), "after": base_snapshot()}
        proc = _run_cli(tmp_path, payload)
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output["ok"] is True
        assert output["mismatches"] == []
        assert output["restored"] == []

    def test_cli_ng_exits_one_and_outputs_json(self, tmp_path):
        after = base_snapshot()
        after["summaries"][0]["cell"] = "B99"
        payload = {"before": base_snapshot(), "after": after}
        proc = _run_cli(tmp_path, payload)
        assert proc.returncode == 1
        output = json.loads(proc.stdout)
        assert output["ok"] is False
        assert "summary_moved" in kinds(output)

    def test_cli_without_restored_defaults_to_empty_list(self, tmp_path):
        payload = {"before": base_snapshot(), "after": base_snapshot()}
        proc = _run_cli(tmp_path, payload)
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output["restored"] == []

    def test_cli_with_restored_passes_it_through(self, tmp_path):
        payload = {
            "before": base_snapshot(),
            "after": base_snapshot(),
            "restored": ["合計", "売上グラフ"],
        }
        proc = _run_cli(tmp_path, payload)
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output["restored"] == ["合計", "売上グラフ"]

    def test_cli_chart_source_hidden_exits_one(self, tmp_path):
        after = base_snapshot()
        after["hidden_columns"] = ["B"]
        payload = {"before": base_snapshot(), "after": after}
        proc = _run_cli(tmp_path, payload)
        assert proc.returncode == 1
        output = json.loads(proc.stdout)
        assert output["ok"] is False
        assert "chart_source_hidden" in kinds(output)
