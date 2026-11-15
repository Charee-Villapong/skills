"""triage_check.py の仕様テスト（完了の定義から先に書いたテスト）。

対象仕様: ig-reply/SKILL.md「Triage first」節と Issue #68。
- 全コメントを6区分（KEYWORD / LEAD / SUBSTANCE / QUESTION / SUPPORT /
  NOISE）のいずれか1つだけに分類する
- 提示する件数は実数と一致させる（区分ごとの件数と合計）
- 書く順序は固定: KEYWORD → LEAD → SUBSTANCE → QUESTION → SUPPORT →
  NOISE
- SUPPORT の返信は最大8語（いいねだけでもよい）
- NOISE の返信は無し、または1行まで
- 区分の判定（どのコメントがどの区分か）は意味の判断なので対象外。
  対象は振り分け結果の形の検査だけ
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from triage_check import TriageChecker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "triage_check.py"

BUCKETS = ("KEYWORD", "LEAD", "SUBSTANCE", "QUESTION", "SUPPORT", "NOISE")


def valid_data():
    return {
        "total": 6,
        "stated_counts": {
            "KEYWORD": 1,
            "LEAD": 1,
            "SUBSTANCE": 1,
            "QUESTION": 1,
            "SUPPORT": 1,
            "NOISE": 1,
        },
        "items": [
            {"comment": "CLAUSE", "bucket": "KEYWORD", "reply": "Sent."},
            {
                "comment": "we had this exact thing happen in June",
                "bucket": "LEAD",
                "reply": "The bit that fixed it for us was the trigger.",
            },
            {
                "comment": "your numbers ignore renewals",
                "bucket": "SUBSTANCE",
                "reply": "Fair point, renewals change the picture.",
            },
            {
                "comment": "what if they refuse to sign it?",
                "bucket": "QUESTION",
                "reply": "",
            },
            {"comment": "great post", "bucket": "SUPPORT", "reply": "Glad it helped"},
            {"comment": "check my page", "bucket": "NOISE", "reply": ""},
        ],
    }


def codes(result):
    return [violation["code"] for violation in result["violations"]]


class TestValidTriage:
    def test_valid_triage_passes(self):
        result = TriageChecker().check(valid_data())
        assert result["ok"] is True
        assert result["violations"] == []

    def test_counts_and_total_are_reported_for_all_buckets(self):
        result = TriageChecker().check(valid_data())
        assert result["total"] == 6
        assert result["counts"] == {bucket: 1 for bucket in BUCKETS}

    def test_stated_counts_and_total_are_optional(self):
        data = valid_data()
        del data["total"]
        del data["stated_counts"]
        result = TriageChecker().check(data)
        assert result["ok"] is True
        assert result["total"] == 6

    def test_empty_triage_passes_with_zero_counts(self):
        result = TriageChecker().check({"total": 0, "items": []})
        assert result["ok"] is True
        assert result["total"] == 0
        assert result["counts"] == {bucket: 0 for bucket in BUCKETS}


class TestCompleteness:
    def test_unknown_bucket_is_a_violation(self):
        data = valid_data()
        data["items"][0]["bucket"] = "FAN"
        del data["stated_counts"]
        del data["total"]
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "unknown_bucket" in codes(result)

    def test_missing_bucket_is_a_violation(self):
        data = valid_data()
        del data["items"][1]["bucket"]
        del data["stated_counts"]
        del data["total"]
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "unknown_bucket" in codes(result)

    def test_same_comment_in_two_buckets_is_a_violation(self):
        data = valid_data()
        data["items"][1]["comment"] = data["items"][0]["comment"]
        del data["stated_counts"]
        del data["total"]
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "duplicate_comment" in codes(result)


class TestCounts:
    def test_stated_count_mismatch_is_a_violation(self):
        data = valid_data()
        data["stated_counts"]["KEYWORD"] = 41
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "count_mismatch" in codes(result)

    def test_stated_total_mismatch_is_a_violation(self):
        data = valid_data()
        data["total"] = 84
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "total_mismatch" in codes(result)

    def test_unknown_bucket_in_stated_counts_is_a_violation(self):
        data = valid_data()
        data["stated_counts"]["FAN"] = 1
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "unknown_bucket" in codes(result)


class TestOrder:
    def test_out_of_order_buckets_are_a_violation(self):
        data = valid_data()
        data["items"][0], data["items"][1] = data["items"][1], data["items"][0]
        del data["stated_counts"]
        del data["total"]
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "wrong_order" in codes(result)

    def test_same_bucket_grouping_is_fine(self):
        data = valid_data()
        extra = dict(data["items"][0])
        extra["comment"] = "WORD"
        data["items"].insert(1, extra)
        del data["stated_counts"]
        del data["total"]
        result = TriageChecker().check(data)
        assert result["ok"] is True
        assert result["counts"]["KEYWORD"] == 2


class TestSupportLength:
    def test_support_reply_of_eight_words_passes(self):
        data = valid_data()
        data["items"][4]["reply"] = "one two three four five six seven eight"
        result = TriageChecker().check(data)
        assert result["ok"] is True

    def test_support_reply_of_nine_words_is_a_violation(self):
        data = valid_data()
        data["items"][4]["reply"] = "one two three four five six seven eight nine"
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "support_reply_too_long" in codes(result)

    def test_support_without_reply_passes(self):
        data = valid_data()
        del data["items"][4]["reply"]
        result = TriageChecker().check(data)
        assert result["ok"] is True

    def test_support_word_limit_is_a_variable(self):
        data = valid_data()
        data["items"][4]["reply"] = "one two three four"
        result = TriageChecker(max_support_words=3).check(data)
        assert result["ok"] is False
        assert "support_reply_too_long" in codes(result)


class TestNoiseForm:
    def test_noise_with_one_line_reply_passes(self):
        data = valid_data()
        data["items"][5]["reply"] = "No."
        result = TriageChecker().check(data)
        assert result["ok"] is True

    def test_noise_with_two_line_reply_is_a_violation(self):
        data = valid_data()
        data["items"][5]["reply"] = "No.\nReally, no."
        result = TriageChecker().check(data)
        assert result["ok"] is False
        assert "noise_reply_too_long" in codes(result)


class TestInputShape:
    def test_missing_items_is_a_violation(self):
        result = TriageChecker().check({"total": 3})
        assert result["ok"] is False
        assert "invalid_input" in codes(result)

    def test_non_dict_input_is_a_violation(self):
        result = TriageChecker().check(["not", "a", "dict"])
        assert result["ok"] is False
        assert "invalid_input" in codes(result)


class TestCli:
    def _run(self, payload, *extra_args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *extra_args],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    def test_cli_valid_input_exits_zero(self):
        proc = self._run(valid_data())
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["ok"] is True

    def test_cli_violation_exits_one(self):
        data = valid_data()
        data["total"] = 99
        proc = self._run(data)
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["ok"] is False

    def test_cli_reads_a_file(self, tmp_path):
        path = tmp_path / "triage.json"
        path.write_text(json.dumps(valid_data()), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["ok"] is True

    def test_cli_max_support_words_option(self):
        data = valid_data()
        data["items"][4]["reply"] = "one two three four"
        proc = self._run(data, "--max-support-words", "3")
        assert proc.returncode == 1
        assert "support_reply_too_long" in codes(json.loads(proc.stdout))
