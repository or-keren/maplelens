# Monster Search Implementation Plan

> **For agentic workers:** work the tasks in order, test first (red → green) in each. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Path tab's search, typing a monster's name lists that monster; picking
it lists the maps it spawns on, with the most spawns first (`26 · 54%`); Start goes to
the chosen map.

**Architecture:** The spawn data loader moves out of `class_helper` into a shared
`maplelens/spawns.py`, so the Path tool can read it without importing another tool. A
new pure module, `path_arrow/monsters.py`, does two things: it ranks maps and monsters
together for the search, and it lists a monster's maps (`haunts`). `path_arrow/ui.py`
puts monster rows in the existing match list and swaps the list for a monster's maps
when one is picked.

**Spec:** `docs/superpowers/specs/2026-11-14-monster-search-design.md` (approved
2026-11-14, with the proposals for its three open questions: sort by count, show count
and share, monsters in the same list with no minimum length).

## Global constraints

- Screen-reading only: nothing here touches the game, and
  `uv run python scripts/check_screen_only.py` passes.
- No new dependency or data file, and `monsters.json` doesn't change.
- Typing a map name gives the same matches in the same order as before when no monster
  matches.
- `PathArrowTool.go()` behaves exactly as before (the Class and Quests tabs use it).
- Never change `version` in `pyproject.toml`.
- Text shown in the tab:
  - Monster row: `{name}  Lv {level}  ›`, with the tooltip `Lv {level} · {hp:,} HP · {exp:,} EXP`.
  - A monster's map row: `{map name}  {count} · {share}%`. The tooltip is
    `{street} / {name}` on one line and `{count} of {total} spawn spots · {types} monster
    types` on the next.
  - Grey line over a monster's maps: `{name} · Lv {level} · {n} maps` (`1 map` when
    there's only one).

## Review focus

- **Picking a monster must not search again.** Setting the field's text would fire
  `_on_text` and put back the plain search list, so the text goes in with signals
  blocked → `test_picking_a_monster_lists_its_maps` (Task 3).
- **Start while a monster row is current** (typed, never clicked) goes to its busiest map,
  the same as picking it and pressing Start *(my call; the spec didn't say)* →
  `test_start_on_a_monster_row_goes_to_its_busiest_map` (Task 3).
- **`go()` while a monster's maps are showing** (a Class tab click) still starts the right
  trip and clears the grey line → `test_go_leaves_monster_mode` (Task 3).
- **Map rows keep `Qt.UserRole` = map id.** `_begin`, `go()` and the Start button's
  enabled check read it, so monster rows carry their id in a separate role
  (`MONSTER_ROLE = Qt.UserRole + 1`) and leave `UserRole` empty.
- **Ties in the ranking**: a map and a monster with the same name (`Pig Beach` / `Pig`)
  both show, ranked by the one rule → `test_matches_ranks_maps_and_monsters_together`
  (Task 2).

---

## Phase 1: Foundation

### Task 1: The spawn data in a shared module

**Description:** Move `Monster`, `MapSpawns`, `SpotData`, `load_spots` and the `SPOTS`,
`PICTURES` and `ICONS` paths from `tools/class_helper/data.py` into a new
`src/maplelens/spawns.py`, unchanged. `class_helper` and the tests import them from
there. This is a pure move, with no change in behaviour.

**Acceptance criteria:**
- [ ] `maplelens.spawns` has the types, paths and `load_spots`, unchanged.
- [ ] `class_helper/data.py` no longer defines them. `class_helper/data.py`, `plan.py`
      and `ui.py` import them from `maplelens.spawns`.
- [ ] AGENTS.md Layout lists `spawns.py`: "the spawn data (`monsters.json`, map
      pictures, monster icons), shared by the Class and Path tools".

**Verification:**
- [ ] `uv run pytest tests/test_spot_data.py tests/test_spot_card.py tests/test_class_ui.py tests/test_class_plan.py` passes.
- [ ] `uv run ruff check` passes.
- [ ] `grep -rn "class_helper.data import.*\(load_spots\|SpotData\|MapSpawns\|Monster\)" src tests` finds nothing.

**Dependencies:** none

**Files:**
- Create: `src/maplelens/spawns.py`
- Modify: `src/maplelens/tools/class_helper/data.py`, `plan.py`, `ui.py`
- Modify: `tests/test_spot_data.py`, `tests/test_spot_card.py`, `tests/test_class_ui.py`
- Modify: `AGENTS.md`

**Scope:** M. Many files, but each changes only its import lines.

### Task 2: Pure monster search (`path_arrow/monsters.py`)

**Description:** The logic, tested without Qt:

```python
@dataclass(frozen=True)
class Haunt:
    map_id: str
    count: int  # this monster's spawn spots on the map
    total: int  # all spawn spots on the map
    types: int  # different monsters on the map

    @property
    def share(self) -> int:  # whole percent, rounded
        ...


@dataclass(frozen=True)
class MonsterHit:
    id: str
    monster: Monster


def haunts(spots: SpotData, maps: dict[str, MapInfo], monster_id: str) -> list[Haunt]:
    """Maps in `maps` where the monster spawns: most spots first, then higher share, then A–Z."""


def matches(maps, spots, text, limit=8) -> list[MapInfo | MonsterHit]:
    """`search`'s maps plus monsters whose name contains `text` and that have a haunt;
    names starting with `text` first, then A–Z; at most `limit`."""
```

`matches` gets its maps from `search(maps, text, limit=len(maps))`, so the street
matching stays in one place. It then sorts maps and monsters with `search`'s key. Map-only
results therefore come out in the same order as `search(maps, text)`.

