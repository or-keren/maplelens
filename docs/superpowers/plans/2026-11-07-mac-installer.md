# Mac Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Mac player downloads `MapleLens-X.Y.Z.dmg` from the same GitHub Release as
the Windows setup, drags MapleLens to Applications, opens it, and later updates it in one
click, with no Terminal at any point.

**Architecture:** PyInstaller freezes MapleLens into `MapleLens.app` (its own spec,
`packaging/mac/maplelens.spec`). `scripts/build_installer.py` gets a Mac path in three
stages (freeze, sign, dmg) so CI can sign in a job that runs no third-party code. The
existing `UpdateCheck` gains a Mac install step: a `/bin/sh` helper (new
`src/maplelens/update_mac.py`) that waits for MapleLens to exit, swaps the bundle from the
dmg, and reopens it.

**Tech Stack:** Python 3.12, uv, PySide6, pyobjc (all present); PyInstaller (existing
`build` group); Apple's built-in `codesign`, `security`, `hdiutil`, `ditto`, `sips`,
`iconutil`. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-07-mac-installer-design.md`. Read it first;
this plan points at its sections instead of repeating them.

## Global Constraints

- Screen-only rule (`AGENTS.md`): nothing touches the game, its Wine prefix or process;
  no `osascript`, no activating another app, no input events. Run the guard after every
  change.
- Windows players see no change: every existing Windows test keeps passing unchanged in
  meaning; `packaging/windows/` is not edited.
- Never change `version` in `pyproject.toml`. Never push tags or create Releases by hand.
- Never commit the certificate, its password, a built `.app` or `.dmg`. Never print the
  secrets. Never remove quarantine flags or touch the TCC database.
- Apple silicon (arm64) only.
- `CFBundleIdentifier` = `io.github.or-keren.maplelens` (confirmed by the owner 2026-11-08;
  it can never change after the first Mac release).
- Signing identity name (the certificate's Common Name): `MapleLens Release`. The build
  reads it from env `MAPLELENS_SIGN_IDENTITY`; unset means ad-hoc (`-`) with a printed
  notice.
- GitHub secrets: `MAC_SIGN_P12_BASE64`, `MAC_SIGN_P12_PASSWORD`. Only the `mac-sign`
  job sees them.
- Release assets: `MapleLens-Setup-X.Y.Z.exe` (Windows, unchanged) and
  `MapleLens-X.Y.Z.dmg` (Mac).
- Every text shown in the box's notice line fits `overlay.TAB_W` (186 px), tested like
  `test_notice_fits_the_tab_width_at_the_longest_version`.
- Commands before every commit: `uv run pytest`, `uv run ruff check`,
  `uv run ruff format --check`, `uv run python scripts/check_screen_only.py`.
- Tests that need macOS tools (`hdiutil`, `codesign`) are marked
  `@pytest.mark.skipif(sys.platform != "darwin", reason="macOS tools")`; CI runs them on
  `macos-latest`.

## Review Focus

1. **The app runs from the mounted dmg or from Downloads (translocated)** → no download
   starts; the "Move to Applications" line shows. Test in Task 5 (`can_replace`) and
   Task 6 (`UpdateCheck` with a refusing `can_install`).
2. **The swap fails halfway** (disk full, `ditto` fails, the rename is refused) → the old
   `MapleLens.app` is still at its path and opens again; the next launch shows a line.
   Test in Task 5 (helper run against a real dmg with a read-only target).
3. **Player quits MapleLens while the helper waits, or MapleLens takes long to exit** →
   the helper only proceeds once the PID is gone, never starts a second copy. Test in
   Task 5 (helper given a live PID waits until it exits).
4. **Screen Recording is revoked while MapleLens runs** → the next tick shows the
   permission line instead of black frames or errors. Test in Task 3.
5. **A Release that has only the exe (an older release, or a Mac build that failed in a
   past run)** → the Mac app sees "no update", Windows still updates. Test in Task 4
   (`no_dmg` fixture).

## File map

```
packaging/mac/maplelens.spec       new: PyInstaller Analysis + BUNDLE for the Mac
packaging/mac/icon.icns            main's maple leaf (scripts/make_icon.py); see Step 5
scripts/build_installer.py         Mac stages: --freeze-only / --sign-only / --dmg-only / all
src/maplelens/capture_mac.py       has_access(), request_access(); ensure_access stays for grab.py
src/maplelens/capture_win.py       has_access() -> True, request_access() no-op
src/maplelens/capture.py           re-exports the two new names
src/maplelens/update.py            asset_name(); parse_latest(reply, platform); can_update on darwin
src/maplelens/update_mac.py        new: bundle_path, can_replace, HELPER, helper_cmd, install_update, read_result
src/maplelens/app.py               permission line + menu item; UpdateCheck Mac wiring
.github/workflows/release.yml      mac-build + mac-sign jobs; publish attaches the dmg
README.md, AGENTS.md, CONTRIBUTING.md
tests/test_build_installer.py, test_capture_mac.py, test_app.py, test_update.py,
tests/test_update_mac.py (new), test_release_workflow.py, test_docs.py,
tests/fixtures/github/both_assets.json, no_dmg.json (new)
```

## Dependency graph

```
T0 Checkpoint A (spike, gate)
 └─ T1 Mac freeze ─ T2 sign + dmg ─ T7 release.yml
 T3 permission line          (independent of T1–T2)
 T4 update.py per platform ─ T5 update_mac.py ─ T6 UpdateCheck on the Mac
 T8 docs (after T1–T7) ─ T9 owner inputs + fork release + manual test + PR
