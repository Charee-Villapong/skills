#!/usr/bin/env python3
"""
audit_metrics.py - compute per-post audit metrics and rank the posts.

Implements ig-audit/SKILL.md, "What to actually measure". Raw views is
mostly a function of follower count, so each post is scored with:

- outlier multiple: views / the account's own median views
- non-follower reach: share of reach from non-followers (input value)
- hold at 3s: viewers still there at 3s / viewers who started
- average watch time: straight from insights (input value)
- sends per reach: shares / reach
- follows per reach: follows / reach

Ranking is by outlier multiple, then by sends per reach. It is never
by raw views.

Ranking and any tendency summary are only produced when the sample is
at or above the minimum sample size (default 30 posts, the size the
skill says can show a pattern). Below that, per-post metrics are still
computed, but ``ranking`` is empty, every ``rank`` is null and
``tendency`` is null: the tool does not state a tendency it cannot
support. The minimum is a variable (module constant and CLI flag).

Input is a JSON list of post objects or a tab-separated file with a
header row. Post fields: ``id``, ``views``, ``reach``, ``shares``
(``sends`` also accepted), ``follows``, ``started``, ``at_3s``,
``average_watch_time`` and ``non_follower_reach``. Output is JSON.
The median views come from ``--median-views`` when given, otherwise
from the median of the posts' own views.

Usage
  python3 audit_metrics.py posts.json --median-views 4100
  python3 audit_metrics.py posts.tsv --min-sample 30
"""

import argparse
import json
import statistics
import sys

DEFAULT_MIN_SAMPLE = 30


def _num(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _ratio(numerator, denominator):
    num = _num(numerator)
    den = _num(denominator)
    if num is None or not den:
        return None
    return round(num / den, 4)


class AuditMetricsCalculator:
    """Compute audit metrics, and rank only with a large enough sample."""

    def __init__(self, median_views=None, min_sample=DEFAULT_MIN_SAMPLE):
        self.median_views = _num(median_views)
        self.min_sample = min_sample

    def _median_views(self, posts):
        if self.median_views:
            return self.median_views
        views = [v for v in (_num(p.get("views")) for p in posts) if v]
        if not views:
            return None
        return float(statistics.median(views))

    def compute_post(self, post, median_views):
        views = _num(post.get("views"))
        shares = post.get("shares", post.get("sends"))
        outlier = None
        if views is not None and median_views:
            outlier = round(views / median_views, 2)
        return {
            "id": post.get("id", ""),
            "views": int(views) if views is not None else None,
            "outlier_multiple": outlier,
            "non_follower_reach": _num(post.get("non_follower_reach")),
            "hold_at_3s": _ratio(post.get("at_3s"), post.get("started")),
            "average_watch_time": _num(post.get("average_watch_time")),
            "sends_per_reach": _ratio(shares, post.get("reach")),
            "follows_per_reach": _ratio(post.get("follows"), post.get("reach")),
            "rank": None,
        }

    def analyse(self, posts):
        median_views = self._median_views(posts)
        computed = [self.compute_post(p, median_views) for p in posts]
        sufficient = len(computed) >= self.min_sample
        ranking = []
        tendency = None
        if sufficient:
            ordered = sorted(
                computed,
                key=lambda p: (
                    -(p["outlier_multiple"] or 0),
                    -(p["sends_per_reach"] or 0),
                ),
            )
            for index, post in enumerate(ordered, start=1):
                post["rank"] = index
            ranking = [p["id"] for p in ordered]
            tendency = {
                "top": ranking[:5],
                "bottom": ranking[-5:][::-1],
            }
        return {
            "sample_size": len(computed),
            "min_sample": self.min_sample,
            "sufficient": sufficient,
            "median_views": (
                int(median_views)
                if median_views and float(median_views).is_integer()
                else median_views
            ),
            "posts": computed,
            "ranking": ranking,
            "tendency": tendency,
        }


def read_posts(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    text = raw.strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            return list(data.get("posts") or [])
        return list(data)
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    cols = [c.strip().lower() for c in lines[0].split("\t")]
    posts = []
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) < len(cols):
            cells += [""] * (len(cols) - len(cells))
        posts.append(dict(zip(cols, [c.strip() for c in cells])))
    return posts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compute audit metrics and rank posts."
    )
    parser.add_argument("input", nargs="?", default="-", help="JSON or TSV file")
    parser.add_argument("--median-views", type=float, default=None)
    parser.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE)
    args = parser.parse_args(argv)

    posts = read_posts(args.input)
    if not posts:
        print("no usable posts.", file=sys.stderr)
        return 2
    calculator = AuditMetricsCalculator(
        median_views=args.median_views, min_sample=args.min_sample
    )
    result = calculator.analyse(posts)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
