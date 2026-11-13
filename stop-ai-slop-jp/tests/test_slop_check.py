#!/usr/bin/env python3
"""slop_check.py の仕様テスト。

仕様の出所は Issue #53 と SKILL.md「クイックチェック」の記号レベル・
語彙レベルだけである。
- 検出項目がゼロ、または各項目が上限以内なら通過
- 上限を超えた項目は一覧で出し、通過させない
- 上限の根拠: 副詞は1段落に2個以上重ねない、○○すぎるは1記事に
  3回以上使わない、偏愛語・必殺技造語は1記事に複数撒かない

    pytest tests/test_slop_check.py
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import slop_check as sc  # noqa: E402

SCRIPT = os.path.join(ROOT, "scripts", "slop_check.py")
CLEAN = "昨日は駅まで歩いた。途中で雨が降ったので、喫茶店に入った。"


def items(result):
    return {f["item"]: f for f in result["findings"]}


class TestCleanText:
    def test_clean_text_passes_with_no_findings(self):
        r = sc.check(CLEAN)
        assert r["passed"] is True
        assert r["decision"] == "pass"
        assert r["findings"] == []


class TestSymbols:
    def test_fullwidth_dash_fails(self):
        r = sc.check("結論は単純だった──はずだ。")
        assert r["passed"] is False
        assert items(r)["全角ダッシュ"]["count"] >= 1

    def test_bold_residue_fails(self):
        r = sc.check("**重要**なのは速度だ。")
        assert items(r)["アスタリスク残骸"]["count"] == 1

    def test_colon_halfwidth_space_fails(self):
        r = sc.check("結論: 速度が大事だ。")
        assert items(r)["コロン後の半角スペース"]["count"] == 1

    def test_nakaguro_three_items_fail(self):
        r = sc.check("対象は速度・精度・費用だ。")
        assert items(r)["中黒の3項目並列"]["count"] == 1

    def test_nakaguro_two_items_pass(self):
        r = sc.check("対象は速度・精度だ。")
        assert "中黒の3項目並列" not in items(r)

    def test_quoted_adjective_fails(self):
        r = sc.check("この作業は「軽い」ものだ。")
        assert items(r)["形容詞・心情のかぎ括弧"]["count"] == 1

    def test_decorative_emoji_over_limit_fails(self):
        r = sc.check("公開した🚀 次も公開した🎯 さらに公開した✨")
        assert items(r)["装飾絵文字"]["count"] == 3
        assert r["passed"] is False

    def test_one_decorative_emoji_within_limit(self):
        r = sc.check("公開した🚀")
        assert r["passed"] is True


class TestVocabulary:
    def test_two_favorite_words_fail(self):
        r = sc.check("大事なのは本質だ。現場の熱量も要る。")
        f = items(r)["AI偏愛語"]
        assert f["count"] == 2
        assert r["passed"] is False

    def test_one_favorite_word_within_limit(self):
        r = sc.check("大事なのは本質だ。")
        assert r["passed"] is True

    def test_two_killer_words_fail(self):
        r = sc.check("そこに真理があった。美学の問題でもある。")
        assert items(r)["必殺技造語"]["count"] == 2
        assert r["passed"] is False

    def test_yokomoji_metaphors_fail_when_scattered(self):
        r = sc.check("思考のOSを変えた。人生をハックした。")
        assert items(r)["横文字メタファー"]["count"] >= 2
        assert r["passed"] is False

    def test_katakana_overuse_fails_when_scattered(self):
        r = sc.check("コンテキストを共有し、アライメントを取った。")
        assert items(r)["過剰なカタカナ"]["count"] == 2
        assert r["passed"] is False

    def test_translation_verbs_over_limit_fail(self):
        r = sc.check(
            "結果が同じ方向を指している。変化を示している。背景を物語っている。"
        )
        assert items(r)["翻訳調動詞"]["count"] == 3
        assert r["passed"] is False

    def test_adverbs_stacked_in_one_paragraph_fail(self):
        r = sc.check("めっちゃ速くてガチで驚いた。")
        assert items(r)["副詞の重なり（段落内）"]["count"] >= 1
        assert r["passed"] is False

    def test_adverbs_split_across_paragraphs_pass(self):
        r = sc.check("めっちゃ速かった。\n\nガチで驚いた。")
        assert "副詞の重なり（段落内）" not in items(r)

    def test_sugiru_three_times_fails(self):
        r = sc.check("美味しすぎる。楽しすぎる。嬉しすぎる。")
        assert items(r)["○○すぎる"]["count"] == 3
        assert r["passed"] is False

    def test_sugiru_twice_within_limit(self):
        r = sc.check("美味しすぎる。楽しすぎる。")
        assert r["passed"] is True

    def test_academic_self_reference_fails(self):
        r = sc.check("本稿では速度を扱う。")
        assert items(r)["アカデミック自称"]["count"] == 1


class TestLimitsAreVariables:
    def test_sugiru_limit_can_be_changed(self):
        text = "美味しすぎる。楽しすぎる。"
        assert sc.check(text)["passed"] is True
        assert sc.check(text, sugiru_limit=1)["passed"] is False

    def test_defaults_match_skill(self):
        assert sc.DEFAULT_SUGIRU_LIMIT == 2
        assert sc.DEFAULT_ADVERBS_PER_PARAGRAPH == 1
        assert sc.DEFAULT_FAVORITE_LIMIT == 1


class TestCli:
    def run_cli(self, text, *extra):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--json", *extra],
            input=text,
            capture_output=True,
            text=True,
        )
        return proc, json.loads(proc.stdout)

    def test_cli_fail_exits_1_and_lists_findings(self):
        proc, out = self.run_cli("**重要**だ──。")
        assert proc.returncode == 1
        assert out["decision"] == "fail"
        assert len(out["findings"]) >= 2

    def test_cli_pass_exits_0(self):
        proc, out = self.run_cli(CLEAN)
        assert proc.returncode == 0
        assert out["decision"] == "pass"
