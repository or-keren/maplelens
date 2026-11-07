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
uv run --group build python scripts/build_installer.py   # Windows: dist\MapleLens-Setup-X.Y.Z.exe
```

The build needs Inno Setup 6 (`winget install JRSoftware.InnoSetup --scope user`);
`--freeze-only` stops at the app folder `dist\MapleLens\`.

## Layout

- `src/maplelens/` — the package
  - `capture.py` (shared: `pick_window`) + `capture_win.py` / `capture_mac.py` — find the game window, grab its pixels
  - `readers/` — screenshot → value (`glyphs`, `ocr`, `exp`, `level`, `job`, `map_name`, `minimap_pos` (`read_view`); `read_all` in `__init__`); numbers via glyph templates, words (map, class) via the system OCR: `ocr.py` (shared) + `ocr_win.py` / `ocr_mac.py`
  - `overlay.py` — the see-through `Layer` and draggable `Box`; `overlay_mac.py` — the macOS panels
  - `data/maps.json` — the map data; `data/minimaps/` — minimap pictures
  - `store.py` — settings file and data folder
  - `update.py` — the update check's pure part: GitHub's latest-release reply → `Release`, version compare, digest check (`MAPLELENS_UPDATE_REPO` overrides the repo)
  - `app.py` — entry point (`uv run maplelens`); also the update check's threads, download and handoff to Setup (`UpdateCheck`)
  - `tools/exp_meter/` — the EXP meter: `meter`, `history`, `text`, `ui`
  - `tools/path_arrow/` — the path arrow: `maps`, `route`, `camera`, `ui`
- `scripts/check_screen_only.py` — the guard; banned lists live there, with reasons
- `scripts/grab.py` — save a cropped fixture screenshot of the game
- `scripts/make_level_font.py` — build the level digit templates from `scripts/level_sprites/`
- `scripts/build_installer.py` — the Windows build: freeze, check the bundle, `MapleLens.exe --self-check`, Inno Setup; run locally and by `release.yml`
- `packaging/windows/` — `maplelens.spec` (PyInstaller), `maplelens.iss` (Inno Setup; its `AppId` never changes), the icon, `NOTICE.txt` and the license texts the build ships
- `.github/workflows/` — `ci.yml` (the checks), `prepare-release.yml` (started by hand: bumps the version, opens the release PR), `release.yml` (on push to `main`: publishes a version that has no tag yet)
- `tests/` — pytest; `tests/fixtures/screens/` holds cropped PNG screenshots, `tests/fixtures/github/` saved `releases/latest` replies
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — designs and plans

Planned, **not yet** created: `tools/<name>/` for the class helper and prices.

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
