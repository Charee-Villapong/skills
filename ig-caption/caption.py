#!/usr/bin/env python3
"""
caption.py - lint an Instagram caption and show exactly what the feed shows
before the "... more".

Instagram gives a caption about 125 characters in the feed and hides the rest
behind a tap. Almost every caption that fails, fails there: the hook is in
sentence three, or the first line is a greeting, or the whole thing opens on a
hashtag. This prints the visible window as a box so you can read it the way a
scrolling stranger does, then checks the eight things that are worth checking.

The 125-character cut is an approximation. The real number moves with the
device, the font size and where your line breaks fall, which is exactly why
you want a margin rather than a caption engineered to end at 125. Change it
with --truncate if you want to test a tighter one.

Usage
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "proposal software,client contract"
  pbpaste | python3 caption.py -
  python3 caption.py caption.txt --json
"""

import argparse
import json
import re
import sys
import textwrap

LIMIT = 2200             # Instagram's hard caption limit.
TRUNCATE = 125           # Roughly where the feed cuts to "... more".
HASHTAG_LIMIT = 5        # Instagram's cap per post or reel since 18 Dec 2025,
                         # down from 30. Announced by the @Creators account:
                         # "using fewer (up to 5) more targeted hashtags,
                         # rather than many generic ones, can improve both your
                         # content's performance and people's experience".

EMOJI_WARN_PER_100 = 4   # emoji per 100 characters above which the caption
                         # reads as decoration rather than punctuation.

HASHTAG_RE = re.compile(r"(?:^|\s)(#[A-Za-z0-9_]+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[A-Za-z0-9_.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:com|co|io|net|org|ai|app)/\S*",
                     re.IGNORECASE)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-⇿️]")
# Identical copy in ig-reel/beats.py. The ig-* folders are copied on
# their own, so this stays a copy rather than an import; keep the two in
# sync (pinned by ig-viral/test_ig_shared_parts_characterization.py).
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)

ASKS = [
    (re.compile(r"(?i)\bcomment (?:the word |\")?[A-Z0-9]{2,}\b"), "comment a keyword"),
    (re.compile(r"(?i)\b(?:dm|message) me\b"), "DM me"),
    (re.compile(r"(?i)\bsave (?:this|it)\b"), "save this"),
    (re.compile(r"(?i)\bshare (?:this|it)\b"), "share this"),
    (re.compile(r"(?i)\bfollow (?:me|for)\b"), "follow"),
    (re.compile(r"(?i)\blink in (?:my )?bio\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:swipe|tap) (?:through|left|right|for|to)\b"), "swipe or tap"),
    (re.compile(r"(?i)\btell me\b|\bwhat would you\b|\bwhich one\b"), "answer a question"),
]

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily"}


