import sys

import pytest
from pytest import approx

from maplelens.readers import Reading
from maplelens.readers.minimap_pos import MinimapView
from maplelens.store import DEFAULTS
from maplelens.tools.path_arrow.maps import MapInfo, Minimap, Portal

MM = Minimap(2000, 1000, 1000, 500)  # fits a 125x62 px minimap window
MID = MinimapView((125, 62), (62.5, 31.0), ())  # the dot mid-map: world (0, 0)
RECT = (0, 0, 1366, 768)
OPEN = "Open your minimap to see the arrow"


def mk(id, name, portals=(), street="Road", minimap=MM, npcs=()):
    portals = tuple(Portal(*p) for p in portals)
    return MapInfo(id, street, name, False, minimap, portals, None, npcs)


MAPS = {
    m.id: m
    for m in [
        mk("A", "Apple", [(300, -300, "B")]),
        mk("B", "Berry", [(0, 0, "A"), (0, 0, "C"), (0, 0, "M")]),
        mk("C", "Cherry", [(0, 0, "B")]),
        mk("M", "Hush", [(0, 0, "B")], minimap=None),  # reachable, but no minimap
        mk("D", "Date"),  # nothing leads here
        mk("X", "Xylo", [(0, 0, "C")], street="Bay"),
        mk("N", "Nomap", [(0, 0, "B")], minimap=None),
        mk("G", "Grand", [(0, 0, "B")], minimap=Minimap(6400, 1600, 800, 800)),  # no NPCs
        # Same-title neighbours, as Maple Road / Mushroom Town (88x47 vs 94x53 px).
        mk("P", "Pair", [(500, 0, "Q")], minimap=Minimap(1408, 760, 479, 295)),
        mk("Q", "Pair", [(-500, 0, "P"), (450, 300, "R")], minimap=Minimap(1498, 850, 299, 445)),
        mk("R", "Rose", [(0, 0, "Q")]),
        mk("L", "The Very Long Road Past The Old Mushroom Forest Gate", [(0, 0, "B")]),
        mk("K", "Keep", [(0, 0, "B")], minimap=Minimap(6400, 1600, 800, 800), npcs=((0, 0),) * 3),
        mk("T1", "Twin", [(0, 0, "B")], street="Hill"),
        mk("T2", "Twin", [(0, 0, "B")], street="Dale"),
        mk("H", "Hollow", [(300, -300, "B", True)]),  # a hidden portal
    ]
}


def title(id):
    return MAPS[id].title


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.overlay import Layer
    from maplelens.tools.path_arrow.ui import PathArrowTool

    QApplication.instance() or QApplication([])

    def build(settings=None, on_changed=lambda: None, typing=lambda on: None):
        layer = Layer()
        layer.show()
        settings = dict(DEFAULTS, boxes={}) if settings is None else settings
        return PathArrowTool(settings, on_changed, layer, typing, MAPS)

    return build


def feed(tool, map_name, t=0.0, view=MID, rect=RECT, times=2):
    for i in range(times):
        tool.update(
            Reading(t + i * 0.5, None, None, None, map_name, minimap=view), rect, t + i * 0.5
        )


def go(tool, at, dest, t=0.0):
    feed(tool, title(at), t)
    tool._search.setText(MAPS[dest].name)
    tool._start.click()


def centre(w):
    return w.x() + w.width() / 2, w.y() + w.height() / 2


def test_search_lists_matches(make):
    tool = make()
    tool._search.setText("b")
    shown = [tool._matches.item(i).text() for i in range(tool._matches.count())]
    assert shown == ["Berry", "Xylo"]  # Xylo's street is "Bay"


def test_no_route_message(make):
    tool = make()
    go(tool, "A", "D")
    assert tool._info.text() == "No route from here to Date"
    assert not tool.running


