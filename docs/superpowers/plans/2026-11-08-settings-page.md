# Settings Page and EXP Sessions Implementation Plan

Spec: `docs/superpowers/specs/2026-11-08-settings-page-design.md`. Base (refreshed
2026-11-14): or-keren/maplelens `main` at 7be7403 (v0.6.3), the `origin` remote here; the
local `main` was fast-forwarded to it. The fork's `main` (`fork` remote) is behind, so don't
branch from it. One commit per task, one PR per phase, from the fork (`dbeilin/maplelens`)
to `or-keren/maplelens`. No PR changes `version`.

**Refresh, 2026-11-14:** Phases 1 and 2 are rechecked against v0.6.3. Phase 3 waits for the
`build-choice` decision. Phases 4 and 5 are rewritten on top of #79's session average: `auto`
(#79) stays the default, and manual Start/Pause/Reset is an opt-in.

The spec and this plan go in as the first commit of Phase 1.

## Overview

A Settings window takes the set-once items out of the ••• menu and adds what has no home
today: turning tools off, the arrow's size and steadiness, a build per job, and how EXP
sessions work. Players who choose manual tracking get Start, Pause and Reset on the EXP tab,
and History gets a best sessions list.

## Architecture decisions

- **Each tool builds its own section.** `settings_section() -> QWidget` on each tool, using
  only `overlay.py` helpers. `settings_window.py` stacks them and owns General, so no tool
  learns about another (`AGENTS.md`).
- **A turned-off tool is swapped for a null tool at the call.** `Tick.run` passes `OFF` (an
  object whose `update` does nothing, with `running`, `dot` and `open` false) in its place.
  `update_tools` keeps its signature, so its existing tests and fakes don't change, and
  `QuestFocus` sees `open` false while Quests is off without knowing why.
- **Tabs are hidden, never removed.** `Box.set_tab_shown(i, on)` hides the button, dot and
  page. Every hard-coded index (`select(0|1)`, `set_tab_dot(1|2, …)`, `QuestFocus(box, 3)`,
  the footer's tab 0) stays right.
- **The reader skips an off tool's windows.** `Tick.run` filters `due(...)`'s result by the
  on tools before `reader.ask`; `due` itself stays as it is. On the Mac that's the request
  sent to the helper process, so nothing new crosses the process line.
- **The session is a pure state machine** (`exp_meter/session.py`), like `meter.py`.
  `ExpMeterTool` holds `_meter: ExpMeter | None` and makes a fresh one on each Start,
  carrying the paused session's gains over, which is how a pause avoids crediting EXP earned
  during it while the session's totals go on.
- **#79's session stays in `meter.py`.** It gains a `carry` start and a `split` switch (off
  in `manual`); `_totals` and the gain counting don't change, and its tests pass unchanged.
- **`exp_sessions` stores each session's own totals,** written from the live `session()`, so
  a saved row always matches the tab. See the spec's `best-sessions` section for why.

## Dependency graph

```
T1 keys + validation ─ T2 empty window ─┬─ T3 move update + marks items
                                        └─ T4 hide a tab ─ T5 turn tools off ─ T6 go rows
                                                              │
        ┌─────────────────────────────┬───────────────────────┘
        │                             │                       │
 T7 arrow size + show          T9 build per job      T10 state machine   T11 meter carry/split
        │                                                     │                   │
 T8 colour                                                    └─ T12 manual mode ─┘
                                                                   + EXP section
                                                              │
                                                      T13 store sessions
                                                              │
                                                      T14 Best sessions tab
                                                              │
                                                      T15 README + full check
```

Phases 2, 3 and 4 are independent once Phase 1 is merged, and touch different tool files, so
they could run in parallel. Daniel works alone, so they run in order.

## Phase 1: the settings window (PR 1)

### Task T1: new settings and their validation

**Description:** Add `exp_on`, `path_on`, `class_on` and `quests_on` to `DEFAULTS`, flat.
Add a `clean` step in `load_settings` that resets a value of the wrong type or range to its
default; it covers only keys it's told about, so the existing keys (`boxes`, `tab_width`,
`quests_*`) load as today. Later tasks add their keys to it.

**Acceptance criteria:**
- [ ] A settings file without the new keys loads with their defaults.
- [ ] A string or number in place of a boolean falls back to the default.

