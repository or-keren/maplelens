# EXP Progression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The EXP tab's live rate counts only active time, History keeps only 5-minute visits and shows short map names, and a "Best for you now" strip lists the top 3 maps for the current job line.

**Architecture:** The rate change lives in `ExpMeter` (pure). The 5-minute rule is a constant plus SQL filters in `history.py` and a save guard in `ExpMeterTool`. The job line is a new `ClassData.line`, handed to the EXP tool by `app.py` as a callable, because one tool may not import another. All new text is built by pure functions in `text.py`.

**Tech Stack:** Python 3, PySide6, sqlite3, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-08-exp-progression-design.md`

## Global Constraints

- Screen-reading only. `uv run python scripts/check_screen_only.py` must pass.
- Don't change `version` in `pyproject.toml`.
- No new dependencies and no new settings. The idle cutoff stays `settings["idle_cutoff_s"]` (default 90), shared by the live rate and the segments.
- `exp_meter` must not import `class_helper` (AGENTS.md: a tool depends only on readers and overlay).
- No DB schema change and no deletes. Short visits are hidden by the queries.
- Exact copy: `EXP · last 5 min`, `EXP · paused`, `Best maps: waiting for your class and level`, `Best for {job}, Lv {level} (±3)`, `Best for {job}, Lv {level} (±3): no 5-minute visits yet`.
- After every task: `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` all pass.

## Review Focus

- **AFK then back:** after a gap longer than the cutoff, the rate shows its pre-AFK value (it doesn't decay), and the first gain after the gap adds neither time nor EXP. Test: Task 1 `test_afk_gap_neither_counts_nor_decays`.
- **History opened before the game is read:** job or level is None, so the strip shows the waiting line and nothing crashes. Test: Task 4 `test_best_lines_waiting` and `test_history_window_refresh_without_job`.
- **An old database with 1-minute rows:** these are hidden from the table, the strip and the class helper's `best_rate`. Test: Task 2 `test_short_visits_hidden`.
- **History saved under "Thief":** it still counts for a Rogue/Assassin line. Test: Task 3 `test_line_includes_aliases_and_tree`.
- **Quitting after 5+ minutes on a map saves the latest end time,** and quitting before 5 minutes saves nothing. Test: Task 2's updated `test_quit_menu_item_saves_and_quits`.

---

### Task 1: Live rate over active time

**Files:**
- Modify: `src/maplelens/tools/exp_meter/meter.py` (`Rate`, `ExpMeter.__init__`, `feed`, `_on_exp`, `rate`)
- Modify: `src/maplelens/tools/exp_meter/text.py` (`box_lines`)
- Test: `tests/test_meter.py`, `tests/test_text.py`

**Interfaces:**
- Produces: `Rate(exp_per_min: float, pct_per_min: float, minutes_to_level: float | None, paused: bool = False)`.
- Produces: the `ExpMeter.job -> str | None` and `ExpMeter.level -> int | None` properties (the confirmed values), used by Task 4.
- Produces: `box_lines` labels the rate `EXP · paused` when `rate.paused`, otherwise `EXP · last 5 min`.

**The rule** (spec §1). An *exp event* is the baseline's first confirmation, or a gain `_gain` accepts. Death, misread and spike rejections are not events. Each accepted gain has `gap = t - previous event t`. If `gap <= idle_cutoff_s`, append `(t, raw, pct, gap)` to `_window`; otherwise append nothing, because that gain starts a fresh stretch. Either way the gain becomes the previous event. After appending, drop entries from the left while the remaining gaps still add up to ≥ `window_s` without the leftmost one. `rate(now)`: `active = sum(gaps)`. Return None if `active < 60`. Otherwise divide the sums by `active / 60`, and set `paused = now - last event t > idle_cutoff_s`. Gains made while map, class or level can't be read still count in the live rate, as today. Delete `_first_t`.

- [ ] **Step 1: Write the failing tests** in `tests/test_meter.py`, using the file's `feed` and `steady` helpers:

```python
def test_rate_after_a_minute_of_active_time_even_if_app_started_earlier():
    m = ExpMeter()
    m.feed(None)  # app running long before any game reading
    for i in range(3):  # baseline at 1000.5, gains at 1030.5, 1060.5
        feed(m, 1000 + i * 30, 1000 + 100 * i, 10 + 0.5 * i)
    rate = m.rate(1061)
    assert rate.pct_per_min == pytest.approx(1.0)
    assert not rate.paused


