#!/usr/bin/env python3
"""
login_attempts.py - stop a failed login route from being repeated.

A small state counter for login attempts. Each route (a sign in method, a
code sent by text message, and so on) may fail only up to a per-route
limit, and only so many distinct routes may fail before trying stops
altogether and the task moves to the fallback: asking the user to finish
the setting on their own device.

The limits are variables, not fixed numbers. The defaults follow the
skill: one failure per route, two distinct failed routes in total.

How a recorded failure is decided (per route):

- "retry_same_route": the route that just failed is still below its
  own limit, so the same route may be retried.
- "try_other_route": the route reached its own limit, but the number
  of routes that have reached their limit is still below the distinct
  limit, so a different route may be tried.
- "stop_fallback": the number of routes that have reached their limit
  has reached the distinct limit. Stop trying and move to the fallback.

Usage
  python3 login_attempts.py --state state.json fail password
  python3 login_attempts.py --state state.json check sms-code
  python3 login_attempts.py --state state.json success password
  python3 login_attempts.py --state state.json --max-same-route 2 fail password

``fail`` prints {"decision", "route", "failure_count", "failed_routes"}
where decision is "retry_same_route", "try_other_route" or
"stop_fallback". ``check`` prints {"can_attempt": bool}.
"""

import argparse
import json
from pathlib import Path

RETRY_SAME_ROUTE = "retry_same_route"
TRY_OTHER_ROUTE = "try_other_route"
STOP_FALLBACK = "stop_fallback"

DEFAULT_MAX_SAME_ROUTE_FAILURES = 1
DEFAULT_MAX_DISTINCT_ROUTE_FAILURES = 2


class LoginAttemptGuard:
    """Count login failures per route and decide when to stop trying."""

    def __init__(
        self,
        max_same_route_failures=DEFAULT_MAX_SAME_ROUTE_FAILURES,
        max_distinct_route_failures=DEFAULT_MAX_DISTINCT_ROUTE_FAILURES,
    ):
        self.max_same_route_failures = max_same_route_failures
        self.max_distinct_route_failures = max_distinct_route_failures
        self._failures = {}

    def failure_count(self, route):
        return self._failures.get(route, 0)

    def failed_routes(self):
        return list(self._failures)

    def _exhausted_routes(self):
        return [
            route
            for route, count in self._failures.items()
            if count >= self.max_same_route_failures
        ]

    def _stopped(self):
        # Trying stops once the routes that reached their own limit
        # reach the distinct limit. See the module docstring for the
        # full decision rules.
        return len(self._exhausted_routes()) >= self.max_distinct_route_failures

    def can_attempt(self, route):
        if self._stopped():
            return False
        return self.failure_count(route) < self.max_same_route_failures

    def record_failure(self, route):
        """Record one failed attempt on ``route`` and return the decision."""
        self._failures[route] = self.failure_count(route) + 1
        if self.failure_count(route) < self.max_same_route_failures:
            return RETRY_SAME_ROUTE
        if self._stopped():
            return STOP_FALLBACK
        return TRY_OTHER_ROUTE

    def record_success(self, route):
        """Record a successful login; all recorded failures are cleared."""
        self._failures.clear()

    def to_dict(self):
        return {
            "max_same_route_failures": self.max_same_route_failures,
            "max_distinct_route_failures": self.max_distinct_route_failures,
            "failures": dict(self._failures),
        }

    @classmethod
    def from_dict(cls, data):
        guard = cls(
            max_same_route_failures=data.get(
                "max_same_route_failures", DEFAULT_MAX_SAME_ROUTE_FAILURES
            ),
            max_distinct_route_failures=data.get(
                "max_distinct_route_failures",
                DEFAULT_MAX_DISTINCT_ROUTE_FAILURES,
            ),
        )
        guard._failures = dict(data.get("failures") or {})
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
        guard = LoginAttemptGuard.load(state_path)
        if args.max_same_route is not None:
            guard.max_same_route_failures = args.max_same_route
        if args.max_distinct_routes is not None:
            guard.max_distinct_route_failures = args.max_distinct_routes
        return guard
    return LoginAttemptGuard(
        max_same_route_failures=(
            args.max_same_route
            if args.max_same_route is not None
            else DEFAULT_MAX_SAME_ROUTE_FAILURES
        ),
        max_distinct_route_failures=(
            args.max_distinct_routes
            if args.max_distinct_routes is not None
            else DEFAULT_MAX_DISTINCT_ROUTE_FAILURES
        ),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Stop a failed login route from being repeated."
    )
    parser.add_argument("--state", required=True, help="state file (JSON)")
    parser.add_argument("--max-same-route", type=int, default=None)
    parser.add_argument("--max-distinct-routes", type=int, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fail", "check", "success"):
        sub = subparsers.add_parser(name)
        sub.add_argument("route")
    args = parser.parse_args(argv)

    guard = _load_guard(args)
    if args.command == "fail":
        decision = guard.record_failure(args.route)
        guard.save(args.state)
        print(
            json.dumps(
                {
                    "decision": decision,
                    "route": args.route,
                    "failure_count": guard.failure_count(args.route),
                    "failed_routes": guard.failed_routes(),
                },
                ensure_ascii=False,
            )
        )
    elif args.command == "check":
        print(json.dumps({"can_attempt": guard.can_attempt(args.route)}))
    elif args.command == "success":
        guard.record_success(args.route)
        guard.save(args.state)
        print(
            json.dumps(
                {"route": args.route, "failed_routes": guard.failed_routes()},
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
