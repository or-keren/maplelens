import sys

import pytest

from maplelens import overlay
from maplelens.overlay import game_to_layer


def test_game_to_layer_125pct():
    assert game_to_layer(1250, 500, 1.25) == (1000.0, 400.0)


def _box(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.overlay import Box

    QApplication.instance() or QApplication([])
    return Box("t", {}, lambda: None)


def test_box_tabs_switch(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    a, b = QLabel("a"), QLabel("b")
    assert box.add_tab("A", a) == 0
    assert box.add_tab("B", b) == 1
    assert a.isVisibleTo(box) and not b.isVisibleTo(box)
    box._tab_buttons[1].click()
    assert b.isVisibleTo(box) and not a.isVisibleTo(box)


def test_a_hidden_tall_tab_never_stretches_the_current_one(monkeypatch):
    """Wrapped text on the current tab once sized it by the tallest tab, hidden ones too."""
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    def page(text):
        p = QWidget()
        p.setFixedWidth(overlay.TAB_W)
        label = QLabel(text)
        label.setWordWrap(True)
        QVBoxLayout(p).addWidget(label)
        return p, label

    def settle():
        for _ in range(20):
            QApplication.processEvents()

    box = _box(monkeypatch)
    current, line = page("Not in the map list yet, so no route from here")
    line.hide()
    box.add_tab("A", current)
    box.add_tab("B", page("word " * 120)[0])
    box.show()
    settle()
    line.show()  # the current tab's first wrapped line
    settle()
    assert current.height() == current.heightForWidth(overlay.TAB_W)


def test_tab_dot(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel())
    box.add_tab("B", QLabel())
    assert not box._tab_dots[1].isVisibleTo(box)
    box.set_tab_dot(1, True)
    assert box._tab_dots[1].isVisibleTo(box)
    box.set_tab_dot(1, False)
    assert not box._tab_dots[1].isVisibleTo(box)


def _three_tabs(monkeypatch, tab_width=None):
    from PySide6.QtWidgets import QLabel

    from maplelens.overlay import Box

    _box(monkeypatch)
    box = Box("t", {"tab_width": tab_width}, lambda: None)
    pages = [QLabel(t) for t in "abc"]
    for title, page in zip("ABC", pages, strict=True):
        box.add_tab(title, page)
    return box, pages


def test_a_hidden_tab_loses_its_button_and_the_others_keep_their_indexes(monkeypatch):
    box, (_a, _b, c) = _three_tabs(monkeypatch)
    box.set_tab_shown(1, False)
    assert not box._tab_buttons[1].isVisibleTo(box)
    box.select(2)
    assert c.isVisibleTo(box) and box.current == 2
    box.set_tab_dot(2, True)
    assert box._tab_dots[2].isVisibleTo(box)


@pytest.mark.parametrize("tab_width", [None, 300])
def test_hiding_the_open_tab_shows_the_first_one_still_on(monkeypatch, tab_width):
    box, (a, b, _c) = _three_tabs(monkeypatch, tab_width)
    box.show()
    box.select(0)
    width = box.width()
    box.set_tab_shown(0, False)
    assert box.current == 1 and b.isVisibleTo(box) and not a.isVisibleTo(box)
    box.adjustSize()
    assert box.width() == width  # the pages' fixed width sizes the box, not the strip


def test_select_and_a_dot_leave_a_hidden_tab_hidden(monkeypatch):
    box, (_a, _b, c) = _three_tabs(monkeypatch)
    box.set_tab_shown(2, False)
    box.select(2)  # QuestFocus asking for a tab that's off
    assert box.current == 0 and not c.isVisibleTo(box)
    box.set_tab_dot(2, True)
    assert not box._tab_dots[2].isVisibleTo(box)
    box.set_tab_shown(2, True)  # back on: the dot it was given shows
    assert box._tab_buttons[2].isVisibleTo(box) and box._tab_dots[2].isVisibleTo(box)


def _footer_box(monkeypatch):
    """Two tabs, a footer owned by tab 0, turned on, on tab 1."""
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel())
    box.add_tab("B", QLabel())
    line = QLabel("pin")
    box.add_footer(line, 0)
    box.set_footer_shown(True)
    box.select(1)
    return box, line


def test_footer_shows_on_other_tabs_only_when_on(monkeypatch):
    box, line = _footer_box(monkeypatch)
    assert line.isVisibleTo(box)
    box.set_footer_shown(False)
    assert not line.isVisibleTo(box)


def test_hiding_the_footers_tab_hides_the_footer(monkeypatch):
    box, line = _footer_box(monkeypatch)
    box.set_tab_shown(0, False)  # EXP off: no pinned EXP line either
    assert not line.isVisibleTo(box)
    box.set_tab_shown(0, True)
    assert line.isVisibleTo(box)


def test_footer_follows_select(monkeypatch):
    box, line = _footer_box(monkeypatch)
    box.select(0)  # its own tab: the full numbers are there
    assert not line.isVisibleTo(box)
    box.select(1)  # as QuestFocus does
    assert line.isVisibleTo(box)


def test_footer_hides_with_status_and_about(monkeypatch):
    box, line = _footer_box(monkeypatch)
    box.set_status("Looking for the game")
    assert not line.isVisibleTo(box)
    box.set_status(None)
    assert line.isVisibleTo(box)
    box.show_about("1.0", "", "")
    assert not line.isVisibleTo(box)
    box.close_about()
    assert line.isVisibleTo(box)


def test_allow_typing_toggles_focus_flag(monkeypatch):
    from PySide6.QtCore import Qt

    box = _box(monkeypatch)
    box.show()
    assert box.windowFlags() & Qt.WindowDoesNotAcceptFocus
    box.allow_typing(True)
    assert not box.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert box.isVisible()
    box.allow_typing(False)
    assert box.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert box.isVisible()


def test_native_setup_offscreen_is_noop(monkeypatch):
    calls = []
    if sys.platform == "darwin":  # overlay_mac needs AppKit, which only the Mac has
        from maplelens import overlay_mac

        monkeypatch.setattr(overlay_mac, "make_panel", calls.append)
    box = _box(monkeypatch)
    box.show()
    assert calls == []


def test_font_per_platform():
    assert overlay.FONT == ("Helvetica Neue" if sys.platform == "darwin" else "Segoe UI")


@pytest.mark.skipif(sys.platform != "darwin", reason="overlay_mac needs AppKit")
def test_allow_typing_off_releases_keyboard_on_mac(monkeypatch):
    from maplelens import overlay_mac

    calls = []
    monkeypatch.setattr(overlay_mac, "release_keyboard", lambda: calls.append(1))
    box = _box(monkeypatch)
    box.show()
    box.allow_typing(True)
    assert calls == []
    box.allow_typing(False)
    assert calls == [1]


@pytest.mark.skipif(sys.platform != "darwin", reason="overlay_mac needs AppKit")
@pytest.mark.parametrize("active", [True, False])
def test_release_keyboard_deactivates_only_when_active(monkeypatch, active):
    from maplelens import overlay_mac

    calls = []

    class FakeApp:
        def isActive(self):
            return active

        def deactivate(self):
            calls.append(1)

    class FakeNSApplication:
        sharedApplication = staticmethod(FakeApp)

    monkeypatch.setattr(overlay_mac, "NSApplication", FakeNSApplication)
    overlay_mac.release_keyboard()
    assert calls == ([1] if active else [])


def test_status_line_replaces_the_tabs(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    page = QLabel("page")
    box.add_tab("A", page)
    box.set_status("Looking for the game")
    assert box._status.isVisibleTo(box) and box._status.text() == "Looking for the game"
    assert not page.isVisibleTo(box) and not box._tab_buttons[0].isVisibleTo(box)
    box.set_tab_dot(0, True)  # a tool may turn its dot on meanwhile
    box.set_status(None)
    assert not box._status.isVisibleTo(box)
    assert page.isVisibleTo(box) and box._tab_buttons[0].isVisibleTo(box)
    assert box._tab_dots[0].isVisibleTo(box)


def test_submenu_lists_choices_when_opened(monkeypatch):
    box = _box(monkeypatch)
    picked, choices = [], ["A", "B"]
    box.add_submenu("Pick", lambda: choices, picked.append)
    [action] = box.actions()
    menu = action.menu()
    menu.aboutToShow.emit()
    assert [a.text() for a in menu.actions()] == ["A", "B"]
    choices = ["C"]  # the list is read again each time the menu opens
    menu.aboutToShow.emit()
    [c] = menu.actions()
    c.trigger()
    assert picked == ["C"]


def test_notice_shows_under_the_tabs_and_x_dismisses_it(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    page = QLabel("page")
    box.add_tab("A", page)
    dismissed = []
    box.set_notice("Update to 0.2.0: click •••", lambda: dismissed.append(1))
    assert box._notice.isVisibleTo(box)
    assert box._notice_text.text() == "Update to 0.2.0: click •••"
    assert page.isVisibleTo(box) and box._tab_buttons[0].isVisibleTo(box)
    box._notice_close.click()
    assert not box._notice.isVisibleTo(box)
    assert dismissed == [1]


def test_notice_none_hides_it(monkeypatch):
    box = _box(monkeypatch)
    box.set_notice("x", lambda: None)
    box.set_notice(None)
    assert not box._notice.isVisibleTo(box)


def test_notice_stays_while_the_status_line_shows(monkeypatch):
    box = _box(monkeypatch)
    box.set_notice("x", lambda: None)
    box.set_status("Looking for the game")
    assert box._notice.isVisibleTo(box)


@pytest.mark.parametrize(
    "which",
    ["update", "downloading", "failed", "up to date", "couldn't check", "move", "allow"],
)
def test_notice_fits_the_tab_width_at_the_longest_version(monkeypatch, which):
    from maplelens import app

    text = {
        "update": app.update_notice("10.10.10"),
        "downloading": app.downloading_notice("10.10.10"),
        "failed": app.UPDATE_FAILED,
        "up to date": app.UP_TO_DATE,
        "couldn't check": app.COULDNT_CHECK,
        "move": app.MOVE_TO_APPLICATIONS,
        "allow": app.ALLOW_UPDATES,
    }[which]
    box = _box(monkeypatch)
    box.set_notice(text, lambda: None)
    assert box._notice.sizeHint().width() <= overlay.TAB_W


def test_menu_item_can_go_first_and_be_relabelled(monkeypatch):
    box = _box(monkeypatch)
    box.add_menu_item("Quit", lambda: None)
    item = box.add_menu_item("Update to 0.2.0…", lambda: None, at=0)
    assert [a.text() for a in box.actions()] == ["Update to 0.2.0…", "Quit"]
    item.setText("Update to 0.3.0…")
    assert box.actions()[0].text() == "Update to 0.3.0…"


def test_menu_items_can_go_before_the_last_one(monkeypatch):
    box = _box(monkeypatch)
    box.add_menu_item("Pick", lambda: None)
    box.add_menu_item("Quit", lambda: None)
    box.add_menu_item("Check now", lambda: None, at=-1)
    box.add_toggle("Check automatically", True, lambda on: None, at=-1)
    assert [a.text() for a in box.actions()] == ["Pick", "Check now", "Check automatically", "Quit"]


def test_toggle_shows_its_state_and_reports_changes(monkeypatch):
    box = _box(monkeypatch)
    changes = []
    toggle = box.add_toggle("Check automatically", True, changes.append)
    assert toggle.isCheckable() and toggle.isChecked()
    toggle.trigger()
    assert not toggle.isChecked()
    toggle.trigger()
    assert changes == [False, True]
    assert not box.add_toggle("Off", False, changes.append).isChecked()


def test_menu_button_shows_with_the_tabs_and_with_the_status_line(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel("page"))
    assert box._menu_button.isVisibleTo(box)
    box.set_status("Looking for the game")
    assert box._menu_button.isVisibleTo(box)
    box.set_status(None)
    assert box._menu_button.isVisibleTo(box)


def test_menu_button_sits_right_of_the_tabs_and_the_status(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel("page"))
    box.show()
    button = box._menu_button.geometry()
    assert button.left() >= box._strip_row.geometry().right()
    box.set_status("Looking for the game")
    box.adjustSize()
    assert box._menu_button.geometry().left() >= box._status.geometry().right()
    assert box._menu_button.geometry().top() <= box._status.geometry().top() + 4


def _menu_texts(menu):
    menu.aboutToShow.emit()  # what Qt does as the menu opens
    return [a.text() for a in menu.actions()]


def test_attached_menu_lists_the_box_actions_when_it_opens(monkeypatch):
    from PySide6.QtWidgets import QMenu

    box = _box(monkeypatch)
    box.add_submenu("Pick game window…", lambda: ["A"], lambda t: None)
    box.add_menu_item("Quit", lambda: None)
    menu = QMenu()
    box.attach_menu(menu)
    assert _menu_texts(menu) == ["Pick game window…", "Quit"]
    box.add_menu_item("Update to 0.2.0…", lambda: None, at=0)  # the update check, later on
    assert _menu_texts(menu) == ["Update to 0.2.0…", "Pick game window…", "Quit"]
    assert menu.actions() == box.actions()


def test_opening_an_attached_menu_twice_keeps_every_action_working(monkeypatch):
    from PySide6.QtWidgets import QMenu

    box = _box(monkeypatch)
    picked, quit_ = [], []
    box.add_submenu("Pick", lambda: ["A"], picked.append)
    box.add_menu_item("Quit", lambda: quit_.append(1))
    menu = QMenu()
    box.attach_menu(menu)
    _menu_texts(menu)
    _menu_texts(menu)
    pick, quit_action = box.actions()  # still the box's, not deleted by clear()
    assert [a.text() for a in box.actions()] == ["Pick", "Quit"]
    quit_action.trigger()
    sub = pick.menu()
    sub.aboutToShow.emit()
    sub.actions()[0].trigger()
    assert quit_ == [1] and picked == ["A"]


def test_menu_button_opens_the_box_menu(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel("page"))
    box.add_menu_item("Quit", lambda: None)
    box.show()
    box.move(400, 300)  # off the screen's edges, which Qt keeps the menu inside
    QTest.mouseClick(box._menu_button, Qt.LeftButton)
    try:
        assert box._menu.isVisible()
        assert [a.text() for a in box._menu.actions()] == ["Quit"]
        # just under the button, right edges lined up: the box sits at the game's right
        button_bottom_right = box._menu_button.mapToGlobal(box._menu_button.rect().bottomRight())
        assert box._menu.geometry().top() >= button_bottom_right.y()
        assert abs(box._menu.geometry().right() - button_bottom_right.x()) <= 1
    finally:
        box._menu.hide()


def test_menu_button_never_takes_focus_or_starts_a_drag(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel("page"))
    box.show()
    assert box._menu_button.focusPolicy() == Qt.NoFocus
    QTest.mousePress(box._menu_button, Qt.LeftButton)
    assert box._drag_from is None
    QTest.mouseRelease(box._menu_button, Qt.LeftButton)
    box._menu.hide()
    assert box._drag_from is None


def test_right_click_still_opens_the_box_menu(monkeypatch):
    from PySide6.QtCore import Qt

    box = _box(monkeypatch)
    box.add_menu_item("Quit", lambda: None)
    assert box.contextMenuPolicy() == Qt.ActionsContextMenu


def test_menu_button_lines_up_with_the_first_line_of_a_two_line_status(monkeypatch):
    from PySide6.QtWidgets import QLabel

    box = _box(monkeypatch)
    box.add_tab("A", QLabel("page"))
    box.show()
    box.set_status("Looking for the game…\nclick ••• to pick it")
    box.adjustSize()
    button, status = box._menu_button.geometry(), box._status.geometry()
    assert abs(button.top() - status.top()) <= 2  # the corner, not between the lines
    box.set_status(None)
    box.adjustSize()
    button, strip = box._menu_button.geometry(), box._strip_row.geometry()
    assert abs(button.center().y() - strip.center().y()) <= 2  # level with the tab titles


@pytest.mark.parametrize("on", [True, False])
def test_allow_typing_leaves_a_hidden_box_hidden(monkeypatch, on):
    box = _box(monkeypatch)
    box.show()
    box.hide()  # the player hid MapleLens
    box.allow_typing(on)
    assert not box.isVisible()


URL = "https://github.com/someone/maplelens"


def _tabbed_box(monkeypatch):
    from PySide6.QtWidgets import QWidget

    box = _box(monkeypatch)
    page = QWidget()
    page.setFixedSize(overlay.TAB_W, 40)  # as wide as the real tabs
    box.add_tab("A", page)
    return box, page


def test_about_replaces_the_tabs_and_x_brings_them_back(monkeypatch):
    box, page = _tabbed_box(monkeypatch)
    box.show_about("0.1.0", "Up to date", URL)
    assert box.about_open
    assert not box._strip_row.isVisibleTo(box) and not page.isVisibleTo(box)
    assert not box._status.isVisibleTo(box)
    for part in (box._about_title, box._about_close, box._menu_button, box._about):
        assert part.isVisibleTo(box)
    assert box._about_title.text() == "About MapleLens"
    assert box._about_version.text() == "0.1.0"
    assert box._about_updates.text() == "Up to date"
    box._about_close.click()
    assert not box.about_open
    assert box._strip_row.isVisibleTo(box) and page.isVisibleTo(box)
    assert not box._about.isVisibleTo(box) and not box._about_title.isVisibleTo(box)


def test_a_status_set_while_about_is_open_shows_once_it_closes(monkeypatch):
    box, page = _tabbed_box(monkeypatch)
    box.show_about("0.1.0", "Up to date", URL)
    box.set_status("Looking for the game")  # the tick, every 500 ms
    assert not box._status.isVisibleTo(box) and box._about.isVisibleTo(box)
    box.close_about()
    assert box._status.isVisibleTo(box) and box._status.text() == "Looking for the game"
    assert not page.isVisibleTo(box)
    box.set_status(None)
    assert page.isVisibleTo(box) and not box._status.isVisibleTo(box)


def test_the_about_updates_line_changes_and_lights_up_for_an_update(monkeypatch):
    box, _ = _tabbed_box(monkeypatch)
    box.show_about("0.1.0", "Checking…", URL)
    assert overlay.ACCENT not in box._about_updates.styleSheet()
    box.set_about_updates("Update to 0.2.0 available", accent=True)
    assert box._about_updates.text() == "Update to 0.2.0 available"
    assert overlay.ACCENT in box._about_updates.styleSheet()
    box.set_about_updates("Up to date")
    assert overlay.ACCENT not in box._about_updates.styleSheet()


def test_the_github_link_opens_the_url(monkeypatch):
    from PySide6.QtCore import QUrl

    opened = []
    monkeypatch.setattr(overlay.QDesktopServices, "openUrl", opened.append)
    box, _ = _tabbed_box(monkeypatch)
    box.show_about("0.1.0", "Up to date", URL)
    assert box._about_link.text() == "GitHub page ↗"
    box._about_link.click()
    assert opened == [QUrl(URL)]


def test_about_never_takes_focus(monkeypatch):
    from PySide6.QtCore import Qt

    box, _ = _tabbed_box(monkeypatch)
    assert box._about_close.focusPolicy() == Qt.NoFocus
    assert box._about_link.focusPolicy() == Qt.NoFocus


def test_about_at_the_longest_version_keeps_the_box_width(monkeypatch):
    box, _ = _tabbed_box(monkeypatch)
    box.show()
    width = box.width()
    box.show_about("10.10.10", "Update to 10.10.10 available", URL)
    box.set_about_updates("Update to 10.10.10 available", accent=True)
    box.adjustSize()
    assert box._about.sizeHint().width() <= overlay.TAB_W
    assert box.width() == width


def test_buttons_have_kinds_and_never_take_focus(monkeypatch):
    from PySide6.QtCore import Qt

    from maplelens.overlay import primary_button, secondary_button

    _box(monkeypatch)  # the app
    hits = []
    p = primary_button("Start", lambda: hits.append("p"))
    s = secondary_button("Stop", lambda: hits.append("s"))
    assert (p.property("kind"), s.property("kind")) == ("primary", "secondary")
    assert p.focusPolicy() == s.focusPolicy() == Qt.NoFocus
    p.click()
    s.click()
    assert hits == ["p", "s"]


def test_info_line_text_and_height(monkeypatch):
    from maplelens.overlay import LABEL_COLOR, LABEL_PT, InfoLine, text_label

    _box(monkeypatch)
    line = InfoLine()
    line.setText("No route")  # short: offscreen fonts are wide, and a wrap isn't the point
    assert line.text() == "No route"
    plain = text_label("No route", LABEL_PT, LABEL_COLOR)
    assert line.sizeHint().height() <= plain.sizeHint().height() + 2  # no taller fallback font


def test_add_submenu_returns_its_action_and_can_go_before_an_item(monkeypatch):
    box = _box(monkeypatch)
    box.add_menu_item("Quit", lambda: None)
    action = box.add_submenu("Pick", lambda: ["a"], lambda t: None, at=-1)
    assert action.text() == "Pick"
    assert [a.text() for a in box.actions()] == ["Pick", "Quit"]


def test_a_tab_with_a_wide_hint_keeps_the_box_width(monkeypatch):
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    box = _box(monkeypatch)
    tab = QWidget()
    tab.setFixedWidth(overlay.TAB_W)  # every tab is this wide; its wrapped text hints wider
    text = QLabel("a long line that wraps " * 20)
    text.setWordWrap(True)
    QVBoxLayout(tab).addWidget(text)
    box.add_tab("A", tab)
    box.show()  # a shown box's pages size from their raw hints
    box.adjustSize()
    assert box.width() == overlay.TAB_W + 24  # the box's 12 px side margins


@pytest.mark.parametrize(
    ("saved", "width"),
    [
        (None, overlay.TAB_W),
        ("wide", overlay.TAB_W),  # a hand-edited settings file
        (True, overlay.TAB_W),
        (50, overlay.TAB_W),
        (300, 300),
        (9999, overlay.MAX_TAB_W),
    ],
)
def test_a_saved_tab_width_is_kept_within_the_limits(saved, width):
    assert overlay.fit_tab_w(saved) == width


def _resizable(monkeypatch, settings=None):
    from PySide6.QtWidgets import QLabel

    from maplelens.overlay import Box

    _box(monkeypatch)  # the app
    saves = []
    box = Box("t", {} if settings is None else settings, lambda: saves.append(1))
    box.add_tab("A", QLabel("page"))
    box.show()
    _settle()
    return box, saves


def _settle():
    from PySide6.QtWidgets import QApplication

    for _ in range(20):
        QApplication.processEvents()


class _GripDrag:
    """The player's drag of the box's corner handle, by global position as the mouse moves."""

    def __init__(self, box):
        from PySide6.QtCore import QPointF

        self.grip = box._grip
        self.start = QPointF(self.grip.mapToGlobal(self.grip.rect().center()))

    def _send(self, kind, dx, button, buttons):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        at = self.start + QPointF(dx, 0)
        local = self.grip.mapFromGlobal(at)
        QApplication.sendEvent(
            self.grip, QMouseEvent(kind, local, at, button, buttons, Qt.NoModifier)
        )

    def press(self):
        from PySide6.QtCore import QEvent, Qt

        self._send(QEvent.MouseButtonPress, 0, Qt.LeftButton, Qt.LeftButton)

    def move(self, dx):
        from PySide6.QtCore import QEvent, Qt

        self._send(QEvent.MouseMove, dx, Qt.NoButton, Qt.LeftButton)
        _settle()

    def release(self, dx):
        from PySide6.QtCore import QEvent, Qt

        self._send(QEvent.MouseButtonRelease, dx, Qt.LeftButton, Qt.NoButton)
        _settle()


def test_dragging_the_grip_widens_the_box_and_saves_once_on_release(monkeypatch):
    settings = {}
    box, saves = _resizable(monkeypatch, settings)
    before = box.width()
    drag = _GripDrag(box)
    drag.press()
    drag.move(60)
    drag.move(100)
    assert box.width() == before + 100
    assert saves == []  # no disk write per mouse move
    drag.release(100)
    assert saves == [1]
    assert settings["tab_width"] == overlay.TAB_W + 100


@pytest.mark.parametrize(
    ("dx", "tab_w"), [(-80, overlay.TAB_W), (9999, overlay.MAX_TAB_W)], ids=["min", "max"]
)
def test_the_grip_stops_at_the_width_limits(monkeypatch, dx, tab_w):
    box, _ = _resizable(monkeypatch)
    drag = _GripDrag(box)
    drag.press()
    drag.move(dx)
    drag.release(dx)
    assert box.width() == tab_w + 24  # the box's 12 px side margins


def test_a_saved_width_is_used_from_the_start(monkeypatch):
    box, _ = _resizable(monkeypatch, {"tab_width": 300})
    assert box.width() == 300 + 24


def test_the_grip_keeps_to_the_bottom_right_corner_clear_of_the_content(monkeypatch):
    box, _ = _resizable(monkeypatch)
    drag = _GripDrag(box)
    drag.press()
    drag.move(80)
    drag.release(80)
    grip = box._grip.geometry()
    assert (grip.right(), grip.bottom()) == (box.width() - 1, box.height() - 1)
    assert grip.left() > box._pages.geometry().right()


def test_grabbing_the_grip_never_drags_the_box(monkeypatch):
    box, _ = _resizable(monkeypatch)
    box.move(400, 300)
    drag = _GripDrag(box)
    drag.press()
    drag.move(50)
    assert box._drag_from is None
    assert box.pos().x() == 400 and box.pos().y() == 300
    drag.release(50)


def test_a_box_at_its_default_spot_stays_put_while_and_after_resizing(monkeypatch):
    """The default spot hangs from the box's right edge, so it would slide from under the mouse."""
    box, _ = _resizable(monkeypatch)
    game = (0, 0, 1366, 768)
    box.place(game)
    spot = box.pos()
    drag = _GripDrag(box)
    drag.press()
    drag.move(100)
    box.place(game)  # the tick, every 500 ms
    assert box.pos() == spot
    drag.release(100)
    box.place(game)
    assert box.pos() == spot


def test_the_grip_hides_with_the_tabs(monkeypatch):
    """The status line sets its own width, so there is nothing for a drag to change."""
    box, _ = _resizable(monkeypatch)
    assert box._grip.isVisibleTo(box)
    box.set_status("Looking for the game")
    assert not box._grip.isVisibleTo(box)
    box.set_status(None)
    assert box._grip.isVisibleTo(box)


def test_width_listeners_hear_the_current_width_and_each_change(monkeypatch):
    box, _ = _resizable(monkeypatch, {"tab_width": 250})
    heard = []
    box.on_tab_w(heard.append)
    assert heard == [250]
    box.set_tab_w(300)
    box.set_tab_w(300)  # no change, nothing to tell
    assert heard == [250, 300]


def test_about_follows_the_width(monkeypatch):
    box, _ = _resizable(monkeypatch, {"tab_width": 300})
    box.show_about("0.1.0", "Up to date", URL)
    _settle()
    assert box.width() == 300 + 24


def test_wrapped_text_takes_fewer_lines_in_a_wider_box(monkeypatch):
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    box, _ = _resizable(monkeypatch)
    tab = QWidget()
    tab.setFixedWidth(overlay.TAB_W)
    text = QLabel("a long line that wraps " * 8)
    text.setWordWrap(True)
    QVBoxLayout(tab).addWidget(text)
    box.select(box.add_tab("B", tab))
    box.on_tab_w(tab.setFixedWidth)
    _settle()
    narrow = box.height()
    box.set_tab_w(overlay.MAX_TAB_W)
    _settle()
    assert box.height() < narrow
    box.set_tab_w(overlay.TAB_W)
    _settle()
    assert box.height() == narrow


def test_four_tabs_and_a_dot_fit(monkeypatch):
    from PySide6.QtWidgets import QWidget

    box = _box(monkeypatch)
    for title in ("EXP", "Path", "Class", "Quests"):
        page = QWidget()
        page.setFixedWidth(overlay.TAB_W)
        box.add_tab(title, page)
    box.set_tab_dot(1, True)
    box.adjustSize()
    assert box.width() == overlay.TAB_W + 24


def test_current_and_touches(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    box = _box(monkeypatch)
    page = QWidget()
    page.setFixedWidth(overlay.TAB_W)
    row = overlay.Row("name", "sub", lambda: None)
    QVBoxLayout(page).addWidget(row)
    for title, p in (("A", page), ("B", QWidget()), ("C", QWidget())):
        box.add_tab(title, p)
    box.show()
    assert box.current == 0
    box.select(2)
    assert (box.current, box.touches) == (2, 0)
    QTest.mouseClick(box._tab_buttons[0], Qt.LeftButton)
    assert (box.current, box.touches) == (0, 1)
    QTest.mouseClick(row, Qt.LeftButton)
    assert box.touches == 2


def test_row_reports_hover(monkeypatch):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication

    _box(monkeypatch)  # the app
    seen = []
    row = overlay.Row("A", "", None, on_hover=seen.append)
    row.show()
    QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    QApplication.sendEvent(row, QEvent(QEvent.Leave))
    row.hide()
    assert seen == [True, False, False]