```

---

### Task 0: Checkpoint A (spike; decides the signing and update sections)

Throwaway. Nothing from it is committed except the results written into the spec. Work
in the session scratch folder.

**Files:** Modify: `docs/superpowers/specs/2026-11-07-mac-installer-design.md` (a new
"Checkpoint A results" section).

- [ ] **Step 1: Make a throwaway self-signed code-signing certificate** in the login
  keychain, CN `MapleLens Spike` (Keychain Access → Certificate Assistant → Create a
  Certificate, type Code Signing, or `openssl` with `extendedKeyUsage=codeSigning` and
  `security import`). Check: `security find-identity -p codesigning` lists it (it shows as
  not trusted; that's expected and fine for `codesign`).
- [ ] **Step 2: Build a tiny spike app twice** with PyInstaller (`--windowed`, a
  `BUNDLE` with `CFBundleIdentifier` `io.github.maplelens.spike`): on launch it writes
  `CGPreflightScreenCaptureAccess()` and its own version to a log in the scratch folder,
  calls `CGRequestScreenCaptureAccess()` if needed, and if a file `update-url.txt` exists
  next to the log, downloads that URL with `urllib`, then runs the same swap the real
  helper will (Task 5's `HELPER` script logic, drafted here) and quits. Version 1 and 2
  differ only in the version string. Sign both with `codesign --force --deep --sign
  "MapleLens Spike"`. Pack each in a dmg with `hdiutil create`.
- [ ] **Step 3: Install v1 like a player**: serve the dmgs with `python -m http.server`,
  download v1 in Safari (so it is quarantined), drag to `/Applications`, open → expect
  the Gatekeeper block; Open Anyway in System Settings; allow Screen Recording. *(Person
  at the Mac needed for these clicks.)* Record **(c)**: did preflight turn true without
  reopening the app?
- [ ] **Step 4: Update to v2 from inside v1** (write `update-url.txt`, reopen v1). Record:
  **(a)** v2 logs preflight true with no prompt; **(b)** v2 opened with no Gatekeeper
  prompt (`xattr -p com.apple.quarantine` on the downloaded dmg and new app: present or
  not); **(d)** did the rename of `/Applications/…app` succeed, show a macOS prompt, or
  fail (exact error text / exit code, and what the System Settings → Privacy & Security
  → App Management list shows). Also check that
  `x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture` and
  `…?Privacy_AppBundles` open the right System Settings pages.
- [ ] **Step 5: Repeat Step 4 with both builds ad-hoc signed** (`--sign -`), to confirm
  (a) fails without our certificate.
- [ ] **Step 6: Write "Checkpoint A results"** into the spec and apply the decisions:
  - (a) passes → plan unchanged. Fails → self-signing is dropped: Task 2 signs ad-hoc
    only, Task 7 has no `mac-sign` secrets (the dmg is made in `mac-build`), Task 8's
    README says updates ask for Screen Recording again.
  - (b) quarantined → Task 8's README adds the Open Anyway step for updates too.
  - (c) restart needed → Task 3's line is `Allowed? Quit and reopen MapleLens` once the
    request was made (must fit; else `Reopen MapleLens after allowing`).
  - (d) → Task 5's `HELPER` uses the exact error seen to write `blocked`; if macOS
    prompts instead, `blocked` is written only when the rename still fails.
  - Delete the spike certificate from the keychain.
- [ ] **Step 7: Commit** the spec change: `docs(spec): Mac installer Checkpoint A results`.

**Gate:** stop and show the results to the user before Task 1.

---

### Task 1: Frozen `MapleLens.app` (freeze stage)

**Files:**
- Create: `packaging/mac/maplelens.spec`, `packaging/mac/icon.icns`
- Modify: `scripts/build_installer.py`
- Test: `tests/test_build_installer.py`

**Interfaces:**
- Produces in `build_installer.py`:
  - `MAC_SPEC = REPO / "packaging" / "mac" / "maplelens.spec"`
  - `MAC_APP = DIST / "MapleLens.app"`, `MAC_EXE = MAC_APP / "Contents/MacOS/MapleLens"`
  - `MAC_BUNDLE_PKG = MAC_APP / "Contents/Resources/maplelens"` *(confirm after the
    first freeze; use wherever PyInstaller puts the package data)*
  - `MAC_LICENSES = MAC_APP / "Contents/Resources/licenses"`
  - `MAC_REQUIRED = ["Contents/Frameworks/PySide6/Qt/plugins/platforms/libqcocoa.dylib"]`
    *(confirm path after the first freeze)*
  - `MAC_LICENSE_SOURCES`: `LICENSE_SOURCES` without `winrt-LICENSE.txt`, plus
    `"pyobjc-LICENSE.txt": _dist_file("pyobjc-core", <its license file>)`; Python's
    license from wherever the uv-managed Python keeps it on the Mac.
  - `freeze_cmd(spec: Path = SPEC) -> list[str]`
  - `check_bundle(src, bundle, app=APP, required=REQUIRED) -> None`
  - `copy_licenses(dest, sources=LICENSE_SOURCES) -> None`
  - `sign_cmd(app: Path, identity: str) -> list[str]` =
    `["codesign", "--force", "--deep", "--timestamp=none", "--sign", identity, str(app)]`
  - `main(argv=None, run=_run, platform=sys.platform) -> int`

- [ ] **Step 1: Pin the existing Windows tests to `platform="win32"`.** Every
  `build_installer.main(...)` call in `tests/test_build_installer.py` passes
  `platform="win32"`, so they mean the same on macOS CI.
- [ ] **Step 2: Write the failing tests**

```python
def test_mac_freeze_only_freezes_licenses_signs_adhoc_then_self_checks(mac_bundle_ok):
    calls = []
    assert build_installer.main(["--freeze-only"], run=_record(calls), platform="darwin") == 0
    freeze, sign, check = calls
    assert str(build_installer.MAC_SPEC) in freeze
    assert sign == build_installer.sign_cmd(build_installer.MAC_APP, "-")
    assert check == [str(build_installer.MAC_EXE), "--self-check"]
    assert (mac_bundle_ok / "MapleLens-LICENSE.txt").is_file()  # copied before signing


