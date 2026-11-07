# Tray Icon and Menu Button Implementation Plan

Spec: `docs/superpowers/specs/2026-11-07-tray-and-menu-button-design.md`. Branch:
`tray-menu-spec`, from or-keren/maplelens `main` at 4199c20 (v0.1.0, PR #10 merged). One
commit per task. The PR goes from the fork (`dbeilin/maplelens`) to `or-keren/maplelens`
once Checkpoint C passes. It changes no `version`: the release goes through Prepare
release.

## Overview

On Windows, MapleLens gets a tray icon. Right-clicking it opens the box's menu, and
left-clicking it hides or shows everything MapleLens draws. On every platform, the box
gets a ⋯ button in its top-right corner that opens the same menu. Right-clicking the box
still works too. Every "right-click" in the app, README and installer becomes "⋯".

Added after T1–T5 were built (T7): an "About MapleLens" menu item opens an About view
inside the box. It shows the version, a line on update status, and a link to the GitHub
page.

## Architecture decisions

- **One list, filled on open.** The box's own `actions()` stay the menu. A helper on
  `Box`, `attach_menu(menu: QMenu)`, connects the menu's `aboutToShow` so it clears and
  re-adds `self.actions()` each time it opens. The ⋯ button's menu and the tray's menu
  both use it. So the update check's runtime items show up everywhere, and nothing keeps
  a second list *(my call: the spec left the name to the builder)*.
  - `QMenu.clear()` deletes only actions the menu owns. The box owns these, including
    the "Pick game window…" submenu, so they survive. A test opens the menu twice to
    prove it.
- **The tray is in `app.py`, behind a seam.** `make_tray(box, icon, *, tray_cls,
  available)` builds it. Offscreen tests pass a fake tray class and `available=True`,
  because a real `QSystemTrayIcon` needs a real tray. `main()` passes `QSystemTrayIcon`
  and `QSystemTrayIcon.isSystemTrayAvailable() and sys.platform == "win32"`.
- **Hidden is a flag in `main()`, not a window state.** `Shown` (a tiny class with `on:
  bool` and `toggle()`) is read by the tick before `layer.show()`. `Box.allow_typing`
  shows the box again only if it was visible before the flag change. Qt's own
  `isVisible()` can't be the flag, because the tick hides and shows the `Layer` on its
  own when the game is lost or found.
- **The icon is package data.** `src/maplelens/data/icon.ico` is the one copy. The exe,
  Setup and the tray all point at it, and the build's `REQUIRED` list and `--self-check`
  both prove it's in the bundle and loads.
- **The risky part comes first** (T1): whether the frozen app can load the `.ico`.
  `qico.dll` ships, but `--self-check` runs without a `QApplication`, and the tray is
  useless without its icon.

## Dependency graph

```
T1 icon as package data, loads in the frozen app      T2 ⋯ button + attach_menu
   │                                                      │
   │                                                      ├── T3 text: "right-click" → "⋯"
   │                                                      │
   └──────────────────────┬───────────────────────────────┘
                          T4 tray icon, right-click menu (Windows)
                          │
                          T5 Hide / Show (tray left-click + menu item)
                          │
                          T7 About view in the box (added 2026-11-07)
                          │
                          T6 docs, installed-build run, PR
```

T7 came after T6's docs and build were done, so T6's installed run now covers About too.

T1 and T2 are independent, as are T3 and T4. Daniel works alone, so they run in order.

## Phase 1: the foundations

### Task T1: the icon as package data, loaded by the frozen app

**Description:**
- `git mv packaging/windows/icon.ico src/maplelens/data/icon.ico`.
- `maplelens.spec`: `icon=` points at the new path (`ROOT / "src" / "maplelens" / "data"
  / "icon.ico"`).
- `maplelens.iss`: `SetupIconFile=..\..\src\maplelens\data\icon.ico`, relative to the
  `.iss`.
- `app.py`: `ICON = Path(__file__).parent / "data" / "icon.ico"`. `self_check` fails if
  `QImage(str(ICON)).isNull()`. If `QImage` can't use its plugins without an app, use a
  `QGuiApplication` on the offscreen platform inside `self_check`. That window-free check
  is what the build runs.
- `scripts/build_installer.py`: add `_internal/maplelens/data/icon.ico` to `REQUIRED`.
- `tests/test_build_installer.py`: `test_icon_exists` checks the new path.

**Acceptance criteria:**
- [ ] `uv run --group build python scripts/build_installer.py` builds the setup. The
      setup exe and `MapleLens.exe` still show the icon in Explorer.
      *2026-11-07: builds (PyInstaller embeds the icon, ISCC takes the new path). The
      Explorer look is still to check by hand.*
- [x] `dist\MapleLens\MapleLens.exe --self-check` exits 0. With the bundled
      `icon.ico` deleted, or `qico.dll` deleted, it exits 1.
      *2026-11-07: 0, 1, 1, and 0 again once restored. The first build failed it: `ICON`
      came from `app.py`'s own folder, which the frozen app runs outside the package, so
      it's found from `maplelens.__file__` instead.*
- [x] `packaging/windows/icon.ico` is gone, and nothing points at it
      (`git grep "windows/icon.ico"` finds only the older specs and plans, which stay as
      written).

**Verification:** `uv run pytest tests/test_build_installer.py tests/test_app.py`, the
four checks, and the build above.

**Dependencies:** none. **Files:** `src/maplelens/data/icon.ico`,
`packaging/windows/maplelens.spec`, `packaging/windows/maplelens.iss`,
`scripts/build_installer.py`, `src/maplelens/app.py`, `tests/test_build_installer.py`.
**Scope:** M.

### Task T2: the ⋯ button and `attach_menu`

**Description:**
- `overlay.py`: a top row (`QHBoxLayout`) holds the tab strip and the status line, which
  take turns as today, with the ⋯ button on the right in both states. `set_status`
  keeps toggling the strip, pages and status. The ⋯ isn't part of any of them.
- The button is styled like the notice's ×: flat, `LABEL_COLOR`, `Qt.NoFocus`, pointing
  hand. Clicking it pops up a `QMenu` filled by `attach_menu`, just under the button.
- `attach_menu(menu)`: on `aboutToShow`, `menu.clear()`, then `menu.addAction(a)` for
  each of `self.actions()`.
- Glyph: try "⋯" (U+22EF) in Segoe UI. If Qt's fallback shows a box or the wrong
  height, use "•••" or paint three dots. Record the choice in the commit message, because
  T3's text uses it.
- Docstrings drop "right-click" ("the box's menu").

**Acceptance criteria:**
- [x] Offscreen tests: the ⋯ is visible with tabs and while `set_status("Looking…")`
      shows. Its menu lists `box.actions()` in order, including an item added with
      `at=0` after the menu was attached. Opening it twice leaves every action alive and
      working. The button has `Qt.NoFocus`, and pressing it leaves `_drag_from` at
      `None`. `contextMenuPolicy()` is still `Qt.ActionsContextMenu`.
      *2026-11-07: glyph is "•••" (U+2022 ×3) at 10 pt. Segoe UI has no U+22EF, and the
      fallback font drew it faint and 2 px taller. Opening twice caught a real bug:
      PySide's `QMenu.clear()` let Python delete the box's actions, so the fill removes
      them one by one instead.*
- [x] By hand, `uv run maplelens` on Windows: the ⋯ sits top-right at 100% and 150%
      scaling, in both states. Its menu opens under it, and after picking an item or
      pressing Esc, the game still has the keyboard.

**Verification:** `uv run pytest tests/test_overlay.py`, the four checks, and the run
above.

**Dependencies:** none. **Files:** `src/maplelens/overlay.py`, `tests/test_overlay.py`.
**Scope:** S.

### Checkpoint A: the foundations

- [x] T1 and T2 committed, and the four checks pass.
- [x] The frozen self-check proves the icon loads.
- [x] Daniel has seen the ⋯ on the box and agrees with the glyph and the place.

## Phase 2: the feature

### Task T3: text points at ⋯

**Description:**
- `app.py`: `LOOKING` → "Looking for MapleStory… click ⋯ to pick the game window".
  `update_notice` → "Update to X.Y.Z: click ⋯". `UPDATE_FAILED` → "Update failed: click
  ⋯". `build_box`'s docstring. (Use the T2 glyph throughout.)
- `maplelens.iss`: "MapleLens is still running. Quit it from the ⋯ menu on its box or
  its tray icon, then try again."
- `README.md`: the install step, Updating, the update-check paragraph and the
  from-source paragraph say "click ⋯ on the box" where they say "right-click the box".
- "Looking for…" one line or two (spec, open question): pick by how it looks at 100% and
  150%, next to the ⋯.
- Update the tests that assert the old strings.

**Acceptance criteria:**
- [x] `git grep -i "right-click\|right click" -- src README.md packaging` finds nothing
      in what the player sees. The box's right-click still works, it just isn't
      mentioned.
      *2026-11-07: finds nothing. The text says "•••" (T2's glyph). The `.iss` writes it
      as `#$2022` codes so the script stays ASCII; ISCC compiles it.*
- [x] `test_notice_fits_the_tab_width_at_the_longest_version` passes with the new text.
- [x] By hand: the "Looking for…" state reads well next to the ⋯ at 100% and 150%.
      *2026-11-07: first two lines (one made the box 395 px wide). Then Daniel cut it to
      "Looking for MapleStory…" alone, since the ••• beside it is hint enough. It's one
      line and 197 px wide. While the status shows, the button stays top-aligned, so a
      longer status would keep it level with the first line. Still to see on a real
      screen.*

**Verification:** `uv run pytest`, the four checks.

**Dependencies:** T2. **Files:** `src/maplelens/app.py`, `packaging/windows/maplelens.iss`,
`README.md`, `tests/test_app.py`, `tests/test_overlay.py`. **Scope:** S.

### Task T4: the tray icon and its menu (Windows)

**Description:**
- `app.py`: `make_tray(box, icon, *, tray_cls=QSystemTrayIcon, available) -> tray |
  None`. When `available`, it builds the tray with `QIcon(str(ICON))`, the tooltip
  "MapleLens", and a `QMenu` that `box.attach_menu` fills, then `show()`s it. Otherwise
  it returns `None`.
- `main()` calls it after `update_check`, with `available = sys.platform == "win32" and
  QSystemTrayIcon.isSystemTrayAvailable()`, and keeps the reference (a tray with no
  reference is collected and vanishes).
- Quit from the tray is the box's own "Quit MapleLens" action, so `aboutToQuit` saves as
  today.

**Acceptance criteria:**
- [x] Tests with a fake tray class: the tooltip is "MapleLens", the icon isn't null, and
      the menu lists `box.actions()`, including an update item added afterwards. With
      `available=False` there's no tray.
      *2026-11-07: plus `tray_available()`: false off Windows, and on Windows without a
      notification area.*
- [x] By hand, `uv run maplelens` on Windows: the icon shows in the notification area
      (or its overflow) with the tooltip. Right-click shows the same menu as ⋯. Quit
      from it saves the session (it's in History after a restart). The game keeps the
      keyboard afterwards.
      *2026-11-07: a scripted run with the real `QSystemTrayIcon` found the tray
      available and the icon visible, with the "MapleLens" tooltip, all six icon sizes
      and the box's menu. The clicks, Quit's save and the focus check are still to do by
      hand.*

**Verification:** `uv run pytest tests/test_app.py`, the four checks, and the run above.

**Dependencies:** T1, T2. **Files:** `src/maplelens/app.py`, `tests/test_app.py`.
**Scope:** S.

### Task T5: Hide / Show

**Description:**
- `app.py`: `Shown` holds `on` and `toggle()`. Toggling hides or shows the box and the
  `Layer`, and relabels the menu item "Hide MapleLens" ↔ "Show MapleLens".
- The item goes in just before Quit (`at=-1`), and only when `make_tray` returned a tray.
- The tray's `activated` with `QSystemTrayIcon.Trigger` (left click) calls `toggle()`.
- The tick shows the `Layer` only while `shown.on`. It still runs the tools, the readers
  and `poll_updates` while hidden.
- `overlay.py`: `allow_typing` calls `show()` only if the box was visible before the flag
  change.
- Not saved: every start begins shown.

**Acceptance criteria:**
- [x] Tests (fake tray, offscreen): toggling hides the box and the `Layer`, and the label
      reads "Show MapleLens". A tick with the game "found" (faked `client_rect`/`grab`)
      leaves both hidden and still updates the EXP tool. Toggling back shows both.
      `allow_typing(False)` on a hidden box leaves it hidden. With no tray there's no
      Hide item.
      *2026-11-07: the tick is now `Tick` (a dataclass with `run(now)`), so tests drive
      it. Toggling back shows the box at once and the `Layer` on the next tick with the
      game, so an empty `Layer` never shows while the game is gone.*
- [x] By hand: left-clicking the tray icon hides the box and the arrow, and again brings
      them back. A double-click toggles once, not twice. While hidden for a minute of
      play, the EXP session keeps counting.
      *2026-11-07: a scripted run with the real tray: `Trigger` hides and shows, and
      `DoubleClick` does nothing. Whether a real double-click sends one `Trigger` or two
      is still to see by hand, along with the clicks and the minute of play.*

**Verification:** `uv run pytest`, the four checks, and the run above.

**Dependencies:** T4. **Files:** `src/maplelens/app.py`, `src/maplelens/overlay.py`,
`tests/test_app.py`, `tests/test_overlay.py`. **Scope:** M.

### Checkpoint B: the feature works from source

- [x] T3–T5 committed, and `uv run pytest` and the four checks pass on Windows.
- [x] Spec Testing → by hand on Windows, steps 1–6, from `uv run maplelens`.
- [x] Daniel tries it in a real play session before Phase 3.
  *2026-11-07: Daniel's play session, from `uv run maplelens` on Windows, passed
  every item on the checklist: ••• placed right and its menu at 100% and 150%, the
  game keeping the keyboard after the ••• and tray menus, the tray icon, tooltip and
  menu, Hide / Show by left click (a double click toggles once), the EXP session
  and the path arrow carrying on while hidden, and Quit from the tray saving the
  session. 498 tests and the four checks pass.*

## Phase 2b: About (added 2026-11-07)

### Task T7: the About view in the box

**Description:** (spec Goals → About, Constraints → About and "The view and the status
line don't fight")
- `overlay.py`, on `Box`:
  - an About view: the top row shows "About MapleLens" and a × (`mark_button`, like the
    notice's) before the •••, and the pages area shows Version / version, Updates /
    line, and "GitHub page ↗" in `ACCENT`
  - `show_about(version, updates, url)`, `set_about_updates(text)`, `close_about()`, and
    an `about_open` property (names are the builder's call)
  - `set_status` records the text while About is open, without showing it. `close_about`
    shows what was recorded last: the tabs, or the status line.
  - the link opens `url` with `QDesktopServices.openUrl`
- `app.py`:
  - `UpdateCheck.status() -> str`: "Checking…" while `_thread` runs, "Update to X.Y.Z
    available" while `release` is set, "Up to date" or "Couldn't check" from the last
    check's outcome (new: `_last`, set in `poll` where the result is collected),
    "Automatic checks off" with the toggle off and nothing checked yet, else "Not
    checked yet".
  - `ABOUT = "About MapleLens"` added at `at=-1` *after* `add_hide`, so it lands between
    Hide and Quit (between "Check for updates automatically" and Quit with no tray).
  - Its callback opens the view with `version("maplelens")`, the status (or "Running
    from source" when `updates is None`) and `https://github.com/{update.REPO}`.
  - `Tick.run`: while `box.about_open`, `box.set_about_updates(...)` with the current
    status, after `poll_updates`.
- Lands on or-keren/maplelens#12, which is already open from this branch. The PR body
  gets an About line.
- The update line is coloured with `ACCENT` only for "Update to … available".

**Acceptance criteria:**
- [x] Offscreen tests for every point under spec Testing → About: the view replaces the
      strip, pages and status. × restores tabs or "Looking…", whichever was set last.
      The status line covers each `UpdateCheck` state, "Running from source" shows with
      no check, and the line refreshes on a tick while open. The link URL follows
      `MAPLELENS_UPDATE_REPO`. The view at 10.10.10 is no wider than `TAB_W`. The item
      sits just before Quit, after Hide when there's a tray.
      *2026-11-07: 17 new tests, 515 in all. Names: `Box.show_about(version, updates,
      url, *, accent)`, `set_about_updates(text, *, accent)`, `close_about()`,
      `about_open`. In `app.py`: `UpdateCheck.status()`, `about_line(updates)` (the text,
      and whether to use `ACCENT`), and `add_about(box, updates)`. The panel is fixed at
      `TAB_W`, so the box stays 210 px with About open, even at 10.10.10 (offscreen
      renders at 100% and 150%). The installer build and `--self-check` pass.*
- [x] By hand, `uv run maplelens` on Windows: About from •••, the tray menu and
      right-click shows "Running from source" and the right version. × brings back the
      tabs. With the game closed, it brings back "Looking for MapleStory…". The game
      keeps the keyboard after × and after the ••• menu. The box doesn't change width.
      *2026-11-07: Daniel tried it from `uv run maplelens`: "looks good". His only
      question was the missing update items, which a source run never has (see the
      update-check spec). They show in the frozen build.*
- [x] `git grep -i "right-click\|right click" -- src README.md packaging` is still empty.

**Verification:** `uv run pytest tests/test_overlay.py tests/test_app.py`, then
`uv run pytest` and the four checks, and the run above.

**Dependencies:** T2, T5. **Files:** `src/maplelens/overlay.py`, `src/maplelens/app.py`,
`tests/test_overlay.py`, `tests/test_app.py`. README: one line in T6's tray paragraph
or the install steps ("•••, then About MapleLens shows the version"). **Scope:** M.

### Checkpoint B2: About works from source

- [x] T7 committed, and `uv run pytest` and the four checks pass on Windows.
  *2026-11-07: `f241f57`, 515 tests, and CI green on Windows and macOS.*
- [x] Daniel has opened About from the ••• and the tray, and agrees with how it looks
      at 100% and 150%.
      *2026-11-07: Daniel's run, as in T7 above.*

## Phase 3: ship it

### Task T6: docs, the installed build, then the PR

**Description:**
- `README.md`: one line under the install steps about the tray icon: left-click hides or
  shows MapleLens, right-click opens the same menu as ⋯. (Windows only.)
- `AGENTS.md` Layout: `data/icon.ico` (the app icon) under `data/`, and drop the icon from
  the `packaging/windows/` line.
- Spec status line: built, with the date. Tick this plan's boxes, with run notes for the
  manual checks.
- Build the setup, install it over v0.1.0, and run spec Testing → by hand on Windows,
  steps 1–7, on the installed app. Step 2's update item comes from a test release on the
  fork, as in the update-check plan's U7. Delete that test release afterwards.
- Mac: CI only, unless a Mac is at hand for spec Testing → by hand on a Mac. Say which
  in the PR.
- Push `tray-menu-spec` to the fork and open the PR to `or-keren/maplelens` *(ask
  Daniel first: both are outward-facing)*.

**Acceptance criteria:**
- [ ] Every spec success criterion holds, each with a test or a run note. Mac-only ones
      say whether a Mac or only CI checked them.
- [ ] The installed build: tray icon with the right icon, ⋯ menu, Hide/Show, and Quit
      from the tray all work. The hand-run Setup over a running MapleLens shows the new
      "still running" text. About shows the installed version and a real update
      status (spec Testing → by hand, step 8).
- [x] CI is green on the PR (Windows and macOS).
      *2026-11-07: or-keren/maplelens#12, both jobs green at `f241f57`
      ([run](https://github.com/or-keren/maplelens/actions/runs/42411025054)).*

**Verification:** the build, the installed run, and CI.

**Dependencies:** T1–T5, and T7 for the installed run. **Files:** `README.md`,
`AGENTS.md`, the spec, this plan.
**Scope:** S.

**Run notes (2026-11-07):**
- Docs done in `af05bfe`. The README's tray line doesn't say "right-click" ("Its menu is
  the same as •••"), so criterion 5's grep stays empty.
- `MapleLens-Setup-0.1.0.exe` built from `af05bfe`, bundle check and `--self-check`
  passing. A 0.1.1 was also built from this branch, with the version bumped only for the
  build and restored afterwards.
- **No test release** (Daniel): the PR goes up now, and Daniel publishes a release later.
  So the installed run (spec Testing → by hand, steps 1–7, including step 2's update item
  and step 7's "still running" text) and the Explorer look of the exe and Setup icons
  (T1) are still open. The PR says so.
- **Mac: CI only** (Daniel). The ••• and the text are the only Mac changes. Its by-hand
  check isn't done.

### Checkpoint C: done

- [ ] All spec success criteria met.
- [ ] PR open from the fork, CI green, Daniel has reviewed it.

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| The frozen app can't load `icon.ico` (no plugin path without an app, or `qico.dll` dropped) | High: a blank tray icon | T1 first. `--self-check` loads it, and the build fails if it doesn't. |
| A `QMenu` shown from the box or the tray takes focus from the game | High: the anti-goal | By-hand focus checks in T2 and T4, as in the update-check plan's focus runs. Same Qt path as today's right-click menu. |
| `menu.clear()` deletes the box's actions | Med: menu items vanish after one open | The box owns its actions. A test opens each menu twice and triggers an item after. |
| A tick re-shows a hidden box or arrow | Med: Hide doesn't stick | One `Shown` flag read by the tick and `allow_typing`, with a test for each. |
| "⋯" renders as a box or off-centre in Segoe UI | Low | T2 falls back to "•••" or painted dots, and T3's text follows. |
| On the Mac, the ⋯ menu opens under the panel | Low: the panel sits at `NSPopUpMenuWindowLevel - 1` | Spec Testing → by hand on a Mac, if a Mac is at hand. Otherwise the PR says it's unchecked. |
| The tray is collected because nothing holds it | Low | `main()` keeps the reference. The T4 by-hand run would show it at once. |
| The tick's `set_status` every 500 ms knocks the About view away, or × brings back stale tabs while the game is gone | Med: About flickers or lies | `set_status` only records while About is open, and × shows the recorded state. A test calls `set_status` both ways while open. |
| The About updates line disagrees with the menu (says "Up to date" while "Update to X…" is in the menu) | Med | One source: `UpdateCheck.status()` reads `release` first. A test for a dismissed update. |

## Open questions

- **Owner (from the spec): the icon's new home** in `src/maplelens/data/`. T1 assumes yes.
  If the owner says no, the build copies it there instead, and only T1 changes.
- ~~**Daniel: is a Mac at hand** for the spec's by-hand Mac check, or is it CI only
  (T6)?~~ CI only (Daniel, 2026-11-07).
