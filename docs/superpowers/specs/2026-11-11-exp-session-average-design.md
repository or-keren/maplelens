# MapleLens: EXP meter session average design

Date: 2026-11-11. Status: approved by the owner (2026-11-11).
Issue: [or-keren/maplelens#50](https://github.com/or-keren/maplelens/issues/50).
Mockup the owner picked (D, blank under the session): `.superpowers/brainstorm/815-1794426036/content/session-box-v3.html`
(local, not committed; this document is the reference).

## Intent

The EXP tab shows only the last 5 active minutes. A slow start or a lucky last 5 minutes
swings that number, and there is no number for "how well am I doing in general this
session" (owner). Today the owner checks History after the visit is over.

Add a **session average**: active EXP/h over the whole session, next to the last-5-min
rate. The owner's words set the scope: the session is the whole session, and "not sure
that a level up should interfere with that". So the issue's first idea (the current
map/class/level segment) is dropped: a segment ends at every level-up and map change.

The screen-only rule in `AGENTS.md` holds: this only adds arithmetic over readings the
meter already takes.

## Goals

- **One session number across maps, classes and levels** (owner). A level-up, a map change
  or a class change never resets it.
- **A session splits by itself after a long break** (owner picked this over a Reset
  button): 30 minutes with no counted EXP gain ends the session. The next counted gain starts a
  new one. Closing MapleLens ends it too.
- **Shown beside the last-5-min rate, in two columns** (owner picked layout D):

  ```
  EXP  Path  Class  Quests          <- the tabs, as today
  Last 5 min      Session · 2h 10m
  12,345 /h       10,870 /h
  1.23% /h                          <- blank under the session (owner)
  Level up in
  1h 5m
  [History]
  ```

  The box keeps today's width (`TAB_W`). The mockup checked that seven-digit numbers
  ("1,234,567 /h") still fit side by side at 214 px.
- **Active EXP/h only, no %/h for the session** (owner: blank instead of the %). A percent
  per hour doesn't add up across levels.

## Non-goals

- Saving the session anywhere, or showing it in History. History keeps per-segment
  visits, as today.
- A Reset button, a setting for the 30 minutes, or a choice of window length (that is
  [#20](https://github.com/or-keren/maplelens/issues/20)).
- A session "Level up in". It stays on the last-5-min rate (my call: the current pace
  predicts the next level better than a session that began two maps ago).
- Mesos. When mesos comes, the box will likely gain an "EXP" heading over these two
  columns and a matching "Mesos" block (owner looked at this, mockup G, and chose to leave
  the tab name as the only "EXP" for now).

## Anti-goals

- A session number that disagrees with History's way of counting. It must count exactly
  the gains a segment counts (below), so a one-map, one-level session matches that
  segment's totals (`open_segment()`; a History row also pools earlier visits, so it isn't
  the comparison).
- A wider box, or a box that blinks: the two-column row must keep the tab's fixed width
  and the "same rows, new text only" update `ExpMeterTool._show` does today.

## How it counts

- **Which gains:** the gains the open segment counts (`Segment.gains` in `meter.py`):
  timed from the segment clock, under the idle cutoff, not while map/job/level is
  unreadable, not in monster-free towns (quest rewards). The session is all such gains
  since it began, across segments.
- **Totals:** the same `_totals(gains, idle_cutoff_s)` the segments use, run per segment
  and summed, so the break filter (buffs, walking, looting) applies too, with each map's
  own pace. (Run once over the pooled session, a fast map's pace made a slower map's kills
  look like breaks and dropped that map; found in review.) EXP/h = exp / active_s × 3600.
- **Under a minute of active time:** "— /h", as the live rate does.
- **The 30-minute split:** when a counted gain arrives more than 30 minutes after the
  previous counted gain, the session is cleared first and that gain starts the new one. A constant in
  `meter.py` (`SESSION_BREAK_S = 1800`), no setting (my call).
- **During a long break:** the old session's number stays on screen until the first gain
  of the new session (my call). A quick disconnect or relog under 30 minutes keeps the
  session.

## The box

- **Left column label:** "Last 5 min" (my call: no "EXP ·" prefix, the tab says EXP; owner
  agreed for now). It changes to "Measuring" under a minute of active time (from main's
early estimate), to "Paused" when the live rate is paused and to
  "Can't read bar" in the accent colour when the bar is unreadable, as the label does
  today.
- **Right column label:** "Session · " + the session's active time via `format_duration`
  ("Session · 2h 10m"; "Session · <1m" at the start). Before the session's first counted gain,
  just "Session".
- **Values:** left as today (EXP/h, %/h). Right: the session EXP/h, then a blank line.
- **"Waiting for game"** replaces the whole box as today.
- **Below:** "Level up in" and the History button, unchanged.
- **Column width:** the two columns split whatever width the tab has (my call: the player
  can drag the tabs out to `MAX_TAB_W`), never a fixed half of `TAB_W`.

## Left to the builder

- How `box_lines` and `ExpMeterTool._show` carry a row of two columns (a grid row, or a
  new row shape). Keep the text pure in `text.py` and tested; keep the no-blink update.
- Where the session totals live: `ExpMeter` is the natural place (it already sees every
  segment's gains), e.g. a `session(now)` method beside `rate(now)`.
- Check in the real app on Windows (and the Mac's 220 px `TAB_W`) that "Session · 12h 10m"
  and two seven-digit values fit; if the label doesn't, drop the minutes (e.g.
  "Session · 12h").
- Tests: meter (across a level-up and a map change; the 30-minute split; matching a
  segment's totals) and text (labels and values, the blank line).
