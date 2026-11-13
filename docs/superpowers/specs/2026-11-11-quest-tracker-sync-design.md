# MapleLens: follow the game's Quest Helper

Date: 2026-11-11. Status: draft, for the owner's review.
Issue: [or-keren/maplelens#65](https://github.com/or-keren/maplelens/issues/65).
Builds on the quest helper design (`2026-11-09-quest-helper-design.md`); everything there
holds unless this document changes it.

## Intent

The game has its own tracker: you follow a started quest and a small **Quest Helper**
panel shows it with its progress ("0 / 25 Torn Ledger Pages"). The owner follows quests
there, and expects MapleLens to follow the same ones without pressing MapleLens's Track
button too (owner: "as long as it's there the overlay will track the same").

MapleLens also reads the panel's progress. **A target that's done gets no row; once every
target is done, only the hand-in row is left** (owner). **When the quest leaves the
game's panel, MapleLens untracks it** (owner: "when the quest is done, it should untrack
it automatically"; owner agreed this applies whether it was handed in or just unfollowed).

The screen-only rule in `AGENTS.md` holds: MapleLens reads the panel's pixels. It never
clicks the panel's buttons or follows a quest for the player.

## What the panel looks like (grabs, 2026-11-11, 1920x1080)

Three grabs, in the owner's grabs folder (not committed): `tracker_1920x1080.png`,
`tracker2_1920x1080.png`, `tracker_min_1920x1080.png`.

- At the game window's top right by default (whether it can be dragged is unknown: check).
  Title bar **"Quest Helper (n/5)"**: n quests followed, 5 at most; an AUTO button, a
  −/+ (minimize) button, another button.
- Under it, one block per quest: the quest's name in bold (long names cut with "…", e.g.
  "A rainbow snail shell that makes…") with a ⓧ to unfollow, then one line per target:
  **"have / need Target"** ("0 / 30 Red Snail Shell"). Kill lines look the same with the
  monster's name (owner). The panel grows down a block per quest.
- The panel is see-through grey: the map shows behind dark text.
- **Minimized**: only the title bar is left, still "Quest Helper (3/5)", with + where −
  was.
- Only started quests can be followed (owner), so every quest in the panel is taken.
- A fully done quest stays in the panel ("30 / 30") until it's handed in (owner), so
  leaving the panel means handed in or unfollowed, never just done.
- With nothing followed the panel stays, as "Quest Helper (0/5)" (owner), so the last
  quest leaving is seen like any other: a **Read** panel with no blocks.

Checked against `data/quests.json`: all three names are there, and every target's text
matches our item's name exactly ("Torn Ledger Pages", "Rainbow-colored Snail Shell",
"Red Snail Shell"). "Donating to Kerning City" is one of 18 quests with that name; only
506119 asks for Red Snail Shell, so **the target lines tell apart quests that share a
name**, which the quest window can't.

Not seen yet: whether a done line changes colour (it keeps its numbers, so have ≥ need
works either way), the empty 0/5 panel, and a second resolution.

## Goals

- **Follow the game's panel.** A quest in the panel is tracked in MapleLens, added to the
  saved tracked list like a Track click. No click in MapleLens needed.
- **Progress hides what's done.** A target with have ≥ need is done. Done targets get no
  row; a quest with every target done shows only its hand-in row.
- **Untrack on leaving.** A quest that came from the panel and is no longer in a readable
  panel is untracked.
- **Warn when the panel can't be read** (owner): a small warning line in the Quests tab.
- **No panel, no change** (owner): when the panel isn't on screen, the Quests tab works
  exactly as it does today.

## Non-goals

- Clicking or following anything in the game (the screen-only rule).
- Showing the counts themselves ("12 / 30") in rows. The game's panel shows them; rows
  only drop what's done *(my call; not asked for)*.
- Saving progress across restarts. Progress lives in memory from the latest panel read
  *(my call)*.
- Switching the box to the Quests tab when the panel changes. Only the quest window
  switches it, as today.

## Anti-goals

- **Untracking a quest that's still followed.** A covered, half-read, minimized or
  briefly hidden panel must never untrack anything. When unsure, keep.
- **Hiding a row that isn't done.** A target's row is hidden only when a line was read and
  matched to it with have ≥ need.
- A tick slowed down by reading a panel that's on screen all the time.

## How it behaves

### Four states of the panel

| Panel | Tracked list | Rows | Warning |
|---|---|---|---|
| **Read**: found, every quest block read | panel's quests added; panel-origin quests not in it untracked (after the debounce below) | done targets hidden | none |
| **Minimized**: title bar with + | unchanged | last-read progress kept | none *(my call: the player chose it)* |
| **Unreadable**: found, but cut by the frame's edge, or fewer blocks read than its n, or a block garbled | unchanged: nothing added or untracked | last-read progress kept | yes |
| **Not there** | unchanged | as today: every row shown | none |

"Not there" drops the in-memory progress: once the panel is gone, rows are as today
(owner: "the behavior should be like it was up until now").

