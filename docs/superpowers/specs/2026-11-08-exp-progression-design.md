# EXP progression: honest live rate, cleaner history, best maps

Four changes to the EXP meter (`src/maplelens/tools/exp_meter/`), all in one PR.

## Why

The owner trains with the EXP tab open and checks History to decide where to train next.
Four things get in the way:

1. **The live rate is wrong for the first 5 minutes.** `ExpMeter.rate()` divides the EXP
   gained by wall-clock time since the app started (up to 5 min). Time in town, walking to
   the map or standing AFK counts as training time, so the number starts low and only
   becomes honest once a full 5 minutes of real training fill the window.
2. **History is full of short visits.** Walking through a map and killing two monsters
   saves a row. The open visit is flushed every 60 s, so anything over a minute lands in
   the database.
3. **Map names are unreadable.** Titles are stored as `"<street> / <name>"`, e.g.
   `"Victoria Island / Henesys Hunting Ground I"` or `"Hidden Street / ..."`. The Map column
   truncates them, so most rows show only the same prefix.
4. **No quick answer to "what's my best map?"** The table can be sorted by EXP/h, but
   EXP/h rises with level (stronger character, stronger monsters), so a raw sort just
   lists the maps trained at the highest levels.

## Goals

- The live rate is right after about a minute of training, and stays right through AFK
  breaks.
