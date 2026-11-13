# Overlay redesign and README screenshots

Two pieces, in this order:

1. **Overlay redesign:** a calmer Class tab built around "go train here", and one shared
   look for every tab (colours, buttons, text size).
2. **README screenshots:** real in-game shots of the redesigned overlay, taken with the
   owner playing, added to the README.

The screenshots wait for the redesign, so they show what people will download.

## Why

MapleLens is public on GitHub, and that's where new players find it. The README has no
pictures, so a visitor can't see what it does. The overlay itself has grown one tool at a
time, and the Class tab shows it most. At Rogue Lv 28 it's 18 lines of same-size text, says
"At 30: become an Assassin or a Bandit" twice, and puts a build dropdown above the class
and level. The owner finds it overwhelming. Asked what they most want from it mid-game,
they said: **where to go train**.

## Goals

- The Class tab answers "where should I train now?" at a glance, and one click starts the
  route there.
- Every tab follows the same visual rules, so yellow means "do this" and stands out again.
- Fix the visible defects the review found (below).
- The README shows MapleLens running over the game: one picture at the top, one per tool.

## Non-goals

- No new features, settings or tools. In particular there's no compact or collapsed box mode
  and no colour theme setting.
- The History window keeps its plain table look (my call: it's a normal desktop window,
  not part of the overlay).
- No change to readers, map data or class data, except fixing a reader bug if the Ellinia
  investigation (below) finds one.
- The GitHub social preview image stays as it is.

## Anti-goals (a failure even if it works)

- Any tab ends up taller than it is today, or the box changes width when you switch tabs.
- Yellow ends up on plain information again.
- Anything takes keyboard focus away from the game. Clickable rows keep `Qt.NoFocus`, as
  the buttons do today.
- Anything that breaks the screen-reading-only rule (AGENTS.md).

## Part 1: the overlay

### Shared look (`overlay.py`)

These rules apply to every tab:

| Role | Look | Used for |
|---|---|---|
| **Do this** | `ACCENT` yellow `#ffcc33` | selected tab underline, primary button, AP/SP chip, the job-advance row's outline, the path arrow, the "add here" ring on class marks, the tab's level-up dot, the update notice |
| **For your information** | label grey, prefixed with `ⓘ` (`#7fa8ff`) | why something isn't available: map not in the list, no route, no arrow on this map, no minimap, can't read the stat or skill window |
| **Label** | 10 pt (was 9), `#aebdd3` (was `#9fb0c8`) | every grey label in the box's tabs. Box only: the AP/SP marks over the game's windows (`_Mark`) keep 9 pt, so `LABEL_PT` doesn't simply change in place (my call) |
| **Value** | unchanged: 12 pt bold white | |

- **Two kinds of button**, defined once in `overlay.py` and used by every tool:
  - *Primary*: yellow filled with dark text (`#2a1d00`), bold, 4 px radius. Start, and the
    clickable rows' `›`, use this colour.
  - *Secondary*: transparent with a 1 px `#3d4b63` outline and light text. History and Stop
    use this. No tool keeps the default Windows-grey button.
- **The box background** gets slightly darker, `QColor(16, 18, 24, 224)` (was
  `20, 20, 24, 200`), with a 1 px `rgba(255,255,255,0.08)` edge.
- **Text fields** (the Path search) have a neutral `#3d4b63` border, which turns yellow only
  while you type in the field.
- Each tool has its own copy of the styles and colours (`_FIELD`, `_DARK`, `_HERE_BG` in
  `path_arrow/ui.py` and `class_helper/ui.py`). These move into `overlay.py`, so every tool
  uses the same set.
- An instruction to act stays yellow, for example "Open your minimap to see the arrow" and
  "Hidden portal: stand on it and press ↑". Explanations become the grey `ⓘ` style. The rule
  for any message *in a tab* not named here: if the player can fix it right now with one
  action, it's yellow; otherwise it's `ⓘ`. The box's status line ("Looking for
  MapleStory…", the Screen Recording messages) and the About view keep their look (my call).
- **Map names in the box are the short name**, the part after the last " / " (as
  `MapInfo.name` already is on the Path tab). They're elided to one line, with the full
  title as the tooltip. This applies to the Class rows, the advance row's sub-line and the
  footer (my call: full titles wrap to two or three lines at this width).

### Class tab

