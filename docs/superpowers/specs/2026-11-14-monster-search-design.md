# Monster search in the Path tab — design

Status: **draft, waiting for the owner's review.**

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

- **One search field finds maps and monsters.** Typing `boar` lists the monsters whose
  name contains it next to the maps that match. There's no Map / Monster switch.
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
- Typing a map name must work exactly as before: the same matches in the same order
  when no monster matches.

## The tab

```
┌ Path ──────────────────────┐
│ [ boar                   ] │
│ ┌────────────────────────┐ │
│ │ Fire Boar   Lv 32  ›   │ │  ← a monster row (›: opens its maps)
│ │ Boar ...               │ │
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
- **Ranking** *(my call)*: one list, maps and monsters together. Names that start with
  the text come first, then the rest in A–Z order, the same rule `search` uses now. The
  limit stays at 8 rows in total.
- **A monster's maps**: every map in `maps.json` where it spawns, most spawn spots first;
  ties go to the higher share, then A–Z. The row is the map's name (`name · street` when
  two share a name, as now), then `count · share%`. Long names elide in the middle, as
  now. The tooltip gives the full title and `26 of 48 spawn spots · 3 monster types`.
- **Picking a monster** puts its name in the field and swaps the list for its maps, with
  the first one current, so **Start right away goes to the busiest map.** A grey line
  above the list names the monster and how many maps it has.
- **Leaving the monster:** editing the field returns to a normal search.
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
  - `search` returns maps and monsters, ranked as above.
  - `where(spots, maps, monster_id) -> list[Haunt]` *(name the builder's)* returns map id,
    count, total, share and types, sorted as above, keeping only maps in `maps.json`.
- **UI, in `tools/path_arrow/ui.py`:**
  - `_on_text` fills monster rows too. An item's `UserRole` tells a map from a monster
    (for example `("map", id)` / `("monster", id)`).
  - `_pick` on a monster row fills the field without searching again, shows the grey
    line, and fills the list from `where`.
  - `go()` (used by the Class and Quests tabs) is unchanged.
- **AGENTS.md Layout:** the new shared module.

## Testing

- `tests/test_maps.py`:
  - search returns monsters as well as maps.
  - A map-only search gives the same results as before.
  - A name that starts with the text ranks first.
  - The limit of 8 still holds.
- `where` is tested on a small spots fixture: counts, shares, types and the sort, and a
  map missing from `maps.json` is left out. One check runs on the real data: Fire Boar's
  first row is The Burnt Land V, 26 of 48, matching meowdb.
- `tests/test_path_ui.py`:
  - Typing a monster's name shows its row.
  - Clicking it shows its maps, most spawns first, with the first one current.
  - Start then begins a trip to that map.
  - Editing the field goes back to a normal search.
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
