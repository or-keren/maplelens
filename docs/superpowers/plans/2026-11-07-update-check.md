# Update Check Implementation Plan

Spec: `docs/superpowers/specs/2026-11-06-update-check-design.md`. Branch: `update-check-spec`
(based on `feat/windows-installer`). Ships **inside or-keren/maplelens#10** (Daniel,
2026-11-07), so v0.1.0 already has the update check. `feat/windows-installer` is
fast-forwarded only once everything here passes, so the open PR never shows half-built
work. One commit per task.

## Overview

The installed Windows app checks GitHub's latest release at launch and every 24 h. A
newer `vX.Y.Z` shows a dismissable line in the box and an "Update to X.Y.Z…" menu item.
One click downloads the setup exe and checks its SHA-256 against GitHub's `digest`. Then
MapleLens saves, quits and hands over to Setup, which upgrades with no prompts and starts
the new version.

## Architecture decisions

- **Pure core in `src/maplelens/update.py`:** parse a `releases/latest` reply into
  `Release(version, url, digest)` or `None`, compare versions, check a file's digest.
  Tested with saved JSON replies, with no network.
- **No QThread.** Checks and downloads run on a plain `threading.Thread` that leaves its
  result in a slot. The existing 500 ms tick picks it up and touches Qt. Qt is never
  called off the Qt thread, and no new signal plumbing is needed *(my call)*.
- **Standard library only:** `urllib.request`, `json`, `hashlib`. No new dependency.
- **The asset digest is real.** Checked 2026-11-07: `gh api repos/astral-sh/uv/releases/latest`
  returns `"digest": "sha256:…"` on each asset. A reply with no digest is treated as "can't
  verify", so the file is never run.
- **The handoff is the risky part, so it comes first** (U2). It is built and tested with two
  locally built setups before any network code exists.
- **Fork testing uses a release created by hand.** `gh release create` on
  `dbeilin/maplelens` with a locally built N+1 setup. GitHub computes the digest itself.
  This avoids merging into the fork's `main` again. The fork's test releases are deleted
  afterwards.
- **Tampering is tested by a test, not a fake server.** The spec's manual "tampered
  download" run becomes a test: the update action gets a downloader that returns the
  wrong bytes. The spec's Testing section is updated to match (U6).

## Dependency graph

```
U1 update.py (pure)          U2 handoff: app quits → Setup upgrades silently → relaunch
   │                             │
   └──────────┬──────────────────┘
              U3 check at launch/daily → notice line + menu item
              │
              U4 one click: download → digest → handoff
              │
              U5 opt-out toggle + "Check for updates now" + messages
              │
              U6 docs + spec/PR wording ── U7 fork end-to-end, then push to PR #10
```

U1 and U2 are independent. Daniel works alone, so they run in order, U2 right after U1.

## Phase 1: the risky parts

### Task U1: `update.py`, the pure core (done)

**Description:**
- `parse_latest(reply: dict) -> Release | None`: tag `vX.Y.Z` (three integers) plus the
  asset named exactly `MapleLens-Setup-X.Y.Z.exe`, its `browser_download_url` and its
  `digest`.
- `is_newer(release, running: str) -> bool`.
- `digest_ok(path, digest) -> bool`: `sha256:<hex>`, streamed. `None` or another algorithm
  means False.
- `REPO`, overridable by `MAPLELENS_UPDATE_REPO`.
- `should_check(frozen, platform, settings) -> bool`: the gate (Windows and frozen and
  `update_check`).

**Acceptance criteria:**
- [x] Fixtures in `tests/fixtures/github/` give the right result: newer, same, no asset,
      wrong asset name, `v1.2` / `1.2.3` / `v1.2.3-beta` tags, missing digest.
- [x] `0.9.0 < 0.10.0`, equal is not newer, junk is not newer, and nothing raises on junk.
- [x] `digest_ok`: match True; one changed byte, a missing digest, or `md5:…` False.

**Verification:** `uv run pytest tests/test_update.py`, then the four checks.

