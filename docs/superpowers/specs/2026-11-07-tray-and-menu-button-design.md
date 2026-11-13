# MapleLens — tray icon and menu button design

Date: 2026-11-07. Status: decisions made by Daniel (contributor) 2026-11-07; built
2026-11-07 (`docs/superpowers/plans/2026-11-07-tray-and-menu-button.md`), except About
(Goals → About, plan task T7), added the same day and not built yet. The owner
(or-keren) reviews it with the PR.

## Intent

Two problems with how players reach MapleLens's menu today:

1. **No tray icon.** While MapleLens runs on Windows, nothing in the taskbar's notification
   area shows it. A player who loses track of the box (dragged off-screen, game moved)
   has no way to find MapleLens, quit it or tell that it's running.
2. **The menu is hidden.** "Pick game window…", the update items and Quit only open when
   you right-click the box. Nothing on the box says a menu exists, so the box's text has
   to say "right-click".

This work adds a **tray icon on Windows**, plus a visible **⋯ button** on the box. Both
open the same menu the box's right-click opens today.

3. **No way to tell which version is running** (Daniel, 2026-11-07, after T1–T5 were
   built). The version is read at runtime for the update check and the User-Agent, but
   nothing shows it. Installed players can find it in Settings → Apps, but nobody looks
   there. An **About view** inside the box fixes this (see Goals → About).

The glyph ended up as "•••" (T2). Where this spec says "⋯", the app shows "•••".

The screen-only rule in `AGENTS.md` holds unchanged. The tray icon and the button belong
to MapleLens's own windows. They never touch the game's window, process, files or
traffic, and they send no input to it.

## What's there today (checked 2026-11-07, on `main` at 4199c20, v0.1.0)

- **Menu** (`overlay.py`): `Box.add_menu_item`, `add_toggle` and `add_submenu` add
  `QAction`s to the box itself, and the box shows them with `Qt.ActionsContextMenu`. So
  the box's own action list *is* the menu. Items come from three places:
  - `build_box` in `app.py`: "Pick game window…" and "Quit MapleLens"
  - the update check: "Update to X.Y.Z…" at the top, plus "Check for updates
    automatically" and "Check for updates now", added at runtime
- **Box layout:** a column of the tab strip, the pages, the status line and the notice
  line. `set_status(text)` hides the tab strip and the pages and shows one line in their
  place. That's the "Looking for MapleStory…" state, which is exactly when a new player
  needs "Pick game window…".