def test_check_bundle_needs_the_qt_cocoa_plugin(tmp_path):
    ...
    # like test_check_bundle_needs_the_qt_windows_plugin, with required=MAC_REQUIRED


def test_mac_licenses_ship_pyobjc_not_winrt():
    assert "pyobjc-LICENSE.txt" in build_installer.MAC_LICENSE_SOURCES
    assert "winrt-LICENSE.txt" not in build_installer.MAC_LICENSE_SOURCES


def test_mac_spec_and_icon_exist():
    assert build_installer.MAC_SPEC.is_file()
    assert (ROOT / "packaging" / "mac" / "icon.icns").is_file()


def test_mac_spec_pins_the_bundle_id_and_hides_the_dock_icon():
    text = build_installer.MAC_SPEC.read_text()
    assert "io.github.or-keren.maplelens" in text
    assert "LSUIElement" in text
```

  *(Superseded 2026-11-08: the user asked for a Dock icon; see the Mac installer
  spec. The test is now `test_mac_spec_pins_the_bundle_id_and_keeps_the_dock_icon` and
  asserts no `LSUIElement`.)*

  `mac_bundle_ok` is a fixture like `bundle_ok` that also points `MAC_LICENSES` at
  `tmp_path` and returns it.
- [ ] **Step 3: Run them:** `uv run pytest tests/test_build_installer.py -v` → the new
  tests FAIL (`MAC_SPEC` undefined); the Windows tests PASS.
- [ ] **Step 4: Write `packaging/mac/maplelens.spec`.** Same `Analysis` as the Windows
  spec (entry `app.py`, `collect_data_files("maplelens") + copy_metadata("maplelens")`,
  same `excludes`), its own `UNUSED` list for the Mac file names (Qt translations, PDF,
  Quick/Qml, VirtualKeyboard frameworks, OpenCV's ffmpeg; trim only what the self-check
  and a manual run prove unused). `EXE(console=False, upx=False, argv_emulation=False)`,
  `COLLECT`, then `BUNDLE(name="MapleLens.app", icon=.../icon.icns,
  bundle_identifier="io.github.or-keren.maplelens", version=<pyproject version, read
  with tomllib>, info_plist={"CFBundleShortVersionString": v, "CFBundleVersion": v,
  "LSUIElement": True, "LSMinimumSystemVersion": <what the wheels need>})`.
  *(Superseded 2026-11-08: the user asked for a Dock icon; see the Mac installer
  spec. No `LSUIElement`.)*
- [ ] **Step 5: Make `packaging/mac/icon.icns`** from `packaging/windows/icon.ico` with
  `sips` (to PNG) and `iconutil` (from an `.iconset` of the standard sizes).
  *(Superseded 2026-11-08: main's `scripts/make_icon.py` draws the maple leaf
  `packaging/mac/icon.icns` alongside `src/maplelens/data/icon.ico`; the rebase kept
  main's.)*
- [ ] **Step 6: Implement the Mac freeze stage in `build_installer.py`.** On `darwin`,
  `--freeze-only` runs: `freeze_cmd(MAC_SPEC)` → `copy_licenses(MAC_LICENSES,
  MAC_LICENSE_SOURCES)` → `sign_cmd(MAC_APP, "-")` (licenses invalidate PyInstaller's
  own signature) → `check_bundle(SRC_PKG, MAC_BUNDLE_PKG, MAC_APP, MAC_REQUIRED)` →
  `[MAC_EXE, "--self-check"]` with `SELF_CHECK_S`. No version-info file on the Mac.
  Windows path unchanged.
- [ ] **Step 7: Run tests:** `uv run pytest tests/test_build_installer.py -v` → PASS.
- [ ] **Step 8: Real freeze:** `uv run --group build python scripts/build_installer.py
  --freeze-only` → exits 0; confirm/adjust `MAC_BUNDLE_PKG` and `MAC_REQUIRED`; open
  `dist/MapleLens.app` with the game running: no Dock icon, box shows, EXP and path
  arrow read as from source. Record the `.app` size in the commit message.
  *(Superseded 2026-11-08: the user asked for a Dock icon; see the Mac installer
  spec. MapleLens now shows in the Dock.)*
- [ ] **Step 9: Four checks, commit:** `feat(build): freeze MapleLens.app on the Mac`.

---

### Task 2: Sign and dmg stages

**Files:** Modify: `scripts/build_installer.py`. Test: `tests/test_build_installer.py`.

**Interfaces:**
- Consumes: Task 1's `MAC_*`, `sign_cmd`, `main(..., platform)`.
- Produces:
  - `IDENTITY_ENV = "MAPLELENS_SIGN_IDENTITY"`; `sign_identity() -> str` (env value, or
    `"-"` after printing `no MAPLELENS_SIGN_IDENTITY: signing ad-hoc`)
  - `verify_cmd(app: Path) -> list[str]` = `["codesign", "--verify", "--deep", "--strict", str(app)]`
  - `dmg_path(version: str) -> Path` = `DIST / f"MapleLens-{version}.dmg"`
  - `make_dmg(app: Path, dmg: Path, run=_run) -> None`: stage folder `DIST / "dmg"`
    (emptied first) holding a `ditto` copy of the app and a symlink
    `Applications -> /Applications`; then
    `["hdiutil", "create", "-volname", "MapleLens", "-srcfolder", str(stage), "-fs", "HFS+", "-format", "UDZO", "-ov", str(dmg)]`
  - CLI on `darwin`: `--freeze-only` (Task 1), `--sign-only` (sign with
    `sign_identity()`, then verify), `--dmg-only` (self-check, then `make_dmg`), no flag
    = all three in order. `--sign-only` and `--dmg-only` must work with **only the
    standard library** (the sign job runs the runner's `python3`, no packages).

- [ ] **Step 1: Write the failing tests**

```python
def test_mac_full_build_freezes_signs_verifies_self_checks_and_makes_the_dmg(
    mac_bundle_ok, monkeypatch
):
    monkeypatch.setenv("MAPLELENS_SIGN_IDENTITY", "MapleLens Release")
    monkeypatch.setattr(build_installer, "make_dmg", lambda app, dmg, run: made.append(dmg))
    ...
    # calls: freeze, adhoc sign, self-check, sign "MapleLens Release", verify, self-check
    # made == [dmg_path(read_version())]


