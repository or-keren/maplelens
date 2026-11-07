import hashlib
import re
import sys

import pytest

from maplelens import app
from maplelens.readers import glyphs, ocr


@pytest.fixture
def no_cache():
    glyphs.clear_cache()
    yield
    glyphs.clear_cache()


def test_self_check_passes_from_source(no_cache):
    if ocr.engine() is None:
        pytest.skip("no system OCR engine here")
    assert app.self_check() == 0


def test_self_check_fails_without_templates(tmp_path, monkeypatch, no_cache):
    monkeypatch.setattr(glyphs, "TEMPLATES", tmp_path)
    assert app.self_check() == 1


def test_self_check_fails_without_ocr(monkeypatch, no_cache):
    monkeypatch.setattr(ocr, "engine", lambda: None)
    assert app.self_check() == 1


def test_main_runs_self_check_before_any_window(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["maplelens", "--self-check"])
    monkeypatch.setattr(app, "self_check", lambda: 7)
    monkeypatch.setattr(app, "QApplication", None)  # building one would fail the test
    assert app.main() == 7


def test_a_second_start_exits_without_opening_a_window(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["maplelens"])
    monkeypatch.setattr(app, "mark_running", lambda: False)  # another copy holds the mutex
    monkeypatch.setattr(app, "QApplication", None)  # building one would fail the test
    assert app.main() == 0


def test_a_second_start_from_a_terminal_says_why(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["maplelens"])
    monkeypatch.setattr(app, "mark_running", lambda: False)
    monkeypatch.setattr(app, "QApplication", None)
    app.main()
    assert capsys.readouterr().err == "MapleLens is already running\n"


def test_self_check_fails_without_a_version(monkeypatch, no_cache):
    # a dist-info folder without METADATA gives None, not an error
    monkeypatch.setattr(app, "version", lambda name: None)
    assert app.self_check() == 1


GAME = (2, "MapleStory")
GUIDE = (1, "MapleStory Classic Thief Guide - Chrome")


@pytest.fixture
def windows(monkeypatch):
    """Fake open windows: set .list to the (handle, title) pairs on screen."""
    from maplelens.capture import pick_window

    class Windows:
        list: list = []  # noqa: RUF012

    monkeypatch.setattr(
        app.capture,
        "find_window",
        lambda title, exact=False: pick_window(Windows.list, title, exact),
    )
    return Windows


def test_unset_title_finds_the_game_and_saves_it(windows):
    windows.list = [GUIDE, GAME]
    settings, saves = {"window_title": None}, []
    assert app.find_game(settings, lambda: saves.append(1)) == 2
    assert settings["window_title"] == "MapleStory"
    assert saves == [1]


def test_unset_title_ignores_near_matches(windows):
    windows.list = [GUIDE]
    settings, saves = {"window_title": None}, []
    assert app.find_game(settings, lambda: saves.append(1)) is None
    assert settings["window_title"] is None
    assert saves == []


def test_saved_title_still_matches_by_substring(windows):
    windows.list = [GUIDE, GAME]
    settings, saves = {"window_title": "Thief Guide"}, []
    assert app.find_game(settings, lambda: saves.append(1)) == 1
    assert saves == []


def test_choosing_a_window_saves_its_title():
    settings, saves = {"window_title": None}, []
    app.choose_window(settings, lambda: saves.append(1), "Some Client")
    assert settings["window_title"] == "Some Client"
    assert saves == [1]


class _Raises:
    def update(self, *_):
        raise ValueError("bad frame")


class _Quiet:
    running = False

    def update(self, *_):
        pass


class _Box:
    def set_tab_dot(self, *_):
        pass


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "maplelens.log"
    path.write_text("from last run\n")
    app.start_log(path)
    yield path
    monkeypatch.setattr(app, "_log_path", None)


def test_start_log_empties_the_file(log):
    assert log.read_text() == ""


