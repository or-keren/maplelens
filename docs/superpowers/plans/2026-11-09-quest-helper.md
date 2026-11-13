# Quest Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Quests tab. It shows the quest open in the game with one row per place to go, keeps tracked quests, and starts the path arrow to a monster's best map or right to an NPC. The box switches to the tab while a quest window is open.

**Architecture:**
- A new pure reader, `readers/quest_window.py`, joins `read_all`.
- A new tool, `tools/quest_helper/`, has three modules: `data.py` loads our `quests.json`, `plan.py` builds the rows without Qt, and `ui.py` is the tab.
- The path arrow learns NPC targets: `Trip(at=…)` and `go(map_id, at, label)`.
- `app.py` wires the tools together with callables (go, heading, stop, hops) and adds `QuestFocus`, the automatic tab switch. Tools never import each other.

**Tech Stack:** Python 3.12, PySide6, OpenCV + numpy, the system OCR (`readers/ocr.py`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-09-quest-helper-design.md`

## Global Constraints

- Screen-only (`AGENTS.md`). The reader only reads pixels. Nothing sends input or reads game memory or files. Run `uv run python scripts/check_screen_only.py` after every task.
- No new dependency. Never write the guard's banned module or Win32 names in comments under `src/` or `scripts/`.
- Never change `version` in `pyproject.toml`.
- Readers are pure `screenshot -> value` functions, tested on PNG fixtures. They return `None` or `UNREADABLE`, never a wrong value.
- `tools/quest_helper/` imports only `readers`, `overlay`, `store` and its own modules. Like `class_helper/data.py`, it reads `data/maps.json` directly. Everything it needs from the path arrow comes in as a callable.
- Fixtures: crop them to the quest window. Paint over character names, chat and other players. Filenames carry resolution and scale, e.g. `quest_available_1366x768_100.png`. The owner reviews every PNG before commit.
- **Data fetching** follows the owner's permission (2026-11-09):
  - The agent may fetch from meowdb with an honest User-Agent naming MapleLens, at most one request every 2 s, and stops on 403/429.
  - Prefer the OSMS v1 files for anything they have.
  - The converter and the downloaded files stay outside the repo.
  - `quests.json` holds facts only (ids, names, counts, positions), no site wording.
- Rows and buttons keep `Qt.NoFocus`. Nothing takes keyboard focus from the game.
- Every tab has the same fixed width, `TAB_W`. The box gets one new, wider width that fits four tabs plus the Path dot at today's 14 px spacing.
- Fixed strings, exactly:
  - "Open a quest in the game to see where to go"
  - "This quest isn't in MapleLens's list yet"
  - "Where to get it: unknown"
  - "Where it spawns: unknown"
  - "Not in the map list yet"
  - "Track"
  - "Tracked ✓"
  - "Stop"
  - "Open in the game"
  - "Tracking · {n} quests"
  - "Going · {n} maps away"
  - "gives the quest"
  - "hand in"
  - "also for {quest}"
  - "{npc} is on this map"
- The near-tie fraction `NEAR_TIE = 0.8` and the arrival distance `NPC_NEAR` are named constants.

## Calls made in this plan (owner to check)

- **Quest names shared by several quests** (the job advancement ones, one per class, e.g. "Test of Qualification") show the grey line "Several quests have this name; MapleLens can't tell which yet". They never show one class's targets for another. If the spike finds the quest window shows its NPC's name, Task 6 may tell them apart that way instead.
- **An NPC on several maps** goes to the one with the fewest map changes from where you are. If where you are isn't known, it goes to the first in the data.
- **NPC world positions** in `quests.json` use the same coordinates as `maps.json`'s NPC markers, and a test checks that. OSMS's map NPC x/y are in another frame (map 1's Heena is (319, 665) there, but (-46, 280) in ours). So positions come from meowdb, as `maps.json`'s did.
- **One misread doesn't switch tabs.** The box changes tab only after two readings in a row agree on the quest window being open or closed, as the path tool does with map names.
- **"Can't read the quest window: move it fully into view" is grey**, the same as the Class tab's line for the stat window, though the spec allows yellow for a one-action fix. It keeps the two tabs consistent.
- **A row click counts as touching the box**, like a tab click, Track or ×. So does a press anywhere on the box. Clicks in the ••• menu don't count.

## Review Focus

1. **The quest window misreads for one tick while it's still open.** The tab keeps showing the quest, and the box doesn't switch back and forth. Tests: Task 8 `test_one_missed_reading_keeps_the_tab`, Task 7 `test_one_missed_reading_keeps_the_open_quest`.
2. **A shared quest name** (job advancement). It shows the grey line, never another class's rows. Test: Task 3 `test_shared_name_finds_nothing`.
3. **A tracked quest id the data no longer has** (after a data update). It's dropped when settings load, without a crash, and the rest stay. Test: Task 7 `test_unknown_tracked_id_is_dropped`.
4. **A row clicked before MapleLens knows where you are.** The path tool only picks the map, as `go` does today. No row is outlined and nothing raises. Test: Task 7 `test_row_click_before_map_known_outlines_nothing`.
5. **The game closing or minimizing while the quest window is open** (readings become `None`). This counts as the window closing: the box goes back unless it was touched. Test: Task 8 `test_no_reading_counts_as_closed`.

---

### Task 1: Spike: the quest window (owner grabs, builder reads; gate)

**Files:**
- Create: `tests/fixtures/screens/quest_*.png` (owner's grabs, cropped)
- Modify: this plan, Task 6 (the findings)

- [ ] **Step 1: Owner grabs.** With `uv run python scripts/grab.py --label <name>`, grab the quest window showing:
  - an **available** (not yet taken) quest, at 1366x768 and at 1920x1080;
  - an **in-progress** quest, at both sizes;
  - one quest window **half off screen**.

  Crop each to the quest window and paint over names and chat. The owner reviews them before they're committed.
- [ ] **Step 2: Find the name.** Find a fixed anchor (title bar art, a label) with `glyphs.find_anchor`, the name's box relative to it, and its ink colours.
- [ ] **Step 3: Read the name.** Use `ocr.read_lines` on all four grabs. It must read the exact name on each, or snap to it with `map_name.snap_title`.
- [ ] **Step 4: Taken or not.** Find what tells taken from not-taken (a tab, a button, a label), if anything does. Also note whether the window shows the quest's NPC name.
- [ ] **Step 5: Gate.** Write the findings into Task 6 (anchor name, offsets, ink, taken signal). **If the name can't be read on all four grabs, stop and bring it to the owner.** Search by name is the fallback to discuss. Tasks 2–5 don't depend on this and may run meanwhile.
- [ ] **Step 6: Commit** the fixtures and the plan edit: `test: quest window fixtures and reader findings`.

### Task 2: `quests.json` and its loader

**Files:**
- Create: `src/maplelens/data/quests.json`
- Create: `src/maplelens/tools/quest_helper/__init__.py` (empty), `src/maplelens/tools/quest_helper/data.py`
- Create: `tests/fixtures/quests_small.json`, `tests/test_quest_data.py`

**Interfaces:**
- Produces, in `quest_helper/data.py`:
  - `DATA` (data/quests.json), `MAPS` (data/maps.json)
  - `Npc(id: int, name: str, places: tuple[tuple[str, int, int], ...])`: each place is (map id, world x, world y)
  - `Mob(id: int, name: str, spawns: dict[str, int])`: map id -> spawn count
  - `Item(id: int, name: str, drops: tuple[int, ...], shops: tuple[int, ...])`: monster ids that drop it, and NPC ids that sell it
  - `Quest(id: int, name: str, giver: int | None, taker: int | None, mobs: tuple[tuple[int, int], ...], items: tuple[tuple[int, int], ...], start_items: tuple[int, ...])`: mobs and items as (id, count), in the quest's order
  - `QuestData(quests: dict[int, Quest], npcs: dict[int, Npc], mobs: dict[int, Mob], items: dict[int, Item], map_names: dict[str, str])`: map id -> the map's name, from maps.json
  - `load(path: Path = DATA, maps: Path = MAPS) -> QuestData`. All dataclasses are frozen. `load` is `@cache`d for the default paths only.

File shape (JSON object keys are strings; map ids are maps.json's 9-digit strings):

```json
{"quests": [{"id": 1001, "name": "…", "giver": 2, "taker": 1, "mobs": [[100100, 20]],
             "items": [[4000000, 10]], "start_items": [4031000]}],
 "npcs":  {"2": {"name": "Sera", "places": [["000000001", -46, 280]]}},
 "mobs":  {"100100": {"name": "…", "spawns": {"104000100": 12}}},
 "items": {"4000000": {"name": "…", "drops": [100100], "shops": []}}}
```

- [ ] **Step 1: Write the failing tests** in `tests/test_quest_data.py`:
  - `test_loads_small_fixture`: `load(SMALL, maps=<maps.json>)` gives the fixture's quest with tuples as above. `map_names["000000001"] == "Mushroom Town - West Entrance"`.
  - `test_every_reference_resolves`: on the real file, every quest's giver, taker, mob, item and start item id is a key in `npcs`, `mobs` or `items`. Every item's drops are in `mobs` and its shops in `npcs`.
  - `test_npc_places_are_map_markers`: every NPC place's map is in maps.json, and its `(x, y)` is one of that map's `npcs` entries in maps.json.
  - `test_kept_quests`: more than 200 quests; none is an event, citizenship or crafting quest. Assert that no name contains "Citizen" and that quest 1001's start items are `(4031000,)`. Also assert quest 1001's giver is 2 (Sera) and its taker is 1 (Heena). If meowdb says otherwise, stop and ask.
  - `test_every_quest_has_somewhere_to_go`: each quest has a giver, a taker, a mob or an item.
- [ ] **Step 2: Run** `uv run pytest tests/test_quest_data.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Convert.** Write the one-off converter in the scratchpad, not the repo.
  - **From OSMS v1:** quests (name, `npc_id` giver, requirements of type mob/item, `start_items`) and monster spawns (`spawns` -> map id `str(id).zfill(9)`, count).
  - **From meowdb:** hand-in NPCs, item drops and shops, and NPC world positions (the `npcs[].x/y` of each meowdb map record, as for maps.json).
  - Keep Victoria Island and Maple Island. Leave out event quests (citizenship and crafting went in on 2026-11-09, owner), and keep only the entries some kept quest refers to.
  - Write `quests.json` compact, keys sorted.
- [ ] **Step 4: Implement `load`** and the dataclasses in `data.py`.
- [ ] **Step 5: Run** `uv run pytest tests/test_quest_data.py -v`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(quests): quest data and loader`.

### Task 3: Quest rows (pure)

**Files:**
- Create: `src/maplelens/tools/quest_helper/plan.py`
- Test: `tests/test_quest_plan.py` (uses `tests/fixtures/quests_small.json`; extend the fixture as the tests need)

**Interfaces:**
- Consumes: Task 2's `QuestData`, `Quest`, `Mob`, `Npc`.
- Produces, in `plan.py`:
  - `NEAR_TIE = 0.8`
  - `Target(title: str, sub: str, map_id: str | None, at: tuple[int, int] | None, npc: str | None, info: bool)`, frozen. `map_id is None` means it isn't clickable. `info` means `sub` is a grey ⓘ line. `npc` is the NPC's name, for the arrival line.
  - `Hops = Callable[[str], int | None]`: map changes from where the player is; None when unknown or no route
  - `best_map(spawns: dict[str, int], listed: Collection[str], hops: Hops) -> str | None`
  - `npc_place(npc: Npc, listed: Collection[str], hops: Hops) -> tuple[str, int, int] | None`
  - `find_quest(data: QuestData, name: str) -> Quest | None`: None when no quest has that name **or several do**. `shared_name(data, name) -> bool` tells the two apart.
  - `targets(data: QuestData, quest: Quest, *, giver: bool, hops: Hops) -> list[Target]`
  - `show_giver(taken: bool | None, tracked: bool) -> bool`: `not taken` when taken is known, else `not tracked`
  - `also_for(map_id: str, others: list[tuple[str, list[Target]]]) -> list[str]`: names of the other quests with a clickable row to `map_id`

Row rules (from the spec; exact strings in Global Constraints; `×` is U+00D7):

| Case | title | sub | map_id / at |
|---|---|---|---|
| Monster with its quest items | `Jr. Necki ×20 · Skin ×10` | best map's name | best map / None |
| Item from another monster | `Item ×n` | `<Monster> · <map>` | that monster's best map |
| Item from a shop | `Item ×n` | `<NPC> · <map>` | NPC's map / NPC's x, y |
| Hand-in NPC | `Luke` | `<map> · hand in` | NPC's map / x, y |
| Giver NPC | `Luke` | `<map> · gives the quest` | NPC's map / x, y |
| Giver is taker, both shown | `Luke` | `<map>` | NPC's map / x, y |

- **Item source order:** a drop from a monster already on the quest, then another drop, then a shop. Among several dropping monsters, use the one whose best map has the most spawns.
- **Short item names:** an item's name loses a leading `<monster name> ` when it shares a row with that monster.
- **Row order:** giver, monsters in the quest's order, items, hand-in.
- **Start items** get no row.

- [ ] **Step 1: Write the failing tests:**
  - `test_best_map_most_spawns`: `best_map({"a": 10, "b": 4}, {"a", "b"}, lambda m: None) == "a"`
  - `test_near_tie_goes_to_fewer_hops`: `best_map({"a": 10, "b": 8}, {"a","b"}, {"a": 3, "b": 1}.get) == "b"`, and with `{"a": 10, "b": 7}` the answer is `"a"`
  - `test_best_map_skips_unlisted`: `best_map({"x": 50, "a": 2}, {"a"}, …) == "a"`, and `best_map({"x": 5}, {"a"}, …) is None`
  - `test_monster_row_carries_its_items`: the title is `"Jr. Necki ×20 · Skin ×10"`, `sub` is the map's name, `at is None`
  - `test_other_drop_and_shop_rows`: the sub-lines are `"<Monster> · <map>"` and `"<NPC> · <map>"`. The shop row's `at` is the NPC's x, y.
  - `test_unknown_cases_are_info_rows`: an item with no source gives `Target(…, sub="Where to get it: unknown", map_id=None, info=True)`. A monster with no spawns gives "Where it spawns: unknown". A best map that isn't listed gives "Not in the map list yet".
  - `test_start_items_get_no_row`
  - `test_row_order_and_giver`: with `giver=True`, the rows are giver, monsters, items, hand-in. With the same NPC as giver and taker, there's one row whose sub is the map name.
  - `test_show_giver`: `show_giver(True, False) is False`, `show_giver(False, True) is True`, `show_giver(None, False) is True`, `show_giver(None, True) is False`
  - `test_shared_name_finds_nothing`: two fixture quests named "Test of Qualification": `find_quest` is None and `shared_name` is True. An unknown name: None and False.
  - `test_also_for`: `also_for("a", [("Q2", [Target(…map_id="a"…)]), ("Q3", [])]) == ["Q2"]`
  - `test_npc_place_fewest_hops`
- [ ] **Step 2: Run** `uv run pytest tests/test_quest_plan.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `plan.py`. `best_map`: among listed maps, the near-ties are those with `count >= NEAR_TIE * top`. Pick by `(hops or inf, -count, map_id)`.
- [ ] **Step 4: Run** the tests again. Expected: PASS.
- [ ] **Step 5: Commit** `feat(quests): quest rows`.

### Task 4: Path arrow: NPC targets

**Files:**
- Modify: `src/maplelens/tools/path_arrow/route.py` (`Trip`)
- Modify: `src/maplelens/tools/path_arrow/ui.py` (`go`, `_settle`, `_render`, `_on_stop`)
- Test: `tests/test_route.py`, `tests/test_path_ui.py`

**Interfaces:**
- Produces:
  - `Trip(maps, start, goal, taxi, at: tuple[int, int] | None = None)`. `Trip.at` is the NPC's world spot. `arrived` keeps meaning "on the goal map". On arrival, `target(player)` returns `at` (None without one).
  - `PathArrowTool.go(map_id: str, at: tuple[int, int] | None = None, label: str | None = None) -> None`. `label` is the NPC's name, used in the header and arrival line. The Class tab's `go(map_id)` calls are unchanged.
  - `PathArrowTool.heading() -> tuple[str, tuple[int, int] | None, int] | None`: (goal map, at, maps left = `len(steps) - 1 - index`) while a trip runs.
  - `PathArrowTool.stop() -> None` (today's `_on_stop`, public).
  - `PathArrowTool.hops(map_id: str) -> int | None`: `len(plan(...)) - 1` from the confirmed map with the taxi box's setting. None when the map is unknown or there's no route.
  - `NPC_NEAR` in `path_arrow/ui.py`: world px. Start at 60 and tune it in Task 9.
  - `ON_MAP = "{} is on this map"`

Arrival rule for a trip with `at`, each tick, once `trip.arrived`:
- The player is within `NPC_NEAR` of `at`: "Arrived at {label}" for `ARRIVED_S`, and the trip ends.
- The map has no minimap, or the minimap is open but `can_place` is false: the trip ends with the `ON_MAP` line.
- Otherwise the trip keeps running and the arrow points at `at`. A closed minimap asks for it, as today.

A trip without `at` ends on reaching the map, as today.

- [ ] **Step 1: Write the failing tests:**
  - `test_route.py::test_target_is_the_npc_on_arrival`: a 2-map trip with `at=(50, 60)`. After `on_map(goal)`, `arrived` is true and `target((0, 0)) == (50, 60)`. Without `at`, `target` is None.
  - `test_path_ui.py::test_npc_trip_points_then_arrives`: `go(goal, (x, y), "Luke")`. On the goal map with the player far away, the trip still runs and the arrow shows. Move the player within `NPC_NEAR`: the header is `"Arrived at Luke"` and `running` is False.
  - `test_npc_trip_without_minimap_arrives_on_map`: the goal map has `minimap=None`. On reaching it, the header is `ON_MAP.format("Luke")`.
  - `test_heading_stop_hops`: `heading()` is `(goal, (x, y), n)` while running and None after `stop()`. `hops(goal)` equals the plan's length minus 1. `hops` is None before the map is known.
- [ ] **Step 2: Run** `uv run pytest tests/test_route.py tests/test_path_ui.py -v`. Expected: the new tests fail.
- [ ] **Step 3: Implement.** Keep `_arrived` as the full header text plus its time, so one line covers "Arrived at …" and `ON_MAP`.
- [ ] **Step 4: Run** the whole suite: `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(path): lead to an NPC on the goal map`.

### Task 5: Overlay: shared `Row`, the wider box, `current` and `touches`

**Files:**
- Modify: `src/maplelens/overlay.py` (`Row` moves here; `TAB_W`; `Box.current`, `Box.touches`)
- Modify: `src/maplelens/tools/class_helper/ui.py` (import `Row` from overlay)
- Modify: `tests/test_class_ui.py` (imports; the literal `210` and `186` become `overlay.TAB_W + 24` and `overlay.TAB_W`), `tests/test_overlay.py`

**Interfaces:**
- Produces:
  - `overlay.Row(name, sub, on_click, *, best=False, outline=False)`, unchanged
  - `TAB_W`: the new value
  - `Box.current -> int`: the shown tab's index
  - `Box.touches -> int`: a count of mouse presses on the box or any widget in it, so far. It's counted with an application event filter that Box installs on itself; the filter always returns False.

- [ ] **Step 1: Write the failing tests** in `tests/test_overlay.py`:
  - `test_four_tabs_and_a_dot_fit`: a Box with tabs "EXP", "Path", "Class", "Quests" (pages `TAB_W` wide), and `set_tab_dot(1, True)`. After `adjustSize()`, `box.width() == overlay.TAB_W + 24`.
  - `test_current_and_touches`: `select(2)` sets `current` to 2 and leaves `touches` unchanged. `QTest.mouseClick` on a tab button raises `touches`. So does a press on a `Row` inside a page.
- [ ] **Step 2: Run** `uv run pytest tests/test_overlay.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Move `Row` with its `_PAD`. Set `TAB_W` to the smallest even value that passes `test_four_tabs_and_a_dot_fit` on Windows, and update its comment ("the box is N px wide…").
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS, including the Class and Path width tests at the new width.
- [ ] **Step 5: Commit** `feat(overlay): a box wide enough for four tabs; shared Row`.

### Task 6: Quest window reader

**Files:**
- Create: `src/maplelens/readers/quest_window.py`
- Create: templates or anchors found in Task 1, under `readers/templates/` as the other anchors are
- Modify: `src/maplelens/readers/__init__.py` (`Reading.quest`, `read_all`)
- Test: `tests/test_readers.py`

**Findings from Task 1** (five owner grabs, 2026-11-09; the controller read them against the OSMS data):

- **Layout.** The quest window has two panes side by side. The left (list) pane has a title bar "QUEST" with a close button, then three tabs: **Available**, **In Progress** and **Completed**. The active tab is drawn red/pink and the others grey. Below the tabs, quests sit in groups (a group bar per region, e.g. "Ellinia (1)"), and the selected quest's row is highlighted dark blue with white text. The right (details) pane has a blue header block holding a small green circle, a title, "Level N+" and an NPC picture. Under it come the body lines.
- **The header and the list rows show the quest's CHAIN name, not its own name.** OSMS `chain` makes this concrete:
  - the header "Caretaker's Ledger" is quest 10213 "The Filing Error" (chain "Caretaker's Ledger");
  - the header "Maple World's Unique F…" is quest 80001 "Make a Match Cards Set" (chain "Maple World's Unique Fun: Match Cards").

  Long chain names are cut with "…" in both the header and the list row.
- **The quest's own name is the bold dark line in the details body.** Examples: "The Filing Error", "Make a Match Cards Set". It is never cut. Its height varies:
  - in progress: under a "Quest Summary" box (item icon + "Torn Ledger Pages 0 / 25");
  - available: under a blue "! Talk to NPC Casey" line.

  The description text follows it, in a lighter font, with NPC and map names in blue.
- **Taken.** In Progress means `taken=True`, Available means `taken=False`. **Completed** returns `None`, since there's nothing to help with.
- **Read the bold body line,** snapped with `map_name.snap_title` to `known_quest_names()`. This also tells shared names apart only if they differ, so job-advancement quests still show the shared-name line. The header and list text aren't needed.
- **Off screen.** In `quest_offscreen_1366x768_100.png` the details pane is cut by the screen edge, so the bold line isn't visible. That gives `UNREADABLE`.
- **Scale.** The window scales with the frame: 770x556 px in the 1920x1080 grabs, 548x397 in the 1366x768 ones. It's drawn at screen-pixel positions, like the stat window (`readers/window.py`).
- **Fixtures** (cropped, no names or chat): `quest_progress_1920x1080_100.png`, `quest_available_1920x1080_100.png`, `quest_progress_1366x768_100.png`, `quest_available_1366x768_100.png` and `quest_offscreen_1366x768_100.png`. They're in `.superpowers/sdd/2026-11-09-quest-helper/grabs/` and move to `tests/fixtures/screens/`. Expected readings:
  - the progress grabs: `QuestOpen("The Filing Error", True)`;
  - the available grabs: `QuestOpen("Make a Match Cards Set", False)` (80001 isn't in `quests.json`; the name is returned as read);
  - the off-screen grab: `UNREADABLE`.

**Interfaces:**
- Produces:
  - `QuestOpen(name: str, taken: bool | None)`, frozen
  - `read_quest_window(img: np.ndarray, frame: np.ndarray, scale: float) -> QuestOpen | str | None`, shaped like `read_stat_window`. It returns None when no quest window is open, and `window.UNREADABLE` when one is open but its name can't be read. Otherwise the name is snapped with `map_name.snap_title` to `known_quest_names()`, which loads names from `data/quests.json` (cached).
  - `Reading.quest: "QuestOpen | str | None" = None`

- [ ] **Step 1: Write the failing tests:**
  - `test_read_quest_window`, parametrized over the four Task 1 grabs: the exact quest name, and `taken` as Task 1 found it (None if the window doesn't show it).
  - `test_quest_window_off_screen_is_unreadable`: the half-off-screen grab gives `UNREADABLE`.
  - `test_no_quest_window`: every existing non-quest fixture gives None.
  - `test_read_all_fills_quest`
- [ ] **Step 2: Run** `uv run pytest tests/test_readers.py -v`. Expected: the new tests fail.
- [ ] **Step 3: Implement** with Task 1's anchor, offsets and ink, through `ocr.crop` and `ocr.read_lines`.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(readers): read the open quest window`.

### Task 7: The Quests tab

**Files:**
- Create: `src/maplelens/tools/quest_helper/ui.py`
- Modify: `src/maplelens/store.py` (`DEFAULTS`)
- Test: `tests/test_quest_ui.py`

**Interfaces:**
- Consumes:
  - Task 2's `load`
  - Task 3's `targets`, `find_quest`, `shared_name`, `show_giver`, `also_for`
  - Task 5's `Row`
  - Task 6's `QuestOpen`
  - Task 4's callable shapes
- Produces:
  - `QuestHelperTool(settings: dict, on_settings_changed: Callable[[], None], go: Callable[[str, tuple[int, int] | None, str | None], None], heading: Callable[[], tuple[str, tuple[int, int] | None, int] | None], stop: Callable[[], None], hops: Callable[[str], int | None], data: QuestData | None = None)`
  - `.title == "Quests"`, `.tab: QWidget` (`TAB_W` wide)
  - `.update(r: Reading | None, game_rect, now: float) -> None`
  - `.open -> bool`: the quest window is seen in this reading (`r.quest is not None`)
  - `store.DEFAULTS` gains `"quests_tracked": []` (quest ids, in tracking order) and `"quests_expanded": None` (one quest id)

Behaviour (spec, "How it behaves"):
- **Top part,** only while a quest window is open: the label "Open in the game", then the quest name in bold with a primary "Track" button (a grey "Tracked ✓" if it's already tracked), then its rows. An `UNREADABLE` window shows the grey line "Can't read the quest window: move it fully into view". A name with no quest shows "This quest isn't in MapleLens's list yet". A shared name shows the "Several quests…" line.
- **Tracking part:** the label "Tracking · {n} quests". Each quest is a header with ▸/▾ and ×. One is expanded at a time; clicking a header expands it. × stops tracking. The open quest isn't listed twice.
- **Empty:** the grey line "Open a quest in the game to see where to go".
- **The running row:** its row (`map_id`, `at`) equals `heading()[:2]`. It's outlined (`Row(outline=True)`) with a secondary "Stop" button in place of `›`, and its sub is "Going · {n} maps away". Stop calls `stop`.
- **"Also for":** a clickable row's sub ends " · also for <quest>" when another tracked quest has a row to the same map. The full text is the tooltip.
- **Rebuilding:** rows are rebuilt only when what's shown changes (as `ClassHelperTool._render`). The tab is never taller than `MAX_H`, the tallest Class tab state measured in `test_class_ui`. Past that, it scrolls.

- [ ] **Step 1: Write the failing tests** in `tests/test_quest_ui.py`, with `quests_small.json` and recording fakes for go, heading, stop and hops:
  - `test_open_quest_shows_rows_and_track`
  - `test_track_saves_and_survives_close`: Track adds the id to `settings["quests_tracked"]` and calls `on_settings_changed`. After `update` with `quest=None`, the quest is still shown under Tracking.
  - `test_tracked_open_quest_shows_tracked_mark_once`
  - `test_one_expanded_and_remove`
  - `test_row_click_goes`: a monster row calls `go(map, None, None)`. An NPC row calls `go(map, (x, y), "Luke")`.
  - `test_running_row_outlined_with_stop`
  - `test_row_click_before_map_known_outlines_nothing`: heading returns None, so no row is outlined, and nothing raises
  - `test_also_for`
  - `test_unreadable_unknown_and_shared_lines`
  - `test_one_missed_reading_keeps_the_open_quest`: open, then one reading with `quest=None`, then open again. The top part stays shown throughout. It hides after two `None` readings in a row.
  - `test_unknown_tracked_id_is_dropped`: `quests_tracked: [999999, <known>]` shows only the known quest
  - `test_height_capped`: an open quest with 6 rows plus 3 tracked quests gives `tab.sizeHint().height() <= MAX_H`
- [ ] **Step 2: Run** `uv run pytest tests/test_quest_ui.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ui.py` and the two `DEFAULTS` keys.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(quests): the Quests tab`.

### Task 8: Wire it in: the fourth tab and the automatic switch; docs

**Files:**
- Modify: `src/maplelens/app.py` (`main`, `update_tools`, `Tick`, new `QuestFocus`)
- Modify: `tests/test_app.py`, `tests/test_class_ui.py`, `tests/test_path_ui.py` (every `update_tools(...)` call gains the quest tool)
- Modify: `AGENTS.md` (Layout), `README.md` (status line; credits), `packaging/windows/NOTICE.txt` (credits)

**Interfaces:**
- Consumes:
  - Task 4's `go(map_id, at, label)`, `heading`, `stop`, `hops`
  - Task 5's `Box.current` and `Box.touches`
  - Task 7's `QuestHelperTool`
- Produces:
  - `QuestFocus(box: Box, index: int)` with `.update(open_: bool) -> None`:
    - The state changes only after two calls in a row agree.
    - **On open:** if `box.current != index`, remember `back = box.current` and `touches = box.touches`, then `select(index)`.
    - **On close:** if `back` is set and `box.touches` hasn't changed since, `select(back)`. Either way, forget `back`.
  - `update_tools(box, exp, path, cls, quest, focus, reading, rect, now, seen)`. The quest tool runs in its own try like the others. Then `focus.update(quest.open)`.

Wiring in `main`:
- The quest tool's `go` is `path_tool.go` with no `box.select`: the player stays on Quests.
- Its `heading`, `stop` and `hops` are `path_tool`'s.
- The tools list becomes `[tool, path_tool, cls_tool, quest_tool]`.
- `QuestFocus(box, 3)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_app.py`, with a fake box (`current`, `touches`, `select`):
  - `test_switches_on_open_and_back_on_close`
  - `test_touch_keeps_the_tab`: a `touches` change between open and close leaves the box where it is
  - `test_already_on_quests_stays`
  - `test_one_missed_reading_keeps_the_tab`: open, open, closed, open, so no switch back
  - `test_no_reading_counts_as_closed`: `update_tools(..., reading=None, ...)` twice after an open switches back
  - `test_quest_tool_error_does_not_stop_the_others`
- [ ] **Step 2: Run** `uv run pytest tests/test_app.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `QuestFocus` and the wiring. Update every `update_tools` caller in the tests.
- [ ] **Step 4: Docs.**
  - **`AGENTS.md` Layout:** add `readers/quest_window.py`, `data/quests.json` and `tools/quest_helper/` — `data`, `plan`, `ui`.
  - **`README.md`:** add the Quests tab to the status line. Add the credit "Quest data adapted from [meowdb](https://meowdb.com/msclassic) (NiaDB) and [OSMS Data Explorer](https://osmsdataexplorer.com) (CC BY 4.0)."
  - **`NOTICE.txt`:** the same credit, as plain text.
- [ ] **Step 5: Run** `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and `uv run python scripts/check_screen_only.py`. Expected: all pass.
- [ ] **Step 6: Commit** `feat(quests): Quests tab in the box, switched to while a quest is open`. The PR body says `Closes #25`.

### Task 9: Owner check in the game (Windows)

- [ ] **Step 1:** Run `uv run maplelens` with the game windowed or borderless. The owner checks the spec's "Done means" 1–5:
  1. Opening a quest switches the box to Quests and shows its rows. Closing it switches back, or the box stays if it was clicked.
  2. Track survives closing the window and a restart.
  3. A monster row leads to its best map. An NPC row leads to the NPC itself.
  4. Two tracked quests on one map show "also for".
  5. A half off-screen window shows the ⓘ line, and tracked quests still work.
- [ ] **Step 2:** Tune `NPC_NEAR` (and `NEAR_TIE` if a row looks wrong) from what the owner sees, then commit `tune(quests): …`.
- [ ] **Step 3:** The Mac is checked later, once there's a Mac grab of the quest window (spec).