**Verification:** `uv run pytest tests/test_store.py`

**Dependencies:** None. **Files:** `store.py`, `tests/test_store.py`. **Scope:** XS

### Task T2: an empty Settings window opens from the menu

**Description:** Extract History's window setup (`HistoryWindow.__init__` lines 83–90:
`WA_QuitOnClose` off, `Qt.Tool`, `WA_ShowWithoutActivating`, on top and no focus off the
Mac; and `native_setup` in `showEvent`) into one helper in `overlay.py`, and use it for both
windows. Add `settings_window.py` with a scrolling page and headed sections (General, then
one per tool that has a `settings_section()`), and "Settings…" in the menu, before Hide
(`add_menu_item(..., at=-1)` placed before `add_hide` runs). Add the new module to
`AGENTS.md`'s Layout (`test_docs.py` checks it).

**Acceptance criteria:**
- [ ] "Settings…" shows in the box's menu (and so the tray's), just before Hide.
- [ ] Opening twice gives one window, brought forward. Closing it leaves the app running.
- [ ] History's existing window tests still pass unchanged.
- [ ] A click on a checkbox in the window works with the window never taking focus
      (offscreen: `QTest.mouseClick`; by hand at Checkpoint A).

**Verification:** `uv run pytest tests/test_settings_window.py tests/test_ui.py`; draw the
window with `QWidget.grab()` and look at it.

**Dependencies:** T1. **Files:** `settings_window.py` (new), `overlay.py`, `exp_meter/ui.py`,
`app.py`, `AGENTS.md`, `tests/test_settings_window.py` (new). **Scope:** M

### Task T3: move the update and marks items into Settings

**Description:** General gets "Check for updates automatically" and a "Check for updates now"
button, only when an `UpdateCheck` exists (the installed app, Windows and Mac). The Class
section gets the AP/SP marks toggle. Both call the existing `check.set_auto`,
`check.check_now` and `cls.set_marks`. Remove the two `box.add_*` calls at the end of
`update_check` and the `MARKS` toggle in `main`. The Build submenu stays until Phase 3.

**Acceptance criteria:**
- [ ] Those menu items are gone from every menu; "Update to X.Y.Z…" stays at the top.
- [ ] Toggling in Settings saves, and survives a restart.
- [ ] With no `UpdateCheck` (from source), the update controls don't show.

**Verification:** `uv run pytest tests/test_app.py tests/test_class_ui.py`. Expect churn in
`test_app.py` wherever it indexes `actions()` by position (search for `actions()[`); look
items up by text where touched.

**Dependencies:** T2. **Files:** `settings_window.py`, `app.py`, `class_helper/ui.py`,
`tests/test_app.py`, `tests/test_class_ui.py`. **Scope:** M

### Task T4: the box can hide a tab

**Description:** `Box.set_tab_shown(index, on)`. Hides the button, dot and page. If the open
tab is hidden, select the first one still shown. `select` and `set_tab_dot` leave a hidden
tab hidden (a dot set on a hidden tab shows only once the tab does). Hiding the footer's own
tab hides the footer too.

**Acceptance criteria:**
- [ ] A hidden tab's button is gone, and indexes of the others still work.
- [ ] Hiding the open tab moves to the first shown one, and the box's width doesn't change,
      at `TAB_W` and at a dragged `tab_width`.
- [ ] `select(i)` on a hidden tab does nothing.

**Verification:** `uv run pytest tests/test_overlay.py`

**Dependencies:** None. **Files:** `overlay.py`, `tests/test_overlay.py`. **Scope:** S

### Task T5: turning tools off

**Description:** A switch heading each tool's card (built that way after Daniel tried the first
build; first done as four checkboxes in General). `OFF` in `Tick.run`, both calls of
`update_tools`. Each tool gets a small `stop(now)`: EXP closes and saves (as `shutdown`
does) and makes a fresh meter, and the app hides the pinned line (`set_footer_shown(False)`,
back to `pinned` when on); Path ends the trip (`stop()`) and hides the arrow; Class hides its
marks; Quests needs nothing beyond `OFF` (its `open` is false, so `QuestFocus` stays put).
`Tick.run` drops an off tool's windows from `due(...)` before `reader.ask`. The last tool
that's on has its switch locked. Off tools' settings are greyed out.

