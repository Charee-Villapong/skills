#!/usr/bin/env python3
"""癖の重なり判定（natural-japanese-writing「考え方」節の機械化）。

機械検出（scripts/check.py）の出力を入力として、修正が要るかを判定する。
判定ルールは SKILL.md「考え方」節が正本である。

- 同じ段落に違う種類の癖が ``min_kinds`` 種以上重なったら直す
  （同じ癖が何回出ても1種と数える）
- ★印の癖は ``star_min`` 個見つけたら直す（既定は1個）
- 判定に必要な検出出力が欠けた場合は判定せず、不足分を出す

入力は JSON で、段落ごとの癖の種類を次の形で渡す。
check.py の ``paragraph_scores`` の出力がそのまま使える。

    {"paragraphs": [{"paragraph": 1, "kinds": ["★太字（**）", "癖A"]}]}

使い方:
    python3 check.py 文章.md --json | python3 overlap_judgement.py --from-check
    python3 overlap_judgement.py 入力.json
    cat 入力.json | python3 overlap_judgement.py
    python3 overlap_judgement.py 入力.json --min-kinds 2

``--from-check`` は check.py の JSON 出力（``dense_paragraphs`` と
``star_total``）を受け付ける形である。段落ごとの内訳が無い出力では、
★の有無と重なった段落の有無だけから判定する。

終了コード: 0 = 修正不要、1 = 修正が必要、2 = 入力不足で判定しない。
出力は常に JSON である。
"""

from __future__ import annotations

import argparse
import json
import sys

DEFAULT_MIN_KINDS = 3
DEFAULT_STAR_MIN = 1
STAR_PREFIX = "★"


class OverlapJudgement:
    """段落ごとの癖の重なりから修正要否を判定する。"""

    def __init__(
        self,
        min_kinds: int = DEFAULT_MIN_KINDS,
        star_min: int = DEFAULT_STAR_MIN,
    ) -> None:
        self.min_kinds = min_kinds
        self.star_min = star_min

    def judge(self, data: object) -> dict:
        """検出出力 ``data`` を判定し、結果を dict で返す。"""
        missing = self._missing_fields(data)
        if missing:
            return {
                "decision": "insufficient",
                "needs_revision": None,
                "missing": missing,
                "reasons": [],
                "min_kinds": self.min_kinds,
                "star_min": self.star_min,
            }
        reasons: list[str] = []
        for entry in data["paragraphs"]:  # type: ignore[index]
            kinds = list(dict.fromkeys(entry["kinds"]))
            number = entry.get("paragraph")
            star_kinds = [k for k in kinds if k.startswith(STAR_PREFIX)]
            if len(star_kinds) >= self.star_min:
                reasons.append(
                    f"段落{number}: ★の癖が{len(star_kinds)}種ある"
                    f"（{'、'.join(star_kinds)}）"
                )
            if len(kinds) >= self.min_kinds:
                reasons.append(
                    f"段落{number}: 違う種類の癖が{len(kinds)}種重なっている"
                    f"（{'、'.join(kinds)}）"
                )
        return {
            "decision": "revise" if reasons else "no_revise",
            "needs_revision": bool(reasons),
            "missing": [],
            "reasons": reasons,
            "min_kinds": self.min_kinds,
            "star_min": self.star_min,
        }

    @staticmethod
    def _missing_fields(data: object) -> list[str]:
        if not isinstance(data, dict):
            return ["paragraphs"]
        paragraphs = data.get("paragraphs")
        if not isinstance(paragraphs, list):
            return ["paragraphs"]
        missing = []
        for i, entry in enumerate(paragraphs):
            if not isinstance(entry, dict) or not isinstance(entry.get("kinds"), list):
                missing.append(f"paragraphs[{i}].kinds")
        return missing


def judge(
    data: object,
    min_kinds: int = DEFAULT_MIN_KINDS,
    star_min: int = DEFAULT_STAR_MIN,
) -> dict:
    """モジュール定数を既定値として判定する便利関数。"""
    return OverlapJudgement(min_kinds=min_kinds, star_min=star_min).judge(data)


def from_check_output(data: object) -> dict | None:
    """check.py の JSON 出力を段落形式へ変換する。変換不能なら None。"""
    if not isinstance(data, dict):
        return None
    if "paragraphs" in data:
        return data
    dense = data.get("dense_paragraphs")
    star_total = data.get("star_total")
    if not isinstance(dense, list) or not isinstance(star_total, int):
        return None
    paragraphs = [
        {"paragraph": p.get("paragraph"), "kinds": list(p.get("kinds") or [])}
        for p in dense
        if isinstance(p, dict)
    ]
    if star_total > 0 and not any(
        k.startswith(STAR_PREFIX) for p in paragraphs for k in p["kinds"]
    ):
        paragraphs.append({"paragraph": None, "kinds": ["★（詳細不明）"]})
    return {"paragraphs": paragraphs}


_EXIT_CODES = {"no_revise": 0, "revise": 1, "insufficient": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="癖の重なり判定")
    parser.add_argument(
        "file", nargs="?", help="入力 JSON ファイル（省略時は標準入力）"
    )
    parser.add_argument("--min-kinds", type=int, default=DEFAULT_MIN_KINDS)
    parser.add_argument("--star-min", type=int, default=DEFAULT_STAR_MIN)
    parser.add_argument(
        "--from-check",
        action="store_true",
        help="check.py の JSON 出力を入力として受け付ける",
    )
    args = parser.parse_args(argv)

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if args.from_check:
        converted = from_check_output(data)
        data = converted if converted is not None else data
    result = judge(data, min_kinds=args.min_kinds, star_min=args.star_min)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return _EXIT_CODES[result["decision"]]


if __name__ == "__main__":
    sys.exit(main())