def test_a_tool_error_is_logged_once(log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)  # a windowed exe has no console
    seen: set[str] = set()
    for _ in range(3):
        app.update_tools(_Box(), _Raises(), _Quiet(), None, None, 0.0, seen)
    text = log.read_text(encoding="utf-8")
    assert text.count("ValueError: bad frame") == 1
    assert "Traceback" in text


def test_picker_leaves_out_our_own_windows(monkeypatch):
    monkeypatch.setattr(app.capture, "window_titles", lambda: ["MapleLens", "MapleStory"])
    assert app.game_choices() == ["MapleStory"]


@pytest.mark.skipif(sys.platform != "win32", reason="named mutexes are a Windows thing")
def test_mark_running_holds_the_mutex_the_installer_checks(monkeypatch):
    import ctypes

    monkeypatch.setattr(app, "APP_MUTEX", "MapleLensTestMutex")
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    synchronize = 0x00100000
    assert not kernel32.OpenMutexW(synchronize, False, "MapleLensTestMutex")
    assert app.mark_running()
    handle = kernel32.OpenMutexW(synchronize, False, "MapleLensTestMutex")
    assert handle
    kernel32.CloseHandle(ctypes.c_void_p(handle))


@pytest.mark.skipif(sys.platform != "win32", reason="named mutexes are a Windows thing")
def test_mark_running_is_false_while_another_copy_holds_the_mutex(monkeypatch):
    monkeypatch.setattr(app, "APP_MUTEX", "MapleLensTestSecondCopy")
    assert app.mark_running()  # the first copy
    assert not app.mark_running()  # a second start finds it held


def test_installer_checks_the_apps_mutex():
    iss = (app.Path(__file__).parent.parent / "packaging" / "windows" / "maplelens.iss").read_text(
        encoding="utf-8"
    )
    assert f'#define AppMutexName "{app.APP_MUTEX}"' in iss
    # AppMutex only tells the player to close MapleLens; the [Code] section closes it
    assert "\nAppMutex=" not in iss


ISS = app.Path(__file__).parent.parent / "packaging" / "windows" / "maplelens.iss"


def test_update_cmd_runs_setup_silently_in_update_mode():
    setup = app.Path("C:/Users/דניאל/AppData/Roaming/MapleLens/updates/MapleLens-Setup-0.2.0.exe")
    assert app.update_cmd(setup) == [
        str(setup),
        "/SILENT",
        "/SP-",
        "/SUPPRESSMSGBOXES",
        "/NOCANCEL",
        app.UPDATE_FLAG,
    ]


@pytest.fixture
def handoff(monkeypatch):
    """Fake process start and Qt quit; .calls records them in order."""

    class Handoff:
        calls: list = []  # noqa: RUF012
        fail: Exception | None = None

    Handoff.calls = []

    def popen(cmd, **kw):
        if Handoff.fail:
            raise Handoff.fail
        Handoff.calls.append(("start", cmd, kw))

    class FakeQApplication:
        @staticmethod
        def quit():
            Handoff.calls.append(("quit",))

    def no_exit(*a):
        raise AssertionError("install_update must quit through QApplication.quit")

    monkeypatch.setattr(app.subprocess, "Popen", popen)
    monkeypatch.setattr(app, "QApplication", FakeQApplication)
    monkeypatch.setattr(app.sys, "exit", no_exit)
    return Handoff


def test_install_update_starts_setup_then_quits_through_qt(handoff, tmp_path):
    setup = tmp_path / "MapleLens-Setup-0.2.0.exe"
    app.install_update(setup)
    (start, cmd, kw), quit_ = handoff.calls
    assert start == "start"
    assert cmd == app.update_cmd(setup)
    assert kw["cwd"] == setup.parent  # never inside the folder Setup replaces
    assert quit_ == ("quit",)


def test_install_update_keeps_running_when_setup_wont_start(handoff, tmp_path):
    handoff.fail = OSError("blocked")
    with pytest.raises(OSError):
        app.install_update(tmp_path / "MapleLens-Setup-0.2.0.exe")
    assert handoff.calls == []  # no quit: the old version keeps running


