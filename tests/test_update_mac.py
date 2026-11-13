import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from maplelens import update_mac

mac_tools = pytest.mark.skipif(sys.platform != "darwin", reason="macOS tools")

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_installer", ROOT / "scripts" / "build_installer.py"
)
build_installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_installer)


def test_bundle_path():
    assert update_mac.bundle_path("/Applications/MapleLens.app/Contents/MacOS/MapleLens") == Path(
        "/Applications/MapleLens.app"
    )
    assert update_mac.bundle_path("/usr/bin/python3") is None


@mac_tools
@pytest.mark.parametrize(
    "path",
    [
        "/Volumes/MapleLens/MapleLens.app",
        "/private/var/folders/x/AppTranslocation/ABC/d/MapleLens.app",
    ],
)
def test_can_replace_refuses_the_dmg_and_translocation(path, monkeypatch):
    monkeypatch.setattr(update_mac.os, "access", lambda *a: True)  # only the path refuses
    assert not update_mac.can_replace(Path(path))


@mac_tools
def test_can_replace_needs_a_writable_folder(tmp_path):
    apps = tmp_path / "apps"
    apps.mkdir()
    assert update_mac.can_replace(apps / "MapleLens.app")
    apps.chmod(0o555)
    try:
        assert not update_mac.can_replace(apps / "MapleLens.app")
    finally:
        apps.chmod(0o755)


def test_helper_cmd_passes_paths_as_arguments():
    dmg, app, result = Path("/u/M.dmg"), Path("/A/MapleLens.app"), Path("/u/result.txt")
    cmd = update_mac.helper_cmd(42, dmg, app, result)
    assert cmd == [
        "/bin/sh",
        "-c",
        update_mac.HELPER,
        "maplelens-update",
        "42",
        *map(str, (dmg, app, result)),
    ]
    assert not any(str(p) in cmd[2] for p in (dmg, app, result))


def test_read_result_reads_once(tmp_path):
    assert update_mac.read_result(tmp_path) is None
    (tmp_path / update_mac.RESULT).write_text("blocked\n")
    assert update_mac.read_result(tmp_path) == "blocked"
    assert update_mac.read_result(tmp_path) is None


@pytest.fixture
def handoff(monkeypatch):
    """Fake process start and Qt quit; .calls records them in order."""
    calls = []

    def popen(cmd, **kw):
        if handoff.fail:
            raise handoff.fail
        calls.append(("start", cmd, kw))

    class FakeQApplication:
        @staticmethod
        def quit():
            calls.append(("quit",))

    handoff.calls, handoff.fail = calls, None
    monkeypatch.setattr(update_mac.subprocess, "Popen", popen)
    monkeypatch.setattr(update_mac, "QApplication", FakeQApplication)
    monkeypatch.setattr(
        update_mac.sys, "executable", "/Applications/MapleLens.app/Contents/MacOS/MapleLens"
    )
    return handoff


def test_install_update_starts_the_helper_then_quits_through_qt(handoff, tmp_path):
    dmg = tmp_path / "MapleLens-0.2.0.dmg"
    update_mac.install_update(dmg)
    (start, cmd, kw), quit_ = handoff.calls
    assert start == "start"
    assert cmd == update_mac.helper_cmd(
        os.getpid(), dmg, Path("/Applications/MapleLens.app"), tmp_path / update_mac.RESULT
    )
    assert kw["start_new_session"] is True
    assert quit_ == ("quit",)


def test_install_update_keeps_running_when_the_helper_wont_start(handoff, tmp_path):
    handoff.fail = OSError("no sh")
    with pytest.raises(OSError):
        update_mac.install_update(tmp_path / "MapleLens-0.2.0.dmg")
    assert handoff.calls == []


def test_install_update_refuses_outside_an_app_bundle(handoff, monkeypatch, tmp_path):
    monkeypatch.setattr(update_mac.sys, "executable", "/usr/local/bin/python3")
    with pytest.raises(RuntimeError, match=r"\.app"):
        update_mac.install_update(tmp_path / "MapleLens-0.2.0.dmg")
    assert handoff.calls == []