**Acceptance criteria:**
- [ ] `haunts` counts spots, totals and types, sorts as specified, and leaves out maps
      that aren't in `maps`.
- [ ] `matches` gives `search`'s result exactly when no monster matches. Monsters with
      no haunt are never listed. The limit holds across maps and monsters together.
- [ ] On the shipped data, Fire Boar (`30`) has 14 haunts, and the first is
      `Haunt("010004115", 26, 48, 3)` (The Burnt Land V, share 54).

**Verification:**
- [ ] Tests written first in `tests/test_monster_search.py`:
  - `test_haunts_counts_and_sorts` (on `spots_small.json` plus a few `MapInfo`s)
  - `test_haunts_skips_maps_without_route_data`
  - `test_matches_is_search_when_no_monster_matches`
  - `test_matches_ranks_maps_and_monsters_together`
  - `test_matches_skips_monsters_without_haunts`
  - `test_matches_limit`
  - `test_fire_boar_matches_meowdb` (real data)
- [ ] `uv run pytest tests/test_monster_search.py tests/test_maps.py` passes.

**Dependencies:** Task 1

**Files:**
- Create: `src/maplelens/tools/path_arrow/monsters.py`, `tests/test_monster_search.py`
- Possibly modify: `tests/fixtures/spots_small.json`, if the fixture needs a third map
  for the sort tests. Check that `test_class_ui` and `test_spot_card` still pass if so.

**Scope:** S

### Checkpoint: Foundation
- [ ] `uv run pytest`, `uv run ruff check` and the guard all pass.
- [ ] Nothing visible has changed yet.

---

## Phase 2: The tab

### Task 3: Monster rows and a monster's maps in the Path tab

**Description:** Wire `matches` and `haunts` into `PathArrowTool`.

- `PathArrowTool.__init__` gets `spots: SpotData | None = None`, which defaults to
  `load_spots()`, following the `maps` parameter. `app.py` doesn't change.
- `_on_text` calls `matches(self.maps, self._spots, text)`:
  - Map rows are built as now.
  - Monster rows show `name  Lv N  ›`, with `MONSTER_ROLE` = monster id and the stats
    tooltip.
  - It also clears monster mode: the grey line is hidden and `self._monster = None`.
- `_pick(item)`: on a monster row, call `_show_monster(id)`. On a map row, do what it
  does now.
- `_show_monster(id)`:
  - Put the name in the field with signals blocked.
  - Set `self._monster = id` and show the grey line (a new `text_label`, in the label grey,
    above the list).
  - Fill the list from `haunts`, sized like `_on_text` does (`MATCH_ROWS` visible), with
    row 0 current.
  - Map rows carry `UserRole` = map id. The list stays open and typing mode ends.
- `_begin`: when the current item is a monster row, use its first haunt's map. The
  simplest way is to call `_show_monster` first, then go on with row 0.
- The Start button's enabled check is unchanged: a current item exists.

**Acceptance criteria:**
- [ ] Typing part of a monster's name lists it, marked with `›`.
- [ ] Clicking it puts its name in the field, shows the grey line, and lists its maps
      (most spawns first, `count · share%`), with the first one current.
- [ ] Start (or clicking a map row, then Start) begins a trip to that map.
- [ ] Editing the field returns to a normal search with no grey line. `go()` works
      from monster mode too.
- [ ] Every existing `test_path_ui.py` test still passes unchanged.

**Verification:**
- [ ] Tests written first in `tests/test_path_ui.py`. The `make` fixture gets a small
      `SpotData` whose maps are ids in its `MAPS` (e.g. a "Snail" on `A` ×3 and `C` ×1):
  - `test_typing_a_monster_lists_it`
  - `test_picking_a_monster_lists_its_maps` (order, row text, current row 0, list still
    shown, the field shows the monster's name)
  - `test_start_after_picking_a_monster_starts_a_trip`
  - `test_start_on_a_monster_row_goes_to_its_busiest_map`
  - `test_editing_after_a_monster_searches_again`
  - `test_go_leaves_monster_mode`
- [ ] `uv run pytest tests/test_path_ui.py` passes.

**Dependencies:** Task 2

**Files:**
- Modify: `src/maplelens/tools/path_arrow/ui.py`, `tests/test_path_ui.py`

**Scope:** S–M

### Checkpoint: Complete
- [ ] `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and
      `uv run python scripts/check_screen_only.py` all pass.
- [ ] By eye in the running app on Windows (`uv run maplelens`, with the game open):
  - Type `fire boar`, click it, and The Burnt Land V `26 · 54%` is listed first.
  - Start, and the arrow leads toward it.
  - A plain map search (`henesys`) still works.
  - A long name such as `East Rocky Mountain VII  20 · 35%` elides readably at the
    default tab width.
- [ ] The owner reviews before a PR.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Moving `load_spots` breaks the Class tab (an import missed, or the `@cache` loader in a test) | Med | Task 1 is a pure move with only the existing tests; grep for old imports; the full test suite runs at the checkpoint |
| `_on_text` fires during `_show_monster` and puts the plain search back | Med | `blockSignals` as `_pick` already does; tested directly |
| Rows too cramped at 214 px | Low | `ElideMiddle` is already on; checked by eye; the share can be dropped later (spec's open question 2) |
| Monster ids (OSMS) mixed up with game ids elsewhere | Low | `haunts` only reads `monsters.json`; no other id space is touched |

## Not in this plan

Nearest-first sorting, the spot card on hover over a monster's map rows, and searching
NPCs or items (all in the spec's non-goals).
