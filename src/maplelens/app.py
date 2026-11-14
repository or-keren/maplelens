"""MapleLens entry point: watch the game window and run the tools."""

import contextlib
import json
import multiprocessing
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QImage
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import maplelens
from maplelens import capture, update, update_mac
from maplelens.overlay import ABOUT, MENU_MARK, Box, Layer
from maplelens.reader import InlineReader, ProcessReader, Rect
from maplelens.readers import due, found, glyphs, ocr, quest_window
from maplelens.settings_window import GeneralSection, SettingsWindow, ToolSection
from maplelens.store import data_dir, load_settings, save_settings
from maplelens.tools.class_helper import data as class_data
from maplelens.tools.class_helper.ui import ClassHelperTool
from maplelens.tools.exp_meter.history import best_rate, open_db
from maplelens.tools.exp_meter.ui import ExpMeterTool
from maplelens.tools.path_arrow import maps
from maplelens.tools.path_arrow.ui import PathArrowTool
from maplelens.tools.quest_helper import data as quest_data
from maplelens.tools.quest_helper.ui import QuestHelperTool

_TICK_MS = 500
APP_NAME = "MapleLens"  # also the title of our own windows, which the picker leaves out
# The app icon, as package data: the exe and Setup are built with it, and the app loads it.
# Found from the package, not from this file: the frozen app runs this file as a script
# outside the package folder.
ICON = Path(maplelens.__file__).parent / "data" / "icon.ico"
# The game client's window title. With no title saved, only a window with exactly this
# title counts, so a browser tab like "MapleStory wiki - Chrome" never does.
DEFAULT_TITLE = "MapleStory"
_log_path: Path | None = None  # where report_once also writes; set by start_log
LOOKING = f"Looking for {DEFAULT_TITLE}…"  # the box's ••• beside it has the window picker
# Allow it (the menu item opens the page), then reopen: macOS grants a running app nothing.
NEEDS_SCREEN_RECORDING = f"Allow, then reopen: click {MENU_MARK}"
SCREEN_RECORDING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
)
# Held while MapleLens runs. The Windows installer and uninstaller look for it (AppMutex in
# packaging/windows/maplelens.iss) and ask the player to close MapleLens first.
APP_MUTEX = "MapleLensRunning"
# Tells Setup the app started it to update itself: Setup waits for MapleLens to exit instead
# of asking to close it, then starts the new version (IsUpdateRun in maplelens.iss).
UPDATE_FLAG = "/MAPLELENSUPDATE"
_ALREADY_EXISTS = 183  # Windows' error code when the named mutex was already there


def build_box(
    settings: dict,
    save: Callable[[], None],
    tools: list,
    pick: Callable[[str], None] | None = None,
) -> Box:
    """The one overlay box: a tab per tool; the window picker and Quit in its menu."""
    box = Box("exp_meter", settings, save)
    for tool in tools:
        box.add_tab(tool.title, tool.tab)
        box.on_tab_w(tool.set_tab_w)
    if pick:
        box.add_submenu("Pick game window…", game_choices, pick)
    # quit() runs aboutToQuit, where main() saves through shutdown()
    box.add_menu_item("Quit MapleLens", QApplication.quit)
    box.show()
    return box


def screen_status(has_access: bool, hwnd) -> str | None:
    """The box's status line: the permission first, then the game search; None when fine."""
    if not has_access:
        return NEEDS_SCREEN_RECORDING
    return None if hwnd else LOOKING


def setup_screen_recording(box: Box) -> None:
    """Show the system's Screen Recording prompt if it's needed (the box says so after);
    on the Mac add the menu item that opens its settings page, above Quit."""
    if not capture.has_access():
        capture.request_access()
    if sys.platform == "darwin":
        box.add_menu_item(
            "Open Screen Recording settings…",
            lambda: QDesktopServices.openUrl(QUrl(SCREEN_RECORDING_URL)),
            at=-1,
        )


def find_game(settings: dict, save: Callable[[], None]) -> int | None:
    """The game window, or None.

    A saved title matches exactly, else as a substring. With none saved, a window titled
    exactly DEFAULT_TITLE counts, and its title is saved the first time one turns up.
    """
    if settings["window_title"]:
        return capture.find_window(settings["window_title"])
    found = capture.find_window(DEFAULT_TITLE, exact=True)
    if found is not None:
        settings["window_title"] = DEFAULT_TITLE
        save()
    return found


def game_choices() -> list[str]:
    """Window titles to offer in the picker: every window but MapleLens's own."""
    return [t for t in capture.window_titles() if t != APP_NAME]


def choose_window(settings: dict, save: Callable[[], None], title: str) -> None:
    """Make `title` the game window's title from now on."""
    settings["window_title"] = title
    save()


