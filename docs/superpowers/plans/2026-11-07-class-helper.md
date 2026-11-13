# Class Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Class tab with training maps, gear, the next job advance and a "next step" line, and marks on the game's own stat and skill windows that show where unspent AP and SP go. All of it is computed from our own `classes.json`.

**Architecture:** Two new pure readers (`stat_window`, `skill_window`) join `read_all`. A new tool, `tools/class_helper/`, holds the data loader (`data.py`), the pure plan maths (`plan.py`), and the tab plus the marks on the `Layer` (`ui.py`). `app.py` gives the tool a `go(map_id)` callable, which starts the path arrow, and a `best_rate(title)` lookup into the EXP history. The tool imports neither of the other tools.

**Tech Stack:** Python 3.12, PySide6, OpenCV + numpy (glyph templates), the system OCR (`readers/ocr.py`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-06-class-helper-design.md`

## Global Constraints

- Screen-only (`AGENTS.md`). Marks are drawn only on MapleLens's own `Layer` (`WindowTransparentForInput`), so clicks pass through to the game. Nothing sends input. Run `uv run python scripts/check_screen_only.py` after every task.
- No new dependency. Never write the guard's banned module or Win32 names in comments under `src/` or `scripts/`.
- Readers are pure functions `screenshot -> value`, tested on PNG fixtures. Like the level reader (R17), they return `None` and never a wrong value.
- Tools don't import each other. `tools/class_helper/` imports only `readers`, `overlay`, `store` and its own modules.
- Fixtures: cropped to the window, never the full screen. Paint over the character name, chat and other players. Filenames carry resolution and scale, e.g. `stat_a_1366x768_100.png`.
- Data holds facts only (targets, IDs, level ranges). It never holds meowdb wording, and no meowdb file is downloaded or shipped. Each record keeps its `source` guide URL.
- Guide pages are read once, outside the repo, with an honest User-Agent naming MapleLens, at most one request every 10 s, stopping on 403/429. The conversion notes and any converter stay out of the repo.
- Up to 3 training maps. Job advance shows from 2 levels before it's due. A level-up shows only a dot; the box never comes forward.
- Remembered stats and skill levels last for this session only. Only the build choice is saved, in `settings.json` under `class_builds`.
- No free text: every line on the tab comes from data plus the fixed strings named in this plan.

## Calls made in this plan (owner to check)

- **Expected AP and SP come from the window's own total**, not from "5 AP / 3 SP per level since the advance". The total is the points spent plus the unspent points, as read. That total is then spread over the plan. A late job advance or rolled starting stats can't make up a false "behind". It also means the SP maths no longer depends on how many SP an advance grants. The spec's in-game check (Task 1) is narrowed to one question: is the skill window's SP count per tab or shared?
- **The open skill tab is the job its rows match.** The tab strip's graphics are not read. If rows match skills of two different jobs, the window counts as unreadable.
- **The skills and items tables live in `classes.json`**, copied from OSMS at conversion time. That way the ID checks run offline.
- **The AP/SP badge** shows the remembered unspent points only while the level is still the one they were read at. Otherwise the badge is left out instead of guessed.
- **"Thief" reads as "Rogue"** (`ALIASES` in `data.py`). The status bar shows "Rogue" (`job_a_*` fixtures).

## Review Focus

1. **Switching to another character.** When the read job changes, or the level drops, the remembered stats, skill levels and badge are forgotten. The tab never shows one character's stats for another. Test: Task 8, `test_character_switch_forgets`.
2. **Class OCR flickering to `None` for a tick.** The tab keeps the last job. It doesn't blank out, reset the build picker or show a level-up dot. Test: Task 8, `test_job_flicker_keeps_tab`.
3. **A window dragged or closed between ticks.** The marks move with it or hide. They never stay at the old spot. Test: Task 9, `test_marks_follow_and_hide`.
4. **A job with no record** (3rd job at 70+, a class not yet converted). The tab says "No plan for Hermit yet", no marks show and nothing raises. Test: Task 8, `test_no_plan_for_job`.
5. **A saved build name the data no longer has.** It falls back to the main build without a crash. Test: Task 2, `test_unknown_build_falls_back_to_main`.

---

### Task 1: Owner prep: fixtures and the SP pool check (no code)

The readers (Tasks 6 and 7) can't start until this is done. Tasks 2 to 5 don't depend on it.

- [ ] **Step 1: Confirm the SP pool in game.** With a 2nd-job character that has unspent SP, open the skill window and switch between the 1st- and 2nd-job tabs. Does the SP count change between tabs (per tab) or stay the same (shared)? Write the answer into the spec's "SP in Classic" decision. If the pool is **shared**, stop: Task 9's "N SP to place" line and its mark rule must be re-planned first.
- [ ] **Step 2: Grab the stat window** with `uv run python scripts/grab.py --title MapleStory --label stat` at 1366×768, 1920×1080, 2560×1440 and on the Mac (2732×1536). Crop each grab to the window plus a few px of margin, saved under `tests/fixtures/screens/`. For each resolution, save:
  - `stat_a_<res>_100.png`: the full window with unspent AP > 0, plus one stat that has an equipment bonus (e.g. `25 (20+5)`)
  - `stat_covered_<res>_100.png`: another window over part of the stat rows
  - `stat_edge_<res>_100.png`: the window half off the frame's edge
- [ ] **Step 3: Grab the skill window** the same way:
  - `skill_a_<res>_100.png`: 1st-job tab with unspent SP
  - `skill_b_<res>_100.png`: a tab scrolled down so the first rows are out of view
  - `skill_covered_<res>_100.png`
  - `skill_edge_<res>_100.png`
- [ ] **Step 4: Paint over the character name** in every stat-window crop, and over any chat line. Write down each fixture's true values: level, AP, base STR/DEX/INT/LUK; tab, SP, and each visible row's skill name and level. Tasks 6 and 7 copy them into `EXPECTED`.
- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/screens/stat_* tests/fixtures/screens/skill_* docs/superpowers/specs/2026-11-06-class-helper-design.md
git commit -m "test(fixtures): stat and skill window grabs; SP pool confirmed"
```

### Task 2: `classes.json` schema, loader and checks (owner's path first)

This task covers four records: Beginner, Rogue, Assassin and Bandit. The other 11 come in Task 10.

**Files:**
- Create: `src/maplelens/tools/class_helper/__init__.py` (empty), `src/maplelens/tools/class_helper/data.py`, `src/maplelens/data/classes.json`
- Create: `tests/test_class_data.py`, `tests/fixtures/classes_small.json`

**Interfaces:**
- Produces (`data.py`):
  - `DATA: Path` (→ `data/classes.json`), `MAPS: Path` (→ `data/maps.json`), `ALIASES = {"Thief": "Rogue"}`, `STATS = ("STR", "DEX", "INT", "LUK")`
  - `Place(map_id: str | None, name: str, title: str | None)`: `title` is `"Street / Name"` from `maps.json`; it is `None` when `map_id` is `None`
  - `Band(from_level: int, to_level: int, hold: dict[str, tuple[int, float]], rest: str)` with `targets(level) -> dict[str, int]`, where each target is `int(base + per_level * level)`
  - `SpStep(skill: int, up_to: int)`
  - `Skill(id: int, name: str, job: str, max: int, requires: dict[int, int])`
  - `Item(id: int, name: str, req: dict[str, int])`: `req` keys are `"level"` plus any of `STATS`
  - `TrainRow(place: Place, from_level: int, to_level: int, mobs: tuple[int, int])`
  - `GearRow(item: Item, from_level: int, where: Place | None)`
  - `Advance(level: int, next_jobs: tuple[str, ...], npc: str | None, where: Place | None)`
  - `Build(name: str, ap: tuple[Band, ...], sp: tuple[SpStep, ...], gear: tuple[GearRow, ...], reset_at: int | None, advance: Advance | None)`
  - `JobPlan(job: str, tier: int, from_level: int, source: str, training: tuple[TrainRow, ...], advance: Advance | None, builds: tuple[Build, ...])` with `build(name: str | None) -> Build` (an unknown name or `None` gives `builds[0]`) and `advance_for(build) -> Advance | None` (`build.advance or self.advance`)
  - `ClassData(jobs: dict[str, JobPlan], skills: dict[int, Skill], items: dict[int, Item])` with `plan(job: str | None) -> JobPlan | None` (applies `ALIASES`)
  - `load(path: Path = DATA, maps_path: Path = MAPS) -> ClassData`, cached per path pair
- JSON shape (IDs are strings in JSON and ints in Python; map IDs stay strings):

```json
{
  "skills": {"4000000": {"name": "Nimble Body", "job": "Rogue", "max": 20, "requires": {}}},
  "items": {"1472000": {"name": "Garnier", "req": {"level": 10, "LUK": 25}}},
  "jobs": [{
    "job": "Rogue", "tier": 1, "from_level": 10,
    "source": "https://meowdb.com/msclassic/guides/<slug>",
    "advance": {"level": 30, "next_jobs": ["Assassin", "Bandit"], "npc": "Dark Lord", "map_id": "103000003"},
    "training": [{"map_id": "103000101", "from_level": 10, "to_level": 15, "mobs": [8, 12]},
                 {"map_id": null, "name": "A map not in maps.json", "from_level": 15, "to_level": 21, "mobs": [15, 18]}],
    "builds": [{
      "name": "LUK", "reset_at": null,
      "ap": [{"from": 10, "to": 200, "hold": {"DEX": 25}, "rest": "LUK"}],
      "sp": [{"skill": 4000000, "up_to": 3}],
      "gear": [{"item": 1472000, "from_level": 10, "map_id": null}]
    }]
  }]
}
```

  A `hold` value is either an int (fixed) or `{"base": b, "per_level": p}`. A build may carry its own `"advance"`, as Beginner's "heading for" builds do. (The IDs above only show the shape. Use the real ones.)

- [ ] **Step 1: Write the loader tests** in `tests/test_class_data.py` against `tests/fixtures/classes_small.json`. That file is hand-made: one job `"Rogue"` with two builds `"LUK"` and `"Sindit"`, map IDs `000000001`/`000000010`, a growing hold `{"base": 0, "per_level": 1}` and a `null` map row. Load it with `load(SMALL, MAPS)`.

```python
def test_aliases_and_titles():
    d = load(SMALL, MAPS)
    assert d.plan("Thief") is d.plan("Rogue")
    assert d.plan("Hermit") is None and d.plan(None) is None
    row = d.plan("Rogue").training[0]
    assert row.place.title == "Maple Road / Mushroom Town - West Entrance"


def test_missing_map_keeps_its_name_and_no_title():
    row = load(SMALL, MAPS).plan("Rogue").training[1]
    assert row.place == Place(None, "A map not in maps.json", None)


def test_unknown_build_falls_back_to_main():
    p = load(SMALL, MAPS).plan("Rogue")
    assert p.build("Gone") is p.builds[0] and p.build(None) is p.builds[0]
    assert p.build("Sindit").name == "Sindit"


def test_band_targets_grow_with_level():
    band = load(SMALL, MAPS).plan("Rogue").build("Sindit").ap[0]  # hold DEX base 0, per_level 1
    assert band.targets(30) == {"DEX": 30}
```

- [ ] **Step 2: Write the data checks** in the same file. Each one runs against the shipped `DATA` and fails with the offending ID or job in its message:
  - `test_every_map_id_is_in_maps_json`: covers training, gear `where` and advance `where`; a `null` `map_id` must come with a `name`
  - `test_every_plan_skill_is_known_and_on_its_tab`: each `SpStep.skill` is in `skills`, that skill's `job` is the record's job, and `up_to <= max`. Each `requires` key is in `skills`.
  - `test_skill_names_are_unique`: the skill window matches rows by name
  - `test_every_gear_item_is_known`
  - `test_bands_cover_from_level_to_200`: per build, the bands are sorted and contiguous, with the first `from` equal to the record's `from_level` and the last `to == 200`. `rest` is not in `hold`, and every key is in `STATS`.
  - `test_records_cover_the_owners_path`: `{"Beginner", "Rogue", "Assassin", "Bandit"} <= set(load().jobs)`
- [ ] **Step 3: Run the tests.** `uv run pytest tests/test_class_data.py -v`. Expected: FAIL (`ModuleNotFoundError: maplelens.tools.class_helper`).
- [ ] **Step 4: Implement `data.py`.** It reads `maps.json` with `json` only, as `readers/map_name.known_titles` does, and never imports `tools.path_arrow`.
- [ ] **Step 5: Convert the four records** into `src/maplelens/data/classes.json`. Sources are the meowdb beginner, Rogue (thief), Assassin and Bandit guides, read under the Global Constraints rule. IDs, max levels, prerequisites, item requirements and monster levels come from `https://osmsdataexplorer.com/data/api/v1/`. Only skills and items that a plan names go in the tables, plus every skill of each converted job, since the skill window matches against them. Bandit gets the main build plus "Sindit", with `reset_at` at the guide's level. Beginner gets one build per class it can head for, each with its own `advance`.
- [ ] **Step 6: Run the tests.** `uv run pytest tests/test_class_data.py -v`. Expected: PASS.
- [ ] **Step 7: Commit**

```bash
git add src/maplelens/tools/class_helper src/maplelens/data/classes.json tests/test_class_data.py tests/fixtures/classes_small.json
git commit -m "feat(class_helper): classes.json loader and checks, owner's path converted"
```

### Task 3: `ap_advice`

**Files:**
- Create: `src/maplelens/tools/class_helper/plan.py`, `tests/test_class_plan.py`

**Interfaces:**
- Consumes: `Band`, `Build`, `STATS` (Task 2)
- Produces: `Advice(add: int = 0, over: int = 0, behind: int = 0)` (frozen dataclass), `band_at(build: Build, level: int) -> Band | None`, `ap_advice(band: Band, level: int, stats: dict[str, int], unspent: int) -> dict[str, Advice]` (a key for each of `STATS`)

- [ ] **Step 1: Write the failing tests.** `B` is `Band(1, 200, {"DEX": (25, 0.0)}, "LUK")`. Stats are written `s(str, dex, int, luk)`.

```python
def test_holds_fill_first_then_the_main_stat():
    a = ap_advice(B, 20, s(4, 20, 4, 30), 10)
    assert a["DEX"] == Advice(add=5) and a["LUK"] == Advice(add=5)
    assert a["STR"] == a["INT"] == Advice()


def test_over_a_hold_puts_the_main_stat_behind():
    a = ap_advice(B, 20, s(4, 35, 4, 20), 0)
    assert a["DEX"] == Advice(over=10) and a["LUK"] == Advice(behind=10)


def test_short_points_still_go_to_the_hold_first():
    a = ap_advice(B, 20, s(4, 20, 4, 30), 3)
    assert a["DEX"] == Advice(add=3, behind=2) and a["LUK"] == Advice(over=2)


def test_stats_outside_the_plan_never_get_points_or_tags():
    a = ap_advice(B, 20, s(4, 25, 9, 30), 5)  # INT rolled 9 at the start
    assert a["INT"] == Advice() and a["LUK"] == Advice(add=5)


def test_growing_hold_and_band_lookup():
    grow = Band(1, 200, {"DEX": (0, 1.0)}, "LUK")
    assert ap_advice(grow, 30, s(4, 28, 4, 40), 2)["DEX"] == Advice(add=2)
    build = Build("x", (Band(1, 29, {}, "LUK"), grow), (), (), None, None)
    assert band_at(build, 29).to_level == 29 and band_at(build, 30) is grow
```

- [ ] **Step 2: Run the tests.** `uv run pytest tests/test_class_plan.py -v`. Expected: FAIL (import error).
- [ ] **Step 3: Implement `ap_advice`** with this algorithm (the tests don't fully pin it):

```python
plan = [*band.hold, band.rest]
budget = sum(stats[k] for k in plan) + unspent  # points the plan's stats share
expected, left = {}, budget
for k, target in band.targets(level).items():  # holds in data order
    expected[k] = min(target, left)
    left -= expected[k]
expected[band.rest] = left
adds, left = {}, unspent
for k in plan:  # holds first, the rest last
    adds[k] = min(max(0, expected[k] - stats[k]), left)
    left -= adds[k]
# over = max(0, stats - expected); behind = max(0, expected - stats - add); stats outside the plan: Advice()
```

- [ ] **Step 4: Run the tests.** `uv run pytest tests/test_class_plan.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(class_helper): ap_advice`.

### Task 4: `sp_advice`

**Files:**
- Modify: `src/maplelens/tools/class_helper/plan.py`, `tests/test_class_plan.py`

**Interfaces:**
- Consumes: `SpStep`, `Skill` (Task 2), `Advice` (Task 3)
- Produces: `sp_advice(steps: Sequence[SpStep], levels: dict[int, int], unspent: int, skills: dict[int, Skill], tab: str) -> dict[int, Advice] | None`
  - `levels` holds only the skills whose level is known (a read row at level 0 is known).
  - The result is `None` when the next point would go to a step whose skill isn't known. The UI then says "scroll the list once".
  - The result has a key for every known skill.
  - `over` and `behind` are filled only when every skill of `tab` (from `skills`) is known. Otherwise only `add` is set.
  - A known skill not in `steps` that has points gets `Advice(over=level)`. The UI tags it "off plan".

- [ ] **Step 1: Write the failing tests.** The skills are A=1 (max 3), B=2 (max 2, requires {1: 1}) and C=3 (max 1), all of job `"T"`. `STEPS = [SpStep(1, 1), SpStep(2, 2), SpStep(1, 3), SpStep(3, 1)]`.

```python
def test_points_go_to_the_first_unmet_steps():
    a = sp_advice(STEPS, {1: 0, 2: 0, 3: 0}, 3, SK, "T")
    assert (a[1].add, a[2].add, a[3].add) == (1, 2, 0)


def test_a_step_waits_for_its_prerequisite():
    a = sp_advice([SpStep(2, 2), SpStep(1, 1)], {1: 0, 2: 0, 3: 0}, 2, SK, "T")
    assert (a[1].add, a[2].add) == (1, 1)


def test_off_plan_points_show_and_the_plan_falls_behind():
    sk = {**SK, 4: Skill(4, "D", "T", 5, {})}
    a = sp_advice(STEPS, {1: 0, 2: 0, 3: 0, 4: 2}, 0, sk, "T")
    assert a[4] == Advice(over=2) and a[1] == Advice(behind=1) and a[2] == Advice(behind=1)


def test_unknown_earlier_skill_needs_a_scroll():
    assert sp_advice(STEPS, {2: 0, 3: 0}, 1, SK, "T") is None


def test_unknown_later_skill_still_marks_without_tags():
    a = sp_advice(STEPS, {1: 0, 2: 0}, 3, SK, "T")
    assert (a[1], a[2]) == (Advice(add=1), Advice(add=2))


def test_finished_plan_places_nothing():
    a = sp_advice(STEPS, {1: 3, 2: 2, 3: 1}, 2, SK, "T")
    assert all(v == Advice() for v in a.values())
```

- [ ] **Step 2: Run the tests.** `uv run pytest tests/test_class_plan.py -v -k "step or plan or skill or points"`. Expected: FAIL.
- [ ] **Step 3: Implement `sp_advice`.** Both the adds and the expected levels come from one walk, which gives one point at a time to the first step that is unmet and whose prerequisites are met:

```python
def _walk(steps, levels, points, skills):  # -> dict | None (None: next point hits an unknown skill)
    lv = dict(levels)
    for _ in range(points):
        step = next(
            (
                s
                for s in steps
                if lv.get(s.skill, -1) < s.up_to
                and all(lv.get(r, 0) >= n for r, n in skills[s.skill].requires.items())
            ),
            None,
        )
        if step is None:
            break
        if step.skill not in lv:
            return None
        lv[step.skill] += 1
    return lv
```

  adds = `_walk(steps, levels, unspent)` minus `levels`. When the tab is fully known, expected = `_walk(steps, {k: 0 for k in tab skills}, sum(levels.values()) + unspent)`, and over/behind follow as in Task 3.
- [ ] **Step 4: Run the tests.** `uv run pytest tests/test_class_plan.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(class_helper): sp_advice`.

### Task 5: Tab content: training, gear, advance, next step

**Files:**
- Modify: `src/maplelens/tools/class_helper/plan.py`, `tests/test_class_plan.py`

**Interfaces:**
- Consumes: `JobPlan`, `Build`, `TrainRow`, `GearRow`, `Item`, `Advance` (Task 2)
- Produces: `MAX_MAPS = 3`, `ADVANCE_EARLY = 2`
  - `training(plan: JobPlan, level: int) -> list[TrainRow]`: rows whose band contains `level`, in guide order, at most `MAX_MAPS`
  - `gear(build: Build, level: int) -> tuple[GearRow | None, GearRow | None]`: `now` is the last row with `from_level <= level`; `next` is the first row after it
  - `short(item: Item, stats: dict[str, int] | None) -> dict[str, int]`: the missing points per stat; empty when `stats` is `None`
  - `advance_due(plan: JobPlan, build: Build, level: int) -> Advance | None`: shown once `level >= adv.level - ADVANCE_EARLY`
  - `advance_text(adv: Advance) -> str`, e.g. `"At 30: become an Assassin or a Bandit"`
  - `next_step(plan: JobPlan, build: Build, level: int) -> str | None`

- [ ] **Step 1: Write the failing tests** against `classes_small.json`, extended with as many training rows as these tests need (keep them in data order), two gear rows ("First Claw" at 10, "Second Claw" at 15, needing DEX 30) and an advance at 30 to `["Assassin", "Bandit"]`. Sindit gets `reset_at: 30`.

```python
def test_up_to_three_maps_in_guide_order():
    rows = training(ROGUE, 12)
    assert len(rows) <= 3 and all(r.from_level <= 12 <= r.to_level for r in rows)


def test_gear_now_next_and_shortfall():
    now, nxt = gear(ROGUE.build("LUK"), 12)
    assert (now.from_level, nxt.from_level) == (10, 15)
    assert short(nxt.item, {"STR": 4, "DEX": 25, "INT": 4, "LUK": 40}) == {"DEX": 5}
    assert short(nxt.item, None) == {}


def test_advance_shows_two_levels_early():
    assert advance_due(ROGUE, ROGUE.builds[0], 27) is None
    assert advance_due(ROGUE, ROGUE.builds[0], 28).level == 30
    assert advance_text(advance_due(ROGUE, ROGUE.builds[0], 31)) == (
        "At 30: become an Assassin or a Bandit"
    )


def test_next_step_is_the_nearest_milestone():
    assert next_step(ROGUE, ROGUE.build("LUK"), 12) == "At 15: get Second Claw"
    assert next_step(ROGUE, ROGUE.build("LUK"), 16) == "At 30: become an Assassin or a Bandit"
    assert next_step(ROGUE, ROGUE.build("Sindit"), 29) == "At 30: become an Assassin or a Bandit"
    assert next_step(ROGUE, ROGUE.build("Sindit"), 30) == "Now: become an Assassin or a Bandit"
```

  The tie at 30 goes to the advance. Order on a tie: advance, gear, reset. The reset reads `"At N: reset AP for the Sindit build"`. A milestone already due reads `"Now: …"` instead of `"At N: …"`. Article: "an" before a vowel, "a" otherwise.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement the five functions** in `plan.py`.
- [ ] **Step 4: Run the tests.** `uv run pytest tests/test_class_plan.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(class_helper): training, gear, advance and next-step lines`.

### Task 6: Stat window reader

**Why this reader differs from the status-bar readers (measured on the owner's 2026-11-08 grabs):** the game draws its windows at screen-pixel positions, so after `glyphs.normalize` a draggable window's glyphs come out differently at each sub-pixel offset (15 offsets per axis at 1440, 45 at 1080). Exact-mask glyph templates fail at most positions. Two fixes, both proven in a prototype on every grab:
1. **Window-aligned scaling.** Find the window coarsely on the normalized frame. Then try each native start `(int(ox*s)+kx, int(oy*s)+ky)` for `kx, ky in range(-ceil(2s), ceil(2s)+1)`, scale that native crop by exactly `1/s` (`cv2.resize(c, None, fx=1/s, fy=1/s, interpolation=cv2.INTER_AREA)`; never a rounded `dsize`: the 0.13% error drifts 0.4 px down the window at 1080), and keep the start whose title scores best **at its exact spot** (no search slack). At 768 (`s == 1`) this is the plain crop.
2. **Correlated digits with a margin.** On that 768-scale window image, slide each glyph template (grey, 1 px of background around the ink, 13 rows) along the field strip with `TM_CCOEFF_NORMED`. Take local maxima at or above `GLYPH_MIN`. Greedily keep the best non-overlapping ones. A glyph is accepted only if no other char scores within `GLYPH_MARGIN` of it within 1 px. Every ink column of the strip must be covered by an accepted glyph, else the field reads `None`. In the prototype, every accepted glyph scored ≥ 0.83 at 1080/1440 and 1.0 at 768.

The skill window (Task 7) uses the same two steps, so they live in `readers/window.py`, shared by both.

**Files:**
- Create: `src/maplelens/readers/window.py`, `src/maplelens/readers/stat_window.py`, `src/maplelens/readers/templates/stat_title.png`, `stat_bottom.png` (the ABILITY POINT label), `templates/window_font/*.png`
- Modify: `src/maplelens/readers/__init__.py` (`Reading`, `read_all`), `src/maplelens/readers/glyphs.py` (`CHAR_NAMES` gains `"plus": "+"`, `"lpar": "("`, `"rpar": ")"`, `"slash": "/"`), `tests/test_readers.py`
- Fixtures (already cut, names painted over): copy `stat_*.png` from `.superpowers/sdd/2026-11-07-class-helper/fixtures/` into `tests/fixtures/screens/`. They are **native** crops (not normalized), the window plus 3 px (768-scale) of margin.

**Interfaces:**
- Produces in `window.py`:
  - `UNREADABLE = "unreadable"`
  - `align(frame: np.ndarray, native: np.ndarray, scale: float, anchors: list[tuple[str, tuple[int, int]]], size: tuple[int, int]) -> tuple[np.ndarray, tuple[int, int]] | None`: `anchors` are (template name, its offset from the window's top-left); returns the window-aligned 768-scale BGR image of `size` (w, h) and the window's top-left in `frame` coordinates, or `None` when no anchor scores ≥ `ANCHOR_MIN`. Parts of the window outside `native` come back as black (so their fields read `None`).
  - `read_number_text(win: np.ndarray, box: tuple[int, int, int, int]) -> str | None`: the strip of `box` (x, y, w, h in window coordinates) read with `window_font`, or `None`.
- Produces in `stat_window.py`:
  - `StatWindow(level: int, ap: int, base: dict[str, int], total: dict[str, int], plus: dict[str, tuple[int, int]])` (frozen). `plus` is the centre of each stat's **single-arrow** + button (the left one of the two), in `frame` coordinates. `total` per R6.
  - `parse_stat(text: str) -> tuple[int, int] | None`: `(base, total)`; "25" → (25, 25); "124(122+2)" → (122, 124) only when 122 + 2 == 124; anything else `None`.
  - `read_stat_window(frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None) -> StatWindow | str | None`: `native` defaults to `frame`, `scale` to `native.shape[0] / frame.shape[0]`. `None` when no anchor is found, `UNREADABLE` when found but any field reads `None`, fails `parse_stat`, or fails the AP check.
  - `Reading` gains `stats: "StatWindow | str | None" = None`, as its last field; `read_all` calls `stat_window.read_stat_window(img, frame, frame.shape[0] / glyphs.BASE_H)`.
- AP check (R13): `sum(base) + ap <= 25 + 5 * (level - 1)`, else `UNREADABLE`. On the owner's level 28 Rogue it is equal: 4 + 25 + 4 + 122 + 5 = 160.

**Fixture truth (all three `stat_a_*`):** level 28, AP 5, base STR 4 / DEX 25 / INT 4 / LUK 122, total LUK 124 (others = base). `stat_covered_1366x768_100.png`: an inventory window over the left half of the stat rows, title covered, the ABILITY POINT label visible → `UNREADABLE`. `stat_edge_1366x768_100.png`: the window mostly off the frame's left edge → `None` or `UNREADABLE` (record which; never a `StatWindow`).

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize(
    "text, want",
    [
        ("25", (25, 25)),
        ("124(122+2)", (122, 124)),
        ("4(4+0)", (4, 4)),
        ("25(20+4)", None),
        ("", None),
        ("2a", None),
        ("25(20+", None),
    ],
)
def test_parse_stat(text, want):
    assert parse_stat(text) == want
```

  Fixtures are native crops, so the stat tests load them with a helper `_window_args(name) -> (frame, native, scale)`: `scale = H / 768` from the filename's `WxH`, `frame = cv2.resize(native, None, fx=1/scale, fy=1/scale, interpolation=cv2.INTER_AREA)`. Add each `stat_*` fixture to `EXPECTED` (the `plus` centres measured once on the fixture) and route `stat_*` through `read_stat_window(*_window_args(name))`. Also:
  - `test_no_stat_window_reads_none`: every `exp_a_*` fixture gives `None`.
  - `test_stat_reads_at_every_offset`: for `stat_a_2560x1440_100.png`, drop the first `k` native columns and rows for `k in range(0, 15, 2)`; every read equals the same `StatWindow` with `plus` shifted by the dropped amount / scale (±1).
  - `test_stat_ap_check`: monkeypatch the AP so the sum exceeds the bound → `UNREADABLE`.
- [ ] **Step 2: Run the tests.** `uv run pytest tests/test_readers.py -v -k stat`. Expected: FAIL.
- [ ] **Step 3: Cut the templates** from `stat_a_1366x768_100.png` (native = 768 look): the title text and the ABILITY POINT label as anchors, and one grey glyph per digit plus `(`, `)`, `+`, `/` into `window_font/` (13 rows: the glyph's 9 rows plus 2 above and 2 below; 1 px of background left and right). A glyph the fixture lacks may be cut from the skill fixture (same font). Digits advance 7 px; the stat value column starts 58 px right of the window's left edge.
- [ ] **Step 4: Implement** `window.py` and `stat_window.py` as above. Field boxes are constants relative to the window's top-left (named like `LV_DX` in `level.py`). Strips end before the + buttons. Tune `ANCHOR_MIN`, `GLYPH_MIN` and `GLYPH_MARGIN` on the fixtures and write the measured scores in a comment beside them.
- [ ] **Step 5: Run the tests.** `uv run pytest tests/test_readers.py -v`. Expected: all PASS, the old fixtures too.
- [ ] **Step 6: Commit** with `feat(readers): stat window`.

### Task 7: Skill window reader

**Files:**
- Create: `src/maplelens/readers/skill_window.py`, `templates/skill_title.png`, `templates/skill_bottom.png` (the SKILL POINT label)
- Modify: `src/maplelens/readers/__init__.py`, `tests/test_readers.py`
- Fixtures: copy `skill_*.png` from `.superpowers/sdd/2026-11-07-class-helper/fixtures/` into `tests/fixtures/screens/` (native crops, as in Task 6).

**Interfaces:**
- Consumes: `window.align`, `window.read_number_text`, `window.UNREADABLE` (Task 6), `ocr.crop`, `ocr.read_lines`, the `skills` table of `data/classes.json` (read directly with `json`, as `map_name.known_titles` reads `maps.json`)
- Produces:
  - `SkillRow(skill: int, level: int, plus: tuple[int, int])` and `SkillWindow(tab: str, sp: int, rows: tuple[SkillRow, ...])` (frozen). `plus`: the single-arrow + button's centre in `frame` coordinates.
  - `known_skills() -> dict[str, list[tuple[int, str]]]` (name → every (id, job) with that name; R3), cached
  - `read_skill_window(frame, native=None, scale=None) -> SkillWindow | str | None`
  - `Reading` gains `skills: "SkillWindow | str | None" = None`, after `stats`

**Fixture truth (all three `skill_a_*`):** tab "Rogue", SP 3, rows in order: Nimble Body 15, Keen Eyes 15, Disorder 2, Dark Sight 0, Double Stab 0, Lucky Seven 20. Rows sit 40 px apart (768 scale). `skill_covered_2560x1440_100.png`: inventory over the top rows, title covered, SKILL POINT label visible → `UNREADABLE`. `skill_edge_2560x1440_100.png`: the window mostly off the left edge → `None` or `UNREADABLE` (never a `SkillWindow`). No scrolled (`skill_b`) grab exists: a 1st-job Rogue has 6 skills and the list doesn't scroll. Rows whose name line is blank are simply not returned.

- [ ] **Step 1: Write the failing tests.** `EXPECTED` entries for each `skill_*` fixture, routed through `read_skill_window(*_window_args(name))`. Then:

```python
def test_unknown_skill_name_is_unreadable(monkeypatch):
    monkeypatch.setattr(skill_window, "known_skills", lambda: {})
    assert read_skill_window(*_window_args("skill_a_1366x768_100.png")) == UNREADABLE
```

  Plus `test_skill_level_over_max_is_unreadable` (monkeypatch a skill's max below its read level) and `test_skill_reads_at_every_offset` (as Task 6, on `skill_a_2560x1440_100.png`).
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement it.** `align` the window (anchors: title, SKILL POINT label). Read SP and each row's level with `read_number_text`. Read each row's name with OCR from the native pixels (`ocr.crop`), and snap it with `difflib.get_close_matches(cutoff=0.8)` plus the length guard `job.read_job` uses. The tab is the job that every matched row shares (R3: a name may map to several (id, job) pairs; take the one job in all of them). A row that snaps to nothing, rows with no shared job, or a level above the skill's `max` make the result `UNREADABLE`. Wire it into `read_all` like Task 6.
- [ ] **Step 4: Run the tests.** `uv run pytest tests/test_readers.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(readers): skill window`.

### Task 8: Go, best rate, and the Class tab

**Files:**
- Modify: `src/maplelens/overlay.py` (`_select` → `select`), `src/maplelens/tools/path_arrow/ui.py` (add `go`), `src/maplelens/tools/exp_meter/history.py` (add `best_rate`), `src/maplelens/store.py` (`"class_builds": {}`), `src/maplelens/app.py`
- Create: `src/maplelens/tools/class_helper/ui.py`, `tests/test_class_ui.py`
- Modify tests: `tests/test_path_ui.py` (`box._select` → `box.select`; `go` tests), `tests/test_history.py`, `tests/test_app.py` (`update_tools` calls)

**Interfaces:**
- Consumes: Tasks 2–5; `Reading.stats`/`.skills` (Tasks 6–7; tests build the `Reading` objects directly)
- Produces:
  - `Box.select(index: int) -> None` (public, same body)
  - `PathArrowTool.go(map_id: str) -> None`: fills the field with the map, as `_pick` does, then runs `_on_start`. `_on_start` keeps working from the picked item.
  - `best_rate(conn, title: str) -> float | None`: the highest per-level EXP/min on that map, by the same grouping as `history`
  - `ClassHelperTool(settings: dict, on_settings_changed: Callable[[], None], layer: Layer, go: Callable[[str], None], best_rate: Callable[[str], float | None], data: ClassData | None = None)` with `title = "Class"`, `tab: QWidget`, `dot: bool` (property), `update(r: Reading | None, game_rect: tuple | None, now: float) -> None` and `hide_marks() -> None` (a no-op until Task 9)
  - `update_tools(box, exp, path, cls, reading, rect, now, seen)`: `cls` errors are logged like the others, then `cls.hide_marks()` runs. It also does `box.set_tab_dot(2, cls.dot)`.
  - Fixed strings in `ui.py`: `NO_CLASS = "Can't read your class yet"`, `NO_PLAN = "No plan for {} yet"`, `OPEN_STATS = "Open your stat window once"`, `STAT_UNREAD = "Can't read your stat window: move it fully into view"`, `SKILL_UNREAD = "Can't read your skill window: move it fully into view"`

- [ ] **Step 1: Write the plumbing tests.**
  - `test_go_starts_a_trip`: `feed(tool, title("A")); tool.go("C")`, then `tool.running and tool.trip.goal == "C"`.
  - `test_go_before_the_map_is_known_picks_only`: no feed; `tool.go("C")` leaves `not tool.running` and `tool._search.text() == "Cherry"`.
  - `test_best_rate`: two `Segment`s on one title at 600 and 900 EXP/min give `best_rate(conn, t) == approx(900)`, and an unseen title gives `None`.
- [ ] **Step 2: Write the tab tests** in `tests/test_class_ui.py`, built like `test_path_ui.make` with `data=load(SMALL, MAPS)` and a `gone: list[str]` that records the calls to `go`. The helper `texts(tool)` returns the visible `QLabel` texts of `tool.tab`.

```python
def test_unknown_class_says_so(make):
    tool = make()
    tool.update(R(job=None, level=None), RECT, 0)
    assert NO_CLASS in texts(tool)


def test_no_plan_for_job(make):
    tool = make()
    tool.update(R(job="Hermit", level=72), RECT, 0)
    assert NO_PLAN.format("Hermit") in texts(tool)


def test_training_rows_go_and_best_rate(make):
    tool = make(best_rate=lambda t: 1234.0)
    tool.update(R(level=12), RECT, 0)
    assert any("best 1,234/min" in t for t in texts(tool))
    go_buttons(tool)[0].click()
    assert tool.gone == ["000000001"]


def test_stats_never_read_then_badge_until_level_changes(make):
    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert OPEN_STATS in texts(tool)
    tool.update(R(level=12, stats=SW(level=12, ap=3)), RECT, 1)
    assert "3 AP to spend" in texts(tool)
    tool.update(R(level=13), RECT, 2)
    assert not any("AP to spend" in t for t in texts(tool))


def test_build_picker_saved(make):
    saved = []
    tool = make(on_changed=lambda: saved.append(1))
    tool.update(R(level=12), RECT, 0)
    tool._builds.setCurrentText("Sindit")
    assert tool._settings["class_builds"] == {"Rogue": "Sindit"} and saved


def test_job_flicker_keeps_tab(make):
    tool = make()
    tool.update(R(level=12), RECT, 0)
    tool.update(R(job=None, level=12), RECT, 1)
    assert NO_CLASS not in texts(tool) and not tool.dot


def test_character_switch_forgets(make):
    tool = make()
    tool.update(R(level=25, stats=SW(level=25, ap=0)), RECT, 0)
    tool.update(R(job="Magician", level=20), RECT, 1)
    assert OPEN_STATS in texts(tool)


def test_level_up_dot_until_opened(make):
    tool = make()
    tool.update(R(level=14), RECT, 0)  # tab not shown
    tool.update(R(level=15), RECT, 1)  # a new map or gear at 15
    assert tool.dot
    tool.tab.show()
    tool.update(R(level=15), RECT, 2)
    assert not tool.dot
```

  `R(...)` defaults to `job="Rogue"`. `SW(...)` builds a `StatWindow` with default stats. `go_buttons(tool)` returns the visible `QPushButton`s whose text is "Go", top to bottom.
- [ ] **Step 3: Run the tests.** `uv run pytest tests/test_class_ui.py tests/test_path_ui.py tests/test_history.py -v`. Expected: the new tests FAIL.
- [ ] **Step 4: Implement the plumbing.** `Box.select`, `PathArrowTool.go`, `best_rate` (one SQL query), and `DEFAULTS["class_builds"]`.
- [ ] **Step 5: Implement `ClassHelperTool`** (tab only, no marks yet). The tab is `TAB_W` wide, styled with `text_label` and the path tab's button look. From the top, it shows:
  - the class and level, the badge (`"3 AP · 2 SP to spend"`; either half drops when unknown) and a `QComboBox` picker, visible only with more than one build
  - "Train here": per row, the name, `"Lv 10–15 · mobs 8–12 · best 1,234/min"` and a Go button when `place.map_id`
  - "Gear": `"Now: …"` and `"Next: … at 15"`, plus `"5 DEX short"`, with Go on `where`
  - the job advance (`advance_text` + NPC · map name + Go)
  - "Next step"
  - the reasons (`OPEN_STATS`, `STAT_UNREAD`, …)

  Memory: the last job and level, the stats plus the level they were read at, and `skills[tab] -> {id: level}` with `sp[tab]`. All of it is cleared when the job changes to another non-`None` job or the level drops. Dot: set when the level rises and the tuple of (training map ids, gear ids, advance shown, points to place) changes while `not self.tab.isVisible()`; cleared on any update while it is visible. Rebuild the rows only when that content tuple or the best rates change, not every tick.
- [ ] **Step 6: Wire `app.py`.**

```python
conn = open_db(data_dir() / "maplelens.db")
tool = ExpMeterTool(settings, conn)
...


def go(map_id: str) -> None:
    path_tool.go(map_id)
    box.select(1)


cls_tool = ClassHelperTool(settings, save, layer, go, lambda t: best_rate(conn, t))
box = build_box(settings, save, [tool, path_tool, cls_tool], pick)
```

  Pass `cls_tool` to both `update_tools` calls, and update `test_app.py` and `test_path_ui.py`'s callers to the new signature.
- [ ] **Step 7: Run the full checks.** `uv run pytest && uv run ruff check && uv run python scripts/check_screen_only.py`. Expected: all PASS.
- [ ] **Step 8: Commit** with `feat(class_helper): Class tab with Go into the path arrow`.

### Task 9: Marks on the stat and skill windows

**Files:**
- Modify: `src/maplelens/tools/class_helper/ui.py`, `tests/test_class_ui.py`

**Interfaces:**
- Consumes: `ap_advice`, `band_at` (Task 3), `sp_advice` (Task 4), `StatWindow`/`SkillWindow`/`UNREADABLE` (Tasks 6–7), `game_to_layer`, `glyphs.BASE_H`
- Produces: a `_Mark(QWidget)` child of the layer (a ring of `ACCENT` with a tag beside it, or a quiet tag alone in `LABEL_COLOR`), plus:
  - `ClassHelperTool.marks() -> list[tuple[str, tuple[int, int]]]`: the visible marks' (tag, layer centre), for tests
  - `hide_marks()` now hides them all
  - tags: `"{n} here"`, `"{STAT} {n} over plan"`, `"{STAT} {n} behind plan"`, `"off plan"`, `SCROLL = "scroll the list once"`, and the tab line `"{Beginner|1st job|2nd job} tab: {n} SP to place"`

- [ ] **Step 1: Write the failing tests.** `pos(x, y)` turns a normalized point into layer coordinates for `RECT`, as `PathArrowTool._place_arrow` does.

```python
def test_rings_on_the_plus_buttons(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30))), RECT, 0)
    assert tool.marks() == [("5 here", pos(*PLUS["LUK"]))]


def test_marks_follow_and_hide(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5)), RECT, 0)
    moved = SW(level=20, ap=5, plus={k: (x + 40, y) for k, (x, y) in PLUS.items()})
    tool.update(R(level=20, stats=moved), RECT, 1)
    assert [p for _, p in tool.marks()] == [pos(PLUS["LUK"][0] + 40, PLUS["LUK"][1])]
    tool.update(R(level=20), RECT, 2)
    assert tool.marks() == []


