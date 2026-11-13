# MapleLens — Phase 3 design: class helper

Date: 2026-11-06. Status: draft for owner review.
Mockups: [MapleLens class helper: mockups](https://claude.ai/artifact/3UAWYD2ZkN5BzqXKjmBnmW)
(the AP/SP marks there are the first pass; this document supersedes them where they differ).

## Intent

Today the owner alt-tabs to a class guide to answer four questions: where do my AP go,
where do my SP go, where should I train, and what gear can I use. The class helper
answers them in the game, for the player's current class and level, **automatically and
as data, never as paragraphs of guide text**. Anything that is a place hooks into the
path arrow.

Two surfaces:

1. **On the game's own stat and skill windows.** When the player opens one, MapleLens
   reads what the character has now, compares it with what the guide plan expects at this
   level, and, if points are unspent, marks where each one goes. The player still clicks
   every + themselves.
2. **A Class tab in the overlay box**, next to EXP and Path: training maps, gear, the next
   step, each place with a Go button that starts the path arrow.

## Owner decisions

- **Structured data of our own, with credit** (owner: "just credit, we don't need their
  raw data, we can read it and create our own structured data"). The advice comes from
  the meowdb (NiaDB) class guides, read once and written into our own data format. We do
  not download or ship meowdb's data files.
- **Automatic, not free text** (owner). Every line on the tab is computed from data.
- **Training maps hook into the path finder** (owner): Go starts the path arrow.
- **AP and SP advice sits on the game window that spends them** (owner): the stat window
  for AP, the skill window for SP.
- **Compare the current state with the plan for this level** (owner): read the stats and
  skill levels off the window, compare with the guide's targets at the current level,
  and if points are left, show where they go.
- **Class tab content** (owner agreed to the proposal): training maps, gear, job
  advancement, one "next step" line. The EXP meter's own history is shown next to each
  training map.
- **Guide prose is left out** (owner agreed): potion tips, common mistakes, example builds
  and citizenship. The credit links to the guide pages for those.
- **A build picker** (owner chose it over "main build only" and "guess the build"). Where
  a guide offers more than one build (LUK thief or the STR/DEX "Sindit" reset, Arrow
  Blow or Double Shot, Energy Bolt or Magic Claw, the weapon type for Fighter / Page /
  Spearman, the class a Beginner is heading for), the Class tab has a small picker. It
  is chosen once per class and remembered in `settings.json`. The guide's main build is
  the default until the player picks.
- **SP in Classic** (owner): each job tab has its own SP pool; 3 SP per level. The owner
  believes leftover 1st-job SP can still be spent on the 1st-job tab after the 2nd job
  advance. **Confirmed 2026-11-07** (owner, in game): the skill window shows a separate
  SP count on each job tab. The SP maths doesn't depend on the other questions (leftover
  SP, SP for the advance itself): it works from what each tab shows, spent plus unspent.

## Goals

- Stat window: read level, unspent AP, and base STR / DEX / INT / LUK. Mark each + that
  should get points, with how many ("3 here", "2 here").
- Skill window: read the open job tab, unspent SP, and each skill's current level. Mark
  each skill that should get SP, with how many, in the plan's order.
- Show the gap against the plan quietly: "DEX 10 over plan" when past it, "LUK 6 behind
  plan" when behind with no points to spend. Never suggest anything that can't be
  undone.
- Class tab: class and level; unspent AP/SP if known; up to 3 training maps for this
  level with level range, monster levels and the player's own best EXP/min there; gear
  usable now and the next piece coming; job advancement; one "next step" line.
- Go on any place starts the path arrow to it.
- A dot on the Class tab when something new applies after a level-up.

## Non-goals

- **Clicking or spending points for the player.** Never. The screen-only rule
  (`AGENTS.md`) forbids sending input; marks are drawn on MapleLens's own see-through
  layer, and clicks pass through to the game.
- 3rd job and beyond. Neither the guides nor the client data have it yet. At level 70 the
  tab says what the next job is ("At 70: become a Hermit") and nothing more.
- Reading the equipment window or inventory. Gear advice is by level and stats only.
- Quests, potions, mobs-to-avoid, a build editor, the player writing their own plan.
  (Picking among the guide's own builds is in scope; see the build picker.)
- Live download of any guide or data at runtime. Data ships with the app and changes by
  commit, as `maps.json` does today.

## Anti-goals (a failure even if it technically works)

- **Free text.** If a line can't be computed from data, it doesn't appear.
- **A stale or guessed mark.** A ring on the wrong + is worse than none. If a window
  can't be read with confidence (covered, half off-screen, unknown skill), its marks hide
  and the Class tab says why, as the path arrow does.
- **Anything that looks like automation** or reads game memory/files.
- **Copying meowdb wholesale.** Our data holds facts (targets, map IDs, item IDs, level
  ranges), not their wording.

## Data

### Where it comes from

- **Advice**: the 15 meowdb guide pages — the beginner guide plus the 14 1st- and 2nd-job
  class guides under `https://meowdb.com/msclassic/guides/<slug>`. Read once, by a person
  or an agent at the page level (an honest User-Agent naming MapleLens, one request every
  10 seconds or slower, stop on 403/429), and converted by hand into our format, outside
  the repo, like the map data conversion. The converter or notes don't go in the repo.
- **Facts used to fill IDs and requirements**: OSMS Data Explorer's public dataset,
  `https://osmsdataexplorer.com/data/api/v1/` (CC BY 4.0, already credited): skill IDs,
  max levels and prerequisites; item IDs, level and stat requirements; monster levels and
  spawn maps. Map IDs come from our own `data/maps.json`.

### Our file: `src/maplelens/data/classes.json`

One record per job the job reader can return, 1st and 2nd job (Beginner included). The
exact schema is the builder's; it must hold:

- `job` (as `readers/job.py` spells it), `next_jobs`, and `source` (the guide page URL,
  for the credit).
- **Builds**: one or more named builds, the first being the guide's main one. The AP
  plan, SP plan and gear rows below belong to a build; training maps and job
  advancement may be shared.
- **AP plan**: for any level, the target base value of each stat. Old-school builds are
  "hold some stats at a target, put the rest into the main stat", so bands of
  `{levels, hold: {DEX: 25}, rest: "LUK"}` are the expected shape; a band may set a
  target that grows with level. A build with an AP reset (Sindit) records the reset as a
  milestone at its level: before it, the marks follow the pre-reset targets; the reset
  itself shows only as the "next step" line, never as a mark *(my call)*.
- **SP plan**: one ordered list of steps `{skill_id, up_to_level}` per job tab, since
  each tab has its own pool. The expected skill levels on a tab at level L are found by
  spending, in order, 3 SP per level earned since that job's advance (plus any SP the
  advance grants, once confirmed in game). Leftover SP on the 1st-job tab after the 2nd
  advance is advised from the 1st-job plan.
- **Training maps**: `{map_id, from_level, to_level}` rows, taken from each class
  guide's own "training maps" table (not from meowdb's Training Advisor or grind-map
  tools). A guide map that isn't in our `maps.json` keeps its name and gets no Go
  button *(my call: adding maps to `maps.json` is out of scope here)*.
