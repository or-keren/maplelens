# Monster search in the Path tab — design

Status: **approved 2026-11-14**; revised the same day after the first build: a Maps /
Monsters switch instead of one mixed list, and special copies hidden (owner).

## Why

The Path tab's search finds maps by name or street only (`maps.search`). A player who
wants Fire Boars has to look up somewhere else (meowdb, OSMS) which maps have them,
remember a name, then come back and type it. The data to answer that ships with the app
already: `data/monsters.json` (from OSMS, added for the training spot card, #45) lists
every spawn spot on every map.

Checked 2026-11-14: counting spawn spots per monster per map in our `monsters.json`
gives exactly what meowdb shows. For Fire Boar it's 14 maps, The Burnt Land V 26 of 48
(54%), 3 monster types, down to Deep Valley I 4 of 40. So we need nothing new from OSMS,
and nothing is fetched at runtime.

## Goals

- **The player chooses what to search: Maps or Monsters** (owner, after seeing one mixed
  list: "better to have the user choose"). A two-button switch over the field; Maps is
  the default, so the tab starts as it does today. Typing `boar` under Monsters lists
  only the monsters whose name contains it.
- **Special copies are hidden** (owner). OSMS numbers its quest, party-quest and event
  copies of monsters from 800000 (the Lv 30 Fire Boar of the job-advancement map, the
  Kerning PQ's Ligator and King Slime, Primrose Hill's event monsters). Monster search
  never lists them. Field bosses (700000s: Mano, Mushmom, Stumpy…) stay.
- **Picking a monster lists its maps**, most spawns first, each with its count and share:
  `The Burnt Land V   26 · 54%`.
- **Picking one of those maps works like picking a map today:** the field shows its name,
  and Start (or a click) sets off with the path arrow.

## Non-goals

- **"Nearest map"** (meowdb's *Find nearest map*). It would rank by route length from
  where you are. Left for later; see Open questions.
- **Mob rate and respawn columns.** The training spot card already decided `mob_rate`
  isn't shown, and respawn is the same assumed 7.5 s on nearly every map.
- **The spot card on hover** over a monster's map rows. The card is the Class tab's for
  now; putting it here is its own change.
- **Monsters on maps we have no route data for** (maps not in `maps.json`). The arrow
  can't lead there, so they aren't listed.
- **Searching NPCs or items.**

## Anti-goals

- The search field must keep its focus rules: it takes the keyboard only while you
  type, never the game's (`_Search`).
- Under Maps, typing must work exactly as before: the same matches in the same order.

## The tab

```
┌ Path ──────────────────────┐
│  Maps   [Monsters]         │  ← the switch; Maps by default
│ [ boar                   ] │
│ ┌────────────────────────┐ │
│ │ Fire Boar   Lv 32  ›   │ │  ← a monster row (›: opens its maps)
│ │ Wild Boar   Lv 25  ›   │ │
│ └────────────────────────┘ │
│ ☐ Use taxi       [ Start ] │
└────────────────────────────┘
          click Fire Boar ↓
┌────────────────────────────┐
│ [ Fire Boar              ] │
│ Fire Boar · Lv 32 · 14 maps│  ← grey line
│ ┌────────────────────────┐ │
│ │ The Burnt Land V 26·54%│ │  ← current row, Start goes here
│ │ The Burnt Land III 24… │ │
│ │ Dangerous Valley 21·62%│ │  (scrolls, MATCH_ROWS visible)
│ └────────────────────────┘ │
│ ☐ Use taxi       [ Start ] │
└────────────────────────────┘
```

- **Monster rows** show the name, `Lv N` and a `›`, so they read as "opens more", not
  "goes here". A tooltip gives `Lv 32 · 842 HP · 60 EXP`.
- **The switch** *(look my call)*: two small buttons, `Maps` and `Monsters`, styled like
  the box's tab strip (the chosen one white with a yellow underline, the other grey).
  They never take focus. Switching searches the field's text again under the new choice.
  The choice isn't saved; the tab starts on Maps. The field's placeholder says what it
  searches (`Map name or street` / `Monster name`).
- **Ranking**: monsters whose name starts with the text first, then the rest A–Z, as
  `search` ranks maps; at most 8.
- **`go()`** (a click in the Class or Quests tab) switches to Maps, since it fills the
  field with a map's name.
- **A monster's maps**: every map in `maps.json` where it spawns, most spawn spots first;
  ties go to the higher share, then A–Z. The row is the map's name (`name · street` when
  two share a name, as now), then `count · share%`. Long names elide in the middle, as
  now. The tooltip gives the full title and `26 of 48 spawn spots · 3 monster types`.
- **Picking a monster** puts its name in the field and swaps the list for its maps, with
  the first one current, so **Start right away goes to the busiest map.** A grey line
  above the list names the monster and how many maps it has.
- **Leaving the monster:** editing the field returns to the monster search.
- **Picking a map row** (from either list) works like today's `_pick`: the list closes
  and Start goes there.
- **A monster whose maps all lack route data** isn't listed at all.

## Data

- Spawn spots: `monsters.json` `maps[id].spawns`, a list of `[monster id, x, y]`.
  - **Count** is the number of spots for that monster.
  - **Share** is count ÷ all the spots on that map.
  - **Types** is the number of different monsters on that map.
- Monster names, levels, HP and EXP: `monsters.json` `monsters`.
- No new data file, and no change to `monsters.json`.

## Code

- **Shared loading.** `load_spots` and its types (`Monster`, `MapSpawns`, `SpotData`) are
  in `tools/class_helper/data.py`. The training-spot-card spec said they move to a shared
  module when a second tool needs them, and Path is that second tool. They move to
  `src/maplelens/spawns.py` *(name my call)* and `class_helper` imports them from there.
  Tools still don't import each other.
- **Pure logic, in `tools/path_arrow/maps.py`** (or a small `monsters.py` beside it,
  builder's call), tested without Qt:
  - `search` is unchanged (Maps).
  - `find_monsters(maps, spots, text)` returns the monsters for the Monsters search, ranked
    as above, without special copies or monsters that have no map in `maps.json`.
  - `haunts(spots, maps, monster_id) -> list[Haunt]` returns map id, count, total, share
    and types, sorted as above, keeping only maps in `maps.json`.
- **UI, in `tools/path_arrow/ui.py`:**
  - The switch: two checkable buttons in an exclusive group above the field.
  - `_on_text` fills map rows (Maps) or monster rows (Monsters). Map rows keep their id
    in `Qt.UserRole`; monster rows keep theirs in a role of their own.
  - `_pick` on a monster row fills the field without searching again, shows the grey
    line, and fills the list from `haunts`.
  - `go()` (used by the Class and Quests tabs) switches to Maps first.
- **AGENTS.md Layout:** the new shared module.

## Testing

- `find_monsters`: a name that starts with the text ranks first, the limit of 8 holds,
  and special copies and monsters with no routable map are left out.
- `haunts` is tested on a small spots fixture: counts, shares, types and the sort, and a
  map missing from `maps.json` is left out. One check runs on the real data: Fire Boar's
  first row is The Burnt Land V, 26 of 48, matching meowdb.
- `tests/test_path_ui.py`:
  - Under Maps (the default), typing a monster's name lists no monster.
  - Under Monsters, typing a monster's name shows its row and no maps.
  - Clicking it shows its maps, most spawns first, with the first one current.
  - Start then begins a trip to that map.
  - Editing the field goes back to the monster search; switching to Maps searches the
    text as a map name.
  - `go()` from Monsters switches back to Maps and starts the trip.
- `tests/test_spot_data.py` and `test_class_ui.py` still pass after the move.

## Done means

- The cases above pass.
- `uv run pytest`, `uv run ruff check` and `uv run python scripts/check_screen_only.py`
  all pass.
- Checked by eye in the running app on Windows:
  - Type `fire boar`, pick it, Start, and the arrow leads toward The Burnt Land V.
  - A plain map search still works.

## Open questions

1. **Sort a monster's maps by count (like meowdb), or nearest first?** Count is simple
   and works when you aren't on a known map. Nearest would need a route search for each
   map, and the order would change as you move. *Proposal: count now, nearest later.*
2. **Show the share (`26 · 54%`) or only the count (`26`)?** The tab is about 214 px
   wide, so long map names lose room to it. *Proposal: both; the name elides.*
3. **Should monsters show in the same list as maps,** or only after you type at least 3
   letters, so short searches stay map-only? *Proposal: same list, no minimum.*

## Left to the builder

The `UserRole` shape, the grey line's exact wording, column alignment in the rows, and
where the pure helpers live.
