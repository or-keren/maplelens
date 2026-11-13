# Cheaper ticks, part 3: read the game in a helper process (Mac)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the Mac, grab and read the game in a separate process, which macOS doesn't
slow down while the game is in front, so a fullscreen tick goes from about 700 ms to
under 200 ms and the UI thread no longer waits on reading.

**Architecture:** One new module, `reader.py`, holds the work one tick hands off: grab,
trim the black bars, `read_all`. It also holds two readers with one interface:
`InlineReader` does the work on the spot (Windows, and the tests), and `ProcessReader`
sends it to a long-lived child process over a `multiprocessing` pipe and picks up the
answer on a later tick. `Tick.run` asks for a reading and takes whichever reading is
ready. The child keeps the readers' caches (anchor spots, window spots, scaled reads)
between ticks, as today's single process does.

**Tech Stack:** Python 3 stdlib `multiprocessing` (spawn), PySide6, pytest.

**Spec:** none. This argues from the live measurements below. Part 2
(`2026-11-12-tick-cost-2.md`, Task 0) said to plan this if a helper process escaped the
slowdown, which it did.

## What was measured live (2026-11-12, MapleStory fullscreen in front, the owner playing)

| median, fullscreen 3024x1700 | part 1, in the app | prototype: grab + read in a child |
|---|---|---|
| tick (UI thread) | 701 ms | 170 ms (it still waited for the child) |
| `normalize` | 96 ms | 9.2 ms (full speed) |
| `read_all` | 436 ms | 59 ms |
| grab + `picture_box` | 240 ms | 75 ms |
| readings per second | 1.22 | 2 (one per 500 ms tick; EXP read on 112 of 117 ticks) |

### Task 3, from source (2026-11-12, 06e78de, fullscreen, 238 s, the owner playing)

| median | part 1 | part 3 |
|---|---|---|
| tick (UI thread) | 701 ms | 40 ms |
| UI lag (50 ms probe, worst per tick) | 682 ms | 101 ms (p90 130) |
| the child's `read_game` | — | 131 ms (`normalize` 9.2 ms: full speed; max 903) |
| readings per second | 1.22 | 1.98 |
| EXP read | 340 / 342 | 470 / 472 |

- The first 4 ticks (about 2 s) had no answer while the child started. Every tick after that had one, with no errors.
- The stat window was read on 24 ticks, the skill window on 46 and the tracker on 455. The quest window was never read.
- Quitting left no MapleLens or helper process.
- With no rate yet, the EXP box shows dashes for the first minute of play (`Meter.rate` needs 60 s of active time). The owner noticed: "in the first 20 seconds it didn't give exp numbers without any warning". The behaviour isn't new.
- Spawn re-imports the main script: a script that wraps `app.main()` needs its own `__name__` guard (the tracer did not, which ran a second app in the child).

### Task 3, the frozen app (25c6b09, `--freeze-only`, run from `~/MapleLens-test`)

- `--self-check` exits 0. Once Screen Recording was granted to the build, its helper read the game: the EXP box filled in, so the app's permission covers its child.
- While it ran there were three processes: the app, the helper (`--multiprocessing-fork`) and multiprocessing's resource tracker. There was no Dock icon and one menu-bar icon.
- Quitting from the menu ended all three.
- A locally built app is signed ad hoc, so macOS asks for Screen Recording again. The installed copy shares its bundle id, which is why the owner had to reset it (`tccutil reset ScreenCapture io.github.or-keren.maplelens`). `open` sometimes launched the installed copy instead of the build.

Not redone: part 2's capture tasks. The child's work is 131 ms a tick at full speed, so they would save about 40 ms of it and none of the UI thread's time.

The prototype (scratchpad `helper_child.py` and `live_helper.py`) was unchanged
MapleLens, with grab, trim and `read_all` sent to a plain child process. Opting the app
out of App Nap changed nothing (95 ms `normalize`), so the slowdown follows the app,
not every process it starts.

## Global Constraints

- Screen-only (`AGENTS.md`): the child only captures the game's pixels and reads them.
  It sends no input and opens no window. Don't write the guard's banned names in
  comments or docstrings under `src/` or `scripts/`.
- Readers stay pure `frame -> value` functions. No reader or tool changes in this plan.
- No new dependency (`multiprocessing` is stdlib). Never change `version` in
  `pyproject.toml`.
- Windows behaviour must not change: Windows uses `InlineReader`, same work, same tick.
- One capturer at a time: the child is the only process that captures. The app itself
  stops calling `capture.grab` on the Mac.