def test_start_shows_arrow_and_header(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    go(tool, "A", "C")
    assert tool.running
    assert tool._header.text() == "To Cherry · 1 of 3"
    assert tool.arrow.isVisible()
    assert centre(tool.arrow) == approx((683, 545 - ui.ARROW_DY), abs=1)
    assert tool.arrow.angle == approx(-45)  # up and right, to the portal at (300, -300)


def test_one_frame_misread_does_not_reroute(make):
    tool = make()
    go(tool, "A", "C")
    steps, angle = tool.trip.steps, tool.arrow.angle
    feed(tool, title("X"), 1.0, times=1)
    assert tool.arrow.isVisible() and tool.arrow.angle == angle  # held, not re-aimed with an
    # unconfirmed map's minimap
    feed(tool, title("A"), 2.0, times=1)
    feed(tool, None, 3.0, times=1)
    feed(tool, title("A"), 4.0, times=1)
    assert tool.trip.steps is steps and tool.trip.index == 0


def test_wrong_map_reroutes(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("X"), 1.0)
    assert [s.map_id for s in tool.trip.steps] == ["X", "C"]
    assert tool._header.text() == "To Cherry · 1 of 2"


def test_route_list_marks_done_and_here(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("B"), 1.0)
    assert tool._header.text() == "To Cherry · 2 of 3"
    text = tool._route_list.text()
    assert "<s>" in text.split("Apple")[0]  # done: struck through
    assert "▸" in text.split("Berry")[0].split("Apple")[1]  # yours
    assert "<s>" not in text.split("Apple")[1]


def test_arrival_then_search(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("B"), 1.0)
    feed(tool, title("C"), 2.0)
    assert tool._header.text() == "Arrived at Cherry"
    assert not tool.arrow.isVisible()
    assert not tool.running
    assert not tool._choose.isVisibleTo(tool.tab)
    feed(tool, title("C"), 2.5 + 5.1, times=1)
    assert tool._choose.isVisibleTo(tool.tab)
    assert tool._header.text() == "From: Cherry (where you are)"
    assert not tool.running


def test_minimap_message_after_3s(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, None, 10.0, view=None, times=1)
    feed(tool, None, 12.0, view=None, times=1)
    assert not tool._message.isVisibleTo(tool.tab)
    feed(tool, None, 13.1, view=None, times=1)
    assert tool._message.text() == OPEN and tool._message.isVisibleTo(tool.tab)
    assert not tool.arrow.isVisible()
    assert tool.running
    feed(tool, title("A"), 14.0)  # it comes back on its own
    assert not tool._message.isVisibleTo(tool.tab) and tool.arrow.isVisible()


def test_dot_missing_message_after_the_hold(make):
    """The reader gives no minimap when it doesn't find the dot exactly once: the common
    one-frame miss. Held, it says nothing; past the hold, the reason shows."""
    tool = make()
    go(tool, "A", "C")  # last aimed at t=0.5
    feed(tool, title("A"), 1.0, view=None, times=1)
    assert tool.arrow.isVisible()
    assert not tool._message.isVisibleTo(tool.tab)  # no "Open your minimap" flash
    feed(tool, title("A"), 2.6, view=None, times=1)  # 2.1 s since it was last aimed
    assert tool._message.text() == OPEN and tool._message.isVisibleTo(tool.tab)
    assert not tool.arrow.isVisible()


def test_unknown_map_message(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    go(tool, "A", "C")
    feed(tool, "Road / Nowhere", 1.0)
    assert tool._info.text() == ui.NOT_LISTED
    assert not tool.arrow.isVisible()
    assert tool.running


def test_no_minimap_message(make):
    tool = make()
    go(tool, "N", "C", 0.0)
    assert tool.running and tool._route_list.isVisibleTo(tool.tab)
    assert tool._info.text() == "No minimap on this map"
    assert not tool.arrow.isVisible()


def test_no_arrow_on_big_map_without_npcs(make):
    tool = make()
    clipped = MinimapView((200, 100), (100.0, 50.0), ())  # picture 400x100 px
    feed(tool, title("G"), view=clipped)
    tool._search.setText("Cherry")
    tool._start.click()
    assert tool.running
    assert tool._info.text() == "No arrow on this map yet"
    assert not tool.arrow.isVisible()


def test_start_disabled_when_map_unknown(make):
    tool = make()
    tool._search.setText("Cherry")
    assert not tool._start.isEnabled()
    assert tool._header.text() == "From: (can't read your map yet)"
    feed(tool, "Road / Nowhere")
    assert not tool._start.isEnabled()
    assert tool._header.text() == "From: Nowhere"
    feed(tool, title("A"), 1.0)
    assert tool._start.isEnabled()
    assert tool._header.text() == "From: Apple (where you are)"


def test_taxi_choice_saved(make):
    calls = []
    settings = dict(DEFAULTS, boxes={})
    tool = make(settings, lambda: calls.append(1))
    assert tool._taxi.isChecked() and tool._taxi.text() == "Use taxi"
    tool._taxi.setChecked(False)
    go(tool, "A", "C")
    assert settings["path_taxi"] is False and calls == [1]
    tool._stop.click()
    go(tool, "A", "C", 1.0)
    assert calls == [1]  # unchanged: not saved again


def test_arrow_follows_game_rect_size(make):
    tool = make()
    go(tool, "A", "C")
    small = centre(tool.arrow)
    feed(tool, title("A"), 1.0, rect=(0, 0, 2732, 1536))
    assert centre(tool.arrow) == approx((2 * small[0], 2 * small[1]), abs=1)


def test_stop_ends_route(make):
    tool = make()
    go(tool, "A", "C")
    tool._stop.click()
    assert not tool.running and not tool.arrow.isVisible()
    assert tool._choose.isVisibleTo(tool.tab)


def test_typing_toggles_focus(make):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    calls = []
    tool = make(typing=calls.append)
    tool.tab.show()
    QTest.mouseClick(tool._search, Qt.LeftButton)
    assert calls == [True]
    QTest.keyClick(tool._search, Qt.Key_Escape)
    assert calls == [True, False]
    QTest.mouseClick(tool._search, Qt.LeftButton)
    go(tool, "A", "C")
    assert calls == [True, False, True, False]
    tool.tab.close()


def test_same_title_neighbours_told_apart_by_minimap_size(make):
    p_view = MinimapView((88, 47), (44.0, 23.5), ())
    q_view = MinimapView((94, 53), (47.0, 26.5), ())
    tool = make()
    feed(tool, title("P"), view=p_view)
    tool._search.setText("Rose")
    tool._start.click()
    assert [s.map_id for s in tool.trip.steps] == ["P", "Q", "R"]
    assert tool.arrow.isVisible()
    angle = tool.arrow.angle
    feed(tool, title("Q"), 1.0, view=q_view, times=1)  # same title, Q's minimap
    assert tool.arrow.angle == angle  # held: never re-aimed with P's minimap formula
    feed(tool, title("Q"), 1.5, view=q_view, times=1)
    assert tool._header.text() == "To Rose · 2 of 3"
    assert tool.arrow.isVisible() and tool.arrow.angle == approx(
        90
    )  # straight down: Q puts you at (450, -20)


def test_matches_show_three_rows(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    tool._search.setText("r")  # every "Road" map
    m = tool._matches
    assert m.count() > ui.MATCH_ROWS
    assert m.maximumHeight() == m.sizeHintForRow(0) * ui.MATCH_ROWS + 2 * m.frameWidth()


def test_long_names_elide_to_the_box_width(make):
    from maplelens.overlay import Box
    from maplelens.tools.path_arrow import ui

    tool = make()
    box = Box("t", {}, lambda: None)
    box.add_tab("Path", tool.tab)
    box.show()  # a shown box's pages size from their raw hints
    feed(tool, title("L"))
    # Mac fonts are wider, so fewer letters fit before the cut
    prefix = "From: The Ve" if sys.platform == "win32" else "From: The"
    assert tool._header.text().startswith(prefix) and "…" in tool._header.text()
    assert tool._header.text().endswith("(where you are)")
    tool._search.setText("r")  # the full, scrolling list
    width = ui.TAB_W + 24  # the box's 12 px side margins
    assert box.sizeHint().width() == width
    tool._search.setText("Cherry")
    tool._start.click()
    assert "…" in tool._route_list.text()
    assert box.sizeHint().width() == width
    tool._stop.click()
    feed(tool, title("A"), 1.0)  # short names: the box keeps its width
    assert box.sizeHint().width() == width
    box.close()


class _Cls:
    dot = False
    open = False
    title = "Class"

    def __init__(self):
        from PySide6.QtWidgets import QLabel

        self.tab = QLabel()

    def set_tab_w(self, width):
        self.tab.setFixedWidth(width)

    def update(self, *_):
        pass

    def hide_marks(self):
        pass


def test_go_starts_a_trip(make):
    tool = make()
    feed(tool, title("A"))
    tool.go("C")
    assert tool.running and tool.trip.goal == "C"


def test_go_before_the_map_is_known_picks_only(make):
    tool = make()
    tool.go("C")
    assert not tool.running and tool._search.text() == "Cherry"


def test_tick_feeds_both_tools_and_dots_path_tab(make):
    from maplelens.app import build_box, update_tools
    from maplelens.tools.exp_meter.history import open_db
    from maplelens.tools.exp_meter.ui import ExpMeterTool

    path, cls = make(), _Cls()
    exp = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(":memory:"))
    box = build_box({"boxes": {}}, lambda: None, [exp, path, cls])
    widths = set()
    for i in (0, 1):
        box.select(i)
        widths.add(box.sizeHint().width())
    assert len(widths) == 1  # same box width on both tabs
    update_tools(box, exp, path, cls, _Cls(), _Cls(), None, None, 1.0, set())
    assert box._tab_dots[1].isHidden()
    go(path, "A", "C", 1.0)
    assert path.running
    update_tools(box, exp, path, cls, _Cls(), _Cls(), None, None, 2.0, set())
    assert not box._tab_dots[1].isHidden()
    box.close()
    exp.shutdown(3.0)


def test_clipped_map_part_without_markers_says_why(make):
    tool = make()
    clipped = MinimapView((200, 100), (100.0, 50.0), ())  # no NPC markers in the window
    feed(tool, title("K"), view=clipped)
    tool._search.setText("Cherry")
    tool._start.click()
    assert tool._info.text() == "No arrow on this part of the map yet"
    assert not tool.arrow.isVisible()


MISS = MinimapView((135, 62), (67.5, 31.0), ())  # player_world None for this frame only


def test_unclipped_frame_miss_has_no_line(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("A"), 1.0, view=MISS, times=1)
    assert not tool._message.isVisibleTo(tool.tab) and not tool._info.isVisibleTo(tool.tab)


@pytest.mark.parametrize(
    "last, now, kept", [(5.0, 5.0, True), (5.0, 7.0, True), (5.0, 7.01, False), (None, 5.0, False)]
)
def test_held(last, now, kept):
    from maplelens.tools.path_arrow.ui import held

    assert held(last, now) is kept


def test_a_missed_frame_keeps_the_arrow_for_two_seconds(make):
    tool = make()
    go(tool, "A", "C")  # last aimed at t=0.5
    where, angle = tool.arrow.pos(), tool.arrow.angle
    feed(tool, title("A"), 1.0, view=MISS, times=1)
    feed(tool, title("A"), 2.5, view=MISS, times=1)
    assert tool.arrow.isVisible() and tool.arrow.pos() == where and tool.arrow.angle == angle
    feed(tool, title("A"), 2.6, view=MISS, times=1)  # 2.1 s since it was last aimed
    assert not tool.arrow.isVisible()


def test_the_hold_never_outlasts_stop_or_a_new_map(make):
    tool = make()
    go(tool, "A", "C")
    tool.stop()
    assert not tool.arrow.isVisible()
    go(tool, "A", "C", 1.0)
    feed(tool, title("B"), 2.0)  # on B now, aimed afresh
    assert tool.arrow.isVisible()
    tool._here = MAPS["A"]  # as if the map changed under a held arrow
    feed(tool, None, 2.6, view=MISS, times=1)
    assert not tool.arrow.isVisible()


@pytest.mark.parametrize("size", [24, 36, 72])
def test_the_arrow_grows_about_the_same_centre(make, size):
    from maplelens.tools.path_arrow import ui

    tool = make()
    go(tool, "A", "C")
    tool.set_arrow_size(size)
    assert tool.arrow.width() == size
    assert centre(tool.arrow) == approx((683, 545 - ui.ARROW_DY), abs=1)
    feed(tool, title("A"), 1.0)  # placed afresh at the new size
    assert centre(tool.arrow) == approx((683, 545 - ui.ARROW_DY), abs=1)
    assert tool._settings["arrow_size"] == size


def test_the_saved_size_is_used_from_the_start(make):
    tool = make(dict(DEFAULTS, boxes={}, arrow_size=60))
    assert tool.arrow.width() == 60


def test_arrow_off_keeps_the_route_running(make):
    saved = []
    tool = make(on_changed=lambda: saved.append(1))
    go(tool, "A", "C")
    tool.set_arrow_on(False)
    assert not tool.arrow.isVisible() and tool.running and saved
    feed(tool, title("B"), 1.0)
    assert not tool.arrow.isVisible() and tool._header.text() == "To Cherry · 2 of 3"
    tool.set_arrow_on(True)
    assert tool.arrow.isVisible()


def test_the_path_section_sets_the_arrow(make):
    from PySide6.QtWidgets import QCheckBox, QLabel, QSlider

    from maplelens.tools.path_arrow import ui

    tool = make()
    section = tool.settings_section()  # held: its widgets live as long as it does
    (show,) = section.findChildren(QCheckBox)
    (slider,) = section.findChildren(QSlider)
    assert show.text() == ui.SHOW_ARROW and show.isChecked()
    slider.setValue(slider.maximum())
    assert tool.arrow.width() == 72 and tool._preview.width() == 72
    assert any(w.text() == "Arrow size: 72 px" for w in section.findChildren(QLabel))
    show.setChecked(False)
    assert tool._settings["arrow_on"] is False
    assert not slider.isEnabled() and not tool._swatches[0].isEnabled()  # moot with no arrow


def test_a_swatch_colours_the_arrow_and_the_preview(make):
    from maplelens.store import ARROW_COLORS

    saved = []
    tool = make(on_changed=lambda: saved.append(1))
    go(tool, "A", "C")
    section = tool.settings_section()  # noqa: F841 - held: the swatches live as long as it
    assert [s.color for s in tool._swatches] == list(ARROW_COLORS)
    assert [s.chosen for s in tool._swatches] == [True] + [False] * (len(ARROW_COLORS) - 1)
    red = next(s for s in tool._swatches if s.toolTip() == "Red")
    red.click()
    assert tool.arrow.color == tool._preview.color == "#ff5a5a" == tool._settings["arrow_color"]
    assert red.chosen and not tool._swatches[0].chosen and saved
    assert tool.arrow.isVisible()  # recoloured in place


def test_the_saved_colour_is_used_from_the_start(make):
    tool = make(dict(DEFAULTS, boxes={}, arrow_color="#4fd8ff"))
    assert tool.arrow.color == "#4fd8ff"
