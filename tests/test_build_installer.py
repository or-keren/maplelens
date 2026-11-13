import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_installer", ROOT / "scripts" / "build_installer.py"
)
build_installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_installer)


@pytest.fixture
def bundle_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(build_installer, "check_bundle", lambda src, bundle: None)
    monkeypatch.setattr(build_installer, "VERSION_FILE", tmp_path / "version_info.txt")
    monkeypatch.setattr(build_installer, "LICENSES", tmp_path / "licenses")
    monkeypatch.setattr(build_installer, "LICENSE_SOURCES", {})  # winrt's exists on Windows only


@pytest.fixture
def mac_bundle_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(build_installer, "check_bundle", lambda *args: None)
    monkeypatch.setattr(build_installer, "MAC_LICENSES", tmp_path)
    mine = build_installer.MAC_LICENSE_SOURCES["MapleLens-LICENSE.txt"]
    monkeypatch.setattr(build_installer, "MAC_LICENSE_SOURCES", {"MapleLens-LICENSE.txt": mine})
    return tmp_path


def _record(calls):
    """A fake run: keeps each command, ignores the timeout."""
    return lambda cmd, timeout=None: calls.append(cmd)


def test_freeze_only_runs_pyinstaller_then_the_self_check(bundle_ok):
    calls = []
    assert build_installer.main(["--freeze-only"], run=_record(calls), platform="win32") == 0
    cmd, check = calls
    assert check == [str(ROOT / "dist" / "MapleLens" / "MapleLens.exe"), "--self-check"]
    assert cmd[1:3] == ["-m", "PyInstaller"]
    assert str(ROOT / "packaging" / "windows" / "maplelens.spec") in cmd
    assert cmd[cmd.index("--distpath") + 1] == str(ROOT / "dist")
    assert cmd[cmd.index("--workpath") + 1] == str(ROOT / "build")


def test_spec_file_exists():
    assert (ROOT / "packaging" / "windows" / "maplelens.spec").is_file()


def test_full_build_freezes_checks_then_runs_inno_setup(bundle_ok, monkeypatch, tmp_path):
    iscc = tmp_path / "ISCC.exe"
    monkeypatch.setattr(build_installer, "find_iscc", lambda: iscc)
    calls = []
    assert build_installer.main([], run=_record(calls), platform="win32") == 0
    _, check, setup = calls
    assert check[-1] == "--self-check"
    version = build_installer.read_version(ROOT / "pyproject.toml")
    assert setup[0] == str(iscc)
    assert f"/DAppVersion={version}" in setup
    assert f"/DSourceDir={ROOT / 'dist' / 'MapleLens'}" in setup
    assert f"/O{ROOT / 'dist'}" in setup
    assert setup[-1] == str(ROOT / "packaging" / "windows" / "maplelens.iss")


def test_full_build_needs_inno_setup_before_freezing(bundle_ok, monkeypatch):
    monkeypatch.delenv("ISCC", raising=False)
    monkeypatch.setattr(build_installer, "ISCC_PLACES", [])
    monkeypatch.setattr(build_installer.shutil, "which", lambda name: None)
    calls = []
    with pytest.raises(SystemExit, match="Inno Setup"):
        build_installer.main([], run=_record(calls), platform="win32")
    assert calls == []


def test_find_iscc_takes_the_env_var_first(monkeypatch, tmp_path):
    iscc = tmp_path / "ISCC.exe"
    iscc.write_bytes(b"")
    monkeypatch.setenv("ISCC", str(iscc))
    assert build_installer.find_iscc() == iscc


def test_find_iscc_looks_in_the_usual_places(monkeypatch, tmp_path):
    iscc = tmp_path / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir()
    iscc.write_bytes(b"")
    monkeypatch.delenv("ISCC", raising=False)
    monkeypatch.setattr(build_installer.shutil, "which", lambda name: None)
    monkeypatch.setattr(build_installer, "ISCC_PLACES", [tmp_path / "nope.exe", iscc])
    assert build_installer.find_iscc() == iscc


def test_iss_installs_per_user_with_a_fixed_app_id():
    iss = (ROOT / "packaging" / "windows" / "maplelens.iss").read_text(encoding="utf-8")
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}$", iss, re.MULTILINE)
    assert "PrivilegesRequired=lowest" in iss
    assert "DefaultDirName={userpf}\\MapleLens" in iss
    assert "OutputBaseFilename=MapleLens-Setup-{#AppVersion}" in iss
    # uninstall keeps settings and history: it deletes only the downloaded setups
    assert re.findall(r"^.*\{userappdata\}.*$", iss, re.MULTILINE) == [
        r'Type: filesandordirs; Name: "{userappdata}\MapleLens\updates"'
    ]