- **Gear**: `{item_id, from_level, where_map_id}` rows; requirements come from OSMS at
  conversion time and are stored with the row.
- **Job advancement**: `{level, map_id, npc_name}` for the next job.

All IDs must resolve: a test loads `classes.json` and checks every `map_id` given is in
`maps.json`, every skill ID is in the OSMS skill list, and the bands cover every level
the job spans with no gap.

### Credit

- `README.md`: under the existing credit lines, "Class plans adapted from the NiaDB class
  guides", linking each of the 15 guide pages (NiaDB's reuse page asks for a link to the
  exact page, not the homepage).
- `classes.json` keeps each record's `source` URL.

## How it works

### New readers (screenshot → value, pure, tested on PNG fixtures)

- `readers/stat_window.py`: finds the stat window anywhere in the frame (the player can
  drag it), returns `None` if it isn't there or can't be fully read, else the level,
  unspent AP, base STR/DEX/INT/LUK, and the frame position of each stat's + button.
- `readers/skill_window.py`: finds the skill window, returns `None` or the open job tab,
  unspent SP, and for each visible skill row its skill (matched against the known skills
  of that job tier, as `job.py` matches against `JOBS`), current level, and the position
  of its + button. Rows scrolled out of view are simply not returned.
- Numbers via glyph templates, words via the system OCR, like the existing readers. Both
  join `read_all`.
