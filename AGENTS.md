# MapleLens — agent instructions

A screen-reading-only overlay for MapleStory Classic. Read this before changing anything.

## The rule (non-negotiable)

MapleLens is **screen-reading only**. It may capture pixels of the game
window and draw its own separate window on top. It must never:

- read or write game process memory, or inject into / attach to the process
- read, modify, or hook game files or the client's network traffic
- send input (keys/clicks) to the game — no automation of any kind

Breaking this can get players banned. `scripts/check_screen_only.py` enforces
it in CI and after every Claude Code edit. If a task seems to need any of the
above, stop and say so instead of working around it.

## Commands

```
uv sync                                      # set up / update the environment
uv run pytest                                # tests
uv run ruff check                            # lint
uv run ruff format                           # format
uv run python scripts/check_screen_only.py   # screen-only guard
uv run --group build python scripts/build_installer.py   # Windows: dist\MapleLens-Setup-X.Y.Z.exe; Mac: dist/MapleLens-X.Y.Z.dmg (Intel: -intel.dmg)
```

The build needs Inno Setup 6 (`winget install JRSoftware.InnoSetup --scope user`);
`--freeze-only` stops at the app folder `dist\MapleLens\`.

On the Mac, `--freeze-only`, `--sign-only` and `--dmg-only` run one stage; the build signs
with the identity in `MAPLELENS_SIGN_IDENTITY` (ad-hoc when unset).

## Layout

- `src/maplelens/` — the package
  - `capture.py` (shared: `pick_window`) + `capture_win.py` / `capture_mac.py` — find the game window, grab its pixels
  - `readers/` — screenshot → value (`glyphs`, `ocr`, `exp`, `level`, `job`, `map_name`, `minimap_pos` (`read_view`), `stat_window`, `skill_window`, `quest_window`, `quest_tracker` (the game's Quest Helper panel); `read_all` in `__init__`, with `due` / `found` for which windows to read this tick: one that isn't on screen is searched one tick in four, the minimap every tick); numbers via glyph templates, words (map, class, skill names) via the system OCR: `ocr.py` (shared) + `ocr_win.py` / `ocr_mac.py`. The draggable game windows (`window.py`, shared) are read differently: scaled from the window's own corner, digits by correlation with a margin, since exact templates miss at most sub-pixel offsets
  - `overlay.py` — the see-through `Layer` and draggable `Box` (its ••• menu button, `attach_menu`), the tab's `Row` (`on_hover` reports the mouse entering and leaving), `paint_box`, `FloatingWindow` (History's and Settings' setup: over the game, never taking the keyboard); `overlay_mac.py` — the macOS panels
  - `settings_window.py` — the Settings window: General (built by the app) and a section per tool (`settings_section()`)
  - `data/maps.json` — the map data; `data/minimaps/` — minimap pictures; `data/item_icons/` — reward item pictures; `data/icon.ico` — the app icon (the exe, Setup and the tray)
  - `data/monsters.json` — each map's monster cap, spawn spots and respawn timers, and monster stats (OSMS ids); `data/map_pictures/`, `data/monster_icons/` — their pictures
  - `data/classes.json` — per-job advice (training maps, AP/SP plans, gear)
  - `data/quests.json` — the quests (the NPCs, monsters and items each quest needs; event quests are left out)
  - `store.py` — settings file and data folder; `clean` puts a wrong saved value back to its default
  - `update.py` — the update check's pure part: GitHub's latest-release reply → `Release`, version compare, digest check (`MAPLELENS_UPDATE_REPO` overrides the repo)
  - `update_mac.py` — the Mac update helper: swaps the app from the downloaded dmg, then relaunches it
  - `reader.py` — the per-tick grab, trim and `read_all` (`read_game`), run here (`InlineReader`) or in a child process (`ProcessReader`)
  - `app.py` — entry point (`uv run maplelens`); also the update check's threads, download and handoff to Setup (`UpdateCheck`), the Windows tray icon (`make_tray`), Hide / Show (`Shown`) and the tick (`Tick`, which keeps `turn` / `seen_at` for that schedule; on the Mac it reads through `ProcessReader`, a helper process macOS doesn't slow, `make_reader`)
  - `tools/exp_meter/` — the EXP meter: `meter`, `history`, `text`, `ui`
  - `tools/path_arrow/` — the path arrow: `maps`, `route`, `camera`, `ui`
  - `tools/class_helper/` — the class helper: `data`, `plan`, `ui` (the Class tab, the training spot hover card `SpotCard`, and the marks on the stat and skill windows)
  - `tools/quest_helper/` — the quest helper: `data`, `plan`, `rewards`, `ui` (the Quests tab, which shows each quest's rewards; the box switches to it while a quest window is open)
- `scripts/check_screen_only.py` — the guard; banned lists live there, with reasons
- `scripts/grab.py` — save a cropped fixture screenshot of the game; `--screen` grabs the screen over it, MapleLens included, for README shots
- `scripts/profile_reads.py` — time `read_all` per reader on saved frames (`FRAME... [--passes N]`), to measure a change to the per-tick work
- `scripts/make_level_font.py` — build the level digit templates from `scripts/level_sprites/`
- `scripts/make_icon.py` — draw the icon: `src/maplelens/data/icon.ico`, `packaging/mac/icon.icns` (the Mac app), `docs/icon.png` (README), `docs/social-preview.png` (uploaded by hand: repo Settings → Social preview)
- `scripts/build_installer.py` — the Windows build (also the Mac freeze, sign and dmg stages): freeze, check the bundle, `MapleLens.exe --self-check`, Inno Setup; run locally and by `release.yml`
- `packaging/mac/` — `maplelens.spec` (PyInstaller), `icon.icns`; the bundle id `io.github.or-keren.maplelens` never changes
- `packaging/windows/` — `maplelens.spec` (PyInstaller), `maplelens.iss` (Inno Setup; its `AppId` never changes), `NOTICE.txt` and the license texts the build ships
- `.github/workflows/` — `ci.yml` (the checks), `prepare-release.yml` (started by hand: bumps the version, opens the release PR), `release.yml` (on push to `main`: publishes a version that has no tag yet)
- `tests/` — pytest; `tests/fixtures/screens/` holds cropped PNG screenshots, `tests/fixtures/github/` saved `releases/latest` replies
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — designs and plans

Planned, **not yet** created: `tools/<name>/` for prices.

## Conventions

- Readers are pure functions `screenshot -> value`, tested against PNG
  fixtures, so tests never need the game running.
- Each tool lives in its own folder and depends only on readers + overlay,
  never on another tool.
- Don't add a dependency for what a few lines can do. Never add a module on
  the guard's banned list.
- Don't write the banned module or Win32 names in comments or docstrings under
  `src/` or `scripts/` — the guard matches text.
- Never change `version` in `pyproject.toml` in a feature PR: a new version reaching
  `main` publishes a release. Releases go through Prepare release (CONTRIBUTING.md).

## Fixture screenshots

- Crop to the region the reader needs (EXP bar, minimap…), never the full screen.
- Never commit character names, chat, or other players' info.
- Put resolution and UI scale in the filename, e.g. `exp_bar_1366x768_100.png`.
