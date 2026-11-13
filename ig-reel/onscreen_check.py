#!/usr/bin/env python3
"""
onscreen_check.py - check a Reel's on-screen text cards before shooting.

Each card is checked on three rules from the ig-reel skill:

- six words or fewer per card,
- inside the safe zone on a 1080x1920 frame: nothing above y=230 or
  below y=1440, and the right 230 pixels stay clear (right edge at
  most 850),
- the hook card (the first card, and any card marked as the hook) is
  up at frame 1.

The limits are variables, not fixed numbers in the checks. The
defaults above follow the skill text; change them with the CLI flags
or the constructor arguments.

Input is JSON: either {"cards": [...]} or a bare list of cards.
Each card is an object:

    {"text": "5 HOURS -> 20 MIN", "x": 40, "y": 300,
     "width": 400, "height": 80, "frame": 1}

- ``text``: the card text (required).
- ``x`` / ``y``: the card's top-left corner in frame pixels.
  ``width`` / ``height`` or ``x2`` / ``y2`` may give the far edge;
  without them the top-left point itself is checked.
- hook timing: ``frame`` / ``start_frame`` (frame 1 passes), or
  ``start_seconds`` (0 passes). A hook card with no timing fails.
- ``role``: set to "hook" (or ``is_hook``: true) to mark a hook card
  that is not the first card.

Usage
  python3 onscreen_check.py cards.json
  python3 onscreen_check.py cards.json --max-words 6 --safe-top 230
  cat cards.json | python3 onscreen_check.py -

Prints {"ok", "violations", "cards_checked"} as JSON. Each violation
is {"card_index", "kind", "detail", ...}. Exit code is 0 when every
card passes, 1 when there is any violation, 2 on bad input.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from reeltext import words  # noqa: E402

DEFAULT_MAX_WORDS = 6
DEFAULT_FRAME_WIDTH = 1080
DEFAULT_FRAME_HEIGHT = 1920
DEFAULT_SAFE_TOP = 230
DEFAULT_SAFE_BOTTOM = 1440
DEFAULT_RIGHT_CLEAR = 230


class OnScreenChecker:
    """Check on-screen text cards against word and safe-zone rules."""

    def __init__(
        self,
        max_words=DEFAULT_MAX_WORDS,
        safe_top=DEFAULT_SAFE_TOP,
        safe_bottom=DEFAULT_SAFE_BOTTOM,
        frame_width=DEFAULT_FRAME_WIDTH,
        frame_height=DEFAULT_FRAME_HEIGHT,
        right_clear=DEFAULT_RIGHT_CLEAR,
    ):
        self.max_words = max_words
        self.safe_top = safe_top
        self.safe_bottom = safe_bottom
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.right_clear = right_clear

    @property
    def safe_right(self):
        return self.frame_width - self.right_clear

    def _hook_timing_ok(self, card):
        if "frame" in card:
            return card["frame"] == 1
        if "start_frame" in card:
            return card["start_frame"] == 1
        if "first_frame" in card:
            return bool(card["first_frame"])
        if "start_seconds" in card:
            return card["start_seconds"] == 0
        if "start_time" in card:
            return card["start_time"] == 0
        return False

    @staticmethod
    def _is_hook(card, index):
        return index == 0 or card.get("role") == "hook" or bool(card.get("is_hook"))

    def check(self, cards):
        violations = []

        def add(index, kind, detail, **extra):
            violations.append(
                {"card_index": index, "kind": kind, "detail": detail, **extra}
            )

        if not cards:
            add(-1, "no_cards", "no on-screen text cards were given")
            return {"ok": False, "violations": violations, "cards_checked": 0}

        for i, card in enumerate(cards):
            text = card.get("text", "")
            count = len(words(text))
            if count > self.max_words:
                add(
                    i,
                    "too_many_words",
                    f"{count} words, over the {self.max_words}-word limit",
                    word_count=count,
                )
            x = card.get("x")
            y = card.get("y")
            if y is not None and y < self.safe_top:
                add(i, "above_safe_zone", f"y={y} is above safe top {self.safe_top}")
            bottom = None
            if card.get("y2") is not None:
                bottom = card["y2"]
            elif y is not None and card.get("height") is not None:
                bottom = y + card["height"]
            elif y is not None:
                bottom = y
            if bottom is not None and bottom > self.safe_bottom:
                add(
                    i,
                    "below_safe_zone",
                    f"bottom={bottom} is below safe bottom {self.safe_bottom}",
                )
            right = None
            if card.get("x2") is not None:
                right = card["x2"]
            elif x is not None and card.get("width") is not None:
                right = x + card["width"]
            elif x is not None:
                right = x
            if right is not None and right > self.safe_right:
                add(
                    i,
                    "right_clear_zone",
                    f"right={right} enters the right {self.right_clear}px "
                    f"clear zone (limit {self.safe_right})",
                )
            if self._is_hook(card, i) and not self._hook_timing_ok(card):
                add(
                    i,
                    "hook_not_at_first_frame",
                    "hook card is not up at frame 1",
                )

        return {
            "ok": not violations,
            "violations": violations,
            "cards_checked": len(cards),
        }


def _cards_from_payload(payload):
    if isinstance(payload, dict):
        return payload.get("cards") or []
    if isinstance(payload, list):
        return payload
    raise ValueError("input must be a JSON object with 'cards' or a JSON list")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check Reel on-screen text cards (words, safe zone, hook frame)."
    )
    parser.add_argument(
        "input", nargs="?", default="-", help="JSON file, or - for stdin"
    )
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument("--safe-top", type=int, default=DEFAULT_SAFE_TOP)
    parser.add_argument("--safe-bottom", type=int, default=DEFAULT_SAFE_BOTTOM)
    parser.add_argument("--right-clear", type=int, default=DEFAULT_RIGHT_CLEAR)
    parser.add_argument("--frame-width", type=int, default=DEFAULT_FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=DEFAULT_FRAME_HEIGHT)
    args = parser.parse_args(argv)

    try:
        raw = (
            sys.stdin.read()
            if args.input == "-"
            else open(args.input, encoding="utf-8").read()
        )
        cards = _cards_from_payload(json.loads(raw))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    checker = OnScreenChecker(
        max_words=args.max_words,
        safe_top=args.safe_top,
        safe_bottom=args.safe_bottom,
        right_clear=args.right_clear,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
    )
    result = checker.check(cards)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