- History rows (and the class helper's `best_rate`) only count visits of 5 minutes or more.
- The Map column shows the map's own name.
- The History window opens with the owner's top 3 maps for their current class and level,
  each with its rate.

## Non-goals

- No change to readers, the segment model (map/class/level), or the database schema.
- Old short visits already in the database are hidden, not deleted.
- The live window is not reset on a map change (not asked for).
- No new settings.

## Anti-goals

- The live rate must not decay toward zero while the player is AFK; it should say so instead.
- No migration step that could lose a player's history.

## 1. Live rate over active time

**Active time** = the sum of gaps between consecutive counted EXP gains, where a gap
longer than the idle cutoff counts as zero. This is the same rule `Segment.active_s`
already uses, so the live rate and the History averages measure the same thing.

- A gain whose preceding gap is longer than the cutoff (or the very first gain) starts a
  fresh stretch: its gap is not counted and **neither is its amount**, so
  `rate = sum(amounts) / sum(gaps)` over gains whose preceding gap ≤ cutoff.
- The window is the **last 5 minutes of active time** (`window_s = 300`), not the last
  5 wall-clock minutes. Walk back from the newest gain, summing counted gaps, until 300 s
  is reached; older gains can be dropped from the deque.
- `rate()` returns `None` until there is at least **60 s of active time** in the window
  (replaces today's "60 s since the first reading").
- **Paused:** when `now - last counted gain > cutoff`, the rate keeps its last value and is
  flagged paused. Add `paused: bool` to `Rate`. The box shows the numbers with the label
  `EXP · paused` instead of `EXP · last 5 min`. The level-up ETA keeps using the
  active-time rate.
- Gains rejected by `_gain` (death, misread, spike) are not in the window, as today. Their
  timestamps don't count as gains for gap purposes either (my call: simplest, and a death
  is rare).
- The window spans level-ups and map changes, as today.

**The cutoff (my call):** the owner suggested 1 minute. The meter already has
`idle_cutoff_s` (default 90 s, saved in existing players' settings files) for the History
active time. I'm using that one setting for both, so the live and history rates agree and
there's one knob. Changing the default to 60 wouldn't reach players who already have a
settings file anyway. Builder: keep it a single value passed to `ExpMeter`.

## 2. History: visits of 5 minutes or more

A **visit** is one `Segment`: one map, class and level. A level-up partway through splits a
visit, and each piece is judged on its own (my call).

- **Qualifies** when `end - start >= 300` (time on the map, not active time). Constant
  `MIN_VISIT_S = 300` in `history.py`, not a setting.
- **Saving:** `ExpMeterTool._save` flushes the open segment only once it qualifies, and a
  closed segment is saved only if it qualifies.
- **Reading:** `history()` and `best_rate()` both add `AND end - start >= 300` to their
  `WHERE`, which also hides short visits saved by older versions. Nothing is deleted.

## 3. Map names

In the History window (table and the strip below), show only the part after the last
`" / "` (`title.rpartition(" / ")[2]`); the full title goes in the cell's tooltip. Grouping
and storage keep the full title. Sorting the Map column sorts by the short name.

## 4. "Best for you now" strip

A strip at the top of the History window, above the table:

```
Best for Rogue, Lv 28 (±3)
  Henesys Hunting Ground I    52,300 EXP/h   1.85% /h
  Ant Tunnel I                47,900 EXP/h   1.70% /h
  Pig Beach                   41,200 EXP/h   1.42% /h
```

- **Which rows:** the owner's own history only, visits that qualify (section 2), for the
  **current job line**, at levels **current − 3 to current + 3**. Grouped by map, rate =
  `SUM(exp) / SUM(active_s)` across those levels (same formula as `history()`), top 3 by
  EXP/h. A new pure query function in `history.py`, e.g.
  `best_maps(conn, jobs: set[str], level, n=3, spread=3) -> list[HistoryRow-like]`
  (`WHERE job IN (...)`).
- **Job line (the owner's decision):** not just the exact job name the game shows, so that
  right after an advancement (Lv 10, 30, 70) an Assassin at Lv 31 still counts their Rogue
  visits at Lv 28–30. The line of a job = the job itself, every job before it and every job
  after it on the advancement tree (`next_jobs` in `classes.json`, from both the job's and
  its builds' `advance`), plus Beginner. Sibling branches are left out: an Assassin's line
  has Rogue and Hermit but not Bandit. Beginner is in every line (my call: everyone was one).
  Aliases apply both ways: History stores the reader's name, so a line that holds "Rogue"
  also holds "Thief" (`class_helper/data.py` `ALIASES`). A job missing from `classes.json`
  has a line of just itself (plus its alias).
- **Where the line comes from:** `exp_meter` may not import `class_helper` (AGENTS.md: a
  tool depends only on readers and overlay). Add `ClassData.line(job) -> frozenset[str]`
  in `class_helper/data.py`, and have `app.py` pass `lambda j: class_data_obj.line(j)` into
  `ExpMeterTool`, the same way it already hands the class helper `best_rate` from
  `exp_meter`. The strip header still names the current job (`Best for Assassin, Lv 31`).
- **Rate shown:** EXP/h and %/h, formatted as in the table.
- **Current class and level:** the meter's confirmed values (`ExpMeter` exposes them;
  today they're `_job.value` / `_level.value`). `HistoryWindow.refresh` takes them as
  arguments; `ExpMeterTool._show_history` passes them. The strip refreshes whenever the
  window is shown, like the table.
- **Empty states:** class or level unknown (game not read yet) → `Best maps: waiting for
  your class and level`. Known but no qualifying history in range → `Best for Rogue, Lv 28
  (±3): no 5-minute visits yet`.
- **Look:** plain Qt labels in the window, same plain style as the table (the History
  window is a normal desktop window, not overlay). Layout details are the builder's call.
  `HistoryWindow` is a `QTableWidget` today; it becomes a `QWidget` holding the strip and
  the table.
- Not clickable (no route start from here). The Class tab already starts routes.

## Testing

Pure logic gets tests in the existing files, no game needed:

- `tests/test_meter.py`: rate available after 60 s of active time even if the app started
  long before; an AFK gap > cutoff neither adds time nor lets the rate decay; the gain right
  after an AFK gap isn't counted; window covers the last 300 s of active time across a gap;
  `paused` flag set after the cutoff. Update `test_rate_none_before_a_minute` to the new
  rule.
- `tests/test_history.py`: short segments are hidden from `history()` and `best_rate()`;
  `best_maps` picks the given jobs, ±3 levels, top 3 by EXP/h, and returns nothing for
  an empty range.
- `tests/test_class_data.py`: `line("Assassin")` holds Beginner, Rogue, Thief, Assassin,
  Hermit and not Bandit; an unknown job's line is just itself.
- `tests/test_ui.py`: the existing open-segment flush test grows past 5 minutes.
- `tests/test_text.py`: the short-name helper and the paused label in `box_lines`.
- `tests/test_ui.py`: `_save` skips an open segment under 5 minutes; the strip's empty
  states.

## Left to the builder

- Exact strip layout and spacing, and where the short-name helper lives (`text.py` fits).
- Deque pruning details, as long as the rate matches the definition above.
