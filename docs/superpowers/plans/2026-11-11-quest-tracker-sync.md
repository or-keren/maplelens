# Follow the game's Quest Helper: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Quests tab follows the quests in the game's Quest Helper panel: it tracks
them, hides targets that are done, and untracks a quest when it leaves the panel.

**Architecture:** A new pure reader `readers/quest_tracker.py` turns a frame into the
panel's state (`Reading.tracker`). Pure functions in `tools/quest_helper/plan.py` match a
panel block to a quest and filter its rows by progress. `QuestHelperTool.update` keeps
the tracked list in step with the panel, with a debounce, and draws the warning and ⓘ
lines.

**Tech Stack:** Python 3, numpy, OpenCV, the system OCR (`readers/ocr.py`), PySide6,
pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-quest-tracker-sync-design.md`. It builds on
`docs/superpowers/specs/2026-11-09-quest-helper-design.md`; read both.

## Global Constraints

- Screen-only (`AGENTS.md`): read pixels only; never click, send keys, or read game memory
  or files. Don't write the guard's banned names in comments or docstrings.
- Readers are pure `frame -> value` functions tested on cropped PNG fixtures, named with
  resolution and UI scale (`tracker_three_1920x1080_100.png`). Crop to the panel only. No
  character names, chat or other players' info. The owner reviews every PNG before it is
  committed.
- The quest helper depends only on readers, overlay and its own data, never on another
  tool. No new dependency.
- Never change `version` in `pyproject.toml`.
- Never untrack a quest when unsure: a minimized, covered, half-read or briefly missing
  panel changes nothing in the tracked list.
- A target's row is hidden only when a panel line was read, matched to it, and has
  have ≥ need.
- Rows and buttons keep `Qt.NoFocus`; the tab never takes focus from the game.
- Copy, exactly:
  - `"Can't read the game's Quest Helper: move it fully into view"` (yellow, `"action"` item)
  - `"Can't read all of the game's Quest Helper"` (grey ⓘ)
  - `"{name}: not in MapleLens's list yet"` (grey ⓘ)
  - `"{name}: several quests have this name"` (grey ⓘ)
- Every task ends with `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`
  and `uv run python scripts/check_screen_only.py` passing.

## Review Focus

1. **The panel covered for a moment** by the quest window or another game window, so only
   some blocks read. Expected: nothing is untracked and no progress is lost. Tests:
   Task 1 `test_tracker_block_painted_over_is_partly`, Task 3
   `test_minimized_unreadable_and_partly_change_nothing`.
2. **The panel at another sub-pixel offset** (dragged, or a different window size).
   Expected: the same reading. Test: Task 1 `test_tracker_reads_at_every_offset`.
3. **The OCR misreads a letter in a target line** ("Snail SheIl"). Expected: the line
   still matches its target. Test: Task 2 `test_line_matches_despite_one_wrong_letter`.
4. **A hand-edited or old `settings.json`** with no or bad `quests_followed`. Expected:
   it's cleaned, not a crash. Test: Task 3 `test_bad_followed_setting_is_replaced`.
5. **One tick with no panel** (a loading screen, a frame grabbed mid-redraw). Expected:
   progress isn't dropped and rows don't flash. Test: Task 3
   `test_one_missing_panel_keeps_progress`.

---

### Task 1: Panel reader (spike first)

**Files:**
- Create: `src/maplelens/readers/quest_tracker.py`
- Commit (already cut, owner-approved): the eight `tests/fixtures/screens/tracker_*.png`
- Create: the title anchor template and `tracker_font/` glyph templates in `src/maplelens/readers/templates/`
- Modify: `src/maplelens/readers/__init__.py` (`Reading.tracker`, `read_all`)
- Modify: `src/maplelens/app.py` `self_check` (load the new template, if any, as `quest_window.known_quest_names()` is loaded)
- Modify: `AGENTS.md` Layout: add `quest_tracker` to the `readers/` list
- Test: `tests/test_readers.py`

**Interfaces:**
- Produces, in `maplelens.readers.quest_tracker`:
  ```python
  PARTLY = "tracker partly read"  # found, but fewer blocks read than its count, or one garbled


  @dataclass(frozen=True)
  class TrackerLine:
      have: int
      need: int
      text: str  # the target's name, snapped to a known item or monster name, else as read


  @dataclass(frozen=True)
  class TrackerQuest:
      name: str  # snapped to the one known quest name it reads as (a cut name gives the
      # full name); else as read, a cut name keeping its trailing dots
      lines: tuple[TrackerLine, ...]


  @dataclass(frozen=True)
  class Tracker:
      count: int  # the n in "Quest Helper (n/5)"
      minimized: bool
      quests: tuple[TrackerQuest, ...]  # () when minimized; len == count when read


  def read_quest_tracker(
      frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
  ) -> Tracker | str | None: ...
  ```
  It returns None when there's no panel, `window.UNREADABLE` when the frame's edge cuts the
  panel, `PARTLY` when fewer blocks read than `count` or a block's name is empty or a
  line's numbers don't read, and a `Tracker` otherwise.
- Produces: `Reading.tracker: "Tracker | str | None" = None`, filled by `read_all` with
  `quest_tracker.read_quest_tracker(img, frame, scale)`.

- [x] **Steps 1–2 (done by the controller with the owner): fixtures**

All approved for commit, in `tests/fixtures/screens/`, native crops of the panel's corner
(the panel touches the crop's top and right edges, as in the full frame):
`tracker_one_…`, `tracker_three_…`, `tracker_min_…`, `tracker_empty_…` (1920x1080),
`tracker_a_1366x768_100.png`, and from the digit grabs: `tracker_eight_1920x1080_100.png`
(4 quests, "28 / 30"), `tracker_event_1920x1080_100.png` (4 quests, an event quest),
`tracker_dark_1920x1080_100.png` (5 quests, the panel drawn darker).

The digit grabs, for cutting glyph templates (not to be committed), are in
`%APPDATA%\MapleLens\grabs\`: `digits_001…041_1920x1080.png`,
`digits2_001…025_1920x1080.png`, `digits8_1920x1080.png`. Their target lines show every
digit 0–9 and "/" ("2 / 30" … "28 / 30" on the Red Snail Shell line). Their titles show
4/5 and 5/5; the fixtures add 0/5, 1/5 and 3/5. No title shows a 2. Other players' names
show near the panel's left edge in `digits_013`, `_025`, `_026`, `_028`: don't use them.

- [ ] **Step 3: Spike: digits by template, words by OCR**

The first spike (`task-1-report.md`) found that the system OCR can't read the panel's
numbers or "/" (0 of 27 lines exact; "0 / 1" comes back as "D 11"), and names are exact
in 20 of 27 reads. It also found that the panel is located by a "Quest Helper" title
template through `window.align`, that the layout is fixed (768 scale: block i's name on
rows 26+48i, its line from 42+48i; panel bottom ≈ 12+48n), that + and − can be told
apart, and that a warm read takes 6 ms. Its scratch scripts are in the session scratchpad
named in the report.

So, the method:
- **Numbers** ("have / need" and the title's count) are read by glyph templates in the
  panel's font, cut from the digit grabs into `src/maplelens/readers/templates/tracker_font/`
  (`0.png`…`9.png`, `slash.png`, named as `window_font` is), and matched as
  `window.read_number_text` does (score, margin, every ink column covered). The panel is
  see-through, so `read_number_text`'s flat-background check doesn't hold: it needs its own
  check, or an ink mask first. Reuse what `window.py` offers; add a sibling only for the
  difference.
- **The count:** read the title's digit with the same templates if they fit its font
  (check on 0, 1, 3, 4, 5). If the title uses another font, the count is the number of
  blocks the panel's height holds (its bottom edge at ≈ 12+48n), and a panel whose bottom
  edge can't be found is `PARTLY`.
- **Words** (names, and the target text after the numbers) by OCR, as now. Names are
  snapped to `quest_window.known_quest_names()`: `map_name.snap_title` for a whole name,
  and for a cut name (ending in dots) the one known name it starts, or else the one it
  snaps to by `snap_title` against the known names cut to the same length. Target text is
  snapped with `snap_title` to the item and monster names in `data/quests.json`.

Run it on every fixture at the native offsets `test_stat_reads_at_every_offset` uses, and
time a warm read.

**Stop rule:** if a number misreads, or a name or target snaps to the wrong known name
(or to none, for a name in the data) on any fixture and offset, or a warm read takes more
than 50 ms, stop and report with the measurements.

- [ ] **Step 4: Write the failing tests in `tests/test_readers.py`**

```python
from maplelens.readers.quest_tracker import (
    PARTLY,
    Tracker,
    TrackerLine,
    TrackerQuest,
    read_quest_tracker,
)