**Dependencies:** none. **Files:** `src/maplelens/update.py`, `tests/test_update.py`,
`tests/fixtures/github/*.json`. **Scope:** S.

### Task U2: the handoff, app quits and Setup upgrades on its own

**Description:**
- `app.install_update(setup_path)` starts the setup detached, with Inno's update flags
  (`/SILENT /SP- /SUPPRESSMSGBOXES /NOCANCEL` plus a marker the `.iss` can see, e.g.
  `/UPDATE`), then quits through `QApplication.quit` so `aboutToQuit` saves the session.
- In `maplelens.iss`:
  - When run with the update marker, Setup waits for the `MapleLensRunning` mutex to go
    (up to ~10 s) **before** `CloseMapleLens` would ask or `taskkill`.
  - A `[Run]` entry starts MapleLens after a silent update run, since `skipifsilent`
    blocks today's.
  - A hand-run setup keeps today's pages and prompt.
- Also check the shared-folder case: Setup is started from `%APPDATA%\MapleLens\…`,
  which may hold non-ASCII characters.

**Acceptance criteria:**
- [x] With N installed and running, running the update path with a locally built N+1
      setup ends with MapleLens N+1 running. No prompt is shown, the uninstall entry
      reads N+1, and `settings.json` and `maplelens.db` are unchanged apart from the
      saved session.
- [x] A hand-run N+1 setup over a running N still asks "MapleLens is running. Close it…?"
      as today. *(2026-11-07, Daniel: the 0.1.0 setup double-clicked over a running
      0.1.1 asked; OK closed MapleLens and the wizard installed.)*
- [x] Starting Setup from a folder with non-ASCII characters works.
- [x] A unit test checks the command line `install_update` builds, and that it quits
      through `QApplication.quit`, not `sys.exit`.

