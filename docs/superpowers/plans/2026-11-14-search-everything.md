# Path search for monsters, NPCs and items: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Path tab finds maps, monsters, NPCs and items, and lists each one's places
under a Best / Closest switch. Best counts drop chance, through one ranking that the
Quests tab shares.

**Architecture:**
- New bundled data: `data/game.json` (NPCs and items) and `counts` in
  `data/monsters.json`.
- `src/maplelens/gamedata.py` (pure Python) loads that data and holds the search and the
  ranking.
- The Class tab's training-spot card moves into shared code. The Path tab grows a
  "picked" state, and the Quests tab ranks through `gamedata`.

**Tech Stack:** Python 3.12, PySide6, pytest, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-11-14-search-everything-design.md`. Read it first:
this plan argues from it.

## Global Constraints

- Screen-only rule (AGENTS.md). Nothing is fetched at runtime; all data ships in
  `src/maplelens/data/`.
- Tools never import each other. Shared code lives outside `tools/`: `gamedata.py`, and
  `spot_card.py` beside `overlay.py`.
- Ids: NPC and monster ids are OSMS's own, and item ids are the game's. They are `int` in
  `gamedata`. `SpotData` and the card keep monster ids as `str`, as `monsters.json` does
  today.
- Rates are percentages (`40.0` means 40%), shown as `~40%`, and may be `None`.
- `NEAR_TIE = 0.8`, the same value as `quest_helper/plan.py` today.
- New setting: `"path_best": True` in `store.DEFAULTS`. True means Best, False means
  Closest.
- Fetching from meowdb: user agent `MapleLens data conversion (github.com/or-keren/maplelens)`,
  with a pause of at least 1.5 s between requests. OSMS v1:
  `https://osmsdataexplorer.com/data/api/v1/{items,npcs,monsters,maps}.json`.
- Don't change `version` in `pyproject.toml`. Don't write banned module or Win32 names in
  `src/` or `scripts/` comments (AGENTS.md).
- Every task ends with `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`
  and `uv run python scripts/check_screen_only.py` all passing.

## Review Focus

1. **Typing a single letter** ("a") matches hundreds of things. The list must stay fast
   and capped at `SEARCH_LIMIT`, and the box must not grow. Test owned by Task 3.
2. **The player's map isn't known yet** (just started, minimap closed). Picking a monster
   must still list its places in Best order, without "N away". Test owned by Task 7.
3. **A picked thing whose places are all unreachable or off-list.** The list shows greyed
   "no route" rows, or "Where to get it: unknown", and Start does nothing. It must not
   crash. Test owned by Task 7.
4. **Typing again after picking.** × must return to the search with the text kept, and a
   new pick must replace the old places, not append to them. Test owned by Task 7.
5. **The hover card going stale.** The card must hide when the list closes, when the tab
   changes, and when Stop or Start is pressed, as on the Class tab. Test owned by Task 8.

---

### Task 1: Build the data (one-off conversion, outside the repo)

**Files:**
- Create (outside the repo): `%LOCALAPPDATA%\Temp\maplelens-data\convert.py`. Run it with
  `uv run python -I`, and keep downloads in their own subfolder.
- Create: `src/maplelens/data/game.json`, `src/maplelens/data/npc_icons/<npc id>.png`
- Modify: `src/maplelens/data/monsters.json` (adds the monsters and a top-level `counts`),
  `src/maplelens/data/item_icons/` (adds an icon for every item)
- Leave `quests.json` untouched. Task 5 slims it.

**Produces:**

`game.json`:

```json
{"npcs":  {"109": {"name": "Mina", "places": [["010000002", -258, 84]]}},
 "items": {"4000004": {"name": "Red Snail Shell", "drops": [[5, 40.0]], "shops": []}}}
```

- `places` entries are `[map id, x | null, y | null]`.
- `drops` entries are `[monster id, rate % | null]`.
- `shops` holds NPC ids.

`monsters.json` gains `"counts": {"010006010": {"57": 6, "58": 4}}`: map id → monster id →
spawns. It covers only maps that have no entry under `maps`. Those maps' monsters are
added to `monsters` (name, level, hp, exp from OSMS `monsters.json`).

- [ ] **Step 1: Write `convert.py`** to assemble everything from these sources:

