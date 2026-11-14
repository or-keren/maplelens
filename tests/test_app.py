import hashlib
import re
import sys
import threading
import types
from typing import ClassVar

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal

import maplelens
from maplelens import app, overlay, reader, update_mac
from maplelens.readers import Reading, glyphs, ocr
from maplelens.tools.path_arrow import maps


@pytest.fixture(autouse=True)
def apple_silicon(monkeypatch):
    """The Mac tests pick Apple silicon's dmg whatever CPU runs them."""
    monkeypatch.setattr(maplelens.update._platform, "machine", lambda: "arm64")


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


def test_self_check_fails_without_classes_json(monkeypatch, no_cache):
    from maplelens.tools.class_helper import data

    monkeypatch.setattr(data, "load", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert app.self_check() == 1


def test_self_check_fails_without_quests_json(monkeypatch, no_cache):
    from maplelens.tools.quest_helper import data

    monkeypatch.setattr(data, "load", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert app.self_check() == 1


def test_self_check_fails_without_quest_names(monkeypatch, no_cache):
    from maplelens.readers import quest_window

    monkeypatch.setattr(
        quest_window, "known_quest_names", lambda: (_ for _ in ()).throw(FileNotFoundError())
    )
    assert app.self_check() == 1


class _Path:
    def __init__(self, starts: bool):
        self.starts, self.running, self.calls = starts, False, []

    def go(self, *args):
        self.calls.append(args)
        self.running = self.starts


@pytest.mark.parametrize("starts, selected", [(True, []), (False, [1])])
def test_quest_go_shows_the_path_tab_only_when_no_trip_runs(starts, selected):
    path, picked = _Path(starts), []
    app.quest_go(path, picked.append)("town", (1, 2), "Heena")
    assert path.calls == [("town", (1, 2), "Heena")] and picked == selected


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


def test_the_icon_is_package_data():
    assert app.ICON.is_file()
    assert app.ICON.parent == maps.DATA.parent  # next to maps.json, so the bundle ships it


def test_self_check_fails_without_the_icon(tmp_path, monkeypatch, no_cache):
    monkeypatch.setattr(app, "ICON", tmp_path / "icon.ico")
    assert app.self_check() == 1


def test_self_check_fails_on_an_icon_qt_cant_read(tmp_path, monkeypatch, no_cache):
    # the frozen app without its ico image plugin reads the file but can't decode it
    (tmp_path / "icon.ico").write_bytes(b"not an icon")
    monkeypatch.setattr(app, "ICON", tmp_path / "icon.ico")
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
    dot = False
    open = False

    def update(self, *_):
        pass

    def hide_marks(self):
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
        app.update_tools(
            _Box(), _Raises(), _Quiet(), _Quiet(), _Quiet(), _Quiet(), None, None, 0.0, seen
        )
    text = log.read_text(encoding="utf-8")
    assert text.count("ValueError: bad frame") == 1
    assert "Traceback" in text


class _FocusBox:
    def __init__(self, current=0):
        self.current, self.touches = current, 0
        self.selects = []

    def select(self, i):
        self.selects.append(i)
        self.current = i

    def set_tab_dot(self, *_):
        pass


class _Open(_Quiet):
    def __init__(self, open_=True):
        self.open = open_

    def update(self, r, *_):
        self.open = r is not None


def _focus(box):
    return app.QuestFocus(box, 3)


def test_switches_on_open_and_back_on_close():
    box = _FocusBox(1)
    f = _focus(box)
    f.update(True)
    assert box.current == 1  # one reading isn't enough
    f.update(True)
    assert box.current == 3
    f.update(False)
    f.update(False)
    assert box.current == 1


def test_touch_keeps_the_tab():
    box = _FocusBox(0)
    f = _focus(box)
    f.update(True)
    f.update(True)
    box.touches += 1
    f.update(False)
    f.update(False)
    assert box.current == 3


def test_a_touch_before_opening_does_not_block_the_way_back():
    box = _FocusBox(1)
    box.touches = 5
    f = _focus(box)
    for o in (True, True, False, False):
        f.update(o)
    assert box.selects == [3, 1]


def test_already_on_quests_stays():
    box = _FocusBox(3)
    f = _focus(box)
    for o in (True, True, False, False):
        f.update(o)
    assert box.selects == []


def test_one_missed_reading_keeps_the_tab():
    box = _FocusBox(0)
    f = _focus(box)
    for o in (True, True, False, True):
        f.update(o)
    assert box.selects == [3]  # the single closed reading didn't switch back
    f.update(True)
    assert box.selects == [3]


def test_no_reading_counts_as_closed():
    box = _FocusBox(2)
    f = app.QuestFocus(box, 3)
    q = _Open()
    for r in ("r", "r", None, None):
        app.update_tools(box, _Quiet(), _Quiet(), _Quiet(), q, f, r, None, 0.0, set())
        if r is None:
            assert not q.open
        if r == "r" and box.selects:
            assert box.current == 3
    assert box.selects == [3, 2]


def test_quest_tool_error_does_not_stop_the_others(log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    ran = []

    class Cls(_Quiet):
        def update(self, *_):
            ran.append(1)

    q = _Raises()
    q.open = False
    app.update_tools(_Box(), _Quiet(), _Quiet(), Cls(), q, _Quiet(), None, None, 0.0, set())
    assert ran and "bad frame" in log.read_text(encoding="utf-8")


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


def _latest(v, digest="sha256:" + "0" * 64, name=None):
    """A releases/latest reply for version `v`, its one asset the Windows setup or `name`."""
    name = name or f"MapleLens-Setup-{v}.exe"
    return {
        "tag_name": f"v{v}",
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://example.invalid/{name}",
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


@pytest.fixture(autouse=True)
def _screen_access(monkeypatch):
    """Screen Recording allowed, as it always is on Windows; a test that needs it off says so."""
    monkeypatch.setattr(app.capture, "has_access", lambda: True)


@pytest.fixture
def make_check(qt_box, tmp_path):
    """make_check(fetch, settings, save, **kw): an UpdateCheck on qt_box, running 0.1.0
    on Windows unless kw says platform="darwin"."""

    def make(fetch, settings=None, save=lambda: None, **kw):
        settings = {"update_dismissed": None} if settings is None else settings
        kw.setdefault("folder", tmp_path / "updates")
        kw.setdefault("platform", "win32")
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


def test_from_source_there_is_no_update_check(qt_box, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    fetch = _Fetch(NEWER)
    assert app.update_check(qt_box, {"update_check": True}, lambda: None, set(), 0.0, fetch) is None
    assert fetch.calls == 0
    assert _menu(qt_box) == ["Quit MapleLens"]  # neither update item


def test_the_installed_app_adds_no_menu_items(qt_box, installed):
    settings = {"update_check": True, "update_dismissed": None}
    app.update_check(qt_box, settings, lambda: None, set(), 0.0, _Fetch(NEWER))
    assert _menu(qt_box) == ["Quit MapleLens"]  # its controls are in Settings


def test_toggle_off_survives_a_restart_and_check_now_still_works(qt_box, installed, tmp_path):
    from maplelens.store import load_settings, save_settings

    path = tmp_path / "settings.json"
    settings = load_settings(path)

    def save():
        save_settings(path, settings)

    first = app.update_check(qt_box, settings, save, set(), 0.0, _Fetch())
    first.set_auto(False)  # Settings' "Check for updates automatically", unticked
    assert load_settings(path)["update_check"] is False

    fetch, settings = _Fetch(NEWER), load_settings(path)  # "restart": settings from the file
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, fetch)
    _run(check, 10 * app.UpdateCheck.EVERY_S)
    assert fetch.calls == 0  # no automatic request
    assert settings["update_check"] is False  # what Settings' checkbox starts from
    check.check_now()  # Settings' "Check now"
    _run(check, 10 * app.UpdateCheck.EVERY_S + 1)
    assert fetch.calls == 1


def test_toggling_back_on_resumes_the_automatic_checks(qt_box, installed):
    fetch, settings = _Fetch(NEWER), {"update_check": False, "update_dismissed": None}
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, fetch)
    _run(check, 10.0)
    assert fetch.calls == 0
    check.set_auto(True)
    _run(check, 11.0)
    assert fetch.calls == 1


def _check_now(check, _box, now):
    check.check_now()  # Settings' "Check now"
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

    def urlopen(req, timeout, context):
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


# --- the Mac: the dmg, where the app lives, what the last update left -----------------

DMG = _latest("0.2.0", GOOD, name="MapleLens-0.2.0.dmg")


def test_the_installed_mac_app_gets_an_update_check(qt_box, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(app, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app, "version", lambda name: "0.1.0")
    folder = tmp_path / "updates"
    folder.mkdir()
    (folder / "MapleLens-0.1.0.dmg").write_bytes(b"last update's dmg")
    (folder / update_mac.RESULT).write_text("failed\n")
    settings = {"update_check": True, "update_dismissed": None}
    check = app.update_check(qt_box, settings, lambda: None, set(), 0.0, _Fetch(DMG))
    assert isinstance(check, app.UpdateCheck)
    assert _menu(qt_box) == ["Quit MapleLens"]  # its controls are in Settings
    assert list(folder.iterdir()) == []  # the old dmg cleared, the result read once
    assert qt_box._notice_text.text() == app.UPDATE_FAILED
    assert check._install is update_mac.install_update
    assert check._can_install() == app.MOVE_TO_APPLICATIONS  # pytest isn't inside a .app
    app_exe = tmp_path / "MapleLens.app" / "Contents" / "MacOS" / "MapleLens"
    monkeypatch.setattr(sys, "executable", str(app_exe))
    assert check._can_install() is None  # a writable folder
    _run(check, 10.0)
    assert check.release is not None and check.release.version == "0.2.0"  # found the dmg


def test_mac_downloads_the_dmg_checks_it_and_hands_over(qt_box, make_check, tmp_path):
    installs, download = [], _Download()
    check = make_check(_Fetch(DMG), download=download, install=installs.append, platform="darwin")
    _run(check, 10.0)
    qt_box.actions()[0].trigger()  # "Update to 0.2.0…"
    _finish_download(check)
    dmg = tmp_path / "updates" / "MapleLens-0.2.0.dmg"
    assert installs == [dmg]
    assert dmg.read_bytes() == SETUP
    [(_, dest)] = download.calls
    assert dest.name == "MapleLens-0.2.0.dmg.part"


def test_an_intel_mac_downloads_the_intel_dmg(qt_box, make_check, tmp_path, monkeypatch):
    monkeypatch.setattr(maplelens.update._platform, "machine", lambda: "x86_64")
    installs, download = [], _Download()
    intel = _latest("0.2.0", GOOD, name="MapleLens-0.2.0-intel.dmg")
    check = make_check(_Fetch(intel), download=download, install=installs.append, platform="darwin")
    _run(check, 10.0)
    qt_box.actions()[0].trigger()  # "Update to 0.2.0…"
    _finish_download(check)
    assert installs == [tmp_path / "updates" / "MapleLens-0.2.0-intel.dmg"]


def test_mac_refuses_to_download_from_the_dmg(qt_box, make_check):
    download = _Download()
    check = make_check(
        _Fetch(DMG),
        download=download,
        platform="darwin",
        can_install=lambda: app.MOVE_TO_APPLICATIONS,
    )
    _run(check, 10.0)
    qt_box.actions()[0].trigger()
    assert check._download_thread is None
    assert download.calls == []
    assert qt_box._notice_text.text() == app.MOVE_TO_APPLICATIONS
    check.poll(10.0 + app.UpdateCheck.REPLY_S)
    assert not qt_box._notice.isVisibleTo(qt_box)
    assert _menu(qt_box)[0] == "Update to 0.2.0…"  # the item stays for after the move
    assert check.status() == app.update_available("0.2.0")  # About says so too


def test_a_blocked_update_asks_to_allow_it(qt_box, make_check, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    opened = []
    monkeypatch.setattr(app.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    check = make_check(_Fetch(DMG), platform="darwin")
    check.show_result("blocked")
    assert qt_box._notice_text.text() == app.ALLOW_UPDATES
    assert _menu(qt_box) == [app.ALLOW_UPDATES_ITEM, "Quit MapleLens"]
    qt_box.actions()[0].trigger()
    assert opened == [app.APP_MANAGEMENT_URL]
    assert "blocked" in log.read_text(encoding="utf-8")
    _run(check, 10.0)  # the first check finds 0.2.0: the line stays until it's closed
    assert qt_box._notice_text.text() == app.ALLOW_UPDATES
    qt_box._notice_close.click()
    _run(check, 10.0 + app.UpdateCheck.EVERY_S)
    assert qt_box._notice_text.text() == app.update_notice("0.2.0")


def test_a_failed_mac_update_says_so_on_the_next_start(qt_box, make_check, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    check = make_check(_Fetch(), platform="darwin")
    check.show_result(None)  # no update last time
    assert not qt_box._notice.isVisibleTo(qt_box)
    assert log.read_text(encoding="utf-8") == ""
    check.show_result("failed")
    assert qt_box._notice_text.text() == app.UPDATE_FAILED
    assert "failed" in log.read_text(encoding="utf-8")


def test_clear_updates_keeps_the_result(tmp_path):
    names = ["MapleLens-0.1.0.dmg", "MapleLens-0.2.0.dmg.part", "MapleLens-Setup-0.1.0.exe"]
    for name in [*names, update_mac.RESULT]:
        (tmp_path / name).write_bytes(b"x")
    app.clear_updates(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [update_mac.RESULT]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS's CA list")
def test_tls_on_the_mac_trusts_macos_cas_without_homebrew(monkeypatch):
    # the shipped OpenSSL looks for CAs in Homebrew's folder; a friend's Mac has none
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent")
    assert app._tls("darwin").cert_store_stats()["x509_ca"] > 0


def test_download_file_saves_the_reply_with_the_user_agent(tmp_path, monkeypatch):
    import io

    seen = {}

    def urlopen(req, timeout, context):
        seen["url"], seen["headers"] = req.full_url, dict(req.headers)
        return io.BytesIO(SETUP)

    monkeypatch.setattr(app.urllib.request, "urlopen", urlopen)
    dest = tmp_path / "MapleLens-Setup-0.2.0.exe.part"
    app.download_file(URL, dest)
    assert dest.read_bytes() == SETUP
    assert seen["url"] == URL
    assert seen["headers"]["User-agent"] == f"MapleLens/{app.version('maplelens')}"


def test_the_box_text_points_at_the_menu_button():
    from maplelens.overlay import MENU_MARK

    assert app.LOOKING == "Looking for MapleStory…"  # the ••• beside it is the hint
    assert app.update_notice("1.2.3") == f"Update to 1.2.3: click {MENU_MARK}"
    assert app.UPDATE_FAILED == f"Update failed: click {MENU_MARK}"
    mac = (app.MOVE_TO_APPLICATIONS, app.ALLOW_UPDATES)
    for text in (app.LOOKING, app.update_notice("1.2.3"), app.UPDATE_FAILED, *mac):
        assert "right" not in text.lower()


class _FakeTray(QObject):
    """Stands in for QSystemTrayIcon, which needs a real notification area."""

    made: ClassVar[list["_FakeTray"]] = []
    activated = Signal(object)  # a QSystemTrayIcon.ActivationReason

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self._icon, self.shown = icon, False
        self._tip = self._menu = None
        _FakeTray.made.append(self)

    def icon(self):
        return self._icon

    def setToolTip(self, tip):
        self._tip = tip

    def toolTip(self):
        return self._tip

    def setContextMenu(self, menu):
        self._menu = menu

    def contextMenu(self):
        return self._menu

    def show(self):
        self.shown = True


@pytest.fixture
def fake_tray():
    _FakeTray.made = []
    return _FakeTray


def test_the_tray_shows_the_app_icon_and_name(qt_box, fake_tray):
    tray = app.make_tray(qt_box, app.ICON, available=True, tray_cls=fake_tray)
    assert tray is fake_tray.made[0] and tray.shown
    assert tray.toolTip() == "MapleLens"
    assert not tray.icon().isNull()
    assert tray.parent() is qt_box  # lives as long as the box


def test_the_tray_menu_is_the_box_menu_with_items_added_later(qt_box, fake_tray):
    tray = app.make_tray(qt_box, app.ICON, available=True, tray_cls=fake_tray)
    qt_box.add_menu_item("Update to 0.2.0…", lambda: None, at=0)  # the update check, later
    menu = tray.contextMenu()
    menu.aboutToShow.emit()  # what Qt does as the menu opens
    assert menu.actions() == qt_box.actions()
    assert [a.text() for a in menu.actions()] == ["Update to 0.2.0…", "Quit MapleLens"]


def test_no_tray_where_there_is_none(qt_box, fake_tray):
    assert app.make_tray(qt_box, app.ICON, available=False, tray_cls=fake_tray) is None
    assert fake_tray.made == []


def test_no_tray_on_linux(monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    assert not app.tray_available()


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("there", [True, False])
def test_the_tray_needs_a_notification_area_or_menu_bar(monkeypatch, platform, there):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: there))
    assert app.tray_available() is there


@pytest.fixture
def hide(qt_box, fake_tray):
    """The box and a Layer, both shown, with a tray and its Hide item."""
    from maplelens.overlay import Layer

    layer = Layer()
    qt_box.show()
    layer.show()
    tray = app.make_tray(qt_box, app.ICON, available=True, tray_cls=fake_tray)
    return qt_box, layer, tray, app.add_hide(qt_box, layer, tray)


def test_the_hide_item_sits_just_before_quit(hide):
    box, *_ = hide
    assert _menu(box) == ["Hide MapleLens", "Quit MapleLens"]


def test_hide_hides_the_box_and_the_layer_and_show_brings_the_box_back(hide):
    box, layer, _, shown = hide
    shown.toggle()
    assert not shown.on
    assert not box.isVisible() and not layer.isVisible()
    assert _menu(box)[0] == "Show MapleLens"
    shown.toggle()
    assert shown.on and box.isVisible()  # the Layer follows on the next tick
    assert _menu(box)[0] == "Hide MapleLens"


def test_the_hide_item_toggles(hide):
    box, _, _, shown = hide
    box.actions()[0].trigger()
    assert not shown.on and not box.isVisible()


def test_a_left_click_on_the_tray_toggles_and_other_clicks_dont(hide):
    from PySide6.QtWidgets import QSystemTrayIcon

    box, _, tray, shown = hide
    tray.activated.emit(QSystemTrayIcon.Trigger)
    assert not shown.on and not box.isVisible()
    for other in (QSystemTrayIcon.Context, QSystemTrayIcon.DoubleClick):
        tray.activated.emit(other)  # a double click comes after its first click's Trigger
    assert not shown.on
    tray.activated.emit(QSystemTrayIcon.Trigger)
    assert shown.on and box.isVisible()


def test_with_no_tray_there_is_no_hide_item(qt_box):
    from maplelens.overlay import Layer

    shown = app.add_hide(qt_box, Layer(), None)
    assert shown.on
    assert _menu(qt_box) == ["Quit MapleLens"]


def test_on_the_mac_a_tray_click_opens_the_menu_and_doesnt_toggle(qt_box, fake_tray):
    from PySide6.QtWidgets import QSystemTrayIcon

    from maplelens.overlay import Layer

    tray = app.make_tray(qt_box, app.ICON, available=True, tray_cls=fake_tray)
    shown = app.add_hide(qt_box, Layer(), tray, click=False)
    assert _menu(qt_box) == ["Hide MapleLens", "Quit MapleLens"]  # the way back
    tray.activated.emit(QSystemTrayIcon.Trigger)
    assert shown.on


def test_on_the_mac_maplelens_leaves_the_dock(monkeypatch):
    calls = []  # never the real activation policy
    fake = types.SimpleNamespace(make_accessory=lambda: calls.append("accessory"))
    monkeypatch.setitem(sys.modules, "maplelens.overlay_mac", fake)
    monkeypatch.setattr(maplelens, "overlay_mac", fake, raising=False)
    app.hide_from_dock()
    assert calls == ["accessory"]


class _Recorder:
    """A tool that keeps what each update got."""

    running = False
    dot = False
    open = False

    def __init__(self):
        self.updates = []

    def update(self, reading, rect, now):
        self.updates.append((reading, rect, now))


@pytest.fixture
def game_found(monkeypatch):
    """A tick that finds the game, grabs a frame and reads `READING` from it."""
    rect = (0, 0, 800, 600)
    monkeypatch.setattr(app, "find_game", lambda settings, save: 42)
    monkeypatch.setattr(app.capture, "client_rect", lambda hwnd: rect)
    monkeypatch.setattr(app.capture, "grab", lambda hwnd, r: np.full((600, 800, 3), 60, np.uint8))
    monkeypatch.setattr(reader, "read_all", lambda frame, now, due=None: READING)
    return rect


READING = Reading(5.0, None, None, None, None)  # nothing on screen: found() is empty


def _tick(box, layer, shown, updates=None):
    from PySide6.QtWidgets import QLabel

    for title in ("EXP", "Path", "Class"):  # the tick sets the Path and Class tabs' dots
        box.add_tab(title, QLabel())
    exp, path = _Recorder(), _Recorder()
    tick = app.Tick(
        settings={"window_title": "MapleStory"},
        save=lambda: None,
        box=box,
        layer=layer,
        exp=exp,
        path=path,
        cls=_Recorder(),
        quest=_Recorder(),
        focus=_Quiet(),
        updates=updates,
        seen=set(),
        shown=shown,
    )
    return tick, exp


def test_a_tick_while_hidden_keeps_both_hidden_and_the_tools_running(hide, game_found):
    box, layer, _, shown = hide
    shown.toggle()
    tick, exp = _tick(box, layer, shown)
    tick.run(5.0)
    assert not box.isVisible() and not layer.isVisible()
    assert exp.updates == [(READING, game_found, 5.0)]  # still recording
    shown.toggle()
    tick.run(6.0)
    assert box.isVisible() and layer.isVisible()


def test_a_tick_with_the_game_shows_the_layer(hide, game_found):
    box, layer, _, shown = hide
    layer.hide()
    tick, exp = _tick(box, layer, shown)
    tick.run(5.0)
    assert layer.isVisible() and box.isVisible()
    assert exp.updates == [(READING, game_found, 5.0)]


def test_a_tick_leaves_fullscreen_black_bars_out(hide, game_found, monkeypatch):
    box, layer, _, shown = hide
    frame = np.zeros((600, 800, 3), np.uint8)
    frame[75:525] = 60  # the 16:9 picture, between two 75-row bars
    monkeypatch.setattr(app.capture, "grab", lambda hwnd, r: frame)
    seen = []
    monkeypatch.setattr(
        reader, "read_all", lambda f, now, due=None: seen.append(f.shape) or READING
    )
    tick, exp = _tick(box, layer, shown)
    tick.run(5.0)
    assert seen == [(450, 800, 3)]
    assert exp.updates == [(READING, (0, 75, 800, 450), 5.0)]


def test_a_tick_without_an_answer_leaves_the_tools_alone(hide, game_found):
    box, layer, _, shown = hide
    layer.hide()
    tick, exp = _tick(box, layer, shown)
    tick.reader = types.SimpleNamespace(ask=lambda job: None, take=lambda: None)
    tick.run(5.0)
    assert exp.updates == []
    assert layer.isVisible()


def test_a_tick_searches_a_closed_window_on_its_turn(hide, game_found, monkeypatch):
    box, layer, _, shown = hide
    dues = []

    def read_all(f, now, due=None):
        dues.append(due)
        tracker = "a tracker" if len(dues) > 2 and "tracker" in due else None  # open from tick 2
        return Reading(now, None, None, None, None, tracker=tracker)

    monkeypatch.setattr(reader, "read_all", read_all)
    tick, _ = _tick(box, layer, shown)
    for i in range(7):
        tick.run(float(i))
    assert [i for i, d in enumerate(dues) if "tracker" in d] == [3, 4, 5, 6]  # its turn, then seen
    assert [i for i, d in enumerate(dues) if "stats" in d] == [0, 4]


def test_a_window_found_in_a_lagging_answer_is_due_on_the_next_job(hide, game_found):
    box, layer, _, shown = hide
    tick, _ = _tick(box, layer, shown)
    jobs = []

    class Lagging:  # like ProcessReader: an answer is there on the next tick, not this one
        inflight, fresh = None, False

        def ask(self, job):
            jobs.append(job)
            self.inflight = (game_found, Reading(5.0, None, None, None, None, stats="s"))
            self.fresh = True

        def take(self):
            if self.fresh:
                self.fresh = False
                return None
            answer, self.inflight = self.inflight, None
            return answer

    tick.reader = Lagging()
    for i in range(3):
        tick.run(float(i))
    assert "stats" in jobs[0][3]  # its search turn (turn 0)
    assert "stats" in jobs[1][3]  # found in the answer taken first thing on tick 1
    assert "stats" in jobs[2][3]


def test_a_tick_without_the_game_hides_the_layer_and_says_looking(hide, monkeypatch):
    box, layer, _, shown = hide
    monkeypatch.setattr(app, "find_game", lambda settings, save: None)
    tick, exp = _tick(box, layer, shown)
    tick.run(5.0)
    assert not layer.isVisible()
    assert box._status.text() == app.LOOKING
    assert exp.updates == [(None, None, 5.0)]


def test_a_tick_without_screen_recording_asks_for_it_and_never_looks(hide, game_found, monkeypatch):
    box, layer, _, shown = hide
    monkeypatch.setattr(app.capture, "has_access", lambda: False)
    monkeypatch.setattr(app, "find_game", lambda settings, save: pytest.fail("looked"))
    tick, exp = _tick(box, layer, shown)
    tick.hwnd = 42  # found before the permission was revoked
    tick.run(5.0)
    assert not layer.isVisible()
    assert box._status.text() == app.NEEDS_SCREEN_RECORDING
    assert exp.updates == [(None, None, 5.0)]
    assert tick.hwnd is None


class _Gate:
    """A fetch that waits until opened, so a check can be caught running."""

    def __init__(self, reply):
        self.reply, self.open = reply, threading.Event()

    def __call__(self):
        self.open.wait(5)
        return self.reply


def test_update_status_while_a_check_runs_then_with_a_newer_release(make_check):
    fetch = _Gate(NEWER)
    check = make_check(fetch)
    check.poll(5.0)  # the first check starts
    assert check.status() == "Checking…"
    fetch.open.set()
    check._thread.join(5)
    check.poll(5.0)
    assert check.status() == "Update to 0.2.0 available"


def test_update_status_keeps_a_dismissed_update(make_check):
    settings = {"update_dismissed": "0.2.0"}  # its line is hidden, the update isn't
    check = make_check(_Fetch(NEWER), settings)
    _run(check, 5.0)
    assert check.status() == "Update to 0.2.0 available"


def test_update_status_with_nothing_newer(make_check):
    check = make_check(_Fetch(_latest("0.1.0")))
    _run(check, 5.0)
    assert check.status() == "Up to date"


def test_update_status_after_a_failed_check(make_check, log, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    check = make_check(_Fetch(error=OSError("offline")))
    _run(check, 5.0)
    assert check.status() == "Couldn't check"


def test_update_status_before_the_first_check(make_check):
    assert make_check(_Fetch(NEWER)).status() == "Not checked yet"


def test_update_status_with_automatic_checks_off(make_check):
    settings = {"update_check": False, "update_dismissed": None}
    check = make_check(_Fetch(_latest("0.1.0")), settings)
    _run(check, 5.0)  # off: no check starts
    assert check.status() == "Automatic checks off"
    check.check_now()
    _run(check, 6.0)
    assert check.status() == "Up to date"  # a check since starting answers instead


def test_about_line_from_source_and_with_an_update(make_check):
    assert app.about_line(None) == ("Running from source", False)
    check = make_check(_Fetch(NEWER))
    assert app.about_line(check) == ("Not checked yet", False)
    _run(check, 5.0)
    assert app.about_line(check) == ("Update to 0.2.0 available", True)


def test_about_sits_just_before_quit(qt_box):
    app.add_about(qt_box, None)
    assert _menu(qt_box) == ["About MapleLens", "Quit MapleLens"]


def test_about_comes_after_hide_with_a_tray(hide):
    box, *_ = hide
    app.add_about(box, None)
    assert _menu(box) == ["Hide MapleLens", "About MapleLens", "Quit MapleLens"]


def test_the_about_item_opens_the_view_with_the_version_and_the_repo(qt_box, monkeypatch):
    monkeypatch.setattr(app, "version", lambda name: "0.1.0")
    monkeypatch.setattr(app.update, "REPO", "someone/fork")  # MAPLELENS_UPDATE_REPO
    opened = []
    monkeypatch.setattr(qt_box, "show_about", lambda *a, **kw: opened.append((a, kw)))
    app.add_about(qt_box, None)
    qt_box.actions()[0].trigger()
    url = "https://github.com/or-keren/maplelens"  # not the fork the update check asks
    assert opened == [(("0.1.0", "Running from source", url), {"accent": False})]


def test_the_about_line_follows_a_check_on_each_tick(qt_box, make_check, monkeypatch):
    from maplelens.overlay import Layer

    monkeypatch.setattr(app, "find_game", lambda settings, save: None)
    monkeypatch.setattr(app, "version", lambda name: "0.1.0")
    fetch = _Gate(NEWER)
    check = make_check(fetch)
    app.add_about(qt_box, check)
    qt_box.actions()[-2].trigger()  # About, just before Quit
    assert qt_box._about_updates.text() == "Not checked yet"
    layer = Layer()
    tick, _ = _tick(qt_box, layer, app.Shown(qt_box, layer), updates=check)
    tick.run(5.0)  # the first check starts
    assert qt_box._about_updates.text() == "Checking…"
    fetch.open.set()
    check._thread.join(5)
    tick.run(6.0)
    assert qt_box._about_updates.text() == "Update to 0.2.0 available"
    assert qt_box.about_open  # still open: the line changed in place


def test_screen_status_asks_for_the_permission_before_looking():
    assert app.screen_status(False, None) == app.NEEDS_SCREEN_RECORDING
    assert app.screen_status(False, 42) == app.NEEDS_SCREEN_RECORDING  # revoked mid-run
    assert app.screen_status(True, None) == app.LOOKING
    assert app.screen_status(True, 42) is None


def test_permission_line_fits_the_box(qt_box):
    qt_box.set_status(app.NEEDS_SCREEN_RECORDING)
    assert qt_box._status.sizeHint().width() <= overlay.TAB_W
    assert "right" not in app.NEEDS_SCREEN_RECORDING.lower()  # the ••• is the way in


@pytest.fixture
def no_prompt(monkeypatch):
    """Screen Recording already allowed: the real calls could show the system prompt."""
    monkeypatch.setattr(app.capture, "has_access", lambda: True)
    monkeypatch.setattr(app.capture, "request_access", lambda: pytest.fail("prompted"))


def test_the_mac_box_has_the_screen_recording_item(qt_box, monkeypatch, no_prompt):
    monkeypatch.setattr(sys, "platform", "darwin")
    opened = []
    monkeypatch.setattr(app.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    app.setup_screen_recording(qt_box)
    assert _menu(qt_box) == ["Open Screen Recording settings…", "Quit MapleLens"]
    qt_box.actions()[0].trigger()
    assert opened == [app.SCREEN_RECORDING_URL]


def test_windows_box_has_no_screen_recording_item(qt_box, monkeypatch, no_prompt):
    monkeypatch.setattr(sys, "platform", "win32")
    app.setup_screen_recording(qt_box)
    assert _menu(qt_box) == ["Quit MapleLens"]


def test_main_no_longer_exits_without_screen_recording(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    real = QApplication.instance() or QApplication([])

    class Proxy:  # the one QApplication a process allows, with exec() ending at once
        def __getattr__(self, name):
            return getattr(real, name)

        def exec(self):
            return 0

    fake = lambda argv: Proxy()  # noqa: E731
    fake.quit = QApplication.quit
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(sys, "argv", ["maplelens"])
    monkeypatch.setattr(app, "QApplication", fake)
    monkeypatch.setattr(app, "mark_running", lambda: True)
    monkeypatch.setattr(app, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app, "update_check", lambda *a, **k: None)
    monkeypatch.setattr(app, "_log_path", None)
    requests = []
    monkeypatch.setattr(app.capture, "has_access", lambda: False)
    monkeypatch.setattr(app.capture, "request_access", lambda: requests.append(1))
    assert app.main() == 0
    assert requests == [1]


class _BuildTool:
    def __init__(self):
        self.names, self.name, self.picked = ["LUK", "Sindit"], "LUK", []
        self.builds_changed = None

    def build_names(self):
        return self.names

    def build_name(self):
        return self.name

    def pick_build(self, name):
        self.picked.append(name)


def test_build_menu_follows_the_class_tool(qt_box):
    tool = _BuildTool()
    action = app.add_build_menu(qt_box, tool)
    assert not action.isVisible()
    assert [a.text() for a in qt_box.actions()][-1] == "Quit MapleLens"  # above Quit
    tool.builds_changed()
    assert action.isVisible() and action.text() == "Build: LUK"
    tool.name = "Sindit"
    tool.builds_changed()
    assert action.text() == "Build: Sindit"
    tool.names = []  # a job with no plan, or one build
    tool.builds_changed()
    assert not action.isVisible()


def test_build_menu_lists_and_picks(qt_box):
    tool = _BuildTool()
    action = app.add_build_menu(qt_box, tool)
    tool.builds_changed()
    menu = action.menu()
    menu.aboutToShow.emit()
    assert [a.text() for a in menu.actions()] == ["LUK", "Sindit"]
    menu.actions()[1].trigger()
    assert tool.picked == ["Sindit"]


def test_make_reader_uses_a_helper_on_the_mac():
    assert isinstance(app.make_reader("darwin"), reader.ProcessReader)
    assert isinstance(app.make_reader("win32"), reader.InlineReader)


@pytest.mark.skipif(sys.platform != "darwin", reason="the helper process is the Mac's")
def test_self_check_fails_when_the_helper_never_answers(monkeypatch, no_cache):
    class Silent:
        def __init__(self, work=None):
            pass

        def ask(self, job):
            pass

        def take(self):
            return None

        def close(self):
            pass

    monkeypatch.setattr(app, "ProcessReader", Silent)
    monkeypatch.setattr(app, "HELPER_CHECK_S", 0.2)
    assert app.self_check() == 1


def test_a_loading_screen_leaves_the_box_where_the_bars_put_it(hide, game_found, monkeypatch):
    # fullscreen on a 16:10 Mac: bars above and below; a map change's black frame has none
    box, layer, _, shown = hide
    black = np.zeros((600, 800, 3), np.uint8)
    barred = black.copy()
    barred[75:525] = 60  # 800x450, 16:9
    frames = [barred, black, barred]
    monkeypatch.setattr(app.capture, "grab", lambda hwnd, r: frames.pop(0))
    tick, _ = _tick(box, layer, shown)
    tick.run(1.0)
    at = box.pos()
    tick.run(2.0)  # the loading screen
    assert box.pos() == at
    tick.reader = types.SimpleNamespace(ask=lambda job: None, take=lambda: None)
    tick.run(3.0)  # an answer still on its way
    assert box.pos() == at


def test_a_tick_skips_the_tools_turned_off(hide, game_found):
    box, layer, _, shown = hide
    tick, exp = _tick(box, layer, shown)
    tick.settings.update(exp_on=False, class_on=False)
    tick.run(5.0)
    assert exp.updates == [] and tick.cls.updates == []
    assert tick.path.updates == [(READING, game_found, 5.0)]
    assert tick.quest.updates == [(READING, game_found, 5.0)]
    tick.settings["exp_on"] = True
    tick.run(6.0)
    assert exp.updates == [(READING, game_found, 6.0)]


def test_a_tick_doesnt_read_an_off_tools_windows(hide, game_found, monkeypatch):
    box, layer, _, shown = hide
    dues = []
    monkeypatch.setattr(reader, "read_all", lambda f, now, due=None: dues.append(due) or READING)
    tick, _ = _tick(box, layer, shown)
    tick.settings.update(class_on=False, quests_on=False)
    for i in range(8):  # two turns of every closed window
        tick.run(float(i))
    assert not any({"stats", "skills", "quest", "tracker"} & set(d) for d in dues)


def test_quests_off_never_switches_the_box_to_quests():
    box = _FocusBox(1)
    f = app.QuestFocus(box, 3)
    for _ in range(3):  # a quest window open in the game; Quests is off, so OFF stands in
        app.update_tools(box, _Quiet(), _Quiet(), _Quiet(), app.OFF, f, "r", None, 0.0, set())
    assert box.selects == []


class _Stops(_Quiet):
    def __init__(self):
        self.calls = []
        self.can_go = True
        self.arrow = types.SimpleNamespace(hide=lambda: self.calls.append("arrow hidden"))

    def set_can_go(self, on):
        self.can_go = on

    def stop(self, *now):
        self.calls.append(("stop", *now))

    def hide_marks(self):
        self.calls.append("marks hidden")


@pytest.fixture
def switches(qt_box):
    from PySide6.QtWidgets import QLabel

    from maplelens.settings_window import SettingsWindow, ToolSection

    pages = []
    for title in ("EXP", "Path", "Class", "Quests"):
        pages.append(QLabel(title))
        qt_box.add_tab(title, pages[-1])
    footer = QLabel("pin")
    qt_box.add_footer(footer, 0)
    qt_box.set_footer_shown(True)
    sections = {t: QLabel(t) for t in ("Path", "Class")}
    window = SettingsWindow([ToolSection(t, True, w) for t, w in sections.items()])
    settings, saves = {}, []
    exp, path, cls, quest = _Stops(), _Stops(), _Stops(), _Stops()
    save = lambda: saves.append(dict(settings))  # noqa: E731
    sw = app.ToolSwitches(settings, save, qt_box, exp, path, cls, quest)
    sw.apply(window, ["EXP", "Path", "Class", "Quests"])
    return types.SimpleNamespace(
        sw=sw, box=qt_box, settings=settings, saves=saves, exp=exp, path=path, cls=cls,
        quest=quest, sections=sections, footer=footer,
    )  # fmt: skip


def test_turning_path_off_ends_the_trip_and_greys_its_section(switches):
    s = switches
    s.box.select(1)
    s.sw.set(1, False, 9.0)
    assert s.settings["path_on"] is False and s.saves[-1]["path_on"] is False
    assert s.path.calls == [("stop",), "arrow hidden"]
    assert not s.box._tab_buttons[1].isVisibleTo(s.box) and s.box.current == 0
    assert not s.sections["Path"].isEnabled()
    s.sw.set(1, True, 10.0)
    assert s.box._tab_buttons[1].isVisibleTo(s.box) and s.sections["Path"].isEnabled()


def test_turning_exp_off_saves_it_and_hides_the_pinned_line(switches):
    s = switches
    s.box.select(2)
    assert s.footer.isVisibleTo(s.box)
    s.sw.set(0, False, 9.0)
    assert s.exp.calls == [("stop", 9.0)]
    assert not s.footer.isVisibleTo(s.box)
    s.sw.set(0, True, 10.0)
    assert s.footer.isVisibleTo(s.box)  # pin_exp is still on


def test_path_off_makes_class_and_quests_rows_inert(switches):
    s = switches
    assert s.cls.can_go and s.quest.can_go
    s.sw.set(1, False, 9.0)
    assert not s.cls.can_go and not s.quest.can_go
    s.sw.set(1, True, 10.0)
    assert s.cls.can_go and s.quest.can_go


def test_turning_class_off_hides_its_marks(switches):
    switches.sw.set(2, False, 9.0)
    assert switches.cls.calls == ["marks hidden"]


def test_tools_saved_off_start_hidden(qt_box):
    from PySide6.QtWidgets import QLabel

    for title in ("EXP", "Path", "Class", "Quests"):
        qt_box.add_tab(title, QLabel(title))
    settings = {"quests_on": False, "path_on": False}
    cls, quest = _Stops(), _Stops()
    sw = app.ToolSwitches(settings, lambda: None, qt_box, _Stops(), _Stops(), cls, quest)
    sw.apply(None, [])
    assert not qt_box._tab_buttons[3].isVisibleTo(qt_box)
    assert qt_box._tab_buttons[2].isVisibleTo(qt_box)
    assert not cls.can_go and not quest.can_go  # Path saved off: no trips from the start


def test_tool_sections_follow_the_tabs_with_each_tools_own_settings(qt_box):
    from PySide6.QtWidgets import QLabel

    class Tool:
        def __init__(self, title, has):
            self.title = title
            if has:
                self.settings_section = lambda: QLabel(title)

    tools = [Tool("EXP", False), Tool("Path", True), Tool("Class", True), Tool("Quests", False)]
    got = app.tool_sections(tools, {"class_on": False})
    assert [(t.title, t.on, t.body is not None) for t in got] == [
        ("EXP", True, False),
        ("Path", True, True),
        ("Class", False, True),
        ("Quests", True, False),
    ]