# --- the real helper: hdiutil and ditto, a fake `open` ---------------------------------


def make_app(folder: Path, version: str) -> Path:
    app = folder / "MapleLens.app"
    app.mkdir(parents=True)
    (app / "version.txt").write_text(version)
    return app


def make_dmg_with(tmp_path: Path, version: str) -> Path:
    """A dmg holding MapleLens.app/version.txt, made by the release build's make_dmg so
    a change to its layout breaks these tests."""
    app = make_app(tmp_path / "dmg-src", version)
    dmg = tmp_path / f"MapleLens-{version}.dmg"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(build_installer, "DIST", tmp_path / "dist")  # its staging folder
        build_installer.make_dmg(app, dmg)
    return dmg


def attached_from(folder: Path) -> list[str]:
    """The /dev entries of disk images attached from files under `folder`."""
    info = plistlib.loads(
        subprocess.run(["hdiutil", "info", "-plist"], capture_output=True, check=True).stdout
    )
    return [
        image["system-entities"][0]["dev-entry"]
        for image in info.get("images", [])
        if image.get("image-path", "").startswith(str(folder.resolve()))
    ]


@pytest.fixture(scope="session")
def built_dmg(tmp_path_factory):
    """hdiutil create takes seconds: build the 0.2.0 dmg once."""
    folder = tmp_path_factory.mktemp("dmg")
    yield make_dmg_with(folder, "0.2.0")
    # hdiutil create now and then leaves its own work image attached
    for dev in attached_from(folder):
        subprocess.run(["hdiutil", "detach", "-quiet", "-force", dev], check=False)
    assert attached_from(folder) == []


@pytest.fixture
def dmg(tmp_path, built_dmg):
    """A copy of the 0.2.0 dmg in this test's updates folder (the helper deletes it)."""
    (tmp_path / "updates").mkdir()
    return Path(shutil.copy(built_dmg, tmp_path / "updates"))