| What | Where |
|---|---|
| NPC name, picture | OSMS `npcs.json` (`id`, `name`, `icon_url`); keep NPCs on a map in `maps.json` (OSMS map id → `str(id).zfill(9)`) |
| NPC spots | meowdb `/msclassic/maps/<map id>` for each map in `maps.json`: the `placedNpcs` list (`href` `/msclassic/npcs/<id>` is the OSMS id, plus `x`, `y`) |
| Shops | meowdb `/msclassic/npc-shops`: each shop's NPC link and its item links; item game id from the icon URL where present, else by exact name in OSMS `items.json` |
| Drops | meowdb `/msclassic/monsters/<id>` for every monster in `monsters.json` plus the `quests.json` monsters: the page's drop list. Each drop's rate comes from the "OSMLib Reference Drop Rates" table (`section#osmlib-drop-rates`) when the item is there, else `null`. Rows only in the OSMLib table are not drops |
| Item name, icon | OSMS `items.json` (`name`, `icon_url`) |
| Quest monsters off the OSMS maps | `quests.json` `mobs[id].spawns` for maps without an entry in `monsters.json` `maps` → `counts` |

Items kept: every item dropped by a kept monster, sold by a kept NPC, or named in
`quests.json` `items`. The last group includes the 292 that have neither a drop nor a
shop.

- [ ] **Step 2: The script asserts, and stops on failure:**
  - every meowdb monster id's name equals the OSMS name
  - every `quests.json` NPC, monster and item id is present
  - for every `quests.json` item, the old `drops` ⊆ the new drop monster ids, and the old
    `shops` ⊆ the new `shops`
  - Luna (109)'s shop includes Orange (2010004)
  - Red Snail (5) → Red Snail Shell (4000004) has rate 40.0

  It prints the meowdb NPCs it couldn't match, and the items without an icon.

- [ ] **Step 3: Run it.** Expected: no assertion fails; about 1,500 items and about 300
  NPCs.

- [ ] **Step 4: `uv run pytest`.** Expected: all pass. `load_spots` ignores the new
  top-level `counts`.

- [ ] **Step 5: Commit**

```bash
git add src/maplelens/data
git commit -m "data: every NPC and item with drops, rates and shops; NPC pictures (#88)"
```

### Task 2: `gamedata.py`: load the game data

**Files:**
- Create: `src/maplelens/gamedata.py`, `tests/test_gamedata.py`,
  `tests/fixtures/gamedata/monsters.json`, `tests/fixtures/gamedata/game.json` (a few
  entries each)
- Modify: `src/maplelens/tools/class_helper/data.py`. Move `Monster`, `MapSpawns`,
  `SpotData`, `load_spots`, `SPOTS`, `PICTURES`, `ICONS` into `gamedata.py`, and
  re-import them from there.
- Modify: `src/maplelens/tools/class_helper/plan.py`, `ui.py`, `tests/test_spot_data.py`
  (imports only)
- Modify: `AGENTS.md` Layout. Add `gamedata.py`, `data/game.json` and `data/npc_icons/`.
  Tools may use `gamedata` as they use readers and overlay.

**Produces:**

```python
GAME: Path        # data/game.json
NPC_ICONS: Path   # data/npc_icons
Hops = Callable[[str], int | None]

@dataclass(frozen=True)
class Npc:  id: int; name: str; places: tuple[tuple[str, int | None, int | None], ...]
@dataclass(frozen=True)
class Mob:  id: int; name: str; spawns: dict[str, int]; level: int = 0
@dataclass(frozen=True)
class Item: id: int; name: str; drops: tuple[tuple[int, float | None], ...]; shops: tuple[int, ...]
@dataclass(frozen=True)
class GameData:
    npcs: dict[int, Npc]; mobs: dict[int, Mob]; items: dict[int, Item]
    def npc_icon(self, npc: int) -> Path | None
    def item_icon(self, item: int) -> Path | None
def load_game(monsters: Path = SPOTS, game: Path = GAME) -> GameData  # default paths cached, as quest_helper.data.load does
```

`Mob.spawns` counts a monster's spawn spots per map under `maps`, merged with `counts`.

- [ ] **Step 1: Write the failing tests** in `tests/test_gamedata.py`:
  - `test_loads_fixture`: an `Npc` with a `(map, None, None)` place, an `Item` with a
    `None` rate, and a `Mob` whose `spawns` merges the spots under `maps` with `counts`.
  - `test_shipped_references_resolve`: in `load_game()`, every drop monster is in `mobs`,
    every shop is in `npcs`, and every place map is in `maps.json`.
  - `test_shipped_examples`: `items[4000004].drops` contains `(5, 40.0)`; `109` is in
    `items[2010004].shops`; `mobs[57].spawns` (Aqumander) is non-empty;
    `mobs[5].level == 4`.
