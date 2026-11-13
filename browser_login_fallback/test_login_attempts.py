"""login_attempts.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル browser_login_fallback の
「Stop repeating a failed login route」節。

- 同じログイン経路では、失敗は上限（既定1回）まで。同じ経路を繰り返さない
- 別経路は、失敗した経路の種類が上限（既定2種類）未満のときだけ試してよい
- 異なる経路が上限まで失敗したら止め、代替手段へ切り替える

実装（login_attempts.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

import 方式は同リポジトリ ig-caption/test_caption_characterization.py の
慣例（sys.path へテストファイルのディレクトリを入れてから import）に合わせる。

実行方法:
    python3 -m pytest test_login_attempts.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from login_attempts import LoginAttemptGuard  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "login_attempts.py"


# ---------------------------------------------------------------------------
# 初期状態
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_failure_count_for_unrecorded_route_is_zero(self):
        guard = LoginAttemptGuard()
        assert guard.failure_count("A") == 0
        assert guard.failure_count("never-tried") == 0

    def test_failed_routes_initially_empty(self):
        guard = LoginAttemptGuard()
        assert guard.failed_routes() == []

    def test_can_attempt_initially_true_for_any_route(self):
        guard = LoginAttemptGuard()
        assert guard.can_attempt("A") is True
        assert guard.can_attempt("B") is True


# ---------------------------------------------------------------------------
# 正常系: 既定値での流れ（スキル本文どおり）
# ---------------------------------------------------------------------------


class TestDefaultFlow:
    def test_route_a_first_failure_returns_try_other_route(self):
        guard = LoginAttemptGuard()
        assert guard.record_failure("A") == "try_other_route"

    def test_route_b_first_failure_after_a_returns_stop_fallback(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        assert guard.record_failure("B") == "stop_fallback"

    def test_default_flow_failure_counts(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        assert guard.failure_count("A") == 1
        assert guard.failure_count("B") == 0
        guard.record_failure("B")
        assert guard.failure_count("A") == 1
        assert guard.failure_count("B") == 1

    def test_default_flow_failed_routes_lists_both_routes(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        assert guard.failed_routes() == ["A"]
        guard.record_failure("B")
        assert set(guard.failed_routes()) == {"A", "B"}
        assert len(guard.failed_routes()) == 2

    def test_after_stop_fallback_no_route_can_be_attempted(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.can_attempt("A") is False
        assert guard.can_attempt("B") is False
        assert guard.can_attempt("C") is False


# ---------------------------------------------------------------------------
# 設定変更: max_same_route_failures
# ---------------------------------------------------------------------------


class TestCustomSameRouteLimit:
    def test_max_same_2_first_failure_returns_retry_same_route(self):
        guard = LoginAttemptGuard(max_same_route_failures=2)
        assert guard.record_failure("A") == "retry_same_route"

    def test_max_same_2_second_failure_returns_try_other_route(self):
        guard = LoginAttemptGuard(max_same_route_failures=2)
        guard.record_failure("A")
        assert guard.record_failure("A") == "try_other_route"

    def test_max_same_2_can_attempt_still_true_after_first_failure(self):
        guard = LoginAttemptGuard(max_same_route_failures=2)
        guard.record_failure("A")
        assert guard.can_attempt("A") is True

    def test_max_same_2_can_attempt_false_after_second_failure(self):
        guard = LoginAttemptGuard(max_same_route_failures=2)
        guard.record_failure("A")
        guard.record_failure("A")
        assert guard.can_attempt("A") is False
        # 別経路はまだ試せる（失敗した経路の種類は1つだけ）。
        assert guard.can_attempt("B") is True


# ---------------------------------------------------------------------------
# 設定変更: max_distinct_route_failures
# ---------------------------------------------------------------------------


class TestCustomDistinctRouteLimit:
    def test_max_distinct_3_second_route_failure_still_try_other_route(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=3)
        assert guard.record_failure("A") == "try_other_route"
        assert guard.record_failure("B") == "try_other_route"

    def test_max_distinct_3_third_route_failure_returns_stop_fallback(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=3)
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.record_failure("C") == "stop_fallback"

    def test_max_distinct_3_can_attempt_third_route_after_two_failures(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=3)
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.can_attempt("C") is True

    def test_max_distinct_3_can_attempt_false_for_unused_route_after_stop(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=3)
        guard.record_failure("A")
        guard.record_failure("B")
        guard.record_failure("C")
        assert guard.can_attempt("D") is False

    def test_max_distinct_1_first_failure_returns_stop_fallback(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=1)
        assert guard.record_failure("A") == "stop_fallback"


# ---------------------------------------------------------------------------
# can_attempt の境界
# ---------------------------------------------------------------------------


class TestCanAttempt:
    def test_can_attempt_false_for_route_that_reached_limit(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        assert guard.can_attempt("A") is False

    def test_can_attempt_true_for_unused_route_before_stop(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        assert guard.can_attempt("B") is True

    def test_can_attempt_false_for_unused_route_after_stop(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.can_attempt("unused-route") is False

    def test_can_attempt_false_for_both_failed_routes_after_stop(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.can_attempt("A") is False
        assert guard.can_attempt("B") is False


# ---------------------------------------------------------------------------
# failure_count / failed_routes
# ---------------------------------------------------------------------------


class TestFailureCountAndRoutes:
    def test_failure_count_tracked_independently_per_route(self):
        guard = LoginAttemptGuard(
            max_same_route_failures=3, max_distinct_route_failures=3
        )
        guard.record_failure("A")
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.failure_count("A") == 2
        assert guard.failure_count("B") == 1
        assert guard.failure_count("C") == 0

    def test_failed_routes_has_no_duplicates_for_repeated_same_route(self):
        guard = LoginAttemptGuard(max_same_route_failures=2)
        guard.record_failure("A")
        guard.record_failure("A")
        assert guard.failed_routes() == ["A"]
        assert guard.failure_count("A") == 2

    def test_failed_routes_reflects_only_routes_that_failed(self):
        guard = LoginAttemptGuard(max_distinct_route_failures=3)
        guard.record_failure("sms")
        guard.record_failure("password")
        assert set(guard.failed_routes()) == {"sms", "password"}
        assert "email-link" not in guard.failed_routes()


# ---------------------------------------------------------------------------
# record_success によるリセット
# ---------------------------------------------------------------------------


class TestRecordSuccess:
    def test_success_clears_failure_counts(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_success("A")
        assert guard.failure_count("A") == 0

    def test_success_clears_all_recorded_failures(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        guard.record_success("B")
        assert guard.failure_count("A") == 0
        assert guard.failure_count("B") == 0
        assert guard.failed_routes() == []

    def test_success_restores_can_attempt(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        assert guard.can_attempt("A") is False
        guard.record_success("B")
        assert guard.can_attempt("A") is True
        assert guard.can_attempt("B") is True
        assert guard.can_attempt("C") is True

    def test_success_resets_decision_flow_to_initial(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        guard.record_success("B")
        # 初期状態に戻っているので、既定の流れが最初から再現される。
        assert guard.record_failure("A") == "try_other_route"
        assert guard.record_failure("B") == "stop_fallback"

    def test_success_on_fresh_guard_is_noop(self):
        guard = LoginAttemptGuard()
        guard.record_success("A")
        assert guard.failed_routes() == []
        assert guard.failure_count("A") == 0
        assert guard.can_attempt("A") is True


# ---------------------------------------------------------------------------
# to_dict / from_dict の往復
# ---------------------------------------------------------------------------


class TestDictRoundTrip:
    def test_roundtrip_preserves_failure_counts_and_routes(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        restored = LoginAttemptGuard.from_dict(guard.to_dict())
        assert restored.failure_count("A") == 1
        assert restored.failure_count("B") == 0
        assert restored.failed_routes() == ["A"]
        assert restored.can_attempt("A") is False
        assert restored.can_attempt("B") is True

    def test_roundtrip_preserves_stopped_state(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        restored = LoginAttemptGuard.from_dict(guard.to_dict())
        assert set(restored.failed_routes()) == {"A", "B"}
        assert restored.can_attempt("A") is False
        assert restored.can_attempt("C") is False

    def test_roundtrip_of_empty_guard_is_initial_state(self):
        restored = LoginAttemptGuard.from_dict(LoginAttemptGuard().to_dict())
        assert restored.failed_routes() == []
        assert restored.failure_count("A") == 0
        assert restored.can_attempt("A") is True
        assert restored.record_failure("A") == "try_other_route"

    def test_roundtrip_preserves_custom_limits(self):
        guard = LoginAttemptGuard(
            max_same_route_failures=2, max_distinct_route_failures=3
        )
        assert guard.record_failure("A") == "retry_same_route"
        restored = LoginAttemptGuard.from_dict(guard.to_dict())
        # 上限が既定値に戻っていたら以下の判断は変わる。
        # 判定は経路単位: same=2 のため、各経路の1回目は retry_same_route、
        # 2回目でその経路が上限到達。distinct=3 のため、上限到達が
        # 3種類目で stop_fallback になる。
        assert restored.can_attempt("A") is True
        assert restored.record_failure("A") == "try_other_route"
        assert restored.record_failure("B") == "retry_same_route"
        assert restored.record_failure("B") == "try_other_route"
        assert restored.record_failure("C") == "retry_same_route"
        assert restored.record_failure("C") == "stop_fallback"

    def test_to_dict_survives_json_roundtrip(self):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        data = json.loads(json.dumps(guard.to_dict()))
        restored = LoginAttemptGuard.from_dict(data)
        assert restored.failure_count("A") == 1
        assert restored.failed_routes() == ["A"]


# ---------------------------------------------------------------------------
# save / load の往復（JSON ファイル）
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_save_load_preserves_failure_counts_and_routes(self, tmp_path):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        path = str(tmp_path / "state.json")
        guard.save(path)
        restored = LoginAttemptGuard.load(path)
        assert restored.failure_count("A") == 1
        assert restored.failed_routes() == ["A"]
        assert restored.can_attempt("A") is False
        assert restored.can_attempt("B") is True

    def test_save_load_preserves_stopped_state(self, tmp_path):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        guard.record_failure("B")
        path = str(tmp_path / "state.json")
        guard.save(path)
        restored = LoginAttemptGuard.load(path)
        assert set(restored.failed_routes()) == {"A", "B"}
        assert restored.can_attempt("C") is False

    def test_save_load_preserves_custom_limits(self, tmp_path):
        guard = LoginAttemptGuard(
            max_same_route_failures=2, max_distinct_route_failures=3
        )
        assert guard.record_failure("A") == "retry_same_route"
        path = str(tmp_path / "state.json")
        guard.save(path)
        restored = LoginAttemptGuard.load(path)
        # 判定は経路単位: same=2 のため、各経路の1回目は retry_same_route、
        # 2回目でその経路が上限到達。distinct=3 のため、上限到達が
        # 3種類目で stop_fallback になる。
        assert restored.can_attempt("A") is True
        assert restored.record_failure("A") == "try_other_route"
        assert restored.record_failure("B") == "retry_same_route"
        assert restored.record_failure("B") == "try_other_route"
        assert restored.record_failure("C") == "retry_same_route"
        assert restored.record_failure("C") == "stop_fallback"

    def test_save_creates_valid_json_file(self, tmp_path):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        path = tmp_path / "state.json"
        guard.save(str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_load_then_continue_recording(self, tmp_path):
        guard = LoginAttemptGuard()
        guard.record_failure("A")
        path = str(tmp_path / "state.json")
        guard.save(path)
        restored = LoginAttemptGuard.load(path)
        # 読み込んだ状態の続きから、既定の流れで止まる。
        assert restored.record_failure("B") == "stop_fallback"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_cli(state_path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state", str(state_path), *args],
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_cli_fail_on_new_state_returns_try_other_route(self, tmp_path):
        state = tmp_path / "state.json"
        result = run_cli(state, "fail", "A")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["decision"] == "try_other_route"
        assert payload["route"] == "A"
        assert payload["failure_count"] == 1
        assert payload["failed_routes"] == ["A"]

    def test_cli_fail_creates_state_file(self, tmp_path):
        state = tmp_path / "state.json"
        assert not state.exists()
        result = run_cli(state, "fail", "A")
        assert result.returncode == 0
        assert state.exists()

    def test_cli_fail_persists_state_across_invocations(self, tmp_path):
        state = tmp_path / "state.json"
        first = run_cli(state, "fail", "A")
        assert json.loads(first.stdout)["decision"] == "try_other_route"
        # 別プロセスの呼び出しでも前回の状態を引き継ぐ。
        second = run_cli(state, "fail", "B")
        assert second.returncode == 0
        payload = json.loads(second.stdout)
        assert payload["decision"] == "stop_fallback"
        assert payload["route"] == "B"
        assert payload["failure_count"] == 1
        assert set(payload["failed_routes"]) == {"A", "B"}

    def test_cli_check_on_new_state_is_true(self, tmp_path):
        state = tmp_path / "state.json"
        result = run_cli(state, "check", "A")
        assert result.returncode == 0
        assert json.loads(result.stdout)["can_attempt"] is True

    def test_cli_check_after_failure_reflects_limits(self, tmp_path):
        state = tmp_path / "state.json"
        run_cli(state, "fail", "A")
        result_a = run_cli(state, "check", "A")
        assert json.loads(result_a.stdout)["can_attempt"] is False
        result_b = run_cli(state, "check", "B")
        assert json.loads(result_b.stdout)["can_attempt"] is True

    def test_cli_check_after_stop_is_false_for_unused_route(self, tmp_path):
        state = tmp_path / "state.json"
        run_cli(state, "fail", "A")
        run_cli(state, "fail", "B")
        result = run_cli(state, "check", "C")
        assert json.loads(result.stdout)["can_attempt"] is False

    def test_cli_success_clears_persisted_state(self, tmp_path):
        state = tmp_path / "state.json"
        run_cli(state, "fail", "A")
        run_cli(state, "fail", "B")
        result = run_cli(state, "success", "B")
        assert result.returncode == 0
        check = run_cli(state, "check", "A")
        assert json.loads(check.stdout)["can_attempt"] is True
        # 消去後は既定の流れが最初から再現される。
        again = run_cli(state, "fail", "A")
        payload = json.loads(again.stdout)
        assert payload["decision"] == "try_other_route"
        assert payload["failure_count"] == 1
        assert payload["failed_routes"] == ["A"]

    def test_cli_max_same_route_flag_first_failure_retries_same(self, tmp_path):
        state = tmp_path / "state.json"
        result = run_cli(state, "--max-same-route", "2", "fail", "A")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["decision"] == "retry_same_route"
        assert payload["failure_count"] == 1

    def test_cli_max_same_route_flag_second_failure_tries_other(self, tmp_path):
        state = tmp_path / "state.json"
        run_cli(state, "--max-same-route", "2", "fail", "A")
        result = run_cli(state, "--max-same-route", "2", "fail", "A")
        payload = json.loads(result.stdout)
        assert payload["decision"] == "try_other_route"
        assert payload["failure_count"] == 2
        assert payload["failed_routes"] == ["A"]

    def test_cli_max_distinct_routes_flag_allows_third_route(self, tmp_path):
        state = tmp_path / "state.json"
        run_cli(state, "--max-distinct-routes", "3", "fail", "A")
        second = run_cli(state, "--max-distinct-routes", "3", "fail", "B")
        assert json.loads(second.stdout)["decision"] == "try_other_route"
        third = run_cli(state, "--max-distinct-routes", "3", "fail", "C")
        payload = json.loads(third.stdout)
        assert payload["decision"] == "stop_fallback"
        assert set(payload["failed_routes"]) == {"A", "B", "C"}
