#!/usr/bin/env python3
"""
detect.py - a five-check panel that scores how machine-written a draft looks.

What this is:  five local heuristics modelled on the signals public AI
detectors actually measure - sentence-length variation, concreteness, stock
vocabulary, typographic fingerprint, and voice. Every score is computed on
your machine from the text alone. Nothing is uploaded.

What this is NOT:  GPTZero, Originality, Copyleaks, Winston or Turnitin.
It does not call their APIs and it cannot promise their verdict. It catches
the things they all key on, which is why fixing them tends to move their
numbers too - but the only honest claim is the one on this line.

Each check returns a HUMAN score from 0 to 100. Higher is better.

Usage
  python3 detect.py draft.txt
  pbpaste | python3 detect.py -
  python3 detect.py draft.txt --json
  python3 detect.py before.txt after.txt      # compare two drafts
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

# Scoring values. Calibrated; named so that changing one is a single
# deliberate edit rather than a hunt through the checks. The scale()
# endpoints are the human/machine anchors each check is mapped between.
TOO_SHORT_WORDS = 25           # below this a check says "too short to judge"
BURSTINESS_HUMAN_CV = 0.70
BURSTINESS_MACHINE_CV = 0.22
SPECIFICITY_HUMAN_DENSITY = 6.0
SPECIFICITY_MACHINE_DENSITY = 0.5
SLOP_HUMAN_DENSITY = 0.0
SLOP_MACHINE_DENSITY = 4.0
FINGERPRINT_HUMAN_PER_1K = 0.0
FINGERPRINT_MACHINE_PER_1K = 12.0
FINGERPRINT_INVISIBLE_WEIGHT = 4
FINGERPRINT_EM_DASH_WEIGHT = 2
VOICE_CONTRACTION_HUMAN = 3.0
VOICE_CONTRACTION_MACHINE = 0.0
VOICE_PERSON_HUMAN = 8.0
VOICE_PERSON_MACHINE = 1.0
VOICE_CONTRACTION_WEIGHT = 0.35
VOICE_PERSON_WEIGHT = 0.35
VOICE_TELLS_WEIGHT = 0.30
VOICE_TELL_PENALTY = 22        # score points per structural tell
UNIFORM_BULLETS_PSTDEV = 1.6   # bullet lengths closer than this are uniform
UNIFORM_BULLETS_PENALTY = 12
OVERALL_MEAN_WEIGHT = 0.6
OVERALL_MIN_WEIGHT = 0.4
PASS_THRESHOLD = 70
PASS_MIN_CHECK = 55
REVIEW_THRESHOLD = 50

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-z']+")
CONTRACTIONS = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)
PRONOUNS = re.compile(r"\b(i|me|my|mine|we|us|our|you|your)\b", re.IGNORECASE)
NUMBERS = re.compile(r"\b\d[\d,.]*%?\b|\$\d")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)


# clamp() and bar() below are identical copies of the ones in
# ig-reel/hookscore.py; keep them in sync (pinned by
# ig-viral/test_ig_shared_parts_characterization.py). WORD_RE above is
# deliberately narrower than the ig-reel one: it drops digits and money.
def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Map value onto 0-100 where `human` -> 100 and `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text):
    return WORD_RE.findall(text)


def check_burstiness(text):
    """Humans vary sentence length hard. Models write even."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "too short to judge"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=BURSTINESS_HUMAN_CV, machine=BURSTINESS_MACHINE_CV)
    return score, f"variation {cv:.2f} across {len(lens)} sentences (want 0.55+)"


def check_specificity(text):
    """Numbers, names and concrete nouns. Slop is abstract."""
    w = words(text)
    if len(w) < TOO_SHORT_WORDS:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    hits = len(NUMBERS.findall(text)) + len(set(PROPER.findall(text)))
    density = hits * per100
    score = scale(density, human=SPECIFICITY_HUMAN_DENSITY,
                  machine=SPECIFICITY_MACHINE_DENSITY)
    return score, f"{hits} concrete markers, {density:.1f} per 100 words (want 4+)"


def check_slop(text, lex):
    """Stock vocabulary density against the lexicon."""
    w = words(text)
    if not w:
        return 50.0, "empty"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        pattern = re.compile(r"\b" + re.escape(entry["find"]).replace(r"\ ", r"\s+") + r"\b",
                             re.IGNORECASE)
        n = len(pattern.findall(text))
        if n:
            hits += n
            found.append(entry["find"])
    density = hits * 100 / len(w)
    score = scale(density, human=SLOP_HUMAN_DENSITY, machine=SLOP_MACHINE_DENSITY)
    detail = f"{hits} stock terms, {density:.1f} per 100 words"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text):
    """Characters a phone keyboard does not produce."""
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf")
    em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    total = (invisible * FINGERPRINT_INVISIBLE_WEIGHT
             + em * FINGERPRINT_EM_DASH_WEIGHT + curly + ellip + nbsp)
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=FINGERPRINT_HUMAN_PER_1K,
                  machine=FINGERPRINT_MACHINE_PER_1K)
    detail = (f"{invisible} invisible, {em} em dash, {curly} curly quote, "
              f"{ellip} ellipsis, {nbsp} hard space")
    return score, detail


def check_voice(text, lex):
    """Contractions, person, and the shapes models default to."""
    w = words(text)
    if len(w) < TOO_SHORT_WORDS:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    contractions = len(CONTRACTIONS.findall(text)) * per100
    person = len(PRONOUNS.findall(text)) * per100
    tells = 0
    names = []
    for s in lex["structures"]:
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3
               and statistics.pstdev(bullets) < UNIFORM_BULLETS_PSTDEV)
    score = (scale(contractions, human=VOICE_CONTRACTION_HUMAN,
                   machine=VOICE_CONTRACTION_MACHINE) * VOICE_CONTRACTION_WEIGHT
             + scale(person, human=VOICE_PERSON_HUMAN,
                     machine=VOICE_PERSON_MACHINE) * VOICE_PERSON_WEIGHT
             + clamp(100 - tells * VOICE_TELL_PENALTY) * VOICE_TELLS_WEIGHT)
    if uniform:
        score -= UNIFORM_BULLETS_PENALTY
        names.append("uniform-bullets")
    detail = (f"{contractions:.1f} contractions, {person:.1f} personal pronouns "
              f"per 100 words, {tells} structural tell(s)")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["BURSTINESS", "SPECIFICITY", "SLOP DENSITY", "FINGERPRINT", "VOICE"]


def run(text, lex):
    results = {}
    results["BURSTINESS"] = check_burstiness(text)
    results["SPECIFICITY"] = check_specificity(text)
    results["SLOP DENSITY"] = check_slop(text, lex)
    results["FINGERPRINT"] = check_fingerprint(text)
    results["VOICE"] = check_voice(text, lex)
    scores = [results[c][0] for c in CHECKS]
    # The weakest check drags the verdict: a detector only needs one signal.
    overall = (statistics.mean(scores) * OVERALL_MEAN_WEIGHT
               + min(scores) * OVERALL_MIN_WEIGHT)
    verdict = ("PASS" if overall >= PASS_THRESHOLD
               and min(scores) >= PASS_MIN_CHECK else (
                   "REVIEW" if overall >= REVIEW_THRESHOLD else "FLAGGED"))
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout):
    title = "AI DETECTION PANEL" + (f"  -  {label}" if label else "")
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HUMAN SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != "PASS":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest signal: {weakest}. Fix that first.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Score how machine-written a draft looks.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("compare", nargs="?", help="second file, to show before/after")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lexicon", default=LEX)
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
