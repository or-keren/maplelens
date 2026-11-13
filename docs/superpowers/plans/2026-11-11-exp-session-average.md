# EXP session average Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the session's active EXP/h beside the last-5-min rate in the EXP tab, as a second column.

**Architecture:** `ExpMeter` keeps one more list, the session's gains: the same tuples it appends to
`Segment.gains`, across segments, cleared when a counted gain comes more than 30 minutes after the
previous one. `session()` sums them with the existing `_totals`. `box_lines` returns rows of columns
instead of a flat list; `ExpMeterTool._show` lays a multi-column row out side by side.

**Tech Stack:** Python 3, PySide6, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-11-exp-session-average-design.md`

## Global Constraints

- Screen-only (AGENTS.md): no new reads of anything; arithmetic over readings the meter already takes. `uv run python scripts/check_screen_only.py` passes.
- No new dependency. Don't change `version` in `pyproject.toml`.
- Session split: `SESSION_BREAK_S = 1800` in `meter.py`, no setting; strictly *more than* 1800 s between counted gains splits.
- Session shows EXP/h only, never %/h; the line under it is blank (`""`).
- Box width unchanged (`TAB_W`); the two columns split the tab's current width equally (the player can drag it to `MAX_TAB_W`).
- "Level up in" stays on the last-5-min rate. Nothing about the session is saved.
- `uv run pytest`, `uv run ruff check`, `uv run ruff format` clean before each commit.

## Review Focus

- Game closed or minimized for under 30 minutes, then back: the session carries on. → `test_session_kept_while_game_gone` (Task 1)
- Map, class or level unreadable mid-session: those gains don't count, and the session isn't split. → `test_session_skips_paused_gains` (Task 1)
- A quest reward handed in at a town mid-session: not counted. → `test_session_skips_town_quest_rewards` (Task 1)
- The break exactly 30 minutes vs. just over: kept vs. split. → `test_session_split_boundary` (Task 1)
- "Session · 12h 10m" and seven-digit values at 214 px (Windows) and 220 px (Mac): fit without widening the box. → render check, Task 2 Step 7

---

### Task 1: Session totals in the meter

**Files:**
- Modify: `src/maplelens/tools/exp_meter/meter.py` (new constant, dataclass, list in `__init__`, hook in `_on_exp` where `seg.gains.append` is, `session()` beside `rate()`)
- Test: `tests/test_meter.py`

**Interfaces:**
- Produces: `SESSION_BREAK_S = 1800`; `@dataclass class SessionRate: exp_per_min: float | None; active_s: float` (`exp_per_min` is None under 60 s of active time); `ExpMeter.session(self) -> SessionRate | None` (None before the session's first counted gain).

- [ ] **Step 1: Write the failing tests** at the end of `tests/test_meter.py` (after `TOWN` is defined; use the file's `feed`, `steady`, `TOWN` helpers):

```python
def test_session_none_before_first_counted_gain():
    m = ExpMeter()
    feed(m, 0, 1000, 10.0)  # the first reading is only the baseline
    assert m.session() is None
    feed(m, 20, 1100, 10.5)  # timed from the segment's open at 0.5
    s = m.session()
    assert s.active_s == pytest.approx(20)
    assert s.exp_per_min is None  # under a minute


def test_session_matches_open_segment():
    m = ExpMeter()
    steady(m, 13)
    s, seg = m.session(), m.open_segment()
    assert s.active_s == pytest.approx(seg.active_s)
    assert s.exp_per_min == pytest.approx(seg.exp / seg.active_s * 60)


def test_session_spans_level_up_and_map_change():
    m = ExpMeter()
    for i, pct in enumerate([94, 95, 96, 97, 98]):
        feed(m, i * 30, pct * 1000, pct)
    feed(m, 150, 1000, 1.0, level=23)  # level-up: closes the level-22 segment
    feed(m, 180, 2000, 2.0, level=23)
    feed(m, 210, 3000, 3.0, level=23, map_name="Other Map")  # map change
    feed(m, 240, 4000, 4.0, level=23, map_name="Other Map")
    segs = [*m.pop_closed(), m.open_segment()]
    assert len(segs) >= 3
    assert m.session().active_s == pytest.approx(sum(s.active_s for s in segs))
    assert m.session().exp_per_min * m.session().active_s / 60 == pytest.approx(
        sum(s.exp for s in segs)
    )


@pytest.mark.parametrize("brk, active", [(1800, 120 + 30), (1801, 30)])
def test_session_split_boundary(brk, active):
    m = ExpMeter()
    steady(m, 5)  # counted gains at 30..120: 120 s
    last = 4 * 30
    feed(m, last + brk - 30, 5000, 50.0)  # after the break: starts the clock only
    feed(m, last + brk, 5100, 50.5)  # counted, `brk` s after the last counted gain
    assert m.session().active_s == pytest.approx(active)


def test_session_kept_while_game_gone():
    m = ExpMeter()
    steady(m, 5)
    for t in range(130, 730, 3):  # 10 minutes with the game closed
        m.feed(None)
    feed(m, 730, 5000, 50.0)
    feed(m, 760, 5100, 50.5)
    assert m.session().active_s == pytest.approx(120 + 30)


def test_session_skips_paused_gains():
    m = ExpMeter()
    steady(m, 5)
    feed(m, 150, 1250, 12.5, map_name=None)  # map unreadable: not counted
    assert m.session().active_s == pytest.approx(120)


def test_session_skips_town_quest_rewards():
    m = ExpMeter()
    steady(m, 5)
    before = m.session()
    feed(m, 160, 9000, 40.0, map_name=TOWN)
    assert m.session() == before