@pytest.fixture
def fake_open(tmp_path):
    """Env for the helper with an `open` that records its arguments; .opened reads them."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "opened.txt"
    script = bin_ / "open"
    script.write_text(f'#!/bin/sh\necho "$*" >> "{log}"\n')
    script.chmod(0o755)

    return SimpleNamespace(
        env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"},
        opened=lambda: log.read_text().splitlines() if log.exists() else [],
    )


@pytest.fixture
def old_pid():
    """A PID that has already exited (and been reaped)."""
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def run_helper(pid, dmg, app, env):
    result = dmg.parent / update_mac.RESULT
    return subprocess.Popen(update_mac.helper_cmd(pid, dmg, app, result), env=env)


@mac_tools
def test_helper_swaps_the_app_and_reopens_it(tmp_path, fake_open, old_pid, dmg):
    app = make_app(tmp_path / "Applications", "0.1.0")
    assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) == 0
    assert (app / "version.txt").read_text() == "0.2.0"
    assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]  # no .new/.old
    assert not dmg.exists()
    assert update_mac.read_result(dmg.parent) is None
    assert fake_open.opened() == [f"-g {app}"]


@mac_tools
def test_helper_waits_for_maplelens_to_exit(tmp_path, fake_open, dmg):
    app = make_app(tmp_path / "Applications", "0.1.0")
    maplelens = subprocess.Popen(["sleep", "1"])
    helper = run_helper(maplelens.pid, dmg, app, fake_open.env)
    time.sleep(0.6)
    assert helper.poll() is None
    assert (app / "version.txt").read_text() == "0.1.0"
    assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]
    assert fake_open.opened() == []
    maplelens.wait()  # reaped: until then the PID is a zombie that still answers kill -0
    assert helper.wait(timeout=30) == 0
    assert (app / "version.txt").read_text() == "0.2.0"
    assert fake_open.opened() == [f"-g {app}"]


@mac_tools
def test_helper_keeps_the_old_app_when_the_copy_fails(tmp_path, fake_open, old_pid):
    app = make_app(tmp_path / "Applications", "0.1.0")
    updates = tmp_path / "updates"
    updates.mkdir()
    dmg = updates / "MapleLens-0.2.0.dmg"
    dmg.write_bytes(b"not a disk image")
    assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) != 0
    assert update_mac.read_result(updates) == "failed"
    assert (app / "version.txt").read_text() == "0.1.0"
    assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]
    assert fake_open.opened() == [f"-g {app}"]


@mac_tools
def test_helper_keeps_the_old_app_in_a_read_only_folder(tmp_path, fake_open, old_pid, dmg):
    app = make_app(tmp_path / "Applications", "0.1.0")
    app.parent.chmod(0o555)
    try:
        assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) != 0
        assert update_mac.read_result(dmg.parent) == "failed"
        assert (app / "version.txt").read_text() == "0.1.0"
        assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]
        assert fake_open.opened() == [f"-g {app}"]
    finally:
        app.parent.chmod(0o755)


@mac_tools
def test_helper_replaces_a_stale_copy_from_an_interrupted_update(tmp_path, fake_open, old_pid, dmg):
    app = make_app(tmp_path / "Applications", "0.1.0")
    stale = make_app(tmp_path / "stale", "0.1.5")
    (stale / "leftover.txt").write_text("from an update that was cut off")
    stale.rename(app.parent / "MapleLens.app.new")
    (app.parent / "MapleLens.app.old").mkdir()  # mv would move the app into it
    assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) == 0
    assert sorted(p.name for p in app.iterdir()) == ["version.txt"]
    assert (app / "version.txt").read_text() == "0.2.0"
    assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]


@mac_tools
def test_helper_reopens_the_old_app_when_it_cant_make_a_mount_point(tmp_path, fake_open, old_pid):
    app = make_app(tmp_path / "Applications", "0.1.0")
    updates = tmp_path / "updates"
    updates.mkdir()
    (tmp_path / "bin" / "mktemp").symlink_to("/usr/bin/false")
    env = fake_open.env
    helper = run_helper(old_pid, updates / "MapleLens-0.2.0.dmg", app, env)
    assert helper.wait(timeout=30) != 0
    assert update_mac.read_result(updates) == "failed"
    assert (app / "version.txt").read_text() == "0.1.0"
    assert fake_open.opened() == [f"-g {app}"]


@mac_tools
def test_helper_reports_blocked_when_macos_refuses_the_rename(tmp_path, fake_open, old_pid, dmg):
    app = make_app(tmp_path / "Applications", "0.1.0")
    subprocess.run(["chflags", "uchg", app], check=True)  # mv: "Operation not permitted"
    try:
        assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) != 0
        assert update_mac.read_result(dmg.parent) == "blocked"
        assert (app / "version.txt").read_text() == "0.1.0"
        assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]
        assert fake_open.opened() == [f"-g {app}"]
    finally:
        subprocess.run(["chflags", "nouchg", app], check=True)


@mac_tools
def test_helper_puts_the_old_app_back_when_the_new_one_wont_move_in(
    tmp_path, fake_open, old_pid, dmg
):
    app = make_app(tmp_path / "Applications", "0.1.0")
    mv = tmp_path / "bin" / "mv"  # refuses only the second rename, the new app's
    mv.write_text('#!/bin/sh\ncase $1 in *.new) exit 1 ;; esac\nexec /bin/mv "$@"\n')
    mv.chmod(0o755)
    assert run_helper(old_pid, dmg, app, fake_open.env).wait(timeout=30) != 0
    assert update_mac.read_result(dmg.parent) == "failed"
    assert (app / "version.txt").read_text() == "0.1.0"
    assert sorted(p.name for p in app.parent.iterdir()) == ["MapleLens.app"]
    assert fake_open.opened() == [f"-g {app}"]