**Acceptance criteria:**
- [ ] Each of the four tools turns off and on live, and its `update` isn't called while off.
- [ ] Turning off EXP saves the open segment and hides the pinned line; turning it on brings
      the line back if `pin_exp` is on. The last tool on can't be turned off.
- [ ] With Quests off, an open quest window doesn't switch the box to Quests.
- [ ] With Class or Quests off, the reader isn't asked for their windows.
- [ ] A tick with any tools off writes nothing to the log, and indexes for dots stay right.

**Verification:** `uv run pytest tests/test_settings_window.py tests/test_app.py`; by hand,
turn each off during a route.

**Dependencies:** T1, T2, T4. **Files:** `settings_window.py`, `app.py`, `exp_meter/ui.py`,
`path_arrow/ui.py`, `class_helper/ui.py`. **Scope:** M

### Task T6: go rows when Path is off

**Description:** `set_can_go(bool)` on `ClassHelperTool` and `QuestHelperTool`. With Path
off, Class rows aren't clickable and have no `›`, and Quests' target rows aren't clickable.
The app calls both when Path turns on or off, and once at start.

**Acceptance criteria:**
- [ ] With Path off, no Class row or Quests target row is clickable; turning Path on restores
      them live.

**Verification:** `uv run pytest tests/test_class_ui.py tests/test_quest_ui.py`

**Dependencies:** T5. **Files:** `class_helper/ui.py`, `quest_helper/ui.py`, `app.py`,
`tests/test_class_ui.py`, `tests/test_quest_ui.py`. **Scope:** S

### Checkpoint A (before PR 1)

- [ ] `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`,
      `uv run python scripts/check_screen_only.py` all pass.
- [ ] By hand on Windows: the menu is short, everything in Settings applies at once, and the
      game keeps the keyboard even while clicking in Settings.
- [ ] By hand on a Mac: the checkboxes and the button work in the non-activating panel, and
      Settings is in the menu bar icon's menu.
- [ ] By hand: turn Quests off, open a quest window in the game: the box stays on its tab.
- [ ] Rebase on the then-current `origin/main` (see Risks).

## Phase 2: arrow options (PR 2)

### Task T7: arrow size and show

**Description:** `arrow_size` (24–72, step 4, default 36) and `arrow_on`, validated. `_Arrow`
takes its size as an attribute in place of `ARROW_SIZE` (today at `path_arrow/ui.py` lines
63, 70, 72 and 446; the constant stays as the default). The Path section has the checkbox,
a slider and a real `_Arrow` as the preview.

**Acceptance criteria:**
- [ ] The arrow changes size live and stays centred on the same point at 24, 36 and 72.
- [ ] `arrow_on` off keeps the route list and hides only the arrow.

**Verification:** `uv run pytest tests/test_path_ui.py tests/test_store.py`

**Dependencies:** T2. **Files:** `path_arrow/ui.py`, `store.py`, `tests/test_path_ui.py`,
`tests/test_store.py`. **Scope:** S

### Task T8: arrow colour (was: keep the arrow steady)

**Description:** Built first as `arrow_steady`, a checkbox for a 2 s hold through missed
frames. The checkbox is gone; the hold stays, always on (without it the arrow hardly showed
on Daniel's map). In the checkbox's place: `arrow_color`, one of six `ARROW_COLORS` swatches in the Path card, validated
in `clean`. `_Arrow` paints in its `color`; the preview follows.

**Acceptance criteria:**
- [x] A swatch recolours the arrow and the preview live, and is saved.
- [x] A saved colour that isn't offered loads as yellow.

**Verification:** `uv run pytest tests/test_path_ui.py tests/test_store.py`

**Dependencies:** T7. **Files:** `path_arrow/ui.py`, `store.py`, `tests/test_path_ui.py`,
`tests/test_store.py`. **Scope:** S

### Checkpoint B (before PR 2)

- [ ] The four checks pass.
- [ ] By hand: on a route, change the size and the colour and watch the arrow follow.

## Phase 3: build choice (PR 3)

### Task T9: a build per job in Settings

**Description:** The Class section lists every entry of `ClassData.jobs` with more than one
build, with a dropdown, reading and writing `class_builds` under `plan.job`. Remove
`add_build_menu`, `builds_changed` and `_tell_builds`, along with their tests
(`test_app.py` from line 1409, `test_class_ui.py:180`).

**Acceptance criteria:**
- [ ] A job with one build isn't listed; jobs not yet reached are.
- [ ] Choosing a build updates the Class tab at once, and is saved.
- [ ] The Build submenu is gone.

**Verification:** `uv run pytest tests/test_class_ui.py tests/test_app.py`

**Dependencies:** T3. **Files:** `class_helper/ui.py`, `app.py`, `tests/test_class_ui.py`,
`tests/test_app.py`. **Scope:** M

## Phase 4: EXP sessions, manual mode (PR 4)

Rewritten 2026-11-14 on top of #79. `auto` is the default and behaves as #79 does today.

### Task T10: the session state machine

**Description:** `exp_meter/session.py`, pure. States: not tracking, tracking, paused. Events:
start, pause, reset, gain, tick, set mode. In `auto` it starts tracking and never pauses; the
30-minute split stays in the meter. Add `session.py` to `AGENTS.md`.

**Acceptance criteria:**
- [ ] Every row of the spec's rules table, in both modes, plus the mode switches (`manual` →
      `auto` while paused goes on tracking).