def test_installer_knows_the_update_flag():
    iss = ISS.read_text(encoding="utf-8")
    assert f"'{app.UPDATE_FLAG}'" in iss
    # an update run relaunches MapleLens; skipifsilent keeps the hand-run entry from doing so
    assert re.search(r'^Filename: "\{app\}\\MapleLens\.exe";.*Check: IsUpdateRun', iss, re.M)


# --- the update check ---------------------------------------------------------------


def _latest(v, digest="sha256:" + "0" * 64):
    """A releases/latest reply for version `v`."""
    return {
        "tag_name": f"v{v}",
        "assets": [
            {
                "name": f"MapleLens-Setup-{v}.exe",
                "browser_download_url": f"https://example.invalid/MapleLens-Setup-{v}.exe",
                "digest": digest,
            }
        ],
    }


NEWER = _latest("0.2.0")  # the running version is 0.1.0 throughout


@pytest.fixture
def qt_box(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.overlay import Box

    QApplication.instance() or QApplication([])
    box = Box("t", {}, lambda: None)
    box.add_menu_item("Quit MapleLens", lambda: None)
    return box


class _Fetch:
    """A fake fetch: returns .reply (or raises .error); counts its calls."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def __call__(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def make_check(qt_box, tmp_path):
    """make_check(fetch, settings, save, **kw): an UpdateCheck on qt_box, running 0.1.0."""

    def make(fetch, settings=None, save=lambda: None, **kw):
        settings = {"update_dismissed": None} if settings is None else settings
        kw.setdefault("folder", tmp_path / "updates")
        return app.UpdateCheck(qt_box, settings, save, fetch, "0.1.0", set(), now=0.0, **kw)

    return make


def _run(check, now):
    """A tick at `now`, a wait for any check it started, then the tick that collects it."""
    check.poll(now)
    if check._thread is not None:
        check._thread.join(5)
    check.poll(now)


def _menu(box):
    return [a.text() for a in box.actions()]


def test_first_check_waits_a_few_seconds(qt_box, make_check):
    fetch = _Fetch(NEWER)
    check = make_check(fetch)
    _run(check, app.UpdateCheck.FIRST_S - 1)
    assert fetch.calls == 0
    _run(check, app.UpdateCheck.FIRST_S)
    assert fetch.calls == 1


def test_a_newer_release_shows_the_line_and_the_menu_item(qt_box, make_check):
    check = make_check(_Fetch(NEWER))
    _run(check, 10.0)
    assert qt_box._notice.isVisibleTo(qt_box)
    assert qt_box._notice_text.text() == app.update_notice("0.2.0")
    assert _menu(qt_box) == ["Update to 0.2.0…", "Quit MapleLens"]


def test_the_same_version_shows_nothing(qt_box, make_check):
    check = make_check(_Fetch(_latest("0.1.0")))
    _run(check, 10.0)
    assert not qt_box._notice.isVisibleTo(qt_box)
    assert _menu(qt_box) == ["Quit MapleLens"]


def test_dismissing_saves_the_version(qt_box, make_check):
    settings, saves = {"update_dismissed": None}, []
    check = make_check(_Fetch(NEWER), settings, lambda: saves.append(1))
    _run(check, 10.0)
    qt_box._notice_close.click()
    assert settings["update_dismissed"] == "0.2.0"
    assert saves == [1]


def test_an_error_in_the_update_step_is_logged_and_the_tick_goes_on(monkeypatch):
    logged = []
    monkeypatch.setattr(app, "report_once", lambda e, seen: logged.append(e))

    class Broken:
        def poll(self, now):
            raise OSError("settings.json is locked")

    app.poll_updates(Broken(), 1.0, set())  # doesn't raise
    app.poll_updates(None, 1.0, set())  # no update check (run from source): nothing
    assert [type(e) for e in logged] == [OSError]


def test_a_failed_save_on_dismiss_is_logged(qt_box, make_check, monkeypatch):
    # settings.json held by antivirus: the click mustn't raise into Qt, unlogged
    logged = []
    monkeypatch.setattr(app, "report_once", lambda e, seen: logged.append(e))

    def save():
        raise PermissionError("settings.json is locked")

    check = make_check(_Fetch(NEWER), save=save)
    _run(check, 10.0)
    qt_box._notice_close.click()
    assert [type(e) for e in logged] == [PermissionError]


def test_a_dismissed_version_keeps_the_menu_item_but_no_line(qt_box, make_check):
    check = make_check(_Fetch(NEWER), {"update_dismissed": "0.2.0"})
    _run(check, 10.0)
    assert not qt_box._notice.isVisibleTo(qt_box)
    assert _menu(qt_box) == ["Update to 0.2.0…", "Quit MapleLens"]


def test_a_later_version_brings_the_line_back_and_relabels_the_item(qt_box, make_check):
    fetch = _Fetch(NEWER)
    check = make_check(fetch, {"update_dismissed": "0.2.0"})
    _run(check, 10.0)
    fetch.reply = _latest("0.3.0")
    _run(check, 10.0 + app.UpdateCheck.EVERY_S)
    assert fetch.calls == 2
    assert qt_box._notice.isVisibleTo(qt_box)
    assert qt_box._notice_text.text() == app.update_notice("0.3.0")
    assert _menu(qt_box) == ["Update to 0.3.0…", "Quit MapleLens"]


def test_checks_again_only_after_a_day(qt_box, make_check):
    fetch = _Fetch(NEWER)
    check = make_check(fetch)
    _run(check, 10.0)
    _run(check, 10.0 + app.UpdateCheck.EVERY_S - 1)
    assert fetch.calls == 1
    _run(check, 10.0 + app.UpdateCheck.EVERY_S)
    assert fetch.calls == 2


def test_a_failing_check_is_logged_once_and_shows_nothing(qt_box, make_check, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    fetch = _Fetch(error=OSError("offline"))
    check = make_check(fetch)
    _run(check, 10.0)
    _run(check, 10.0 + app.UpdateCheck.EVERY_S)
    assert fetch.calls == 2  # the next scheduled check tries again
    assert not qt_box._notice.isVisibleTo(qt_box)
    assert _menu(qt_box) == ["Quit MapleLens"]
    text = log.read_text(encoding="utf-8")
    assert text.count("OSError: offline") == 1
    assert "Traceback" in text


def test_a_hanging_check_never_blocks_a_tick(qt_box, make_check, log, monkeypatch):
    import threading

    monkeypatch.setattr(sys, "stderr", None)
    let_go, calls = threading.Event(), []

    def hangs():
        calls.append(1)
        let_go.wait(5)
        raise TimeoutError("timed out")

    check = make_check(hangs)
    for day in range(5):  # ticks go on while the request hangs, and start no second one
        check.poll(10.0 + day * app.UpdateCheck.EVERY_S)
    assert calls == [1]
    assert not qt_box._notice.isVisibleTo(qt_box)
    let_go.set()
    check._thread.join(5)
    check.poll(10.0 + 4 * app.UpdateCheck.EVERY_S)
    assert log.read_text(encoding="utf-8").count("TimeoutError: timed out") == 1
    assert not qt_box._notice.isVisibleTo(qt_box)


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """Pretend to be the installed Windows app 0.1.0, with its data folder in tmp_path."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(app, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app, "version", lambda name: "0.1.0")


@pytest.mark.parametrize("where", ["source", "mac"])
def test_from_source_or_on_the_mac_there_is_no_update_check(qt_box, monkeypatch, where):
    if where == "source":
        monkeypatch.delattr(sys, "frozen", raising=False)
    else:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", "darwin")
    fetch = _Fetch(NEWER)
    assert app.update_check(qt_box, {"update_check": True}, lambda: None, set(), 0.0, fetch) is None
    assert fetch.calls == 0
    assert _menu(qt_box) == ["Quit MapleLens"]  # neither update item


def test_the_installed_app_has_both_items_above_quit(qt_box, installed):
    settings = {"update_check": True, "update_dismissed": None}
    app.update_check(qt_box, settings, lambda: None, set(), 0.0, _Fetch(NEWER))
    assert _menu(qt_box) == [
        "Check for updates now",
        "Check for updates automatically",
        "Quit MapleLens",
    ]
    assert qt_box.actions()[1].isCheckable() and qt_box.actions()[1].isChecked()


def test_toggle_off_survives_a_restart_and_check_now_still_works(qt_box, installed, tmp_path):
    from maplelens.store import load_settings, save_settings

    path = tmp_path / "settings.json"
    settings = load_settings(path)

    def save():
        save_settings(path, settings)

    # kept, as main keeps its own: the menu items call into it
    first = app.update_check(qt_box, settings, save, set(), 0.0, _Fetch())
    qt_box.actions()[1].trigger()  # untick "Check for updates automatically"
    assert load_settings(path)["update_check"] is False
    assert first is not None

    for a in qt_box.actions()[:-1]:  # "restart": a fresh menu, settings read from the file
        qt_box.removeAction(a)
    fetch, settings = _Fetch(NEWER), load_settings(path)
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, fetch)
    _run(check, 10 * app.UpdateCheck.EVERY_S)
    assert fetch.calls == 0  # no automatic request
    assert not qt_box.actions()[1].isChecked()
    qt_box.actions()[0].trigger()  # "Check for updates now"
    _run(check, 10 * app.UpdateCheck.EVERY_S + 1)
    assert fetch.calls == 1


