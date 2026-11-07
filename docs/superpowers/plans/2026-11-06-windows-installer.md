# Windows Installer Implementation Plan

**Goal:** A Windows player downloads `MapleLens-Setup-X.Y.Z.exe` from GitHub Releases,
installs it with no Python and no admin prompt, and MapleLens finds the game on its own.
Releases are made by a "prepare release" workflow that opens a PR; merging that PR
publishes the release.

**Spec:** `docs/superpowers/specs/2026-11-06-windows-installer-design.md` (modules
`first-run` and `installer`). Read it first; this plan points at its sections instead of
repeating them. Tasks are tracked as the checkboxes in this file.

**Tech stack:** Python 3.12, uv 0.12, PySide6, OpenCV, winrt (all present). New:
PyInstaller (dev-only `build` group), Inno Setup 6 (build tool on the runner and on
Daniel's PC, not a Python dependency).

## Architecture decisions

- **Freeze risk first.** PyInstaller with PySide6 and the `winrt-*` namespace packages is
  the part most likely to fight back (hidden imports, missing DLLs, size). It goes before
  the first-run UI work, which is ordinary code. Daniel's own `settings.json` already has
  a `window_title`, so the frozen app can be tested before first-run exists.
- **One build entry point**, `scripts/build_installer.py`, used both locally and in CI. It
  reads the version from `pyproject.toml`, runs PyInstaller, runs the exe's self-check,
  then runs Inno Setup. CI never has build logic of its own beyond calling it.
- **Self-check flag on the exe** (`MapleLens.exe --self-check`): loads every template,
  `maps.json`, every minimap picture, the OCR engine and the version, then exits 0 or 1. The exit code is the
  signal, because a windowed exe has no console. This is the only reliable way to prove
  the *frozen* app has its data. Checking the files in `dist/` would not catch a missing
  hidden import.
- **Default-title match is exact**, through an `exact` option on the existing
  `pick_window` / `find_window`, not a second matching function.
- **Release detection = version has no tag yet** (spec, Release flow). `release.yml`
  never needs to know how the PR was merged.
- **Version bump with `uv version --bump`**, which updates `pyproject.toml` and `uv.lock`
  together *(confirm the flag in the uv docs for the runner's uv version)*.
- **One PR to `or-keren/maplelens`** (Daniel, 2026-11-06), from branch
  `feat/windows-installer`. One commit per task (conventional-commit messages, as the
  repo uses), so the owner can review it commit by commit.

## Dependency graph

```
T0 fork + auth
 ├─ T1 templates load from any path
 │   └─ T2 frozen app (PyInstaller)
 │       └─ T3 --self-check + version
 │           └─ T7 exe metadata + licenses
 │               └─ T8 Inno Setup installer ◄── also needs T6 (Sandbox check)
 │                   └─ T9 release.yml
 │                       └─ T10 prepare-release.yml
 │                           └─ T11 docs
 └─ T4 exact default title ─ T5 keep running + status ─ T6 picker + log file
```

---

## Phase 0: Setup

### Task 0: Fork, auth and branch

**Description:** `origin` is `git@github.com:or-keren/maplelens.git` and fetching fails
("Permission denied (publickey)"). Daniel needs a fork to push branches, open PRs, and
test the release workflows without touching the owner's repo.

**Acceptance criteria:**
- [x] A fork `<daniel>/maplelens` exists; `origin` = the fork, `upstream` = `or-keren/maplelens`.
- [x] `git fetch upstream` works (SSH key added to GitHub, or HTTPS through `gh auth login`).
      *(HTTPS: `upstream` = `https://github.com/or-keren/maplelens.git`, Git Credential Manager.)*
- [x] Branch `feat/windows-installer` based on `upstream/main`, carrying the spec and this plan.

**Verification:** `git fetch upstream && git log --oneline -1 upstream/main`.

**Dependencies:** None. **Files:** none. **Scope:** XS.

---

## Phase 1: Freeze risk first

### Task 1: Templates load from any path

**Description:** `readers/glyphs.py` loads templates with `cv2.imread(str(path))` (lines 43
and 105). On Windows, OpenCV can't open a path with non-ASCII characters, and the installed
app lives under `C:\Users\<name>\AppData\Local\Programs\MapleLens`. Read the file bytes
and decode them instead (`np.fromfile` + `cv2.imdecode`), keeping the same flags and the
same `FileNotFoundError`.

**Acceptance criteria:**
- [x] A template copied into a folder named with non-ASCII characters (e.g. `tmp_path / "דניאל"`)
      loads through `glyphs.load` and the font loader, with `TEMPLATES` monkeypatched.
- [x] A missing template still raises `FileNotFoundError`.
- [x] All existing reader tests pass with the same values.

**Verification:**
- [x] Write the non-ASCII test first and see it fail on Windows (if it passes, OpenCV has
      fixed this: keep the test, drop the code change, note it in the spec).
- [x] `uv run pytest tests/test_glyphs.py tests/test_readers.py`, then the four repo checks.

**Dependencies:** T0. **Files:** `src/maplelens/readers/glyphs.py`, `tests/test_glyphs.py`.
**Scope:** S.

### Task 2: Frozen app runs (PyInstaller, one-folder, windowed)

**Description:** Add `pyinstaller` to a new `build` dependency group, write
`packaging/windows/maplelens.spec`, and the freeze half of `scripts/build_installer.py`.
Entry point: `src/maplelens/app.py`. Collect `maplelens`'s package data (templates,
`maps.json`) at their module-relative paths; collect the `winrt` namespace packages;
exclude unused Qt modules. Check the current PyInstaller docs and the PySide6 hook first
(source-driven).

**Acceptance criteria:**
- [x] `uv run python scripts/build_installer.py --freeze-only` produces
      `dist\MapleLens\MapleLens.exe`; `build/` is gitignored.
- [x] With the game running windowed and Daniel's existing `settings.json`, the exe shows
      the box, and the EXP meter and path arrow read the same as `uv run maplelens`.
      *(2026-11-06: no `settings.json` existed on Daniel's PC. A frozen probe of `read_all`
      on the live game matched the source run exactly: EXP, level, job, and map name via
      OCR. The frozen app ran 25 s against the game with no tracebacks. Daniel checked the
      box by eye: looks right.)*
- [x] No console window opens. *(exe subsystem is GUI.)*
- [x] `uv run python scripts/check_screen_only.py` passes with the new `uv.lock`.
- [x] Folder size recorded (target: installer ≤ 150 MB later). *(207 MB after trimming
      ~55 MB of unused OpenCV video and Qt Pdf/Quick/Qml/translations; 262 MB untrimmed.
      PyInstaller 6.22.3, hooks-contrib 2026.9.)*

**Verification:**
- [x] Build, launch, compare EXP/level/map readings side by side with the source run.
      *(Readings compared by the probe; Daniel checked the box by eye.)*
- [x] Four repo checks.

**Dependencies:** T1. **Files:** `pyproject.toml`, `uv.lock`,
`packaging/windows/maplelens.spec`, `scripts/build_installer.py`, `.gitignore`.
**Scope:** M. **Risk:** highest in the plan; see Risks.

### Task 3: `--self-check` and runtime version

**Description:** `maplelens --self-check` loads every template font and anchor, loads
`maps.json` through `tools/path_arrow/maps.load`, decodes every picture in
`data/minimaps/` through `maps.picture`, creates the OCR engine, and reads the app version
(`importlib.metadata`; the PyInstaller spec copies `maplelens`'s metadata). It exits 0 if
all succeed, else 1, before any window opens. `build_installer.py` runs the built exe with
`--self-check` and fails the build on non-zero. It also fails if the built app holds fewer
template or minimap PNGs than `src/` (`maps.picture` quietly returns `None` for a missing
file, so the self-check alone can't catch a dropped picture).

**Acceptance criteria:**
- [x] From source, `uv run maplelens --self-check` exits 0.
- [x] A unit test with `TEMPLATES` pointing at an empty folder gets 1.
- [x] Deleting one template, or one minimap picture, from `dist\MapleLens\…` makes the
      build script fail. *(Tried on the built app: a missing template or minimap fails the
      file count; a missing `maps.json`, OCR table or version metadata fails the exe. Run
      the exe through `subprocess`: Git Bash doesn't wait for a windowed exe and shows 0.)*

**Verification:** `uv run pytest tests/test_app.py`; build, delete a template by hand,
re-run the check, then rebuild.

**Dependencies:** T2. **Files:** `src/maplelens/app.py`, `scripts/build_installer.py`,
`packaging/windows/maplelens.spec`, `tests/test_app.py` (new). **Scope:** S.

### Checkpoint A: the frozen app is real
- [x] T1–T3 done; four repo checks pass; Windows and macOS CI green on the branch.
      *(2026-11-06: Windows CI green on the fork's draft PR, dbeilin/maplelens#1. The fork's
      macOS jobs never get a runner (account-side; upstream's start in seconds), so macOS
      CI is deferred to the upstream PR, by Daniel's call.)*
- [x] Frozen exe works with the game on Daniel's PC; size noted. *(207 MB folder.)*
- [x] Decide with Daniel: continue, or rethink (e.g. Nuitka) if T2 fought too hard.
      *(Continue with PyInstaller: winrt's own hook did the hard part.)*

---

## Phase 2: first-run

### Task 4: Exact default title, saved on first match

**Description:** `pick_window(titles, title, exact=False)` and `find_window(title,
exact=False)` on both platforms. In `app.py`, with no saved `window_title`, the tick
looks for `DEFAULT_TITLE = "MapleStory"` with `exact=True`, and saves the title once a
window matches. A saved title keeps today's exact-then-substring rule.

**Acceptance criteria:**
- [x] Unset title + windows `[…, "MapleStory"]` → found, and `settings["window_title"]` saved.
- [x] Unset title + only `"MapleStory Classic Thief Guide - Chrome"` → not found.
- [x] Saved `"Thief Guide"` → still found by substring (existing test unchanged).
      *(2026-11-06: `find_game` in `app.py`; checked on Daniel's PC with the game open:
      the Windows client's title is exactly `MapleStory`, and Discord's `#maple-story`
      and a Firefox tab were skipped. The `grab.py` exit went too, since with it the
      default title could never be reached; Task 5 adds the status line.)*

**Verification:** `uv run pytest tests/test_capture.py tests/test_capture_mac.py`; four checks.

**Dependencies:** T0. **Files:** `src/maplelens/capture.py`, `capture_win.py`,
`capture_mac.py`, `app.py`, `tests/test_capture.py`. **Scope:** M.

### Task 5: No exit; the box says what's going on

**Description:** Remove the `Run: uv run python scripts/grab.py …` exit. While no game
window is found, the box shows one plain line (spec copy: "Looking for MapleStory…
right-click to pick the game window") and the tools get the existing no-reading path.
Decide where the box sits when there's no game rect (e.g. its last saved spot or the
screen's top-left) and keep it simple.

**Acceptance criteria:**
- [x] With no `settings.json` and no game running, `uv run maplelens` stays open and shows
      the line; starting the game makes it disappear and the tools work.
- [x] Box status shown/hidden through one `Box` method, with an offscreen Qt test.
      *(2026-11-06: `Box.set_status`. Checked live with a temp `APPDATA` and the default
      title swapped for one that matches nothing: the box showed only the line, near the
      screen centre where Qt puts a new window. With the title switched back to
      `MapleStory`, the line went, the tabs came back, the box moved onto the game and
      the title was saved. Not checked: an actual cold start with the game closed. A
      minimized game hides the box as before; it doesn't show "Looking for".)*

**Verification:** `uv run pytest tests/test_overlay.py`; manual run with
`%APPDATA%\MapleLens\settings.json` renamed (rename it back afterwards).

**Dependencies:** T4. **Files:** `src/maplelens/app.py`, `src/maplelens/overlay.py`,
`tests/test_overlay.py`. **Scope:** S.

### Task 6: "Pick game window…" and the log file

**Description:** A right-click menu item lists `capture.list_windows()` and saves the
chosen title (the next tick uses it). Separately, `report_once` also appends to
`%APPDATA%\MapleLens\maplelens.log` (truncated at startup), and printing never crashes
when there's no console (`sys.stderr` is `None` in a windowed exe).

**Acceptance criteria:**
- [x] Picking a window saves its title and the overlay follows that window.
- [x] A raised error in a tool shows up once in `maplelens.log`.
- [x] With `sys.stderr = None` (monkeypatched), `report_once` writes the log and doesn't raise.
      *(2026-11-06: the picker lists `capture.window_titles()`, new on both platforms: the
      titles `find_window` matches. On the Mac, `list_windows()` gives "app — window"
      strings that could never match. MapleLens's own window is left out. Checked live:
      starting from a title that matched nothing, choosing "MapleStory" from the menu saved
      it and moved the box onto the game. The log is emptied at startup.)*

**Verification:** `uv run pytest`; manual pick on Daniel's PC; four checks.

**Dependencies:** T5. **Files:** `src/maplelens/app.py`, `tests/test_app.py`
(the picker list may need a small helper in `overlay.py`). **Scope:** S–M.

### Checkpoint B: first-run works
- [x] T4–T6 done; four checks; CI green on Windows and macOS (on the fork).
      *(2026-11-06: both jobs green at dcff3de, [run 42291074586](https://github.com/dbeilin/maplelens/actions/runs/42291074586).)*
- [x] Mac behaviour from source unchanged apart from first-run (Mac CI is the check; Daniel
      has no Mac, which the PR description will say).

---

## Phase 3: Installer

### Task 7: Exe metadata and licenses

**Description:** `build_installer.py` writes a PyInstaller version-info file from the
`pyproject.toml` version, so the exe's Properties → Details shows MapleLens and the
version. Add the icon (placeholder until the owner picks one). Copy license texts for
PySide6/Qt (LGPL-3.0), OpenCV, numpy and MapleLens itself into the app folder, plus
the meowdb credit.

**Acceptance criteria:**
- [x] Exe Properties show product name MapleLens and the version from `pyproject.toml`.
      *(0.1.0; placeholder "ML" icon embedded, owner to replace.)*
- [x] `dist\MapleLens\licenses\` holds the license files listed above.
      *(Plus winrt and Python. The PySide6 wheels carry no LGPL text, so the LGPL-3.0
      and GPL-3.0 texts are vendored in `packaging/windows/licenses/`.)*

**Verification:** build; check Properties and the folder.

**Dependencies:** T3. **Files:** `scripts/build_installer.py`,
`packaging/windows/maplelens.spec`, `packaging/windows/icon.ico`,
`packaging/windows/NOTICE.txt`. **Scope:** S.

### Task 8: Inno Setup installer

**Description:** `packaging/windows/maplelens.iss` per spec (Goals → installer, Upgrades):
fixed `AppId` (generate one GUID; the owner confirms it in PR review),
`PrivilegesRequired=lowest`, `{localappdata}\Programs\MapleLens`, Start-menu shortcut,
unticked desktop shortcut, launch-after-install, close a running MapleLens before
upgrading, uninstall leaves `%APPDATA%\MapleLens`. `build_installer.py` runs `iscc` with the
version and writes `dist\MapleLens-Setup-X.Y.Z.exe`.

**Acceptance criteria:**
- [x] `uv run python scripts/build_installer.py` produces the setup exe (≤ 150 MB, or a reason).
      *(60 MB, Inno Setup 6.7.3 from `winget install JRSoftware.InnoSetup --scope user`.
      Run with `--group build`.)*
- [x] In **Windows Sandbox**: install with no admin prompt, launch from Start menu, see the
      "Looking for MapleStory…" line, uninstall; program folder and shortcuts gone.
      *(Daniel, 2026-11-06. The first run found uninstall left MapleLens running; Setup and
      the uninstaller now close it after one OK, and the re-run passed.)*
- [x] On Daniel's PC: install 0.1.0, use it, build again with the version temporarily set to
      0.1.1 (not committed), install over it while MapleLens runs → asked to close it,
      settings and history kept, one entry in Settings → Apps.
      *(2026-11-06, scripted with `/VERYSILENT /SUPPRESSMSGBOXES` and the setup logs: the
      0.1.1 setup asked "MapleLens is running. Close it and continue?" and closed it;
      exe, bundled metadata and the one uninstall entry all read 0.1.1, with no 0.1.0 files
      left; `settings.json` and `maplelens.db` hashes unchanged; the installed 0.1.1 passed
      `--self-check`. Uninstalling while it ran asked, closed it, and removed the folder,
      Start-menu shortcut and registry entry, and kept `%APPDATA%\MapleLens`. Not
      covered: the dialogs as a player sees them, and use with the game running.)*

**Verification:** the three manual runs above, written into the PR description.

**Dependencies:** T7, and T6 for the Sandbox check. **Files:** `packaging/windows/maplelens.iss`,
`scripts/build_installer.py`. **Scope:** M.

### Checkpoint C: the installer works
- [x] Success criteria 1–4 of the spec met by hand.
      *(1: Windows Sandbox, T8. 2: T4–T6 live checks. 3: the frozen exe against the source
      run, T2; the installed copy is the same files but wasn't run against the game.
      4: the 0.1.0 → 0.1.1 upgrade, T8.)*
- [x] Sizes and Sandbox results written down for the PR description.

---

## Phase 4: Release automation

All workflow testing happens **on Daniel's fork** (Actions enabled, "Allow GitHub Actions
to create and approve pull requests" on). Nothing runs against the owner's repo until the
PR merges.

### Task 9: `release.yml`

**Description:** On push to `main`: read the version; if tag `vX.Y.Z` exists, stop
successfully. Otherwise, on `windows-latest`: install Inno Setup if the runner lacks it,
`uv sync --locked --group build`, the four checks, `build_installer.py`, then create the
tag and publish the Release with the setup exe and generated notes (`gh release create
… --generate-notes`). `permissions: contents: write`; a `concurrency` group so two pushes
can't race to the same tag.

**Acceptance criteria:**
- [x] On the fork: a push that doesn't change the version → run ends "already released",
      nothing created.
      *(2026-11-06, [run 42285879241](https://github.com/dbeilin/maplelens/actions/runs/42285879241):
      "v0.1.0 is already released, nothing to do"; the Windows job skipped.)*
- [x] A push with a new version → tag + published Release with the exe and notes.
      *(2026-11-06, [run 42285355184](https://github.com/dbeilin/maplelens/actions/runs/42285355184):
      published [v0.1.0](https://github.com/dbeilin/maplelens/releases/tag/v0.1.0) at
      66598e2 with `MapleLens-Setup-0.1.0.exe` (61 MB) and generated notes, in 2.5 min.
      `windows-latest` already had Inno Setup 6, and `--self-check` passed on it.)*
- [x] A forced failure (e.g. a deleted template on a test branch merged to the fork's main)
      → no tag, no Release.
      *(2026-11-06: version 0.1.1 with `exp_label_1366.png` deleted, pushed to the fork's
      main. [Run 42286113698](https://github.com/dbeilin/maplelens/actions/runs/42286113698)
      failed at `pytest` (the EXP reader tests); an earlier try,
      [42285989590](https://github.com/dbeilin/maplelens/actions/runs/42285989590), failed at
      `uv sync --locked` because `uv.lock` still said 0.1.0. Neither created a v0.1.1 tag
      or release.)*

*(2026-11-06: `tests/test_release_workflow.py` keeps the checks in step with `ci.yml` and
the publish step last. The fork's v0.1.0 tag and release are test output, removed with
Task 10's.)*

**Verification:** the three fork runs; links in the PR description.

**Dependencies:** T8. **Files:** `.github/workflows/release.yml`. **Scope:** S–M.

### Task 10: `prepare-release.yml`

**Description:** `workflow_dispatch` with input `bump` (`patch` / `minor` / `major`):
`uv version --bump <bump>`, refuse if the tag, branch `release/vX.Y.Z` or an open PR
already exists, run the four checks, commit `release: vX.Y.Z`, push the branch, `gh pr
create` with a body that says merging publishes the release. `permissions: contents:
write, pull-requests: write`.

**Acceptance criteria:**
- [x] On the fork, `minor` from 0.1.0 opens PR `release: v0.2.0` whose diff is only the
      version lines in `pyproject.toml` and `uv.lock`.
      *(2026-11-06. The first try, [run 42288201228](https://github.com/dbeilin/maplelens/actions/runs/42288201228),
      also changed `uv.lock`'s `revision = 3` to `5`: the runner's uv 0.13.7 re-locked
      with a newer lock format than Daniel's 0.12.1. The bump now uses `--frozen` and edits
      the lock's version line, checked by `uv sync --locked`.
      [Run 42288853699](https://github.com/dbeilin/maplelens/actions/runs/42288853699)
      then opened [PR 3](https://github.com/dbeilin/maplelens/pull/3) with exactly the two
      version lines.)*
- [x] Merging it makes `release.yml` publish `v0.2.0` with no other step (spec criterion 5).
      *([Run 42289092404](https://github.com/dbeilin/maplelens/actions/runs/42289092404)
      published [v0.2.0](https://github.com/dbeilin/maplelens/releases/tag/v0.2.0) from the
      merge commit, with `MapleLens-Setup-0.2.0.exe` and notes listing PR 3.)*
- [x] Running prepare again while that PR is open fails with a clear message.
      *([Run 42288501886](https://github.com/dbeilin/maplelens/actions/runs/42288501886),
      `patch` while PR 2 was open: "A release PR is already open, merge or close it
      first: …/pull/2", nothing pushed.)*

*(2026-11-06: written, with tests in `tests/test_release_workflow.py`. It refuses while
**any** `release/v*` PR is open, not only one for the same version, so a `patch` run
can't open a second release PR beside a pending `minor`. The fork has "Allow GitHub
Actions to create and approve pull requests" on for these runs.)*

**Verification:** the fork runs; then delete the fork's test tags/releases so the fork
mirrors upstream again.

**Dependencies:** T9. **Files:** `.github/workflows/prepare-release.yml`. **Scope:** S.

### Task 11: Docs

**Description:** README: a "Download" section for players (Releases link, SmartScreen →
More info → Run anyway, windowed/borderless) above the from-source steps. AGENTS.md: Layout
gets `packaging/windows/`, `scripts/build_installer.py`, the two workflows; Commands gets
the build command. CONTRIBUTING.md: how to cut a release (run Prepare release, merge the
PR). Harness design: one line noting packaging is done.

**Acceptance criteria:**
- [x] A player can follow the README from download to first launch without reading
      anything else.
      *(Read-through, 2026-11-06. "From source" no longer needs `grab.py`, since first-run
      finds the game.)*
- [x] AGENTS.md Layout matches the files that exist.
      *(`tests/test_docs.py` checks every path a Layout bullet names, and that the build and
      release files are listed. AGENTS.md also says never to bump `version` in a feature PR.)*

**Verification:** read-through; `uv run ruff check`, guard (README isn't scanned, but
`scripts/` is).

**Dependencies:** T10. **Files:** `README.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`docs/superpowers/specs/2026-11-01-maplelens-harness-design.md`. **Scope:** S.

### Checkpoint D: done
- [x] All six spec success criteria met; evidence (fork run links, Sandbox notes, sizes) in
      the PR descriptions.
- [x] One PR open to `or-keren/maplelens`, linking the spec, with the evidence above, the
      `AppId` / name / icon questions, the one setting the owner must enable, the
      required-checks caveat, and what merging releases (see Open questions).

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PyInstaller misses `winrt` submodules or Qt plugins: the exe starts but capture/OCR/overlay silently fail | High | T3 self-check creates the OCR engine; T2's manual run with the game; collect `winrt` explicitly |
| Antivirus flags the unsigned PyInstaller exe | Med | One-folder mode (fewer flags than one-file); README note; signing is a later spec |
| Installer too big (Qt + OpenCV) | Med | Qt excludes in T2; record size; 150 MB budget |
| Non-ASCII user folder breaks template loading | High (readers dead for those players) | T1, with a test |
| Workflow-opened PRs don't trigger `ci.yml`; required checks block merge | Med | Checks inside both workflows (spec); owner can switch to an App token later |
| Inno Setup missing or a different version on `windows-latest` | Low | `release.yml` installs it if `iscc` isn't found; pin the major version |
| Two pushes to `main` racing to tag the same version | Low | `concurrency` group in `release.yml`; tag-exists check |
| Testing release workflows on the owner's repo by mistake | High (public releases) | All workflow runs on the fork until PR 3 merges (Phase 4 rule) |

## Parallelization

Daniel works alone, so tasks run in order. If help appears: Phase 2 (first-run, T4–T6) is
independent of T1–T3 and T7, and T9/T10 can be drafted while T8 is in review.

## Open questions

- Spec's open questions still stand: the Windows window title, `AppId`/name/icon, who runs
  the prepare workflow, required status checks on `main`.
- *(Decided 2026-11-06.)* Merging the PR publishes **v0.1.0**, the first installer:
  the merge is a push to `main` with an untagged version, and Daniel wants it that way.
  So the `AppId`, display name and icon must be settled in PR review, before merge.