**Verification:** `uv run pytest tests/test_session.py`

**Dependencies:** None. **Files:** `exp_meter/session.py` (new), `AGENTS.md`,
`tests/test_session.py` (new). **Scope:** S

### Task T11: the meter carries a session, and can skip the split

**Description:** In `meter.py`: `ExpMeter(..., carry=...)` starts with a held session's gain
lists, and `ExpMeter(..., split=False)` skips the `SESSION_BREAK_S` check in `feed`. Each
session gain list is kept with its segment (map, job, level), for T13. No change to
`_totals` or to how a gain is counted.

**Acceptance criteria:**
- [ ] A session paused (meter closed) and carried into a fresh meter gives the same
      `session()` as one fed straight through, minus the gains fed while paused.
- [ ] With `split=False`, a gap over 30 minutes keeps the session.
- [ ] Every existing `test_meter.py` test passes unchanged.

**Verification:** `uv run pytest tests/test_meter.py`

**Dependencies:** None. **Files:** `exp_meter/meter.py`, `tests/test_meter.py`. **Scope:** S

### Task T12: manual mode on the EXP tab, and the EXP section

**Description:** `exp_session_mode` (default `auto`, validated in `clean`). `ExpMeterTool`
follows `session.py`: `_meter` is `None` while not tracking or paused; Pause closes and saves
the meter and holds its session; Start makes a fresh meter with `carry=` the held session and
`split=` off in `manual`. In `manual` only, a row of Start/Pause and Reset sits above History
and Pin. `box_lines` and `pin_text` gain "Press Start" and "Paused"; the idle label becomes
"Idle" everywhere. The EXP section has the two mode radios. Existing tests don't change for
`auto`; any that check the "Paused" text change to "Idle".

**Acceptance criteria:**
- [ ] In `auto`, the tab looks and works as before, but for "Idle"; same height.
- [ ] In `manual`, nothing is recorded before Start; EXP gained during a pause isn't counted;
      the first reading after Start is a new baseline; the session column keeps its numbers
      while paused.
- [ ] Reset saves and goes to not tracking. Every button is `Qt.NoFocus`.
- [ ] Switching mode behaves as the spec says.

**Verification:** `uv run pytest tests/test_ui.py tests/test_text.py tests/test_session.py`;
draw the tab in `auto` and in the three `manual` states with `QWidget.grab()` and look at them.

**Dependencies:** T2, T10, T11. **Files:** `exp_meter/ui.py`, `exp_meter/text.py`, `store.py`,
`tests/test_ui.py`, `tests/test_text.py`. **Scope:** M

### Checkpoint D (before PR 4)

- [ ] The four checks pass.
- [ ] By hand on Windows, in the game: in `auto`, nothing changed but "Idle". In `manual`:
      Start, hunt, Pause, hunt, Start: the paused EXP isn't in History or the session.
      Pressing the buttons leaves the game the keyboard.
- [ ] The PR description asks the owner the spec's three open questions.

## Phase 5: best sessions (PR 5)

### Task T13: store sessions

