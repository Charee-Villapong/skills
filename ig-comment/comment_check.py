#!/usr/bin/env python3
"""
comment_check.py - check an Instagram comment draft against the rules.

Checks the parts of the ig-comment "Rules" section that can be decided
from the text alone:

- the comment is one to three sentences,
- it does not open with a banned opening ("Great post", "Love this",
  "So true", "This 👏", "Needed this today", or the creator's first
  name followed by an exclamation mark),
- it is not emoji-only and does not start with an emoji,
- it carries no pitching: no link and no pitching phrase such as
  "check out my page".

The banned lists, phrases and the sentence limit are variables, not
fixed values in the logic. The defaults follow the skill.

Rules that need meaning (never restate the reel, one idea, say the
specific thing) cannot be decided from text alone and stay in SKILL.md.

Usage
  python3 comment_check.py "We raised ours 40% last March."
  python3 comment_check.py --creator-name Alex "Alex! Good point."
  python3 comment_check.py --max-sentences 2 "One. Two. Three."

Prints {"ok", "sentence_count", "violations"} as JSON, where each
violation is {"code", "detail"}. Exit code is 0 when ok, 1 otherwise.
"""

import argparse
import json
import re
import sys

DEFAULT_MIN_SENTENCES = 1
DEFAULT_MAX_SENTENCES = 3

DEFAULT_BANNED_OPENINGS = (
    "Great post",
    "Love this",
    "So true",
    "This 👏",
    "Needed this today",
)

DEFAULT_PITCHING_PHRASES = ("check out my page",)

_LINK_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?。！？]+")


def _is_emoji_char(char):
    code = ord(char)
    return (
        0x1F000 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or code in (0xFE0F, 0x200D)
    )


def count_sentences(text):
    parts = [part for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return len(parts)


class CommentChecker:
    """List rule violations in one comment draft."""

    def __init__(
        self,
        min_sentences=DEFAULT_MIN_SENTENCES,
        max_sentences=DEFAULT_MAX_SENTENCES,
        banned_openings=DEFAULT_BANNED_OPENINGS,
        pitching_phrases=DEFAULT_PITCHING_PHRASES,
    ):
        self.min_sentences = min_sentences
        self.max_sentences = max_sentences
        self.banned_openings = tuple(banned_openings)
        self.pitching_phrases = tuple(pitching_phrases)

    def check(self, text, creator_name=None):
        violations = []
        stripped = (text or "").strip()
        sentence_count = count_sentences(stripped) if stripped else 0

        if not stripped:
            violations.append({"code": "empty_comment", "detail": "comment is empty"})
            return {
                "ok": False,
                "sentence_count": 0,
                "violations": violations,
            }

        if sentence_count > self.max_sentences:
            violations.append(
                {
                    "code": "too_many_sentences",
                    "detail": (
                        f"{sentence_count} sentences, " f"limit is {self.max_sentences}"
                    ),
                }
            )
        if sentence_count < self.min_sentences:
            violations.append(
                {
                    "code": "too_few_sentences",
                    "detail": (
                        f"{sentence_count} sentences, "
                        f"minimum is {self.min_sentences}"
                    ),
                }
            )

        lowered = stripped.lower()
        for opening in self.banned_openings:
            if lowered.startswith(opening.lower()):
                violations.append(
                    {
                        "code": "banned_opening",
                        "detail": f"opens with banned opening: {opening}",
                    }
                )
                break

        if creator_name:
            name_opening = f"{creator_name.strip()}!"
            if stripped.lower().startswith(name_opening.lower()):
                violations.append(
                    {
                        "code": "creator_name_opening",
                        "detail": (
                            "opens with the creator's first name "
                            "and an exclamation mark"
                        ),
                    }
                )

        non_space = [char for char in stripped if not char.isspace()]
        if non_space and all(_is_emoji_char(char) for char in non_space):
            violations.append({"code": "emoji_only", "detail": "comment is emoji only"})
        if non_space and _is_emoji_char(non_space[0]):
            violations.append(
                {
                    "code": "emoji_first_character",
                    "detail": "comment starts with an emoji",
                }
            )

        if _LINK_RE.search(stripped):
            violations.append(
                {"code": "pitching_link", "detail": "comment contains a link"}
            )
        for phrase in self.pitching_phrases:
            if phrase.lower() in lowered:
                violations.append(
                    {
                        "code": "pitching_phrase",
                        "detail": f"comment contains pitching phrase: {phrase}",
                    }
                )
                break

        return {
            "ok": not violations,
            "sentence_count": sentence_count,
            "violations": violations,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a comment draft against the ig-comment rules."
    )
    parser.add_argument("text", help="comment draft text")
    parser.add_argument("--creator-name", default=None)
    parser.add_argument("--min-sentences", type=int, default=None)
    parser.add_argument("--max-sentences", type=int, default=None)
    args = parser.parse_args(argv)

    checker = CommentChecker(
        min_sentences=(
            args.min_sentences
            if args.min_sentences is not None
            else DEFAULT_MIN_SENTENCES
        ),
        max_sentences=(
            args.max_sentences
            if args.max_sentences is not None
            else DEFAULT_MAX_SENTENCES
        ),
    )
    result = checker.check(args.text, creator_name=args.creator_name)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