def test_unreadable_window_hides_marks_and_says_why(make):
    tool = make()
    tool.update(R(level=20, stats=UNREADABLE), RECT, 0)
    assert tool.marks() == [] and STAT_UNREAD in texts(tool)


def test_over_and_behind_tags(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=0, base=s(4, 35, 4, 20))), RECT, 0)
    assert {t for t, _ in tool.marks()} == {"DEX 10 over plan", "LUK 10 behind plan"}


def test_scroll_the_list_once(make):
    tool = make()
    tool.update(R(level=20, skills=KW(rows=LATER_ROWS_ONLY, sp=2)), RECT, 0)
    assert [t for t, _ in tool.marks()] == [SCROLL]


def test_tabs_are_remembered_apart(make):
    tool = make()
    tool.update(R(level=32, job="Bandit", skills=KW(tab="Rogue", sp=2, rows=ALL_ROGUE)), RECT, 0)
    tool.update(R(level=32, job="Bandit", skills=KW(tab="Bandit", sp=0, rows=ALL_BANDIT)), RECT, 1)
    tool.update(R(level=32, job="Bandit"), RECT, 2)
    assert "1st job tab: 2 SP to place" in texts(tool)
```

  `PLUS`, `KW`, `LATER_ROWS_ONLY`, `ALL_ROGUE` and `ALL_BANDIT` are test constants built from `classes_small.json`'s skills.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement the marks.** Each tick, compute them from this tick's reading only (memory never places a mark), then hide the pool and show the ones needed, growing the pool as required. Coordinates: `k = h / BASE_H`, then `game_to_layer(x * k, y * k, dpr)`. The SP plan for a tab is `data.plan(tab).build(chosen[tab]).sp`. Plus buttons with `add == 0` and no over/behind/off-plan get no mark.
- [ ] **Step 4: Run the full checks.** `uv run pytest && uv run ruff check && uv run python scripts/check_screen_only.py`. Expected: PASS.
- [ ] **Step 5: Check by hand in the game** with the owner. Open the stat and skill windows with points unspent: the rings sit on the + buttons, move with a dragged window, and vanish when it closes. Clicking a + still spends a point in the game.
- [ ] **Step 6: Commit** with `feat(class_helper): marks on the stat and skill windows`.

### Task 10: The other 11 classes, credits and docs

**Files:**
- Modify: `src/maplelens/data/classes.json`, `README.md`, `AGENTS.md`, `tests/test_class_data.py`, `tests/test_docs.py`

- [ ] **Step 1: Write the failing tests.**

```python
FIRST_AND_SECOND = ["Beginner", "Warrior", "Magician", "Bowman", "Rogue", "Fighter", "Page",
    "Spearman", "Wizard (Fire, Poison)", "Wizard (Ice, Lightning)", "Cleric", "Hunter",
    "Crossbowman", "Assassin", "Bandit"]