- [ ] **Step 2: `uv run pytest tests/test_gamedata.py -v`.** Expected: fails on import.
- [ ] **Step 3: Implement it as specified above.** Then do the move: `class_helper`
  re-imports, and its behaviour is unchanged.
- [ ] **Step 4: `uv run pytest`.** Expected: all pass, including `test_spot_data.py` and
  `test_spot_card.py`.
- [ ] **Step 5: Commit** with the message `feat: gamedata loads every NPC, monster and item (#88)`.

### Task 3: `gamedata.search`

**Files:** Modify `src/maplelens/gamedata.py`, `tests/test_gamedata.py`.

**Interfaces:**
- Consumes `GameData` from Task 2.
- Produces:

```python
SEARCH_LIMIT = 20
KINDS = ("monster", "npc", "item", "map")  # tie order
@dataclass(frozen=True)
class Match: kind: str; ids: tuple; name: str; line: str  # ids: int ids, or (map_id,) for a map
def search(data: GameData, maps: Mapping[str, tuple[str, str]], text: str, limit: int = SEARCH_LIMIT) -> list[Match]
```

`maps` is map id → (name, street), and only those maps count as places.

- [ ] **Step 1: Write the failing tests.** Build a small `GameData` and `maps` inline:
  - `test_search_order`: for "snail", the exact name "Snail" comes first, then names
    starting with "snail" (monster before item before map at the same tier, then by
    name), then names containing it.
  - `test_search_lines`:
    - monster: `"Monster · Lv 4 · 48 maps"`. Count only maps in `maps`.
    - item with one dropper: `"Item · dropped by Red Snail"`
    - item with several droppers: `"Item · dropped by 3 monsters"`
    - item with shops and one dropper: `"Item · 8 shops · dropped by Jr. Necki"`
    - item with neither: `"Item · no known place"`
    - NPC with one map: `"NPC · Henesys Department Store"`
    - NPC with several maps: `"NPC · 2 maps"`
    - map: `"Map · Maple Road"`. The street matches too, as `path_arrow/maps.search`
      does.
  - `test_same_name_monsters_merge`: two "Jr. Necki" ids give one `Match` with both ids;
    the map count is of the union.
  - `test_search_caps_and_blank`: `""` and `"  "` return `[]`; "a" over 50 names returns
    exactly `SEARCH_LIMIT`.
- [ ] **Step 2: Run the tests.** Expected: fail.
- [ ] **Step 3: Implement it.** Case-insensitive `in`, sorted by
  `(tier, KINDS.index(kind), name)`, where tier 0 is an exact match, 1 a prefix, and 2
  anything else.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with the message `feat: search maps, monsters, NPCs and items (#88)`.

### Task 4: `gamedata` ranking

**Files:** Modify `src/maplelens/gamedata.py`, `tests/test_gamedata.py`.

**Produces:**

```python
NEAR_TIE = 0.8
@dataclass(frozen=True)
class Source:
    map_id: str
    at: tuple[int, int] | None      # an NPC's spot
    via: int                        # monster id, or the shop NPC's id
    shop: bool
    count: int                      # spawns of `via` on the map; 0 for a shop
    rate: float | None              # `via`'s rate; None for a monster search or unknown
    others: int                     # other droppers on the same map
    score: float                    # expected drops per clear, or spawns
    hops: int | None
def mob_places(data, mob_ids: Iterable[int], listed: Collection[str], hops: Hops, closest: bool) -> list[Source]
def item_places(data, item_id: int, listed: Collection[str], hops: Hops, closest: bool) -> list[Source]
def npc_places(data, npc_id: int, listed: Collection[str], hops: Hops) -> list[Source]
```

**Order** (spec, "The ranking"):
1. Shops, by hops.
2. Rated maps.
3. Unrated maps, where `score` = spawns of their droppers.
4. Unreachable (`hops` is None while other places are reachable), last in both modes.

Within groups 2 and 3, Best works as follows:
- places with `score >= NEAR_TIE * top` (top within the group) come first, by
  `(hops, -score, map_id)`
- then the rest by `(-score, map_id)`