def test_afk_gap_neither_counts_nor_decays():
    m = ExpMeter()
    steady(m, 5)  # gains of 0.5 at 30.5 .. 120.5, active 120 s
    before = m.rate(121).pct_per_min
    assert m.rate(400).pct_per_min == pytest.approx(before)
    assert m.rate(400).paused
    feed(m, 600, 1300, 13.0)  # first gain after AFK: 1.0, gap 479.5 s, not counted
    assert m.rate(601).pct_per_min == pytest.approx(before)
    feed(m, 630, 1350, 13.5)
    assert m.rate(631).pct_per_min == pytest.approx(2.5 / (150 / 60))


def test_window_is_last_five_active_minutes_across_a_gap():
    m = ExpMeter()
    steady(m, 11)  # 10 gains of 0.5 over 300 active s, ending 300.5 at 15.0%
    for i in range(1, 5):  # 4 gains of 1.0; the one at 900.5 follows AFK, so it starts a stretch
        feed(m, 900 + (i - 1) * 30, 1500 + 100 * i, 15.0 + i)
    # window: the 3 new 1.0 gains (90 s) + the last 7 old 0.5 gains (210 s)
    assert m.rate(991).pct_per_min == pytest.approx((3.0 + 3.5) / 5)
```

  In `tests/test_text.py`:

```python
def test_box_lines_paused():
    assert box_lines(Rate(100, 0.1, None, paused=True), False)[0][0] == "EXP · paused"
```

- [ ] **Step 2: Run the new tests to verify they fail.**
  Run: `uv run pytest tests/test_meter.py tests/test_text.py -q`. Expected: the four new tests FAIL.

- [ ] **Step 3: Implement the rule above** in `meter.py`, add the `job` and `level` properties, and add the label switch in `box_lines`.

- [ ] **Step 4: Update the existing expectations** that change under the rule. Each test keeps checking what it checks today:
  - `test_level_up_counts_across_wrap`: `7.0 / (150 / 60)`
  - `test_single_frame_misread_ignored`: `m.rate(100) is None` (no gains, so no active time)
  - `test_death_then_map_change_counts_nothing`: `pytest.approx(1.0)`
  - `test_covered_bar_keeps_baseline`: `1.5 / (130 / 60)`
  - `test_paused_gain_not_credited_to_segment`: `1.5 / (90 / 60)`
  - These are unchanged and must still pass: `test_steady_gain_rate`, `test_rate_none_before_a_minute`, `test_death_not_counted`, `test_jump_not_counted` (0.9), `test_covered_level_up_never_negative`.

- [ ] **Step 5: Run everything.** Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`. Expected: all pass.

- [ ] **Step 6: Commit.** `git commit -am "feat(exp): live rate over the last 5 active minutes, paused when idle"`

---

### Task 2: History keeps only 5-minute visits

**Files:**
- Modify: `src/maplelens/tools/exp_meter/history.py`
- Modify: `src/maplelens/tools/exp_meter/ui.py` (`ExpMeterTool._save`)
- Test: `tests/test_history.py`, `tests/test_ui.py`

**Interfaces:**
- Produces: `MIN_VISIT_S = 300` in `history.py`.
- Produces: `best_maps(conn, jobs: Collection[str], level: int, n: int = 3, spread: int = 3) -> list[tuple[str, float, float]]`, returning `(map title, exp_per_min, pct_per_min)` with the highest EXP/min first. It covers qualifying visits with `job IN jobs` and levels `level - spread` to `level + spread`, grouped by map, using `SUM(exp) / SUM(active_s) * 60`.

`history()`, `best_rate()` and `best_maps()` all filter on `active_s > 0 AND end - start >= MIN_VISIT_S` (pass it as a parameter). `_save` saves a closed segment only if `seg.end - seg.start >= MIN_VISIT_S`, and flushes the open one only under that same condition. It sets `_last_flush` only when it actually saves, so the first flush happens on the first tick after the visit qualifies.