RAINBOW = "A rainbow snail shell that makes wishes come true!?"
ARWEN = TrackerQuest("Arwen and the Glass Shoe", (TrackerLine(0, 1, "Arwen's Glass Shoe"),))
FILING = TrackerQuest("The Filing Error", (TrackerLine(0, 25, "Torn Ledger Pages"),))
SHELL = TrackerQuest(RAINBOW, (TrackerLine(0, 1, "Rainbow-colored Snail Shell"),))
EVENT = TrackerQuest("[Event] The Journey Begins", (TrackerLine(0, 30, "Maple Leaf"),))


def donating(have):
    return TrackerQuest("Donating to Kerning City", (TrackerLine(have, 30, "Red Snail Shell"),))


EXPECTED_TRACKER = {
    "tracker_one_1920x1080_100.png": Tracker(1, False, (FILING,)),
    "tracker_three_1920x1080_100.png": Tracker(3, False, (FILING, SHELL, donating(0))),
    "tracker_min_1920x1080_100.png": Tracker(3, True, ()),
    "tracker_empty_1920x1080_100.png": Tracker(0, False, ()),
    "tracker_a_1366x768_100.png": Tracker(3, False, (ARWEN, FILING, SHELL)),
    "tracker_eight_1920x1080_100.png": Tracker(4, False, (ARWEN, FILING, SHELL, donating(28))),
    "tracker_event_1920x1080_100.png": Tracker(4, False, (ARWEN, FILING, SHELL, EVENT)),
    "tracker_dark_1920x1080_100.png": Tracker(
        5, False, (ARWEN, FILING, SHELL, donating(10), EVENT)
    ),
}


