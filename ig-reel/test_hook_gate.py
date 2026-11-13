"""hook_gate.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: スキル ig-reel の「The loop」節 step 2 と Issue #41。

完了の定義:
- フック評価（hookscore.py）の最上位スコアが下限（既定50）以上なら
  台本作成へ進める（ok=True, decision="proceed"）
- 最上位スコアが下限未満なら台本作成を止め、フックの作り直しを求める
  （ok=False, decision="rewrite_hook"）
- 入力は hookscore.py --json の出力形式（単体オブジェクト／配列）を
  そのまま受け取れること

実装（hook_gate.py）はまだ存在しない前提で、仕様だけから書いている。
そのため現時点では全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_hook_gate.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_gate import HookGate  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "hook_gate.py"


class TestGate:
    def test_top_score_above_min_proceeds(self):
        result = HookGate().evaluate([{"score": 86}, {"score": 71}, {"score": 54}])
        assert result["ok"] is True
        assert result["decision"] == "proceed"
        assert result["top_score"] == 86

    def test_top_score_exactly_at_min_proceeds(self):
        # 「under 50」が不可なので 50 は通過
        result = HookGate().evaluate([{"score": 50}])
        assert result["ok"] is True
        assert result["decision"] == "proceed"

    def test_top_score_just_below_min_is_blocked(self):
        result = HookGate().evaluate([{"score": 49.9}, {"score": 30}])
        assert result["ok"] is False
        assert result["decision"] == "rewrite_hook"
        assert result["top_score"] == 49.9

    def test_single_object_input(self):
        result = HookGate().evaluate({"score": 86, "verdict": "STRONG"})
        assert result["ok"] is True
        assert result["top_score"] == 86

    def test_plain_number_list_input(self):
        result = HookGate().evaluate([86, 71, 54])
        assert result["ok"] is True
        assert result["top_score"] == 86

    def test_plain_single_number_input(self):
        assert HookGate().evaluate(49)["ok"] is False
        assert HookGate().evaluate(50)["ok"] is True

    def test_result_shape(self):
        result = HookGate().evaluate([{"score": 86}])
        assert set(result.keys()) == {
            "ok",
            "decision",
            "top_score",
            "min_top_score",
            "count",
        }
        assert result["min_top_score"] == 50
        assert result["count"] == 1

    def test_empty_input_is_blocked_not_proceed(self):
        result = HookGate().evaluate([])
        assert result["ok"] is False
        assert result["decision"] == "rewrite_hook"
        assert result["top_score"] is None
        assert result["count"] == 0

    def test_custom_min_score(self):
        payload = [{"score": 60}]
        assert HookGate().evaluate(payload)["ok"] is True
        assert HookGate(min_top_score=70).evaluate(payload)["ok"] is False
        assert HookGate(min_top_score=60).evaluate(payload)["ok"] is True


class TestCli:
    def _write(self, tmp_path, payload):
        path = tmp_path / "scores.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True
        )

    def test_cli_proceed_exits_0(self, tmp_path):
        path = self._write(
            tmp_path, [{"hook": "a", "score": 86}, {"hook": "b", "score": 54}]
        )
        proc = self._run(str(path))
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["decision"] == "proceed"
        assert out["top_score"] == 86

    def test_cli_blocked_exits_1(self, tmp_path):
        path = self._write(tmp_path, [{"hook": "a", "score": 42}])
        proc = self._run(str(path))
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["decision"] == "rewrite_hook"

    def test_cli_score_flag(self):
        proc = self._run("--score", "86", "--score", "54")
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["top_score"] == 86

    def test_cli_min_score_flag(self, tmp_path):
        path = self._write(tmp_path, [{"score": 60}])
        assert self._run(str(path), "--min-score", "70").returncode == 1
        assert self._run(str(path), "--min-score", "60").returncode == 0

    def test_cli_stdin(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "-"],
            input=json.dumps({"score": 86}),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
