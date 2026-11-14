# Path search for monsters, NPCs and items — design

Issue: [#88](https://github.com/or-keren/maplelens/issues/88) "Path arrow: search for
monsters, items and NPCs, not just maps".

Mockup: a local HTML mock built from the repo's real data (routes from Henesys with taxi,
meowdb drop rates), reviewed by the owner ("looking amazing"). Its four states are
described under **What the player sees**.

## Why

The player needs a Jr. Necki, a Red Snail Shell or a talk with an NPC, but doesn't know
which map to go to. Today the Path tab's search only matches map names and streets, so
they look the map up on a wiki on a second screen, then type its name into MapleLens. The
search should take the thing they actually know: the monster, the NPC or the item.

The same data also fixes the Quests tab's **Best**. Today it picks the monster with the
most spawns that drops a quest item and ignores how often it drops it. Best should mean
the place where you get the item fastest (owner).

## Goals

- **One search box for everything.** The Path tab's search matches maps (as today),
  monsters, NPCs and items. Each match shows its picture and says what it is and how much
  of it there is ("Monster · Lv 4 · 48 maps", "Item · dropped by Red Snail",
  "Map · Maple Road").
- **Full coverage, not just quest things** (owner: items too). This means:
  - every monster in `monsters.json`: the maps OSMS has spawn data for, plus the quest
    monsters' counts
  - every NPC on a map in `data/maps.json`
  - every item one of those monsters drops or one of those NPCs sells
- **Picking a monster or an item lists its places** (owner picked the list over going to
  the nearest one). There is one row per map, or one per shop for an item that's sold. The
  player picks a row, then presses Start as today.
- **A Best / Closest switch** sorts that list (owner). It uses the Quests tab's two words.
- **Best counts drop chance**, in the Path tab and the Quests tab alike, through one
  shared ranking (owner).
- **Pictures on every row** (owner): monster, item and NPC pictures, and a crop of the map
  picture for a map.
- **Hovering a row shows the training-spot card** the Class tab already has: the whole
  map with spawn spots marked.

## Non-goals