**Run notes (2026-11-07, Daniel's PC):**
- Built 0.1.1 from `24faadb`, with the version bumped only for the build. Installed the
  earlier 0.1.0 setup silently.
- The running N was a stand-in, not the installed exe, because N has no update menu item
  until U4. The stand-in ran from source, held `MapleLensRunning`, called the real
  `install_update` on `…\scratchpad\עדכון\MapleLens-Setup-0.1.1.exe`, and took 3 s in
  `aboutToQuit` (a slow save). It added only `/LOG=` to the command line.
- Timeline:
  - 00:24:36.5 Setup starts.
  - 00:24:38.2 Setup's log opens; it waits in `InitializeSetup`.
  - 00:24:40.9 the stand-in's save finishes, and the process exits about 0.1 s later.
  - 00:24:41.25 Setup goes on and installs.
  - 00:24:49.6 install done; the `[Run]` entry starts the new `MapleLens.exe`.
- Results:
  - The log shows no message boxes, and Restart Manager found nothing in use.
  - The uninstall entry read 0.1.1, and MapleLens.exe 0.1.1 was running.
  - `settings.json` and `maplelens.db` were byte-identical before and after.
  - Cleaned up afterwards: uninstalled, data folder intact.
- Still to do: the hand-run prompt (criterion 2), the Sandbox run, and criterion 1 with
  the installed exe as N, which needs U4's menu item. It is re-checked in U7.
- 2026-11-07, U7: criterion 1 passed with the installed 0.1.0 as N (U7 run notes). The
  hand-run prompt and the Sandbox run are still not done.
- 2026-11-07, afterwards: the hand-run prompt passed (criterion 2 above). The Sandbox run
  was dropped by Daniel's call: the PC runs cover the same path.

**Verification:** build N and N+1 locally (version set temporarily, not committed), then
try both paths on Daniel's PC and once in Windows Sandbox. `uv run pytest`, then the four
checks.

**Dependencies:** none (U1 not needed). **Files:** `src/maplelens/app.py`,
`packaging/windows/maplelens.iss`, `tests/test_app.py`. **Scope:** M. **Risk:** highest.

### Checkpoint A: the handoff is real
- [x] U1–U2 done; four checks pass.
- [x] Silent upgrade and relaunch seen on Daniel's PC and in Sandbox. The hand-run setup
      is unchanged. *(PC only; Sandbox dropped by Daniel's call.)*
- [x] Decide with Daniel: continue as is, or fall back to showing the normal wizard (the
      spec's open question) if the silent path fought too hard. *(Silent: no prompts, and
      the game kept the keyboard; see U7's focus run.)*

## Phase 2: the feature

### Task U3: check at launch and daily; notice line and menu item (done)

**Description:**
- **Box:** `Box.set_notice(text, on_dismiss)` shows a line under the pages, separate from
  `set_status`, so the tabs stay. It has a small × that calls `on_dismiss`. `None` hides
  it.
- **Settings:** `store.DEFAULTS` gets `update_check: True` and `update_dismissed: None`.
- **App:**
  - When `should_check`, run a check thread ~5 s after start and then every 24 h. The
    tick collects the result.
  - A newer release shows "MapleLens X.Y.Z is out, right-click to update", unless
    `update_dismissed == X.Y.Z`, and adds or relabels the menu item "Update to X.Y.Z…".
  - Failures go to `report_once` only.

**Acceptance criteria:**
- [x] Offscreen Qt: the notice shows with the tabs still visible, × hides it and calls
      back, and the line fits 186 px at the longest version text (`10.10.10`). Shorten
      the copy if it doesn't fit.
- [x] With a fake fetch returning a newer release, the next tick shows the line and the
      menu item. Dismissed for that version: no line, but the menu item stays. A newer
      version after that shows the line again.
- [x] A fake fetch that raises or hangs: no line, one log entry, ticks keep their timing.
- [x] From source, or `should_check` False: the fetch function is never called.

**Build notes (2026-11-07):**
- The spec's copy, "MapleLens X.Y.Z is out, right-click to update", measures 275 px in
  the box font, too wide. The line now reads **"Update to X.Y.Z: right-click"** (9 pt,
  accent colour), which matches the menu item. The row with its × measures 171 px at
  `10.10.10` and 153 px at `0.2.0`. U6 brings the spec's wording in line.
- "Update to X.Y.Z…" goes at the top of the menu. Clicking it does nothing until U4.
- `report_once` now formats the exception it is given, so an error raised on the check's
  thread is logged with its own traceback.
- The real `fetch_latest` was tried once against GitHub: `astral-sh/uv` replies and parses
  to "no update" (its tag has no `v`). `or-keren/maplelens` has no release yet, so it
  gives 404, which is logged as a failed check. The manual run with a newer
  `MapleLens-Setup` release moves to U7, since no repo has one yet.

**Verification:** `uv run pytest tests/test_overlay.py tests/test_app.py tests/test_update.py`,
then the four checks. Manual: from source with the gate forced on and
`MAPLELENS_UPDATE_REPO` pointing at a repo with a newer release, the line appears.

**Dependencies:** U1. **Files:** `src/maplelens/overlay.py`, `src/maplelens/app.py`,
`src/maplelens/store.py`, `tests/test_overlay.py`, `tests/test_app.py`. **Scope:** M.

### Task U4: one click, from download to digest to handoff (done)

**Description:** "Update to X.Y.Z…" starts a download thread. It saves to
`data_dir()/updates/MapleLens-Setup-X.Y.Z.exe`, writing a `.part` file and renaming it at
the end, and the line says "Downloading X.Y.Z…". If `digest_ok` passes, `install_update`
(U2) runs. Otherwise the line says "Update failed, right-click to retry", the reason is
logged, and the file is deleted. A second click while a download runs does nothing. Old
setups in `updates/` are cleared at startup.

**Acceptance criteria:**
- [x] A fake downloader with the right bytes calls `install_update` with the file.
- [x] Wrong bytes, a missing digest, or a raising downloader: `install_update` is never
      called, the failure line shows, and the log has the reason.
- [x] Clicking twice starts one download.

**Build notes (2026-11-07):**
- The failure line is **"Update failed: right-click"**, since the spec's "Update failed,
  right-click to retry" fit with 1 px to spare (185 of 186). It now measures 144 px, and
  "Downloading 10.10.10…" measures 139 px. U6 brings the spec in line.
- The `.part` is renamed to the setup only after its digest matches. With no digest,
  nothing is downloaded. A setup that won't start (`install_update` raises) also shows
  the failure line, and its file is deleted.
- The daily check leaves the "Downloading…" line alone while a download runs.
- `clear_updates` runs when the check is created and skips files it can't delete. The
  last update's Setup may still be running when the new version starts; the next start
  clears it.
- The real `download_file` was tried once on `astral-sh/uv`'s smallest release asset.
  It followed GitHub's redirect, and `digest_ok` passed with the real `sha256:` digest.

**Verification:** `uv run pytest tests/test_app.py`, then the four checks.

**Dependencies:** U2, U3. **Files:** `src/maplelens/app.py`, `tests/test_app.py`.
**Scope:** S–M.

### Task U5: opt-out toggle, "Check for updates now", and the replies (done)

**Description:**
- `Box.add_toggle(label, checked, on_change)`: a checkable menu item.
- "Check for updates automatically" switches `update_check` and saves it.
- "Check for updates now" runs one check whatever the toggle says. Its reply shows in the
  line: the update, "MapleLens is up to date" or "Couldn't check for updates". The reply
  hides itself after ~10 s, or when × is clicked.
- Both items appear only when the app is frozen on Windows.

**Acceptance criteria:**
- [x] Toggle off: no automatic fetch after a restart (settings round-trip), and "Check
      now" still fetches.
- [x] "Check now" shows each of the three replies (offscreen Qt, fake fetch).
- [x] From source: neither item is in the menu.

**Verification:** `uv run pytest tests/test_overlay.py tests/test_app.py`, then the four
checks.

**Build notes (2026-11-07):**
- U1's `should_check(frozen, platform, settings)` became `can_update(frozen, platform)`.
  The installed Windows app always gets the check and both menu items. The toggle is
  read on each tick, so unticking it stops automatic requests at once, and ticking it
  again resumes them.
- Menu order: "Update to X.Y.Z…" (once known), "Pick game window…", "Check for updates
  now", "Check for updates automatically", "Quit MapleLens". `add_menu_item` takes
  `at=` (as `list.insert`) instead of U3's `first=`.
- *(my call)* "Up to date" and "Couldn't check" hide after 10 s. An update found by
  "Check now" shows even if that version was dismissed, and it stays until × or the
  update, like the automatic line. A reply never covers "Downloading…".
- Qt holds the menu items' links to the `UpdateCheck` weakly, so the caller must keep it.
  `main` does, through the tick.

**Dependencies:** U3. **Files:** `src/maplelens/overlay.py`, `src/maplelens/app.py`,
`tests/test_overlay.py`, `tests/test_app.py`. **Scope:** S.

### Checkpoint B: the feature works from source
- [x] U3–U5 done; four checks pass; fork CI green on Windows and macOS.
- [x] macOS CI shows no request and no new menu items there (gate tests).
- *(2026-11-07: green on the fork's draft PR dbeilin/maplelens#5, run 42352630963 at
  `e9f72c2`: Windows 456 passed, 5 skipped; macOS 454 passed, 16 skipped, all of them
  Windows-only tests. The gate tests aren't skipped on either.)*

## Phase 3: ship it in PR #10

### Task U6: docs, spec and plan wording (done)

**Description:**
- README Download: one paragraph. MapleLens checks GitHub for new versions, what it sends
  (an HTTPS request with `MapleLens/<version>` as User-Agent), how to turn it off, and
  that updating is one click.
- AGENTS.md Layout gets `update.py` and `tests/fixtures/github/`.
- CONTRIBUTING gets "testing an update" with `MAPLELENS_UPDATE_REPO` and the fork.
- Update-check spec: the notice copy becomes "Update to X.Y.Z: right-click" (U3 notes),
  and the failure line "Update failed: right-click" (U4 notes).
- Update-check spec: "v0.1.0 ships without this" becomes "ships in v0.1.0 with #10",
  the open question "which version ships it" is closed, and Testing step 5 says the
  tampered download is a test (Architecture decisions).
- Installer spec: the module line says `update-check` ships in the same PR.

**Acceptance criteria:**
- [x] `tests/test_docs.py` passes (the Layout paths exist).
- [x] A read-through: a player learns from the README that the app calls GitHub and how
      to stop it.

**Verification:** `uv run pytest tests/test_docs.py`, then the four checks.

**Build notes (2026-11-07):**
- The README's Updating paragraph now leads with the one-click update. A second
  paragraph, "The update check talks to GitHub", says when it asks, what it sends, how to
  turn it off, and that source runs never check.
- Also updated: spec success criterion 1, which quoted the old notice copy, and Testing
  step 2, which now publishes N+1 by hand like U7.

**Dependencies:** U5. **Files:** `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, both
specs. **Scope:** S.

### Task U7: end to end on the fork, then into PR #10

**Description:**
1. Build N from this branch and install it, with `MAPLELENS_UPDATE_REPO=dbeilin/maplelens`
   set for the user.
2. Build N+1 locally and publish it on the fork by hand: `gh release create vN+1 …` on
   `dbeilin/maplelens`, never on `or-keren`.
3. Walk spec success criteria 1–7.
4. Delete the fork's test release and tag, and unset the variable.
5. Fast-forward `feat/windows-installer` to this branch and push to the fork, which
   updates PR #10.
6. Update PR #10's description:
   - an "Update check" section with the evidence
   - the new owner question "is calling home OK?", which now blocks the merge
   - the spec link

**Acceptance criteria:**
- [x] Criteria 1–7 seen by hand, with notes in this plan.
- [x] The fork has no test tags or releases left.
- [x] PR #10 shows the new commits, its CI is green, and its description covers the
      update check. *(Commits and description yes; upstream CI waits for the owner to
      approve workflows for a first-time contributor. Fork CI is green.)*

**Verification:** fork run notes; `gh release list --repo dbeilin/maplelens` is empty; PR
checks.

**Dependencies:** U6. **Files:** this plan (notes); PR description. **Scope:** S.

**Run notes (2026-11-07, Daniel's PC):**
- Built 0.1.0 and 0.1.1 from `e674bc6`. 0.1.1 had its version bumped only for the build;
  `pyproject.toml` and `uv.lock` were restored. Published v0.1.1 on `dbeilin/maplelens`
  by hand, tagged at `update-check-spec`. GitHub's asset digest matched the local build's
  SHA-256 (`8c2aee9f…`).
- Installed 0.1.0, with `MAPLELENS_UPDATE_REPO=dbeilin/maplelens` set for the user.
- **Testing gotcha:** Claude Code's sandboxed shell writes to its own copy of
  `%APPDATA%` and of the uninstall registry key. An install run from it put its files on
  disk but no Settings → Apps entry, and the app's settings and log looked unchanged from
  there. Install and read the data folder from a real terminal.
- Criteria:
  1. Pass. Started like a Start-menu launch, the box showed "Update to 0.1.1:
     right-click" with its × on one line under "Looking for MapleStory…". The game wasn't
     open, so the tabs were hidden by that status line, not by the notice.
  2. Pass. 0.1.0 was reinstalled from a real terminal first, so it had its uninstall
     entry. "Check for updates now", then "Update to 0.1.1…": the download ran, Setup
     ran with no questions, and MapleLens came back by itself. Afterwards:
     - one uninstall entry, at 0.1.1; `maplelens-0.1.1.dist-info` installed
     - `settings.json` byte-identical; `maplelens.db` the same time and size (it was
       locked by the running app, so no hash)
     - the setup in `updates\` was deleted by the new version at startup
     - the log was empty: no errors
     - Not observed: the game keeping the keyboard, since the game wasn't open.
  3. By tests only (U4): wrong bytes, no digest, a non-SHA-256 digest, a failed
     download, and a Setup that won't start.
  4. Pass. Offline (the HTTPS proxy pointed at a dead local port): one `URLError` entry
     and no download. With no release on the fork: one `HTTPError 404`.
  5. Pass. Unticking saved `update_check: false` at once, and it survived a restart.
     Offline with the toggle off, the log stayed empty for over 20 s, so no request was
     made. "Check for updates now" logged one `URLError` and showed "Couldn't check for
     updates", which hid itself.
  6. By tests and the gate (`can_update`). `--self-check` returns before any window or
     check is made.
  7. Pass. × hid the line and saved `update_dismissed: "0.1.1"`; after a restart there
     was no line, and "Update to 0.1.1…" was still in the menu. The N+2 part is by test
     only.
- **Found:** MapleLens lets a second copy start while one runs. Each copy keeps its own
  settings and rewrites the whole file when it saves, so one copy silently undid
  Daniel's untick in the other. This is outside the update check, so it's a follow-up.
  *(2026-11-07: fixed in this PR after all, by Daniel's call. A second copy now exits
  before Qt starts when `MapleLensRunning` already exists. Windows only.)*
- Cleaned up: the fork has no releases or tags, and `MAPLELENS_UPDATE_REPO` is removed.
  Installed 0.1.1 was left on Daniel's PC.

**Focus run (2026-11-07, Daniel's PC, game open):**
- v0.1.1 published on the fork again by hand, the same setup as above (digest
  `sha256:8c2aee9f…`). 0.1.0 reinstalled by hand over a running 0.1.1, which was the
  hand-run prompt check.
- With the game in focus, "Update to 0.1.1…" from the menu, then straight back into the
  game. **The game kept the keyboard throughout** (Daniel). Setup installed 0.1.1 at
  15:05:57, and MapleLens came back at 15:06:00.
- The automatic check showed only the menu item, with no line: `update_dismissed` was
  still `"0.1.1"` from criterion 7's run, and uninstalling keeps `%APPDATA%\MapleLens`.
  That is the spec's behaviour.
- An earlier try at 14:30 also updated 0.1.0 → 0.1.1 (about 12 s, no prompts), but
  without watching focus.
- Cleaned up: the fork's v0.1.1 release and tag were deleted again.

### Checkpoint C: done
- [x] All eight spec success criteria met; evidence in PR #10. *(3 and 6 by tests;
      the N+2 part of 7 by test.)*
- [x] Daniel has seen the PR description before it's posted. *(The update-check section
      was posted from another chat; this chat's focus-run edit was shown to Daniel.)*

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Setup starts before MapleLens has exited, and its close path `taskkill`s it (the session in progress is lost) | High | U2: in update mode, Setup waits for the mutex before its close path; tested with a running N |
| Silent Setup doesn't relaunch MapleLens, so the player is left with nothing running | High | U2 `[Run]` entry for update runs; seen in Sandbox |
| The notice line doesn't fit 186 px | Low | U3 test at the longest version; shorten the copy |
| A hanging request blocks the tick | Med | Thread plus timeout; the tick only reads a result slot; a test with a hanging fake |
| Antivirus flags an exe launching a freshly downloaded exe | Med | Same unsigned-exe caveat as the installer; README note; signing is a later spec |
| The PR grows while the owner reviews it | Med | Build on `update-check-spec`; fast-forward #10 only at U7, with a description update |
| Testing against `or-keren` by mistake | High (public releases) | `MAPLELENS_UPDATE_REPO` must point at the fork; releases made by hand on the fork only |

## Open questions

- Owner: calling home once a day, on by default (spec). This now has to be settled
  before #10 merges.
- Owner: pinning `or-keren/maplelens` (spec).
- Checkpoint A: silent install or wizard, decided from what U2 shows.