def start_log(path: Path) -> None:
    """Send report_once to `path` too, emptied now so it holds this run only."""
    global _log_path  # noqa: PLW0603 - one log per process, set once at startup
    path.write_text("", encoding="utf-8")
    _log_path = path


def report_once(e: Exception, seen: set[str]) -> None:
    """Log a traceback the first time each distinct error turns up.

    To the log file, and to stderr when there is one (a windowed exe has none).
    """
    key = f"{type(e).__name__}: {e}"
    if key in seen:
        return
    seen.add(key)
    text = "".join(traceback.format_exception(e))  # also for one raised on another thread
    if sys.stderr is not None:
        sys.stderr.write(text)
    if _log_path is not None:
        with _log_path.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}")


def poll_updates(updates: "UpdateCheck | None", now: float, seen: set[str]) -> None:
    """The tick's update step; an error in it (a save failing) is logged, not raised."""
    if updates is None:
        return
    try:
        updates.poll(now)
    except Exception as e:
        report_once(e, seen)


class QuestFocus:
    """Switch the box to the Quests tab while a quest window is open in the game.

    The state flips only after two updates in a row agree. On close the box goes back to
    the tab it came from, unless the player pressed in the box since.
    """

    def __init__(self, box: Box, index: int):
        self._box, self._index = box, index
        self._open = False  # the settled state
        self._last = False  # the latest update
        self._back: int | None = None
        self._touches = 0

    def update(self, open_: bool) -> None:
        agreed = open_ == self._last
        self._last = open_
        if not agreed or open_ == self._open:
            return
        self._open = open_
        box = self._box
        if open_:
            if box.current != self._index:
                self._back, self._touches = box.current, box.touches
                box.select(self._index)
        else:
            if self._back is not None and box.touches == self._touches:
                box.select(self._back)
            self._back = None


def update_tools(  # noqa: PLR0913, PLR0917 - one per tool plus the frame; a bundle would hide them
    box: Box, exp, path, cls, quest, focus, reading, rect, now: float, seen: set[str]
) -> None:
    """Feed the tools the same reading; the Path tab shows a dot while a trip runs.

    Each tool runs on its own: one raising doesn't stop the others.
    """
    try:
        exp.update(reading, rect, now)
    except Exception as e:
        report_once(e, seen)
    try:
        path.update(reading, rect, now)
    except Exception as e:
        report_once(e, seen)
        path.arrow.hide()  # never leave it pointing from a stale spot
    try:
        cls.update(reading, rect, now)
    except Exception as e:
        report_once(e, seen)
        cls.hide_marks()  # never leave marks from a tick that failed
    try:
        quest.update(reading, rect, now)
    except Exception as e:
        report_once(e, seen)  # it draws nothing on the layer: nothing to hide
    focus.update(quest.open)
    box.set_tab_dot(1, path.running)  # the tabs' indexes in build_box's tools list
    box.set_tab_dot(2, cls.dot)


# Each tool's on/off setting, in the tabs' order (build_box's list): index = tab index
TOOL_KEYS = ("exp_on", "path_on", "class_on", "quests_on")
# The game windows only one tool reads: left unread while it's off
_WINDOWS = {
    "class_on": frozenset({"stats", "skills"}),
    "quests_on": frozenset({"quest", "tracker"}),
}


class _Off:
    """A tool turned off, in its place at the tick: nothing runs, nothing shows."""

    running = dot = open = False

    def update(self, *_) -> None:
        pass


OFF = _Off()


def tool_on(settings: dict, key: str) -> bool:
    return settings.get(key, True)


def unread(settings: dict) -> frozenset[str]:
    """The game windows of the tools turned off, which the reader isn't asked for."""
    off = [parts for key, parts in _WINDOWS.items() if not tool_on(settings, key)]
    return frozenset().union(*off)


def tool_sections(tools: list, settings: dict) -> list[ToolSection]:
    """Each tool's card for the Settings window, in the tabs' order: its switch, and its own
    settings when it has any."""
    return [
        ToolSection(
            t.title,
            tool_on(settings, key),
            t.settings_section() if hasattr(t, "settings_section") else None,
        )
        for t, key in zip(tools, TOOL_KEYS, strict=True)
    ]


