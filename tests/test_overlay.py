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
    "which", ["update", "downloading", "failed", "up to date", "couldn't check"]
)
def test_notice_fits_the_tab_width_at_the_longest_version(monkeypatch, which):
    from maplelens import app

    text = {
        "update": app.update_notice("10.10.10"),
        "downloading": app.downloading_notice("10.10.10"),
        "failed": app.UPDATE_FAILED,
        "up to date": app.UP_TO_DATE,
        "couldn't check": app.COULDNT_CHECK,
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
