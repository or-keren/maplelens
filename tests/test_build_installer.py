import importlib.util
import re
import sys
from pathlib import Path

import pytest

# The build makes the Windows installer and ships the licenses of win32-only packages (winrt).
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the build is Windows-only")

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


def _record(calls):
    """A fake run: keeps each command, ignores the timeout."""
    return lambda cmd, timeout=None: calls.append(cmd)


def test_freeze_only_runs_pyinstaller_then_the_self_check(bundle_ok):
    calls = []
    assert build_installer.main(["--freeze-only"], run=_record(calls)) == 0
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
    assert build_installer.main([], run=_record(calls)) == 0
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
        build_installer.main([], run=_record(calls))
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
        build_installer.main(["--freeze-only"], run=run)


def test_a_hung_self_check_fails_the_build(bundle_ok):
    # an error box in the windowed app would otherwise hold CI until the job's timeout
    timeouts = []

    def run(cmd, timeout=None):
        timeouts.append(timeout)
        if "--self-check" in cmd:
            raise build_installer.subprocess.TimeoutExpired(cmd, timeout)

    with pytest.raises(SystemExit, match="took over"):
        build_installer.main(["--freeze-only"], run=run)
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

    build_installer.main(["--freeze-only"], run=run)
    (_, version_before_freeze, _), (check, _, licenses_before_check) = seen
    assert version_before_freeze
    assert check == "--self-check"
    assert licenses_before_check
    version = build_installer.read_version(ROOT / "pyproject.toml")
    assert f"'{version}'" in build_installer.VERSION_FILE.read_text(encoding="utf-8")


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
    assert (ROOT / "packaging" / "windows" / "icon.ico").is_file()
