#!/usr/bin/env python3
"""記号と語彙の機械検出チェック（stop-ai-slop-jp「クイックチェック」）。

下書きテキストを入力として、クイックチェックの記号レベル・語彙レベルの
項目を数え、上限を超えた項目を一覧で返す。検出項目がゼロ、または各項目が
上限以内なら通過とする。構造レベルと文・段落レベルは目視確認の対象であり、
このツールでは扱わない。

上限の根拠は SKILL.md と references/phrases.md である。

- 記号（全角ダッシュ、``**`` 残骸、コロン後の半角スペース、
  中黒の3項目並列、形容詞・心情のかぎ括弧）は上限0
- 装飾絵文字は1記事に2個まで
- AI偏愛語・必殺技造語・横文字メタファー・過剰なカタカナは
  1記事に合わせて上限まで（既定は各1個。複数撒かない）
- 翻訳調動詞は1記事に2個まで（多用を避ける）
- 副詞は1段落に1個まで（2個以上重ねない）
- 「○○すぎる」は1記事に2回まで（3回以上は不可）

使い方:
    python3 slop_check.py 下書き.txt
    python3 slop_check.py 下書き.txt --json
    cat 下書き.txt | python3 slop_check.py --sugiru-limit 3

終了コード: 0 = 通過、1 = 上限超過あり（提示を止める）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys

DEFAULT_SYMBOL_LIMIT = 0
DEFAULT_EMOJI_LIMIT = 2
DEFAULT_FAVORITE_LIMIT = 1
DEFAULT_KILLER_LIMIT = 1
DEFAULT_YOKOMOJI_LIMIT = 1
DEFAULT_KATAKANA_LIMIT = 1
DEFAULT_TRANSLATION_VERB_LIMIT = 2
DEFAULT_ADVERBS_PER_PARAGRAPH = 1
DEFAULT_SUGIRU_LIMIT = 2
DEFAULT_ACADEMIC_LIMIT = 0

DECORATIVE_EMOJI = "🚀🎯✨💡🔥📈"
FAVORITE_WORDS = (
    "泥臭さ",
    "手触り",
    "解像度",
    "熱量",
    "本質",
    "思想",
    "装置",
    "営み",
    "文脈",
)
KILLER_WORDS = ("真理", "虚飾", "禁欲的", "美学", "境地", "結末")
YOKOMOJI_METAPHORS = (
    "思考のOS",
    "ハック",
    "インストール",
    "リファクタリング",
    "ポートフォリオ",
)
KATAKANA_WORDS = ("コンテキスト", "アライメント", "コミュニケーション")
TRANSLATION_VERBS = ("指している", "示している", "物語っている", "収斂する")
ADVERBS = ("めっちゃ", "ガチで", "普通に", "かなり", "非常に")
ACADEMIC_WORDS = ("本稿", "本記事", "筆者")


def _count_words(text: str, words: tuple[str, ...]) -> tuple[int, list[str]]:
    found: list[str] = []
    for word in words:
        found.extend([word] * text.count(word))
    return len(found), found


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


class SlopChecker:
    """記号・語彙の検出項目を数え、上限と比べる。"""

    def __init__(
        self,
        symbol_limit: int = DEFAULT_SYMBOL_LIMIT,
        emoji_limit: int = DEFAULT_EMOJI_LIMIT,
        favorite_limit: int = DEFAULT_FAVORITE_LIMIT,
        killer_limit: int = DEFAULT_KILLER_LIMIT,
        yokomoji_limit: int = DEFAULT_YOKOMOJI_LIMIT,
        katakana_limit: int = DEFAULT_KATAKANA_LIMIT,
        translation_verb_limit: int = DEFAULT_TRANSLATION_VERB_LIMIT,
        adverbs_per_paragraph: int = DEFAULT_ADVERBS_PER_PARAGRAPH,
        sugiru_limit: int = DEFAULT_SUGIRU_LIMIT,
        academic_limit: int = DEFAULT_ACADEMIC_LIMIT,
    ) -> None:
        self.symbol_limit = symbol_limit
        self.emoji_limit = emoji_limit
        self.favorite_limit = favorite_limit
        self.killer_limit = killer_limit
        self.yokomoji_limit = yokomoji_limit
        self.katakana_limit = katakana_limit
        self.translation_verb_limit = translation_verb_limit
        self.adverbs_per_paragraph = adverbs_per_paragraph
        self.sugiru_limit = sugiru_limit
        self.academic_limit = academic_limit

    def check(self, text: str) -> dict:
        findings: list[dict] = []

        def add(item: str, count: int, limit: int, examples: list[str]) -> None:
            if count > limit:
                findings.append(
                    {
                        "item": item,
                        "count": count,
                        "limit": limit,
                        "examples": examples[:5],
                    }
                )

        def symbol(item: str, pattern: str) -> None:
            hits = re.findall(pattern, text)
            add(item, len(hits), self.symbol_limit, [str(h) for h in hits])

        symbol("全角ダッシュ", r"──|―|—")
        bold_spans = re.findall(r"\*\*[^*\n]+\*\*", text)
        leftover = re.sub(r"\*\*[^*\n]+\*\*", "", text).count("**")
        add(
            "アスタリスク残骸",
            len(bold_spans) + leftover,
            self.symbol_limit,
            bold_spans,
        )
        symbol("コロン後の半角スペース", r"[:：] (?=\S)")
        nakaguro = re.findall(r"\S+・\S+・\S+", text)
        add("中黒の3項目並列", len(nakaguro), self.symbol_limit, nakaguro)
        quoted = [
            m
            for m in re.findall(r"「([^」]{1,8})」", text)
            if "。" not in m and "、" not in m
        ]
        add("形容詞・心情のかぎ括弧", len(quoted), self.symbol_limit, quoted)
        emoji = [c for c in text if c in DECORATIVE_EMOJI]
        add("装飾絵文字", len(emoji), self.emoji_limit, emoji)

        count, found = _count_words(text, FAVORITE_WORDS)
        add("AI偏愛語", count, self.favorite_limit, found)
        count, found = _count_words(text, KILLER_WORDS)
        add("必殺技造語", count, self.killer_limit, found)
        count, found = _count_words(text, YOKOMOJI_METAPHORS)
        add("横文字メタファー", count, self.yokomoji_limit, found)
        count, found = _count_words(text, KATAKANA_WORDS)
        add("過剰なカタカナ", count, self.katakana_limit, found)
        count, found = _count_words(text, TRANSLATION_VERBS)
        add("翻訳調動詞", count, self.translation_verb_limit, found)

        stacked = []
        for para in _paragraphs(text):
            hits = [w for w in ADVERBS if w in para for _ in range(para.count(w))]
            if len(hits) > self.adverbs_per_paragraph:
                stacked.extend(hits)
        if stacked:
            findings.append(
                {
                    "item": "副詞の重なり（段落内）",
                    "count": len(stacked),
                    "limit": self.adverbs_per_paragraph,
                    "examples": stacked[:5],
                }
            )

        sugiru = re.findall(r"[^\s、。！？]+すぎる", text)
        add("○○すぎる", len(sugiru), self.sugiru_limit, sugiru)
        count, found = _count_words(text, ACADEMIC_WORDS)
        add("アカデミック自称", count, self.academic_limit, found)

        return {
            "decision": "fail" if findings else "pass",
            "passed": not findings,
            "findings": findings,
        }


def check(text: str, **kwargs: object) -> dict:
    """モジュール定数を既定値としてチェックする便利関数。"""
    return SlopChecker(**kwargs).check(text)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="記号と語彙の機械検出チェック")
    parser.add_argument("file", nargs="?", help="下書きファイル（省略時は標準入力）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sugiru-limit", type=int, default=DEFAULT_SUGIRU_LIMIT)
    parser.add_argument(
        "--adverbs-per-paragraph",
        type=int,
        default=DEFAULT_ADVERBS_PER_PARAGRAPH,
    )
    parser.add_argument("--favorite-limit", type=int, default=DEFAULT_FAVORITE_LIMIT)
    args = parser.parse_args(argv)

    text = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    result = SlopChecker(
        sugiru_limit=args.sugiru_limit,
        adverbs_per_paragraph=args.adverbs_per_paragraph,
        favorite_limit=args.favorite_limit,
    ).check(text)
    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
        print()
    elif result["passed"]:
        print("通過: 記号・語彙の検出項目はすべて上限以内です")
    else:
        print("不可: 次の項目が上限を超えています（提示を止めて直す）")
        for finding in result["findings"]:
            examples = "、".join(finding["examples"])
            print(
                f"  {finding['item']}: {finding['count']}件"
                f"（上限 {finding['limit']}）: {examples}"
            )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
