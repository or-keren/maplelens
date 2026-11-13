# Overlay Redesign and README Screenshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A calmer Class tab built around "go train here", one shared look for every tab, and real in-game screenshots in the README.

**Architecture:** Shared colours, button and info-line helpers move into `overlay.py`, and every tool uses them. The Class tab's pure logic gains `milestones()` in `plan.py`. Its view is rebuilt from clickable rows, and the build choice moves into the ••• menu. Part 2 adds a `--screen` mode to `scripts/grab.py` and puts the shots into the README after Part 1 is merged.

**Tech Stack:** Python 3, PySide6, pytest (offscreen Qt), uv, ruff.

**Spec:** `docs/superpowers/specs/2026-11-08-overlay-redesign-design.md`

## Global Constraints

- Screen-reading only (AGENTS.md "The rule"): `uv run python scripts/check_screen_only.py` stays green, and no banned module or Win32 names go in comments or docstrings under `src/` or `scripts/`.
- Never change `version` in `pyproject.toml`.
- No new dependency.
- Nothing in the box takes keyboard focus: every new button or clickable row gets `Qt.NoFocus`.
- No tab gets taller than it is today, and the box is 210 px wide (`TAB_W` 186 plus 12 px margins) on every tab, in every state.
- Yellow (`ACCENT` `#ffcc33`) only for "do this": the selected tab, the primary button, the AP/SP chip, the job-advance outline, the arrow, "add here" rings, the tab dot and the update notice.
- Never commit character names, chat, or other players' names. Screenshots are blurred first and shown to the owner before they're committed.
- Each task ends with `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and the guard all passing.

## Review Focus

1. **The `ⓘ` glyph falls back to another font** and makes the line taller or faint (it happened before with the midline ellipsis, see `MENU_MARK`). Expected: an info line is no taller than a plain label. Test in Task 1.
2. **A very long map or NPC name** (no spaces, 40+ characters) in a Class row. Expected: one line, elided with "…", and the box stays 210 px. Test in Task 4.
3. **A training row or gear row with no `map_id`.** Expected: no `›`, and a click does nothing. Test in Task 4.
4. **Points in both pools, and SP read at an older level.** Expected: the chip reads `5 AP · 3 SP`, and SP read at an older level is ignored, as `_points()` does today. Test in Task 4.
5. **The job changes to one with no plan, or with one build.** Expected: the ••• `Build:` item hides, and comes back when the plan has two or more builds again. Test in Task 6.

---

## Part 1: the overlay

### Task 1: Shared look in `overlay.py`, EXP tab on it

**Files:**
- Modify: `src/maplelens/overlay.py`
- Modify: `src/maplelens/tools/exp_meter/ui.py` (History button)
- Test: `tests/test_overlay.py`, `tests/test_ui.py`

**Interfaces:**
- Produces, all in `maplelens.overlay`:
  - Constants: `LABEL_PT = 10`, `LABEL_COLOR = "#aebdd3"`, `FIELD = "#0b0f15"`, `DARK = "#2a1d00"`, `HERE_BG = "#2c3a50"`, `EDGE = "#3d4b63"`, `CHIP_BG = "#3a2e08"`, `INFO_ICON = "#7fa8ff"`. `VALUE_PT`, `VALUE_COLOR`, `ACCENT`, `TAB_W` and `FONT` are unchanged.
  - `FIELD_STYLE: str`: a stylesheet for `QLineEdit` and `QListWidget`. Background `FIELD`, border 1 px `EDGE`, which turns `ACCENT` on `:focus`. The list's selected item uses `HERE_BG`.
  - `primary_button(text: str, on_click: Callable[[], None]) -> QPushButton`: yellow fill, `DARK` bold text, 4 px radius. `:disabled` is `HERE_BG` with `LABEL_COLOR` text. `property("kind") == "primary"`.
  - `secondary_button(text: str, on_click: Callable[[], None]) -> QPushButton`: transparent, 1 px `EDGE` border, `#e6edf7` text, 4 px radius. `property("kind") == "secondary"`.
  - Both buttons: `Qt.NoFocus` and `Qt.PointingHandCursor`.
  - `class InfoLine(QWidget)`: an `ⓘ` in `INFO_ICON`, then word-wrapped text in `LABEL_COLOR` at `LABEL_PT`. It has `setText(text: str) -> None` and `text() -> str`, which returns the text without the icon.