def visible_window(text, cut):
    """What the feed shows. Instagram cuts mid-word, so this does too."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  WHAT THE FEED SHOWS", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "... more" if truncated else "(whole caption fits)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def _check(name, status, detail):
    return {"check": name, "status": status, "detail": detail}


def _length_check(chars):
    return _check("LENGTH", "FAIL" if chars > LIMIT else "PASS",
                  f"{chars} / {LIMIT} characters" + (f", {chars - LIMIT} over the limit"
                                                     if chars > LIMIT else ""))


def _first_line_check(first_line, cut):
    if not first_line:
        return _check("FIRST LINE", "FAIL", "the caption opens on a blank line")
    if first_line.startswith("#") or first_line.startswith("@"):
        return _check("FIRST LINE", "FAIL",
                      "opens on a hashtag or a mention, which is the one position worth a sentence")
    if len(first_line) > cut:
        return _check("FIRST LINE", "WARN",
                      f"{len(first_line)} characters, so it gets cut at {cut} mid-thought. "
                      "Fine if the cut is a cliffhanger, bad if it is a subordinate clause")
    return _check("FIRST LINE", "PASS", f"{len(first_line)} characters, lands whole")


def _hook_concrete_check(window):
    return _check("HOOK IS CONCRETE", "PASS" if CONCRETE_RE.search(window) else "WARN",
                  f"{len(CONCRETE_RE.findall(window))} number(s) or name(s) in the visible window"
                  + ("" if CONCRETE_RE.search(window) else " - nothing checkable before the tap"))


def _hashtags_check(tags, filler):
    if len(tags) > HASHTAG_LIMIT:
        return _check("HASHTAGS", "FAIL", f"{len(tags)} tags, over Instagram's cap of {HASHTAG_LIMIT}. "
                                          "Tags past the fifth do not count and the block reads as old")
    if len(tags) == HASHTAG_LIMIT and filler:
        return _check("HASHTAGS", "WARN", f"{len(tags)} tags, at the cap, and "
                                          f"{len(filler)} of them generic. Spend the five on topics")
    if filler:
        return _check("HASHTAGS", "WARN", f"{len(tags)} tags, {len(filler)} of them generic "
                                          f"({', '.join(filler[:3])}). Those describe nothing")
    return _check("HASHTAGS", "PASS", f"{len(tags)} tag(s)" + (f": {' '.join(tags)}" if tags else ""))


def _tag_placement_check(tags, window):
    if not tags:
        return _check("TAG PLACEMENT", "PASS", "no tags to place")
    if any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        return _check("TAG PLACEMENT", "WARN", "a hashtag is inside the visible window, "
                                               "spending feed space on a label")
    return _check("TAG PLACEMENT", "PASS", "tags are below the fold")


def _links_check(links):
    return _check("LINKS", "WARN" if links else "PASS",
                  f"{len(links)} link(s) in the caption, and captions are not clickable. "
                  f"Move it to the bio or the DM" if links else "no dead links in the body")


def _one_ask_check(asks):
    if len(asks) == 1:
        return _check("ONE ASK", "PASS", f"one call to action: {asks[0]}")
    if not asks:
        return _check("ONE ASK", "WARN", "no call to action. Decide what this post is for")
    return _check("ONE ASK", "WARN", f"{len(asks)} asks ({', '.join(asks)}). "
                                     "Two asks is the same as none")


def _emoji_check(emoji_count, chars):
    density = emoji_count * 100 / max(chars, 1)
    return _check("EMOJI", "WARN" if density > EMOJI_WARN_PER_100 else "PASS",
                  f"{emoji_count} emoji, {density:.1f} per 100 characters"
                  + (" - reads as decoration" if density > EMOJI_WARN_PER_100 else ""))


def _search_terms_check(keywords, stripped, window):
    if not keywords:
        return None
    low = stripped.lower()
    found = [k for k in keywords if k.lower() in low]
    missing = [k for k in keywords if k.lower() not in low]
    in_window = [k for k in found if k.lower() in window.lower()]
    status = "PASS" if not missing else ("WARN" if found else "FAIL")
    return _check("SEARCH TERMS", status,
                  f"{len(found)}/{len(keywords)} present"
                  + (f", {len(in_window)} in the visible window" if found else "")
                  + (f". Missing: {', '.join(missing)}" if missing else ""))


def analyse(text, cut=TRUNCATE, keywords=None):
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = HASHTAG_RE.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    asks = [name for pattern, name in ASKS if pattern.search(stripped)]
    filler = [t for t in tags if t.lower() in FILLER_TAGS]
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = [
        _length_check(chars),
        _first_line_check(first_line, cut),
        _hook_concrete_check(window),
        _hashtags_check(tags, filler),
        _tag_placement_check(tags, window),
        _links_check(links),
        _one_ask_check(asks),
        _emoji_check(len(emoji), chars),
    ]
    search_terms = _search_terms_check(keywords, stripped, window)
    if search_terms:
        checks.append(search_terms)

    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    verdict = "FIX" if fails else ("REVIEW" if warns else "READY")

    return {
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks,
        "checks": checks, "verdict": verdict,
    }


def render(a, out=sys.stdout):
    head = (f"CAPTION LINT  ·  {a['characters']} / {a['limit']} chars  ·  "
            f"{len(a['hashtags'])} hashtags  ·  {len(a['asks'])} ask(s)")
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {c['status']:<5} {c['check']:<17} {c['detail']}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  VERDICT  {a['verdict']}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Lint an Instagram caption.")
    ap.add_argument("input", nargs="?", default="-", help="caption file, or - for stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"characters shown before '... more' (default {TRUNCATE})")
    ap.add_argument("--keywords", default="", help="comma-separated terms you want to be found for")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","))
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0 if a["verdict"] == "READY" else 1)


if __name__ == "__main__":
    main()