def test_toggling_back_on_resumes_the_automatic_checks(qt_box, installed):
    fetch, settings = _Fetch(NEWER), {"update_check": False, "update_dismissed": None}
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, fetch)
    _run(check, 10.0)
    assert fetch.calls == 0
    qt_box.actions()[1].trigger()
    _run(check, 11.0)
    assert fetch.calls == 1


def _check_now(check, box, now):
    [item] = [a for a in box.actions() if a.text() == "Check for updates now"]
    item.trigger()
    check._thread.join(5)
    check.poll(now)


@pytest.fixture
def manual(qt_box, installed):
    """manual(fetch, settings=None): an installed app's UpdateCheck, for "Check now"."""

    def make(fetch, settings=None):
        settings = settings or {"update_check": False, "update_dismissed": None}
        return app.update_check(qt_box, settings, lambda: None, set(), 0.0, fetch)

    return make


def test_check_now_says_up_to_date_then_hides_it(qt_box, manual):
    check = manual(_Fetch(_latest("0.1.0")))
    _check_now(check, qt_box, 20.0)
    assert qt_box._notice.isVisibleTo(qt_box)
    assert qt_box._notice_text.text() == app.UP_TO_DATE
    check.poll(20.0 + app.UpdateCheck.REPLY_S - 1)
    assert qt_box._notice.isVisibleTo(qt_box)
    check.poll(20.0 + app.UpdateCheck.REPLY_S)
    assert not qt_box._notice.isVisibleTo(qt_box)