- Box paint: `QColor(16, 18, 24, 224)`, plus a 1 px `QColor(255, 255, 255, 20)` rounded edge.

- [ ] **Step 1: Write the failing tests** in `tests/test_overlay.py`, using its existing offscreen-app setup:

```python
def test_buttons_have_kinds_and_never_take_focus(app):
    from PySide6.QtCore import Qt
    from maplelens.overlay import primary_button, secondary_button

    hits = []
    p, s = (
        primary_button("Start", lambda: hits.append("p")),
        secondary_button("Stop", lambda: hits.append("s")),
    )
    assert (p.property("kind"), s.property("kind")) == ("primary", "secondary")
    assert p.focusPolicy() == s.focusPolicy() == Qt.NoFocus
    p.click()
    s.click()
    assert hits == ["p", "s"]


def test_info_line_text_and_height(app):
    from maplelens.overlay import LABEL_COLOR, LABEL_PT, InfoLine, text_label

    line = InfoLine()
    line.setText("No minimap on this map")
    assert line.text() == "No minimap on this map"
    plain = text_label("No minimap on this map", LABEL_PT, LABEL_COLOR)
    assert line.sizeHint().height() <= plain.sizeHint().height() + 2  # Review Focus 1
```

In `tests/test_ui.py`: the EXP tab's History button has `property("kind") == "secondary"`.

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_overlay.py tests/test_ui.py -v`
Expected: FAIL with ImportError on `primary_button` / `InfoLine`.

- [ ] **Step 3: Add the constants, `FIELD_STYLE`, the two button helpers, `InfoLine`, and the new box paint to `overlay.py`. Make EXP's History a `secondary_button`.**

If the `ⓘ` makes the line taller under Segoe UI, draw the icon instead: a small circle with an "i", painted in `INFO_ICON` at the label's cap height. Don't use another font.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/overlay.py src/maplelens/tools/exp_meter/ui.py tests/test_overlay.py tests/test_ui.py
git commit -m "feat(overlay): shared colours, buttons and info line"
```

### Task 2: Path tab on the shared look, one honest message

**Files:**
- Modify: `src/maplelens/tools/path_arrow/ui.py`
- Test: `tests/test_path_ui.py`

**Interfaces:**
- Consumes: `FIELD_STYLE`, `HERE_BG`, `DARK`, `primary_button`, `secondary_button`, `InfoLine` (Task 1).
- Produces:
  - `NOT_LISTED = "Not in the map list yet, so no route from here"` (replaces "This map isn't in MapleLens's map list yet").
  - `tool._message`: the yellow label, which now only holds `OPEN` and `HIDDEN`.
  - `tool._info`: an `InfoLine` for every other `_why()` text ("No route from here to …", "No minimap on this map", "No arrow on this map yet", "No arrow on this part of the map yet", `NOT_LISTED`).
- Start becomes `primary_button`, and Stop becomes `secondary_button`. The module's own `_FIELD`, `_DARK` and `_HERE_BG` go, and the `_STYLE` field and list part becomes `FIELD_STYLE`. The route-list colours `_DONE`, `_AHEAD` and `_NUM` stay local.

- [ ] **Step 1: Update and add tests** in `tests/test_path_ui.py`:
  - `test_unknown_map_message`, `test_no_route_message`, `test_no_minimap_message` and `test_no_arrow_on_big_map_without_npcs` read `tool._info.text()` instead of `tool._message.text()`. The unknown-map one expects `NOT_LISTED`.
  - `test_minimap_message_after_3s` and `test_dot_missing_message_immediately` keep `tool._message` (`OPEN` stays yellow).
  - New:

