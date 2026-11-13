#!/usr/bin/env python3
"""
story_check.py - check a story sequence against the placement rules.

The sequence is checked before anything is prepared for posting.
Every limit in the skill is a variable here, not a fixed number in
the code: the frame count range, the safe zone for text, the ask
position and the frame size. The defaults follow the skill. The
safe zone values are this skill's own: they come from the story
viewer's interface and differ from the ig-reel safe zone, so the
two are kept separate on purpose.

Input is a JSON sequence:

    {
      "width": 1080,
      "height": 1920,
      "frames": [
        {"kind": "open", "has_face_or_hand": true,
         "texts": [{"text": "...", "y": 500}]},
        {"kind": "middle", "texts": [{"text": "...", "y": 700}]},
        {"kind": "ask", "sticker": "poll",
         "texts": [{"text": "...", "y": 800}]},
        {"kind": "close", "texts": [{"text": "...", "y": 800}]}
      ]
    }

A text item carries ``y`` (its top) and may carry ``y_bottom``.
A frame may use ``text_y`` instead of a ``texts`` list. Stickers
may be given as ``sticker`` (one) or ``stickers`` (a list). The
ask stickers are poll, question box, quiz and link; a frame with
kind ``ask`` counts as an ask frame even without a sticker.

Checks (violation codes):
- frame_count: the frame count is outside the range.
- dimensions: a width/height pair is not the frame size.
- text_above_safe_zone: a text starts above the safe zone.
- text_below_safe_zone: a text ends below the safe zone.
- ask_position: an ask frame is not at the ask position.
- ask_sticker_count: an ask frame carries more than one sticker.
- first_frame_face: the first frame is marked as having no face
  or hand in it (checked only when the flag is present).

Output is JSON: {"ok": bool, "frame_count": int, "violations":
[{"code", "frame", "detail"}, ...]} where ``frame`` is the 1-based
frame number, or null for a sequence-level violation.

Usage
  python3 story_check.py story.json
  python3 story_check.py - < story.json
  python3 story_check.py story.json --safe-top 200

Exit codes: 0 when the sequence passes, 1 when there are
violations, 2 when the input cannot be read.
"""

import argparse
import json
import sys

DEFAULT_MIN_FRAMES = 3
DEFAULT_MAX_FRAMES = 7
DEFAULT_SAFE_TOP = 250
DEFAULT_SAFE_BOTTOM = 1600
DEFAULT_ASK_POSITION = 4
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920

ASK_STICKERS = frozenset({"poll", "question_box", "quiz", "link"})
ASK_KIND = "ask"


def normalize_sticker(name):
    normalized = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized == "question":
        return "question_box"
    return normalized


def _violation(code, frame, detail):
    return {"code": code, "frame": frame, "detail": detail}


class StoryChecker:
    """Check a story sequence against the placement rules."""

    def __init__(
        self,
        min_frames=DEFAULT_MIN_FRAMES,
        max_frames=DEFAULT_MAX_FRAMES,
        safe_top=DEFAULT_SAFE_TOP,
        safe_bottom=DEFAULT_SAFE_BOTTOM,
        ask_position=DEFAULT_ASK_POSITION,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
    ):
        self.min_frames = min_frames
        self.max_frames = max_frames
        self.safe_top = safe_top
        self.safe_bottom = safe_bottom
        self.ask_position = ask_position
        self.width = width
        self.height = height

    def check(self, sequence):
        frames = list((sequence or {}).get("frames") or [])
        violations = []
        violations += self._frame_count_violations(frames)
        violations += self._dimensions_violations(sequence or {}, None)
        for index, frame in enumerate(frames):
            violations += self._frame_violations(frame, index)
        return {
            "ok": not violations,
            "frame_count": len(frames),
            "violations": violations,
        }

    def _frame_count_violations(self, frames):
        count = len(frames)
        if self.min_frames <= count <= self.max_frames:
            return []
        return [
            _violation(
                "frame_count",
                None,
                f"{count} frames, outside the range "
                f"{self.min_frames} to {self.max_frames}",
            )
        ]

    def _dimensions_violations(self, item, frame_number):
        width = item.get("width")
        height = item.get("height")
        if width is None and height is None:
            return []
        if width == self.width and height == self.height:
            return []
        return [
            _violation(
                "dimensions",
                frame_number,
                f"size is {width}x{height}, must be {self.width}x{self.height}",
            )
        ]

    def _stickers(self, frame):
        stickers = []
        single = frame.get("sticker")
        if single:
            stickers.append(normalize_sticker(single))
        for name in frame.get("stickers") or []:
            stickers.append(normalize_sticker(name))
        return stickers

    def _is_ask(self, frame):
        kind = str(frame.get("kind") or frame.get("role") or "").strip().lower()
        if kind == ASK_KIND:
            return True
        return any(sticker in ASK_STICKERS for sticker in self._stickers(frame))

    def _frame_violations(self, frame, index):
        number = index + 1
        violations = []
        violations += self._dimensions_violations(frame, number)
        violations += self._text_violations(frame, number)
        if index == 0 and frame.get("has_face_or_hand") is False:
            violations.append(
                _violation(
                    "first_frame_face",
                    number,
                    "the first frame has no face or hand in it",
                )
            )
        if self._is_ask(frame):
            if number != self.ask_position:
                violations.append(
                    _violation(
                        "ask_position",
                        number,
                        f"the ask is at frame {number}, "
                        f"must be at frame {self.ask_position}",
                    )
                )
            stickers = self._stickers(frame)
            if len(stickers) > 1:
                violations.append(
                    _violation(
                        "ask_sticker_count",
                        number,
                        f"the ask carries {len(stickers)} stickers, must be one",
                    )
                )
        return violations

    def _text_violations(self, frame, number):
        violations = []
        texts = list(frame.get("texts") or [])
        if frame.get("text_y") is not None:
            texts.append({"text": "", "y": frame["text_y"]})
        for item in texts:
            y = item.get("y")
            if y is not None and y < self.safe_top:
                violations.append(
                    _violation(
                        "text_above_safe_zone",
                        number,
                        f"text at y={y} is above the safe zone "
                        f"(top is y={self.safe_top})",
                    )
                )
            y_bottom = item.get("y_bottom", y)
            if y_bottom is not None and y_bottom > self.safe_bottom:
                violations.append(
                    _violation(
                        "text_below_safe_zone",
                        number,
                        f"text ending at y={y_bottom} is below the "
                        f"safe zone (bottom is y={self.safe_bottom})",
                    )
                )
        return violations


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a story sequence against the placement rules."
    )
    parser.add_argument("input", help="sequence JSON file, or - for stdin")
    parser.add_argument("--min-frames", type=int, default=DEFAULT_MIN_FRAMES)
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    parser.add_argument("--safe-top", type=int, default=DEFAULT_SAFE_TOP)
    parser.add_argument("--safe-bottom", type=int, default=DEFAULT_SAFE_BOTTOM)
    parser.add_argument("--ask-position", type=int, default=DEFAULT_ASK_POSITION)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = handle.read()
        sequence = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    checker = StoryChecker(
        min_frames=args.min_frames,
        max_frames=args.max_frames,
        safe_top=args.safe_top,
        safe_bottom=args.safe_bottom,
        ask_position=args.ask_position,
        width=args.width,
        height=args.height,
    )
    result = checker.check(sequence)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