def test_check_now_says_when_it_couldnt_check(qt_box, manual, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    check = manual(_Fetch(error=OSError("offline")))
    _check_now(check, qt_box, 20.0)
    assert qt_box._notice_text.text() == app.COULDNT_CHECK
    assert "OSError: offline" in log.read_text(encoding="utf-8")
    check.poll(20.0 + app.UpdateCheck.REPLY_S)
    assert not qt_box._notice.isVisibleTo(qt_box)


def test_check_now_shows_the_update_even_if_dismissed(qt_box, manual):
    check = manual(_Fetch(NEWER), {"update_check": False, "update_dismissed": "0.2.0"})
    _check_now(check, qt_box, 20.0)
    assert qt_box._notice_text.text() == app.update_notice("0.2.0")
    assert qt_box.actions()[0].text() == "Update to 0.2.0…"
    check.poll(20.0 + app.UpdateCheck.REPLY_S)
    assert qt_box._notice.isVisibleTo(qt_box)  # an update stays until it's closed or used


def test_a_replys_timer_leaves_a_later_line_alone(qt_box, manual):
    fetch = _Fetch(_latest("0.1.0"))
    check = manual(fetch)
    _check_now(check, qt_box, 20.0)
    fetch.reply = NEWER
    _check_now(check, qt_box, 25.0)
    check.poll(20.0 + app.UpdateCheck.REPLY_S)
    assert qt_box._notice_text.text() == app.update_notice("0.2.0")
    assert qt_box._notice.isVisibleTo(qt_box)


def test_the_installed_windows_app_gets_an_update_check(qt_box, installed, tmp_path):
    old = tmp_path / "updates"
    old.mkdir()
    (old / "MapleLens-Setup-0.1.0.exe").write_bytes(b"last update's setup")
    (old / "MapleLens-Setup-0.2.0.exe.part").write_bytes(b"half a download")
    settings = {"update_check": True, "update_dismissed": None}
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, _Fetch(NEWER))
    assert isinstance(check, app.UpdateCheck)
    assert list(old.iterdir()) == []  # old setups are cleared at startup