```

I traced each against `feed`'s confirm-on-second-read and the segment clock; if one still disagrees, fix the readings, never the asserted rule.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_meter.py -k session -v`
Expected: FAIL with `AttributeError: 'ExpMeter' object has no attribute 'session'`

- [ ] **Step 3: Implement in `meter.py`**

- `self._session: list[tuple[float, int, float, float]] = []` in `__init__`.
- In `_on_exp`, where a gain goes into `seg.gains`, add the same tuple to the session: first, if `self._session` and `t - self._session[-1][0] > SESSION_BREAK_S`, clear it. This is the only place the session grows, so it counts exactly what segments count.
- `session()`: None if the list is empty; else `exp, _, active = _totals(self._session, self.idle_cutoff_s)` and `SessionRate(exp / active * 60 if active >= 60 else None, active)`.
- Mark the cost: `# ponytail: _totals re-sorts the whole session each tick; keep running totals if long sessions show up in a profile`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_meter.py -v`
Expected: all PASS (old tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/tools/exp_meter/meter.py tests/test_meter.py
git commit -m "feat(exp): session totals across maps and levels, split after 30 min without EXP"
```

### Task 2: Two columns in the EXP tab

**Files:**
- Modify: `src/maplelens/tools/exp_meter/text.py` (`box_lines`)
- Modify: `src/maplelens/tools/exp_meter/ui.py` (`ExpMeterTool._show`, `update`)
- Test: `tests/test_text.py` (import `SessionRate` from `meter`), `tests/test_ui.py`

**Interfaces:**
- Consumes: `SessionRate`, `ExpMeter.session()` from Task 1.
- Produces: `box_lines(rate: Rate | None, session: SessionRate | None, waiting: bool, unread: bool = False) -> list[list[tuple[str, list[str]]]]` — rows, each a list of columns, each column (grey label, value lines).

- [ ] **Step 1: Rewrite the `box_lines` tests** in `tests/test_text.py`:

```python
def test_box_lines_values():
    assert box_lines(Rate(12480, 0.42, 137), SessionRate(10000, 7800), False) == [
        [("Last 5 min", ["748,800 /h", "25.20% /h"]), ("Session · 2h 10m", ["600,000 /h", ""])],
        [("Level up in", ["2h 17m"])],
    ]


def test_box_lines_no_rate():
    assert box_lines(None, None, False) == [
        [("Last 5 min", ["— /h", "—% /h"]), ("Session", ["— /h", ""])],
        [("Level up in", ["—"])],
    ]


def test_box_lines_session_under_a_minute():
    assert box_lines(None, SessionRate(None, 20), False)[0][1] == ("Session · <1m", ["— /h", ""])


def test_box_lines_left_label_states():
    assert box_lines(Rate(100, 0.1, 5, paused=True), None, False)[0][0][0] == "Paused"
    assert box_lines(Rate(100, 0.1, 5), None, False, unread=True)[0][0][0] == "Can't read bar"


def test_box_lines_no_level_eta():
    assert box_lines(Rate(100, 0.1, None), None, False)[1] == [("Level up in", ["—"])]


def test_box_lines_waiting():
    assert box_lines(None, None, True) == [[("waiting for game", [])]]
```

- [ ] **Step 2: Update `tests/test_ui.py::test_tool_says_when_bar_unreadable`**: `"EXP · last 5 min"` → `"Last 5 min"`, `"EXP · can't read bar"` → `"Can't read bar"` (`_texts[0]` stays the left label). Add one line after the first `label(...)` call: `assert tool._texts[3].text() == "Session"` (texts run left label, its two values, then the session label).

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_text.py tests/test_ui.py -v`
Expected: FAIL (old flat shape, old labels, `SessionRate` unused by `box_lines`).

- [ ] **Step 4: Implement `box_lines`** per the signature above and the spec's "The box": left label "Can't read bar" (unread) > "Paused" (`rate.paused`) > "Last 5 min"; session label "Session" when `session` is None, else `"Session · " + format_duration(session.active_s / 60)`; session value `f"{x * 60:,.0f} /h"` or `"— /h"`, then `""`.

- [ ] **Step 5: Implement the layout in `ui.py`**

- `update` passes `self._meter.session()` to `box_lines`.
- `_show`: shape becomes the per-row, per-column value counts; same-shape updates still only `setText` (no blink). `_texts` is flattened row by row, column by column, label then values, so `_texts[0]` stays the left label the accent colour targets.
- A one-column row is laid out as today. A multi-column row goes in a container `QWidget` with a `QHBoxLayout` (margins 0) holding one `QVBoxLayout` per column, each added with stretch 1, so the rebuild loop still only deletes widgets. Columns must not push the tab wider than its fixed width.

- [ ] **Step 6: Run all checks**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check && uv run python scripts/check_screen_only.py`
Expected: all pass.

- [ ] **Step 7: Render check (Review Focus: width)** — a throwaway script in the scratchpad, not committed: `QT_QPA_PLATFORM=offscreen`, build an `ExpMeterTool`, call `tool._show(box_lines(Rate(20576, 0.3, 90), SessionRate(18313, 43800), False))` (gives "1,234,560 /h" and "Session · 12h 10m"), then `tool.tab.grab().save(...)` at `set_tab_w(214)` and `set_tab_w(220)`. Look at both PNGs: nothing clipped, columns side by side, tab width unchanged. If the label clips, drop the minutes from the session label past an hour ("Session · 12h") and add a `text.py` test for it.

- [ ] **Step 8: Commit**

```bash
git add src/maplelens/tools/exp_meter/text.py src/maplelens/tools/exp_meter/ui.py tests/test_text.py tests/test_ui.py
git commit -m "feat(exp): session average beside the last-5-min rate (#50)"
```
