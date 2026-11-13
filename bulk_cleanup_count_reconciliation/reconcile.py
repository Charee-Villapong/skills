#!/usr/bin/env python3
"""
reconcile.py - verify bulk cleanup counts against the executed log.

Every number in a bulk cleanup report must be built from the executed log,
never from the search result. This reads a report as JSON, recounts the
five buckets (searched / already_done / newly_done / kept / restored) from
the logged actions, and checks that the split reconciles:

- searched == already_done + newly_done + kept
- every searched item carries exactly one bucket action
- restored items are never counted as newly done

When the check fails, the caller must stop the report and recheck the
scope before publishing any number.

Usage
  python3 reconcile.py report.json

Input JSON
  {
    "scope": "sender or folder and date range (optional)",
    "searched": ["item-id", ...],
    "actions": [{"item_id": "item-id", "result": "newly_done"}, ...]
  }

Output is the result as JSON on stdout. Exit code 0 when the split
reconciles, 1 when it does not.
"""

import json
import sys
from collections import Counter

BUCKETS = ("already_done", "newly_done", "kept")
VALID_RESULTS = BUCKETS + ("restored",)


def reconcile(report):
    """Recount the five buckets from the executed log and reconcile them.

    Returns {"ok": bool, "counts": {...}, "errors": [str]}. ``ok`` is True
    only when ``errors`` is empty, and then the counts satisfy
    searched == already_done + newly_done + kept.
    """
    errors = []
    searched = list(report.get("searched") or [])
    actions = list(report.get("actions") or [])

    counts = {
        "searched": len(searched),
        "already_done": 0,
        "newly_done": 0,
        "kept": 0,
        "restored": 0,
    }

    for item_id, n in Counter(searched).items():
        if n > 1:
            errors.append(f"searched contains a duplicate item: {item_id}")

    searched_set = set(searched)
    results_by_item = {}
    for entry in actions:
        item_id = entry.get("item_id")
        result = entry.get("result")
        if result not in VALID_RESULTS:
            errors.append(f"invalid result for item {item_id}: {result!r}")
            continue
        counts[result] += 1
        results_by_item.setdefault(item_id, []).append(result)

    for item_id, results in results_by_item.items():
        if "restored" in results and "newly_done" in results:
            errors.append(
                f"item {item_id} is both restored and newly_done; "
                "restored items must never count as newly done"
            )
        if item_id not in searched_set:
            for result in results:
                if result != "restored":
                    errors.append(
                        f"action outside the searched scope: " f"{item_id} ({result})"
                    )

    for item_id in searched_set:
        bucket_results = [r for r in results_by_item.get(item_id, []) if r in BUCKETS]
        if len(bucket_results) == 0:
            errors.append(f"searched item has no logged action: {item_id}")
        elif len(bucket_results) > 1:
            errors.append(
                f"searched item has more than one bucket action: "
                f"{item_id} ({', '.join(bucket_results)})"
            )

    return {"ok": not errors, "counts": counts, "errors": errors}


def main(argv):
    if len(argv) != 2:
        print("usage: python3 reconcile.py report.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        report = json.load(fh)
    result = reconcile(report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