Closest sorts by `(hops, -score, map_id)`. When every `hops` is None (position unknown),
Closest uses Best's order. On a map with both rated and unrated droppers, only the rated
ones score, and `via` is the top contributor.

`npc_places` keeps `at` only when x and y are known, and sorts by `(hops, map_id)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_item_score_sums_droppers`: two droppers on one map (10 × 40% + 5 × 10%) give
    one `Source` with `score == 4.5`, `via` = the first, and `others == 1`.
  - `test_rate_beats_spawns`: map A has 20 spawns at 1%, map B has 5 at 40%. B comes
    first in Best.
  - `test_near_tie_nearer_wins`: scores 10 and 8.5 with hops 3 and 1. Best puts the
    8.5 first; at 10 and 7 it puts the 10 first.
  - `test_shops_first_both_modes`: a shop 6 maps away comes before a drop map 1 away, in
    Best and in Closest.
  - `test_unrated_after_rated` and `test_all_unrated_falls_back_to_spawns`.
  - `test_unreachable_last` and `test_unknown_position_closest_is_best`.
  - `test_unlisted_maps_dropped`: a map not in `listed` never appears.
  - `test_mob_places_merged_ids`: spawns of two ids on the same map add up.
- [ ] **Step 2: Run the tests.** Expected: fail.
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with the message `feat: one ranking for places, with drop chance (#88)`.

### Task 5: The Quests tab ranks through `gamedata`, and `quests.json` slims

**Files:**
- Modify: `src/maplelens/tools/quest_helper/data.py`
  - Drop its `Npc`, `Mob`, `Item` and re-export them from `gamedata`.
  - `_load` fills `npcs`, `mobs`, `items` from `load_game()` (taking a `game: GameData`
    parameter for tests). `QuestData` keeps its fields.
- Modify: `src/maplelens/tools/quest_helper/plan.py`
  - `best_map` / `closest_map` / `_mob_map` → the first of `mob_places`.
  - `_top_dropper` / `_loose_item` → the first of `item_places`. The sub line reads
    `"{via name} · {map name}"`, or `"{npc} · {map name}"` with `at` for a shop.
  - The "mine" path in `targets()`: among the quest's own droppers, pick the highest
    (best-map spawns × rate). Treat a `None` rate as 0, and break ties as today.
  - Delete `npc_place`; `_npc_row` uses the first of `npc_places`.
- Modify: `src/maplelens/readers/quest_tracker.py` `target_names()`. Keep the names of the
  monsters and items that `quests.json` quests name (`mobs`, and `items` not in
  `start_items`), looked up in `load_game()`. Same set as today.
- Modify: `src/maplelens/tools/exp_meter/meter.py` `monster_free_maps()`. Use the maps
  with any spawn in `load_game().mobs`, and drop the docstring's quest-only caveat.
- Modify: `src/maplelens/data/quests.json`. Remove `npcs`, `mobs`, `items`.
- Modify tests: `tests/test_quest_plan.py`, `tests/test_quest_data.py`,
  `tests/test_quest_ui.py`, `tests/test_meter.py`, as needed for the new `Item.drops`
  shape `((mob, rate), ...)` and the removed `best_map` / `closest_map` / `npc_place`.
  Their asserted outcomes stay, except as below.

- [ ] **Step 1: Write the failing tests** in `tests/test_quest_plan.py`:
  - `test_loose_item_rate_beats_spawns`: an item dropped by monster 1 (map a, 20 spawns,
    1%) and monster 2 (map b, 5 spawns, 40%). Its row targets map b, sub
    `"<mob 2> · Map B"`.
  - `test_sold_and_dropped_points_to_shop`: the row targets the shop NPC's map with `at`,
    sub `"<npc> · <map>"`.
  - `test_mine_path_uses_rate`: two quest monsters drop the item; the higher
    spawns × rate one carries it.

  Add to `tests/test_quest_data.py`: `test_target_names_unchanged`, comparing
  `target_names()` against a set computed from quests' ids and `load_game()` names, and
  checking that it is a subset smaller than all item names.
- [ ] **Step 2: Run the tests.** Expected: the new tests fail.
- [ ] **Step 3: Implement it as above.** Then remove the three keys from `quests.json`.
- [ ] **Step 4: `uv run pytest`.** Expected: all pass.
- [ ] **Step 5: Commit** with the message `feat: Quests tab Best counts drop chance; quest data reads gamedata (#88)`.

### Task 6: The spot card moves to shared code, and gains Path cards

