# MapleLens — Windows installer design

Date: 2026-11-06. Status: approved by Daniel (contributor) 2026-11-06; the owner
(or-keren) reviews it with the PR.

## Intent

Today players run MapleLens from source: install `uv`, clone the repo, `uv sync`,
`uv run python scripts/grab.py --title …`, then `uv run maplelens`. Most players won't
do that. This work lets a Windows player **download one `setup.exe` from GitHub,
install it, and start MapleLens from the Start menu** with no Python, `uv` or
command line.

The harness design already deferred this ("Release/packaging (PyInstaller exe)
workflow: when the EXP meter works"). The EXP meter and path arrow both work now.

The screen-only rule in `AGENTS.md` holds for every part of this document, unchanged.

## Scope: three modules, built in order

| Module id | Responsibility | Depends on |
|---|---|---|
| `first-run` | An installed MapleLens finds the game without `scripts/grab.py` | — |
| `installer` | Frozen app + `setup.exe` + release build in CI | `first-run` |
| `update-check` | Tell players a newer version is on GitHub and help them get it | `installer` |

This document specs **`first-run` and `installer`**. `first-run` is small and the
installed app is useless without it, so the two ship together. `update-check` has its
own spec (`docs/superpowers/specs/2026-11-06-update-check-design.md`) and ships in the
same PR, or-keren/maplelens#10, so v0.1.0 already has it (Daniel, 2026-11-07). The
installer is designed so it fits (see Goals → Upgrades).

## What's in the box today (checked 2026-11-06)

- Package data that has to ship: `src/maplelens/data/maps.json` (108 KB, 453 maps,
  adapted from meowdb) and **139 PNG glyph templates** under
  `src/maplelens/readers/templates/` (194 KB: the label images, `exp_font/`,
  `level_font/`), plus **299 minimap pictures** in `src/maplelens/data/minimaps/`
  (5.5 MB, added by the owner in `53eddbc` and used by the path arrow). All are found
  next to their module through `Path(__file__)` (`readers/glyphs.py`,
  `readers/map_name.py`, `tools/path_arrow/maps.py`), and both image loaders already
  read through `np.fromfile` + `cv2.imdecode`, so non-ASCII paths work.
- `maps.picture()` returns `None` when a map's picture file is missing, so a build that
  dropped the minimaps would **run without complaint** and the path arrow would just get
  worse. The build has to check this (Testing).
- Must **not** ship: `tests/fixtures/screens/` (61 PNGs, 1 MB), `scripts/level_sprites/`,
  `scripts/`, `docs/`.
- Runtime dependencies: PySide6, numpy, opencv-python-headless and the `winrt-*`
  packages (Windows Graphics Capture and Windows OCR).
- `app.py` prints its messages and tracebacks to the console, and exits on first run
  with `Run: uv run python scripts/grab.py --title <game title> --label first` when
  `settings.json` has no `window_title`.

## Goals

### first-run

- **Default title.** When `settings["window_title"]` is unset, MapleLens looks for a
  window titled exactly `MapleStory` (the client's title, as seen on the Mac where the
  same client runs under Wine). **Exact match only** for the default, so a browser tab
  like "MapleStory wiki – Chrome" never matches. Once a window matches, the title is
  saved to `settings.json`.
- **Picker as fallback** (Daniel: "a combination of 1 and 2"). The box's right-click
  menu gets **Pick game window…**, which lists `capture.list_windows()` and saves the
  chosen title. The player can use it any time, for example when the default doesn't
  match their client.
- **No exit, no console instruction.** When no game window is found, MapleLens keeps
  running and the box says so in plain words (e.g. "Looking for MapleStory… right-click
  to pick the game window"), and the tools get the existing "no reading" path.
- An explicitly saved `window_title` keeps today's behaviour (`pick_window`: exact
  first, else substring), so `grab.py` users notice nothing.
- Works the same on the Mac from source (a shared change in `app.py`, not
  Windows-only code).

### installer

- **Frozen app** with PyInstaller (named in the harness design), **one-folder** mode:
  `MapleLens.exe` plus its folder. One-file mode is rejected *(my call)*: it unpacks to
  a temp folder on every launch, starts slower and trips antivirus more often.
- **Windowed, no console.** Nothing the player needs goes only to stdout.
  Tracebacks that `report_once` prints today also go to a log file,
  `%APPDATA%\MapleLens\maplelens.log`, capped in size *(builder: simplest cap that works,
  e.g. truncate on start)*.
- **Bundled data**: `maps.json`, all 139 templates and all minimap pictures are inside the build at the same
  paths relative to their modules, so the `Path(__file__)` lookups work unchanged. A
  build missing any of them **fails**, not ships.
- **Installer**: Inno Setup, producing `MapleLens-Setup-<version>.exe` (Daniel chose
  Inno Setup over MSI and zip).
  - Per-user install to `%LOCALAPPDATA%\Programs\MapleLens`, **no admin prompt**.
  - Start-menu shortcut; desktop shortcut as an unticked option. No "start with
    Windows".
  - An uninstaller in Settings → Apps. Uninstall removes the program folder and
    shortcuts and **keeps** `%APPDATA%\MapleLens` (settings and EXP history are the
    player's data) *(my call)*.
  - Last installer page: "Launch MapleLens" (ticked).
- **Upgrades in place.** A fixed Inno `AppId` that never changes, so running a newer
  `setup.exe` installs over the old version, keeps settings and history, and leaves
  one entry in Settings → Apps. If MapleLens is running, the installer asks the
  player to close it rather than failing halfway. `update-check` builds on exactly
  this.
- **One version number.** `pyproject.toml`'s `version` feeds the installer name, Inno's
  `AppVersion`, the exe's file version and what the app reports at runtime (which
  `update-check` will compare against GitHub).
- **Unsigned** for now (Daniel, 2026-11-06). The README tells players that SmartScreen
  will warn, and how to get past it (More info → Run anyway).
- **Release flow: prepare → PR → merge releases** (Daniel, 2026-11-06: no manual
  approval of releases; merging the release PR is the approval).
  - **Prepare**: `.github/workflows/prepare-release.yml`, started by hand from the
    Actions tab (`workflow_dispatch`) with a `bump` choice: `patch`, `minor` or `major`.
    It bumps `version` in `pyproject.toml`, refreshes `uv.lock`, runs the same checks
    as `ci.yml`, and opens a PR from branch `release/vX.Y.Z` titled
    `release: vX.Y.Z`. It fails without opening a PR if that tag, branch or PR
    already exists.
  - **Release**: `.github/workflows/release.yml`, on every push to `main`. If
    `pyproject.toml`'s version has no `vX.Y.Z` tag yet, it runs the checks again,
    builds the app and installer on `windows-latest`, runs the smoke check (Testing),
    then creates tag `vX.Y.Z` and **publishes** a GitHub Release with
    `MapleLens-Setup-X.Y.Z.exe` attached and GitHub's generated release notes (the PRs
    merged since the last release). If the tag exists, it does nothing, so a release
    can't happen twice. Any failure publishes nothing and creates no tag. Every
    installed copy runs what it publishes, so the job that runs the checks and the
    build can only read the repo; a separate job that runs nothing but `gh` downloads
    the exe and publishes it. Actions are pinned to commits (or-keren's review).
  - **Checks run inside both workflows** (Daniel's choice): a PR opened with the
    built-in `GITHUB_TOKEN` doesn't start `ci.yml`, so the release PR shows no checks
    of its own. No extra secrets or GitHub App.
  - **Owner setup**: enable "Allow GitHub Actions to create and approve pull requests"
    (Settings → Actions → General). If `main` requires status checks, the release PR
    needs a manual re-run of `ci.yml` before it can merge (Open questions).
- **README**: a "Download" section for players (get the latest setup from Releases,
  the SmartScreen step, windowed/borderless game) above the from-source instructions,
  which stay for developers. Credit lines and third-party notices ship with the app.
- **AGENTS.md**: Layout and Commands list the new files and the build command.

## Non-goals

- **`update-check`**: checking GitHub for a newer version, downloading or applying it.
  Its own spec, shipped in the same PR (#10).
- **Code signing** (Daniel: unsigned for now).
- **MSI**, winget, Microsoft Store, Chocolatey.
- **A Mac app** (the Mac design already postpones `.app`, signing and notarisation).
- **Updating map data separately** from the app. New data ships as a new version.
- **Changing the data source.** `maps.json` stays as it is (see Open questions).
- **Ensuring Windows OCR language packs.** If OCR isn't available, the existing
  `None` path stands.

## Anti-goals

- Anything breaking the screen-only rule. In particular, the installer never looks
  for, reads or writes the game's install folder, files or registry keys, and the
  app gains no new way to touch the game process.
- Shipping the test fixtures or anything else in the repo that could hold a player's
  name or chat.
- An installer that needs admin rights, installs services or drivers, or changes
  system settings.
- A build that "works on my machine": the installer that players download is built
  by CI after a merge to `main`, never from a local `dist/`.

## Constraints

- `AGENTS.md` conventions hold. The guard's banned names stay out of `src/` and
  `scripts/`, comments included.
- **New dependency, dev-only:** `pyinstaller` in a new `build` dependency group (not in
  the runtime `dependencies`). After `uv lock`, `scripts/check_screen_only.py` (which
  also scans `uv.lock`) must still pass. Inno Setup is a build tool installed on the
  CI runner, not a Python dependency.
- **Licenses.** PySide6 is LGPL-3.0: the one-folder build keeps Qt as separate DLLs,
  and its license text ships in the app folder. OpenCV (Apache-2.0) and numpy (BSD)
  licenses ship too. Map data keeps the meowdb credit.
- **Size.** Exclude Qt modules MapleLens doesn't use (WebEngine, QML/Quick,
  Multimedia…). Record the installer size in the PR; above 150 MB needs a reason
  *(my call: a budget, not a hard limit)*.
- **Non-ASCII install paths.** The app installs under the player's profile
  (`C:\Users\<name>\…`), and `<name>` can be non-ASCII (Hebrew, Korean…). OpenCV's
  `cv2.imread` can't open such paths (`scripts/grab.py` already works around the same
  problem for `imwrite`), and `readers/glyphs.py` loads every template with it. Templates
  must load from any path (e.g. read the bytes, then `cv2.imdecode`), with a test that
  loads a template from a non-ASCII folder. *(Found while planning, 2026-11-06.)*
- PyInstaller, PySide6 and winrt details change between versions: check the
  current official docs and hooks before relying on any flag (source-driven).

## Commands (proposed; the builder may adjust names)

```
uv sync --group build                               # dev env + PyInstaller
uv run python scripts/build_installer.py            # freeze + installer → dist\
dist\MapleLens\MapleLens.exe                        # run the frozen app
dist\MapleLens-Setup-0.1.0.exe                      # the installer
```

Existing commands (`uv run pytest`, `uv run ruff check`, `uv run ruff format`, the
guard) are unchanged and must keep passing.

## Project structure

```
packaging/windows/maplelens.spec   PyInstaller spec (data files, Qt excludes, icon, version info)
packaging/windows/maplelens.iss    Inno Setup script (AppId, per-user, shortcuts, upgrade)
packaging/windows/icon.ico         app icon (if the owner has none, a plain placeholder)
scripts/build_installer.py         one entry point: read version, run PyInstaller, run Inno
.github/workflows/prepare-release.yml  manual: bump version → checks → release PR
.github/workflows/release.yml      push to main, new version → checks → build → smoke → tag + Release
src/maplelens/app.py               first-run behaviour, log file
src/maplelens/store.py             default title, if it lives there
tests/test_first_run.py            first-run logic
```

## Testing

- **Unit (pytest, no game, no build)** for `first-run`, as a pure function where
  possible: unset title + a window titled exactly `MapleStory` → found and saved;
  unset title + only `MapleStory wiki – Chrome` → not found; saved title keeps
  substring matching; picking a window saves its title.
- **Smoke check of the frozen build**, in CI and locally: the built exe starts, finds
  its bundled `maps.json`, every template and every minimap picture, and loads the
  Windows OCR engine, then exits with code 0 (or non-zero on any failure). The build
  also fails if the built app holds fewer template or minimap files than `src/`. *(Builder: a hidden
  `--self-check` flag on the exe or a check in the build script; the exit code is the
  signal since the exe has no console.)*
- **Manual, on a clean Windows** (Windows Sandbox, built into Windows 11 Pro): install
  with no Python present, launch from the Start menu, see the "looking for the game"
  box, open the picker, uninstall, confirm the program folder and shortcuts are gone
  and `%APPDATA%\MapleLens` stays.
- **Manual, with the game** on Daniel's PC: fresh install, game windowed at 1366×768
  and one other size, EXP meter and path arrow work as from source. Install a build
  with a higher version over it: settings and EXP history kept, one entry in
  Settings → Apps.

## Boundaries

- **Always:** run the four existing commands before every commit; work on a branch and
  open a PR to `or-keren/maplelens`; keep fixtures and `docs/` out of the build.
- **Ask first (the owner):** the `AppId` and app name before the first public release
  (they can't change after); the icon; anything in `ci.yml`; adding any runtime
  dependency; running the prepare workflow for the first real release.
- **Never:** push release tags or create Releases by hand (only `release.yml` does,
  after a merge); commit a built exe or `dist/`; touch the game's files or folder; add
  a banned module; weaken the guard to make a build pass.

## Success criteria

1. On a Windows 11 machine with no Python, `MapleLens-Setup-<version>.exe` installs
   without an admin prompt and MapleLens starts from the Start menu.
2. With the game running windowed and no `settings.json`, MapleLens finds the game by
   itself; with a non-default title, the player picks it once from the right-click menu.
   No console window appears at any point.
3. EXP meter and path arrow readings in the installed app match `uv run maplelens` on
   the same game screen.
4. Installing a newer version over an older one keeps settings and history and leaves
   one entry in Settings → Apps. Uninstalling leaves `%APPDATA%\MapleLens`.
5. Running the prepare workflow with `minor` on version 0.1.0 opens a PR
   `release: v0.2.0` that changes only the version in `pyproject.toml` and `uv.lock`.
   Merging it publishes Release `v0.2.0` with `MapleLens-Setup-0.2.0.exe` and
   generated notes, with no other manual step. A push to `main` that doesn't change
   the version releases nothing; a failed check, a failed smoke check or a missing
   template publishes nothing and leaves no tag.
6. `uv run pytest`, `ruff check`, `ruff format --check` and the guard pass on Windows
   and macOS CI.

## Open questions

- **Window title on Windows.** Is the game's Windows window title exactly
  `MapleStory`? The Mac spike saw that title; Daniel to confirm with
  `uv run python scripts/grab.py` (no arguments lists titles).
- **Data source.** `maps.json` comes from meowdb (453 maps). Daniel asked about the
  OSMS Data Explorer API (https://osmsdataexplorer.com/data/api/v1/, CC BY 4.0,
  extracted from the client), which on 2026-11-06 listed 336 maps, with minimap and
  render image URLs. Whether to switch or merge is a question for the owner and a
  separate change; it doesn't block the installer.
- **AppId, display name and icon:** the owner's call before the first release. Everything
  ships in one PR, and merging it publishes v0.1.0 (Daniel, 2026-11-06), so these are
  settled in that PR's review.
- **Who runs the prepare workflow and merges release PRs:** presumably the owner.
- **Required status checks on `main`:** if the owner has them, the release PR waits
  for a manual `ci.yml` run. If that becomes annoying, switch the prepare workflow to
  a GitHub App token (a later change).
