"""reconcile.py のテスト（仕様＝完了の定義からのみ作成した先行テスト）。

対象仕様:
- 関数 ``reconcile(report: dict) -> dict``
- CLI ``python3 reconcile.py <入力JSONファイル>`` は結果を JSON で
  標準出力に出し、ok なら終了コード 0、NG なら 1。

照合ルール（仕様）:
1. counts.searched は searched リストの件数。重複があればエラー。
2. searched の各 item は already_done / newly_done / kept のいずれか
   ちょうど1つの action を持たなければならない。
3. searched に無い item への action は restored の場合のみ許される。
4. 同一 item に restored と newly_done の両方がある場合はエラー。
5. result が4区分以外ならエラー。
6. ok は errors が空のときだけ True。そのとき
   searched = already_done + newly_done + kept を満たす。

エラー文言そのものは仕様で固定されていないため、異常系では
文言の完全一致ではなく「ok が False で errors に文字列が入ること」を検証する。

標準ライブラリ + pytest のみで動く。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "reconcile.py"
VALID_RESULTS = ("already_done", "newly_done", "kept", "restored")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def action(item_id, result):
    return {"item_id": item_id, "result": result}


def assert_ng(result):
    """照合NGの共通形: ok=False、errors は空でない文字列リスト。"""
    assert result["ok"] is False
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) > 0
    assert all(isinstance(e, str) and e for e in result["errors"])


def assert_ok(result, *, searched, already_done, newly_done, kept, restored):
    """照合OKの共通形: ok=True、errors 空、counts 内訳が完全一致。"""
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["counts"] == {
        "searched": searched,
        "already_done": already_done,
        "newly_done": newly_done,
        "kept": kept,
        "restored": restored,
    }
    # ルール6: 合計の一致（restored は新規処理の総数に含めない）。
    counts = result["counts"]
    assert counts["searched"] == (
        counts["already_done"] + counts["newly_done"] + counts["kept"]
    )


# ---------------------------------------------------------------------------
# 出力の構造
# ---------------------------------------------------------------------------


class TestOutputStructure:
    def test_output_has_required_keys_and_types(self):
        result = reconcile.reconcile(
            {"searched": ["a"], "actions": [action("a", "newly_done")]}
        )
        assert set(result.keys()) == {"ok", "counts", "errors"}
        assert isinstance(result["ok"], bool)
        assert isinstance(result["counts"], dict)
        assert set(result["counts"].keys()) == {
            "searched",
            "already_done",
            "newly_done",
            "kept",
            "restored",
        }
        assert all(isinstance(v, int) for v in result["counts"].values())
        assert isinstance(result["errors"], list)

    def test_ok_is_true_only_when_errors_empty(self):
        ok_result = reconcile.reconcile(
            {"searched": ["a"], "actions": [action("a", "kept")]}
        )
        assert ok_result["ok"] is True
        assert ok_result["errors"] == []

        ng_result = reconcile.reconcile({"searched": ["a"], "actions": []})
        assert ng_result["ok"] is False
        assert ng_result["errors"] != []


# ---------------------------------------------------------------------------
# 正常系
# ---------------------------------------------------------------------------


class TestNormalCases:
    def test_all_categories_reconcile(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b", "c", "d"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "already_done"),
                    action("c", "kept"),
                    action("d", "newly_done"),
                    # restored は searched 外の item でもよい。
                    action("z", "restored"),
                ],
                "scope": "sender: example",
            }
        )
        assert_ok(
            result,
            searched=4,
            already_done=1,
            newly_done=2,
            kept=1,
            restored=1,
        )

    def test_restored_outside_searched_is_allowed(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("old-1", "restored"),
                    action("old-2", "restored"),
                ],
            }
        )
        assert_ok(result, searched=1, already_done=0, newly_done=1, kept=0, restored=2)

    def test_restored_is_never_counted_as_newly_done(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "kept"),
                    action("x", "restored"),
                    action("y", "restored"),
                    action("z", "restored"),
                ],
            }
        )
        assert result["counts"]["newly_done"] == 1
        assert result["counts"]["restored"] == 3
        assert_ok(result, searched=2, already_done=0, newly_done=1, kept=1, restored=3)

    def test_already_done_is_not_counted_as_newly_done(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b"],
                "actions": [
                    action("a", "already_done"),
                    action("b", "already_done"),
                ],
            }
        )
        assert_ok(result, searched=2, already_done=2, newly_done=0, kept=0, restored=0)

    def test_kept_only(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b"],
                "actions": [action("a", "kept"), action("b", "kept")],
            }
        )
        assert_ok(result, searched=2, already_done=0, newly_done=0, kept=2, restored=0)

    def test_newly_done_only(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b", "c"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "newly_done"),
                    action("c", "newly_done"),
                ],
            }
        )
        assert_ok(result, searched=3, already_done=0, newly_done=3, kept=0, restored=0)

    def test_empty_searched_with_no_actions(self):
        result = reconcile.reconcile({"searched": [], "actions": []})
        assert_ok(result, searched=0, already_done=0, newly_done=0, kept=0, restored=0)

    def test_empty_searched_with_only_restored(self):
        result = reconcile.reconcile(
            {"searched": [], "actions": [action("old", "restored")]}
        )
        assert_ok(result, searched=0, already_done=0, newly_done=0, kept=0, restored=1)

    def test_scope_may_be_omitted(self):
        result = reconcile.reconcile(
            {"searched": ["a"], "actions": [action("a", "already_done")]}
        )
        assert_ok(result, searched=1, already_done=1, newly_done=0, kept=0, restored=0)

    def test_scope_present_does_not_change_counts(self):
        report = {
            "searched": ["a", "b"],
            "actions": [action("a", "newly_done"), action("b", "kept")],
        }
        without_scope = reconcile.reconcile(dict(report))
        with_scope = reconcile.reconcile(
            dict(report, scope="folder: inbox, 2026-01-01..2026-01-31")
        )
        assert with_scope["ok"] is True
        assert with_scope["counts"] == without_scope["counts"]


# ---------------------------------------------------------------------------
# 異常系: searched の重複（ルール1）
# ---------------------------------------------------------------------------


class TestDuplicateSearched:
    def test_duplicate_item_in_searched_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "a"],
                "actions": [action("a", "newly_done")],
            }
        )
        assert_ng(result)

    def test_duplicate_among_many_in_searched_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b", "c", "b"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "kept"),
                    action("c", "already_done"),
                ],
            }
        )
        assert_ng(result)


# ---------------------------------------------------------------------------
# 異常系: action の欠落・二重分類（ルール2）
# ---------------------------------------------------------------------------


class TestMissingAndDuplicateActions:
    def test_missing_action_is_error(self):
        result = reconcile.reconcile({"searched": ["a"], "actions": []})
        assert_ng(result)

    def test_missing_action_for_one_of_many_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b", "c"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "kept"),
                    # c の action が欠けている。
                ],
            }
        )
        assert_ng(result)

    def test_two_different_results_for_same_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("a", "kept"),
                ],
            }
        )
        assert_ng(result)

    def test_same_result_twice_for_same_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("a", "newly_done"),
                ],
            }
        )
        assert_ng(result)

    def test_already_done_and_newly_done_for_same_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a", "b"],
                "actions": [
                    action("a", "already_done"),
                    action("a", "newly_done"),
                    action("b", "kept"),
                ],
            }
        )
        assert_ng(result)

    def test_searched_item_with_only_restored_is_error(self):
        # searched の item は already_done / newly_done / kept の
        # いずれかちょうど1つが必要。restored だけでは欠落になる。
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [action("a", "restored")],
            }
        )
        assert_ng(result)


# ---------------------------------------------------------------------------
# 異常系: 範囲外 item への action（ルール3）
# ---------------------------------------------------------------------------


class TestOutOfScopeActions:
    @pytest.mark.parametrize("result_value", ["newly_done", "already_done", "kept"])
    def test_out_of_scope_non_restored_action_is_error(self, result_value):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("outside", result_value),
                ],
            }
        )
        assert_ng(result)

    def test_out_of_scope_action_with_empty_searched_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": [],
                "actions": [action("outside", "newly_done")],
            }
        )
        assert_ng(result)


# ---------------------------------------------------------------------------
# 異常系: restored と newly_done の併存（ルール4）
# ---------------------------------------------------------------------------


class TestRestoredAndNewlyDoneConflict:
    def test_restored_and_newly_done_for_searched_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("a", "restored"),
                ],
            }
        )
        assert_ng(result)

    def test_restored_and_newly_done_for_out_of_scope_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "kept"),
                    action("x", "restored"),
                    action("x", "newly_done"),
                ],
            }
        )
        assert_ng(result)


# ---------------------------------------------------------------------------
# 異常系: 不正な result 値（ルール5）
# ---------------------------------------------------------------------------


class TestInvalidResultValues:
    @pytest.mark.parametrize(
        "bad_value",
        ["deleted", "done", "NEWLY_DONE", "newly-done", "", "trashed"],
    )
    def test_invalid_result_value_is_error(self, bad_value):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [action("a", bad_value)],
            }
        )
        assert_ng(result)

    def test_invalid_result_for_out_of_scope_item_is_error(self):
        result = reconcile.reconcile(
            {
                "searched": ["a"],
                "actions": [
                    action("a", "newly_done"),
                    action("outside", "deleted"),
                ],
            }
        )
        assert_ng(result)

    @pytest.mark.parametrize("valid_value", list(VALID_RESULTS))
    def test_each_valid_result_value_is_accepted_in_valid_position(self, valid_value):
        # 4区分そのものは値として正しいことの確認。
        # searched 内は3区分、restored は searched 外に置く。
        if valid_value == "restored":
            report = {
                "searched": ["a"],
                "actions": [
                    action("a", "kept"),
                    action("outside", "restored"),
                ],
            }
        else:
            report = {
                "searched": ["a"],
                "actions": [action("a", valid_value)],
            }
        result = reconcile.reconcile(report)
        assert result["ok"] is True
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# CLI: 終了コードと JSON 出力
# ---------------------------------------------------------------------------


def run_cli(tmp_path, report):
    input_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_cli_ok_exits_0_and_prints_json(self, tmp_path):
        proc = run_cli(
            tmp_path,
            {
                "searched": ["a", "b"],
                "actions": [
                    action("a", "newly_done"),
                    action("b", "kept"),
                    action("old", "restored"),
                ],
                "scope": "folder: inbox",
            },
        )
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["errors"] == []
        assert payload["counts"] == {
            "searched": 2,
            "already_done": 0,
            "newly_done": 1,
            "kept": 1,
            "restored": 1,
        }

    def test_cli_ng_exits_1_and_prints_json(self, tmp_path):
        proc = run_cli(
            tmp_path,
            {
                "searched": ["a", "b"],
                # b の action が欠けているため照合NG。
                "actions": [action("a", "newly_done")],
            },
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert payload["errors"]
        assert set(payload["counts"].keys()) == {
            "searched",
            "already_done",
            "newly_done",
            "kept",
            "restored",
        }

    def test_cli_empty_report_exits_0(self, tmp_path):
        proc = run_cli(tmp_path, {"searched": [], "actions": []})
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["counts"] == {
            "searched": 0,
            "already_done": 0,
            "newly_done": 0,
            "kept": 0,
            "restored": 0,
        }

    def test_cli_out_of_scope_newly_done_exits_1(self, tmp_path):
        proc = run_cli(
            tmp_path,
            {
                "searched": ["a"],
                "actions": [
                    action("a", "kept"),
                    action("outside", "newly_done"),
                ],
            },
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert payload["errors"]
