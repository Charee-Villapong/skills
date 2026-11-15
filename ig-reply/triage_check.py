#!/usr/bin/env python3
"""
triage_check.py - check the shape of an ig-reply triage result.

Checks the parts of the ig-reply "Triage first" section that can be
decided from the sorted result alone, once every comment has been read
and assigned:

- every comment sits in exactly one of the six buckets (KEYWORD, LEAD,
  SUBSTANCE, QUESTION, SUPPORT, NOISE) and in no second bucket,
- the counts about to be stated match the assignments, per bucket and
  in total,
- the buckets follow the fixed writing order: KEYWORD, then LEAD,
  SUBSTANCE, QUESTION, SUPPORT, NOISE,
- a SUPPORT reply is at most eight words (a like alone is fine),
- a NOISE reply is nothing, or one line at most.

The bucket order and the SUPPORT word limit are variables, not fixed
values in the logic. The defaults follow the skill.

Which bucket a comment belongs to needs the reading itself and cannot
be decided here; that judgement stays in SKILL.md.

Usage
  python3 triage_check.py triage.json
  cat triage.json | python3 triage_check.py
  python3 triage_check.py --max-support-words 5 triage.json

The input is JSON: {"total": <stated total, optional>,
"stated_counts": {<bucket>: <count>, optional}, "items":
[{"comment": "...", "bucket": "KEYWORD", "reply": "..."}]}.
Prints {"ok", "total", "counts", "violations"} as JSON, where each
violation is {"code", "detail"}. Exit code is 0 when ok, 1 otherwise.
"""

import argparse
import json
import sys
from pathlib import Path

BUCKETS = ("KEYWORD", "LEAD", "SUBSTANCE", "QUESTION", "SUPPORT", "NOISE")

DEFAULT_MAX_SUPPORT_WORDS = 8


def count_words(text):
    return len((text or "").split())


def count_lines(text):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return len(lines)


class TriageChecker:
    """List shape violations in one triage result."""

    def __init__(
        self,
        buckets=BUCKETS,
        max_support_words=DEFAULT_MAX_SUPPORT_WORDS,
    ):
        self.buckets = tuple(buckets)
        self.max_support_words = max_support_words

    def check(self, data):
        violations = []

        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            violations.append(
                {
                    "code": "invalid_input",
                    "detail": "input must be an object with an items list",
                }
            )
            return {"ok": False, "total": 0, "counts": {}, "violations": violations}

        items = data["items"]
        counts = {bucket: 0 for bucket in self.buckets}
        seen_comments = {}
        rank = {bucket: index for index, bucket in enumerate(self.buckets)}
        max_rank = -1

        for position, item in enumerate(items):
            if not isinstance(item, dict):
                violations.append(
                    {
                        "code": "invalid_input",
                        "detail": f"item {position} is not an object",
                    }
                )
                continue
            bucket = item.get("bucket")
            comment = item.get("comment") or ""
            reply = item.get("reply") or ""

            if bucket not in rank:
                violations.append(
                    {
                        "code": "unknown_bucket",
                        "detail": f"item {position} has bucket {bucket!r}",
                    }
                )
                continue

            counts[bucket] += 1

            if comment:
                if comment in seen_comments:
                    violations.append(
                        {
                            "code": "duplicate_comment",
                            "detail": (
                                f"comment appears twice: items "
                                f"{seen_comments[comment]} and {position}"
                            ),
                        }
                    )
                else:
                    seen_comments[comment] = position

            if rank[bucket] < max_rank:
                violations.append(
                    {
                        "code": "wrong_order",
                        "detail": (
                            f"item {position} is {bucket}, which comes "
                            f"before an earlier bucket in the fixed order"
                        ),
                    }
                )
            else:
                max_rank = rank[bucket]

            if bucket == "SUPPORT":
                words = count_words(reply)
                if words > self.max_support_words:
                    violations.append(
                        {
                            "code": "support_reply_too_long",
                            "detail": (
                                f"item {position} SUPPORT reply is {words} "
                                f"words, limit is {self.max_support_words}"
                            ),
                        }
                    )
            if bucket == "NOISE":
                lines = count_lines(reply)
                if lines > 1:
                    violations.append(
                        {
                            "code": "noise_reply_too_long",
                            "detail": (
                                f"item {position} NOISE reply is {lines} "
                                f"lines, limit is 1"
                            ),
                        }
                    )

        total = len(items)

        stated_counts = data.get("stated_counts")
        if stated_counts is not None:
            if not isinstance(stated_counts, dict):
                violations.append(
                    {
                        "code": "invalid_input",
                        "detail": "stated_counts must be an object",
                    }
                )
            else:
                for bucket, stated in stated_counts.items():
                    if bucket not in rank:
                        violations.append(
                            {
                                "code": "unknown_bucket",
                                "detail": f"stated_counts has bucket {bucket!r}",
                            }
                        )
                    elif stated != counts[bucket]:
                        violations.append(
                            {
                                "code": "count_mismatch",
                                "detail": (
                                    f"{bucket} stated {stated}, "
                                    f"actual {counts[bucket]}"
                                ),
                            }
                        )

        stated_total = data.get("total")
        if stated_total is not None and stated_total != total:
            violations.append(
                {
                    "code": "total_mismatch",
                    "detail": f"total stated {stated_total}, actual {total}",
                }
            )

        return {
            "ok": not violations,
            "total": total,
            "counts": counts,
            "violations": violations,
        }


def _load_input(path):
    if path is None or path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the shape of an ig-reply triage result."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="triage result JSON file (default: stdin)",
    )
    parser.add_argument("--max-support-words", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        data = _load_input(args.path)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "total": 0,
                    "counts": {},
                    "violations": [
                        {"code": "invalid_input", "detail": f"cannot read input: {exc}"}
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 1

    checker = TriageChecker(
        max_support_words=(
            args.max_support_words
            if args.max_support_words is not None
            else DEFAULT_MAX_SUPPORT_WORDS
        )
    )
    result = checker.check(data)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
