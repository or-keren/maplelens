# MapleLens — update check design

Date: 2026-11-06. Status: approved by Daniel (contributor) 2026-11-07; the owner
(or-keren) reviews it with the PR.

## Intent

The Windows installer (`docs/superpowers/specs/2026-11-06-windows-installer-design.md`,
PR or-keren/maplelens#10) puts MapleLens on players' PCs. Each release is a GitHub
Release with `MapleLens-Setup-X.Y.Z.exe`. But a player only hears about a release if they
look on GitHub, and then they install it by hand. This work lets the **installed app notice
a newer release and, after one click, update itself**.

This is the `update-check` module from the installer spec's capability map. It builds on
that spec's upgrade-in-place installer: same fixed `AppId`, settings and history kept, one
entry in Settings → Apps.

This ships in v0.1.0, inside or-keren/maplelens#10 with the installer (Daniel,
2026-11-07). So every installed version offers its own updates, and no player has to
install a second version by hand.

The screen-only rule in `AGENTS.md` holds unchanged. The check talks only to GitHub, over
HTTPS, from MapleLens's own process. It never touches the game, its files, its process or
its network traffic.

## What's there today (checked 2026-11-06, on `feat/windows-installer`)

- **Version:** `importlib.metadata.version("maplelens")` works in the frozen app. The
  PyInstaller spec copies the metadata, and `--self-check` fails without it.
- **Release:** `release.yml` publishes tag `vX.Y.Z` with one asset,
  `MapleLens-Setup-X.Y.Z.exe`, and never as a draft or prerelease.
- **Installer** (`packaging/windows/maplelens.iss`):
  - Per-user install, no admin prompt.
  - `InitializeSetup` asks to close a running MapleLens (the `MapleLensRunning` mutex),
    then ends it.
  - The last page's "Launch MapleLens" entry has `skipifsilent`, so it doesn't run in
    silent mode.
- **Box** (`overlay.py`):
  - `set_status(text)` shows one line *in place of* the tabs. It belongs to "Looking for
    MapleStory…", so the update notice can't use it.
  - `add_menu_item` and `add_submenu` add to the right-click menu.
  - The box never takes keyboard focus from the game, except the Path tab's search field.
- **Network:** MapleLens makes no network requests today. The guard bans packet-capture
  and traffic-interception modules, not plain HTTPS clients.
- **Settings:** `store.DEFAULTS`, saved as `settings.json` in `%APPDATA%\MapleLens`.

## Goals

- **Who checks:** only the installed Windows app, meaning the frozen exe (`sys.frozen`)
  on Windows (Daniel, 2026-11-06). `uv run maplelens` and the Mac never check: people
  running from source update with `git pull`, and the Mac has no installer. No network
  request at all on those paths.
- **When:** one check a few seconds after startup, then every 24 hours while MapleLens
  runs (Daniel). Not during `--self-check`. The check runs off the Qt thread and never
  delays a tick (500 ms): a slow or hanging GitHub costs nothing on screen.
- **What it asks:** `GET https://api.github.com/repos/or-keren/maplelens/releases/latest`
  with no token. That endpoint skips drafts and prereleases.
  - The repo is a constant in code, overridable by the `MAPLELENS_UPDATE_REPO`
    environment variable so it can be tested against Daniel's fork *(my call)*.
  - User-Agent `MapleLens/<version>`, with nothing about the player.
  - A short timeout.
- **Newer means:** the tag's `X.Y.Z` (after `v`) is greater than the running version,
  compared as three integers. A tag that isn't `vX.Y.Z`, or a release with no
  `MapleLens-Setup-X.Y.Z.exe` asset, counts as "no update".
