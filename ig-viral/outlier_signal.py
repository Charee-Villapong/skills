#!/usr/bin/env python3
"""
outlier_signal.py - classify collected reels by their outlier multiple.

Implements the one idea in ig-viral/SKILL.md: raw views are not evidence.
A reel is judged by how far it beat its own account, that is
``views / median``, where median is that account's own recent median.

- A multiple at or above the signal threshold (default 3.0) is a signal.
- A multiple below the normal threshold (default 1.5) is a normal day.
- Anything in between is intermediate: neither a signal nor a normal day.
- Accounts are collected within about 10x of the user's own size
  (default ratio 10). When the user's follower count is given, a row
  outside that range is not classified as signal, normal or
  intermediate; it is marked ``out_of_range``.
- A row whose median is missing is not classified at all. It is
  reported in the ``missing`` list instead.

The thresholds and the size ratio are variables (module constants and
CLI flags), not fixed numbers in the decision code.

Input is a tab-separated file with the same columns as swipe.py
(``account``, ``followers``, ``median``, ``views``; extra columns are
ignored), a JSON list of row objects, or ``-`` for stdin. Output is
JSON: ``{"n", "classified": [...], "missing": [...]}`` where each
classified row carries ``outlier_multiple``, ``classification`` and
``in_size_range`` (true, false, or null when the user's size is
unknown).

Usage
  python3 outlier_signal.py captured.tsv
  python3 outlier_signal.py rows.json --user-followers 4000
  python3 outlier_signal.py captured.tsv --signal-threshold 5
"""

import argparse
import json
import re
import sys

SIGNAL = "signal"
NORMAL = "normal"
INTERMEDIATE = "intermediate"
OUT_OF_RANGE = "out_of_range"

DEFAULT_SIGNAL_THRESHOLD = 3.0
DEFAULT_NORMAL_THRESHOLD = 1.5
DEFAULT_SIZE_RATIO = 10.0


def _to_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _to_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


class OutlierSignalClassifier:
    """Classify rows by outlier multiple against variable thresholds."""

    def __init__(
        self,
        signal_threshold=DEFAULT_SIGNAL_THRESHOLD,
        normal_threshold=DEFAULT_NORMAL_THRESHOLD,
        size_ratio=DEFAULT_SIZE_RATIO,
    ):
        self.signal_threshold = signal_threshold
        self.normal_threshold = normal_threshold
        self.size_ratio = size_ratio

    def in_size_range(self, followers, user_followers):
        """True or False when both sizes are known, else None."""
        if not followers or not user_followers:
            return None
        low = user_followers / self.size_ratio
        high = user_followers * self.size_ratio
        return low <= followers <= high

    def classify_one(self, row, user_followers=None):
        """Return the result dict for one row, or None if unclassifiable.

        A row is unclassifiable when its median or its views are
        missing; the caller puts such rows in the missing list.
        """
        median = _to_float(row.get("median"))
        views = _to_float(row.get("views"))
        if not median or views is None:
            return None
        followers = _to_int(row.get("followers"))
        in_range = self.in_size_range(followers, user_followers)
        multiple = round(views / median, 2)
        if in_range is False:
            classification = OUT_OF_RANGE
        elif multiple >= self.signal_threshold:
            classification = SIGNAL
        elif multiple < self.normal_threshold:
            classification = NORMAL
        else:
            classification = INTERMEDIATE
        return {
            "account": row.get("account", ""),
            "followers": followers,
            "median": int(median) if float(median).is_integer() else median,
            "views": int(views) if float(views).is_integer() else views,
            "outlier_multiple": multiple,
            "classification": classification,
            "in_size_range": in_range,
        }

    def analyse(self, rows, user_followers=None):
        classified = []
        missing = []
        for row in rows:
            result = self.classify_one(row, user_followers=user_followers)
            if result is None:
                missing.append(
                    {
                        "account": row.get("account", ""),
                        "followers": _to_int(row.get("followers")),
                        "median": row.get("median"),
                        "views": _to_int(row.get("views")),
                        "reason": "median missing",
                    }
                )
            else:
                classified.append(result)
        return {"n": len(rows), "classified": classified, "missing": missing}


def read_rows(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    text = raw.strip()
    if not text:
        return [], None
    if text.startswith("[") or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            return list(data.get("rows") or []), data.get("user_followers")
        return list(data), None
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return [], None
    head = [c.strip().lower() for c in lines[0].split("\t")]
    if "views" in head:
        cols, body = head, lines[1:]
    else:
        cols, body = ["account", "followers", "median", "views"], lines
    rows = []
    for line in body:
        cells = line.split("\t")
        if len(cells) < len(cols):
            cells += [""] * (len(cols) - len(cells))
        rows.append(dict(zip(cols, [c.strip() for c in cells])))
    return rows, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Classify collected reels by outlier multiple."
    )
    parser.add_argument("input", nargs="?", default="-", help="TSV or JSON file")
    parser.add_argument("--user-followers", type=int, default=None)
    parser.add_argument(
        "--signal-threshold", type=float, default=DEFAULT_SIGNAL_THRESHOLD
    )
    parser.add_argument(
        "--normal-threshold", type=float, default=DEFAULT_NORMAL_THRESHOLD
    )
    parser.add_argument("--size-ratio", type=float, default=DEFAULT_SIZE_RATIO)
    args = parser.parse_args(argv)

    rows, file_user_followers = read_rows(args.input)
    if not rows:
        print("no usable rows.", file=sys.stderr)
        return 2
    user_followers = (
        args.user_followers if args.user_followers is not None else file_user_followers
    )
    classifier = OutlierSignalClassifier(
        signal_threshold=args.signal_threshold,
        normal_threshold=args.normal_threshold,
        size_ratio=args.size_ratio,
    )
    result = classifier.analyse(rows, user_followers=user_followers)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