- **Showing:** `build_box` shows the box once. Each tick, `main()` shows or hides the
  `Layer` (the path arrow's see-through window) depending on whether the game was found.
  `Box.allow_typing` calls `show()`, because changing a window flag hides the window.
- **Text that says "right-click":**
  - `app.py`: `LOOKING`, `update_notice()`, `UPDATE_FAILED`, and `build_box`'s docstring
  - `overlay.py`: three docstrings
  - `README.md`: the install, updating and window-picking steps
  - `packaging/windows/maplelens.iss`: "Quit it from its right-click menu"
- **Icon:** `packaging/windows/icon.ico`. The exe and Setup use it (`maplelens.spec`
  `icon=`, `.iss` `SetupIconFile`). It isn't package data, so the running app can't load
  it.
- **Mac:** the box is a non-activating panel, and MapleLens runs with no Dock icon or menu
  bar of its own (`overlay_mac.make_accessory`). The panel sits at
  `NSPopUpMenuWindowLevel - 1`: above the game, below menus. So a menu opened from the
  box should show above it.

## Goals

- **One menu, three ways to open it** (Daniel: "both"):
  - the **⋯ button** on the box: the advertised way
  - **right-clicking the box**: kept as an unadvertised shortcut (Daniel)
  - **right-clicking the tray icon** (Windows)

  All three show the box's own action list at the moment they open. So an item the update
  check adds later shows up everywhere, and nothing has to keep two lists in step.
- **⋯ button** (Daniel: top-right, always):
  - Sits at the top-right corner of the box in **every** state: next to the tabs, and
    next to the "Looking for MapleStory…" status line when the tabs are hidden.
  - Clicking it opens the menu just under the button. It's styled like the notice line's
    ×: flat, grey (`LABEL_COLOR`), pointing-hand cursor, no focus (`Qt.NoFocus`).
  - Clicking it never starts a drag of the box, and never takes keyboard focus from the
    game.
- **Tray icon** (Windows only, Daniel):
  - Shows while MapleLens runs, from `uv run maplelens` and from the installed app.
    It uses the app icon, and its tooltip is "MapleLens".
  - **Right-click** opens the menu.
  - **Left-click** shows or hides the box (Daniel).
  - Quitting from the tray menu is the same `QApplication.quit`, so the session in
    progress is saved through `aboutToQuit` as today.
- **Hide / Show** *(my call: what "hide" covers)*:
  - A menu item, just before Quit, reads "Hide MapleLens" while the box shows and "Show
    MapleLens" while it's hidden. Left-clicking the tray icon does the same thing.
  - Hiding hides **everything MapleLens draws over the game**: the box, and the `Layer`
    with the path arrow. A hidden box with the arrow still pointing would be half-hidden.
  - The tools **keep running** while hidden. The EXP meter keeps recording, the path
    arrow keeps following the trip, and the update check keeps checking. Hiding is about
    the screen, not about pausing.
  - Not saved: every start shows the box (Daniel).
  - Nothing a tick does brings a hidden box or `Layer` back. That includes
    `allow_typing`'s `show()` and the tick's `layer.show()`.
  - The item exists only where there's a tray icon. On a Mac there would be no way back
    once the box and its ⋯ were gone. *(Since 2026-11-08 the Mac has a Dock icon: its
    menu is the box's, a click on it shows a hidden box, and so the Mac has the item too.
    See the Mac installer spec.)*
- **Text points at ⋯:**
  - `LOOKING` → "Looking for MapleStory…" alone. The ⋯ beside it is hint enough (Daniel,
    2026-11-07, which replaced "… click ⋯ to pick the game window").
  - `update_notice(v)` → "Update to X.Y.Z: click ⋯"
  - `UPDATE_FAILED` → "Update failed: click ⋯"
  - README: each "right-click the box" becomes "click ⋯ on the box". One line under
    install adds the tray icon: left-click hides or shows MapleLens, and right-click has
    the same menu.
  - `.iss`: "Quit it from the ⋯ menu on its box or its tray icon, …"
  - The docstrings in `overlay.py` and `app.py` say "the box's menu" instead of
    "right-click menu".
- **The notice line still fits** the 186 px `TAB_W` at version 10.10.10, with its ×.
  The existing `test_notice_fits_the_tab_width_at_the_longest_version` covers the new
  text.
- **About** (Daniel, 2026-11-07: "an About panel", inside the box, after mockups of a menu
  header, a footer, the tray tooltip and a panel beside the box):
  - A menu item **"About MapleLens"**, just before Quit (after Hide on Windows). It
    shows in all three menus, because it's one of the box's actions.
  - It opens an **About view inside the box**, in place of the tabs. It works the way
    the "Looking for…" line does, so there's no second window over the game and nothing
    to position:

    ```
    ┌──────────────────────────┐
    │ About MapleLens   ×  ••• │
    │ Version                  │
    │ 0.1.0                    │
    │ Updates                  │
    │ Up to date               │
    │ GitHub page ↗            │
    └──────────────────────────┘
    ```
  - **Top row:** "About MapleLens" in place of the tab strip or the status line, then
    a × (styled like the notice line's ×), then the •••, which still opens the menu.
    × brings back whatever the box would show now: the tabs, or "Looking for
    MapleStory…" if the game went away while About was open.
  - **Version:** `version("maplelens")`, in the box's grey label and white value style.
  - **Updates:** one line from the update check, read again each tick while the view is
    open, so "Checking…" turns into the answer without reopening:
    - "Checking…" while a check runs
    - "Update to X.Y.Z available" (in `ACCENT`) once one is known, dismissed or not. The
      menu's "Update to X.Y.Z…" item is still how the player updates.
    - "Up to date" after the last check found nothing newer
    - "Couldn't check" after the last check failed
    - "Not checked yet" before the first check, with automatic checks on
    - "Automatic checks off" with the toggle off and no check run since starting
    - "Running from source" where there's no update check: `uv run maplelens`, and the
      Mac.
  - **GitHub page ↗:** a link in `ACCENT` that opens `https://github.com/<update.REPO>`
    in the player's browser (`QDesktopServices.openUrl`). So it follows
    `MAPLELENS_UPDATE_REPO` like the update check. The browser taking focus is the
    player's own click, not a focus steal.
  - The view fits the 186 px `TAB_W` at version 10.10.10, so opening About never widens
    the box. The longest line is "Update to 10.10.10 available".
  - Not saved: About is closed at every start. Hide / Show leaves it as it was.
  - Opening it never takes keyboard focus from the game, the same as the •••.

## Non-goals

- **Tray or menu-bar icon on the Mac** (Daniel: Windows only for now). The Mac gets the ⋯
  button, because it's part of the box, but no status item and no Hide item. Revisit once
  Mac support has been tested on real hardware.
- **Pop-ups or balloon notifications** (Daniel). The update-check design's "no pop-up"
  stands. The tray tooltip doesn't mention updates either.
- **Remembering Hide across restarts** (Daniel).
- **A hotkey to hide or show.** It would need a global keyboard hook, and the box never
  listens to the game's keyboard.
- **Minimize-to-tray, close-to-tray, or "start with Windows".** The box has no close
  button, and the installer spec already rejected autostart.
- **A new menu layout.** The items and their order stay as they are, plus Hide/Show and
  About.
- **More in About** (Daniel): no release-notes link, no licences or credits, no "reads
  the screen only" line, and no update button (the menu item does that). The tray
  tooltip stays "MapleLens", without the version.
- **A separate About window or dialog** (Daniel): it would be a second window over the
  game. A modal dialog would also take focus.

## Anti-goals

- Anything that breaks the screen-only rule.
- A focus steal. Clicking ⋯ or the tray icon must never take the keyboard from the game,
  beyond what a context menu does today. On the Mac the panel stays non-activating.
- Two menus that can drift apart: a second list of actions kept by hand for the tray.
- A hidden MapleLens that stops recording, or a Hide that leaves no way back.

## Constraints

- **No new dependency.** `QSystemTrayIcon` and `QMenu` are in PySide6, which MapleLens
  already uses. No `pystray`.
- **Menu from the box's actions:** one helper (e.g. `Box.menu_for(parent) -> QMenu`, the
  builder's choice of name) builds a `QMenu` from `self.actions()` when it opens. The ⋯
  button and the tray icon both use it. Sharing a `QAction`, including the "Pick game
  window…" submenu's `menuAction()`, across several menus is supported by Qt.
- **Tray only where it can work:** create it only when `sys.platform == "win32"` and
  `QSystemTrayIcon.isSystemTrayAvailable()`. Elsewhere, including offscreen tests, there's
  no tray and no Hide item, and nothing breaks.
- **Icon as package data** *(my call)*: move `packaging/windows/icon.ico` to
  `src/maplelens/data/icon.ico`, so `collect_data_files("maplelens")` ships it and the
  app loads it next to `maps.json`. `maplelens.spec` (`icon=`), `maplelens.iss`
  (`SetupIconFile`) and `tests/test_build_installer.py` point at the new path, so there's
  one copy. The alternative is two copies of the same file.
- **Layout:** the tab strip and the status line share a top row with the ⋯ on its right.
  The box still hugs its current content (`SetFixedSize`). It may grow wider for the
  longer "Looking for…" line, or that line may wrap onto two lines. The builder picks by
  how it looks at 100% and 150% scaling.
- **Glyph:** "⋯" (U+22EF) has to render in Segoe UI on Windows and Helvetica Neue on the
  Mac, through Qt's font fallback. If it doesn't, draw three dots or use "•••". The text
  uses whichever glyph the button shows.
- **No banned names** in code or comments under `src/` or `scripts/`.
- **Tools stay apart:** the tray icon and Hide live in `overlay.py` and `app.py`, not in
  a tool.
- **About is split the same way:** `overlay.py` draws the view and knows nothing about
  updates. It takes the version, an "updates" text and the URL. `app.py` supplies them.
  `UpdateCheck` gets one method for its status line, based on state it already keeps
  (the running thread, `release`, the toggle), plus the last check's outcome, which is
  the one new piece of state. Exact names are the builder's call.
- **The view and the status line don't fight:** the tick calls `set_status` every
  500 ms. While About is open, that call records the state but shows nothing, and × shows
  whatever was recorded last.

## Commands

```
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run python scripts/check_screen_only.py
uv run --group build python scripts/build_installer.py   # icon path, frozen tray run
```

## Project structure

- `src/maplelens/overlay.py`: the ⋯ button and the shared top row, and the menu helper.
  Docstrings drop "right-click". The About view and its ×.
- `src/maplelens/app.py`: the tray icon and its left/right click, Hide/Show (box +
  `Layer`, kept hidden across ticks and `allow_typing`), and the new text. The "About
  MapleLens" item, its updates line (`UpdateCheck`'s status, or "Running from source"),
  and refreshing that line each tick while About is open.
- `src/maplelens/data/icon.ico`: moved from `packaging/windows/icon.ico`.
- `packaging/windows/maplelens.spec`, `maplelens.iss`: the icon path, and the
  "still running" message.
- `tests/test_overlay.py`, `tests/test_app.py`, `tests/test_build_installer.py`.
- `README.md`. `AGENTS.md` (Layout: the icon's new home).

## Testing

- **Offscreen Qt** (`tests/test_overlay.py`):
  - The ⋯ button is visible with tabs, and while `set_status` shows "Looking for…".
  - Its menu lists the same items as `box.actions()`, in order, including one added after
    the box was built (an update item at `at=0`).
  - Right-click still opens the menu (`contextMenuPolicy` unchanged).
  - The button has `Qt.NoFocus`, and pressing it doesn't start a drag (`_drag_from`
    stays `None`).
- **`tests/test_app.py`:**
  - The new `LOOKING`, `update_notice` and `UPDATE_FAILED` text. The notice still fits
    `TAB_W` at 10.10.10 (the existing test).
  - Hide/Show, with the tray part behind a seam the test can drive (a fake tray, or the
    toggle function called directly): Hide hides the box and the `Layer`, and a tick
    afterwards with the game found leaves both hidden while the tools still update. Show
    brings both back. The item's label flips.
  - With no tray available (offscreen), there's no Hide item and no tray is created.
- **`tests/test_build_installer.py`:** the icon is at its new path, and the frozen bundle
  contains `maplelens/data/icon.ico`.
- **About** (`tests/test_overlay.py`, `tests/test_app.py`, offscreen):
  - Opening About hides the strip, the pages and the status line. It shows the title,
    the ×, the •••, the version and the updates line. × brings the tabs back.
  - `set_status("Looking…")` while About is open shows nothing new. × then shows
    "Looking…", not the tabs, and `set_status(None)` after × shows the tabs.
  - `UpdateCheck`'s status line, for each state: a check running, a newer release, no
    newer release, a failed check, none run yet, and the toggle off. A dismissed update
    still says "Update to X.Y.Z available". With no `UpdateCheck` the line is "Running
    from source".
  - The updates line changes while About stays open, once a check finishes and the tick
    runs.
  - The link opens `https://github.com/` + `update.REPO` (with `openUrl` monkeypatched),
    and follows `MAPLELENS_UPDATE_REPO`.
  - The view at version 10.10.10, with "Update to 10.10.10 available", is no wider than
    `TAB_W`.
  - "About MapleLens" is just before Quit, and after Hide when there's a tray.
- **By hand on Windows**, installed build and `uv run maplelens`:
  1. The tray icon shows with the MapleLens icon and the "MapleLens" tooltip.
  2. Right-clicking the tray icon and clicking ⋯ both show the same menu, including
     "Update to X.Y.Z…" when there is one (against the fork, as in the update-check plan).
  3. Left-clicking the tray icon hides the box and the arrow, and again brings them back.
     While hidden, the EXP session keeps counting.
  4. Quit from the tray saves the session (it's in History after a restart).
  5. With the game focused, clicking ⋯ or the tray icon never leaves the game without
     the keyboard after the menu closes.
  6. "Looking for MapleStory…" shows the ⋯, and "Pick game window…" works from it.
  7. Running a hand-started Setup while MapleLens runs shows the new "still running" text.
  8. About from •••, from the tray menu and from right-click shows the right version.
     On the installed app it shows a real update status: "Up to date" against the
     owner's repo, "Update to … available" against a fork with a newer release. From
     source it says "Running from source". × brings back the tabs. "GitHub page ↗" opens
     the repo, and the game still has the keyboard after × (before the link is used).
- **By hand on a Mac** (`uv run maplelens`): the ⋯ menu opens above the box, the game
  keeps the keyboard, and there's no tray icon and no Hide item.

## Boundaries

- **Always:** keep one menu, built from the box's actions. Run the four checks before
  each commit.
- **Ask first:** any new dependency. Any change to the menu's items or order beyond
  Hide/Show and About. A tray icon on the Mac. Anything more in About.
- **Never:** a pop-up, a focus steal, a global hotkey, or touching the game in any way.

## Success criteria

1. On Windows, a tray icon shows while MapleLens runs, from source and installed.
2. The tray's right-click menu, the ⋯ menu and the box's right-click menu list the same
   items in the same order, and update items added at runtime show in all three.
3. The ⋯ shows in the box's top-right corner with tabs and in the "Looking for…" state,
   on Windows and the Mac.
4. Left-clicking the tray icon, or "Hide MapleLens", hides the box and the arrow until
   the player shows them again. Recording carries on, and the next start shows the box.
5. No text the player sees in the app, the README or the installer says "right-click".
6. The update notice fits 186 px at 10.10.10.
7. The Mac has no tray icon and no Hide item. Nothing changes for it except the ⋯
   button and the text.
8. `uv run pytest`, `ruff check`, `ruff format --check` and the guard pass on Windows and
   macOS CI. The installer build passes its bundle check and `--self-check`.
9. "About MapleLens", in every menu, shows the running version and a true updates line
   inside the box, with no second window, no focus taken, and no change in the box's
   width. × brings back the tabs or "Looking for…", whichever is current.
10. "GitHub page ↗" opens the repo the update check uses.

## Open questions

- **Owner: the icon's new home.** Moving `icon.ico` into `src/maplelens/data/` changes
  where the installer spec said it lives. Is that OK, or should the build copy it there
  instead?
- ~~**Builder: one line or two** for "Looking for MapleStory… click ⋯ to pick the game
  window", next to the ⋯ (Constraints → Layout).~~ Gone: the line is now just "Looking
  for MapleStory…", which fits on one.