def test_settings_default_to_checking():
    from maplelens.store import DEFAULTS

    assert DEFAULTS["update_check"] is True
    assert DEFAULTS["update_dismissed"] is None


def test_fetch_asks_github_with_only_the_version(monkeypatch):
    import io
    import json

    seen = {}

    def urlopen(req, timeout):
        seen["url"], seen["headers"], seen["timeout"] = req.full_url, dict(req.headers), timeout
        return io.BytesIO(json.dumps(NEWER).encode())

    monkeypatch.setattr(app.urllib.request, "urlopen", urlopen)
    assert app.fetch_latest("someone/maplelens") == NEWER
    assert seen["url"] == "https://api.github.com/repos/someone/maplelens/releases/latest"
    assert seen["headers"]["User-agent"] == f"MapleLens/{app.version('maplelens')}"
    assert seen["timeout"] <= 15


# --- one click: download, digest, handoff ---------------------------------------------

SETUP = b"MZ stand-in for a setup exe"
GOOD = "sha256:" + hashlib.sha256(SETUP).hexdigest()
URL = "https://example.invalid/MapleLens-Setup-0.2.0.exe"


class _Download:
    """A fake download: writes .data to the file (or raises .error); records its calls."""

    def __init__(self, data=SETUP, error=None, wait=None):
        self.data, self.error, self.wait, self.calls = data, error, wait, []

    def __call__(self, url, dest):
        self.calls.append((url, dest))
        if self.wait:
            self.wait.wait(5)
        if self.error:
            raise self.error
        dest.write_bytes(self.data)


def _found(make_check, download, digest=GOOD, install=None):
    """An UpdateCheck that has found 0.2.0 (with `digest`) and shows its menu item."""
    check = make_check(
        _Fetch(_latest("0.2.0", digest)), download=download, install=install or (lambda p: None)
    )
    _run(check, 10.0)
    return check


def _finish_download(check, now=11.0):
    check._download_thread.join(5)
    check.poll(now)


def test_update_downloads_checks_the_digest_and_hands_over(qt_box, make_check, tmp_path):
    installs, download = [], _Download()
    check = _found(make_check, download, install=installs.append)
    qt_box.actions()[0].trigger()  # "Update to 0.2.0…"
    assert qt_box._notice_text.text() == app.downloading_notice("0.2.0")
    _finish_download(check)
    setup = tmp_path / "updates" / "MapleLens-Setup-0.2.0.exe"
    assert installs == [setup]
    assert setup.read_bytes() == SETUP
    [(url, dest)] = download.calls
    assert url == URL and dest.name == "MapleLens-Setup-0.2.0.exe.part"
    assert list(setup.parent.iterdir()) == [setup]  # the .part became the setup


