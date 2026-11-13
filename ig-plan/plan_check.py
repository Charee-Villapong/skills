#!/usr/bin/env python3
"""
plan_check.py - check the composition of a weekly Instagram plan.

Implements the judgement in ig-plan/SKILL.md, "What to post":

- four to five posts a week, at least three of them Reels
- never two posts of the same type back to back
- per-type weekly counts and formats:

  =======  ===========  ==================
  type     per week     format
  =======  ===========  ==================
  Proof    1            Reel
  Teach    1 to 2       Reel or Carousel
  Opinion  1            Reel
  Story    0 to 1 (*)   Reel
  Offer    0 to 1 (*)   Carousel or Stories
  =======  ===========  ==================

  (*) Story and Offer are "1 per fortnight" in the skill, so a single
  week carries at most one of each and may carry none.

The limits are variables, not fixed numbers in the logic: the weekly
totals are module constants overridable from the CLI, and the per-type
counts and formats live in ``TYPE_RULES``.

Usage
  python3 plan_check.py plan.json
  python3 plan_check.py plan.json --min-posts 4 --max-posts 5 --min-reels 3

Input JSON
  {"posts": [{"type": "Proof", "format": "Reel"}, ...]}

The posts list is ordered: the back-to-back check uses that order.
Type and format names are case-insensitive.

Output is JSON on stdout: {"ok", "violations", "counts"}.
Exit code 0 when the plan passes, 1 when it has violations,
2 on usage or input errors.
"""

import argparse
import json
import sys

DEFAULT_MIN_POSTS = 4
DEFAULT_MAX_POSTS = 5
DEFAULT_MIN_REELS = 3

# Per-type rules from the skill table. "min"/"max" are posts per week;
# Story and Offer are 1 per fortnight, hence min 0 / max 1 per week.
TYPE_RULES = {
    "Proof": {"min": 1, "max": 1, "formats": ("Reel",)},
    "Teach": {"min": 1, "max": 2, "formats": ("Reel", "Carousel")},
    "Opinion": {"min": 1, "max": 1, "formats": ("Reel",)},
    "Story": {"min": 0, "max": 1, "formats": ("Reel",)},
    "Offer": {"min": 0, "max": 1, "formats": ("Carousel", "Stories")},
}

_CANONICAL_TYPES = {name.lower(): name for name in TYPE_RULES}
_CANONICAL_FORMATS = {
    "reel": "Reel",
    "carousel": "Carousel",
    "stories": "Stories",
    "story": "Stories",
}


def _canonical_type(value):
    return _CANONICAL_TYPES.get(str(value or "").strip().lower())


def _canonical_format(value):
    return _CANONICAL_FORMATS.get(str(value or "").strip().lower())


class WeeklyPlanChecker:
    """Check a weekly plan dict against the "What to post" rules."""

    def __init__(
        self,
        min_posts=DEFAULT_MIN_POSTS,
        max_posts=DEFAULT_MAX_POSTS,
        min_reels=DEFAULT_MIN_REELS,
        type_rules=None,
    ):
        self.min_posts = min_posts
        self.max_posts = max_posts
        self.min_reels = min_reels
        self.type_rules = type_rules or TYPE_RULES

    def check(self, plan):
        violations = []

        def add(code, message, **extra):
            violations.append({"code": code, "message": message, **extra})

        raw_posts = list((plan or {}).get("posts") or [])
        posts = []
        for index, entry in enumerate(raw_posts):
            type_name = _canonical_type(entry.get("type"))
            format_name = _canonical_format(entry.get("format"))
            if type_name is None:
                add(
                    "unknown_type",
                    f"post {index}: unknown type {entry.get('type')!r}",
                    index=index,
                )
            if format_name is None:
                add(
                    "unknown_format",
                    f"post {index}: unknown format {entry.get('format')!r}",
                    index=index,
                )
            posts.append({"type": type_name, "format": format_name})

        by_type = {name: 0 for name in self.type_rules}
        for entry in posts:
            if entry["type"] in by_type:
                by_type[entry["type"]] += 1
        reels = sum(1 for entry in posts if entry["format"] == "Reel")
        counts = {"total": len(posts), "reels": reels, "by_type": by_type}

        if not self.min_posts <= len(posts) <= self.max_posts:
            add(
                "total_posts",
                f"weekly posts must be {self.min_posts} to "
                f"{self.max_posts}, got {len(posts)}",
            )
        if reels < self.min_reels:
            add(
                "min_reels",
                f"Reels must be at least {self.min_reels}, got {reels}",
            )

        for index in range(1, len(posts)):
            current, previous = posts[index], posts[index - 1]
            if current["type"] is not None and current["type"] == previous["type"]:
                add(
                    "consecutive_same_type",
                    f"posts {index - 1} and {index} are both "
                    f"{current['type']}; never two of the same type "
                    "back to back",
                    index=index,
                )

        for name, rule in self.type_rules.items():
            count = by_type[name]
            if not rule["min"] <= count <= rule["max"]:
                add(
                    "type_count",
                    f"{name} must be {rule['min']} to {rule['max']} "
                    f"per week, got {count}",
                    type=name,
                )

        for index, entry in enumerate(posts):
            if entry["type"] is None or entry["format"] is None:
                continue
            allowed = self.type_rules[entry["type"]]["formats"]
            if entry["format"] not in allowed:
                add(
                    "format_for_type",
                    f"post {index}: {entry['type']} must be "
                    f"{' or '.join(allowed)}, got {entry['format']}",
                    index=index,
                )

        return {"ok": not violations, "violations": violations, "counts": counts}


def check_plan(plan, **kwargs):
    """Check ``plan`` with a WeeklyPlanChecker built from ``kwargs``."""
    return WeeklyPlanChecker(**kwargs).check(plan)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the composition of a weekly Instagram plan."
    )
    parser.add_argument("plan", help="plan JSON file")
    parser.add_argument("--min-posts", type=int, default=DEFAULT_MIN_POSTS)
    parser.add_argument("--max-posts", type=int, default=DEFAULT_MAX_POSTS)
    parser.add_argument("--min-reels", type=int, default=DEFAULT_MIN_REELS)
    args = parser.parse_args(argv)

    try:
        with open(args.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read plan: {exc}", file=sys.stderr)
        return 2

    checker = WeeklyPlanChecker(
        min_posts=args.min_posts,
        max_posts=args.max_posts,
        min_reels=args.min_reels,
    )
    result = checker.check(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
