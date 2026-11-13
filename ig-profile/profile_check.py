#!/usr/bin/env python3
"""
profile_check.py - check the lengths and counts of a profile rewrite.

Implements the numeric judgement in ig-profile/SKILL.md,
"Then rewrite, in this order":

- name field options: exactly 3 options, each at most 30 characters
- bio: at most 150 characters in total
- pinned posts: exactly 3
- highlights: 4 to 6
- links: 1 to 5 (one destination is the aim; five is the platform cap)
- grid covers: the first 9, each cover text at most 4 words

The limits are variables, not fixed numbers in the logic: they are
module constants overridable from the CLI.

Usage
  python3 profile_check.py profile.json
  python3 profile_check.py profile.json --name-max-chars 30

Input JSON (counts may be given as a number or as a list, whose
length is used)::

  {
    "name_options": ["...", "...", "..."],
    "bio": "...",
    "pinned_count": 3,
    "highlights": ["Pricing", "Results", "How it works", "About"],
    "link_count": 1,
    "grid_covers": [{"text": "four words or fewer"}, ...]
  }

Grid covers may also be plain strings, read as the cover text.

Output is JSON on stdout: {"ok", "violations", "measurements"}.
Exit code 0 when the rewrite passes, 1 when it has violations,
2 on usage or input errors.
"""

import argparse
import json
import sys

DEFAULT_NAME_MAX_CHARS = 30
DEFAULT_NAME_OPTIONS = 3
DEFAULT_BIO_MAX_CHARS = 150
DEFAULT_PINNED_COUNT = 3
DEFAULT_HIGHLIGHTS_MIN = 4
DEFAULT_HIGHLIGHTS_MAX = 6
DEFAULT_LINKS_MIN = 1
DEFAULT_LINKS_MAX = 5
DEFAULT_GRID_COVERS = 9
DEFAULT_COVER_TEXT_MAX_WORDS = 4


def _count_of(profile, count_key, list_key):
    """Return a count from a number field or a list field, else None."""
    if count_key in profile and profile[count_key] is not None:
        return int(profile[count_key])
    if list_key in profile and profile[list_key] is not None:
        return len(list(profile[list_key]))
    return None


class ProfileChecker:
    """Check a profile rewrite dict against the length/count limits."""

    def __init__(
        self,
        name_max_chars=DEFAULT_NAME_MAX_CHARS,
        name_options=DEFAULT_NAME_OPTIONS,
        bio_max_chars=DEFAULT_BIO_MAX_CHARS,
        pinned_count=DEFAULT_PINNED_COUNT,
        highlights_min=DEFAULT_HIGHLIGHTS_MIN,
        highlights_max=DEFAULT_HIGHLIGHTS_MAX,
        links_min=DEFAULT_LINKS_MIN,
        links_max=DEFAULT_LINKS_MAX,
        grid_covers=DEFAULT_GRID_COVERS,
        cover_text_max_words=DEFAULT_COVER_TEXT_MAX_WORDS,
    ):
        self.name_max_chars = name_max_chars
        self.name_options = name_options
        self.bio_max_chars = bio_max_chars
        self.pinned_count = pinned_count
        self.highlights_min = highlights_min
        self.highlights_max = highlights_max
        self.links_min = links_min
        self.links_max = links_max
        self.grid_covers = grid_covers
        self.cover_text_max_words = cover_text_max_words

    def check(self, profile):
        violations = []
        measurements = {}

        def add(code, message, **extra):
            violations.append({"code": code, "message": message, **extra})

        profile = profile or {}

        # 1. Name field options.
        options = profile.get("name_options")
        if options is None:
            add("missing_field", "name_options is required")
            measurements["name_options"] = 0
        else:
            options = list(options)
            measurements["name_options"] = len(options)
            if len(options) != self.name_options:
                add(
                    "name_options_count",
                    f"name field needs {self.name_options} options, "
                    f"got {len(options)}",
                )
            for index, option in enumerate(options):
                if len(str(option)) > self.name_max_chars:
                    add(
                        "name_too_long",
                        f"name option {index} is {len(str(option))} "
                        f"characters, over {self.name_max_chars}",
                        index=index,
                    )

        # 2. Bio length.
        bio = profile.get("bio")
        if bio is None:
            add("missing_field", "bio is required")
            measurements["bio_chars"] = 0
        else:
            measurements["bio_chars"] = len(str(bio))
            if len(str(bio)) > self.bio_max_chars:
                add(
                    "bio_too_long",
                    f"bio is {len(str(bio))} characters, " f"over {self.bio_max_chars}",
                )

        # 3. Pinned three.
        pinned = _count_of(profile, "pinned_count", "pinned")
        if pinned is None:
            add("missing_field", "pinned_count (or pinned) is required")
            measurements["pinned"] = 0
        else:
            measurements["pinned"] = pinned
            if pinned != self.pinned_count:
                add(
                    "pinned_count",
                    f"pinned posts must be {self.pinned_count}, got {pinned}",
                )

        # 4. Highlights.
        highlights = _count_of(profile, "highlights_count", "highlights")
        if highlights is None:
            add("missing_field", "highlights (or highlights_count) is required")
            measurements["highlights"] = 0
        else:
            measurements["highlights"] = highlights
            if not self.highlights_min <= highlights <= self.highlights_max:
                add(
                    "highlights_count",
                    f"highlights must be {self.highlights_min} to "
                    f"{self.highlights_max}, got {highlights}",
                )

        # 5. Links.
        links = _count_of(profile, "link_count", "links")
        if links is None:
            add("missing_field", "link_count (or links) is required")
            measurements["links"] = 0
        else:
            measurements["links"] = links
            if not self.links_min <= links <= self.links_max:
                add(
                    "link_count",
                    f"links must be {self.links_min} to {self.links_max}, "
                    f"got {links}",
                )

        # 6. Grid covers and their text.
        covers = profile.get("grid_covers")
        if covers is None:
            add("missing_field", "grid_covers is required")
            measurements["grid_covers"] = 0
        else:
            covers = list(covers)
            measurements["grid_covers"] = len(covers)
            if len(covers) != self.grid_covers:
                add(
                    "grid_covers_count",
                    f"grid covers must be {self.grid_covers}, got {len(covers)}",
                )
            for index, cover in enumerate(covers):
                text = cover.get("text", "") if isinstance(cover, dict) else cover
                words = len(str(text).split())
                if words > self.cover_text_max_words:
                    add(
                        "cover_text_words",
                        f"cover {index} text is {words} words, "
                        f"over {self.cover_text_max_words}",
                        index=index,
                    )

        return {
            "ok": not violations,
            "violations": violations,
            "measurements": measurements,
        }


def check_profile(profile, **kwargs):
    """Check ``profile`` with a ProfileChecker built from ``kwargs``."""
    return ProfileChecker(**kwargs).check(profile)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the lengths and counts of a profile rewrite."
    )
    parser.add_argument("profile", help="profile JSON file")
    parser.add_argument("--name-max-chars", type=int, default=DEFAULT_NAME_MAX_CHARS)
    parser.add_argument("--bio-max-chars", type=int, default=DEFAULT_BIO_MAX_CHARS)
    args = parser.parse_args(argv)

    try:
        with open(args.profile, encoding="utf-8") as fh:
            profile = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read profile: {exc}", file=sys.stderr)
        return 2

    checker = ProfileChecker(
        name_max_chars=args.name_max_chars,
        bio_max_chars=args.bio_max_chars,
    )
    result = checker.check(profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