def test_sign_only_without_identity_signs_adhoc_and_says_so(monkeypatch, capsys): ...
def test_build_script_imports_only_the_standard_library_at_top_level():
    tree = ast.parse((ROOT / "scripts" / "build_installer.py").read_text())
    names = {a.name.split(".")[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom)}
    assert names <= sys.stdlib_module_names | {"__future__"}


def test_dmg_stage_has_the_app_and_an_applications_link(tmp_path, monkeypatch):
    ...
    # make_dmg with a fake run: stage holds MapleLens.app and Applications -> /Applications,
    # last command is the hdiutil create above


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS tools")
def test_make_dmg_really_builds_a_dmg(tmp_path):
    ...
    # fake MapleLens.app folder with one file; real run; hdiutil imageinfo exits 0
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Real build** with a throwaway identity (or none): `uv run --group build
  python scripts/build_installer.py` → `dist/MapleLens-X.Y.Z.dmg`; open it, drag to a
  test folder, open the app. Print the dmg size (reuse `report_size`).
- [ ] **Step 6: Four checks, commit:** `feat(build): sign MapleLens.app and make the dmg`.

---

### Task 3: Screen Recording permission as a box line (no exit)

**Files:** Modify: `src/maplelens/capture_mac.py`, `capture_win.py`, `capture.py`,
`src/maplelens/app.py`. Test: `tests/test_capture_mac.py`, `tests/test_app.py`.

