# MapleLens — settings page and EXP sessions design

Date: 2026-11-08, refreshed 2026-11-14. Status: decisions made by Daniel (contributor)
2026-11-08; not built. The owner (or-keren) reviews it with the PR. "My call" marks a choice
made while writing, for Daniel to check.

**Refresh, 2026-11-14 (v0.6.3, `main` at 7be7403).** 47 merges landed since this was written.
`settings-window` and `arrow-options` are rechecked against them below. `build-choice` is
partly done upstream (#72 put a build picker in the Class tab) and needs a decision before it's
built. `exp-sessions` and `best-sessions` clashed with the session average the owner chose in
#79 (`2026-11-11-exp-session-average-design.md`) and were re-decided on top of it the same
day: #79's automatic session stays the default, and manual Start/Pause/Reset is an opt-in.

## Intent

The ••• menu is getting crowded, and it's the only place to change anything. It now mixes
things you do (Quit, Hide) with things you set once (AP/SP marks, update checks, the build).

This work adds a **Settings window**, and moves the set-once items into it. It also adds the
options that have no home today: turning tools off, the path arrow's size and steadiness, and
how EXP sessions work. Players who choose manual tracking get **Start, Pause and Reset** on
the EXP tab, and History gets a **best sessions** list.

The screen-only rule in `AGENTS.md` holds unchanged. Everything here is MapleLens's own
windows and its own data file.

## What's there today (rechecked 2026-11-14, `main` at 7be7403, v0.6.3)

- **Four tools, four tabs:** EXP (0), Path (1), Class (2), Quests (3), in `build_box`'s list
  in `main`. Quests is new since the first draft.
- **Menu** (`app.py`, `main`; one list of the box's actions, shared by the ••• button and the
  tray icon, which is in the menu bar on the Mac since #32; there's no Dock icon any more):
  Update to X.Y.Z… (when there is one), Pick game window…, Open Screen Recording settings…
  (Mac), Build: {name} (when there's a choice), AP/SP marks, Check for updates now, Check
  for updates automatically (both on the installed app, Windows and Mac), Hide, About, Quit.
- **Settings** (`store.py`): a flat `DEFAULTS` dict, now with `tab_width`, `pin_exp` and the
  `quests_*` keys. `load_settings` still does a shallow `update`, so new settings stay flat.
  Nothing validates a saved value's type or range yet.
- **History window** (`exp_meter/ui.py`): no longer a plain desktop window. Since #40 it's
  `Qt.Tool` with `WA_ShowWithoutActivating` everywhere; on Windows also always on top and
  `WindowDoesNotAcceptFocus`; on the Mac `native_setup` makes it a non-activating panel. So
  it floats over the game and never takes the keyboard. `WA_QuitOnClose` is off. This setup
  is written inline in `HistoryWindow.__init__`, not in a helper.
- **Tab indexes are hard-coded in more places:** `box.select(0)` (the pinned EXP line's
  click), `box.select(1)` (Class's go, and `quest_go` when no trip starts),
  `set_tab_dot(1, …)` / `set_tab_dot(2, …)` in `update_tools`, `QuestFocus(box, 3)`, and
  `box.add_footer(tool.pin_line, 0)`.
- **The pinned EXP line** (#87): a footer under every tab but EXP, on while `pin_exp`.
  `Box.set_footer_shown` turns it on and off.
- **The box's width** is the player's since #34: dragging its corner sets `tab_width`
  (`TAB_W` until then, up to `MAX_TAB_W = 480`), and each tool follows through `set_tab_w`.
  The pages' column has that fixed width, so the tab strip doesn't size the box.
- **Two tools start trips on Path:** Class's rows (`go`) and Quests' target rows
  (`quest_go(path_tool, …)`, plus `path_tool.heading`, `.stop` and `.hops`).
- **Reading is split from the tools** (#77): on the Mac a helper process reads the game.
  `readers.due` decides which optional windows to read each turn: `stats`, `skills` (Class)
  and `quest`, `tracker` (Quests); a closed one is searched for one tick in four.
  `update_tools` still takes one argument per tool.
- **The arrow is unchanged.** `_place_arrow` (`path_arrow/ui.py:435`) hides it whenever a
  frame has no position; `_why` ends with "a map that fits may still miss a frame: the arrow
  just hides" (line 433). `ARROW_SIZE = 36` is still one constant used in five places. The
  flicker still hasn't been measured. (#82 and ea3dc83 keep the *box* still on dark maps
  and loading screens; they don't touch the arrow.)
- **EXP, for the later parts:** #79 added a session average beside the last-5-min rate, a
  session that ends by itself after 30 minutes with no counted EXP (`SESSION_BREAK_S` in
  `meter.py`), and isn't saved. #47 already shows "Paused" when the live rate pauses for a
  break. The EXP tab's bottom row is now History and Pin.

## Parts and build order

One design, five parts that ship and test separately:

| Part | What it is | Depends on | State (2026-11-14) |
|---|---|---|---|
| `settings-window` | The window, the menu move, turning things off | none | Refreshed, ready |
| `arrow-options` | Arrow show, size and colour | `settings-window` | Refreshed, ready |
| `build-choice` | Build per job | `settings-window` | Needs a decision (#72) |
| `exp-sessions` | Manual mode: Start, Pause, Reset | `settings-window` | Re-decided on #79, ready |
| `best-sessions` | Sessions stored and ranked in History | `exp-sessions` | Re-decided on #79, ready |

Build in that order. Each part is its own PR, and none changes `version` in `pyproject.toml`.

## Goals

### `settings-window`

- **"Settings…"** is a new item in the box's menu, just before Hide. The tray icon's menu
  (the menu bar's on the Mac) is the same list, so it gets the item too. It opens one window;
  opening it again brings the same window forward.
- It's a **window like History** (Daniel), titled "MapleLens — Settings", with History's
  setup: over the game, never taking the keyboard, a non-activating panel on the Mac.
  Closing it doesn't quit the app. *(Refresh: History changed in #40 from a plain desktop
  window to this; "like History" now means this.)*
- **Mouse controls only:** checkboxes, buttons and sliders, never a text field, since the
  window never takes the keyboard *(my call)*.
- **One scrolling page of cards, in the box's dark look** (Daniel, 2026-11-14, after trying
  the first build): General first, then a card per tool in the tabs' order. **Each tool's
  card is headed by its own on/off switch** (a toggle, painted in the box's colours), with
  its settings indented under it; they grey out while it's off. A tool with nothing to set
  yet says "Nothing to set yet". General shows only when it has anything (the installed
  app's update check). Checkboxes are painted too (a yellow box with a check), and the whole
  row takes the click. The window sizes to its cards, and scrolls past 640 px.
- **Every change applies and saves at once.** There's no OK or Apply, matching today's
  toggles.
- **The menu shrinks to** Update to X.Y.Z… (when there is one), Pick game window…, Open
  Screen Recording settings… (Mac), Build: {name} (until `build-choice` settles it),
  Settings…, Hide, About, Quit.
- **Pin stays on the EXP tab only.** It's a button the player already uses there, and a
  second copy in Settings would be the same setting in two places *(my call)*.

**Each tool's switch** (its card's heading):

| Switch | Setting | Default |
|---|---|---|
| EXP | `exp_on` | on |
| Path | `path_on` | on |
| Class | `class_on` | on |
| Quests | `quests_on` | on |

**General:**

| Control | Setting | Default | Notes |
|---|---|---|---|
| Check for updates automatically | `update_check` (existing) | on | Only where an update check exists (the installed app, Windows and Mac) |
| Check for updates now | none | | A button, beside the toggle; its answer shows in the box's notice line, as today |

**Turning a tool off:**

- Its tab disappears and it stops working, live, with no restart. Its card stays, with its
  switch live and its settings greyed out.
- The tab's button, dot and page are **hidden, not removed**, so every hard-coded tab index
  (listed above) stays right. The box's width doesn't change: it's the pages' fixed width.
- **EXP off:** the meter closes and saves its open segment, as quitting does, and a fresh
  meter starts when it's on again. The session average (#79) starts over with it. The
  pinned EXP line hides while EXP is off, and comes back with it if `pin_exp` is on. *(When
  `exp-sessions` is re-decided, this follows whatever Reset becomes.)*
- **Path off:** a running trip stops and the arrow goes away.
- **Class off:** the marks go away.
- **Quests off:** its tab can't open, so the box never switches to it when a quest window
  opens in the game (`QuestFocus`). Tracked and followed quests stay saved for when it's on
  again.
- **An off tool's game windows aren't searched for:** the reader isn't asked for `stats` and
  `skills` while Class is off, or `quest` and `tracker` while Quests is off, so turning a
  tool off also saves the reading it cost *(my call; it's small: one filter on `due`'s
  result in `Tick.run`)*.
- If the open tab is turned off, the box shows the first tab still on.
- **The last tool that's on can't be turned off:** its switch is locked (it keeps its "on"
  look, with a tooltip saying why). A box with no
  tabs has nothing to show *(my call)*.
- **Rows that start a trip, with Path off:** "click to go" can't work, so the Class tab's
  rows (no `›`) and the Quests tab's target rows aren't clickable. They come back live when
  Path is on again.

### `arrow-options`

Path section:

| Control | Setting | Default |
|---|---|---|
| Show the arrow | `arrow_on` | on |
| Arrow size: slider, 24–72 px in steps of 4, with a live preview | `arrow_size` | 36 |
| Arrow colour: a row of six swatches (yellow, white, red, green, cyan, pink) | `arrow_color` | yellow, the box's accent |

- **Show the arrow** off keeps the route list running with no arrow. "Use taxi" stays on the
  Path tab. Size and colour grey out while it's off.
- **The preview** is the real arrow drawn in the Settings window at the chosen size and
  colour, because the arrow on the game only shows during a trip *(my call)*.
- **Colour swatches, not a colour picker** (Daniel, 2026-11-14): one click, mouse only, so the
  window never takes the keyboard; bright colours that read over the maps with the arrow's
  dark outline. The chosen one is ringed; each names its colour in a tooltip.
- The arrow's centre stays put as it grows. `ARROW_DY` doesn't change.
- **The arrow holds through missed frames, always, with no setting** (Daniel, 2026-11-14).
  It was first built as a "Keep the arrow steady" checkbox. Then the checkbox and the hold
  were both taken out, and without the hold the arrow hardly showed on Daniel's map. So the
  hold is built in: a frame that misses your position keeps the arrow where it was for up to
  `ARROW_HOLD_S = 2.0` s, on the same map and trip, whatever the miss's reason. The common
  miss is a frame where the reader doesn't find the "you" dot exactly once, which comes back
  as no minimap ("Open your minimap"). That line is held back too while the arrow is held;
  past 2 s the arrow hides and the line shows. A frame that *has* a position but no target
  (arrived, or nowhere to point), Stop, or a new map hides it at once.
- **No blink or pulse option** (Daniel).
- *(Refresh 2026-11-14: nothing upstream touched the arrow. Only line numbers moved.)*

### `build-choice`

> **Needs a decision before it's built (2026-11-14).** #72 added a build picker in the Class
> tab itself (a build row that opens the list of builds, and a question for a Beginner), and
> left the `Build: {name}` submenu in the menu too. So the build can already be changed in
> two places. What's left from this section: remove the submenu, and decide whether Settings
> still lists every job for choosing ahead, or whether the Class tab's picker is enough.

Class section:

- One row per job that has more than one build: the job's name and a dropdown of its builds.
  A job with one build isn't listed.
- It shows every job, including ones the character hasn't reached (Daniel), so a player can
  choose ahead.
- It reads and writes `class_builds` as today, and the Class tab follows at once.
- The AP/SP marks toggle moves here (`class_marks`).
- The `Build: {name}` submenu and `add_build_menu` go away *(my call: the crowded menu is the
  reason for this work)*. This undoes the overlay redesign's move of the build into the
  menu, on purpose.

### `exp-sessions`

> **Re-decided 2026-11-14 (Daniel), on top of #79.** #79's automatic session stays exactly as
> the owner chose it, and stays the default. This part adds a **manual mode** that a player
> opts into in Settings. The owner reviews that in the PR (see Open questions).

**A session** is #79's session: one stretch of EXP tracking, across maps, classes and levels,
with its average beside the last-5-min rate. What starts and ends it depends on the mode, set
in the EXP section:

| Setting | Values | Default |
|---|---|---|
| `exp_session_mode` | `auto`: "Track automatically (a session ends after 30 minutes without EXP)"; `manual`: "Track when I press Start" | `auto` |

- **The 30 minutes stay fixed** (`SESSION_BREAK_S`, Daniel, matching #79). No setting.
- **Auto mode changes nothing** but one word (below): no buttons, same tab, same split.

**The rules:**

| Event | `auto` (default) | `manual` |
|---|---|---|
| App starts | Tracking, as today | Not tracking |
| Start | (no button) | Tracking: a new session, or the paused one goes on |
| Pause | (no button) | Paused: nothing counts until Start |
| Reset | (no button) | The session ends and is saved; not tracking |
| 30 min with no counted EXP | The session ends and is saved; the next counted gain starts a new one (#79) | Nothing: it runs until Reset or quit (Daniel) |
| Quit | The session ends and is saved | Same |
| EXP turned off in Settings | The session ends and is saved | Same, and back to not tracking |
| Game closed or minimized | Keeps running; no EXP means no active time | Same |
| Hide | Keeps running: hiding isn't pausing | Same |

- **Reset saves, it never discards** *(my call: a misclick costs nothing)*. Deleting a session
  is out of scope.
- **Manual sessions left running** don't inflate the numbers: the 90 s idle cutoff and #47's
  break filter still leave idle time out of active time.
- **Not tracking records nothing:** no segments, so History's By map and the Class tab's
  "your best" don't grow until Start. That's the point of manual mode, and only players who
  chose it see it.
- **Pause, in the meter:** Pause closes the `ExpMeter` and saves its segments; Start makes a
  fresh one that carries the paused session's gains over. A fresh meter takes a new baseline
  from its first reading, so EXP earned while paused is never credited to the moment Start
  was pressed, and the live rate starts measuring again. The session's totals go on from
  where they were. *(My call. It keeps #79's session arithmetic untouched; `meter.py` gains
  only the carry-over and a switch for the 30-minute split, which manual turns off.)*
- **Switching mode:** a running session carries on. `auto` → `manual` while tracking: it runs
  until Reset, with no 30-minute split from then. `manual` → `auto`: tracking starts if it
  wasn't, a paused session goes on (auto has no buttons to unpause it), and the split applies
  from then.
- **The state machine is pure:** a small class in `exp_meter/session.py`, with no Qt, that
  takes start, pause, reset, gain, tick and mode events.

**What the tab says:**

- **"Idle" replaces "Paused"** as the left label when the live rate pauses for a break (#47),
  in every mode, and in the pinned line (Daniel). "Paused" then means only a manual Pause.
- **Manual, not tracking:** the left label is "Press Start", the session label is "Session",
  every value is `—`. The pinned line says "Press Start".
- **Manual, paused:** the left label is "Paused" and its values are `—`; the session column
  keeps its numbers so far (Daniel). The pinned line says "Paused".
- **Manual, tracking:** as auto. "Can't read bar" and "waiting for game" keep their priority.
- The rows stay the same in every state, so nothing jumps (the no-blink update in `_show`).

**Buttons, manual mode only** (Daniel: a second row, manual only). Above today's History and
Pin row, one row of two, all `Qt.NoFocus`:

| State | Left button | Reset |
|---|---|---|
| Not tracking | **Start** (primary) | disabled |
| Tracking | Pause (secondary) | enabled |
| Paused | **Start** (primary) | enabled |

```
Last 5 min      Session · 1h 20m
12,345 /h       10,870 /h
1.23% /h
Level up in
1h 5m
[ Pause  ] [ Reset ]     <- manual mode only
[History ] [ Pin   ]
```

The tab is one row taller in manual mode only; auto's height doesn't change. The row is a
layout, so it follows a dragged `tab_width`.

### `best-sessions`

- **Every finished session is saved** (Daniel), in both modes, so History can rank them.
- **A new table,** `exp_sessions(start REAL PRIMARY KEY, end REAL, exp INTEGER, active_s REAL,
  job TEXT, level_from INTEGER, level_to INTEGER, map_name TEXT)`, one row per session, with
  the session's own totals: the same numbers the tab's session column showed *(my call, a
  change from the first draft's boundaries-only table: #79 splits a session mid-segment
  after 30 minutes, so a segment can belong to two sessions, and totals rebuilt from
  segments wouldn't match what the player saw)*. `exp_segments` doesn't change.
- `start` is the session's first counted gain (auto) or the Start press (manual); `job` is
  the job at its end; `map_name` is its main map (most active time); `level_from`/`level_to`
  its levels. The meter keeps each session gain list with its segment, so it knows the maps.
- **Written as it goes:** a session's row is written at its first counted gain and updated on
  each 60 s flush, so a crash loses no more than segments do today. A session with no counted
  gain is never written.
- **Existing history shows up right away** (Daniel): when the table is first created, existing
  segments are grouped into sessions by 30-minute gaps (one segment's end to the next one's
  start, matching `SESSION_BREAK_S`), their totals summed, and written once. Approximate, as
  old data has no finer grain.
- **The History window gets two tabs:** "By map" (today's table and best-maps strip) and
  "Best sessions".
- **Best sessions columns:** Date (the session's `end`), Class, Lvl (`28–30` when it changed),
  Main map, Avg EXP/h, Active time. No %/h, as #79 left it out for sessions (a percent per
  hour doesn't add up across levels). Sortable, opening sorted by Avg EXP/h, highest first.
- **Sessions under 5 active minutes aren't listed** *(my call: a one-minute burst shouldn't top
  the list)*. Their segments still count in By map and in the Class tab's "your best".
- With no sessions to list, the tab says so in one line.

## Non-goals

- Blink or pulse settings for the arrow (Daniel).
- Guides from other authors, or a new guide format: only builds already in `classes.json`
  (Daniel).
- Reset to defaults, import or export of settings, colour themes.
- Exposing `idle_cutoff_s` or `jump_factor`.
- A setting for the 30-minute split (Daniel, matching #79).
- Session buttons in `auto` mode (Daniel, keeping the owner's "no Reset button" there).
- Deleting or renaming sessions.
- A global hotkey for Start or Pause: it would need a global keyboard hook.
- Telling characters apart. MapleLens doesn't read names, so a list covers every character on
  the machine; the Class column tells them apart by job.
- Remembering a running session across restarts.

## Anti-goals (a failure even if it works)

- Anything that breaks the screen-only rule.
- The box or the Settings window takes keyboard focus from the game.
- The box's width changes for any reason but the player's drag (`tab_width`), or the EXP tab
  gets taller in `auto` mode.
- `auto` mode behaves differently from #79 in anything but the "Idle" label.
- A saved session's numbers differ from what the tab's session column showed for it.
- An off tool keeps drawing anything over the game (arrow, marks) or switching the box's tab.
- EXP earned while paused or not tracking gets counted.
- Reset or Pause loses an already-counted session.
- The same setting can be changed in two places that drift apart.
- A tool imports another tool.

## Constraints

- **No new dependency.** Everything is PySide6 and `sqlite3`.
- **Tools stay apart** (`AGENTS.md`): each tool builds its own Settings section
  (`settings_section() -> QWidget`), using only `overlay.py` helpers. The window and the
  General section live in the app layer and just stack those sections. No tool knows about
  another.
- **Bad values never break startup:** a hand-edited or corrupt `arrow_size` or
  `exp_session_mode` is clamped or falls back to its default.
- **New windows match History's setup** (`Qt.Tool`, `WA_ShowWithoutActivating`,
  `WA_QuitOnClose` off, on top and no focus on Windows, `native_setup` on show) through one
  shared helper in `overlay.py` rather than a second copy of `HistoryWindow.__init__`'s lines.
- **Tools still don't learn about each other.** The app tells Class and Quests whether trips
  can start (`set_can_go`), and leaves an off tool's windows out of what the reader is asked
  for; no tool reads another's setting.
- **No banned names** in code or comments under `src/` or `scripts/`.

## Commands

```
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run python scripts/check_screen_only.py
uv run maplelens
```

## Project structure

- `src/maplelens/store.py`: the new `DEFAULTS` and their validation.
- `src/maplelens/settings_window.py` (new): the window and its General section.
- `src/maplelens/overlay.py`: hiding and showing a tab; the shared window setup.
- `src/maplelens/app.py`: Settings… in the menu; the old items removed; turning tools off;
  skipping turned-off tools in `update_tools`; the footer and `QuestFocus` following EXP and
  Quests; an off tool's windows left out of what the reader is asked for.
- `src/maplelens/tools/quest_helper/ui.py`: `set_can_go`.
- `src/maplelens/tools/exp_meter/session.py` (new): the session state machine.
- `src/maplelens/tools/exp_meter/meter.py`: carrying a session's gains into a fresh meter, the
  switch for the 30-minute split, and each session gain list kept with its segment.
- `src/maplelens/tools/exp_meter/history.py`: `exp_sessions`, the one-time grouping, the ranked
  query.
- `src/maplelens/tools/exp_meter/ui.py`, `text.py`: the buttons, tab text, History's two tabs,
  the EXP section.
- `src/maplelens/tools/path_arrow/ui.py`: arrow size and holding, the Path section.
- `src/maplelens/tools/class_helper/ui.py`: the Class section; `set_can_go`.
- `tests/test_session.py` (new), `tests/test_settings_window.py` (new), and additions to
  `test_store.py`, `test_history.py`, `test_ui.py`, `test_path_ui.py`, `test_class_ui.py`,
  `test_quest_ui.py`, `test_overlay.py`, `test_app.py`. `test_docs.py`
  checks `AGENTS.md`'s Layout, so a new module goes there in the same commit.
- `README.md`: Start, Pause and Reset; where the settings are. `AGENTS.md`: Layout.

## Code style

As the code does today: small pure parts, Qt only at the edge, values read from `settings`
with a named default.

```python
def _arrow_size(value: object) -> object:
    """An arrow size, clamped into ARROW_SIZES and rounded to its step; None if not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    lo, hi, step = ARROW_SIZES.start, ARROW_SIZES[-1], ARROW_SIZES.step
    return lo + int((min(max(value, lo), hi) - lo) / step + 0.5) * step  # halves round up
```

## Testing

- **Pure, no Qt:**
  - `test_session.py`: every row of the rules table, in both modes, plus the mode switches.
  - `test_meter.py`: a meter carrying a paused session's gains gives the same session totals
    as one that never paused; with the split off, a gap over 30 minutes keeps the session;
    with it on (the default), #79's tests pass unchanged.
  - `test_history.py`: an old database gains `exp_sessions` once, grouped by 30-minute gaps,
    and a second open adds nothing. Ranking, the 5-minute floor, a level range, main map. A
    saved row's EXP/h equals the live `session()` value it was written from.
  - `test_store.py`: out-of-range and wrong-type values fall back or clamp; a settings file
    without the new keys loads.
  - `arrow_size` clamps and rounds; `arrow_color` must be one offered.
- **Offscreen Qt:**
  - The EXP tab in `auto`: no new buttons, the same height as before, "Idle" for a break.
  - The EXP tab in `manual`, in each state: buttons, labels, the session column kept while
    paused; one row taller than `auto`.
  - Gains during a pause add nothing to a segment or the session, and the first reading after
    Start sets a new baseline.
  - Reset in `manual` saves the session and goes to not tracking.
  - The arrow at 24, 36 and 72 px stays centred on the same point; a swatch recolours the
    arrow and the preview live.
  - Turning off each of the four tools hides its tab, stops its `update`, and keeps
    `set_tab_dot`, `select` and `QuestFocus` indexes right. The last tool's switch is
    locked. EXP off hides the pinned line; Quests off stops the switch to Quests; Path off
    makes Class and Quests rows unclickable. The box's width is the same before and after.
  - With Class or Quests off, the reader is never asked for their windows.
  - The menu no longer has the moved items, and has Settings… before Hide.
  - Opening Settings twice gives one window. Closing it leaves the app running.
  - A build picked in Settings shows in the Class tab, and is saved.
- **Before calling it done:** draw the EXP tab in `auto` and in the three `manual` states, and
  the Settings window, offscreen with `QWidget.grab()`, and look at the images.
- **By hand on Windows:**
  1. Switch to `manual`: the tab says Press Start, and hunting adds nothing.
  2. Start, hunt, Pause, hunt more, Start: the EXP from the pause isn't in History.
  3. With the game focused, press Start, Pause and Reset: the game keeps the keyboard.
  4. On a route: change the size and watch the arrow follow.
  5. On a route: pick each colour and see the arrow change.
- **By hand on a Mac:** Settings opens as a panel, the game stays active, and closing it
  doesn't quit.

## Boundaries

- **Always:** run the four checks before each commit. One PR per part. Save a setting the
  moment it changes.
- **Ask first:** any new dependency; any setting beyond this spec; any change to
  `exp_segments` or to `meter.py`'s arithmetic (the carry-over and the split switch aren't
  arithmetic changes; #79's tests passing unchanged shows it).
- **Never:** change `version` in a feature PR; read or send anything to the game; a hotkey;
  discard a session on Reset.

## Success criteria

1. Settings… in the box's menu and the tray's opens one window, and every change in it
   applies at once and survives a restart.
2. The menu has at most eight items (seven once `build-choice` removes Build), with the moved
   items gone from it.
3. Each tool can be turned off and on live. The last one can't be turned off, and nothing
   errors in `maplelens.log` when any are off.
4. The arrow's size changes live from 24 to 72 px, staying centred, and its colour from the
   swatches.
5. `auto` (the default) works as #79 does, with "Idle" for a break. In `manual`, nothing is
   recorded until Start, and a session runs until Reset or quit.
6. EXP earned while paused is never counted.
7. Reset, Quit and #79's 30-minute split save the session. An existing database shows its
   past sessions in Best sessions on first open.
8. The box's width (the player's `tab_width`) and the EXP tab's height in `auto` are
   unchanged.
9. A build chosen for a job in Settings applies, including for a job not yet reached.
10. `uv run pytest`, `ruff check`, `ruff format --check` and the guard pass on Windows and
    macOS CI.

## Open questions

- **For the owner, in the EXP PRs (Daniel chose to settle these there, 2026-11-14):**
  1. A manual mode at all. #50 chose an automatic split over a Reset button; this keeps that
     for everyone by default and adds Start/Pause/Reset only for players who opt in.
  2. "Idle" in place of "Paused" for a break, everywhere, so "Paused" can mean a manual Pause.
  3. Saving sessions and a Best sessions tab, which #79 left out of its scope.
- *(Settled 2026-11-14: `manual` as the default for everyone. Daniel chose `auto` as the
  default and `manual` as an opt-in.)*
