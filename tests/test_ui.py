from maplelens.readers import ExpValue, Reading
from maplelens.store import DEFAULTS
from maplelens.tools.exp_meter.history import history, open_db


def _play(tool, ticks: int) -> None:
    """Ticks 2.5 s apart from t=1000; each EXP value is read twice, as the meter needs."""
    for i in range(ticks):
        t = 1000.0 + i * 2.5
        exp = ExpValue(1000 + i // 2 * 100, 10 + i // 2 * 0.1)
        tool.update(Reading(t, exp, 50, "Mage", "Ant Tunnel"), None, t)


def test_tool_flushes_open_segment_each_minute(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    app = QApplication.instance() or QApplication([])
    conn = open_db(tmp_path / "h.db")
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), conn)
    _play(tool, 145)  # 6 minutes
    rows = history(conn)
    assert len(rows) == 1  # nothing closed, so this came from the periodic flush
    assert rows[0].active_s >= 120
    tool.shutdown(1000 + 145 * 2.5)
    app.processEvents()


def test_stopping_saves_the_visit_and_starts_afresh(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    conn = open_db(tmp_path / "h.db")
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), conn)
    _play(tool, 145)  # 6 minutes
    before = history(conn)[0].active_s
    tool.stop(1000 + 145 * 2.5)  # EXP turned off in Settings
    assert history(conn)[0].active_s >= before  # the open visit was saved, as on quit
    assert tool._meter.session() is None and tool._meter.rate(2000.0) is None  # a fresh meter


def test_tool_skips_visits_under_five_minutes(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    conn = open_db(tmp_path / "h.db")
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), conn)
    _play(tool, 97)  # 4 minutes
    assert history(conn) == []
    tool.shutdown(1000 + 97 * 2.5)
    assert history(conn) == []


def test_tool_says_when_bar_unreadable(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(tmp_path / "h.db"))

    def label(t, exp):
        tool.update(Reading(t, exp, 50, "Mage", "Ant Tunnel"), None, t)
        return tool._texts[0].text()

    assert label(0, ExpValue(1000, 10)) == "Measuring"  # no rate yet
    assert tool._texts[3].text() == "Session"
    assert label(10, None) == "Measuring"  # 10 s: not yet
    assert label(10.5, None) == "Can't read bar"
    assert "#ffcc33" in tool._texts[0].styleSheet()  # amber, to be seen
    assert label(11, ExpValue(1000, 10)) == "Measuring"
    assert "#ffcc33" not in tool._texts[0].styleSheet()
    tool.update(None, None, 100)  # game gone: the clock restarts when it's back
    assert label(105, None) == "Measuring"


def test_closing_history_window_does_not_quit(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import HistoryWindow

    app = QApplication.instance() or QApplication([])
    win = HistoryWindow(open_db(tmp_path / "h.db"))
    win.show()
    survived = []
    QTimer.singleShot(0, win.close)
    QTimer.singleShot(200, lambda: survived.append(1))
    QTimer.singleShot(300, app.quit)  # exec() must still be running at 200 ms
    app.exec()
    assert survived == [1]


def test_history_window_stays_over_the_game_without_taking_focus(monkeypatch, tmp_path):
    import sys

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import HistoryWindow

    QApplication.instance() or QApplication([])
    win = HistoryWindow(open_db(tmp_path / "h.db"))
    assert win.windowType() == Qt.Tool
    assert win.testAttribute(Qt.WA_ShowWithoutActivating)
    if sys.platform != "darwin":  # the Mac's panel does this itself, in native_setup
        assert win.windowFlags() & Qt.WindowStaysOnTopHint
        assert win.windowFlags() & Qt.WindowDoesNotAcceptFocus


def test_quit_menu_item_saves_and_quits(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from maplelens.app import build_box
    from maplelens.tools.exp_meter.ui import ExpMeterTool

    app = QApplication.instance() or QApplication([])
    conn = open_db(tmp_path / "h.db")
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), conn)
    _play(tool, 125)  # just over 5 minutes, so the visit is kept
    box = build_box(dict(DEFAULTS, boxes={}), lambda: None, [tool])
    (quit_item,) = [a for a in box.actions() if a.text() == "Quit MapleLens"]
    save = lambda: tool.shutdown(1320.0)  # noqa: E731 - what app.py connects
    app.aboutToQuit.connect(save)
    QTimer.singleShot(0, quit_item.trigger)
    timed_out = []
    QTimer.singleShot(2000, lambda: (timed_out.append(1), app.exit()))  # no hang if Quit fails
    try:
        app.exec()
    finally:
        app.aboutToQuit.disconnect(save)
    assert not timed_out
    assert history(conn)[0].last == 1320.0


def test_history_button_on_exp_tab(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QPushButton

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(tmp_path / "h.db"))
    assert tool.title == "EXP"
    (button,) = [b for b in tool.tab.findChildren(QPushButton) if b.text() == "History"]
    button.click()
    assert tool._history.isVisible()
    tool._history.close()