@pytest.mark.parametrize("name", sorted(EXPECTED_TRACKER))
def test_read_quest_tracker(name):
    assert read_quest_tracker(*_window_args(name)) == EXPECTED_TRACKER[name]


@pytest.mark.parametrize(
    "name",
    [
        "quest_progress_1920x1080_100.png",
        "stat_a_1920x1080_100.png",
        "title_ellinia_1920x1080_100.png",
        "minimap_a_1920x1080_100.png",
    ],
)
def test_no_tracker(name):
    assert read_quest_tracker(*_window_args(name)) is None


def test_tracker_cut_by_the_frame_edge_is_unreadable():
    native = screen("tracker_three_1920x1080_100.png")[:, :-120]  # the right edge cuts it
    scale = 1080 / 768
    assert read_quest_tracker(_scaled(native, scale), native, scale) == UNREADABLE


def test_tracker_block_painted_over_is_partly():
    """A block covered (here: painted with the panel's own colour) reads fewer than n."""
    # paint the third block's rows (its name and line) of tracker_three with the panel's
    # background colour measured in Step 3; the title still says 3/5
    ...
    assert read_quest_tracker(_scaled(native, scale), native, scale) == PARTLY


def test_tracker_reads_at_every_offset():  # native drops 0-5: to ceil(2 * 1080/768) = 3 frame px
    """Dropping native rows and columns moves the panel to another sub-pixel offset."""
    # as test_stat_reads_at_every_offset, on tracker_three and tracker_eight (1920):
    # every offset reads EXPECTED_TRACKER's value