```python
def test_read_but_unlisted_map_names_itself(make):
    from maplelens.tools.path_arrow.ui import NOT_LISTED

    tool = make()
    feed(tool, "Road / Nowhere")  # read twice: confirmed, not in the data
    assert tool._header.text() == "From: Nowhere"
    assert tool._info.text() == NOT_LISTED and tool._info.isVisibleTo(tool.tab)
    assert not tool._message.isVisibleTo(tool.tab)


def test_start_and_stop_kinds(make):
    tool = make()
    assert tool._start.property("kind") == "primary"
    assert tool._stop.property("kind") == "secondary"
```

  - `test_start_disabled_when_map_unknown`: after `feed(tool, "Road / Nowhere")`, the header is `"From: Nowhere"`. Before any feed it's still `"From: (can't read your map yet)"`.

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_path_ui.py -v`
Expected: FAIL (there's no `_info` and no `NOT_LISTED`, and the header is wrong).

- [ ] **Step 3: Implement it in `path_arrow/ui.py`**
  - `_render()` sends `OPEN` and `HIDDEN` to `_message`, and every other text to `_info`. Each one shows only when it's non-empty.
  - The header has a new branch: when `self._title` is set, `self._here is None` and the map isn't unread, the header is `self._fit("From: {}", short)`. Here `short` is the part of `self._title` after the last `" / "`.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/tools/path_arrow/ui.py tests/test_path_ui.py
git commit -m "feat(path): shared look; a read but unlisted map names itself"
```

### Task 3: `milestones()` and `advance_ready()` in `plan.py`

**Files:**
- Modify: `src/maplelens/tools/class_helper/plan.py`
- Test: `tests/test_class_plan.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Milestone: level: int; text: str; where: Place | None = None; item: Item | None = None`
  - `advance_ready(plan: JobPlan, build: Build, level: int) -> Advance | None`: the advance when `level >= adv.level`, otherwise `None`.
  - `milestones(plan: JobPlan, build: Build, level: int) -> list[Milestone]`, sorted by level. Ties keep this order:
    - The advance, when it exists and isn't ready: `Milestone(adv.level, "Advance: " + " or ".join(adv.next_jobs), adv.where)`.
    - The next gear row: `Milestone(nxt.from_level, f"Gear: {nxt.item.name}", nxt.where, nxt.item)`.
    - The reset, when `build.reset_at is not None and level <= build.reset_at`: `Milestone(build.reset_at, f"Reset AP for the {build.name} build")`.
  - `short_name(name: str) -> str`: the part after the last `" / "`.
- Deleted: `advance_due`, `advance_text`, `next_step`, `ADVANCE_EARLY`, and their tests. `_jobs` goes too if nothing else uses it.

- [ ] **Step 1: Write the failing tests** using the existing helpers in `tests/test_class_plan.py` and the `classes_small.json` Rogue: advance at 30 (Assassin, Bandit); LUK build gear First Claw at 10 and Second Claw at 15; Sindit build `reset_at` 30.

```python
def test_milestones_in_level_order(small):
    rogue = small.jobs["Rogue"]
    luk, sindit = rogue.builds
    assert [(m.level, m.text) for m in milestones(rogue, luk, 12)] == [
        (15, "Gear: Second Claw"),
        (30, "Advance: Assassin or Bandit"),
    ]
    assert [(m.level, m.text) for m in milestones(rogue, sindit, 30)] == [
        (30, "Reset AP for the Sindit build")
    ]  # ready advance left out; no gear


def test_advance_ready_only_at_its_level(small):
    rogue = small.jobs["Rogue"]
    assert advance_ready(rogue, rogue.builds[0], 29) is None
    assert advance_ready(rogue, rogue.builds[0], 30).level == 30


def test_short_name():
    assert short_name("Kerning City Subway / Transfer Area") == "Transfer Area"
    assert short_name("Henesys") == "Henesys"
```