- [ ] **Step 1: Write the failing tests.** In `tests/test_history.py`, change `_seg` so `end = start + 300`, update `test_history_groups_and_averages` to `row.last == 400`, then add:

```python
def test_short_visits_hidden(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, Segment(0, 299, "Henesys", "Hero", 44, 600, 1.2, 60.0))
    assert history(conn) == []
    assert best_rate(conn, "Henesys") is None
    assert best_maps(conn, {"Hero"}, 44) == []


def test_best_maps_job_line_level_range_top_three(tmp_path):
    conn = open_db(tmp_path / "t.db")
    for i, (m, job, lvl, exp) in enumerate(
        [
            ("A", "Rogue", 28, 600),
            ("B", "Thief", 29, 900),
            ("C", "Assassin", 31, 300),
            ("D", "Assassin", 32, 1200),
            ("E", "Bandit", 30, 5000),
            ("F", "Assassin", 35, 5000),
        ]
    ):
        save_segment(conn, _seg(i * 1000, exp=exp, level=lvl, map_name=m, job=job))
    rows = best_maps(conn, {"Rogue", "Thief", "Assassin"}, 31)
    assert [r[0] for r in rows] == ["D", "B", "A"]
    assert rows[0][1] == approx(1200)
```

  In `tests/test_ui.py`:
  - `test_tool_flushes_open_segment_each_minute`: play 6 minutes (145 ticks at 2.5 s) and shut down at `1000 + 145 * 2.5`.
  - Add `test_tool_skips_visits_under_five_minutes`: the same loop for 4 minutes (97 ticks), then `history(conn) == []`, both before and after `tool.shutdown`.
  - `test_quit_menu_item_saves_and_quits`: play 310 s (125 ticks). Drop the "too short for the periodic flush" assert. Quit with `tool.shutdown(1320.0)`, then assert `history(conn)[0].last == 1320.0`.