**Interfaces:**
- Produces:
  - `capture.has_access() -> bool` (Mac: `CGPreflightScreenCaptureAccess()`; Windows: `True`)
  - `capture.request_access() -> None` (Mac: `CGRequestScreenCaptureAccess()`; Windows: no-op)
  - `capture_mac.ensure_access()` stays as is for `scripts/grab.py`.
  - In `app.py`: `NEEDS_SCREEN_RECORDING = "Allow Screen Recording: right-click"`
    (status line; Task 0 (c) may change it), `SCREEN_RECORDING_URL =
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"`,
    menu item `"Open Screen Recording settings…"` (Mac only, opens the URL with
    `QDesktopServices.openUrl`), and `screen_status(has_access: bool, hwnd) -> str | None`
    returning `NEEDS_SCREEN_RECORDING`, `LOOKING` or `None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_status_asks_for_the_permission_before_looking():
    assert app.screen_status(False, None) == app.NEEDS_SCREEN_RECORDING
    assert app.screen_status(False, 42) == app.NEEDS_SCREEN_RECORDING  # revoked mid-run
    assert app.screen_status(True, None) == app.LOOKING
    assert app.screen_status(True, 42) is None

def test_main_no_longer_exits_without_screen_recording(monkeypatch): ...
    # capture.has_access -> False; main() reaches the timer (patch app.exec to return 0)
    # and request_access was called exactly once

def test_the_mac_box_has_the_screen_recording_item(qt_box, monkeypatch): ...
def test_windows_box_has_no_screen_recording_item(qt_box, monkeypatch): ...
def test_permission_line_fits_the_box(...):  # status-line width, like the LOOKING test
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `main()` calls `capture.request_access()` once when
  `has_access()` is false and drops the `return 1`. `tick()` checks `has_access()` first:
  when false it sets the status line, hides the layer, updates tools with no reading,
  and returns before `find_game`. Update `test_ensure_access_prints_once_when_denied`
  only if its meaning changes (it shouldn't: `grab.py` still uses it).
- [ ] **Step 4: Run** → PASS. **Step 5:** from source on the Mac, turn Screen Recording
  off for Terminal in System Settings (by hand, never `tccutil`), run
  `uv run maplelens`: the line shows, the menu item opens the right page, allowing it
  moves the box on (or needs a reopen, per Task 0).
- [ ] **Step 6: Four checks, commit:** `feat(app): ask for Screen Recording in the box instead of exiting`.

---

### Task 4: Update check knows the dmg

**Files:** Modify: `src/maplelens/update.py`. Create: `tests/fixtures/github/both_assets.json`,
`no_dmg.json`. Test: `tests/test_update.py`.

**Interfaces:**
- Produces:
  - `asset_name(version: str, platform: str) -> str`: `MapleLens-Setup-{v}.exe` on
    `win32`, `MapleLens-{v}.dmg` on `darwin`
  - `parse_latest(reply, platform: str = sys.platform) -> Release | None` (matches
    `asset_name(version, platform)`; everything else unchanged)
  - `can_update(frozen, platform)`: `frozen and platform in ("win32", "darwin")`
  - `Release.url` docstring: "the platform's asset's browser_download_url"

- [ ] **Step 1: Write the failing tests**

```python
def test_mac_picks_the_dmg_and_windows_the_exe():
    reply = _load("both_assets.json")  # v0.2.0 with both assets, distinct digests
    assert parse_latest(reply, "darwin").url.endswith("MapleLens-0.2.0.dmg")
    assert parse_latest(reply, "win32").url.endswith("MapleLens-Setup-0.2.0.exe")


