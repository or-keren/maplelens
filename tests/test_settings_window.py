import sys

import pytest


@pytest.fixture
def qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _window(states=(True, True, True), bodies=None, general=None):
    """A window of tools A, B, C; returns it and the (index, on) its switches reported."""
    from maplelens.settings_window import SettingsWindow, ToolSection

    bodies = bodies or {}
    calls = []
    tools = [ToolSection(t, on, bodies.get(t)) for t, on in zip("ABC", states, strict=True)]
    win = SettingsWindow(tools, lambda i, on: calls.append((i, on)), general)
    return win, calls


def _heads(win):
    """The cards' headings, top to bottom."""
    from PySide6.QtWidgets import QWidget

    heads = list(win.findChildren(QWidget, "head"))
    return [w.text() for w in sorted(heads, key=lambda w: w.mapTo(win, w.rect().topLeft()).y())]


def test_each_tool_gets_a_card_headed_by_its_switch(qt):
    from maplelens.settings_window import TITLE

    win, _ = _window()
    assert win.windowTitle() == TITLE == "MapleLens — Settings"
    assert _heads(win) == ["A", "B", "C"]
    assert [s.text() for s in win.switches] == ["A", "B", "C"]


def test_general_comes_first_and_only_when_it_has_anything(qt):
    from maplelens.settings_window import GeneralSection

    win, _ = _window(general=GeneralSection())  # from source: no update check
    assert _heads(win) == ["A", "B", "C"]
    general = GeneralSection()
    general.add_updates(True, lambda _on: None, lambda: None)
    win, _ = _window(general=general)
    assert _heads(win) == ["General", "A", "B", "C"]


def test_a_tool_with_nothing_to_set_says_so(qt):
    from PySide6.QtWidgets import QLabel

    from maplelens.settings_window import NOTHING_YET

    body = QLabel("b's settings")
    win, _ = _window(bodies={"B": body})
    texts = [w.text() for w in win.findChildren(QLabel)]
    assert texts.count(NOTHING_YET) == 2 and "b's settings" in texts


def test_the_window_floats_over_the_game_without_taking_focus(qt):
    from PySide6.QtCore import Qt

    win, _ = _window()
    assert win.windowType() == Qt.Tool
    assert win.testAttribute(Qt.WA_ShowWithoutActivating)
    assert not win.testAttribute(Qt.WA_QuitOnClose)
    if sys.platform != "darwin":  # the Mac's panel does this itself, in native_setup
        assert win.windowFlags() & Qt.WindowStaysOnTopHint
        assert win.windowFlags() & Qt.WindowDoesNotAcceptFocus


def test_opening_twice_gives_one_window(qt):
    from maplelens import app
    from maplelens.overlay import Box
    from maplelens.settings_window import SettingsWindow

    box = Box("t", {}, lambda: None)
    box.add_menu_item("Quit MapleLens", lambda: None)
    win, _ = _window()
    app.add_settings(box, win)
    (item,) = [a for a in box.actions() if a.text() == "Settings…"]
    item.trigger()
    item.trigger()
    assert win.isVisible()
    shown = [w for w in qt.topLevelWidgets() if isinstance(w, SettingsWindow) and w.isVisible()]
    assert shown == [win]
    win.close()


def test_settings_comes_just_before_hide(qt):
    from maplelens import app
    from maplelens.overlay import Box

    class Tray:
        def __init__(self):
            self.activated = type("S", (), {"connect": lambda *_: None})()

    box = Box("t", {}, lambda: None)
    box.add_menu_item("Quit MapleLens", lambda: None)
    app.add_settings(box, _window()[0])
    app.add_hide(box, app.Layer(), Tray())
    app.add_about(box, None)
    assert [a.text() for a in box.actions()] == [
        "Settings…",
        "Hide MapleLens",
        "About MapleLens",
        "Quit MapleLens",
    ]


def test_closing_settings_does_not_quit(qt):
    from PySide6.QtCore import QTimer

    win, _ = _window()
    win.open()
    survived = []
    QTimer.singleShot(0, win.close)
    QTimer.singleShot(200, lambda: survived.append(1))
    QTimer.singleShot(300, qt.quit)  # exec() must still be running at 200 ms
    qt.exec()
    assert survived == [1]


def test_a_click_reaches_a_switch_in_the_window(qt):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    win, calls = _window()
    win.open()
    switch = win.switches[1]
    # on the box itself: a checkbox stretched across the card ignores its empty middle
    QTest.mouseClick(switch, Qt.LeftButton, pos=QPoint(6, switch.height() // 2))
    assert not switch.isChecked() and calls == [(1, False)]
    win.close()


def test_general_has_the_update_controls_only_when_asked(qt):
    from PySide6.QtWidgets import QCheckBox, QPushButton

    from maplelens.settings_window import AUTO_UPDATES, CHECK_NOW, GeneralSection

    assert GeneralSection().empty
    calls = []
    general = GeneralSection()
    general.add_updates(True, calls.append, lambda: calls.append("now"))
    (box,) = general.findChildren(QCheckBox)
    (button,) = general.findChildren(QPushButton)
    assert (box.text(), box.isChecked(), button.text()) == (AUTO_UPDATES, True, CHECK_NOW)
    box.setChecked(False)
    button.click()
    assert calls == [False, "now"]


def test_a_tool_switch_reports_its_index(qt):
    win, calls = _window()
    win.switches[1].setChecked(False)
    win.switches[2].setChecked(False)
    assert calls == [(1, False), (2, False)]


def test_the_last_tool_on_cant_be_turned_off(qt):
    from maplelens.settings_window import LAST_ON

    win, _ = _window((True, True, False))
    a, b, c = win.switches
    assert a.isEnabled() and b.isEnabled() and c.isEnabled()
    b.setChecked(False)
    assert not a.isEnabled() and a.toolTip() == LAST_ON  # the only one left on
    assert b.isEnabled() and c.isEnabled()
    c.setChecked(True)
    assert a.isEnabled() and a.toolTip() == ""


def test_the_last_tool_on_is_locked_from_the_start(qt):
    win, _ = _window((False, True, False))
    a, b, _c = win.switches
    assert not b.isEnabled() and a.isEnabled()


def test_an_off_tools_settings_grey_out_but_its_switch_stays(qt):
    from PySide6.QtWidgets import QLabel

    body = QLabel("b's settings")
    win, _ = _window((True, False, True), bodies={"B": body})
    assert not body.isEnabled()  # saved off
    assert win.switches[1].isEnabled()  # it can be turned back on
    win.set_section_enabled("B", True)
    assert body.isEnabled()
    win.set_section_enabled("B", False)
    assert not body.isEnabled()
    win.set_section_enabled("Nope", False)  # no such tool: nothing to grey