(Use whatever fixture name the file already uses for `classes_small.json`. If it has none, `load(SMALL, MAPS)` as in `test_class_ui.py`.)

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_class_plan.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement it, and delete the replaced functions and their tests.** Leave `ui.py`'s imports broken for now only if Task 4 lands in the same session. Otherwise keep `advance_due` and `next_step` until Task 4 removes their last use.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest tests/test_class_plan.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/tools/class_helper/plan.py tests/test_class_plan.py
git commit -m "feat(class): milestones and advance_ready replace next_step"
```

### Task 4: The Class tab rebuilt

**Files:**
- Modify: `src/maplelens/tools/class_helper/ui.py`
- Test: `tests/test_class_ui.py`

**Interfaces:**
- Consumes: `milestones`, `advance_ready`, `short_name`, `Milestone` (Task 3). `InfoLine`, `HERE_BG`, `CHIP_BG`, `EDGE` (Task 1).
- Produces:
  - `class Row(QWidget)` in `class_helper/ui.py`: `Row(name: str, sub: str, on_click: Callable[[], None] | None, *, best: bool = False, outline: bool = False)`.
    - `name` is drawn on one line, elided to fit, with the full text as the tooltip. It's bold when `best` or `outline`.
    - `sub` is one grey line.
    - A yellow `›` shows only when `on_click` is set. A mouse release inside the row calls `on_click`.
    - `best` gives a `HERE_BG` background. `outline` gives a `HERE_BG` background with a 1 px `ACCENT` border.
    - Attributes: `row.name: str` (the full name), `row.sub: str`, `row.clickable: bool`, and `row.click() -> None`, which calls `on_click` if it's set (for tests).
    - `Qt.NoFocus` and `Qt.PointingHandCursor` (only when clickable).
  - `ClassHelperTool` keeps `update`, `set_marks`, `marks`, `hide_marks`, `dot` and `title`, and adds:
    - `build_names() -> list[str]`: the current plan's build names, or `[]` when there's no plan or only one build.
    - `build_name() -> str | None`: the chosen build of the current plan.
    - `pick_build(name: str) -> None`: saves to `class_builds`, calls the settings callback, and redraws. This replaces `_on_build`.
    - `builds_changed: Callable[[], None]`: a no-op by default. It's called when `build_names()` or `build_name()` may have changed (new plan or new pick).
  - Copy constants: `TRAIN = "Train here · click to go"`, `NO_SPOTS = "No training spots in the guide for Lv {}"`, `READY = "Job advance is ready"`, `NEXT = "Next"`. `NO_CLASS`, `NO_PLAN`, `OPEN_STATS`, `STAT_UNREAD`, `SKILL_UNREAD` and `MARKS` keep their text.
  - `MARK_PT = 9`: `_Mark` uses it instead of `LABEL_PT`.
- Removed: `_builds` (`QComboBox`), `_marks_box` (`QCheckBox`), `marks_changed`, every "Go" button, and `_STYLE`'s combobox, checkbox and go rules.

**Tab content, top to bottom** (spec, "Class tab"):
1. A header row: a `"{job} · Lv {level}"` label, and on the right a chip label (`objectName "chip"`, `CHIP_BG` background, `ACCENT` bold text, 10 px radius). The chip shows `"{ap} AP"`, `"{sp} SP"` or `"{ap} AP · {sp} SP"`, and is hidden when both are 0.
2. When `advance_ready` returns an advance: `Row(READY, " · ".join(npc, short_name(where.name)), go-or-None, outline=True)`.
3. A `TRAIN` label, then one `Row` per `training()` row that has a place:
   - The name is `short_name(place.name)`.
   - The sub-line is `f"your best · {rate:,.0f}/min"` when `best_rate(place.title)` returns a value, otherwise `f"mobs Lv {a}–{b}"`.
   - `best=True` goes on the highest-rate row, and only while there's no advance row.
   - With no rows: `InfoLine(NO_SPOTS.format(level))`.
4. When `milestones()` is non-empty: a 1 px `HERE_BG` divider and a `NEXT` label.
   - One line per milestone: `f"Lv {m.level} · {m.text}"`, using `short_name` for any map name.
   - A gear milestone with a `where` that has a `map_id` is a `Row` (clickable). The others are labels.
   - Under a gear milestone, when `short()` reports missing stats, add a grey `"3 DEX short"`-style line.
5. Hints, each an `InfoLine`: `OPEN_STATS` / `STAT_UNREAD` / `SKILL_UNREAD` (same conditions as `_reasons()`) and `"{tier} tab: {n} SP to place"` (same as `_tab_lines()`).

`NO_CLASS` and `NO_PLAN` render as a single `InfoLine` with nothing else. The level-up dot's key still covers training places, gear ids, whether the advance is ready, and `ap + sp`.

- [ ] **Step 1: Rewrite the tests that change, and add new ones** in `tests/test_class_ui.py`.
  - Add a helper next to `texts()`: `def rows(tool): return sorted(visible Row children of tool.tab, by y)`.
  - `texts()` also collects `InfoLine.text()`.
  - Replace these:

```python
def test_training_rows_click_to_go_and_best_rate(make):
    tool = make(best_rate=lambda t: 1234.0 if t else None)
    tool.update(R(level=12), RECT, 0)
    first, *rest = rows(tool)
    assert first.sub == "your best · 1,234/min" and first.clickable
    first.click()
    assert tool.gone == ["000000001"]