**Description:** The `exp_sessions` table (start, end, exp, active_s, job, level_from,
level_to, map_name), created with a one-time grouping of existing segments by 30-minute gaps.
`ExpMeterTool` writes a session's row at its first counted gain and updates it on each 60 s
flush, on Reset, on #79's split, on EXP off and on quit, from the meter's live `session()`
totals. `best_sessions(conn)` returns ranked rows, with the 5-minute floor.

**Acceptance criteria:**
- [ ] An old database gets its sessions once, and a second open adds nothing.
- [ ] A saved row's EXP/h equals the `session()` value it was written from, including across
      a pause and a 30-minute split mid-segment.
- [ ] Level range and main map are right across a level-up and a map change.

**Verification:** `uv run pytest tests/test_history.py tests/test_ui.py`

**Dependencies:** T12. **Files:** `exp_meter/history.py`, `exp_meter/ui.py`,
`tests/test_history.py`, `tests/test_ui.py`. **Scope:** M

### Task T14: the Best sessions tab

**Description:** History becomes two tabs: "By map" (today's best-maps strip and table) and
"Best sessions" (Date, Class, Lvl, Main map, Avg EXP/h, Active time), which share one table
class. Sorted by Avg EXP/h.

**Acceptance criteria:**
- [ ] Both tabs fill on open, and sort by value. An empty list says so in one line.
- [ ] The window's quit and Mac tests still pass.

**Verification:** `uv run pytest tests/test_ui.py`; draw the window and look at it.

**Dependencies:** T13. **Files:** `exp_meter/ui.py`, `exp_meter/text.py`, `tests/test_ui.py`.
**Scope:** S

### Task T15: README and the full check

**Description:** README: manual mode's Start, Pause and Reset, Best sessions, and where the
settings are. Run the spec's whole by-hand list.

**Acceptance criteria:**
- [ ] Every success criterion in the spec is met or listed as failed.

**Verification:** the four checks, then
`uv run --group build python scripts/build_installer.py` and a run of the installed app.

**Dependencies:** T14. **Files:** `README.md`. **Scope:** S

### Checkpoint E (before PR 5)

- [ ] All of the above, on Windows and macOS CI.
- [ ] Daniel has seen the Settings window, the EXP tab in `auto` and the three `manual`
      states, and Best sessions.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Upstream moves fast (47 merges in six days) and keeps touching `app.py`'s menu and tick | Med | Branch from the newest `origin/main` when Phase 1 starts, and rebase at Checkpoint A. (#34 and #32, the earlier blockers, merged on 2026-11-09) |
| Clicks don't register in a window that never takes focus (Windows `WindowDoesNotAcceptFocus`) | Low | T2's offscreen click test, then by hand at Checkpoint A. Fall back to letting Settings take focus while open, as `Box.allow_typing` does for the Path search |
| The owner says no to manual mode, "Idle" or saved sessions in review | Med | Daniel chose to settle it in the PRs. Each is separable: manual mode is T10–T12, "Idle" is a few strings in T12, saving is Phase 5. Ask early in PR 4's description |
| #79's session code moves upstream before Phase 4 | Med | T11 is small and touches only the session bits of `meter.py`; rebase before starting it |
| Checkboxes and the slider misbehave in the Mac's non-activating panel | Med | Checkpoint A checks by hand. History never needed input, so this is untested ground. Fall back to a normal activating window for Settings |
| The manual row's two buttons don't fit a narrow tab | Low | Two buttons in `TAB_W` (214 px) is roomy; T12's drawn images check it |
| Moving menu items breaks many position-based tests in `test_app.py` | Low | Expected in T3. Look items up by text where touched |

## Open questions

- From the spec, for the owner in PR 4/5: manual mode at all, "Idle" for a break, and saving
  sessions.
- `build-choice` (Phase 3): drop the Build submenu only, or also list every job in Settings?

## Status

Phase 1 (T1–T6) built on `feat/settings-window`, 2026-11-14: the four checks pass and the
window was drawn offscreen; Checkpoint A's by-hand checks on Windows and the Mac are still to
do. Phase 2 (T7–T8) built on `feat/arrow-options`, stacked on it,
2026-11-14: show, size and colour; the 2 s hold through missed frames is built in, with no setting. Phases 1 and 2 were
refreshed against v0.6.3 on 2026-11-14, and Phases 4 and 5 rewritten on top of #79 the same
day. Phase 3 waits for the `build-choice` decision.