class ToolSwitches:
    """Turning a tool off and on in Settings, live: its tab, what it draws, its section.

    The tick passes OFF in an off tool's place (Tick.run), so its update doesn't run.
    """

    def __init__(  # noqa: PLR0913, PLR0917 - the box, the settings and each tool that stops
        self, settings: dict, save: Callable[[], None], box: Box, exp, path, cls, quest
    ):
        self._settings, self._save, self._box = settings, save, box
        self._exp, self._path, self._cls, self._quest = exp, path, cls, quest
        self._window: SettingsWindow | None = None  # its sections grey out with their tools
        self._titles: list[str] = []

    def apply(self, window: SettingsWindow | None, titles: list[str]) -> None:
        """At start: hide the tabs, and grey the sections (headed `titles`, in the tabs'
        order), of the tools saved off."""
        self._window, self._titles = window, titles
        for i, key in enumerate(TOOL_KEYS):
            if not tool_on(self._settings, key):
                self._show(i, False)
        self._tell_can_go()

    def set(self, index: int, on: bool, now: float) -> None:
        key = TOOL_KEYS[index]
        if tool_on(self._settings, key) == on:
            return
        self._settings[key] = on
        if not on:
            self._stop(key, now)
        self._show(index, on)
        if key == "path_on":
            self._tell_can_go()
        self._save()

    def _tell_can_go(self) -> None:
        """Class's and Quests' rows start trips on Path: only while Path is on."""
        on = tool_on(self._settings, "path_on")
        self._cls.set_can_go(on)
        self._quest.set_can_go(on)

    def _stop(self, key: str, now: float) -> None:
        if key == "exp_on":
            self._exp.stop(now)  # saved, as on quit
        elif key == "path_on":
            self._path.stop()
            self._path.arrow.hide()
        elif key == "class_on":
            self._cls.hide_marks()

    def _show(self, index: int, on: bool) -> None:
        self._box.set_tab_shown(index, on)
        if self._window is not None and index < len(self._titles):
            self._window.set_section_enabled(self._titles[index], on)


def quest_go(path_tool, select):
    """The Quests tab's go: if no trip starts, show the Path tab, which says why."""

    def go(map_id: str, at=None, label=None) -> None:
        path_tool.go(map_id, at, label)
        if not path_tool.running:
            select(1)

    return go


HELPER_CHECK_S = 20.0  # how long the build's self-check waits for the helper process


def make_reader(platform: str) -> InlineReader | ProcessReader:
    """macOS slows this app while the game is in front; a child process isn't slowed."""
    return ProcessReader() if platform == "darwin" else InlineReader()


def _helper_answers() -> bool:
    """True if a helper process starts and answers (a frozen app that can't spawn fails here)."""
    helper = ProcessReader(work=repr)  # never captures the screen
    try:
        helper.ask(0)
        end = time.monotonic() + HELPER_CHECK_S
        while time.monotonic() < end:
            if (got := helper.take()) is not None:
                return not isinstance(got, Exception)
            time.sleep(0.05)
        return False
    finally:
        helper.close()


def self_check() -> int:
    """0 if everything MapleLens ships loads, else 1: the build's smoke test.

    Templates, maps.json, every minimap picture, the icon (which also needs Qt's ico
    image plugin), the OCR engine and the version. The exit code is the answer: the
    frozen app is windowed, so it has no console.
    """
    try:
        glyphs.load_all()
        maps.load()
        class_data.load()
        quest_data.load()
        quest_window.known_quest_names()
        pictures = sorted(maps.PICTURES.glob("*.png"))
        if not pictures or any(maps.picture(p.stem) is None for p in pictures):
            return 1
        if QImage(str(ICON)).isNull():  # missing, or no plugin to decode it
            return 1
        if not version("maplelens"):  # None when its metadata file is missing
            return 1
        if sys.platform == "darwin" and not _helper_answers():
            return 1
    except Exception:
        return 1
    return 0 if ocr.engine() is not None else 1


def mark_running() -> bool:
    """Create APP_MUTEX on Windows, held until MapleLens exits; False if a copy holds it.

    True if it can't be created at all: better a second copy than none. Elsewhere, True.
    """
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW(None, False, APP_MUTEX)  # the handle stays open until exit
    return ctypes.get_last_error() != _ALREADY_EXISTS


def update_cmd(setup: Path) -> list[str]:
    """Setup's command line for an update: Inno's no-prompt flags plus UPDATE_FLAG."""
    return [str(setup), "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NOCANCEL", UPDATE_FLAG]


