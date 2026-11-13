#!/usr/bin/env python3
"""
verify_structure.py - compare a sheet snapshot taken after a structural
edit with the record made before the edit.

The caller records every summary position, formula range and chart source
before inserting rows, deleting rows, hiding columns or moving a block,
then reads the tab again afterwards and passes both snapshots here. The
change may be reported only when this check passes; on a mismatch the
caller restores the named items and runs the check again.

Usage
  python3 verify_structure.py input.json

Input JSON
  {
    "before": {
      "summaries": [{"name": "...", "cell": "B10", "formula": "=SUM(B2:B9)"}],
      "formula_ranges": [{"range": "B2:B9", "formula": "=A2*C2"}],
      "charts": [{"name": "...", "source_columns": ["A", "B"]}],
      "hidden_columns": []
    },
    "after": { ... same shape ... },
    "restored": ["names of items restored during the check"]  (optional)
  }

Output is the result as JSON on stdout: {"ok", "mismatches", "restored"}.
Each mismatch is {"kind", "key", "detail"}. Exit code 0 when the snapshots
match, 1 when they do not.
"""

import json
import sys


def _index(items, key):
    return {item[key]: item for item in items or []}


def verify(before, after, restored=None):
    """Compare the after snapshot with the before record.

    Returns {"ok": bool, "mismatches": [{"kind", "key", "detail"}],
    "restored": [...]}. ``restored`` is echoed back so the report can name
    the items that were restored during the check.
    """
    mismatches = []

    def add(kind, key, detail):
        mismatches.append({"kind": kind, "key": key, "detail": detail})

    before_summaries = _index(before.get("summaries"), "name")
    after_summaries = _index(after.get("summaries"), "name")
    for name, old in before_summaries.items():
        new = after_summaries.get(name)
        if new is None:
            add("summary_missing", name, f"summary {name} is gone")
            continue
        if new.get("cell") != old.get("cell"):
            add(
                "summary_moved",
                name,
                f"summary {name} moved: {old.get('cell')} -> {new.get('cell')}",
            )
        if new.get("formula") != old.get("formula"):
            add(
                "summary_formula_changed",
                name,
                f"summary {name} formula changed: "
                f"{old.get('formula')} -> {new.get('formula')}",
            )
    for name in after_summaries:
        if name not in before_summaries:
            add("summary_added", name, f"summary {name} was not in the record")

    before_ranges = _index(before.get("formula_ranges"), "range")
    after_ranges = _index(after.get("formula_ranges"), "range")
    for range_, old in before_ranges.items():
        new = after_ranges.get(range_)
        if new is None:
            add("range_missing", range_, f"formula range {range_} is gone")
            continue
        if new.get("formula") != old.get("formula"):
            add(
                "range_formula_changed",
                range_,
                f"formula in {range_} changed: "
                f"{old.get('formula')} -> {new.get('formula')}",
            )
    for range_ in after_ranges:
        if range_ not in before_ranges:
            add(
                "range_added",
                range_,
                f"formula range {range_} was not in the record",
            )

    before_charts = _index(before.get("charts"), "name")
    after_charts = _index(after.get("charts"), "name")
    for name, old in before_charts.items():
        new = after_charts.get(name)
        if new is None:
            add("chart_missing", name, f"chart {name} is gone")
            continue
        if set(new.get("source_columns") or []) != set(old.get("source_columns") or []):
            add(
                "chart_source_changed",
                name,
                f"chart {name} source columns changed: "
                f"{old.get('source_columns')} -> {new.get('source_columns')}",
            )
    for name in after_charts:
        if name not in before_charts:
            add("chart_added", name, f"chart {name} was not in the record")

    hidden_after = set(after.get("hidden_columns") or [])
    for name, chart in after_charts.items():
        hidden_sources = sorted(set(chart.get("source_columns") or []) & hidden_after)
        if hidden_sources:
            add(
                "chart_source_hidden",
                name,
                f"chart {name} reads hidden columns: " f"{', '.join(hidden_sources)}",
            )

    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "restored": list(restored) if restored else [],
    }


def main(argv):
    if len(argv) != 2:
        print("usage: python3 verify_structure.py input.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        payload = json.load(fh)
    result = verify(
        payload.get("before") or {},
        payload.get("after") or {},
        payload.get("restored"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
