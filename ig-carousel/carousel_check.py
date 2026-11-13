#!/usr/bin/env python3
"""
carousel_check.py - check a carousel deck against the structure limits.

The deck is checked before anything is rendered. Every limit in the
skill is a variable here, not a fixed number in the code: the slide
count range, the cover word limit, the headline and body word limits,
the slide size and the smallest type size. The defaults follow the
skill.

Input is a JSON deck:

    {
      "width": 1080,
      "height": 1350,
      "slides": [
        {"role": "cover", "headline": "...", "body": "..."},
        {"role": "stake", "headline": "", "body": "..."},
        {"role": "content", "headline": "...", "body": "..."},
        {"role": "recap", "headline": "...", "body": "..."},
        {"role": "cta", "headline": "", "body": "..."}
      ]
    }

``role`` is optional. When any slide carries a role, the order is
checked: cover first, stake second, content in the middle, recap
second from last, cta last. ``width`` / ``height`` may sit on the
deck or on a single slide. ``font_size_px`` on a slide is checked
only when present. Words are counted by splitting on whitespace.

Checks (violation codes):
- slide_count: the slide count is outside the range.
- role_order: a role sits in the wrong position.
- cover_headline_words: the cover hook is over the word limit.
- cover_promise_missing: the cover has no promise line under the hook.
- stake_text_missing: the stake slide has no text.
- content_headline_words: a middle slide headline is outside its range.
- content_body_words: a middle slide body is over the word limit.
- dimensions: a width/height pair is not the slide size.
- font_size: a slide type size is below the minimum.

Output is JSON: {"ok": bool, "slide_count": int, "violations":
[{"code", "slide", "detail"}, ...]} where ``slide`` is the 1-based
slide number, or null for a deck-level violation.

Usage
  python3 carousel_check.py deck.json
  python3 carousel_check.py - < deck.json
  python3 carousel_check.py deck.json --max-slides 20

Exit codes: 0 when the deck passes, 1 when there are violations,
2 when the input cannot be read.
"""

import argparse
import json
import sys

DEFAULT_MIN_SLIDES = 6
DEFAULT_MAX_SLIDES = 10
DEFAULT_COVER_MAX_WORDS = 6
DEFAULT_HEADLINE_MIN_WORDS = 3
DEFAULT_HEADLINE_MAX_WORDS = 7
DEFAULT_BODY_MAX_WORDS = 25
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1350
DEFAULT_MIN_FONT_SIZE_PX = 32

ROLE_COVER = "cover"
ROLE_STAKE = "stake"
ROLE_CONTENT = "content"
ROLE_RECAP = "recap"
ROLE_CTA = "cta"


def count_words(text):
    return len((text or "").split())


def _violation(code, slide, detail):
    return {"code": code, "slide": slide, "detail": detail}