def test_a_release_without_the_dmg_is_no_update_on_the_mac():
    reply = _load("no_dmg.json")
    assert parse_latest(reply, "darwin") is None
    assert parse_latest(reply, "win32") is not None
```

  Change `test_can_update`'s `(True, "darwin", False)` to `True`. Existing
  `parse_latest(reply)` calls pass `"win32"` explicitly.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Four checks, commit:** `feat(update): pick the dmg on the Mac`.

---

### Task 5: `update_mac.py`: the swap helper

**Files:** Create: `src/maplelens/update_mac.py`, `tests/test_update_mac.py`.

**Interfaces:**
- Produces:
  - `bundle_path(executable: str) -> Path | None`: the `….app` holding `executable`
    (`…/X.app/Contents/MacOS/MapleLens` → `…/X.app`), else `None` (source run)
  - `can_replace(bundle: Path) -> bool`: false if the path is under `/Volumes/`, contains
    `/AppTranslocation/`, or `os.access(bundle.parent, os.W_OK)` is false
  - `RESULT = "result.txt"` in the updates folder; values `"blocked"` or `"failed"`
  - `HELPER: str` (the script below) and
    `helper_cmd(pid: int, dmg: Path, bundle: Path, result: Path) -> list[str]` =
    `["/bin/sh", "-c", HELPER, "maplelens-update", str(pid), str(dmg), str(bundle), str(result)]`
    (paths are arguments, never pasted into the script text)
  - `install_update(dmg: Path) -> None`: `subprocess.Popen(helper_cmd(os.getpid(), dmg,
    bundle_path(sys.executable), dmg.parent / RESULT), start_new_session=True)`, then
    `QApplication.quit()`; an `OSError` from Popen propagates (MapleLens keeps running)
  - `read_result(folder: Path) -> str | None`: reads and deletes `folder / RESULT`

The script, because its failure handling is the point (adjust the `blocked` test to the
error Task 0 (d) saw):

```sh
set -u
pid=$1 dmg=$2 app=$3 result=$4
while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
mnt=$(mktemp -d) || exit 1
fail() {
  echo "$1" > "$result"
  hdiutil detach -quiet "$mnt" 2>/dev/null
  rm -rf "$app.new"
  open "$app"
  exit 1
}
hdiutil attach -quiet -nobrowse -readonly -mountpoint "$mnt" "$dmg" || fail failed
ditto "$mnt/MapleLens.app" "$app.new" || fail failed
hdiutil detach -quiet "$mnt"
if ! err=$(mv "$app" "$app.old" 2>&1); then
  case $err in *"not permitted"*) fail blocked ;; *) fail failed ;; esac
fi
mv "$app.new" "$app" || { mv "$app.old" "$app"; fail failed; }
rm -rf "$app.old" "$dmg"
open "$app"
```

- [ ] **Step 1: Write the failing tests**

```python
def test_bundle_path():
    assert update_mac.bundle_path("/Applications/MapleLens.app/Contents/MacOS/MapleLens") == Path(
        "/Applications/MapleLens.app"
    )
    assert update_mac.bundle_path("/usr/bin/python3") is None


@pytest.mark.parametrize(
    "path, ok",
    [
        ("/Volumes/MapleLens/MapleLens.app", False),
        ("/private/var/folders/x/AppTranslocation/ABC/d/MapleLens.app", False),
    ],
)
def test_can_replace_refuses_the_dmg_and_translocation(path, ok): ...
def test_can_replace_needs_a_writable_folder(tmp_path): ...  # chmod 0o555 parent -> False


def test_helper_cmd_passes_paths_as_arguments(): ...  # paths not in cmd[2]


def test_read_result_reads_once(tmp_path): ...


# darwin-only, real hdiutil; a fake `open` on PATH records its argument
def test_helper_swaps_the_app_and_reopens_it(tmp_path, fake_open, old_pid): ...
def test_helper_waits_for_maplelens_to_exit(tmp_path, fake_open): ...  # sleep subprocess as pid
def test_helper_keeps_the_old_app_when_the_copy_fails(tmp_path, fake_open, old_pid):
    ...
    # corrupt dmg -> result "failed", old app untouched, reopened


def test_helper_keeps_the_old_app_in_a_read_only_folder(tmp_path, fake_open, old_pid):
    ...
    # app's folder chmod 0o555 -> result "failed", old app untouched, no .new left, reopened