- Never commit the owner's grabs.

## Review Focus

1. **The child dies or hangs** (a capture can block for about 30 s): the next tick
   starts a new child. Nothing waits on the UI thread
   (`test_process_reader_restarts_a_dead_child`, `test_process_reader_gives_up_on_a_stuck_child`).
2. **The frozen app:** spawning must start the child, not a second MapleLens. The
   single-copy check and windows must not run in the child. `--self-check` makes a
   round trip, so the build catches a broken spawn (Task 2).
3. **Quitting MapleLens** ends the child: it's a daemon, and it exits when its pipe closes.
4. **An error in the child** is logged once in the app, like today's errors in a tick
   (`test_process_reader_returns_the_childs_error`).
5. **No reading back yet**: the tools aren't told the read failed. That tick only moves
   the layer, so the path arrow's 3 s "open the minimap" timer doesn't run early
   (`test_a_tick_without_an_answer_leaves_the_tools_alone`).

---

### Task 1: `reader.py`: the work, and the two readers

**Files:**
- Create: `src/maplelens/reader.py`
- Modify: `src/maplelens/app.py` (`Tick` uses a reader; the grab/trim/read lines move out)
- Modify: `tests/test_app.py` (the tick tests patch `reader.read_all`, not `app.read_all`)
- Test: `tests/test_reader.py`
- Modify: `AGENTS.md` (layout line for `reader.py`)

**Interfaces:**
- `Job = tuple[int, tuple[int, int, int, int], float, frozenset[str]]`, which is
  `(hwnd, rect, now, due)`.
- `read_game(job: Job) -> tuple[tuple[int, int, int, int], Reading]`: today's three
  lines from `Tick.run` (grab, `picture_box`, `read_all` on the trimmed frame). It
  returns the trimmed rect in screen pixels and the reading.
- Both readers have:
  - `ask(job) -> None`: starts the work. It's a no-op while a job is in flight.
  - `take() -> tuple[rect, Reading] | Exception | None`: the finished answer or the
    error raised, each returned once. None means nothing is ready yet.
- `InlineReader(work=read_game)`: `ask` runs `work` at once and keeps its result or
  exception for `take`.
- `ProcessReader(work=read_game, stuck_s: float = 30.0)`: a spawn-context
  `multiprocessing.Process(target=serve, args=(child_end, work), daemon=True)`, started
  on the first `ask`.
  - `take` uses `conn.poll()` and never blocks.
  - A child that died (`not is_alive()`), or one with a job in flight for longer than
    `stuck_s`, is killed and replaced on the next `ask`.
  - `close()` ends the child.
- `serve(conn, work) -> None`: the child's loop. It receives a job, sends `work(job)` or
  the exception it raised, and returns on `EOFError`. An exception that won't pickle is
  sent as `RuntimeError(repr(e))`.
- `Tick` gains `reader: InlineReader | ProcessReader = field(default_factory=InlineReader)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_reader.py`. They use only
  stdlib work functions, because a spawned child can import those but not a test's
  closure:
  - `test_inline_reader_answers_at_once`: `InlineReader(work=repr)`; after `ask(job)`,
    `take()` is `repr(job)`, and a second `take()` is None.
  - `test_inline_reader_returns_the_error`: `InlineReader(work=int)`; `take()` is a
    `TypeError`.
  - `test_process_reader_round_trip`: `ProcessReader(work=repr)`; poll `take()` for up
    to 20 s and it's `repr(job)`. A second `ask` while busy is ignored: only one answer
    comes back. Then `close()`.
  - `test_process_reader_returns_the_childs_error`: `work=int` gives a `TypeError`.
  - `test_process_reader_restarts_a_dead_child`: after an answer, kill the child
    (`reader._proc.kill()`, then `join`). The next `ask` and `take` still answer.
  - `test_process_reader_gives_up_on_a_stuck_child`: `work=time.sleep`, `stuck_s=0.5`.
    Call `ask(60)`, wait 1 s, note `reader._proc.pid`, then `ask(60)` again. The pid
    changed, and the old child is no longer alive.
  - `test_read_game_trims_the_black_bars`: monkeypatch `reader.capture.grab` and
    `reader.read_all` with the frame from `test_a_tick_leaves_fullscreen_black_bars_out`.
    `read_game((42, (0, 0, 800, 600), 5.0, frozenset()))` returns
    `((0, 50, 800, 500), READING)`, and `read_all` saw a `(500, 800, 3)` frame.
