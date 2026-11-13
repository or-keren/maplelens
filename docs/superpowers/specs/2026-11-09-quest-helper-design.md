# MapleLens: quest helper design

Date: 2026-11-09. Status: approved by the owner (2026-11-09).
Issue: [or-keren/maplelens#25](https://github.com/or-keren/maplelens/issues/25).
Mockups the owner approved: `.superpowers/brainstorm/27706-1794164667/content/quest-mix.html`
(local, not committed; this document is the reference).

## Intent

Quests name things without saying where they are (owner):

- "talk to an NPC", and you don't know which map that NPC is on;
- "bring 10 of an item", and you don't know where to get it;
- "kill 50 of a monster", and you don't know which map has the most of them.

One quest often names several of these at once. Today the owner leaves the game to look
each one up. The quest helper answers all of them in the overlay: **open the quest in the
game, and MapleLens already knows every NPC, monster and item it needs and can take you
to each one with the path arrow** (owner: "yes" to "you never type anything").

The screen-only rule in `AGENTS.md` holds for every part of this document. The quest
helper reads pixels of the game's quest window and draws in its own box. It never presses
keys or clicks for the player, and it never reads game memory or files.

## Goals

- **A Quests tab** in the overlay box, after EXP, Path and Class.
- **The open quest shows itself** (owner picked the mix over a button beside the game
  window): when a quest is open in the game's quest window, the Quests tab shows it at
  once, with its targets as rows. Zero clicks.
- **The box switches to it by itself** (owner): opening a quest window switches the box to
  the Quests tab; closing it switches back (rule in "The tab").
- **Track keeps it** (owner): a Track button on the open quest adds it to a tracked list
  that stays after the game window closes. Several quests can be tracked.
- **One row per place to go** *(my call, owner agreed)*: a monster and the items it drops
  share one row; an NPC is its own row. Clicking a row starts the path arrow to that place.
- **NPC rows end at the NPC** (owner agreed): on the NPC's map the arrow points at the NPC.
- **Monster rows go to the best map** for that monster (rule below).
- **"Also for …"** *(my call, owner agreed)*: when two tracked quests send you to the same
  map, the row says so.

## Non-goals (first version)

- **Search by quest name** (option C in the mockups). Added only if reading the quest
  window proves unreliable.
- **Progress reading** (kills or items so far). The tab shows what the quest asks for; the
  game's own window shows progress.
- **Quest finder** ("quests for my level near me") and **next quest in a chain**. Later,
  as their own changes.
- A Track button drawn beside the game's quest window (option A). The button lives in
  the tab.
- Live data updates. The data ships with the app and changes by commit.

## Anti-goals

- Anything breaking the screen-only rule, including fetching data at runtime.
- **A confidently wrong place.** A row with no known source or no reachable map says so
  with a grey ⓘ line and isn't clickable. It never guesses a map.
- A Quests tab taller than the tallest existing tab, or a box whose width changes from
  tab to tab (the overlay redesign's anti-goal). Longer content scrolls. The box does get
  one new, wider fixed width for the fourth tab (owner, see "The tab").
- Anything that takes keyboard focus from the game. Rows and buttons keep `Qt.NoFocus`.

## How it behaves

### The tab

Two parts, top to bottom (mockup states 1–3):

1. **Open in the game.** Shown only while the quest window is open and its quest was
   recognised: the quest's name in bold, a primary **Track** button (or a grey
   "Tracked ✓" if it already is), then its rows.
2. **Tracking · n quests.** Each tracked quest is a header line with ▸/▾ and ×. Only one
   is expanded at a time *(my call: keeps the tab short)*; clicking another header expands
   it instead. × stops tracking. When the open quest is also tracked, it shows only in the
   top part (not twice) *(my call)*.

With nothing open and nothing tracked, the tab shows a grey ⓘ "Open a quest in the game
to see where to go".

**Box width** (owner picked a wider box over tighter tabs or a shorter title): four tab
titles plus the Path tab's running dot don't fit today's 210 px box at the code's 14 px
spacing (the builder check measured about 257 px needed). The box gets one new fixed
width that fits them, the same for every tab; `TAB_W` grows to match. Spacing and titles
stay as they are.

**Switching to the tab by itself** (owner): when a quest window opens in the game, the box
switches to the Quests tab. When it closes, the box switches back to the tab it was on,
unless the player touched the box in between (owner's examples: changed tabs, clicked
Track). Any click on the box counts as touching it *(my call: a row click or × too)*;
then the box stays where the player left it. If the box was already on Quests, closing
the window changes nothing.

The tracked list and which quest is expanded are saved in `settings.json` and survive
restarts *(my call)*. MapleLens can't see a quest being handed in, so only × removes one.

### Rows

Each row is the Class tab's clickable row: a title line, a grey sub-line, a yellow `›`.

| Target | Title | Sub-line | Click |
|---|---|---|---|
| Monster (+ items it drops that the quest needs) | `Jr. Necki ×20 · Skin ×10` | best map's short name | route to that map |
| Item sold by an NPC | `Salad ×1` | `<NPC> · <map>` | route to the NPC |
| Item with several sources | the source that comes first by the order below | | |
| NPC to hand in to | `Luke` | `<map> · hand in` | route to the NPC |
| NPC who gives the quest | `Luke` | `<map> · gives the quest` | route to the NPC |

- **Item names drop the monster's name** when the row already names it ("Skin" for
  "Jr. Necki Skin") *(my call; the builder may keep full names if it elides badly)*.