```

If "Maple Leaf" (not in our data, so not snapped) doesn't read exactly at every offset,
compare EVENT's target text loosely in the tests (its quest is never matched anyway) and
say so in the report. Fill in the painted rows and the offset loop from what Step 3
measured. Those two tests are the only bodies left open.

- [ ] **Step 5: Run them to see them fail**

Run: `uv run pytest tests/test_readers.py -k tracker -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maplelens.readers.quest_tracker'`

- [ ] **Step 6: Implement `read_quest_tracker` in `src/maplelens/readers/quest_tracker.py`**

Use the method Step 3 settled. A title whose minimize button shows − is open; + means
minimized, except with a count of 0: the empty panel shows a + too (`tracker_empty_…`), and
0/5 is always `Tracker(0, False, ())` so the last quest leaving untracks it. Add
`Reading.tracker` and fill it in `read_all`. Load the new templates in `self_check` (if
`glyphs.load_all()` doesn't already pick them up).
Add `quest_tracker` to `AGENTS.md`'s readers list.

- [ ] **Step 7: Run the tests to see them pass**

Run: `uv run pytest tests/test_readers.py -v`
Expected: PASS, the quest window and every other reader test included.

- [ ] **Step 8: Run the full checks, then commit**

Run: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`,
`uv run python scripts/check_screen_only.py`. All pass.

```bash
git add src/maplelens/readers/quest_tracker.py src/maplelens/readers/templates docs/superpowers src/maplelens/readers/__init__.py src/maplelens/app.py AGENTS.md tests/test_readers.py tests/fixtures/screens/tracker_*.png
git commit -m "feat(readers): read the game's Quest Helper panel"
```

---

### Task 2: Match a panel block to a quest, and rows by progress

**Files:**
- Modify: `src/maplelens/tools/quest_helper/plan.py`
- Test: `tests/test_quest_plan.py`

**Interfaces:**
- Consumes: `TrackerQuest`, `TrackerLine` (Task 1); `map_name.snap_title(text, names) -> str`
  (existing, `maplelens.readers.map_name`).
- Produces, in `maplelens.tools.quest_helper.plan`:
  ```python
  UNKNOWN = "unknown"  # the name is no single quest in the data
  SEVERAL = "several"  # several quests fit the name and their targets can't settle it
  Part = tuple[str, int]  # ("mob", monster id) or ("item", item id)


  def match_block(data: QuestData, block: TrackerQuest) -> int | str: ...
  def done_parts(
      data: QuestData, quest: Quest, lines: tuple[TrackerLine, ...]
  ) -> frozenset[Part]: ...
  def targets(
      data, quest, *, giver: bool, hops: Hops, done: frozenset[Part] = frozenset()
  ) -> list[Target]: ...
  ```

Rules (from the spec):
- `match_block`: a name ending in "." or "…" is cut: candidates are the quests whose name
  starts with it, without its trailing dots. Otherwise the name is snapped with
  `snap_title(name, {q.name for q in data.quests.values()})`, and candidates are the quests
  with that name. With no candidates, the answer is `UNKNOWN`. With one candidate, that's
  its id. With several, keep those every line of the block fits. A line fits a quest when
  it matches one of the quest's targets (its monsters, and its items that aren't start
  items) by name and by need. The name is snapped with `snap_title` to that quest's
  target names. One left → its id. Otherwise → `SEVERAL`.
- `done_parts`: the parts whose matched line has `have >= need`. A line that matches no
  target is ignored.
- `targets(..., done=)`: a done item gets no row and leaves the monster row's title. A
  done monster leaves its own row's title, and its items then show their full names
  ("Snail Shell ×10", not "Shell ×10"). A monster row with nothing left goes. The giver and
  hand-in rows are never filtered.

- [ ] **Step 1: Write the failing tests in `tests/test_quest_plan.py`**

Use the file's `data()` and `quest()` helpers. `TL = TrackerLine`, `TQ = TrackerQuest`.

```python
def test_match_block_by_name():
    d = data(quest(id=7, name="The Filing Error"))
    assert match_block(d, TQ("The Filing Error", ())) == 7
    assert match_block(d, TQ("The Fiiing Error", ())) == 7  # one letter off snaps
    assert match_block(d, TQ("Nobody's Quest", ())) == UNKNOWN


def test_cut_name_matches_by_prefix():
    d = data(quest(id=7, name="A rainbow snail shell that makes wishes come true!?"))
    assert match_block(d, TQ("A rainbow snail shell that makes...", ())) == 7
    assert match_block(d, TQ("A rainbow snail shell that makes…", ())) == 7


def test_shared_name_told_apart_by_lines():
    a = quest(id=7, name="Donating", items=((10, 30),))
    b = quest(id=8, name="Donating", items=((11, 30),))
    d = replace(data(a), quests={7: a, 8: b})
    assert match_block(d, TQ("Donating", (TL(0, 30, "Slime Gel"),))) == 8
    assert match_block(d, TQ("Donating", ())) == SEVERAL


def test_same_targets_are_several():
    a = quest(id=7, name="Home", taker=1)
    b = quest(id=8, name="Home", taker=2)
    d = replace(data(a), quests={7: a, 8: b})
    assert match_block(d, TQ("Home", ())) == SEVERAL


def test_line_matches_despite_one_wrong_letter():
    q = quest(mobs=((1, 20),), items=((10, 10),))
    assert done_parts(data(q), q, (TL(10, 10, "Jr. Necki SkIn"),)) == {("item", 10)}


def test_done_parts_need_have_at_least_need():
    q = quest(mobs=((1, 20),), items=((10, 10),))
    lines = (TL(20, 20, "Jr. Necki"), TL(9, 10, "Jr. Necki Skin"))
    assert done_parts(data(q), q, lines) == {("mob", 1)}
    assert done_parts(data(q), q, (TL(5, 7, "Jr. Necki"),)) == frozenset()  # need differs


def test_done_monster_leaves_its_items_with_full_names():
    q = quest(mobs=((1, 20),), items=((10, 10),), taker=1)
    rows = targets(data(q), q, giver=False, hops=NONE, done=frozenset({("mob", 1)}))
    assert [r.title for r in rows] == [f"Jr. Necki Skin {TIMES}10", "Luke"]


def test_all_done_leaves_only_the_hand_in():
    q = quest(mobs=((1, 20), (2, 5)), items=((10, 10), (12, 1)), taker=1)
    done = frozenset({("mob", 1), ("mob", 2), ("item", 10), ("item", 12)})
    assert [r.title for r in targets(data(q), q, giver=False, hops=NONE, done=done)] == ["Luke"]


def test_no_progress_is_todays_rows():
    q = quest(mobs=((1, 20),), items=((10, 10),), taker=1)
    d = data(q)
    assert targets(d, q, giver=False, hops=NONE, done=frozenset()) == targets(
        d, q, giver=False, hops=NONE
    )
```

(Import `replace` from `dataclasses`, `TIMES`, `UNKNOWN`, `SEVERAL`, `match_block` and
`done_parts` from `plan`, and the tracker types from Task 1.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_quest_plan.py -v`
Expected: FAIL with `ImportError: cannot import name 'match_block'`

- [ ] **Step 3: Implement `match_block`, `done_parts` and `targets(..., done=)` in `plan.py`**

Follow the rules above. A private helper `_part(data, quest, line) -> Part | None` (the
target a line names) serves both `match_block` and `done_parts`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_quest_plan.py tests/test_quest_ui.py -v`
Expected: PASS (the tab's tests are unchanged by the new default `done`).

- [ ] **Step 5: Run the full checks, then commit**

```bash
git add src/maplelens/tools/quest_helper/plan.py tests/test_quest_plan.py
git commit -m "feat(quests): match the game's Quest Helper blocks and hide done targets"
```

---

### Task 3: The Quests tab follows the panel

**Files:**
- Modify: `src/maplelens/tools/quest_helper/ui.py`
- Modify: `src/maplelens/store.py` (`DEFAULTS["quests_followed"] = []`, commented
  `# quest ids seen in the game's Quest Helper; they leave with it`)
- Modify: `README.md` (the Quest helper paragraph, line ~24: a sentence saying quests
  followed in the game's Quest Helper are tracked by themselves, and their done targets
  drop off; the feature line at ~160 to match)
- Test: `tests/test_quest_ui.py`

**Interfaces:**
- Consumes: `read_quest_tracker`'s values, `PARTLY`, `Tracker*` (Task 1); `match_block`,
  `done_parts`, `UNKNOWN`, `SEVERAL`, `targets(..., done=)` (Task 2).
- Produces: `settings["quests_followed"]: list[int]`, and the copy constants in `ui.py`:
  `UNREAD_PANEL`, `PARTLY_PANEL`, `NOT_LISTED_Q`, `SEVERAL_Q` (the Global Constraints'
  copy, in that order).

Behaviour of `QuestHelperTool.update` with `t = r.tracker` (the spec's states table):

| `t` | Lists | Progress (in memory) | Lines |
|---|---|---|---|
| `Tracker`, not minimized | each block: `match_block` → id: append to `quests_tracked` and `quests_followed` if absent, progress[id] = `done_parts`, missing count reset. `UNKNOWN` / `SEVERAL` → an ⓘ note. Each followed id not in this read: missing += 1; at 2, remove it from both lists, from `quests_expanded`, and from progress | as read | the notes |
| minimized `Tracker`, `UNREADABLE`, `PARTLY` | unchanged; missing counts neither grow nor reset | kept | `UNREADABLE`: yellow `UNREAD_PANEL`; `PARTLY`: grey `PARTLY_PANEL`; else none |
| None, 2 readings in a row | unchanged | cleared | none |
| None, the first reading | unchanged | kept | the previous ones |

Call `on_settings_changed` only when a list changed. `_untrack` (the ×) also removes the
id from `quests_followed`. `_clean` cleans `quests_followed` as `quests_tracked` and keeps
only ids that are also tracked. Rows of a quest come from
`targets(..., done=progress.get(id, frozenset()))`, in the top part too. The warning and
notes go between the top part and the "Tracking" label, as `("action", …)` and
`("info", …)` items. A newly followed quest doesn't change `quests_expanded`.

- [ ] **Step 1: Write the failing tests in `tests/test_quest_ui.py`**

Extend `R` to `R(quest=None, tracker=None)`. Helpers:

```python
SNAIL, SHELL = "Snail", "Snail Shell"  # 1001's targets: Snail x3, Snail Shell x10


def panel(*blocks):
    return R(tracker=Tracker(len(blocks), False, tuple(blocks)))


def mirror(snails=0, shells=0):
    return TrackerQuest(MIRROR, (TrackerLine(snails, 3, SNAIL), TrackerLine(shells, 10, SHELL)))
```

Tests (assertions are on `tool.settings`, `tool.calls`, `texts(tool)` and the titles of
`rows(tool)`, the way the existing tests use them):

- `test_panel_quest_is_tracked_and_saved`: `make()`, update `panel(mirror())`, then
  `quests_tracked == [1001]`, `quests_followed == [1001]`, `calls["changed"] >= 1`, and
  `MIRROR` is in `texts`.
- `test_done_targets_drop_off`: `make(tracked=[1001], expanded=1001)`, then
  `panel(mirror(snails=3, shells=2))`. The rows' titles are `[f"Snail Shell {TIMES}10", "Heena"]`
  (no giver row: a followed quest is taken).
- `test_all_done_shows_only_hand_in`: `panel(mirror(3, 10))`. The titles are `["Heena"]`.
- `test_leaving_the_panel_untracks_after_two_reads`: follow it, then one `panel()` (0/5):
  still tracked. A second `panel()`: `quests_tracked == []`, `quests_followed == []`.
- `test_track_button_quest_stays`: `make(tracked=[SNAILS])`, two `panel()` reads, and
  `quests_tracked == [SNAILS]`.
- `test_minimized_unreadable_and_partly_change_nothing`: follow with
  `panel(mirror(3, 2))`. Then three readings each of `R(tracker=Tracker(0, True, ()))`,
  `R(tracker=UNREADABLE)` and `R(tracker=PARTLY)`, with `expanded=1001`. Still tracked,
  and the rows are still `[f"Snail Shell {TIMES}10", "Heena"]`. A following `panel()` doesn't
  untrack on its own: it is the first of two.
- `test_panel_warnings`: `R(tracker=UNREADABLE)` shows `UNREAD_PANEL` in `ACCENT` (as
  `test_unreadable_window_is_yellow_and_name_unreadable_is_grey` checks the colour).
  `R(tracker=PARTLY)` shows `PARTLY_PANEL` as an `InfoLine`.
- `test_unknown_and_several_blocks_are_notes`:
  `panel(TrackerQuest("Nobody's Quest", ()), TrackerQuest(SHARED, ()), mirror())`. The
  texts contain `"Nobody's Quest: not in MapleLens's list yet"` and
  `f"{SHARED}: several quests have this name"`, with no `PARTLY_PANEL` or `UNREAD_PANEL`,
  and `quests_tracked == [1001]`.
- `test_no_panel_restores_todays_rows`: follow with `panel(mirror(3, 2))`, then two `R()`.
  The rows are back to today's: `[f"Snail {TIMES}3 · Shell {TIMES}10", "Heena"]`. Still tracked.
- `test_one_missing_panel_keeps_progress`: follow with `panel(mirror(3, 2))`, then one
  `R()`. The rows are still `[f"Snail Shell {TIMES}10", "Heena"]`.
- `test_close_on_a_followed_quest_comes_back`: follow, click the header's × (via
  `button(tool, CLOSE)`). It's gone from both lists. `panel(mirror())` again → tracked
  again.
- `test_open_quest_window_uses_progress`: `panel(mirror(3, 2))` and `opened(MIRROR, True)`
  in the same `Reading`. The top part's rows are `[f"Snail Shell {TIMES}10", "Heena"]`.
- `test_bad_followed_setting_is_replaced`: build with settings `quests_followed="x"`, and
  separately `[1001, 999999]` with `tracked=[]`. Each becomes `[]`.

(`TIMES` is `plan.TIMES`, the multiplication sign.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_quest_ui.py -v`
Expected: the new tests FAIL (`KeyError: 'quests_followed'` or wrong rows); the old ones
pass.

- [ ] **Step 3: Implement the table above in `ui.py`, and the default in `store.py`**

Keep state on the tool: `self._progress: dict[int, frozenset[Part]]`,
`self._missing: dict[int, int]`, `self._notes: list[str]`,
`self._panel_line: tuple[str, str] | None` (the warning item), and
`self._no_panel: int` (readings in a row with `t is None`). `_items` reads them. The
existing `_render` redraws only when the items changed.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_quest_ui.py tests/test_app.py tests/test_store.py -v`
Expected: PASS.

- [ ] **Step 5: Update `README.md`, run the full checks, commit**

```bash
git add src/maplelens/tools/quest_helper/ui.py src/maplelens/store.py README.md tests/test_quest_ui.py
git commit -m "feat(quests): follow the game's Quest Helper (#65)"
```

---

### Task 4: Check it in the game with the owner

**Files:** none, unless a fix is needed (then fix it in the task that owns the code, test
first).

- [ ] **Step 1: Run MapleLens from the branch** (`uv run maplelens`) with the game windowed
  or borderless.
- [ ] **Step 2: Walk the spec's "Done means" 1–6 with the owner**, one at a time, writing
  down what each showed. Only the owner can follow, finish, hand in, minimize and move
  quests in the game. MapleLens and the agent only watch.
- [ ] **Step 3: Report.** Every item passed, or which one failed and what it showed.
  Close #65 from the PR description ("Closes #65").
