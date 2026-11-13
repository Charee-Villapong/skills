#!/usr/bin/env python3
"""
hook_gate.py - gate script writing on the top hook score.

The ig-reel loop scores three hooks with hookscore.py and writes the
script on the winner - but only when the winner clears a floor. If
the top score is under the floor, there is no hook yet and no amount
of editing fixes that: stop, and rewrite the hooks instead.

The floor is a variable, not a fixed number in the check. The default
follows the skill: 50. Change it with --min-score or the constructor.

Input is hookscore.py --json output: a single object such as
{"hook": ..., "score": 86.0, ...} or a list of such objects. A bare
list of numbers, a single number, or repeated --score flags are also
accepted.

Usage
  python3 hookscore.py hooks.txt --json | python3 hook_gate.py -
  python3 hook_gate.py scores.json
  python3 hook_gate.py --score 86 --score 54
  python3 hook_gate.py scores.json --min-score 60

Prints {"ok", "decision", "top_score", "min_top_score", "count"} as
JSON, where decision is "proceed" or "rewrite_hook". Exit code is 0
when the gate passes, 1 when it blocks, 2 on bad input.
"""

import argparse
import json
import sys

DEFAULT_MIN_TOP_SCORE = 50

PROCEED = "proceed"
REWRITE_HOOK = "rewrite_hook"


def _scores_from_payload(payload):
    if payload is None:
        return []
    if isinstance(payload, (int, float)):
        return [float(payload)]
    if isinstance(payload, dict):
        if "score" in payload:
            return [float(payload["score"])]
        for key in ("hooks", "results", "scores"):
            if key in payload:
                return _scores_from_payload(payload[key])
        return []
    if isinstance(payload, list):
        scores = []
        for item in payload:
            scores.extend(_scores_from_payload(item))
        return scores
    raise ValueError(f"unsupported score payload: {type(payload).__name__}")


class HookGate:
    """Decide whether the top hook score clears the floor."""

    def __init__(self, min_top_score=DEFAULT_MIN_TOP_SCORE):
        self.min_top_score = min_top_score

    def evaluate(self, payload):
        scores = _scores_from_payload(payload)
        top = max(scores) if scores else None
        ok = top is not None and top >= self.min_top_score
        return {
            "ok": ok,
            "decision": PROCEED if ok else REWRITE_HOOK,
            "top_score": top,
            "min_top_score": self.min_top_score,
            "count": len(scores),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gate script writing on the top hookscore.py score."
    )
    parser.add_argument(
        "input", nargs="?", default=None, help="JSON file, or - for stdin"
    )
    parser.add_argument("--score", type=float, action="append", default=None)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_TOP_SCORE)
    args = parser.parse_args(argv)

    gate = HookGate(min_top_score=args.min_score)
    try:
        if args.score is not None:
            result = gate.evaluate(args.score)
        elif args.input is not None:
            raw = (
                sys.stdin.read()
                if args.input == "-"
                else open(args.input, encoding="utf-8").read()
            )
            result = gate.evaluate(json.loads(raw))
        else:
            result = gate.evaluate(json.loads(sys.stdin.read()))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