class CarouselChecker:
    """Check a carousel deck against the structure limits."""

    def __init__(
        self,
        min_slides=DEFAULT_MIN_SLIDES,
        max_slides=DEFAULT_MAX_SLIDES,
        cover_max_words=DEFAULT_COVER_MAX_WORDS,
        headline_min_words=DEFAULT_HEADLINE_MIN_WORDS,
        headline_max_words=DEFAULT_HEADLINE_MAX_WORDS,
        body_max_words=DEFAULT_BODY_MAX_WORDS,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_font_size_px=DEFAULT_MIN_FONT_SIZE_PX,
    ):
        self.min_slides = min_slides
        self.max_slides = max_slides
        self.cover_max_words = cover_max_words
        self.headline_min_words = headline_min_words
        self.headline_max_words = headline_max_words
        self.body_max_words = body_max_words
        self.width = width
        self.height = height
        self.min_font_size_px = min_font_size_px

    def check(self, deck):
        slides = list((deck or {}).get("slides") or [])
        violations = []
        violations += self._slide_count_violations(slides)
        violations += self._dimensions_violations(deck or {}, None)
        for index, slide in enumerate(slides):
            violations += self._slide_violations(slide, index, len(slides))
        return {
            "ok": not violations,
            "slide_count": len(slides),
            "violations": violations,
        }

    def _slide_count_violations(self, slides):
        count = len(slides)
        if self.min_slides <= count <= self.max_slides:
            return []
        return [
            _violation(
                "slide_count",
                None,
                f"{count} slides, outside the range "
                f"{self.min_slides} to {self.max_slides}",
            )
        ]

    def _expected_role(self, index, total):
        if index == 0:
            return ROLE_COVER
        if index == 1:
            return ROLE_STAKE
        if index == total - 1:
            return ROLE_CTA
        if index == total - 2:
            return ROLE_RECAP
        return ROLE_CONTENT

    def _dimensions_violations(self, item, slide_number):
        width = item.get("width")
        height = item.get("height")
        if width is None and height is None:
            return []
        if width == self.width and height == self.height:
            return []
        return [
            _violation(
                "dimensions",
                slide_number,
                f"size is {width}x{height}, must be " f"{self.width}x{self.height}",
            )
        ]

    def _slide_violations(self, slide, index, total):
        number = index + 1
        violations = []
        violations += self._dimensions_violations(slide, number)
        role = str(slide.get("role") or "").strip().lower()
        if role and total >= 2:
            expected = self._expected_role(index, total)
            if role != expected:
                violations.append(
                    _violation(
                        "role_order",
                        number,
                        f"slide {number} has role '{role}', " f"expected '{expected}'",
                    )
                )
        headline = slide.get("headline") or ""
        body = slide.get("body") or ""
        position = self._expected_role(index, total)
        if position == ROLE_COVER:
            if count_words(headline) > self.cover_max_words:
                violations.append(
                    _violation(
                        "cover_headline_words",
                        number,
                        f"cover hook is {count_words(headline)} words, "
                        f"over the limit of {self.cover_max_words}",
                    )
                )
            if not body.strip():
                violations.append(
                    _violation(
                        "cover_promise_missing",
                        number,
                        "the cover has no promise line under the hook",
                    )
                )
        elif position == ROLE_STAKE:
            if not headline.strip() and not body.strip():
                violations.append(
                    _violation(
                        "stake_text_missing",
                        number,
                        "the stake slide has no text",
                    )
                )
        elif position == ROLE_CONTENT:
            headline_words = count_words(headline)
            if not (
                self.headline_min_words <= headline_words <= self.headline_max_words
            ):
                violations.append(
                    _violation(
                        "content_headline_words",
                        number,
                        f"headline is {headline_words} words, outside "
                        f"the range {self.headline_min_words} to "
                        f"{self.headline_max_words}",
                    )
                )
            if count_words(body) > self.body_max_words:
                violations.append(
                    _violation(
                        "content_body_words",
                        number,
                        f"body is {count_words(body)} words, over "
                        f"the limit of {self.body_max_words}",
                    )
                )
        font_size = slide.get("font_size_px")
        if font_size is not None and font_size < self.min_font_size_px:
            violations.append(
                _violation(
                    "font_size",
                    number,
                    f"type size is {font_size}px, below the minimum "
                    f"of {self.min_font_size_px}px",
                )
            )
        return violations


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a carousel deck against the structure limits."
    )
    parser.add_argument("input", help="deck JSON file, or - for stdin")
    parser.add_argument("--min-slides", type=int, default=DEFAULT_MIN_SLIDES)
    parser.add_argument("--max-slides", type=int, default=DEFAULT_MAX_SLIDES)
    parser.add_argument("--cover-max-words", type=int, default=DEFAULT_COVER_MAX_WORDS)
    parser.add_argument(
        "--headline-min-words", type=int, default=DEFAULT_HEADLINE_MIN_WORDS
    )
    parser.add_argument(
        "--headline-max-words", type=int, default=DEFAULT_HEADLINE_MAX_WORDS
    )
    parser.add_argument("--body-max-words", type=int, default=DEFAULT_BODY_MAX_WORDS)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--min-font-size", type=int, default=DEFAULT_MIN_FONT_SIZE_PX)
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = handle.read()
        deck = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    checker = CarouselChecker(
        min_slides=args.min_slides,
        max_slides=args.max_slides,
        cover_max_words=args.cover_max_words,
        headline_min_words=args.headline_min_words,
        headline_max_words=args.headline_max_words,
        body_max_words=args.body_max_words,
        width=args.width,
        height=args.height,
        min_font_size_px=args.min_font_size,
    )
    result = checker.check(deck)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
