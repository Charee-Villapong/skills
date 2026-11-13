#!/usr/bin/env python3
"""overlap_judgement.py の仕様テスト。

仕様の出所は Issue #52 と SKILL.md「考え方」節だけである。
- 同じ段落に違う種類の癖が3つ以上重なったら直す
- 同じ癖が何回出ても1つと数える
- ★印の癖は1つ見つけたら直す
- 判定に必要な検出出力が欠けた場合は判定せず、不足を出す

    pytest tests/test_overlap_judgement.py
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import overlap_judgement as oj  # noqa: E402

SCRIPT = os.path.join(ROOT, "scripts", "overlap_judgement.py")


def payload(*paragraph_kinds):
    return {
        "paragraphs": [
            {"paragraph": i + 1, "kinds": kinds}
            for i, kinds in enumerate(paragraph_kinds)
        ]
    }


class TestJudge:
    def test_three_distinct_kinds_in_one_paragraph_need_revision(self):
        r = oj.judge(payload(["癖A", "癖B", "癖C"]))
        assert r["decision"] == "revise"
        assert r["needs_revision"] is True

    def test_two_distinct_kinds_do_not_need_revision(self):
        r = oj.judge(payload(["癖A", "癖B"]))
        assert r["decision"] == "no_revise"
        assert r["needs_revision"] is False

    def test_same_kind_repeated_counts_once(self):
        r = oj.judge(payload(["癖A", "癖A", "癖A"]))
        assert r["decision"] == "no_revise"

    def test_kinds_split_across_paragraphs_do_not_add_up(self):
        r = oj.judge(payload(["癖A", "癖B"], ["癖C", "癖D"]))
        assert r["decision"] == "no_revise"

    def test_single_star_kind_needs_revision(self):
        r = oj.judge(payload(["★太字（**）"]))
        assert r["decision"] == "revise"

    def test_star_kind_in_any_paragraph_needs_revision(self):
        r = oj.judge(payload(["癖A"], ["★全角ダッシュ"]))
        assert r["decision"] == "revise"
        assert any("★全角ダッシュ" in reason for reason in r["reasons"])

    def test_clean_input_needs_no_revision(self):
        r = oj.judge(payload([]))
        assert r["decision"] == "no_revise"
        assert r["reasons"] == []

    def test_reason_names_the_paragraph_and_kinds(self):
        r = oj.judge(payload(["癖A"], ["癖A", "癖B", "癖C"]))
        assert any("段落2" in reason for reason in r["reasons"])


class TestInsufficientInput:
    def test_missing_paragraphs_key_is_insufficient(self):
        r = oj.judge({})
        assert r["decision"] == "insufficient"
        assert r["needs_revision"] is None
        assert "paragraphs" in r["missing"]

    def test_paragraph_without_kinds_is_insufficient(self):
        r = oj.judge({"paragraphs": [{"paragraph": 1}]})
        assert r["decision"] == "insufficient"
        assert r["missing"]

    def test_non_dict_input_is_insufficient(self):
        r = oj.judge(["not", "a", "dict"])
        assert r["decision"] == "insufficient"


class TestThresholdsAreVariables:
    def test_min_kinds_can_be_changed(self):
        data = payload(["癖A", "癖B"])
        assert oj.judge(data)["decision"] == "no_revise"
        assert oj.judge(data, min_kinds=2)["decision"] == "revise"

    def test_defaults_match_skill(self):
        assert oj.DEFAULT_MIN_KINDS == 3
        assert oj.DEFAULT_STAR_MIN == 1


class TestCli:
    def run_cli(self, data, *extra):
        proc = subprocess.run(
            [sys.executable, SCRIPT, *extra],
            input=json.dumps(data),
            capture_output=True,
            text=True,
        )
        return proc, json.loads(proc.stdout)

    def test_cli_revise_exits_1(self):
        proc, out = self.run_cli(payload(["★太字（**）"]))
        assert proc.returncode == 1
        assert out["decision"] == "revise"

    def test_cli_no_revise_exits_0(self):
        proc, out = self.run_cli(payload(["癖A"]))
        assert proc.returncode == 0
        assert out["decision"] == "no_revise"

    def test_cli_insufficient_exits_2(self):
        proc, out = self.run_cli({})
        assert proc.returncode == 2
        assert out["decision"] == "insufficient"

    def test_cli_min_kinds_option(self):
        proc, out = self.run_cli(payload(["癖A", "癖B"]), "--min-kinds", "2")
        assert proc.returncode == 1
        assert out["decision"] == "revise"