- [ ] **Step 2: Run the tests to verify they fail.** Run: `uv run pytest tests/test_history.py tests/test_ui.py -q`. Expected: the new tests FAIL (`best_maps` doesn't exist, and short visits still show).

- [ ] **Step 3: Implement** `MIN_VISIT_S`, the filters, `best_maps` and the `_save` guard.

- [ ] **Step 4: Run everything.** Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "feat(exp): keep only visits of 5 minutes or more in History"`

---

### Task 3: Job line in the class data

**Files:**
- Modify: `src/maplelens/tools/class_helper/data.py` (`ClassData`)
- Test: `tests/test_class_data.py`

**Interfaces:**
- Produces: `ClassData.line(job: str) -> frozenset[str]`.

A line is the job (resolved through `ALIASES`), plus every ancestor and every descendant on the `next_jobs` tree, plus the alias names of any job in the set. The tree's edges come from each `JobPlan.advance` and each of its builds' `advance`. Jobs that only appear as a target, like Hermit, still get a line. A job that appears nowhere in the tree returns `frozenset({job})`. Beginner needs no special case: it's the root, so it's an ancestor of every job.

- [ ] **Step 1: Write the failing test** (real data, because the small fixture has no Hermit or Beginner):

```python
def test_line_includes_aliases_and_tree():
    d = load()
    assassin = {"Beginner", "Rogue", "Thief", "Assassin", "Hermit"}
    assert d.line("Assassin") == assassin
    assert d.line("Hermit") == assassin
    assert d.line("Thief") >= {"Beginner", "Rogue", "Assassin", "Bandit", "Hermit", "Chief Bandit"}
    assert "Bandit" not in d.line("Assassin")
    assert d.line("Nobody") == {"Nobody"}
```

- [ ] **Step 2: Run it to verify it fails.** Run: `uv run pytest tests/test_class_data.py -q`. Expected: FAIL with `AttributeError: 'ClassData' object has no attribute 'line'`.

- [ ] **Step 3: Implement `ClassData.line`.**

- [ ] **Step 4: Run everything.** Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "feat(class): job line from the advancement tree"`

---

### Task 4: History window: short names and the "Best for you now" strip

**Files:**
- Modify: `src/maplelens/tools/exp_meter/text.py`
- Modify: `src/maplelens/tools/exp_meter/ui.py` (`HistoryWindow`, `ExpMeterTool`)
- Modify: `src/maplelens/app.py` (main wiring near `ExpMeterTool(settings, conn)` and `ClassHelperTool(...)`)
- Test: `tests/test_text.py`, `tests/test_ui.py`

**Interfaces:**
- Consumes: `ExpMeter.job` and `ExpMeter.level` (Task 1); `best_maps` (Task 2); `ClassData.line` (Task 3).
- Produces: `short_name(title: str) -> str`, which returns `title.rpartition(" / ")[2]`.
- Produces: `best_lines(job: str | None, level: int | None, rows: list[tuple[str, float, float]]) -> tuple[str, list[tuple[str, str, str]]]`, which returns the header plus `(short name, "52,300 EXP/h", "1.85% /h")` per row. Rates are per hour, formatted as in the table: `f"{exp_per_min * 60:,.0f} EXP/h"` and `f"{pct_per_min * 60:.2f}% /h"`. When job or level is None, it returns the waiting header and no rows. When there are no rows, it returns the "no 5-minute visits yet" header.
- Produces: `HistoryWindow(conn, job_line: Callable[[str], Collection[str]] = lambda j: {j})`, a `QWidget` holding the strip (a `QGridLayout` of `QLabel`s) above the existing table. `HistoryWindow.refresh(job: str | None = None, level: int | None = None)`.
- Produces: `ExpMeterTool(settings, conn, job_line=lambda j: {j})`. `_show_history` calls `refresh(self._meter.job, self._meter.level)`.
- `app.py`: `cls_data = class_data.load()` once, then `ExpMeterTool(settings, conn, cls_data.line)` and `ClassHelperTool(..., data=cls_data)`.

The table's Map cell shows `short_name(title)` and sorts by it, with the full title as its tooltip (`item.setToolTip`). Keep the Mac panel flags, `WA_QuitOnClose` and `native_setup` on the new outer widget. Size the window so the table keeps about its current height.

- [ ] **Step 1: Write the failing tests.** In `tests/test_text.py`:

```python
def test_short_name():
    assert short_name("Victoria Island / Henesys Hunting Ground I") == "Henesys Hunting Ground I"
    assert short_name("No Street") == "No Street"


def test_best_lines_waiting():
    assert best_lines(None, 28, []) == ("Best maps: waiting for your class and level", [])


def test_best_lines_empty_and_rows():
    assert best_lines("Rogue", 28, [])[0] == "Best for Rogue, Lv 28 (±3): no 5-minute visits yet"
    head, rows = best_lines("Rogue", 28, [("Hidden Street / Pig Beach", 700.0, 0.03)])
    assert head == "Best for Rogue, Lv 28 (±3)"
    assert rows == [("Pig Beach", "42,000 EXP/h", "1.80% /h")]
```

  In `tests/test_ui.py`, add `test_history_window_refresh_without_job`: an empty DB, `HistoryWindow(conn).refresh(None, None)`, and a `QLabel` with the waiting text is among `win.findChildren(QLabel)`. Then add `test_history_map_cell_short_name_full_tooltip`: save one qualifying segment titled `"Victoria Island / Henesys Hunting Ground I"`, call `refresh("Hero", 44)`, and check that the table's `item(0, 0)` has text `"Henesys Hunting Ground I"` and tooltip equal to the full title. The existing `HistoryWindow` tests must still pass unchanged.

- [ ] **Step 2: Run the tests to verify they fail.** Run: `uv run pytest tests/test_text.py tests/test_ui.py -q`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `short_name` and `best_lines`, the `HistoryWindow` rework and the wiring in `ExpMeterTool` and `app.py`.

- [ ] **Step 4: Run everything, including the guard.** Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run python scripts/check_screen_only.py`. Expected: all pass.

- [ ] **Step 5: Commit.** `git commit -am "feat(exp): short map names and a best-maps strip in History"`