- **Fetching anything at runtime.** All data ships with the app, as for every other tool.
- **Monster spawns for Orbis, El Nath and the Passages** (owner: "not yet, but prepare for
  it in the future"). The 94 maps without OSMS spawn data get none now. The quest monsters
  that already have counts there keep them. The data shape (counts without spots) and the
  card (a map with no dots) already handle such maps, so adding them later is a data-only
  change.
- **Measuring drop rates from the screen**, or correcting the reference rates.
- **Prices, the free market, or which shop sells cheapest.** That's the planned prices
  tool.
- **Search by anything but name** (level, job, item type).
- **Cards on the Quests tab's rows.** The data allows it later, but it's not part of this
  change.

## Anti-goals

- **No ranking that disagrees between tabs.** The Quests tab and the Path tab must show
  the same best place for the same item. That's why there is one ranking (Approaches).
- **Rates presented as exact.** meowdb shows them as "OSMLib reference rates; these may not
  represent MapleStory Classic World rates". MapleLens shows them with a "~" and uses them
  to rank, never as a promise.
- **A thing that's in the game but not found.** If an item can't be found, the player
  concludes the feature is broken. That's why the coverage is full rather than quest-only.
- **Breaking the screen-only rule.** Nothing here reads the game beyond what the Path tab
  already reads (map name, minimap).

## Constraints

- **Tools don't import each other** (AGENTS.md). The Path tab can't use
  `tools/quest_helper` or `tools/class_helper` code. Shared data and logic live outside
  `tools/`.
- **Data sources and terms** (from the quest-helper design):
  - OSMS Data Explorer (CC BY 4.0, already credited): monsters, spawns, NPCs (id, name,
    maps, picture), map pictures, item icons.
  - meowdb / NiaDB, used with the owner's permission: drops, shops and NPC spots that OSMS
    lacks. Fetch it with an identifying user agent and a pause between requests.
  - **Ids.** NPC and monster ids are OSMS's own (Heena = 1, Jr. Necki = 18), and the repo
    keeps them. Item ids are the game's.
    - meowdb's monster ids match OSMS's (Red Snail = 5, Jr. Necki = 18 on both).
    - meowdb's item pages use their own numbers (`/msclassic/item-db/589`), but each icon
      link carries the game id (`cdn.meowdb.com/icons/1322002.png`).
    - meowdb NPCs (shopkeepers, spots) are matched to OSMS ids by name and map. A meowdb
      NPC that matches no OSMS NPC is left out, and the conversion lists those for a look.
  - **The data doesn't exist yet.** Fetching and converting it is the first part of this
    work, and everything else waits on it.
- **Drop rates exist for most drops.** meowdb monster pages carry an "OSMLib Reference Drop
  Rates" table (Red Snail → Red Snail Shell 40%, Jr. Necki → Orange 0.8%). Some drops will
  have no rate.
- **Sizes.** About 1,500 item icons (~0.6 KB each) and ~300 NPC pictures (~3.5 KB each)
  add about 1–2 MB to the install. That's acceptable next to the 9.4 MB of map pictures.
- **`monsters.json` doesn't cover every map.** OSMS has no spawn data for 94 non-town
  maps in `maps.json`: Orbis (38), El Nath (29), Shallow and Deep Passage (20), and a few
  Hidden Street maps. Quest monsters there (Raffle, Aqumander, Echopus, Rafflesia,
  Duskmander, Myewood, Sporewood) have spawn counts in `quests.json` only, and the Quests
  tab routes to them today. That must keep working.
- **Monsters sharing a name.** Jr. Necki is id 18 and also 800001 on a quest-only map. Each
  is its own monster in the data.

## Approaches

Considered, with the owner picking **A**:

- **A. One shared game-data module (picked).** A new `src/maplelens/gamedata.py`, outside
  the tools like `store.py`, loads the monsters, NPCs and items and holds the one "best
  place" ranking. The Quests tab and the Path tab both use it. The training-spot card
  moves out of `tools/class_helper` so the Path tab can show it. Costs: the Quests tab's
  data loading is reworked, and its tests hold its behaviour in place.
- **B. Grow `quests.json` and give the Path tab its own loader.** The Quests tab stays
  almost untouched, but the ranking would exist twice and drift. That's the anti-goal
  above. Rejected.
- **C. One file per kind** (`npcs.json`, `items.json`, …). The same as A, with more files
  and nothing gained. Rejected.

The data is built by a one-off conversion outside the repo, as `quests.json` and
`monsters.json` were. Committing the fetch script is not part of this change.

## The data

- **`data/monsters.json`** keeps its shape and its role (monsters, spawn spots, pictures).
  It also gains the quest monsters' spawn counts on maps where OSMS has no spawn spots
  (today only in `quests.json`), so it becomes the only source of monster spawns. Such a
  map has counts but no spots, and its card shows no dots. Other monsters on those maps
  come later (Non-goals).
- **`data/game.json`** (new) holds:
  - `npcs`: id → name, places `[(map id, world x, world y)]`. Every NPC on a map in
    `maps.json`. An NPC whose spot isn't known gets places with the map only, and the trip
    then ends at the map, as `go(map_id)` without `at` does today.
  - `items`: id → name, `drops: [(monster id, rate % | null)]`, `shops: [npc id]`. Every
    item a monster in `monsters.json` drops or an NPC in `npcs` sells. It also holds every
    item `quests.json` names today, including the 292 that have neither a drop nor a shop
    (reward gear, quest-only items), so reward and quest rows keep their names.
- **`data/quests.json`** shrinks to `quests`, `chain_names` and `other_names`. Its
  `npcs`, `mobs` and `items` move to the two files above, and quests keep pointing at the
  same ids.
- **`data/item_icons/<item id>.png`** grows to every item in `game.json`.
- **`data/npc_icons/<npc id>.png`** (new) holds OSMS's NPC pictures.

Everything that reads `quests.json`'s `npcs`, `mobs` or `items` today reads them from the
new place:

- `readers/quest_tracker.py` `target_names()`: still only the names quests ask for (the
  monsters and items named by a quest's `mobs` and `items`). It must not grow to every
  item, because a wider list makes its name snapping worse. It looks the names up in the
  new files.
- `tools/exp_meter/meter.py` `monster_free_maps()`: the towns where no monster spawns, now
  from `monsters.json`. That covers every monster rather than only quest monsters, so the
  limitation in its docstring goes away.
- `tools/quest_helper/data.py`: `QuestData` gets its NPCs, monsters and items from
  `gamedata`.

## The shared module: `src/maplelens/gamedata.py`

Pure Python, no Qt. It holds:

- **Loading** `monsters.json` and `game.json` into frozen dataclasses (monster, NPC,
  item), cached like the existing loaders, with the paths overridable for tests. The
  class helper's `SpotData` / `load_spots` move here.
- **Search**: `search(text, maps)` returns matches of every kind. A match has a kind
  (map, monster, NPC, item), an id, a name and a count for its grey line.
  - Matching is case-insensitive "name contains text", as today's map search. For maps,
    the street matches too.
  - The order is: exact name first, then names that start with the text, then the rest.
    Ties go by kind (monster, NPC, item, map), then by name.
  - Monsters that share a name are one match with their maps merged.
- **Ranking**: `places(thing, hops, closest)` returns the ranked list of places for a
  monster, NPC or item. Each place has:
  - `map_id`
  - `at`: the NPC's spot, or None
  - `score`
  - `via`: the monster or shop NPC behind the row
  - `rate`
  - `count`: spawns of that monster on the map

  The rules are in the next section. Both tabs call it. The Quests tab takes the first
  place, and the Path tab lists them all.

## The ranking

For an item, each map scores the drops you'd expect from clearing it once:
**Σ (spawns of a dropper on the map × its rate)**, summed over every dropper on that map.
For a monster, the score is its spawn count on the map.

- **Shops come first**, before every drop map, in Best and in Closest (buying beats
  farming). Shops are sorted by fewest maps away.
- **Best:** maps within 80% of the top score (`NEAR_TIE`, as today) count as tied, and the
  nearest of those comes first. Ties after that go by higher score, then by map id. The
  rest follow by score.
- **Closest:** fewest maps away first, then higher score.
- **Unknown rates.** A dropper with no rate still counts, but its maps come after every
  map with a rated dropper. If no dropper has a rate, the ranking falls back to spawns
  (today's behaviour).
- **Unreachable** places (no route from here) come last in both modes. They stay listed,
  greyed out.
- **Unknown position.** When the player's map isn't known, hops are unknown: Closest falls
  back to Best's order and rows drop their "N away".
- **Several droppers on one map:** the row names the one contributing most, and
  "+N more" when there are others.
- Maps outside `maps.json` are never a place. A monster or item whose only places are
  there keeps producing the Quests tab's "Not in the map list yet".

### What changes in the Quests tab

- An item row's place comes from `places(item)`: best map by expected drops, not the
  dropper with the most spawns. The row still reads "{monster} · {map}", where the
  monster is the place's `via`.
- An item that's both sold and dropped now points to the nearest shop. Today it points to
  a drop map: Orange, Lemon and Weighted Earrings change.
- An item riding on one of the quest's own monsters (the "mine" path in `targets()`)
  still rides on that monster. When several of the quest's monsters drop it, the one with
  the higher spawns × rate wins.
- The Best / Closest switch and `starts_closest` are unchanged.

## What the player sees (Path tab)

**Typing.** The match list shows every kind. A row is a 28 px picture, then the name in
bold, then a grey line:

```
[snail ]  Snail              Monster · Lv 1 · 37 maps
[snail ]  Red Snail          Monster · Lv 4 · 48 maps
[shell ]  Red Snail Shell    Item · dropped by Red Snail
[npc   ]  Luna               NPC · Henesys Department Store
[map   ]  Snail Garden       Map · Rainbow Street
```

- A map row's picture is a crop of the map picture (`data/map_pictures`). A map without
  one gets no picture, and its text keeps its place.
- An item with several sources says how many: "Item · 8 shops · dropped by Jr. Necki", or
  "dropped by 3 monsters".
- An item with no known source (a quest reward, a quest-only item) is still found, so
  nothing in the game is missing from search. Its line reads "Item · no known place", and
  picking it shows "Where to get it: unknown" (the Quests tab's wording) with no Start.
  *(Designer's call.)*

**Picking a map** works as today: the field fills, and Start goes there.

**Picking an NPC with one place** works like picking a map, and the trip continues to
their spot (`go(map_id, at, label)`, as the Quests tab does).

**Picking a monster, an item, or an NPC with several places** replaces the field and the
match list with:

- a picked row: picture, name and grey line, plus an × that returns to the search with
  the text kept.
- a line "Where it spawns" (monster) or "Where to get it" (item), with
  **Best | Closest** on the right. It defaults to Best, and the choice is remembered in
  settings like `path_taxi`.
- the places list. The first row is selected, and the list scrolls past `MATCH_ROWS`.
  The rows read:
  - monster map: map picture crop · map name · "27 spawns · 5 away"
  - item drop map: dropper's picture · map name · "Red Snail ×23 · ~40% · 3 away", or
    "· rate unknown" without a rate
  - shop: NPC picture · NPC name · "2 away · Kerning City Pharmacy"
  - unreachable: greyed, "no route"
- Use taxi and Start, as today. Start goes to the selected row's map, and to the NPC's
  spot for a shop.

Rates are shown as meowdb shows them, as a percentage, prefixed "~".

**Hovering a row** (a map match or a place) shows the training-spot card beside the box,
as on the Class tab:

- **A map match** shows the full card, as the Class tab does.
- **A monster or drop place** shows the card with only that monster's spawn spots and its
  monster line, plus "Up to N monsters at once". For an item it adds
  "≈ 9.2 drops per clear".
- **A shop place** shows the NPC's name, the map's title and the NPC's picture.

The card never takes focus or a click (unchanged from the Class tab).

## Moving the card

`SpotCard` (the widget) moves from `tools/class_helper/ui.py` into shared code that
`overlay.py` sits beside. `Card` / `CardMob` and the data side move into `gamedata.py`.
`spot_card()` keeps building the Class tab's card from a training `Place`. A sibling
builds the Path tab's card from a map id plus an optional monster to single out. The
Class tab's behaviour doesn't change, and its tests (`test_spot_card.py`,
`test_spot_data.py`) follow the code.

## Docs

- `AGENTS.md` layout: `gamedata.py`, `data/game.json`, `data/npc_icons/`, the card's new
  home, and that tools may use `gamedata` as they use readers and overlay.
- `README.md`: the Path tab's line mentions searching for monsters, NPCs and items. The
  credits are:
  - OSMS line: add "NPC pictures".
  - meowdb line: drops, shops and NPC spots.
  - a credit for the drop rates: "OSMLib reference rates, via meowdb".

## Tests

- `gamedata`: loading from small test files, the search order (exact, prefix, contains;
  kind ties; merged same-name monsters), and the ranking. The ranking cases are: expected
  drops summed over droppers, the 80% tie going to the nearer map, shops first, unknown
  rates after rated ones, all rates unknown → spawns, unreachable last, unknown position.
- Quests tab: the existing plan tests still pass. New cases cover an item with a higher
  rate on fewer spawns winning, and a sold-and-dropped item pointing to the shop.
- Path tab (`test_path_ui.py`): typing shows mixed kinds; picking a monster shows its
  places; the switch re-sorts and is remembered; × returns to the search; Start on a
  place starts the trip; a one-place NPC starts like a map with `at`.
- `test_quest_data.py` / readers: `target_names()` is still exactly the quest-named
  names.

## Settled with the owner

- **Shipping the OSMLib rates is fine** (owner). They're credited in the README. The data
  keeps a rate optional per drop, so removing them later would be a data change only.
- **Orbis, El Nath and the Passages:** not yet, but prepared for (Non-goals).

## Designer's calls

- Items with no drop or shop show up in search as "Item · no known place".
- meowdb NPCs are matched to OSMS ids by name and map.
- Monsters that share a name are one match.
- Unreachable places go last, greyed out.
- Shops go first in Closest as well as in Best.

## Left to the builder

- The exact JSON shapes, as long as they hold what's above.
- How hops are computed for a whole list: one breadth-first pass from here rather than
  `plan()` per map.
- The crop of a map picture for its row (centre or the busiest part).
- Widget structure for the picked state. Reusing the `_choose` page is fine.