def test_every_first_and_second_job_has_a_plan():
    assert [j for j in FIRST_AND_SECOND if load().plan(j) is None] == []

def test_readme_credits_each_guide_page():  # in test_docs.py
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert [p.source for p in load().jobs.values() if p.source not in readme] == []
```- [ ] **Step 2: Run the tests.** Expected: FAIL (11 jobs missing).
- [ ] **Step 3: Convert the 11 records** by the method in Task 2 Step 5. Builds: Arrow Blow or Double Shot (Bowman), Energy Bolt or Magic Claw (Magician), and one build per weapon type for Fighter, Page and Spearman.
- [ ] **Step 4: Update the docs.** In `README.md`: the status line and, under the existing credits, "Class plans adapted from the NiaDB class guides", followed by the 15 page links. In `AGENTS.md` Layout: `tools/class_helper/` (`data`, `plan`, `ui`), `stat_window` and `skill_window` in the readers list, and `data/classes.json`. Drop the class helper from "Planned".
- [ ] **Step 5: Run the full checks.** `uv run pytest && uv run ruff check && uv run ruff format --check && uv run python scripts/check_screen_only.py`. Expected: PASS.
- [ ] **Step 6: Commit** with `feat(class_helper): all 1st and 2nd jobs; credits and docs`.