def test_failed_self_check_fails_the_build(bundle_ok):
    def run(cmd, timeout=None):
        if "--self-check" in cmd:
            raise build_installer.subprocess.CalledProcessError(1, cmd)

    with pytest.raises(SystemExit, match="self-check"):
        build_installer.main(["--freeze-only"], run=run, platform="win32")


def test_a_hung_self_check_fails_the_build(bundle_ok):
    # an error box in the windowed app would otherwise hold CI until the job's timeout
    timeouts = []

    def run(cmd, timeout=None):
        timeouts.append(timeout)
        if "--self-check" in cmd:
            raise build_installer.subprocess.TimeoutExpired(cmd, timeout)

    with pytest.raises(SystemExit, match="took over"):
        build_installer.main(["--freeze-only"], run=run, platform="win32")
    assert timeouts == [None, build_installer.SELF_CHECK_S]  # the freeze takes its time


def _pngs(root, names):
    for n in names:
        (root / n).parent.mkdir(parents=True, exist_ok=True)
        (root / n).write_bytes(b"")


def test_check_bundle_counts_templates_and_minimaps(tmp_path):
    files = ["readers/templates/a.png", "readers/templates/f/1.png", "data/minimaps/m.png"]
    src, bundle = tmp_path / "src", tmp_path / "bundle"
    app = tmp_path / "app"
    _pngs(src, files)
    _pngs(bundle, files)
    _pngs(app, build_installer.REQUIRED)
    build_installer.check_bundle(src, bundle, app)  # same files: fine
    (bundle / "readers/templates/f/1.png").unlink()
    with pytest.raises(SystemExit, match="templates"):
        build_installer.check_bundle(src, bundle, app)


def test_check_bundle_needs_the_qt_windows_plugin(tmp_path):
    # the self-check opens no window, so it can't notice the box would never show
    src, bundle, app = tmp_path / "src", tmp_path / "bundle", tmp_path / "app"
    _pngs(app, build_installer.REQUIRED)
    build_installer.check_bundle(src, bundle, app)
    (app / "_internal/PySide6/plugins/platforms/qwindows.dll").unlink()
    with pytest.raises(SystemExit, match=r"qwindows\.dll"):
        build_installer.check_bundle(src, bundle, app)


def test_check_bundle_needs_the_icon(tmp_path):
    # the tray shows it; collect_data_files ships it only while it's package data
    src, bundle, app = tmp_path / "src", tmp_path / "bundle", tmp_path / "app"
    _pngs(app, build_installer.REQUIRED)
    build_installer.check_bundle(src, bundle, app)
    (app / "_internal/maplelens/data/icon.ico").unlink()
    with pytest.raises(SystemExit, match=r"icon\.ico"):
        build_installer.check_bundle(src, bundle, app)


def test_read_version_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    assert build_installer.read_version(tmp_path / "pyproject.toml") == "1.2.3"


def test_version_info_names_maplelens_and_the_version():
    text = build_installer.version_info("1.2.3")
    assert "filevers=(1, 2, 3, 0)" in text
    assert "prodvers=(1, 2, 3, 0)" in text
    assert "StringStruct('ProductName', 'MapleLens')" in text
    assert "StringStruct('FileVersion', '1.2.3')" in text
    assert "StringStruct('ProductVersion', '1.2.3')" in text


def test_version_info_rejects_a_non_numeric_version():
    with pytest.raises(SystemExit, match="rc1"):
        build_installer.version_info("1.0.0rc1")


def test_freeze_writes_the_version_file_first_and_licenses_before_the_check(bundle_ok):
    seen = []

    def run(cmd, timeout=None):
        seen.append(
            (
                cmd[-1],
                build_installer.VERSION_FILE.is_file(),
                build_installer.LICENSES.is_dir(),
            )
        )

    build_installer.main(["--freeze-only"], run=run, platform="win32")
    (_, version_before_freeze, _), (check, _, licenses_before_check) = seen
    assert version_before_freeze
    assert check == "--self-check"
    assert licenses_before_check
    version = build_installer.read_version(ROOT / "pyproject.toml")
    assert f"'{version}'" in build_installer.VERSION_FILE.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="winrt is installed on Windows only")