- [ ] **Step 2: Run** `uv run pytest tests/test_reader.py -v`. They fail:
  `maplelens.reader` doesn't exist yet.
- [ ] **Step 3: Write `reader.py`**. Then change `Tick.run`:
  - it builds the job with `due(self.turn, self.seen_at)`, calls `self.reader.ask(job)`,
    then `got = self.reader.take()`;
  - an Exception: `report_once`, and the tools get `reading=None` as today;
  - a tuple: update `seen_at` from `found`, and feed the tools the reading and its rect;
  - None: only `layer.follow` and `box.place` with the untrimmed rect, and the tools
    aren't updated (Review Focus 5);
  - `turn += 1` on every tick that asked, as now.
  With `InlineReader`, `ask` then `take` gives this tick's answer, so every existing tick
  test keeps its meaning. Only their `app.read_all` patches move to `reader.read_all`.
  Add `test_a_tick_without_an_answer_leaves_the_tools_alone`: a stub reader whose `take`
  returns None, so `exp.updates == []` and the layer is visible.
- [ ] **Step 4: Run** `uv run pytest`, `uv run ruff check`, `uv run ruff format`,
  `uv run python scripts/check_screen_only.py`. All pass.
- [ ] **Step 5: Commit** `perf: read the game through a reader that can run in another process`.

### Task 2: the Mac uses `ProcessReader`, frozen app included

**Files:**
- Modify: `src/maplelens/app.py` (`main`, `self_check`)
- Modify: `tests/test_app.py`
- Modify: `AGENTS.md` (the `app.py` line: the helper process)

**Interfaces:**
- Consumes: Task 1's `ProcessReader`, `InlineReader`, `Tick.reader`.
- `main()`:
  - calls `multiprocessing.freeze_support()` as its first line, before `early_exit`,
    so a spawned child of the frozen app runs `serve` and never reaches the single-copy
    check or Qt;
  - builds `Tick(..., reader=ProcessReader() if sys.platform == "darwin" else InlineReader())`;
  - connects `app.aboutToQuit` to `reader.close` as well.
- `self_check()`: on the Mac, it also does a `ProcessReader(work=repr)` round trip,
  timing out after 20 s. If no answer comes back, it returns 1. This runs in the build
  (`MapleLens --self-check`), so a frozen app that can't spawn fails there.

- [ ] **Step 1: Write the failing tests:**
  - `test_self_check_fails_when_the_helper_never_answers`: on darwin only, monkeypatch
    `app.ProcessReader` with a stub whose `take` is always None and a tiny timeout
    constant. `self_check()` returns 1.
  - `test_main_reads_in_a_helper_on_the_mac`: assert which reader `Tick` gets per
    platform, through a small `make_reader(platform: str)` that `main` calls. Test it
    directly: `"darwin"` gives `ProcessReader`, `"win32"` gives `InlineReader`.
- [ ] **Step 2: Run them** and see them fail.
- [ ] **Step 3: Implement.** Use `make_reader(sys.platform)` in `main`.
- [ ] **Step 4: Run** the full checks (Task 1, Step 4), then on the Mac:
  `uv run --group build python scripts/build_installer.py --freeze-only`. Then run the
  built app with `--self-check` and check that it exits 0.
- [ ] **Step 5: Commit** `perf(app): read the game in a helper process on the Mac`.

### Task 3: live check, with the owner present (not delegated)

Same tracer as parts 1 and 2 (scratchpad `live_trace.py`). It times `reader.read_game`
in the child through its own wrapper. The game is fullscreen in front, about 4 minutes,
and the owner opens the quest window, the stat window and the skill window at least once.

- [ ] **Step 1:** Run it from source and record:
  - the tick median (target: under 200 ms in fullscreen);
  - readings per second (target: 2);
  - UI lag median (target: under 100 ms);
  - EXP read rate (target: 95% or more);
  - each window read while open.
- [ ] **Step 2:** Run the frozen `dist/MapleLens.app` and check that:
  - the menu-bar icon appears, with no second Dock or menu-bar icon;
  - Screen Recording still works, meaning the child reads;
  - quitting from the menu leaves no MapleLens process (`pgrep -fl MapleLens`).
- [ ] **Step 3:** Write the numbers into "What was measured", then decide whether part
  2's Tasks 1-3 are still worth doing. At full speed they'd save about 40 ms of the
  child's work per tick. Commit `docs(plans): part 3 live check`.

**Not in this plan:** Windows (no slowdown measured there), a faster tick than 500 ms,
and moving the overlay drawing anywhere else.