**Debounce** *(my call)*: a quest is untracked only after it's been missing from two
readings in a row where the panel was **Read**, the way one missed quest-window reading
is already forgiven. A minimized panel whose n drops (3/5 → 2/5) untracks nothing; it
waits until the panel is read open again.

**Warning text** *(my call, worded like the quest window's)*: "Can't read the game's
Quest Helper: move it fully into view", yellow when moving it would fix it (cut by the
frame's edge), grey otherwise, per the overlay's rule. One line, at the top of the
"Tracking" part.

### Which quests are "from the panel"

MapleLens keeps a second saved list, the quests it has seen in the panel
(`quests_followed` in `settings.json`, cleaned like `quests_tracked`). Only these are
untracked when they leave the panel. A quest tracked with MapleLens's own Track button and
never seen in the panel stays until its × (owner agreed). A Track-button quest that later
shows up in the panel becomes "from the panel" and leaves with it. × in MapleLens removes
a quest from both lists; if the panel still shows it, the next reading adds it back
*(my call: the panel is the source of truth while it's there)*.

### Matching a panel block to a quest

1. The name, as the quest window reader does: snap to the known names; a name cut with
   "…" must start exactly one known name.
2. When several quests have that name (or a cut name fits several), the target lines
   pick one: the quest whose targets match the lines' names and needs.
3. Each target line is matched to the quest's item or monster by name and need.

A block that was read but names no single quest doesn't make the panel Unreadable (moving
the panel wouldn't fix it); it's skipped, neither added nor untracked, with a grey ⓘ line
in the Tracking part *(my call)*:

- a name not in our data (an event quest, say): "<name>: not in MapleLens's list yet";
- a name its targets can't settle: "<name>: several quests have this name". Seven pairs in
  today's data have the same targets and differ only in their NPCs (Becoming a Citizen
  of Honor, Looking for a House, The Right to Own a Home, Matters of the Heart, A Memory
  of Iron, A Heart of Stillness and Wood, The Sage's Burden).

Only a block that couldn't be read (its name or lines garbled) makes the panel
**Unreadable**.

### Rows with progress

The rows are today's (`plan.targets`), filtered by progress. Every followed quest is taken,
so it never has a giver row.

- A **monster row** carries the monster and the quest items it drops. Each part that's
  done drops out of the row's title; the row goes when all its parts are done *(my call)*.
- An **item row** goes when its item is done.
- The **hand-in row** always stays. With every target done, it's the quest's only row.
- A target with no matching line, or a line that didn't read, counts as not done.

Progress applies wherever the quest's rows show: in the Tracking part, and in the top part
when the same quest is also open in the quest window *(my call)*.

## The parts

### 1. Panel reader (spike first)

`readers/quest_tracker.py`: frame → the panel's state: not there, minimized (with n),
unreadable, or read: n, and per block the name as read and its lines (have, need, target
text). A pure function, tested on cropped fixture PNGs like every reader. `Reading` gains a
field and `read_all` fills it.

Spike before building on it:
- Fixtures from the three grabs, cropped to the panel. The owner reviews every PNG before
  commit.
- More grabs as the owner plays: a target done and a quest fully done, a kill quest, five
  quests, the empty 0/5 panel, and a second resolution.
- How the reader finds the panel and its height (the window helpers in `window.py` assume a
  fixed size; this panel grows), how it reads a see-through panel, and how it stays cheap
  when the panel is on screen every tick (the quest window is open only sometimes; this one
  usually is), are the builder's.

If the names or numbers can't be read reliably on a see-through panel, stop and bring it
back to the owner.

### 2. Matching (pure)

In `tools/quest_helper/plan.py` (or beside it): a read block → quest id (the rules above),
and a quest's rows filtered by its progress. Unit tests on the hand-made fixture data, as
today.

### 3. The tab

`QuestHelperTool.update` takes the panel's reading: adds and untracks per the states table,
keeps the last progress, and draws the warning and ⓘ lines. Settings gain
`quests_followed`.

## Docs to update

- `AGENTS.md` Layout: `readers/quest_tracker.py`.
- `README.md`: one line on the Quests tab following the game's Quest Helper.
- Close issue #65 from the PR.

## Done means

With the game windowed or borderless, the owner can:

1. follow a quest in the game and see it in the Quests tab, without clicking MapleLens;
   restart MapleLens and still see it;
2. finish a target and see its row go; finish them all and see only the hand-in row;
3. hand the quest in (or unfollow it) and see it leave the Quests tab, the last one too;
4. minimize the panel and see nothing change; move it half off screen and see the warning,
   with nothing untracked;
5. close the panel and see the tab behave as it does today;
6. follow a "Donating to Kerning City" quest and see the right one's rows.

`uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and the guard pass.

## Left to the builder

The reader's method, offsets, colours and OCR details; how it finds a panel of varying
height; keeping the per-tick cost low; where the matching code lives; the warning's exact
wording.
