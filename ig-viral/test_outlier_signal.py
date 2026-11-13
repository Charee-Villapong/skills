"""outlier_signal.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-viral/SKILL.md「The one idea that makes this worth doing」節と
Issue #43。

- 倍率は views / median
- 倍率が上限しきい値（既定 3.0）以上なら signal
- 倍率が下限しきい値（既定 1.5）未満なら normal
- その間は signal でも normal でもない（intermediate）
- 規模が本人の 10 倍以内（既定）の範囲内にある場合に分類する。
  範囲外は out_of_range とし、signal などに分類しない
- 中央値が欠けた行は分類せず、欠落として一覧に出す

実装はまだ存在しない前提で仕様だけから書いている。そのため現時点では
全テストが失敗（import エラー）するのが正常。

実行方法:
    python3 -m pytest test_outlier_signal.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from outlier_signal import OutlierSignalClassifier  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "outlier_signal.py"


def _row(account="@a", followers=4000, median=10000, views=400000):
    return {
        "account": account,
        "followers": followers,
        "median": median,
        "views": views,
    }


class TestMultiple:
    def test_multiple_is_views_over_median(self):
        result = OutlierSignalClassifier().analyse([_row()])
        assert result["classified"][0]["outlier_multiple"] == 40.0

    def test_multiple_rounding_keeps_two_decimals(self):
        result = OutlierSignalClassifier().analyse([_row(median=3000, views=10000)])
        assert result["classified"][0]["outlier_multiple"] == 3.33


class TestClassification:
    def test_above_signal_threshold_is_signal(self):
        result = OutlierSignalClassifier().analyse([_row(views=400000)])
        assert result["classified"][0]["classification"] == "signal"

    def test_exactly_signal_threshold_is_signal(self):
        # Issue #43: 上限しきい値「以上」ならシグナル
        result = OutlierSignalClassifier().analyse([_row(median=10000, views=30000)])
        assert result["classified"][0]["classification"] == "signal"

    def test_below_normal_threshold_is_normal(self):
        result = OutlierSignalClassifier().analyse([_row(median=10000, views=10000)])
        assert result["classified"][0]["classification"] == "normal"

    def test_exactly_normal_threshold_is_not_normal(self):
        # 下限「未満」なら通常。ちょうど下限は通常ではない
        result = OutlierSignalClassifier().analyse([_row(median=10000, views=15000)])
        assert result["classified"][0]["classification"] == "intermediate"

    def test_between_thresholds_is_intermediate(self):
        result = OutlierSignalClassifier().analyse([_row(median=10000, views=20000)])
        assert result["classified"][0]["classification"] == "intermediate"

    def test_thresholds_are_variables(self):
        clf = OutlierSignalClassifier(signal_threshold=5.0, normal_threshold=2.0)
        result = clf.analyse([_row(median=10000, views=40000)])
        assert result["classified"][0]["classification"] == "intermediate"
        result = clf.analyse([_row(median=10000, views=50000)])
        assert result["classified"][0]["classification"] == "signal"


class TestSizeRange:
    def test_within_ten_times_is_classified(self):
        # 本人 4000、相手 40000 はちょうど 10 倍で範囲内
        result = OutlierSignalClassifier().analyse(
            [_row(followers=40000)], user_followers=4000
        )
        assert result["classified"][0]["in_size_range"] is True
        assert result["classified"][0]["classification"] == "signal"

    def test_within_tenth_is_classified(self):
        result = OutlierSignalClassifier().analyse(
            [_row(followers=400)], user_followers=4000
        )
        assert result["classified"][0]["in_size_range"] is True

    def test_outside_range_is_not_classified_as_signal(self):
        result = OutlierSignalClassifier().analyse(
            [_row(followers=2000000)], user_followers=4000
        )
        row = result["classified"][0]
        assert row["in_size_range"] is False
        assert row["classification"] == "out_of_range"

    def test_small_outside_range_is_out_of_range(self):
        result = OutlierSignalClassifier().analyse(
            [_row(followers=100)], user_followers=4000
        )
        assert result["classified"][0]["classification"] == "out_of_range"

    def test_no_user_followers_means_range_unknown_and_classified(self):
        result = OutlierSignalClassifier().analyse([_row(followers=2000000)])
        row = result["classified"][0]
        assert row["in_size_range"] is None
        assert row["classification"] == "signal"

    def test_size_ratio_is_variable(self):
        clf = OutlierSignalClassifier(size_ratio=5.0)
        result = clf.analyse([_row(followers=40000)], user_followers=4000)
        assert result["classified"][0]["classification"] == "out_of_range"


class TestMissingMedian:
    def test_missing_median_is_not_classified(self):
        result = OutlierSignalClassifier().analyse([_row(median=None)])
        assert result["classified"] == []
        assert len(result["missing"]) == 1
        assert result["missing"][0]["account"] == "@a"

    def test_zero_median_is_missing(self):
        result = OutlierSignalClassifier().analyse([_row(median=0)])
        assert result["classified"] == []
        assert len(result["missing"]) == 1

    def test_empty_string_median_is_missing(self):
        result = OutlierSignalClassifier().analyse([_row(median="")])
        assert len(result["missing"]) == 1

    def test_missing_and_classified_are_separated(self):
        rows = [_row(account="@ok"), _row(account="@bad", median=None)]
        result = OutlierSignalClassifier().analyse(rows)
        assert [r["account"] for r in result["classified"]] == ["@ok"]
        assert [r["account"] for r in result["missing"]] == ["@bad"]
        assert result["n"] == 2


class TestCli:
    def _run(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin,
            capture_output=True,
            text=True,
        )

    def test_cli_tsv_outputs_json(self, tmp_path):
        tsv = tmp_path / "captured.tsv"
        tsv.write_text(
            "account\tfollowers\tmedian\tviews\thook\n"
            "@a\t4000\t10000\t400000\tsome hook\n"
            "@b\t4000\t\t5000\tno median hook\n",
            encoding="utf-8",
        )
        proc = self._run(str(tsv))
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["classified"][0]["classification"] == "signal"
        assert data["missing"][0]["account"] == "@b"

    def test_cli_json_input(self, tmp_path):
        src = tmp_path / "rows.json"
        src.write_text(json.dumps([_row()]), encoding="utf-8")
        proc = self._run(str(src))
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["classified"][0]["outlier_multiple"] == 40.0

    def test_cli_user_followers_flag(self, tmp_path):
        src = tmp_path / "rows.json"
        src.write_text(json.dumps([_row(followers=2000000)]), encoding="utf-8")
        proc = self._run(str(src), "--user-followers", "4000")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["classified"][0]["classification"] == "out_of_range"

    def test_cli_no_rows_exits_2(self, tmp_path):
        src = tmp_path / "empty.json"
        src.write_text("[]", encoding="utf-8")
        proc = self._run(str(src))
        assert proc.returncode == 2