- **Items the quest hands you** (its start items) get no row.
- **Item source order**: a drop from a monster the quest already sends you to, then any
  other drop (best map rule), then a shop. An item may name several monsters; the row
  uses the one whose best map has the most spawns *(my call)*.
- **Same NPC gives and takes** the quest: one row, sub-line `<map>`.
- **Giver row**: shown when the quest isn't taken yet. If the reading spike (below) finds
  the quest window shows taken vs not-taken, use that. If it can't tell: the open,
  untracked quest shows the giver row; a tracked quest doesn't *(my call)*.
- **Row order**: giver (if shown), monster rows in the quest's order, item rows, hand-in
  last.
- **Rows that can't be clicked**, with a grey ⓘ sub-line: an item with no known source
  ("Where to get it: unknown"), a monster with no spawn in the data, a map not in
  `maps.json` ("Not in the map list yet").
- **"Also for"**: if another tracked quest has a row to the same map, the sub-line ends
  "· also for <quest>" (elided; full text as tooltip).

### Best map for a monster *(my call, owner agreed)*

The map with the most spawn points of that monster. Maps with at least 80% of that count
are near-ties; among them, the one with fewest map changes from the player's current map
wins (the path arrow's route, taxi setting included). With the current map unknown, the
most spawns wins. Ties broken any stable way. The 80% is a named constant to tune.

### Clicking a row

The row starts the path arrow, the same way a Class training row does (the app passes
the tool a `go` callable). The player stays on the Quests tab; the Path tab shows its
running dot as today. While that trip runs, its row is outlined in `ACCENT` with a
secondary **Stop** button in place of `›`, and its sub-line says how many maps are left
(mockup state 3).

**NPC targets need a path arrow change.** Today a trip ends on arrival at the map. A trip
to an NPC carries the NPC's world position; on the destination map the arrow points at the
NPC instead of hiding, and the trip arrives when the player is within a small distance of
it (a named constant). Then the usual "Arrived" line shows, naming the NPC. Every other
rule of the path arrow (reroute, minimap closed, big maps) is unchanged.
Where the arrow can't place the player on the NPC's map (no arrow on that map, no
minimap there), the trip arrives on reaching the map, as today, and the line says the
NPC is on this map *(my call)*. A closed minimap on an arrow map is today's rule: the trip
keeps running and asks for the minimap.

### When the quest window can't be read

The top part shows a grey ⓘ line ("Can't read the quest window: move it fully into view"
or whatever the spike shows is the fixable cause; yellow if the player can fix it with one
action, per the overlay's rule). The tracked list keeps working. A quest name that is read
but matches no known quest shows ⓘ "This quest isn't in MapleLens's list yet".

## The parts

### 1. Quest window reader (the risky part: spike first)

`readers/quest_window.py`: frame → the open quest's name (or `None`), plus whether it is
taken, if the window shows that. Pure function, tested on fixture PNGs like every reader.
The name is read with the system OCR and snapped to the known quest names (as
`map_name.py` snaps map titles).

**Nobody on this project has seen Classic's quest window yet.** Before building on it:
the owner grabs the quest window with `scripts/grab.py` (an available quest and an
in-progress one, at two resolutions), and the builder checks the name can be found and
read reliably, and what tells taken from not-taken. If the name can't be read reliably,
stop and bring it back to the owner; search by name (non-goal above) is the fallback to
discuss. Fixtures: cropped to the quest window, no character names or chat; the owner
reviews every PNG before commit. `Reading` gains the new field and `read_all` fills it.

The reader goes through `readers/ocr.py`, so it uses each platform's OCR. Done means is
checked on Windows; the Mac gets the same code path and is checked when a Mac grab
exists *(my call)*. The data, the quest logic and the path arrow change don't depend on
the spike and may proceed alongside it, since a search fallback would reuse them all
*(my call)*; the spike still comes first in the plan, since it can change the tab.

### 2. Data file (ours)

`src/maplelens/data/quests.json`, our own format, built by a one-off conversion outside
the repo (as `maps.json` was; the converter isn't committed). The exact schema is the
builder's; it must hold:

- **Quests** (Victoria and Maple Island; Classic has nothing else yet, owner): id, name,
  giver NPC, hand-in NPC, required monsters with counts, required items with counts,
  start items. Event quests are left out, and so is 80000 "Mar" the Fairy and the Water of
  Life (no source names its NPC). Citizenship and crafting quests are in *(owner decided
  2026-11-09; they were first left out as not "go somewhere" quests, but many are "talk
  to this NPC" quests)*. Many citizenship quests share a name (e.g. "Donating to Kerning
  City" x18), so the tab shows "Several quests have this name" for those. Left-out names
  go in `other_names`, so the quest window still reads them.
- **NPCs**: id, name, map id, world x/y.
- **Monsters**: id, name, spawn count per map.
- **Items**: id, name, sources (dropped by monster ids; sold by NPC ids).

Only what the tool needs, and only entries some kept quest refers to.

**Sources** (see the owner's memory note on data sources):

- [OSMS Data Explorer](https://osmsdataexplorer.com) public dataset v1
  (`https://osmsdataexplorer.com/data/api/v1/`, CC BY 4.0, already credited): quests,
  requirements, givers, NPCs with maps and positions, monster spawns with counts. Prefer
  it for anything it has.
- **meowdb (NiaDB)**, used with the owner's permission (2026-11-08): hand-in NPCs
  (OSMS has none), item drops and shops (OSMS has none; they're decided by the game's
  servers). The owner's permission covers an agent fetching it the way the map data was
  fetched (owner, 2026-11-09), politely: an identifying user agent and a pause between
  requests.
- Map ids already match: both sources and our `maps.json` use Classic's own ids.

Checks in `tests/`: the file loads; every NPC, monster, item and map id a quest refers to
is in the file (or, for maps, in `maps.json`); every NPC's map is in `maps.json`.

### 3. Quest logic (pure)

`tools/quest_helper/` (the name is the builder's): load the data, find a quest by read
name, build its rows (grouping, source order, best map, giver/hand-in, "also for"), no Qt.
Unit tests on a small hand-made fixture file, as the class helper does.

### 4. The tab (Qt)

The Class tab's clickable `Row` lives in `class_helper/ui.py` today; it moves to
`overlay.py` so both tools use it (tools never import each other). Otherwise the tab
uses `overlay.py`'s shared look only: primary and
secondary buttons, `ACCENT`, the grey ⓘ style, `TAB_W`. Depends only on readers, overlay
and its own data, never on another tool. The app wires `go` (and, for the running-row
outline, a way to ask which trip is running and to stop it) as it does for the Class tab.

### 5. Path arrow change

`go(map_id, npc=None)` (shape is the builder's): the NPC target and arrival rule in
"Clicking a row". The Class tab's calls are unchanged.

## Docs to update

- `AGENTS.md` Layout: `readers/quest_window.py`, `tools/quest_helper/`, `data/quests.json`.
- `README.md`: the tool in the status line, and a credit line for meowdb quest data
  (NiaDB, with a link) next to the existing ones. The OSMS credit is already there.
- `packaging/windows/NOTICE.txt`: the same credits, if it lists data sources (it does
  today).
- Close issue #25 from the PR.

## Done means

With the game windowed or borderless, the owner can:

1. open a quest in the game and see the box switch to the Quests tab with its rows,
   without clicking; close it and see the box go back, or stay if they clicked it;
2. Track it, close the quest window, and still see it; restart MapleLens and still see it;
3. click a monster row and be led to its best map; click an NPC row and be led to the NPC
   itself on its map;
4. track two quests that share a map and see "also for";
5. move the quest window half off screen and see the ⓘ line, with tracked quests still
   working.

`uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and the guard pass.

## Left to the builder

The reader's colours, offsets and OCR details; the data file's exact schema; the box's
new width in pixels; the
arrival distance and the 80% constant's final values; how the tab scrolls when long; how
item names are shortened; how the app asks the path tool which trip is running.