- Fixtures: the owner grabs cropped windows with `scripts/grab.py` at the three
  resolutions already used (1366×768, 1920×1080, 2560×1440) plus the Mac grab, including
  a covered or half off-screen window case for each.

### Plan maths (pure, unit-tested)

- `ap_advice(plan, level, stats, unspent) → per-stat {add, over, behind}`: fill held stats
  up to their target first, the rest into the main stat. A stat already above target is
  "over" and gets nothing.
- `sp_advice(plan, job, level, skills, unspent) → per-skill {add, over, behind}`: walk the
  steps in order from the *actual* skill levels; the unspent SP go to the first unmet
  steps. Skills not in the plan at all get nothing; points already in them show as "off
  plan".
- Steps whose skill's prerequisite (from OSMS) isn't met yet are skipped until it is.
- **Rows scrolled out of view** *(my call)*: skill levels are remembered for the session
  from every row ever read. Marks show on visible rows when every earlier plan step's
  skill level is known; if one isn't, the window shows one tag, "scroll the list once",
  instead of marks. That keeps marks honest without hiding them most of the time.

### Marks on the game windows

Drawn on the existing see-through `Layer`, at the + positions the reader returned: a ring
on each + that should get points, with a small tag ("3 here"); a quiet tag for "over" or
"behind". If the window isn't read this tick, the marks hide; they never stay behind on
an old position. A skill tab that isn't open but still needs SP gets one line on the
Class tab ("1st job tab: 2 SP to place").

### The Class tab

As mockup 3. Order: class and level with an "AP / SP to spend" badge, and the build
picker beside it when the class has more than one build; **Train here** (up
to 3 maps whose band contains the level, each with level range, the monster levels from
OSMS, and the player's best EXP/min there from the EXP meter history if any); **Gear**
(usable now, then the next piece and its level; if the last-read stats are short of its
requirement, "5 DEX short"); **Job advance** from 2 levels before it's due; **Next step**,
the nearest of those milestones.

Stats and skill levels are remembered from the last time each window was read, for this
session only, so the tab can show them with the windows closed. If they were never read,
the tab says "Open your stat window once" instead of guessing.

### Go

Go starts the path arrow to that map exactly as if the player had picked it and pressed
Start, and switches the box to the Path tab. Tools don't import each other (`AGENTS.md`):
`app.py` hands the class helper a `go(map_id)` callable and an EXP history lookup, the
same way it already hands the path arrow `allow_typing`.

### Level-up dot

When the level reader reports a new level and something on the tab changed (a new map,
gear, job advance, or points to place), the Class tab gets a dot until it's opened. The
box is not brought to the front (my call; dot only).

## Builder's calls

- The exact `classes.json` schema, file split, and how the conversion is organised.
- How windows are located (template, frame colour) and how glyphs are built for their
  digits.
- Tag wording and exact sizes, within the look of the EXP and Path tabs.
- Where `ap_advice` / `sp_advice` live (expected: `tools/class_helper/plan.py`).
- Tie-breaks when more than 3 maps fit a level.

## Calls I made (owner to check)

- Up to 3 training maps on the tab.
- Job advance shows from 2 levels before.
- Level-up shows a dot only; the box doesn't come forward.
- Remembered stats and skill levels last for the session only.
- Steps blocked by a prerequisite are skipped until it's met.
- Guide maps missing from `maps.json` show without Go.
- Scrolled-out skill rows: "scroll the list once" until every earlier step is known.
- The Sindit AP reset shows as a "next step" line, never as a mark.

## Docs to update

`AGENTS.md` Layout (`tools/class_helper/`, the two readers, `data/classes.json`; drop the
class helper from "Planned"); `README.md` status and the credit lines.
