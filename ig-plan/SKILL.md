---
name: ig-plan
description: >-
  Build the week on Instagram - what to post, which format, when, and who to
  engage with. Use when the user says "plan my week", "what should I post",
  "content calendar", "I have nothing to post about", or wants a posting
  schedule and an engagement list.
---

# ig-plan

The control room. Everything else in this pack executes; this decides what gets
executed. Run it once a week, on the same day.

## Input

If `~/.claude/instagram/voice.md`, `swipe.md` and `log.md` exist, read them.
The swipe file is the user's own evidence from `/ig-viral` about which formulas
are landing in their niche right now, and it outranks anything in this file.
The log stops the plan repeating a theme from the last fortnight.

If they do not exist, ask for four things and write them down:

1. What the user sells, and to whom.
2. The three or four themes they want to be known for.
3. What actually happened this week: a client call, a number, a mistake, a
   thing they built, an argument they had. This is where posts come from.
4. Ten accounts worth being visible to.

## What to post

Check the composition with `plan_check.py` in this folder before the plan
is final. It lists every violation of the weekly counts (four to five
posts, at least three of them Reels), the per-type counts and formats,
and the rule that no two posts of the same type sit back to back. If it
reports violations, fix the plan and check again; do not finalise a
failing plan. The limits are the tool's `--min-posts`, `--max-posts` and
`--min-reels` variables and its `TYPE_RULES`; the defaults are the
numbers above.

Reels are the only format on Instagram that reliably reaches people who
do not follow the account. Carousels go deep with the people who already
do. Stories are daily and are planned separately.

What each type is for:

- **Proof** — something that happened, with a number.
- **Teach** — one thing the viewer can do today.
- **Opinion** — a position that could lose you followers.
- **Story** — a scene with a cost.
- **Offer** — what you sell, said plainly, no apology.

For each slot give: the theme, the specific angle from what actually happened
this week, the format, and the hook formula number from `ig-reel/hooks.json`.
Not a topic, an angle. "AI" is not a plan. "The proposal we lost because the
draft had an em dash in it" is a Reel.

## When to post

Guide times, by audience:

- Consumer audience: early evening, local time.
- Business audience: early morning, local time.

Local time means the audience's timezone. If the audience and the user
are in different timezones, use the audience's.

These times apply only when both of these hold:

- The audience is awake.
- The audience is not at work.

Priority: the hour matters far less than the first two seconds. A Reel
that performs keeps being shown for days; a well-timed Reel that does
not perform gets buried. If the user is working on posting times before
their hooks work, say plainly that they are polishing the wrong thing.

## The engagement round, which is not optional

20 minutes a day, before posting, not after. Build a list of 10:

- **5 reach** - accounts with an audience the user wants, where a good comment
  gets seen. Comment early, before the thread is 200 deep.
- **3 peers** - same size, same field. This is the group that reciprocates.
- **2 buyers** - people who could actually buy. Comment for weeks before any
  DM, and never pitch in a comment.

Hand the list to `/ig-comment`.

## Output

```
WEEK OF SEP 15

MON  engage only  (20 min, list below)
TUE  7:30pm  REEL      PROOF    #5  Time Collapse   - 5hr proposal to 20 min
WED  stories only + engage
THU  7:00pm  CAROUSEL  TEACH    Job B caption       - the 8-slide clause breakdown
FRI  7:30pm  REEL      OPINION  #2  Negative Command - stop doing discovery calls
SAT  -
SUN  6:00pm  REEL      STORY    #21 Mid-Sentence    - the refund email

STORIES  every day, 3 to 5 frames, question box on Thursday.

ENGAGE  (5 reach / 3 peers / 2 buyers)
  ...

Say "write Tuesday" and I will draft it.
```

Write the plan to `~/.claude/instagram/plan.md` so the other skills can read
it. Nothing is scheduled or posted anywhere. This is a plan and the user runs
it.