def test_tick_updates_labels_in_place(monkeypatch, tmp_path):
    """Rebuilding the labels each tick blanks the box for a frame: it flickered."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(tmp_path / "h.db"))
    before = tool.tab.findChildren(QLabel)
    tool.update(None, None, 1.0)
    assert tool.tab.findChildren(QLabel) == before


def test_history_is_a_secondary_button(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QPushButton

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    tool = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(tmp_path / "h.db"))
    (button,) = [b for b in tool.tab.findChildren(QPushButton) if b.text() == "History"]
    assert button.property("kind") == "secondary"


def test_history_window_refresh_without_job(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel

    from maplelens.tools.exp_meter.ui import HistoryWindow

    QApplication.instance() or QApplication([])
    win = HistoryWindow(open_db(tmp_path / "h.db"))
    win.refresh(None, None)
    texts = [w.text() for w in win.findChildren(QLabel)]
    assert "Best maps: waiting for your class and level" in texts


def test_history_map_cell_short_name_full_tooltip(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

    from maplelens.tools.exp_meter.history import save_segment
    from maplelens.tools.exp_meter.meter import Segment
    from maplelens.tools.exp_meter.ui import HistoryWindow

    QApplication.instance() or QApplication([])
    conn = open_db(tmp_path / "h.db")
    title = "Victoria Island / Henesys Hunting Ground I"
    save_segment(conn, Segment(0, 300, title, "Hero", 44, 600, 1.2, 60.0))
    win = HistoryWindow(conn, lambda j: {j})
    win.refresh("Hero", 44)
    (table,) = win.findChildren(QTableWidget)
    assert table.item(0, 0).text() == "Henesys Hunting Ground I"
    assert table.item(0, 0).toolTip() == title
    shown = table.fontMetrics().horizontalAdvance("Henesys Hunting Ground I")
    assert table.columnWidth(0) > shown  # the name fits, not cut to "Henesys …"
    texts = [w.text() for w in win.findChildren(QLabel)]
    assert "Best for Hero, Lv 44 (±3)" in texts
    assert "36,000 EXP/h" in texts


def _tool(monkeypatch, tmp_path, settings=None, **kw):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.exp_meter.ui import ExpMeterTool

    QApplication.instance() or QApplication([])
    return ExpMeterTool(settings or dict(DEFAULTS, boxes={}), open_db(tmp_path / "h.db"), **kw)


def _pin_button(tool):
    from PySide6.QtWidgets import QPushButton

    (button,) = [b for b in tool.tab.findChildren(QPushButton) if b.text() in {"Pin", "Unpin"}]
    return button


def test_pin_button_toggles_setting_label_and_footer(monkeypatch, tmp_path):
    settings, saves, shown = dict(DEFAULTS, boxes={}), [], []
    tool = _tool(
        monkeypatch, tmp_path, settings, save=lambda: saves.append(1), show_pin=shown.append
    )
    pin = _pin_button(tool)
    assert not tool.pinned and pin.text() == "Pin" and pin.property("kind") == "secondary"
    pin.click()
    assert settings["pin_exp"] and tool.pinned and pin.text() == "Unpin"
    assert shown == [True] and saves == [1]
    pin.click()
    assert not settings["pin_exp"] and not tool.pinned and pin.text() == "Pin"
    assert shown == [True, False] and saves == [1, 1]


def test_pinned_setting_is_read_at_start(monkeypatch, tmp_path):
    tool = _tool(monkeypatch, tmp_path, dict(DEFAULTS, boxes={}, pin_exp=True))
    assert tool.pinned and _pin_button(tool).text() == "Unpin"


def test_pin_line_follows_the_tick_and_opens_the_tab(monkeypatch, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    opened = []
    tool = _tool(monkeypatch, tmp_path, open_tab=lambda: opened.append(1))
    tool.update(None, None, 1.0)
    assert tool.pin_line.text() == "Waiting for game"
    tool.update(Reading(2.0, ExpValue(1000, 10), 50, "Mage", "Ant Tunnel"), None, 2.0)
    assert tool.pin_line.text() == "Measuring…"
    QTest.mouseClick(tool.pin_line, Qt.LeftButton)
    assert opened == [1]


def test_longest_pin_line_fits_the_tab(monkeypatch, tmp_path):
    from maplelens import overlay

    tool = _tool(monkeypatch, tmp_path)
    tool.pin_line.set_text("100.00%/h · Lvl in 99h 59m", False)
    assert tool.pin_line.sizeHint().width() <= overlay.TAB_W


def test_pin_line_is_never_blank_before_the_first_tick(monkeypatch, tmp_path):
    assert _tool(monkeypatch, tmp_path).pin_line.text() == "Waiting for game"


def test_pin_shows_the_line_even_if_saving_fails(monkeypatch, tmp_path):
    import pytest

    def locked():
        raise OSError("settings.json is locked")

    shown = []
    tool = _tool(monkeypatch, tmp_path, save=locked, show_pin=shown.append)
    with pytest.raises(OSError):
        tool._toggle_pin()
    assert shown == [True]  # the line follows the button; only the save is lost