**Files:**
- Create: `src/maplelens/spot_card.py`. It takes `SpotCard`, `_Art`, `_words`, `CARD_W`,
  `PICTURE_H`, `ICON`, `ICON_FIT`, `DOT_R`, `DOT_EDGE`, `_MARGIN` from
  `tools/class_helper/ui.py`.
- Modify: `src/maplelens/gamedata.py`. Move `Card`, `CardMob`, `DOT_COLOURS`, `CAP` and
  `respawn_text` in from `class_helper/plan.py`. `spot_card()` stays in `class_helper`.
- Modify: `class_helper/ui.py`, `class_helper/plan.py`, `tests/test_spot_card.py`
  (imports)
- Modify: `AGENTS.md` Layout (`spot_card.py`)

**Produces** (in `gamedata.py`):

```python
@dataclass(frozen=True)
class Card: ...existing fields...; lines: tuple[str, ...] = ()   # extra lines after `cap`
def map_card(spots: SpotData, map_id: str, name: str, street: str, only: str | None = None, extra: str | None = None) -> Card | None
def npc_card(data: GameData, npc_id: int, map_title: str, shop: bool = False) -> Card | None
```

- `map_card`: the Class tab's card for any map. With `only`, it keeps just that monster's
  line and dots, in `DOT_COLOURS[0]`. `extra` goes into `lines`. For a map with `counts`
  but no `maps` entry, it returns a card with no picture and no dots, but the monster
  line ("6 spawns"). It returns None when there's nothing to show.
- `npc_card`: title = NPC name, street = `map_title`, picture = the NPC picture,
  size = the picture's own size, no mobs, and `lines = ("Sells it",)` when `shop`.

`SpotCard.fill` scales a picture by at most 1×, so an NPC isn't blown up. Check that the
Class tab's map pictures are unaffected.

- [ ] **Step 1: Write the failing tests** in `tests/test_spot_card.py`:
  - `test_map_card_only_one_monster`: shipped map `000000040` with `only="2"` has one mob
    line and only colour `#ffcc33` dots.
  - `test_map_card_counts_only_map`: a map in `counts` gives no picture and a "6 spawns"
    line.
  - `test_map_card_extra_line`
  - `test_npc_card`
  - `test_fill_never_upscales`: an offscreen `SpotCard` given a 59×69 picture keeps it
    at most 59×69.
- [ ] **Step 2: Run the tests.** Expected: fail.
- [ ] **Step 3: Implement it, and do the moves.**
- [ ] **Step 4: `uv run pytest`.** Expected: all pass, `test_class_ui.py` included.
- [ ] **Step 5: Commit** with the message `refactor: the spot card is shared; map and NPC cards for the Path tab (#88)`.

### Task 7: The Path tab searches everything, and lists places

**Files:**
- Modify: `src/maplelens/tools/path_arrow/ui.py`, `src/maplelens/tools/path_arrow/route.py`,
  `src/maplelens/store.py` (`"path_best": True`)
- Modify: `src/maplelens/tools/path_arrow/maps.py`. Delete `search`; `gamedata.search`
  replaces it. Move its test in `tests/test_maps.py` into Task 3's tests if anything
  isn't covered there.
- Modify: `tests/test_path_ui.py`, `tests/test_route.py`
- Modify: `src/maplelens/app.py` only if the `PathArrowTool` constructor changes. It
  gains `game: GameData | None = None` (None → `load_game()`), so tests pass their own.

**Interfaces:**
- Consumes: `search`, `Match` (Task 3); `mob_places`, `item_places`, `npc_places`,
  `Source` (Task 4); `GameData.npc_icon` / `item_icon`, `SpotData.icon` /
  `SpotData.picture` (Task 2).
- Produces: `route.distances(maps, start: str, taxi: bool) -> dict[str, int]`, one
  breadth-first pass with the same edges as `plan`. `PathArrowTool.hops` uses it for
  lists, cached per (here, taxi).

**Behaviour** (spec, "What the player sees"):
- The match list keeps `QListWidget` (keyboard, current item). Each item gets an item
  widget: a 28 px picture (monster icon, item icon, NPC picture, or a centre crop of the
  map picture), the name in bold, and `Match.line` in grey, both elided to the tab width.
  `Qt.UserRole` holds the `Match`.
- A map match, or an NPC with one listed place, picks as today. An NPC goes through
  `go(map_id, at, label=npc name)`-style `_begin(at, label)`.
