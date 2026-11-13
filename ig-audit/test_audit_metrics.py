"""audit_metrics.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-audit/SKILL.md「What to actually measure」節と Issue #44。

- 投稿ごとに計算する: outlier = views / アカウント自身の中央値 views、
  hold_at_3s = 3秒時点で残っていた視聴者 / 開始した視聴者、
  sends_per_reach = shares / reach、follows_per_reach = follows / reach
- 順位は outlier と sends_per_reach による（再生数の大きさではない）
- 標本数が下限（既定 30）以上の場合に順位付けと傾向を出す。
  下限未満の場合は傾向の断定を出さない（順位も付けない）

実装はまだ存在しない前提で仕様だけから書いている。そのため現時点では
全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_audit_metrics.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_metrics import AuditMetricsCalculator  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "audit_metrics.py"


def _post(
    pid="p1",
    views=41000,
    reach=10000,
    shares=100,
    follows=50,
    started=1000,
    at_3s=700,
    watch=12.5,
    non_follower=0.6,
):
    return {
        "id": pid,
        "views": views,
        "reach": reach,
        "shares": shares,
        "follows": follows,
        "started": started,
        "at_3s": at_3s,
        "average_watch_time": watch,
        "non_follower_reach": non_follower,
    }


def _posts(n, **kwargs):
    return [_post(pid=f"p{i}", **kwargs) for i in range(n)]


class TestMetricCalculation:
    def test_outlier_is_views_over_median(self):
        calc = AuditMetricsCalculator(median_views=4100)
        result = calc.analyse([_post(views=74600)])
        assert result["posts"][0]["outlier_multiple"] == 18.2

    def test_median_computed_from_posts_when_not_given(self):
        posts = _posts(3)
        posts[0]["views"] = 1000
        posts[1]["views"] = 4100
        posts[2]["views"] = 9000
        result = AuditMetricsCalculator().analyse(posts)
        assert result["median_views"] == 4100
        by_id = {p["id"]: p for p in result["posts"]}
        assert by_id["p2"]["outlier_multiple"] == round(9000 / 4100, 2)

    def test_hold_at_3s(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(
            [_post(started=1000, at_3s=710)]
        )
        assert result["posts"][0]["hold_at_3s"] == 0.71

    def test_sends_per_reach(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(
            [_post(reach=10000, shares=128)]
        )
        assert result["posts"][0]["sends_per_reach"] == 0.0128

    def test_follows_per_reach(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(
            [_post(reach=10000, follows=25)]
        )
        assert result["posts"][0]["follows_per_reach"] == 0.0025

    def test_passthrough_fields(self):
        result = AuditMetricsCalculator(median_views=4100).analyse([_post()])
        post = result["posts"][0]
        assert post["average_watch_time"] == 12.5
        assert post["non_follower_reach"] == 0.6

    def test_missing_denominator_gives_none_not_error(self):
        post = _post()
        post["reach"] = 0
        post["started"] = 0
        result = AuditMetricsCalculator(median_views=4100).analyse([post])
        assert result["posts"][0]["sends_per_reach"] is None
        assert result["posts"][0]["hold_at_3s"] is None


class TestRanking:
    def test_rank_by_outlier_not_views(self):
        # 中央値が小さい側の投稿が、再生数の絶対値が小さくても上位になる
        posts = _posts(30, views=4100)
        posts[0].update(id="hit", views=8200)  # 2.0x (median 4100)
        posts[1].update(id="plain", views=4100)  # 1.0x
        result = AuditMetricsCalculator(median_views=4100).analyse(posts)
        assert result["ranking"][0] == "hit"
        ranks = {p["id"]: p["rank"] for p in result["posts"]}
        assert ranks["hit"] < ranks["plain"]

    def test_sends_per_reach_breaks_outlier_tie(self):
        posts = _posts(30, views=4100)
        posts[0].update(id="low-sends", views=8200, shares=10)
        posts[1].update(id="high-sends", views=8200, shares=900)
        result = AuditMetricsCalculator(median_views=4100).analyse(posts)
        assert result["ranking"][0] == "high-sends"
        assert result["ranking"][1] == "low-sends"

    def test_rank_numbers_start_at_one_and_are_unique(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(_posts(30))
        ranks = sorted(p["rank"] for p in result["posts"])
        assert ranks == list(range(1, 31))


class TestSampleGate:
    def test_below_min_sample_no_ranking_no_tendency(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(_posts(6))
        assert result["sufficient"] is False
        assert result["ranking"] == []
        assert result["tendency"] is None
        assert all(p["rank"] is None for p in result["posts"])

    def test_below_min_sample_still_computes_metrics(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(_posts(6))
        assert result["posts"][0]["outlier_multiple"] == 10.0
        assert result["sample_size"] == 6

    def test_at_min_sample_ranking_and_tendency_present(self):
        result = AuditMetricsCalculator(median_views=4100).analyse(_posts(30))
        assert result["sufficient"] is True
        assert len(result["ranking"]) == 30
        assert result["tendency"] is not None
        assert result["tendency"]["top"][0] == result["ranking"][0]

    def test_min_sample_is_variable(self):
        calc = AuditMetricsCalculator(median_views=4100, min_sample=6)
        result = calc.analyse(_posts(6))
        assert result["sufficient"] is True
        assert len(result["ranking"]) == 6


class TestCli:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_cli_json_input_outputs_json(self, tmp_path):
        src = tmp_path / "posts.json"
        src.write_text(json.dumps(_posts(30)), encoding="utf-8")
        proc = self._run(str(src), "--median-views", "4100")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["sufficient"] is True
        assert len(data["ranking"]) == 30

    def test_cli_small_sample_gates_tendency(self, tmp_path):
        src = tmp_path / "posts.json"
        src.write_text(json.dumps(_posts(6)), encoding="utf-8")
        proc = self._run(str(src), "--median-views", "4100")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["tendency"] is None
        assert data["ranking"] == []

    def test_cli_tsv_input(self, tmp_path):
        header = (
            "id\tviews\treach\tshares\tfollows\tstarted\tat_3s\t"
            "average_watch_time\tnon_follower_reach\n"
        )
        rows = "".join(
            f"p{i}\t41000\t10000\t100\t50\t1000\t700\t12.5\t0.6\n" for i in range(30)
        )
        src = tmp_path / "posts.tsv"
        src.write_text(header + rows, encoding="utf-8")
        proc = self._run(str(src), "--median-views", "4100")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["sample_size"] == 30

    def test_cli_no_rows_exits_2(self, tmp_path):
        src = tmp_path / "empty.json"
        src.write_text("[]", encoding="utf-8")
        proc = self._run(str(src))
        assert proc.returncode == 2