def test_copy_licenses_ships_every_license(tmp_path):
    build_installer.copy_licenses(tmp_path)
    names = {p.name for p in tmp_path.iterdir()}
    assert names == {
        "NOTICE.txt",
        "MapleLens-LICENSE.txt",
        "PySide6-Qt-LGPL-3.0.txt",
        "PySide6-Qt-GPL-3.0.txt",
        "OpenCV-LICENSE.txt",
        "OpenCV-LICENSE-3RD-PARTY.txt",
        "numpy-LICENSE.txt",
        "winrt-LICENSE.txt",
        "Python-LICENSE.txt",
    }
    lgpl = (tmp_path / "PySide6-Qt-LGPL-3.0.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl
    notice = (tmp_path / "NOTICE.txt").read_text(encoding="utf-8")
    assert "meowdb" in notice
    assert all(p.stat().st_size > 0 for p in tmp_path.iterdir())


def test_icon_exists():
    # one copy, as package data: the exe, Setup and the running app all use it
    assert (ROOT / "src" / "maplelens" / "data" / "icon.ico").is_file()
    assert not (ROOT / "packaging" / "windows" / "icon.ico").exists()


def test_the_spec_and_setup_point_at_the_packaged_icon():
    spec = (ROOT / "packaging" / "windows" / "maplelens.spec").read_text(encoding="utf-8")
    iss = (ROOT / "packaging" / "windows" / "maplelens.iss").read_text(encoding="utf-8")
    assert 'ROOT / "src" / "maplelens" / "data" / "icon.ico"' in spec
    assert r"SetupIconFile=..\..\src\maplelens\data\icon.ico" in iss


def test_setup_says_where_to_quit_a_running_maplelens():
    iss = (ROOT / "packaging" / "windows" / "maplelens.iss").read_text(encoding="utf-8")
    # the menu button's bullets as character codes: the script stays ASCII
    assert "Quit it from the ' + #$2022#$2022#$2022 +" in iss
    assert "' menu on its box or its tray icon, then try again.'" in iss
    assert "right-click" not in iss


def test_mac_freeze_only_freezes_licenses_signs_adhoc_then_self_checks(mac_bundle_ok):
    calls = []
    assert build_installer.main(["--freeze-only"], run=_record(calls), platform="darwin") == 0
    freeze, sign, check = calls
    assert str(build_installer.MAC_SPEC) in freeze
    assert sign == build_installer.sign_cmd(build_installer.MAC_APP, "-")
    assert check == [str(build_installer.MAC_EXE), "--self-check"]
    assert (mac_bundle_ok / "MapleLens-LICENSE.txt").is_file()  # copied before signing


def test_check_bundle_needs_the_qt_cocoa_plugin(tmp_path):
    src, bundle, app = tmp_path / "src", tmp_path / "bundle", tmp_path / "app"
    req = build_installer.MAC_REQUIRED
    _pngs(app, req)
    build_installer.check_bundle(src, bundle, app, req)
    (app / req[0]).unlink()
    with pytest.raises(SystemExit, match=r"libqcocoa\.dylib"):
        build_installer.check_bundle(src, bundle, app, req)


def test_the_mac_bundle_needs_the_packaged_icon():
    assert "Contents/Resources/maplelens/data/icon.ico" in build_installer.MAC_REQUIRED


def test_mac_licenses_ship_pyobjc_not_winrt():
    assert "pyobjc-LICENSE.txt" in build_installer.MAC_LICENSE_SOURCES
    assert "winrt-LICENSE.txt" not in build_installer.MAC_LICENSE_SOURCES


@pytest.mark.skipif(sys.platform != "darwin", reason="pyobjc is installed on the Mac only")
def test_copy_licenses_ships_the_mac_set(tmp_path):
    build_installer.copy_licenses(tmp_path, build_installer.MAC_LICENSE_SOURCES)
    assert {p.name for p in tmp_path.iterdir()} == set(build_installer.MAC_LICENSE_SOURCES)
    assert all(p.stat().st_size > 0 for p in tmp_path.iterdir())


def test_mac_spec_and_icon_exist():
    assert build_installer.MAC_SPEC.is_file()
    assert (ROOT / "packaging" / "mac" / "icon.icns").is_file()


def test_mac_spec_pins_the_bundle_id_and_stays_out_of_the_dock():
    text = build_installer.MAC_SPEC.read_text()
    assert "io.github.or-keren.maplelens" in text
    assert '"LSUIElement": True' in text  # in the menu bar, not the Dock


def test_mac_full_build_freezes_signs_verifies_self_checks_and_makes_the_dmg(
    mac_bundle_ok, monkeypatch
):
    monkeypatch.setenv("MAPLELENS_SIGN_IDENTITY", "MapleLens Release")
    made = []
    monkeypatch.setattr(build_installer, "make_dmg", lambda app, dmg, run: made.append(dmg))
    calls = []
    assert build_installer.main([], run=_record(calls), platform="darwin") == 0
    app, exe = build_installer.MAC_APP, str(build_installer.MAC_EXE)
    assert calls[1:] == [
        build_installer.sign_cmd(app, "-"),
        [exe, "--self-check"],
        build_installer.sign_cmd(app, "MapleLens Release"),
        build_installer.verify_cmd(app),
        [exe, "--self-check"],
    ]
    assert made == [build_installer.dmg_path(build_installer.read_version())]


def test_sign_only_without_identity_signs_adhoc_and_says_so(monkeypatch, capsys):
    monkeypatch.delenv("MAPLELENS_SIGN_IDENTITY", raising=False)
    calls = []
    assert build_installer.main(["--sign-only"], run=_record(calls), platform="darwin") == 0
    app = build_installer.MAC_APP
    assert calls == [build_installer.sign_cmd(app, "-"), build_installer.verify_cmd(app)]
    assert "signing ad-hoc" in capsys.readouterr().out


@pytest.mark.parametrize("machine", ["arm64", "x86_64"])
def test_the_dmg_is_named_as_the_update_check_looks_for_it(machine):
    from maplelens import update

    dmg = build_installer.dmg_path("1.2.3", machine)
    assert dmg.name == update.asset_name("1.2.3", "darwin", machine)


def test_dmg_only_self_checks_then_makes_the_dmg(monkeypatch):
    made = []
    monkeypatch.setattr(build_installer, "make_dmg", lambda app, dmg, run: made.append(app))
    calls = []
    assert build_installer.main(["--dmg-only"], run=_record(calls), platform="darwin") == 0
    assert calls == [[str(build_installer.MAC_EXE), "--self-check"]]
    assert made == [build_installer.MAC_APP]


def test_new_flags_are_mac_only_and_exclusive():
    for flag in ("--sign-only", "--dmg-only"):
        with pytest.raises(SystemExit):
            build_installer.main([flag], run=_record([]), platform="win32")
    with pytest.raises(SystemExit):
        build_installer.main(["--sign-only", "--dmg-only"], run=_record([]), platform="darwin")


def test_build_script_imports_only_the_standard_library_at_top_level():
    tree = ast.parse((ROOT / "scripts" / "build_installer.py").read_text())
    names = {a.name.split(".")[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom)}
    assert names <= sys.stdlib_module_names | {"__future__"}


def _fake_app(root):
    app = root / "MapleLens.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text("x")
    return app


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS tools")
def test_dmg_stage_has_the_app_and_an_applications_link(tmp_path, monkeypatch):
    monkeypatch.setattr(build_installer, "DIST", tmp_path / "dist")
    app, dmg, calls = _fake_app(tmp_path), tmp_path / "out.dmg", []
    stage = tmp_path / "dist" / "dmg"
    stage.mkdir(parents=True)
    (stage / "stale").write_text("x")

    def run(cmd, timeout=None):
        calls.append(cmd)
        if cmd[0] == "ditto":  # the fake ditto copies like the real one
            build_installer.shutil.copytree(cmd[1], cmd[2], symlinks=True)

    build_installer.make_dmg(app, dmg, run)
    assert calls[0] == ["ditto", str(app), str(stage / "MapleLens.app")]
    assert (stage / "MapleLens.app" / "Contents" / "Info.plist").is_file()
    assert os.readlink(stage / "Applications") == "/Applications"
    assert not (stage / "stale").exists()
    assert calls[-1] == [
        "hdiutil", "create", "-volname", "MapleLens", "-srcfolder", str(stage),
        "-fs", "HFS+", "-format", "UDZO", "-ov", str(dmg),
    ]  # fmt: skip


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS tools")
def test_make_dmg_really_builds_a_dmg(tmp_path, monkeypatch):
    monkeypatch.setattr(build_installer, "DIST", tmp_path / "dist")
    dmg = tmp_path / "out.dmg"
    build_installer.make_dmg(_fake_app(tmp_path), dmg)
    subprocess.run(["hdiutil", "imageinfo", str(dmg)], check=True, capture_output=True)