@pytest.mark.parametrize(
    ("digest", "download", "reason"),
    [
        (GOOD, _Download(b"tampered"), "doesn't match"),
        (None, _Download(), "no digest"),
        ("md5:" + "0" * 32, _Download(), "doesn't match"),
        (GOOD, _Download(error=OSError("connection reset")), "connection reset"),
    ],
    ids=["wrong bytes", "no digest", "not sha256", "download fails"],
)
def test_an_unverified_setup_never_runs(
    qt_box, make_check, tmp_path, log, monkeypatch, digest, download, reason
):
    monkeypatch.setattr(sys, "stderr", None)
    installs = []
    check = _found(make_check, download, digest, installs.append)
    qt_box.actions()[0].trigger()
    _finish_download(check)
    assert installs == []
    assert qt_box._notice.isVisibleTo(qt_box)
    assert qt_box._notice_text.text() == app.UPDATE_FAILED
    assert reason in log.read_text(encoding="utf-8")
    assert list((tmp_path / "updates").glob("*")) == []  # nothing left to run by mistake


def test_a_failed_update_can_be_retried(qt_box, make_check):
    installs, download = [], _Download(error=OSError("connection reset"))
    check = _found(make_check, download, install=installs.append)
    qt_box.actions()[0].trigger()
    _finish_download(check)
    download.error = None
    qt_box.actions()[0].trigger()
    _finish_download(check)
    assert len(download.calls) == 2
    assert len(installs) == 1


def test_clicking_twice_starts_one_download(qt_box, make_check):
    import threading

    let_go = threading.Event()
    download = _Download(wait=let_go)
    check = _found(make_check, download)
    qt_box.actions()[0].trigger()
    qt_box.actions()[0].trigger()
    check.poll(11.0)
    qt_box.actions()[0].trigger()
    let_go.set()
    _finish_download(check)
    assert len(download.calls) == 1


def test_the_daily_check_leaves_the_downloading_line_alone(qt_box, make_check):
    import threading

    let_go = threading.Event()
    check = _found(make_check, _Download(wait=let_go))
    qt_box.actions()[0].trigger()
    _run(check, 10.0 + app.UpdateCheck.EVERY_S)  # finds 0.2.0 again mid-download
    assert qt_box._notice_text.text() == app.downloading_notice("0.2.0")
    let_go.set()
    _finish_download(check)


def test_setup_that_wont_start_shows_the_failure(qt_box, make_check, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)

    def blocked(path):
        raise OSError("blocked by antivirus")

    check = _found(make_check, _Download(), install=blocked)
    qt_box.actions()[0].trigger()
    _finish_download(check)
    assert qt_box._notice_text.text() == app.UPDATE_FAILED
    assert "blocked by antivirus" in log.read_text(encoding="utf-8")


def test_clear_updates_skips_what_it_cant_delete(tmp_path, monkeypatch):
    app.clear_updates(tmp_path / "missing")  # no folder yet: nothing to do
    (tmp_path / "MapleLens-Setup-0.1.0.exe").write_bytes(b"still running")

    def in_use(self, missing_ok=False):
        raise PermissionError("in use")

    monkeypatch.setattr(app.Path, "unlink", in_use)
    app.clear_updates(tmp_path)  # Setup may still be running; the next start clears it


def test_download_file_saves_the_reply_with_the_user_agent(tmp_path, monkeypatch):
    import io

    seen = {}

    def urlopen(req, timeout):
        seen["url"], seen["headers"] = req.full_url, dict(req.headers)
        return io.BytesIO(SETUP)

    monkeypatch.setattr(app.urllib.request, "urlopen", urlopen)
    dest = tmp_path / "MapleLens-Setup-0.2.0.exe.part"
    app.download_file(URL, dest)
    assert dest.read_bytes() == SETUP
    assert seen["url"] == URL
    assert seen["headers"]["User-agent"] == f"MapleLens/{app.version('maplelens')}"
