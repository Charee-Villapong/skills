#!/usr/bin/env python3
"""
extract_check.py - judge whether extracted material is too thin.

For the ig-repurpose "Extract, do not summarise" section: list what was
found, with counts, before writing anything. If the asset yields fewer
items than the minimum, it is thin, and posts squeezed out of it will
be thin too - say that instead of proceeding to the weekly plan.

The categories, the minimum total and the maximum recommended posts
are variables, not fixed values in the logic. The defaults follow the
skill: six categories, a minimum of four items in total, and at most
six recommended posts from one asset.

Usage
  python3 extract_check.py --claims 5 --numbers 9 --stories 3 \\
      --mechanisms 4 --mistakes 2 --lines 7
  python3 extract_check.py --input counts.json

Prints {"counts", "total", "is_thin", "verdict", "can_proceed",
"recommended_posts", "message"} as JSON. Exit code is 0 when the
material is sufficient, 1 when it is thin.
"""

import argparse
import json
import sys
from pathlib import Path

CATEGORIES = (
    "claims",
    "numbers",
    "stories",
    "mechanisms",
    "mistakes",
    "lines",
)

DEFAULT_MIN_TOTAL = 4
DEFAULT_MAX_RECOMMENDED_POSTS = 6


class ExtractChecker:
    """Assess extraction counts and judge the material's thinness."""

    def __init__(
        self,
        categories=CATEGORIES,
        min_total=DEFAULT_MIN_TOTAL,
        max_recommended_posts=DEFAULT_MAX_RECOMMENDED_POSTS,
    ):
        self.categories = tuple(categories)
        self.min_total = min_total
        self.max_recommended_posts = max_recommended_posts

    def _normalise(self, counts):
        unknown = set(counts) - set(self.categories)
        if unknown:
            raise ValueError(f"unknown categories: {sorted(unknown)}")
        normalised = {}
        for category in self.categories:
            value = counts.get(category, 0)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"count for {category} must be an integer")
            if value < 0:
                raise ValueError(f"count for {category} must not be negative")
            normalised[category] = value
        return normalised

    def assess(self, counts):
        normalised = self._normalise(dict(counts or {}))
        total = sum(normalised.values())
        is_thin = total < self.min_total
        if is_thin:
            recommended = total
            message = (
                f"Thin material: only {total} items found, below the "
                f"minimum of {self.min_total}. Do not squeeze four "
                "posts out of it; narrow the plan to at most "
                f"{recommended} post(s) or use a richer asset."
            )
        else:
            recommended = min(total, self.max_recommended_posts)
            message = (
                f"Sufficient material: {total} items found. "
                f"Proceed to the weekly plan with {recommended} post(s)."
            )
        return {
            "counts": normalised,
            "total": total,
            "is_thin": is_thin,
            "verdict": "thin" if is_thin else "sufficient",
            "can_proceed": not is_thin,
            "recommended_posts": recommended,
            "message": message,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Judge whether extracted material is too thin."
    )
    parser.add_argument("--input", default=None, help="counts JSON file")
    parser.add_argument("--min-total", type=int, default=None)
    parser.add_argument("--max-posts", type=int, default=None)
    for category in CATEGORIES:
        parser.add_argument(f"--{category}", type=int, default=None)
    args = parser.parse_args(argv)

    if args.input:
        counts = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        counts = {
            category: getattr(args, category)
            for category in CATEGORIES
            if getattr(args, category) is not None
        }
    checker = ExtractChecker(
        min_total=(args.min_total if args.min_total is not None else DEFAULT_MIN_TOTAL),
        max_recommended_posts=(
            args.max_posts
            if args.max_posts is not None
            else DEFAULT_MAX_RECOMMENDED_POSTS
        ),
    )
    try:
        result = checker.assess(counts)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["can_proceed"] else 1


if __name__ == "__main__":
    sys.exit(main())
