# MapleLens — Mac installer design

Date: 2026-11-07. Status: approved by the user 2026-11-07; the owner (or-keren) reviews it with the PR.

## Intent

Windows players download one `setup.exe` from GitHub Releases, install it with no Python
or command line, start MapleLens like any app, and later update it with one click
(`2026-11-06-windows-installer-design.md`, `2026-11-06-update-check-design.md`). Mac
players still run from source (`2026-11-06-mac-support-design.md` deferred "a downloadable
Mac app").

This work gives **Mac players the same experience as Windows players** (user,
2026-11-07): download from the same Release, install without Terminal, start from
Applications/Launchpad, the box finds the game by itself, and the app offers new versions
and updates itself in one click.

The screen-only rule in `AGENTS.md` holds for every part of this document, unchanged.

## What's there today (checked 2026-11-07, `main` at 4199c20)

- Mac support works from source: `capture_mac.py` (`CGWindowListCreateImage`, sRGB),
  `ocr_mac.py` (Vision), `overlay_mac.py` (non-activating panels; `make_accessory()`, no
  Dock icon, until 2026-11-08, when the user asked for a Dock icon: now `make_regular()`).
  Runtime deps on the Mac: PySide6, numpy, opencv-python-headless and three
  `pyobjc-framework-*` packages (Cocoa, Quartz, Vision).
- `capture_mac.ensure_access()` checks Screen Recording, asks macOS for it, **prints** a
  message and returns `False`, and `main()` exits. A windowed `.app` has no console, so
  as it stands an installed Mac app would quit silently on first launch.
- `store.data_dir()` is already `~/Library/Application Support/MapleLens` on the Mac.
- First-run (default title `MapleStory`, "Pick game window…", "Looking for MapleStory…")
  is shared code and already works on the Mac.
- `--self-check` (`app.self_check`) is platform-neutral: templates, `maps.json`, minimap
  pictures, version metadata, OCR engine.
- `mark_running()` (one copy at a time) is Windows-only; on the Mac it returns `True`.
- Update check: `update.can_update` is `frozen and platform == "win32"`.
  `update.parse_latest` looks only for asset `MapleLens-Setup-X.Y.Z.exe`. `app.py`'s
  `UpdateCheck` downloads, checks the SHA-256 digest, then `install_update` starts Inno
  Setup silently and quits.
- Build: `scripts/build_installer.py` + `packaging/windows/maplelens.spec` (PyInstaller
  one-folder), Windows-only (version-info file, `.ico`, `qwindows.dll`, `winrt` license,
  Inno Setup).
- Release: `release.yml` builds on `windows-latest` in a read-only job; a separate
  `publish` job runs only `gh` to create the tag and Release. `prepare-release.yml` bumps
  the version.
- Guard: bans `osascript`, app activation calls, event posting, Accessibility etc. on the
  Mac. Plain `subprocess` is fine (Windows already uses it to start Setup).

## Decisions

### Unsigned by Apple (user, 2026-11-07: "live with the extra steps for now")

No Apple Developer account, so no Developer ID signature and no notarisation. What that
costs the player, once, on first install (today's macOS):

1. Opening MapleLens is **blocked** ("Apple could not verify…"). The player goes to
   System Settings → Privacy & Security, clicks **Open Anyway**, and confirms. (Right-click
   → Open no longer bypasses this on recent macOS.)
2. macOS asks for **Screen Recording** for MapleLens.

The README walks through both step by step, like the SmartScreen step on
Windows. Signing with an Apple Developer ID later is a separate change.

### Our own signing certificate, so Screen Recording survives updates *(my call, to prove first)*

macOS ties Screen Recording permission to the app's code signature. An ad-hoc signature
(what PyInstaller does by default) is different on every build, so every update would
ask for Screen Recording again. Instead every release is signed with **one self-signed
code-signing certificate** that never changes:

- Made once by the owner (Keychain Access → Certificate Assistant, or `openssl`), valid
  for many years, exported as a `.p12`, stored as two GitHub secrets (the `.p12` in
  base64 and its password). Never committed.
- Gatekeeper still blocks the first install (it isn't Apple's certificate); this only
  aims to keep the permission across updates.
- **Verified at Checkpoint A (2026-11-08):** with the same certificate on both builds the
  permission survives an update; with ad-hoc signing it is lost (the designated
  requirement is the cdhash). See "Checkpoint A results".
- Without a signing identity, a local build falls back to ad-hoc signing and says so,
  rather than failing. The CI sign job always requires the secrets, so a fork's test run
  uses throwaway ones.
- If the certificate is ever lost or replaced, players allow Screen Recording once more.
  Nothing else breaks.

### Package

- **PyInstaller `.app` bundle** (`BUNDLE` in the spec), one-folder as on Windows,
  `MapleLens.app`. **Apple silicon (arm64) only** *(my call: the Mac support work already
  scoped out Intel, `macos-latest` runners are arm64, and opencv has no universal2
  wheel)*. The README says so.
- `Info.plist`:
  - `CFBundleIdentifier`: fixed forever, like the Windows `AppId`, because macOS keys
    permissions on it. `io.github.or-keren.maplelens`, **confirmed by the owner
    2026-11-08**.
  - `CFBundleShortVersionString` / `CFBundleVersion`: the `pyproject.toml` version.
  - No `LSUIElement`: MapleLens is a normal app with a Dock icon (the bundle's
    `icon.icns`) and a menu bar, named by `CFBundleName` "MapleLens" (user, 2026-11-08).
    The Dock icon's menu is the box's menu; clicking the icon brings a hidden box back.
  - Minimum macOS: whatever PySide6 and the wheels need; the builder writes it down.
- Icon: `packaging/mac/icon.icns`, main's maple leaf, drawn by `scripts/make_icon.py`
  with the Windows `src/maplelens/data/icon.ico`. The bundle also ships that `.ico` as
  package data, which the self-check loads, as on Windows.
- Same bundled data as Windows (`maps.json`, every template, every minimap picture) at
  the same module-relative paths; same "fewer PNGs than `src/` fails the build" check;
  required file on the Mac: Qt's Cocoa platform plugin (`libqcocoa.dylib`).
- Licenses: the same set as Windows minus `winrt`, plus pyobjc's license, shipped inside
  the bundle (`Contents/Resources/licenses/` or wherever the builder finds clean).
- **Download: `MapleLens-X.Y.Z.dmg`**, made with the built-in `hdiutil` (no new tool): a
  window with `MapleLens.app` and an `Applications` shortcut to drag it onto. That drag
  is the Mac's install step. *(Dmg over zip: my call. It steers players into
  Applications, which the updater needs; a zip leaves the app in Downloads.)*
- **No uninstaller** (Mac convention): drag MapleLens to the Trash. Settings and EXP
  history in `~/Library/Application Support/MapleLens` stay, as `%APPDATA%\MapleLens`
  does on Windows. The README says where they are.

### First launch in the installed app

- The Screen Recording check no longer exits. When the permission is missing, MapleLens
  asks macOS once (`CGRequestScreenCaptureAccess`, which shows the system prompt with its
  own "Open System Settings" button), **keeps running**, and the box's status line says so
  in plain words: "Allow, then reopen: click •••" (main's ••• menu button replaced the
  right-click wording, 2026-11-08). The box's menu gets an item that opens System
  Settings at Privacy & Security → Screen Recording (a URL opened in System Settings, not
  driving its UI).
- Each tick re-checks; once allowed (and MapleLens reopened), the box moves on to
  "Looking for MapleStory…" and then the normal tools. macOS does **not** give a running app a
  grant made meanwhile (Checkpoint A, (c)), and offers no "Quit & Reopen". So the line
  tells the player to allow it and then reopen MapleLens, and the README says the same.
- From source (`uv run maplelens`) this behaves the same way, which replaces today's
  printed message and exit. `grab.py` keeps its printed message (it's a terminal tool).
- Never a silent quit, a black frame or a crash loop.
- **One copy at a time.** Opening the app from Finder twice already gives one copy
  (LaunchServices). The updater's relaunch must also never start the new version before
  the old one has exited (below). Nothing more is needed *(my call)*.

### One-click update on the Mac (user, 2026-11-07)

Everything the player sees is the Windows behaviour: the same notice line, the same
"Update to X.Y.Z…" menu item, daily check, "Check for updates now", the opt-out toggle,
the same quiet failures. What differs is what happens after the click:

1. `update.can_update` is true for the frozen app on `win32` **and** `darwin`. On the
   Mac `parse_latest` looks for asset `MapleLens-X.Y.Z.dmg`; on Windows still
   `MapleLens-Setup-X.Y.Z.exe`. A release missing the current platform's asset is "no
   update" for that platform.
2. Download to the updates folder under the data folder and **check the SHA-256 digest**,
   exactly as on Windows. No digest or a mismatch: never install it.
3. Hand over to a small detached helper (a `/bin/sh` script started with `subprocess`,
   *builder's call on the exact form*) and quit through Qt so `aboutToQuit` saves the
   session. The helper:
   - waits for MapleLens's process to exit;
   - mounts the dmg read-only and hidden (`hdiutil attach -nobrowse -readonly`), copies
     the new `MapleLens.app` next to the old one with `ditto` (keeps the signature,
     symlinks and permissions; Python's `zipfile`/`shutil` don't reliably), unmounts;
   - swaps old for new with renames, so a failure at any point leaves a working app at
     the original path, never a half-copied one;
   - starts the new version with `open -g` (found through `PATH`) on the app's path,
     which opens MapleLens only, in the background, never the game, and never activates
     another app;
   - reports a failed or blocked swap in a result file in the updates folder; the next
     launch reads it and logs it to `maplelens.log` (the helper doesn't write the log).
4. **Where the app lives.** The updater replaces the bundle at its own path (from
   `sys.executable`). Before downloading, MapleLens checks that it can: the bundle's
   folder is writable, and the app isn't running from the mounted dmg or a translocated
   read-only path (macOS runs a quarantined app that was never moved from read-only
   storage). If it can't, the menu item still shows, and clicking it shows a line like "Move to Applications to update" in the notice line
   instead of downloading (exact copy: whatever fits the 186 px tab width).
5. **No second Gatekeeper prompt** *(verified, Checkpoint A (b))*: a file Python downloads
   itself doesn't get macOS's quarantine flag, so the new version opens without "Open
   Anyway". If it turns out it is flagged, the helper doesn't remove the flag (that would
   be working around Gatekeeper); the README covers the extra click instead.
6. Settings and history survive, as on Windows: they live outside the app bundle.
7. **If macOS's App Management protection blocks the swap** (Checkpoint A, (d): not triggered on macOS 26, kept as a fallback), the
   fallback is to **ask the player to allow it** (user, 2026-11-07), never to work
   around it. The old version stays in place and running (the helper relaunches it), the
   box's notice line says "Allow updates: click •••" (fits 186 px), and the menu gets an
   item that opens System Settings at Privacy & Security → App Management (a URL, not
   driving its UI). Once the player has allowed it, "Update to X.Y.Z…" works as above.
   The README's Mac section has this step. If macOS shows its own prompt instead of
   blocking silently, the line and the README simply say to allow it. The builder finds
   out how macOS reports a block (an error from the rename, a prompt, or nothing) at
   Checkpoint A and how the helper tells MapleLens, e.g. a line in the log the new run
   reads.

### Release

- `release.yml` gains a Mac build next to the Windows build. Both must pass or nothing
  is published and no tag is made. `publish` attaches both files to the same Release:
  `MapleLens-Setup-X.Y.Z.exe` and `MapleLens-X.Y.Z.dmg`.
- **Mac build job** on `macos-latest`, **read-only, no secrets** (it runs downloaded
  packages, as the Windows build does): the four checks, freeze, bundle check,
  `MapleLens.app/Contents/MacOS/MapleLens --self-check`. Uploads the unsigned `.app` as
  an artifact, packed so symlinks and permissions survive (a `ditto`/`tar` archive, not
  the raw folder).
- **Mac sign job** on `macos-latest`, the **only** job that sees the certificate
  secrets, running only Apple's tools (`security`, `codesign`, `hdiutil`): import the
  `.p12` into a temporary keychain, sign the app, verify the signature, build the dmg,
  run `--self-check` again on the signed app, upload the dmg. *(My call: keeps the
  signing key away from third-party code, like `publish` keeps the write token away.)*
- **The sign job fails when the certificate secrets are missing**; the ad-hoc fallback
  is for local builds only *(my call)*. So a public dmg can't ship with a signature that
  loses Screen Recording on every update.
- **This PR merges only once the owner's inputs exist** *(my call)*: the confirmed
  `CFBundleIdentifier`, the certificate secrets, the icon, and a passed Checkpoint A.
  The next release after the merge is the first with a dmg; there's no switch to ship
  the jobs turned off.
- `prepare-release.yml` is unchanged. Actions stay pinned to commits.
- One script builds both systems: `scripts/build_installer.py` grows a Mac path
  (freeze → check → self-check → sign → dmg) and keeps the shared parts (version,
  bundle check, licenses, self-check timeout). Locally on a Mac:
  `uv run --group build python scripts/build_installer.py` →
  `dist/MapleLens-X.Y.Z.dmg`, ad-hoc signed unless a signing identity is given.

### Docs

- **README:** a "Download (Mac)" section next to the Windows one: Apple silicon only; open
  the dmg and drag to Applications; the Open Anyway steps; allowing Screen Recording; game
  windowed; how updates work; where settings live and how to remove MapleLens. "Run from
  source (macOS, developers)" stays.
- **AGENTS.md:** Layout and Commands list the new files and the Mac build command.
- **CONTRIBUTING.md:** the one-time certificate setup and the two secrets.

## Non-goals

- Apple Developer ID signing and notarisation (user: not now).
- Intel Macs, universal builds.
- Mac App Store, Homebrew cask.
- Sparkle or any update framework (the existing update check plus a shell helper covers
  it).
- An uninstaller app, "open at login".
- Changing anything a Windows player sees.

## Anti-goals

- Anything breaking the screen-only rule. The updater and permission screen only touch
  MapleLens's own bundle, its data folder, GitHub and System Settings' URL; never the
  game, its Wine prefix or its process; no AppleScript, no activating other apps.
- Working around Gatekeeper or TCC (removing quarantine flags, editing the TCC database).
  Players make those choices in System Settings themselves.
- A silent failure: a missing permission, a failed update or an unwritable install
  location each show a line in the box and a log entry.
- A broken app after a failed update.
- The signing key reaching a job that runs third-party code, a log, or the repo.

## Files (expected)

```
packaging/mac/icon.icns            app icon (main's maple leaf, scripts/make_icon.py)
packaging/windows/maplelens.spec   gains the Mac BUNDLE (or packaging/mac/maplelens.spec: builder's call)
scripts/build_installer.py         Mac path: freeze, check, self-check, sign, dmg
.github/workflows/release.yml      Mac build + sign jobs; publish attaches the dmg
src/maplelens/update.py            can_update on darwin; per-platform asset name
src/maplelens/app.py               Mac install_update (helper, relaunch); permission screen
src/maplelens/capture_mac.py       ensure_access no longer prints and exits
README.md, AGENTS.md, CONTRIBUTING.md
tests/                             update asset per platform; can_update; helper script text; bundle check on Mac
```

## Testing

- **Checkpoint A, before building the rest (spike on a real Mac):** two throwaway
  PyInstaller builds of a tiny app signed with the same self-signed certificate. Allow
  Screen Recording for build 1, replace it with build 2 the way the updater would
  (Python download → `hdiutil` → `ditto` → `open`), and confirm: (a) build 2 still has
  Screen Recording, (b) build 2 opens with no Gatekeeper prompt, (c) whether a fresh
  grant takes effect without a restart, (d) whether macOS's App Management protection
  (macOS 13+) lets the helper replace `/Applications/MapleLens.app`: silently, after a
  prompt, or not at all. Repeat (a) with ad-hoc signing to confirm the problem is real.
  The results go into this document and decide the signing and update sections.
  - The builder may make a **throwaway** self-signed certificate in the local keychain
    for this spike *(my call)*; the real one is the owner's (Boundaries). The builder
    stops for a person at the Mac only for the clicks (Open Anyway, Screen Recording).
- **Unit (pytest, no build):** `parse_latest` picks the dmg on `darwin` and the exe on
  `win32` from saved `releases/latest` replies (add one with both assets);
  `can_update` truth table; the "can this copy update itself" rule (writable folder, not
  on a dmg, not translocated) as a pure function of paths; the helper's command lines;
  the bundle check with the Mac required file.
- **Smoke check of the frozen app**, in CI and locally: `--self-check` on the built
  `.app` (unsigned in the build job, signed in the sign job) exits 0; the build fails on
  fewer templates or minimap pictures than `src/`.
- **Manual, clean Mac user account** (a new macOS user on the owner's Mac is enough):
  download the dmg from a test Release on a fork, drag to Applications, Open Anyway,
  allow Screen Recording from the box's prompt, see "Looking for MapleStory…", game
  found, EXP meter and path arrow read the same as from source. Then publish a higher
  version on the fork and update from the menu: no Gatekeeper prompt, no Screen
  Recording prompt (if Checkpoint A passed), settings and history kept, new version
  running. Try updating from the mounted dmg: the "Move to Applications" line shows.
- **Windows unchanged:** the existing Windows build, self-check and update tests pass.

## Boundaries

- **Always:** the four checks before every commit; a branch and a PR; fixtures and
  `docs/` out of the build.
- **Ask first (the owner):** `CFBundleIdentifier` before the first Mac release (it can't
  change without losing every player's permission); creating the certificate and the
  secrets; the icon; anything in `ci.yml`; any new runtime dependency.
- **Never:** commit the certificate, its password, a built app or a dmg; print the
  secrets; remove quarantine flags or touch TCC; give the signing key to the build job;
  push tags or Releases by hand; change `version` in `pyproject.toml`.

## Success criteria

1. On an Apple silicon Mac with no Python or developer tools, a player downloads
   `MapleLens-X.Y.Z.dmg` from the Release, drags MapleLens to Applications, opens it via
   Open Anyway, allows Screen Recording once, and MapleLens finds the game by itself. No
   Terminal at any point. MapleLens shows in the Dock with the maple leaf.
2. EXP meter and path arrow readings match `uv run maplelens` on the same screen.
3. "Update to X.Y.Z…" on the Mac downloads, verifies, replaces and restarts MapleLens;
   settings and history kept; no Gatekeeper prompt; no Screen Recording prompt if
   Checkpoint A passed.
4. A failed download, digest mismatch or unwritable location leaves the old version
   running with a line in the box.
5. Merging a release PR publishes one Release with both the exe and the dmg; if either
   build or the signing fails, nothing is published and no tag is made.
6. Windows players see no change; all checks pass on Windows and macOS CI.

## Checkpoint A results (2026-11-08)

Run on a Mac (macOS 26, Apple silicon): throwaway PyInstaller app installed from a
Safari-downloaded dmg, updating itself with a urllib download and the same
`hdiutil`/`ditto`/`mv` helper.

- (a) **Screen Recording across an update:** kept when both builds share the self-signed
  certificate; lost with ad-hoc signing (macOS asked again). System Settings then shows
  one enabled-looking row that doesn't cover the new build; the player must add it with "+".
- (b) **Quarantine:** the urllib-downloaded dmg and the swapped-in app have no
  `com.apple.quarantine` (only `com.apple.provenance`); no Gatekeeper prompt.
- (c) **Fresh grant:** does not reach the running app (`CGPreflightScreenCaptureAccess`
  stayed false until reopened); no "Quit & Reopen" offered.
- (d) **App Management:** renaming `/Applications/<app>.app` worked with no prompt or
  block on macOS 26. The blocked fallback stays as designed; a blocked `mv` prints
  "Operation not permitted" (checked with `chflags uchg`).
- Both settings URLs open the right pane: `Privacy_ScreenCapture` (Screen & System Audio
  Recording) and `Privacy_AppBundles` (App Management).
- Signing on a developer Mac needs the certificate trusted for code signing and its
  keychain on the search list; otherwise codesign says "no identity found".

## Open questions

- The owner: `CFBundleIdentifier`, the certificate, the icon.