Mockup: `.superpowers/brainstorm/24712-1794134804/content/class-tab-v2.html` (local, not
committed). Top to bottom:

1. **Header row:** `"{job} · Lv {level}"` in label grey on the left. On the right, when there
   are points to spend, a yellow chip on a dark amber background (`#3a2e08`): `5 AP`, `3 SP`,
   or `5 AP · 3 SP`. With no points to spend, there's no chip.
2. **Job advance ready** (only when `level >= advance.level`): a row with a yellow 1 px
   outline. It reads "Job advance is ready" in bold, then "{NPC} · {map name}" as a grey
   sub-line. Clicking it starts the route to that map, through the same `go` callback the
   rows use today. With no map, it isn't clickable and has no `›`.
3. **"Train here · click to go":** the rows from `training(plan, level)` that have a place,
   still at most `MAX_MAPS` (3), in the guide's order (my call: they aren't re-sorted by
   rate). Each row has the map name and a grey sub-line, and the whole row is the click
   target. A row with no `map_id` isn't clickable and has no `›`.
   - A row where the player has trained before (`best_rate` returns a value) has the sub-line
     `your best · {rate:,.0f}/min`. The row with the highest rate is **bold on a highlighted
     background** (`#2c3a50`).
   - Any other row shows `mobs Lv {a}–{b}`.
   - The row's level range ("Lv 20–30") is dropped, since every row shown already covers your
     level.
   - **While the job advance row shows**, it has the `#2c3a50` fill as well as the yellow
     outline, and no training row is highlighted. There are still up to 3 rows, as in the
     approved mockup's Lv 30 view.
   - **No spots for this level** (the Beginner plan has none, and neither has a 1st job past
     30 that hasn't advanced): the heading stays, with one `ⓘ` line, `No training spots in
     the guide for Lv {level}` (my call).
4. **"Next" footer**, under a thin divider: the upcoming milestones, sorted by level, one line
   each, starting with `Lv {n} ·`:
   - `Advance: {jobs}` (from `plan.advance_for(build)`), when the advance isn't ready yet
   - `Gear: {item}` (the next gear row). If `short()` reports missing stats, add a grey
     sub-line such as `3 DEX short`. If the gear row has a place, clicking it starts the route
     there, as the training rows do.
   - `Reset AP for the {build} build`, when `build.reset_at` is still ahead

   (My call: the approved mockup had an "At Lv 30" heading. Putting the level on each line
   handles milestones at different levels, and `Lv N` is still the first thing you read.)
   The "Now: {current gear}" line is dropped. When the advance is ready, the footer leaves
   the advance out.
5. **Hints**, last, each one small line in the `ⓘ` style: "Open your stat window once"
   (only while the AP chip can't be filled), can't read the stat or skill window, and
   "{tier} tab: {n} SP to place".

**Removed from the tab:**
- The build dropdown. It moves into the ••• menu as a submenu, `Build: {name} ›`, listing
  the current plan's builds. The submenu only shows when the plan has more than one build.
  Picking a build saves it to `class_builds` as today.
- The "AP/SP marks on game windows" checkbox. The ••• menu item already does this, and the
  owner chose the menu only.
- The separate "Next step" line, which duplicated the advance line. `next_step()` may
  become unused. If it does, delete it and its tests.
- Every Go button.

**States that stay:** "Can't read your class yet" and "No plan for {job} yet" are still the
only content when they apply, now in the `ⓘ` style. The level-up dot on the tab works as
today.

**Defects to fix (must not come back):**
- The box gets wider when you're on the Class tab (223 px at Rogue 28 and 302 px at Beginner
  8, against 210 for the others). Every tab must keep the box exactly the same width in every
  state.
- At Beginner Lv 8, wrapped text overlaps ("Dances with Balrog…" is drawn over "At 10:
  become a Warrior"). The cause is wrapped labels next to buttons. Rows must lay out
  without overlap.
- The marks checkbox text is cut off ("…game windov"). Moving it to the menu fixes this.

### EXP tab

Same content. History becomes a secondary button. The new label size and colour apply.

### Path tab

- Start is the primary button, and Stop and the search field follow the shared rules.
- **One honest message:** in Ellinia the owner saw the header "From: (can't read your map
  yet)" and the yellow line "This map isn't in MapleLens's map list yet" at the same time. The
  second line needs a map title that was read but not matched, so the header is wrong
  whenever that happens. When a title was read but isn't in the data, the header shows the
  title it read (`From: {read title}`). The line under it becomes
  `ⓘ Not in the map list yet, so no route from here`.
- **Investigate Ellinia:** "Victoria Road / Ellinia" *is* in `maps.json` (id `010002000`),
  so a match should have been found. The installed copy the owner ran may be older than
  `main` (it had no Class tab). First reproduce on the current code with a fresh fixture
  (`scripts/grab.py`). If the title reader or `find` is at fault, fix it as a separate commit
  with a fixture test. If it doesn't reproduce, note that and move on. The investigation
  doesn't block Part 1. If the owner can't stand in Ellinia for the fixture when it's needed,
  ship the header and message fix and leave the investigation as a follow-up (my call).

### Testing

- `tests/test_class_ui.py` changes to match the new tab: rows in place of Go buttons, the chip,
  the advance row, the footer, the build submenu and no checkbox. Add a test that the box
  width is the same on every tab in at least these states: Rogue 28, Beginner 8, and no
  class read.
- Keep the existing `uv run pytest`, `ruff` and screen-only guard green.
- Before calling it done, draw every tab offscreen (`QWidget.grab()` on the box, the way the
  design review did) for Rogue 28, Beginner 8, Hunter 34, Lv 30 with the advance ready, and
  the Path tab while choosing and while running. Look at the images. The owner sees them
  too.

## Part 2: README screenshots

Taken after Part 1 is merged, running the redesigned code (from source is fine) with the
owner in the game at 1920×1080 windowed.

### Taking them

The game capture (`capture.grab`) leaves MapleLens's own windows out on purpose, so README
shots grab the screen instead. Add a `--screen` flag to `scripts/grab.py` (my call: a flag on
the existing script rather than a new one). With it, the script finds the game window as it
does now and saves the screen area over its client rect, overlay included, using Qt's
`QScreen.grabWindow(0)` cropped by the client rect (per-monitor DPI aware: Qt keeps each
screen's native top-left, and its size is in logical px). A throwaway version of this was
tested during the design and gave a correct 1920×1080 crop on a 2560×1440 screen at 125%.

The owner sets up each shot in the game and says when it's live. Claude then runs the grab.

| # | Shot | What's on screen |
|---|---|---|
| 1 | **Top picture** | A normal Victoria route running, the Path tab showing the numbered route list, and the arrow clearly visible over the character, with the minimap open |
| 2 | **EXP** | The EXP tab with real numbers after a few minutes of hunting, with the History window open beside the box |
| 3 | **Class** | The Class tab, plus the stat and skill windows open with their marks showing |

Ask the owner to make the chat box as small as possible before each shot.

### Privacy (must)

Never commit character names, chat, or other players' names (AGENTS.md). Before anything is
saved under `docs/`, blur the character's name tag, the name in the bottom status bar, any
other player's name, and anything left of the chat. Show the owner each final image before
committing it.

### Into the README

- Images go in `docs/screenshots/` as PNGs: `hero.png`, `exp.png`, `path.png`,
  `class.png`. Crop each one to what it's showing, with the hero at most 1600 px wide. Keep
  each file under about 1 MB so the README loads fast.
- The hero goes right under the intro paragraph, before the status note.
- A new short **What it does** section goes before "The promise", with one image and a
  one-line caption per tool.
- Alt text describes what's shown, for example "MapleLens's path arrow over the character,
  with the route list in the box".

## Left to the builder

- Exact spacing, paddings and row heights, as long as no tab gets taller than today.
- How the shared button and field styles are expressed in `overlay.py` (a stylesheet string,
  helper functions, or both).
- Whether the Class rows are `QPushButton`s, custom widgets, or labels with a click handler,
  as long as they never take focus.
- How the hero and per-tool images are cropped.

## Calls made during the design (for the owner to check)

- The training spots stay in the guide's order; the best one is highlighted, not moved.
- The footer puts `Lv N ·` on each line instead of one "At Lv 30" heading.
- The History window keeps its look.
- The screen grab is a `--screen` flag on `scripts/grab.py`.
- Map names are the short name, elided to one line.
- With no training spots for the level, an `ⓘ` line says so; the heading stays.
- The bigger label size is for the box only; the marks over the game's windows keep 9 pt,
  and the status line and About keep their look.
- The Ellinia investigation doesn't block Part 1.
