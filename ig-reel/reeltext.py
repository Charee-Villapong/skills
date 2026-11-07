"""Shared text helpers for the ig-reel tools (beats.py and hookscore.py).

Kept inside the ig-reel folder so the folder stays the copy unit: both
tools load this module from their own directory. Other ig-* folders
deliberately keep their own variants (ig-viral's swipe counts words
without stripping thousands separators, ig-human's detect counts only
letters); those differences are pinned by the shared-parts
characterization tests and are not to be aligned here.
"""

import re

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")


def words(text):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))