def test_row_without_a_map_is_not_clickable(make):  # Review Focus 3
    tool = make()
    tool.update(R(level=15), RECT, 0)
    plain = [r for r in rows(tool) if r.name == "A map not in maps.json"]
    assert plain and not plain[0].clickable
    plain[0].click()
    assert tool.gone == []


def test_chip_counts_points(make):  # Review Focus 4
    tool = make()
    tool.update(R(level=12, stats=SW(level=12, ap=5), skills=KW(sp=3, rows=ALL_ROGUE)), RECT, 0)
    assert "5 AP · 3 SP" in texts(tool)
    tool.update(R(level=13), RECT, 1)
    assert not any(t.endswith(("AP", "SP")) for t in texts(tool))


def test_advance_ready_row_on_top_and_out_of_footer(make):
    tool = make()
    tool.update(R(level=30), RECT, 0)
    assert rows(tool)[0].name == READY
    assert not any("Advance:" in t for t in texts(tool))
    assert not any(r.best for r in rows(tool))


def test_footer_lists_milestones(make):
    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert NEXT in texts(tool)
    assert "Lv 15 · Gear: Second Claw" in texts(tool) + [r.name for r in rows(tool)]
    assert "Lv 30 · Advance: Assassin or Bandit" in texts(tool)


def test_no_spots_says_so(make):
    tool = make()
    tool.update(R(level=25), RECT, 0)  # no Rogue training row covers 25 in the small data
    assert NO_SPOTS.format(25) in texts(tool)


def test_long_name_stays_one_line(make):  # Review Focus 2
    from maplelens.tools.class_helper.ui import Row

    row = Row("Victoria Road / " + "X" * 60, "mobs Lv 1–2", None)
    row.setFixedWidth(186)
    assert row.sizeHint().height() == Row("Short", "mobs Lv 1–2", None).sizeHint().height()


def test_no_build_picker_or_marks_box_in_the_tab(make):
    from PySide6.QtWidgets import QCheckBox, QComboBox

    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert not tool.tab.findChildren(QComboBox) and not tool.tab.findChildren(QCheckBox)