```

  Fixtures: `make_dmg_with(tmp_path, version)` builds a dmg holding a folder
  `MapleLens.app/version.txt` with real `hdiutil create`; `old_pid` is the PID of a
  finished `subprocess.run(["true"])`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (on the Mac).
- [ ] **Step 5: Guard + four checks, commit:** `feat(update): Mac helper that swaps the app from the dmg`.

---

### Task 6: `UpdateCheck` on the Mac

**Files:** Modify: `src/maplelens/app.py`. Test: `tests/test_app.py`, `tests/test_overlay.py`.

**Interfaces:**
- Consumes: Task 4 `asset_name`, `can_update`; Task 5 `install_update`, `can_replace`,
  `bundle_path`, `read_result`.
- Produces:
  - `UpdateCheck(..., platform: str = sys.platform, can_install: Callable[[], str | None] = lambda: None)`:
    `_get` names the file `update.asset_name(release.version, platform)`; `_update`
    first calls `can_install()` and, if it returns a line, shows it (with the usual
    `REPLY_S` timer) instead of downloading
  - `UpdateCheck.show_result(result: str | None) -> None`: `"failed"` → `UPDATE_FAILED`;
    `"blocked"` → `ALLOW_UPDATES` line plus menu item `ALLOW_UPDATES_ITEM` opening
    `APP_MANAGEMENT_URL`; either result also goes to `maplelens.log` (the spec's
    "logs to maplelens.log", since the helper itself has no log)
  - `MOVE_TO_APPLICATIONS = "Move to Applications to update"`,
    `ALLOW_UPDATES = "Allow updates: right-click"`,
    `ALLOW_UPDATES_ITEM = "Allow MapleLens to update…"`,
    `APP_MANAGEMENT_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AppBundles"`
    (Task 0 confirms the URL)
  - `clear_updates` globs `MapleLens-*` (exe, dmg, `.part`) and leaves `result.txt`
  - `update_check(...)` on `darwin`: `install=update_mac.install_update`,
    `can_install=lambda: None if (b := update_mac.bundle_path(sys.executable)) and update_mac.can_replace(b) else MOVE_TO_APPLICATIONS`,
    then `check.show_result(update_mac.read_result(folder))`

- [ ] **Step 1: Write the failing tests**

```python
def test_the_installed_mac_app_gets_an_update_check(qt_box, monkeypatch, tmp_path):
    ...
    # frozen + darwin -> UpdateCheck with both menu items, like the Windows test


def test_mac_downloads_the_dmg_checks_it_and_hands_over(qt_box, make_check, tmp_path):
    ...
    # make_check(platform="darwin"): downloaded file is MapleLens-0.2.0.dmg, install got it


def test_mac_refuses_to_download_from_the_dmg(qt_box, make_check):
    ...
    # can_install returns MOVE_TO_APPLICATIONS -> notice shows it, download never called


def test_a_blocked_update_asks_to_allow_it(qt_box, make_check):
    ...
    # show_result("blocked") -> ALLOW_UPDATES line, ALLOW_UPDATES_ITEM in the menu


def test_a_failed_mac_update_says_so_on_the_next_start(qt_box, make_check): ...
def test_clear_updates_keeps_the_result(tmp_path): ...
```

  In `test_overlay.py`, add `MOVE_TO_APPLICATIONS` and `ALLOW_UPDATES` to the notice
  width test's parameters. Change `test_from_source_or_on_the_mac_there_is_no_update_check`
  to cover source runs only.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Four checks, commit:** `feat(update): one-click update on the Mac`.

---

### Task 7: `release.yml` builds, signs and publishes the dmg

**Files:** Modify: `.github/workflows/release.yml`. Test: `tests/test_release_workflow.py`.

**Interfaces:**
- Consumes: Task 2's `--freeze-only`, `--sign-only`, `--dmg-only`, `dmg_path`.
- Produces jobs:
  - `mac-build` (`macos-latest`, `contents: read`, no `secrets.`): checkout
    (`persist-credentials: false`), setup-uv, `uv sync --locked --group build`, the four
    checks, `build_installer.py --freeze-only`, `ditto -c -k --keepParent
    dist/MapleLens.app dist/MapleLens-app.zip`, upload artifact `mac-app`.
  - `mac-sign` (`needs: [version, mac-build]`, `macos-latest`, `contents: read`): no
    setup-uv, no `uv`/`pip`. Steps: checkout; fail with a clear `::error::` if either
    secret is empty; download `mac-app`, `ditto -x -k` into `dist/`; import the `.p12`
    into a temporary keychain under `$RUNNER_TEMP` (the decoded file deleted in the same
    step); `python3 scripts/build_installer.py --sign-only` with
    `MAPLELENS_SIGN_IDENTITY: MapleLens Release`; **delete the keychain** (`if: always()`);
    then `python3 scripts/build_installer.py --dmg-only` (the self-check runs only after
    the key is gone); upload artifact `mac-dmg`.
  - `publish`: `needs: [version, build, mac-sign]`, downloads `setup` and `mac-dmg`,
    `gh release create` with both files.
  - Actions pinned to commits, as now.