- **How the player finds out** (Daniel: box line + menu item, no pop-up):
  - **A notice line in the box**, apart from the status line and leaving the tabs in place:
    "Update to X.Y.Z: right-click" (2026-11-07: "MapleLens X.Y.Z is out, right-click to
    update" measured 275 px, too wide for the box). It has a small **×**. Clicking it hides
    the line for that version only (`update_dismissed` in settings). A newer version
    brings the line back.
  - **Menu item "Update to X.Y.Z…"** in the right-click menu, there whenever an update
    is known, dismissed or not.
  - Neither one takes keyboard focus from the game or raises a window.
  - The line has to fit the box's 186 px tab width. The builder checks it, as the
    installer work did for "Looking for".
- **One-click update** (Daniel), from "Update to X.Y.Z…":
  1. Download the asset's `browser_download_url` to a temp folder under MapleLens's data
     folder. Off the Qt thread, with the notice line showing "Downloading X.Y.Z…".
  2. **Check its SHA-256** against the asset's `digest` field from the same API reply
     (`sha256:<hex>`). If it doesn't match, or GitHub gave no digest, **never run it**.
  3. Start the setup and quit MapleLens. The player sees no extra prompts in between:
     no "close MapleLens?" box and no wizard pages to click through. They see the
     installer's progress, then MapleLens starts again on the new version.
  4. Settings and history survive, as with any upgrade, and the session in progress is
     saved the way Quit saves it (`aboutToQuit`). It is never killed.
- **Opt-out** (Daniel: menu toggle):
  - A checkable menu item "Check for updates automatically", on by default, saved as
    `update_check` in settings.
  - Off means no automatic requests.
  - A separate **"Check for updates now"** menu item always works, so a player with the
    toggle off can still ask.
- **Failures are quiet but visible:**
  - Offline, rate-limited (60 requests per hour per IP without a token; we make about
    one a day), GitHub down, or a malformed reply: no line, no menu item, one entry in
    `maplelens.log`, and the next scheduled check tries again.
  - A manual "Check for updates now" that fails shows "Couldn't check for updates" in the
    notice line, so the click isn't met with silence. "No update" shows "MapleLens is up
    to date".
  - A failed download or digest mismatch shows "Update failed: right-click" (the menu
    item tries again) and logs the reason. The old version keeps running.
- **README:** one line under Download: MapleLens checks GitHub for new versions, what it
  sends (an HTTPS request with its version in the User-Agent), and how to turn it off.

## Non-goals

- **Updating from source or on the Mac** (Daniel): see Goals → Who checks.
- **Automatic install without a click**: rejected. It would restart the overlay
  mid-session, and run an unsigned exe the player never approved.
- **Delta updates, background install, or a separate updater exe**: the full setup exe is
  about 60 MB and upgrades in place already.
- **Code signing**: still a later spec. A file downloaded by MapleLens itself gets no
  Mark-of-the-Web, so SmartScreen doesn't prompt. The digest check is what stands
  between the player and a swapped file.
- **Release channels, prereleases or "skip this version forever"**: `releases/latest`
  only. The × hides one version's line, and the menu item stays.
- **Changelogs in the app**: the notice links nowhere. The Release page has the notes.

## Anti-goals

- Anything that breaks the screen-only rule. The update code never looks at the game's
  window, process, files or traffic. It sends no input and starts no process other
  than MapleLens's own setup.
- A pop-up, a focus steal, or a window that covers the game.
- Running a file whose SHA-256 wasn't checked against GitHub's digest.
- Losing the EXP session in progress, or leaving the player with no MapleLens (old one
  gone, new one not started) without saying so.
- Any network request from source runs, the Mac, `--self-check`, or with the toggle off
  (except "Check for updates now").

## Constraints

- **No new dependency.** Python's standard library does the request, the JSON, the
  SHA-256 and the version compare (`AGENTS.md`: no dependency for what a few lines can
  do).
- **Pure core, thin wiring**, the way readers are pure:
  - A module `src/maplelens/update.py` holds the pure parts: parse the API reply into
    "version + asset URL + digest, or nothing", compare versions, check a file's digest.
    It is tested against JSON fixtures, with no network.
  - The thread, the timer, the download, starting setup and quitting live in `app.py` or
    a thin layer over it.
  - `update.py` depends on nothing in `tools/` or `readers/`.
- **Installer changes** go in `maplelens.iss`. Two options: the app passes Inno's silent
  flags (`/SILENT /SP- /SUPPRESSMSGBOXES /NOCANCEL`), plus a `[Run]` entry that relaunches
  MapleLens after a silent install (`skipifsilent` blocks today's). Or the app runs the
  normal wizard and only the extra prompts go. Either way, a hand-run setup keeps today's
  pages and its "close MapleLens?" prompt.
- **Order on update:** MapleLens has to be gone (mutex released) before Setup's
  `InitializeSetup` looks. Otherwise Setup's own close path ends it with `taskkill` and
  the session in progress is lost. The builder makes this race-free. For example, Setup
  can wait for the mutex to go before asking anything. Or the app can start Setup only
  as its very last step, after the save.
- **Paths:** the download folder may contain non-ASCII characters (`C:\Users\דניאל\…`).
  Starting the setup from there must work.
- **No banned names** in code or comments under `src/` or `scripts/`. The guard runs on
  every edit.

## Commands

```
uv sync
uv run pytest                                   # incl. tests/test_update.py
uv run ruff check
uv run ruff format --check
uv run python scripts/check_screen_only.py
uv run --group build python scripts/build_installer.py   # setup exe, for the manual runs
```

## Project structure

- `src/maplelens/update.py`: new, the pure update logic.
- `src/maplelens/app.py`: schedules checks, runs them off the Qt thread, wires the menu
  items and the update action.
- `src/maplelens/overlay.py`: the box's notice line with its ×, apart from `set_status`.
- `src/maplelens/store.py`: `update_check` (True) and `update_dismissed` (None) in
  `DEFAULTS`.
- `packaging/windows/maplelens.iss`: relaunch and no-prompt behaviour for an update run.
- `tests/test_update.py`: new. `tests/fixtures/github/`: new, saved
  `releases/latest` replies (a newer release, the same version, no asset, a bad tag, no
  digest).
- `README.md`, `AGENTS.md` (Layout), `CONTRIBUTING.md` (testing updates against the fork).

## Testing

- **Unit, no network** (`tests/test_update.py`):
  - parse each fixture
  - compare versions: `0.1.0 < 0.2.0`, `0.9.0 < 0.10.0`, equal is "no update", junk is
    "no update"
  - digest match, mismatch and missing
  - only `MapleLens-Setup-X.Y.Z.exe` is picked from the assets
  - the frozen-on-Windows gate, and no check with `update_check` off
- **Offscreen Qt** (`tests/test_overlay.py`): the notice line shows without hiding the
  tabs, the × hides it and records the version, and it fits 186 px.
- **On the fork, by hand** (all workflow and release testing stays on
  `dbeilin/maplelens`, as in the installer plan):
  1. Build and install version N with `MAPLELENS_UPDATE_REPO=dbeilin/maplelens`.
  2. Publish N+1 on the fork by hand (`gh release create`, with a locally built setup),
     so the fork's `main` is left alone. GitHub computes the asset's digest itself.
  3. Start N: within seconds the line and menu item show N+1.
  4. Click "Update to N+1…": it downloads, Setup runs with no prompts, and MapleLens
     comes back as N+1 with settings and history intact.
  5. The tampered download is a test, not a manual run (2026-11-07). `tests/test_app.py`
     gives the update a download with the wrong bytes, one with no digest and one that
     fails. Setup never runs, the line says the update failed, and the log says why.
  6. Run once offline: no line, one log entry.
  7. Afterwards, delete the fork's test tags and releases.

## Boundaries

- **Always:** keep the core pure and tested with fixtures. Run the four checks before
  each commit. Test downloads and installs only against the fork.
- **Ask first:** any new dependency. Any change to how a hand-run setup behaves. Sending
  anything to GitHub beyond the one request and the download.
- **Never:**
  - point a test at `or-keren/maplelens` releases
  - run an unchecked download
  - add a pop-up or focus steal
  - touch the game in any way

## Success criteria

1. With an installed N and a published N+1, the installed app shows "Update to N+1:
   right-click" in the box and "Update to N+1…" in the menu within 10 s of starting, and
   the tabs still show.
2. Clicking "Update to N+1…" ends with MapleLens running N+1. No prompts were clicked,
   the game kept the keyboard throughout, settings and the history DB are unchanged,
   and Settings → Apps has one entry at N+1.
3. A download whose SHA-256 doesn't match the digest, or a release with no digest, is
   never run. The notice says the update failed, and the log says why.
4. Offline, rate-limited, or with no newer release: no notice, no menu item, at most one
   log line per check, and ticks stay on time.
5. With "Check for updates automatically" off, MapleLens makes no request until "Check
   for updates now" is clicked. The setting survives a restart.
6. `uv run maplelens` and the Mac make no request. `--self-check` makes none either.
7. ×-dismissing N+1 hides the line until restart and after it. The menu item stays.
   N+2 shows the line again.
8. `uv run pytest`, `ruff check`, `ruff format --check` and the guard pass on Windows
   and macOS CI.

## Open questions

- **Owner: is calling home OK?** One HTTPS request to GitHub a day, on by default, with
  an opt-out. It is the first network traffic MapleLens makes. The README will say so.
- **Owner: repo name.** The check is pinned to `or-keren/maplelens`. If the repo is ever
  renamed or moved, GitHub's redirects cover the API for a while, but old installs follow
  only as long as the redirect lasts.
- **Builder: silent install or wizard.** Run Setup with `/SILENT` plus a relaunch entry,
  or show the normal wizard without the close prompt. Pick by what the player sees in
  Windows Sandbox (Constraints → Installer changes).
- ~~**Which version ships it**~~ Closed 2026-11-07: v0.1.0, inside #10 (Daniel). See
  Intent.