def test_pick_build_saves_and_tells(make):
    saved, told = [], []
    tool = make(on_changed=lambda: saved.append(1))
    tool.builds_changed = lambda: told.append(1)
    tool.update(R(level=12), RECT, 0)
    assert tool.build_names() == ["LUK", "Sindit"] and tool.build_name() == "LUK"
    tool.pick_build("Sindit")
    assert tool._settings["class_builds"] == {"Rogue": "Sindit"} and saved and told
    tool.update(R(job="Hermit", level=72), RECT, 1)
    assert tool.build_names() == []
```

  - Delete `test_build_picker_saved`, `test_planless_job_hides_the_picker` and `test_the_tab_box_and_the_menu_follow_each_other`.
  - `test_stats_never_read_then_badge_until_level_changes` expects the chip `"3 AP"` in place of `"3 AP to spend"`.
  - Check the levels used above against `classes_small.json` and adjust if a range is off by one. Keep what each test asserts.

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_class_ui.py -v`
Expected: the new tests FAIL (there's no `Row` and no `build_names`).

- [ ] **Step 3: Rebuild the tab in `class_helper/ui.py` as listed above.** `_render()` keeps its "redraw only when the items changed" rule and its immediate `delete(old)`.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest -q`
Expected: all pass. `test_app.py` may fail where it sets `marks_changed`; Task 6 fixes that. If so, run Task 6 before committing, or temporarily keep a no-op `marks_changed` attribute and remove it in Task 6.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/tools/class_helper/ui.py tests/test_class_ui.py
git commit -m "feat(class): tab built around where to train"
```

### Task 5: Same box width on every tab, no overlapping text

**Files:**
- Modify: wherever the root cause is (expected in `src/maplelens/overlay.py` `Box`, or the Class tab's labels)
- Test: `tests/test_class_ui.py`

**Interfaces:**
- Consumes: `Box` and the three tools as `app.py` builds them.

- [ ] **Step 1: Write the failing tests**

```python
STATES = [("Rogue", 28), ("Beginner", 8), ("Rogue", 30), (None, None)]


def test_box_width_is_the_same_on_every_tab(box_with_tools):
    box, cls = box_with_tools  # a Box holding EXP, Path and Class tools, offscreen
    widths = set()
    for job, level in STATES:
        cls.update(R(job=job, level=level), RECT, 0)
        for i in range(3):
            box.select(i)
            box.adjustSize()
            widths.add(box.width())
    assert widths == {210}


def test_class_tab_text_never_overlaps(box_with_tools):
    box, cls = box_with_tools
    for job, level in STATES:
        cls.update(R(job=job, level=level), RECT, 0)
        box.select(2)
        box.adjustSize()
        rects = [
            w.geometry().translated(w.parentWidget().mapTo(cls.tab, QPoint()))
            for w in cls.tab.findChildren(QLabel)
            if w.isVisibleTo(cls.tab)
        ]
        assert not any(
            a.intersects(b)
            for i, a in enumerate(rects)
            for b in rects[i + 1 :]
            if not (a.contains(b) or b.contains(a))
        )
```

Build the `box_with_tools` fixture as `test_class_ui.py`'s `make` does, using the real `classes.json` (`load()`) so that Beginner 8 and Rogue 28 have their real content.

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_class_ui.py -k "width or overlaps" -v`
Expected: the width test FAILS with a set holding a value other than 210 (the design review measured 223 and 302).

- [ ] **Step 3: Find the root cause and fix it there** (superpowers:systematic-debugging). The tab already has `setFixedWidth(TAB_W)`, so look at what sizes the box past it: the page stack's hints (see the comment on `_matches.setSizePolicy` in `path_arrow/ui.py`), a word-wrapped label's minimum width, or the swapped-in `_body`. Fix it once in `Box` if every tab could hit it. Don't patch widths per state.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A src tests
git commit -m "fix(overlay): the box keeps one width on every tab"
```

### Task 6: Build choice in the ••• menu; app wiring

**Files:**
- Modify: `src/maplelens/overlay.py` (`Box.add_submenu` returns its action)
- Modify: `src/maplelens/app.py` (around lines 792-796)
- Test: `tests/test_overlay.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `build_names`, `build_name`, `pick_build`, `builds_changed` (Task 4).
- Produces:
  - `Box.add_submenu(label, choices, on_pick, *, at: int | None = None) -> QAction`: the submenu's `menuAction()`, inserted like `_insert` does.
  - `app.add_build_menu(box: Box, tool) -> QAction`: adds a submenu listing `tool.build_names()` that calls `tool.pick_build`. It sets `tool.builds_changed` to update the action's text to `f"Build: {tool.build_name()}"` and its visibility to `bool(tool.build_names())`. It starts hidden. It goes above the marks toggle.
- Removed: `cls_tool.marks_changed = marks.setChecked` in `app.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_overlay.py
def test_add_submenu_returns_its_action(app):
    box = Box("b", {}, lambda: None)
    action = box.add_submenu("Pick", lambda: ["a"], lambda t: None)
    assert action in box.actions() and action.text() == "Pick"


# tests/test_app.py
def test_build_menu_follows_the_class_tool(qt):  # Review Focus 5
    class Tool:
        names, name, picked = ["LUK", "Sindit"], "LUK", []
        builds_changed = None

        def build_names(self):
            return self.names

        def build_name(self):
            return self.name

        def pick_build(self, n):
            self.picked.append(n)

    box, tool = Box("b", {}, lambda: None), Tool()
    action = app.add_build_menu(box, tool)
    assert not action.isVisible()
    tool.builds_changed()
    assert action.isVisible() and action.text() == "Build: LUK"
    tool.names = []
    tool.builds_changed()
    assert not action.isVisible()
```

Use `test_app.py`'s existing offscreen-Qt fixture in place of `qt` if it has one.

- [ ] **Step 2: Run them and check that they fail**

Run: `uv run pytest tests/test_overlay.py tests/test_app.py -k "submenu or build_menu" -v`
Expected: FAIL.

- [ ] **Step 3: Implement it.** Make `add_submenu` return its action and take `at`, then add `add_build_menu`, wire it in `main`, and drop the `marks_changed` line.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/overlay.py src/maplelens/app.py tests/test_overlay.py tests/test_app.py
git commit -m "feat(app): build choice in the menu"
```

### Task 7: Look at it (render review)

No commit, unless it turns up a fix (which then goes in the task that owns the code).

- [ ] **Step 1:** In the scratchpad (not the repo), write a script that builds the box with the three real tools offscreen and saves `box.grab()` for:
  - EXP with numbers
  - Path while choosing, while running, and with a read but unlisted map
  - Class at Rogue 28 (with 5 AP), Rogue 30 (advance ready), Beginner 8, Hunter 34, and "no class read"
- [ ] **Step 2:** Look at each image against the spec:
  - one width
  - no overlap
  - yellow only on "do this"
  - no tab taller than today's render: Class at Rogue 28 used to be 18 lines, and must now be shorter
- [ ] **Step 3:** Put the images together into one sheet and show it to the owner (SendUserFile). Fix whatever they flag before Part 1's PR.

### Task 8: Ellinia investigation (needs the owner in the game, doesn't block Part 1)

- [ ] **Step 1:** Ask the owner to stand in Ellinia, windowed. Run `uv run python scripts/grab.py --title MapleStory --label map_ellinia`.
- [ ] **Step 2:** Run the readers on the saved frame (`read_all(frame, 0).map_name`) and `find(load(), name, None)`. Compare the result with "Victoria Road / Ellinia" (id `010002000`).
- [ ] **Step 3:** If the reader or `find` is wrong:
  - crop the fixture to the minimap title (AGENTS.md "Fixture screenshots"), named `map_ellinia_1920x1080_100.png`
  - add a failing reader test, fix it (superpowers:systematic-debugging) and commit on its own
- [ ] **Step 4:** If it reads correctly, write that in the PR description. If the owner isn't available, list it in the PR as a follow-up.

---

## Part 2: README screenshots (after Part 1 is merged)

### Task 9: `scripts/grab.py --screen`

**Files:**
- Modify: `scripts/grab.py`
- Modify: `AGENTS.md` (grab.py's line: "also `--screen`: the screen over the game, overlay included, for README shots")
- Test: `tests/test_grab.py` (new)

**Interfaces:**
- Produces: `screen_crop(rect: tuple[int, int, int, int], screens: list[tuple[int, int, int, int, float]]) -> tuple[int, tuple[int, int, int, int]] | None`.
  - `rect` is the game's client rect in physical px.
  - Each screen is `(x, y, logical_w, logical_h, dpr)`, as Qt reports it. Qt keeps each screen's native top-left, and its size is in logical px.
  - It returns the index of the screen holding the rect's top-left, and the crop in that screen's physical pixels. It returns `None` when no screen holds the rect.
  - `--screen` (with `--title` and `--label`, once only): grab `QGuiApplication.screens()[i].grabWindow(0)`, then copy the crop and save it as `<data dir>/grabs/<label>_screen_<W>x<H>.png`. The `QGuiApplication` must exist before `capture.find_window`, so that the process is DPI-aware.

- [ ] **Step 1: Write the failing test**

```python
def test_screen_crop_picks_the_screen_and_offsets():
    from grab import screen_crop  # tests add scripts/ to sys.path the way test_build_installer does

    screens = [(0, 0, 2048, 1152, 1.25), (2560, 0, 1920, 1080, 1.0)]
    assert screen_crop((320, 180, 1920, 1080), screens) == (0, (320, 180, 1920, 1080))
    assert screen_crop((2660, 50, 800, 600), screens) == (1, (100, 50, 800, 600))
    assert screen_crop((-5000, 0, 10, 10), screens) is None
```

- [ ] **Step 2: Run it and check that it fails**

Run: `uv run pytest tests/test_grab.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `screen_crop` and the `--screen` flag.** `--screen` with `--every` is an argparse error.

- [ ] **Step 4: Run the tests and the guard**

Run: `uv run pytest -q; uv run python scripts/check_screen_only.py`
Expected: all pass, and the guard is clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/grab.py tests/test_grab.py AGENTS.md
git commit -m "feat(scripts): grab.py --screen for README shots"
```

### Task 10: Take the shots with the owner, then add them to the README

**Files:**
- Create: `docs/screenshots/hero.png`, `docs/screenshots/path.png`, `docs/screenshots/exp.png`, `docs/screenshots/class.png`
- Modify: `README.md`

- [ ] **Step 1:** Run the redesigned app from source (`uv run maplelens`). For each shot in the spec's table (1 top picture, 2 EXP, 3 Class):
  - Tell the owner what to set up, and to make the chat box as small as possible.
  - Wait for "live", then run `uv run python scripts/grab.py --title MapleStory --label <shot> --screen`.
- [ ] **Step 2:** In the scratchpad (not the repo), blur these with `cv2.GaussianBlur` on the rectangles you pick by eye:
  - the character's name tag
  - the name in the bottom status bar
  - every other player's name
  - what's left of the chat

  Then crop: the hero at most 1600 px wide, and each tool shot to the part showing that tool (`path.png` can be cut from the hero). Each file should be under about 1 MB.
- [ ] **Step 3:** Show the owner every final image (SendUserFile). Only copy them into `docs/screenshots/` after they say yes.
- [ ] **Step 4:** Update `README.md`:
  - The hero goes right after the intro paragraph, before the status note.
  - A new `## What it does` section goes before `## The promise: screen-reading only`. It has one image per tool, each with a one-line caption.
  - Every `<img>` or `![]()` gets alt text that describes it, e.g. "MapleLens's path arrow over the character, with the route list in the box".
- [ ] **Step 5:** Run `uv run pytest tests/test_docs.py -q`. Expected: PASS.
- [ ] **Step 6: Commit**

```bash
git add docs/screenshots README.md
git commit -m "docs: screenshots of MapleLens in the game"
```