- [ ] **Step 1: Write the failing tests**

```python
def test_mac_build_can_only_read_and_sees_no_secrets(): ...
def test_only_mac_sign_sees_the_certificate(): ...  # "secrets." appears only in mac-sign
def test_mac_sign_installs_no_packages(): ...  # no setup-uv, no "uv ", no "pip" in its steps
def test_mac_sign_deletes_the_keychain_before_running_the_app():
    ...
    # index(delete step) < index(--dmg-only step); delete step has if: always()


def test_mac_sign_fails_without_the_certificate(): ...
def test_publish_attaches_the_exe_and_the_dmg(): ...  # needs mac-sign; both file names
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Run the workflow on a fork** (never on `or-keren/maplelens`): push a
  branch with a test version to the fork's `main`, secrets set to a throwaway
  certificate; the Release has both files; a run with the secrets removed fails in
  `mac-sign` and publishes nothing, no tag.
- [ ] **Step 6: Four checks, commit:** `ci(release): build, sign and publish the Mac dmg`.

---

### Task 8: Docs

**Files:** Modify: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`. Test: `tests/test_docs.py`.

- [ ] **Step 1: Failing test:** extend `test_layout_lists_the_build_and_release_files`
  with `packaging/mac/maplelens.spec`, `packaging/mac/icon.icns`,
  `src/maplelens/update_mac.py`. Run → FAIL.
- [ ] **Step 2: README** "Download (Mac)" next to "Download (Windows)": Apple silicon
  only; open the dmg, drag to Applications; the Open Anyway steps (System Settings →
  Privacy & Security → Open Anyway); allowing Screen Recording from the box's line; game
  windowed; updates from the right-click menu (plus whatever Task 0 found for (a), (b),
  (d)); settings in `~/Library/Application Support/MapleLens`; remove by dragging to the
  Trash. Keep "Run from source (macOS, developers)".
- [ ] **Step 3: AGENTS.md** Layout (`packaging/mac/`, `update_mac.py`) and Commands
  (`uv run --group build python scripts/build_installer.py` on the Mac →
  `dist/MapleLens-X.Y.Z.dmg`; `MAPLELENS_SIGN_IDENTITY`).
- [ ] **Step 4: CONTRIBUTING.md** "Mac signing certificate (once)": create a self-signed
  code-signing certificate, CN `MapleLens Release`, valid 20 years (`openssl req -x509`
  with `extendedKeyUsage=codeSigning`), export `.p12` (`openssl pkcs12 -export -legacy`
  so `security import` accepts it), `gh secret set MAC_SIGN_P12_BASE64` /
  `MAC_SIGN_P12_PASSWORD`, keep a backup offline; losing it costs players one Screen
  Recording re-grant.
- [ ] **Step 5: Run** → PASS. Four checks, commit: `docs: Mac download, build and signing`.

---

### Task 9: Owner inputs, end-to-end test, PR

- [ ] **Step 1: Owner confirms** `CFBundleIdentifier` (`io.github.or-keren.maplelens` or
  another, then updated in the spec, Global Constraints and Task 1's spec file), the
  icon, and creates the certificate + secrets per CONTRIBUTING.md.
- [ ] **Step 2: Fork release** with a version above the current one, then a second
  higher one (Task 7 Step 5's fork).
- [ ] **Step 3: Manual test in a new macOS user account** (spec, Testing → Manual):
  download the first dmg in Safari, drag, Open Anyway, allow Screen Recording from the
  box, game found, EXP and path arrow match `uv run maplelens`; then update from the
  menu to the second (with `MAPLELENS_UPDATE_REPO` pointing at the fork: `launchctl
  setenv MAPLELENS_UPDATE_REPO <fork>` before opening the app): no Gatekeeper prompt, no
  Screen Recording prompt if Task 0 (a) passed, settings and history kept. Open the app
  straight from the mounted dmg and click Update: the "Move to Applications" line shows.
- [ ] **Step 4: Windows smoke:** the Windows build and `--self-check` still pass on the
  fork's run; the installed Windows app still updates.
- [ ] **Step 5: PR** to `or-keren/maplelens` from this branch, title
  `feat: Mac installer and one-click update`, body linking spec and plan and listing
  Checkpoint A's results. Merge only once Step 1's inputs exist (spec, Release).