- A monster, an item, or an NPC with several places switches to the picked state, which
  replaces the field and the list:
  - the picked row with ×
  - the label `"Where it spawns"`, `"Where to get it"` or `"Where to find them"` (NPC),
    with `Best | Closest` on the right, set from `settings["path_best"]`; switching saves
    it
  - the places list, with the first row current
- Place row lines:
  - monster: `"27 spawns · 5 away"`
  - drop: `"Red Snail ×23 · ~40% · 3 away"`, adding `" · +1 more"` when `others`, and
    using `"rate unknown"` in place of `~40%`
  - shop: `"2 away · Kerning City Pharmacy"`
  - NPC place: `"2 away"`
  - `"N away"` becomes `"here"` at 0, and `"no route"` (grey text) when unreachable; the
    hops part is left out while the position is unknown
- A place's picture is the dropper's or monster's icon for a drop, the NPC picture for a
  shop, and the map crop for a monster place.
- No places at all: the label reads `"Where to get it: unknown"` / `"Where it spawns:
  unknown"`, with no list, and Start is disabled.
- Start begins a trip to the current place's map, with `at` / label for an NPC or shop.
  An unreachable place leaves the existing "No route" note.
- × goes back to the search, with the text and its matches as they were.

- [ ] **Step 1: Write the failing tests** in `tests/test_path_ui.py`. Pass a small
  `GameData` and use the existing `MAPS`:
  - `test_search_shows_kinds`: typing lists a monster, an item and a map, with each
    item's `Match.line`.
  - `test_pick_monster_lists_places`: rows in Best order; switching to Closest re-sorts
    and sets `settings["path_best"] = False`.
  - `test_start_from_place`: Start on the second row begins a trip whose goal is that
    row's map.
  - `test_shop_place_carries_npc_spot`: the trip's `at` is the NPC's spot.
  - `test_one_place_npc_starts_like_a_map`
  - `test_unknown_position_lists_best_without_hops` (Review Focus 2)
  - `test_all_unreachable_or_unknown` (Review Focus 3): greyed "no route" rows, and the
    "unknown" label with Start disabled.
  - `test_cross_returns_to_search_and_new_pick_replaces` (Review Focus 4)
  - `test_route.py::test_distances_matches_plan`: for every map, `distances[m]` equals
    `len(plan(...)) - 1`.
- [ ] **Step 2: Run the tests.** Expected: fail.
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: `uv run pytest`.** Expected: all pass.
- [ ] **Step 5: Commit** with the message `feat: Path tab finds monsters, NPCs and items and lists their places (#88)`.

### Task 8: Hover card on the Path tab, and docs

**Files:**
- Modify: `src/maplelens/tools/path_arrow/ui.py`, `tests/test_path_ui.py`
- Modify: `README.md`
  - the Path tab line: it finds monsters, NPCs and items
  - OSMS credit: add "NPC pictures"
  - meowdb credit: drops, shops and NPC spots
  - new line: `Drop rates are OSMLib reference rates, via meowdb.`

**Behaviour:** As on the Class tab (`class_helper/ui.py`: `_hide_timer`, the swap when
moving straight between rows, `SpotCard.put(row)`), with
`QListWidget.setMouseTracking(True)` + `itemEntered`. The cards are:
- a map match: `map_card(spots, id, name, street)`
- a monster place: `map_card(..., only=str(via))`
- a drop place: the same, with `extra=f"≈ {score:.1f} drops per clear"`
- a shop place: `npc_card(...)` with "Sells it"
- other matches (monster, item, NPC rows in the search list): no card

The card hides when the mouse leaves the list, the list hides, the picked state changes,
the tab hides, and on Start / Stop.

- [ ] **Step 1: Write the failing tests:**
  - `test_hover_map_match_shows_card`
  - `test_hover_drop_place_card_has_drops_line`
  - `test_card_hides_on_start_and_on_cross` (Review Focus 5)
  - `test_card_hides_when_tab_hides`
- [ ] **Step 2: Run the tests.** Expected: fail.
- [ ] **Step 3: Implement it, and update the README.**
- [ ] **Step 4: Run all four checks** (Global Constraints). Then run the app
  (`uv run maplelens`) against the game, or against a fixture through the run skill.
  Search for "snail", pick Red Snail Shell, hover a row, switch Best / Closest, and press
  Start.
- [ ] **Step 5: Commit** with the message `feat: Path tab hover cards; README credits for drops and rates (#88)`.
