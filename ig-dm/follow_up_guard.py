#!/usr/bin/env python3
"""
follow_up_guard.py - stop follow-up DMs past the limit.

A state guard for the ig-dm "Follow-ups" section. Follow-ups are two,
that is the number: the first at +4 days with something new added, the
second at +10 days as the close-the-loop message. A third attempt is
stopped and is not recorded, so the limit holds in state, not only in
the wording of the skill.

The limit, the schedule days and the banned phrase are variables, not
fixed values in the logic. The defaults follow the skill: two
follow-ups, due at +4 and +10 days, and "just bumping this" is banned.

Usage
  python3 follow_up_guard.py --state state.json check
  python3 follow_up_guard.py --state state.json send \\
      --day-offset 4 --text "New data on this."
  python3 follow_up_guard.py --state state.json send \\
      --day-offset 10 --text "I will stop here."

``check`` prints {"can_send", "follow_up_count", "next_due_day",
"is_next_final"}. ``send`` prints {"decision", "follow_up_count",
"message"} where decision is "allow", "blocked_too_early",
"blocked_banned_phrase" or "stop_limit_reached". Exit code is 0 when
the send is allowed (or for check), 1 when it is stopped or blocked.
"""

import argparse
import json
import sys
from pathlib import Path

ALLOW = "allow"
BLOCKED_TOO_EARLY = "blocked_too_early"
BLOCKED_BANNED_PHRASE = "blocked_banned_phrase"
STOP_LIMIT_REACHED = "stop_limit_reached"

DEFAULT_MAX_FOLLOW_UPS = 2
DEFAULT_SCHEDULE_DAYS = (4, 10)
DEFAULT_BANNED_PHRASES = ("just bumping this",)


class FollowUpGuard:
    """Count sent follow-ups and decide whether another may be sent."""

    def __init__(
        self,
        max_follow_ups=DEFAULT_MAX_FOLLOW_UPS,
        schedule_days=DEFAULT_SCHEDULE_DAYS,
        banned_phrases=DEFAULT_BANNED_PHRASES,
    ):
        self.max_follow_ups = max_follow_ups
        self.schedule_days = tuple(schedule_days)
        self.banned_phrases = tuple(banned_phrases)
        self._history = []

    def follow_up_count(self):
        return len(self._history)

    def history(self):
        return [dict(item) for item in self._history]

    def can_send(self):
        return self.follow_up_count() < self.max_follow_ups

    def is_next_final(self):
        return self.follow_up_count() == self.max_follow_ups - 1

    def next_due_day(self):
        count = self.follow_up_count()
        if count >= self.max_follow_ups:
            return None
        if count < len(self.schedule_days):
            return self.schedule_days[count]
        return self.schedule_days[-1] if self.schedule_days else None

    def can_send_on_day(self, day_offset):
        if not self.can_send():
            return False
        due = self.next_due_day()
        return due is None or day_offset >= due

    def record_follow_up(self, day_offset=None, text=None):
        """Try to record one follow-up send and return the decision."""
        count = self.follow_up_count()
        if not self.can_send():
            return {
                "decision": STOP_LIMIT_REACHED,
                "follow_up_count": count,
                "message": (
                    "Follow-up limit reached. Stop sending and " "close the loop."
                ),
            }
        if text:
            lowered = text.lower()
            for phrase in self.banned_phrases:
                if phrase.lower() in lowered:
                    return {
                        "decision": BLOCKED_BANNED_PHRASE,
                        "follow_up_count": count,
                        "message": (
                            f"Banned follow-up phrase: {phrase}. "
                            "Add something new instead."
                        ),
                    }
        if day_offset is not None:
            due = self.next_due_day()
            if due is not None and day_offset < due:
                return {
                    "decision": BLOCKED_TOO_EARLY,
                    "follow_up_count": count,
                    "message": (
                        f"Too early: this follow-up is due at "
                        f"+{due} days, not +{day_offset} days."
                    ),
                }
        self._history.append({"day_offset": day_offset, "text": text or ""})
        return {
            "decision": ALLOW,
            "follow_up_count": self.follow_up_count(),
            "message": "Follow-up recorded.",
        }

    def to_dict(self):
        return {
            "max_follow_ups": self.max_follow_ups,
            "schedule_days": list(self.schedule_days),
            "banned_phrases": list(self.banned_phrases),
            "history": self.history(),
        }

    @classmethod
    def from_dict(cls, data):
        guard = cls(
            max_follow_ups=data.get("max_follow_ups", DEFAULT_MAX_FOLLOW_UPS),
            schedule_days=tuple(data.get("schedule_days", DEFAULT_SCHEDULE_DAYS)),
            banned_phrases=tuple(data.get("banned_phrases", DEFAULT_BANNED_PHRASES)),
        )
        guard._history = [dict(item) for item in data.get("history") or []]
        return guard

    @classmethod
    def from_history(cls, history, **kwargs):
        guard = cls(**kwargs)
        guard._history = [dict(item) for item in history or []]
        return guard

    def save(self, path):
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _load_guard(args):
    state_path = Path(args.state)
    if state_path.exists():
        guard = FollowUpGuard.load(state_path)
        if args.max_follow_ups is not None:
            guard.max_follow_ups = args.max_follow_ups
        return guard
    return FollowUpGuard(
        max_follow_ups=(
            args.max_follow_ups
            if args.max_follow_ups is not None
            else DEFAULT_MAX_FOLLOW_UPS
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stop follow-up DMs past the limit.")
    parser.add_argument("--state", required=True, help="state file (JSON)")
    parser.add_argument("--max-follow-ups", type=int, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("--day-offset", type=int, default=None)
    send_parser.add_argument("--text", default=None)
    args = parser.parse_args(argv)

    guard = _load_guard(args)
    if args.command == "check":
        print(
            json.dumps(
                {
                    "can_send": guard.can_send(),
                    "follow_up_count": guard.follow_up_count(),
                    "next_due_day": guard.next_due_day(),
                    "is_next_final": guard.is_next_final(),
                },
                ensure_ascii=False,
            )
        )
        return 0
    result = guard.record_follow_up(day_offset=args.day_offset, text=args.text)
    if result["decision"] == ALLOW:
        guard.save(args.state)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["decision"] == ALLOW else 1


if __name__ == "__main__":
    sys.exit(main())