def install_update(setup: Path) -> None:
    """Hand over to `setup`: start it on its own, then quit the way Quit does.

    Quitting through Qt runs aboutToQuit, which saves the session in progress; Setup
    waits for MapleLens to exit before it replaces anything. If Setup can't start, the
    OSError propagates and MapleLens keeps running.
    """
    subprocess.Popen(
        update_cmd(setup),
        cwd=setup.parent,  # not {app}, the folder Setup replaces
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    QApplication.quit()


def update_notice(new: str) -> str:
    """The box's line for an update; it fits TAB_W up to version 10.10.10."""
    return f"Update to {new}: click {MENU_MARK}"


def downloading_notice(new: str) -> str:
    return f"Downloading {new}…"


UPDATE_FAILED = f"Update failed: click {MENU_MARK}"  # the menu item tries again
UP_TO_DATE = "MapleLens is up to date"  # "Check for updates now" replies
COULDNT_CHECK = "Couldn't check for updates"
MOVE_TO_APPLICATIONS = "Move to Applications to update"  # on the dmg or where it can't write
ALLOW_UPDATES = f"Allow updates: click {MENU_MARK}"  # macOS's App Management blocked the swap
ALLOW_UPDATES_ITEM = "Allow MapleLens to update…"
APP_MANAGEMENT_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AppBundles"
# About's updates line (UpdateCheck.status, about_line)
CHECKING = "Checking…"
CURRENT = "Up to date"
FAILED_CHECK = "Couldn't check"
CHECKS_OFF = "Automatic checks off"
NOT_CHECKED = "Not checked yet"
FROM_SOURCE = "Running from source"  # no update check: uv run maplelens


def update_available(new: str) -> str:
    return f"Update to {new} available"


def _user_agent() -> dict[str, str]:
    return {"User-Agent": f"MapleLens/{version('maplelens')}"}  # nothing about the player


MAC_CAS = "/etc/ssl/cert.pem"  # macOS's own CA list, on every Mac


def _tls(platform: str = sys.platform) -> ssl.SSLContext:
    """The Mac app's bundled OpenSSL looks for CAs in Homebrew's folder, which most Macs
    don't have: there, trust macOS's list instead."""
    return ssl.create_default_context(cafile=MAC_CAS if platform == "darwin" else None)


def fetch_latest(repo: str = update.REPO) -> dict:
    """GitHub's latest release of `repo`, as JSON. Sends only MapleLens's version."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={**_user_agent(), "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=10, context=_tls()) as reply:
        return json.load(reply)


def download_file(url: str, dest: Path) -> None:
    """Save `url` to `dest`. The timeout is per read, so a 60 MB setup can take its time."""
    req = urllib.request.Request(url, headers=_user_agent())
    with urllib.request.urlopen(req, timeout=30, context=_tls()) as reply, dest.open("wb") as f:
        shutil.copyfileobj(reply, f)


def clear_updates(folder: Path) -> None:
    """Delete setups and dmgs left from earlier updates (the Mac helper's result stays).
    One still in use stays until next time."""
    for old in folder.glob("MapleLens-*"):
        with contextlib.suppress(OSError):
            old.unlink()


class UpdateCheck:
    """Asks for the latest release a few seconds after start, then once a day, and
    updates on a click of "Update to X.Y.Z…".

    Requests and the download each run on a thread of their own and only fill a slot;
    poll(), called from the tick on the Qt thread, starts them and acts on what they
    left. A slow or hanging request never delays a tick, and the next one waits for it.
    """

    FIRST_S = 5
    EVERY_S = 24 * 3600
    REPLY_S = 10  # how long "Check for updates now" shows "up to date" or "couldn't check"

    def __init__(  # noqa: PLR0913, PLR0917 - the box, settings and the parts tests swap
        self,
        box: Box,
        settings: dict,
        save: Callable[[], None],
        fetch: Callable[[], dict],
        running: str,
        seen: set[str],
        now: float,
        *,
        folder: Path,
        download: Callable[[str, Path], None] = download_file,
        install: Callable[[Path], None] = install_update,
        platform: str = sys.platform,
        can_install: Callable[[], str | None] = lambda: None,  # a line when this copy can't
    ):
        self._box, self._settings, self._save = box, settings, save
        self._fetch, self._running, self._seen = fetch, running, seen
        self._folder, self._download, self._install = folder, download, install
        self._platform, self._can_install = platform, can_install
        self._now = now  # the last poll's, for a click's reply timer
        self._held = False  # show_result's line stays until it's closed or replaced
        self._due = now + self.FIRST_S
        self._thread: threading.Thread | None = None
        self._result: tuple[dict | None, Exception | None] = (None, None)
        self._download_thread: threading.Thread | None = None
        self._got: tuple[Path | None, Exception | None] = (None, None)
        self._item = None  # the "Update to X.Y.Z…" menu item, once an update is known
        self._manual = False  # the request running answers "Check for updates now"
        self._quiet_at: float | None = None  # when the line showing now hides itself
        self.release: update.Release | None = None
        self._last: str | None = None  # the last check's outcome, for status()

    def poll(self, now: float) -> None:
        self._now = now
        if self._quiet_at is not None and now >= self._quiet_at:
            self._say(None)
        if self._download_thread is not None and not self._download_thread.is_alive():
            self._download_thread = None
            self._hand_over(*self._got)
        if self._thread is not None and not self._thread.is_alive():
            self._thread = None
            reply, error = self._result
            manual, self._manual = self._manual, False
            if error is not None:
                report_once(error, self._seen)
                self._last = FAILED_CHECK
                if manual:
                    self._reply(COULDNT_CHECK, now)
            else:
                self._found(update.parse_latest(reply, self._platform), manual, now)
        automatic = self._settings.get("update_check", True)  # the toggle, read each time
        if self._thread is None and now >= self._due and automatic:
            self._due = now + self.EVERY_S
            self._start()

    def status(self) -> str:
        """About's updates line: what the check is doing, or what it last found."""
        if self._thread is not None:
            return CHECKING
        if self.release is not None:  # dismissed or not: the menu item still updates
            return update_available(self.release.version)
        if self._last is not None:
            return self._last
        return NOT_CHECKED if self._settings.get("update_check", True) else CHECKS_OFF

    def check_now(self) -> None:
        """The "Check for updates now" item: one request whatever the toggle, with a reply."""
        self._manual = True
        if self._thread is None:  # else the request already running gives the reply
            self._start()

    def show_result(self, result: str | None) -> None:
        """What the Mac helper left from the last update: "blocked" asks the player to allow
        updates, anything else says it failed. Logged either way: the helper has no log."""
        if result is None:
            return
        report_once(RuntimeError(f"the last update didn't finish: {result}"), self._seen)
        if result == "blocked":
            self._box.add_menu_item(
                ALLOW_UPDATES_ITEM,
                lambda: QDesktopServices.openUrl(QUrl(APP_MANAGEMENT_URL)),
                at=-1,
            )
            self._say(ALLOW_UPDATES, lambda: self._say(None))
        else:
            self._say(UPDATE_FAILED, lambda: self._say(None))
        self._held = True

    def set_auto(self, on: bool) -> None:
        """The "Check for updates automatically" toggle."""
        self._settings["update_check"] = on
        self._store()

    def _store(self) -> None:
        """Save settings from a click; a failed save (a locked file) is logged, not lost."""
        try:
            self._save()
        except OSError as e:
            report_once(e, self._seen)

    def _start(self) -> None:
        self._thread = threading.Thread(target=self._ask, daemon=True)
        self._thread.start()

    def _ask(self) -> None:  # on the check's own thread: no Qt here
        try:
            self._result = (self._fetch(), None)
        except Exception as e:
            self._result = (None, e)

    def _say(self, text: str | None, on_dismiss=None, *, until: float | None = None) -> None:
        self._box.set_notice(text, on_dismiss)
        self._quiet_at = until
        self._held = False

    def _reply(self, text: str, now: float) -> None:
        if self._download_thread is None:  # the "Downloading…" line stays until it ends
            self._say(text, until=now + self.REPLY_S)

    def _found(self, release: update.Release | None, manual: bool, now: float) -> None:
        if release is None or not update.is_newer(release, self._running):
            self._last = CURRENT
            if manual:
                self._reply(UP_TO_DATE, now)
            return
        self.release = release
        label = f"Update to {release.version}…"
        if self._item is None:
            self._item = self._box.add_menu_item(label, self._update, at=0)
        else:
            self._item.setText(label)
        downloading = self._download_thread is not None  # its line stays until it ends
        asked = manual or self._settings.get("update_dismissed") != release.version
        if not downloading and asked and (manual or not self._held):
            self._say(update_notice(release.version), lambda: self._dismiss(release.version))

    def _dismiss(self, new: str) -> None:
        self._settings["update_dismissed"] = new
        self._store()

    def _update(self) -> None:
        """The menu item's click: download the setup; poll() hands over once it's checked."""
        if self.release is None or self._download_thread is not None:
            return  # a second click while downloading does nothing
        if (line := self._can_install()) is not None:
            self._reply(line, self._now)
            return
        self._say(downloading_notice(self.release.version))
        self._got = (None, None)
        self._download_thread = threading.Thread(
            target=self._get, args=(self.release,), daemon=True
        )
        self._download_thread.start()

    def _get(self, release: update.Release) -> None:  # on the download's own thread: no Qt
        setup = self._folder / update.asset_name(release.version, self._platform)
        part = setup.with_name(setup.name + ".part")  # renamed only once its digest matches
        try:
            if release.digest is None:
                raise ValueError(f"GitHub gave no digest for {setup.name}: it can't be checked")
            self._folder.mkdir(parents=True, exist_ok=True)
            self._download(release.url, part)
            if not update.digest_ok(part, release.digest):
                raise ValueError(f"{setup.name} doesn't match GitHub's digest {release.digest}")
            part.replace(setup)
            self._got = (setup, None)
        except Exception as e:
            with contextlib.suppress(OSError):
                part.unlink(missing_ok=True)
            self._got = (None, e)

    def _hand_over(self, setup: Path | None, error: Exception | None) -> None:
        if setup is not None:
            try:
                self._install(setup)  # quits MapleLens: Setup takes it from here
                return
            except Exception as e:  # Setup didn't start; this version keeps running
                error = e
                with contextlib.suppress(OSError):
                    setup.unlink(missing_ok=True)
        if error is not None:
            report_once(error, self._seen)
        self._say(UPDATE_FAILED)


def update_check(  # noqa: PLR0913, PLR0917 - main's parts, plus the fetch tests swap
    box: Box,
    settings: dict,
    save: Callable[[], None],
    seen: set[str],
    now: float,
    fetch: Callable[[], dict] = fetch_latest,
) -> UpdateCheck | None:
    """An UpdateCheck for the installed app (Windows or Mac), else None. Its controls are in
    Settings' General section (GeneralSection.add_updates).

    Keep the result: Qt holds the controls' links to it weakly. Clears the setups and
    dmgs earlier updates left in the data folder's `updates`; on the Mac also shows what
    the last update's helper left there.
    """
    if not update.can_update(getattr(sys, "frozen", False), sys.platform):
        return None
    folder = data_dir() / "updates"
    clear_updates(folder)
    mac = {}
    if sys.platform == "darwin":
        mac = {
            "install": update_mac.install_update,
            "can_install": lambda: (
                None
                if (b := update_mac.bundle_path(sys.executable)) and update_mac.can_replace(b)
                else MOVE_TO_APPLICATIONS
            ),
        }
    check = UpdateCheck(
        box,
        settings,
        save,
        fetch,
        version("maplelens"),
        seen,
        now,
        folder=folder,
        platform=sys.platform,
        **mac,
    )
    if sys.platform == "darwin":
        check.show_result(update_mac.read_result(folder))
    return check


def tray_available() -> bool:
    """A tray icon: in the notification area on Windows, the menu bar on the Mac.

    Not elsewhere, and with no tray the box's ••• still works.
    """
    return sys.platform in ("win32", "darwin") and QSystemTrayIcon.isSystemTrayAvailable()


def make_tray(
    box: Box, icon: Path, *, available: bool, tray_cls: type = QSystemTrayIcon
) -> QSystemTrayIcon | None:
    """MapleLens's tray icon, shown, with the box's menu as its context menu; None if not
    `available`.

    The menu is the box's own items, read again each time it opens. Quit is the box's
    Quit, so the session is saved as it is from the box. Keep the result: an icon
    nothing holds is collected, and leaves the tray.
    """
    if not available:
        return None
    tray = tray_cls(QIcon(str(icon)), box)
    tray.setToolTip(APP_NAME)
    tray.setContextMenu(box_menu(box))
    tray.show()
    return tray


def box_menu(box: Box) -> QMenu:
    """A menu of the box's own items, read again each time it opens: the tray's."""
    menu = QMenu(box)
    box.attach_menu(menu)
    return menu


HIDE, SHOW = f"Hide {APP_NAME}", f"Show {APP_NAME}"
SETTINGS = "Settings…"


def add_settings(box: Box, window: SettingsWindow) -> None:
    """Settings…, above Quit: added before add_hide, so it comes just before Hide."""
    box.add_menu_item(SETTINGS, window.open, at=-1)


class Shown:
    """Whether MapleLens draws over the game: the player's Hide / Show. Not saved.

    Hidden means the box and the Layer, with the path arrow on it. The tools keep
    running: hiding is about the screen, not a pause.
    """

    def __init__(self, box: Box, layer: Layer):
        self.on = True
        self._box, self._layer = box, layer
        self.item: QAction | None = None  # the menu item, relabelled on each toggle

    def toggle(self) -> None:
        """Hide both, or show the box again; the next tick shows the Layer if the game's
        there."""
        self.on = not self.on
        self._box.setVisible(self.on)
        if not self.on:
            self._layer.hide()
        if self.item is not None:
            self.item.setText(HIDE if self.on else SHOW)


def add_hide(box: Box, layer: Layer, tray: QSystemTrayIcon | None, *, click: bool = True) -> Shown:
    """Hide / Show: a menu item just before Quit; the tray's menu has it, so the tray is
    the way back. With `click` (Windows) a left click on the tray icon toggles too; on the
    Mac a click opens the menu instead. With no tray there's no item: a hidden box would
    stay hidden.
    """
    shown = Shown(box, layer)
    if tray is None:
        return shown

    def clicked(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # a left click; a double click has one too
            shown.toggle()

    shown.item = box.add_menu_item(HIDE, shown.toggle, at=-1)
    if click:
        tray.activated.connect(clicked)
    return shown


def about_line(updates: "UpdateCheck | None") -> tuple[str, bool]:
    """About's updates line, and whether it's an update to light up."""
    if updates is None:
        return FROM_SOURCE, False
    text = updates.status()
    release = updates.release
    return text, release is not None and text == update_available(release.version)


def add_build_menu(box: Box, tool) -> QAction:
    """The class tool's build choice, above Quit: "Build: <name>", shown when there's a choice.

    `tool` has build_names(), build_name(), pick_build(name) and a builds_changed hook.
    """
    action = box.add_submenu("Build", tool.build_names, tool.pick_build, at=-1)
    action.setVisible(False)

    def follow() -> None:
        action.setText(f"Build: {tool.build_name()}")
        action.setVisible(bool(tool.build_names()))

    tool.builds_changed = follow
    return action


def add_about(box: Box, updates: "UpdateCheck | None") -> None:
    """The About item, just before Quit: the version, updates and the GitHub page.

    Added after add_hide, so it comes after Hide where there's one.
    """

    def show() -> None:
        text, accent = about_line(updates)
        url = f"https://github.com/{update.HOME_REPO}"
        box.show_about(version("maplelens"), text, url, accent=accent)

    box.add_menu_item(ABOUT, show, at=-1)


@dataclass
class Tick:
    """What MapleLens does every _TICK_MS: find the game, read it, feed the tools.

    `hwnd` is the game window found so far; None looks for it again.
    """

    settings: dict
    save: Callable[[], None]
    box: Box
    layer: Layer
    exp: ExpMeterTool
    path: PathArrowTool
    cls: ClassHelperTool
    quest: QuestHelperTool
    focus: QuestFocus
    updates: "UpdateCheck | None"
    seen: set[str]  # error types/messages already logged
    shown: Shown
    hwnd: int | None = None
    turn: int = 0  # ticks that tried to read a frame: whose turn it is (readers.due)
    seen_at: dict[str, int] = field(default_factory=dict)  # part -> turn it was last on screen
    reader: InlineReader | ProcessReader = field(default_factory=InlineReader)
    bars: tuple[int, ...] | None = None  # (w, h, dx, dy, dw, dh): the last fullscreen bar cut

    def picture(self, rect: Rect, cut: Rect | None = None) -> Rect:
        """The game's picture in window `rect`: `cut`, an answer's, when it left out bars;
        else the last cut for a window this size. A loading screen has no bars to see, so
        without this the box would jump to the window's corner and back on a map change.
        """
        x, y, w, h = rect
        if cut is not None and cut[2:] != rect[2:]:
            self.bars = (w, h, cut[0] - x, cut[1] - y, *cut[2:])
        if self.bars is None or self.bars[:2] != (w, h):
            return rect
        _, _, dx, dy, dw, dh = self.bars
        return x + dx, y + dy, dw, dh

    def remember(self, got, turn: int) -> None:
        """Note which windows a reading answer saw, as of the turn of the job it answers."""
        if got is not None and not isinstance(got, Exception):
            for p in found(got[1]):
                self.seen_at[p] = turn

    def tools(self) -> tuple:
        """The four tools for update_tools, OFF in place of each one turned off."""
        tools = (self.exp, self.path, self.cls, self.quest)
        return tuple(
            t if tool_on(self.settings, key) else OFF
            for t, key in zip(tools, TOOL_KEYS, strict=True)
        )

    def run(self, now: float) -> None:
        poll_updates(self.updates, now, self.seen)  # before the game lookup: shows with no game
        if self.box.about_open:  # its updates line follows the check
            text, accent = about_line(self.updates)
            self.box.set_about_updates(text, accent=accent)
        allowed = capture.has_access()  # each tick: it can be revoked or granted while we run
        self.hwnd = (self.hwnd or find_game(self.settings, self.save)) if allowed else None
        self.box.set_status(screen_status(allowed, self.hwnd))  # a minimized game isn't "looking"
        rect = capture.client_rect(self.hwnd) if self.hwnd else None
        if rect is None:
            self.hwnd = None  # gone or minimized: look again next tick
            self.layer.hide()
            update_tools(self.box, *self.tools(), self.focus, None, None, now, self.seen)
            return
        try:
            # take first: what the last job saw makes this job's `due` (InlineReader has nothing
            # to give yet; its answer comes from the second take)
            got = self.reader.take()
            self.remember(got, self.turn - 1)
            parts = due(self.turn, self.seen_at) - unread(self.settings)  # off tools' windows
            self.reader.ask((self.hwnd, rect, now, parts))
            if got is None:
                got = self.reader.take()
                self.remember(got, self.turn)
        except Exception as e:  # a bad tick counts as no reading; the box still follows the game
            got = e
        self.turn += 1  # bad ticks too: the turns keep going
        if got is None:  # no answer yet: follow the game, leave the tools alone
            rect = self.picture(rect)
            self.layer.follow(rect)
            if self.shown.on:
                self.layer.show()
            self.box.place(rect)
            return
        if isinstance(got, Exception):
            report_once(got, self.seen)
            reading = None
            rect = self.picture(rect)
        else:
            cut, reading = got  # the picture without any fullscreen black bars
            rect = self.picture(rect, cut)
        self.layer.follow(rect)
        if self.shown.on:  # hidden by the player: the tools still run, nothing shows
            self.layer.show()
        update_tools(self.box, *self.tools(), self.focus, reading, rect, now, self.seen)
        self.box.place(rect)


def hide_from_dock() -> None:
    """Mac: no Dock icon, only the menu bar's (make_tray), even run from source."""
    from maplelens import overlay_mac  # AppKit only exists on the Mac

    overlay_mac.make_accessory()


def _start_qt() -> QApplication:
    """The QApplication, started so that it never takes the front from the game itself:
    only the player's click on one of its windows brings MapleLens forward."""
    if sys.platform == "darwin":  # Qt raises a starting app over the others unless told not
        os.environ.setdefault("QT_MAC_SET_RAISE_PROCESS", "0")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if sys.platform == "darwin":
        hide_from_dock()
        app.processEvents()  # finish launching first: a window shown before that activates us
    return app


def early_exit() -> int | None:
    """main's exit code when it must stop before any window, else None.

    The self-check comes first: the build runs it while MapleLens may be running. Then
    one copy at a time: each holds its own settings and rewrites the whole file on save,
    so a second would undo the first's changes. It quits quietly, with no window to take
    focus from the game. An update's new version starts only once the old one has exited.
    """
    if "--self-check" in sys.argv[1:]:
        return self_check()
    if not mark_running():
        if sys.stderr is not None:  # started from a terminal: say why nothing opens
            sys.stderr.write("MapleLens is already running\n")
        return 0
    return None


def main() -> int:
    multiprocessing.freeze_support()  # a spawned child of the frozen app runs here, then exits
    if (code := early_exit()) is not None:
        return code
    app = _start_qt()
    capture.set_dpi_aware()
    start_log(data_dir() / "maplelens.log")
    path = data_dir() / "settings.json"
    settings = load_settings(path)
    layer = Layer()

    def save() -> None:
        save_settings(path, settings)

    conn = open_db(data_dir() / "maplelens.db")
    cls_data = class_data.load()
    # the lambdas defer the lookup: `box` is built from the tools below
    tool = ExpMeterTool(
        settings,
        conn,
        cls_data.line,
        save=save,
        show_pin=lambda on: box.set_footer_shown(on),  # noqa: PLW0108
        open_tab=lambda: box.select(0),
    )
    path_tool = PathArrowTool(settings, save, layer, lambda on: box.allow_typing(on))  # noqa: PLW0108
    seen: set[str] = set()  # error types/messages already logged

    def pick(title: str) -> None:
        choose_window(settings, save, title)
        tick.hwnd = None  # the next tick finds the chosen window

    def go(map_id: str) -> None:
        path_tool.go(map_id)
        box.select(1)

    cls_tool = ClassHelperTool(settings, save, layer, go, lambda t: best_rate(conn, t), cls_data)
    quest_tool = QuestHelperTool(
        settings,
        save,
        quest_go(path_tool, lambda i: box.select(i)),  # noqa: PLW0108 - box is built next
        path_tool.heading,
        path_tool.stop,
        path_tool.hops,
    )  # its go stays on the Quests tab while a trip runs
    tools = [tool, path_tool, cls_tool, quest_tool]  # the tabs' order: indexes below rely on it
    box = build_box(settings, save, tools, pick)
    box.add_footer(tool.pin_line, 0)  # the EXP line, under every tab but EXP's own
    box.set_footer_shown(tool.pinned)
    setup_screen_recording(box)
    add_build_menu(box, cls_tool)
    updates = update_check(box, settings, save, seen, time.time())
    general = GeneralSection()
    if updates is not None:
        general.add_updates(settings["update_check"], updates.set_auto, updates.check_now)
    switches = ToolSwitches(settings, save, box, tool, path_tool, cls_tool, quest_tool)
    settings_window = SettingsWindow(  # held: the menu links to it weakly
        tool_sections(tools, settings),
        lambda i, on: switches.set(i, on, time.time()),
        general,
    )
    switches.apply(settings_window, [t.title for t in tools])
    add_settings(box, settings_window)
    tray = make_tray(box, ICON, available=tray_available())  # held, or it leaves the tray
    shown = add_hide(box, layer, tray, click=sys.platform == "win32")
    add_about(box, updates)  # after Hide: just before Quit
    reader = make_reader(sys.platform)
    tick = Tick(
        settings,
        save,
        box,
        layer,
        tool,
        path_tool,
        cls_tool,
        quest_tool,
        QuestFocus(box, 3),
        updates,
        seen,
        shown,
        reader=reader,
    )
    timer = QTimer()
    timer.timeout.connect(lambda: tick.run(time.time()))
    timer.start(_TICK_MS)
    app.aboutToQuit.connect(lambda: tool.shutdown(time.time()))
    app.aboutToQuit.connect(reader.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
