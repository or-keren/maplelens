import sys

import pytest
from pytest import approx

from maplelens.gamedata import ICONS, PICTURES, GameData, Item, Mob, Npc, SpotData
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


# Pictures from the shipped folders: monster 1, NPCs 1 and 10 and item 4000004 have one;
# NPC 999999 and the test maps have none.
GAME = GameData(
    {
        1: Npc(1, "Mina", (("B", 10, 20),)),  # sells the shell
        10: Npc(10, "Luna", (("A", 1, 2), ("C", 3, 4), ("Z", 0, 0))),  # Z: not listed
        999999: Npc(999999, "Faceless", (("C", 5, 6),)),  # one place, no picture
    },
    {
        1: Mob(1, "Snail", {"A": 2, "C": 9}, 1),
        2: Mob(2, "Snail", {"M": 5}, 2),  # the same name: one match
        3: Mob(3, "Lonely", {"D": 4}, 3),  # nothing leads to D
        5: Mob(5, "Pig", {"C": 3, "M": 1}, 4),
        6: Mob(6, "Cherry Ghost", {"Z": 1}, 5),  # only off the list
    },
    {
        4000004: Item(4000004, "Snail Shell", ((1, 40.0), (5, None)), (1,)),
        4000000: Item(4000000, "Cherry Coin", ((6, 10.0),), ()),
    },
)
SPOTS = SpotData({}, {}, PICTURES, ICONS)


def rows(lst):
    return [lst.itemWidget(lst.item(i)) for i in range(lst.count())]


def names(lst):
    return [r.name for r in rows(lst)]


def lines(lst):
    return [r.line for r in rows(lst)]


def matches(lst):
    from PySide6.QtCore import Qt

    return [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]


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
        return PathArrowTool(settings, on_changed, layer, typing, MAPS, game=GAME, spots=SPOTS)

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
    assert names(tool._matches) == ["Berry", "Xylo"]  # Xylo's street is "Bay"


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
    steps = tool.trip.steps
    feed(tool, title("X"), 1.0, times=1)
    assert not tool.arrow.isVisible()  # not aimed with an unconfirmed map's minimap
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


def test_dot_missing_message_immediately(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("A"), 1.0, view=None, times=1)
    assert tool._message.text() == OPEN
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
    feed(tool, title("Q"), 1.0, view=q_view, times=1)  # same title, Q's minimap
    assert not tool.arrow.isVisible()  # never aimed with P's minimap formula
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


def test_unclipped_frame_miss_has_no_line(make):
    tool = make()
    go(tool, "A", "C")
    feed(tool, title("A"), 1.0, view=MinimapView((135, 62), (67.5, 31.0), ()), times=1)
    assert not tool.arrow.isVisible()  # player_world None for this frame only
    assert not tool._message.isVisibleTo(tool.tab) and not tool._info.isVisibleTo(tool.tab)


def test_no_route_note_clears_on_map_change(make):
    tool = make()
    go(tool, "A", "D")
    assert tool._info.text() == "No route from here to Date"
    feed(tool, title("B"), 1.0)
    assert not tool._message.isVisibleTo(tool.tab) and not tool._info.isVisibleTo(tool.tab)


def test_no_reading_starts_the_minimap_clock(make):
    tool = make()
    go(tool, "A", "C")
    tool.update(None, RECT, 10.0)
    tool.update(None, RECT, 12.0)
    assert not tool._message.isVisibleTo(tool.tab)
    tool.update(None, RECT, 13.1)
    assert tool._message.text() == OPEN
    assert tool.running


def test_stale_map_after_3s_unreadable(make):
    tool = make()
    feed(tool, title("A"))
    tool._search.setText("Cherry")
    assert tool._start.isEnabled()
    feed(tool, None, 10.0, view=None, times=1)
    feed(tool, None, 12.0, view=None, times=1)
    assert tool._header.text() == "From: Apple (where you are)"  # a short gap: still trusted
    feed(tool, None, 13.1, view=None, times=1)
    assert tool._header.text() == "From: (can't read your map yet)"
    assert not tool._start.isEnabled()
    feed(tool, title("A"), 14.0)
    assert tool._start.isEnabled()
    tool._start.click()
    feed(tool, None, 20.0, view=None, times=1)
    feed(tool, None, 23.1, view=None, times=1)
    assert tool.running  # a running trip is kept


def test_duplicate_names_show_their_street(make):
    tool = make()
    tool._search.setText("twin")
    assert names(tool._matches) == ["Twin", "Twin"]
    assert set(lines(tool._matches)) == {"Map · Hill", "Map · Dale"}  # told apart by street


def test_tool_errors_do_not_stop_the_other_tool(make, capsys):
    from PySide6.QtWidgets import QLabel

    from maplelens.app import update_tools
    from maplelens.overlay import Box

    class Broken:
        def update(self, *args):
            raise ValueError("boom")

    path = make()
    box = Box("t", {}, lambda: None)
    box.add_tab("EXP", QLabel())
    box.add_tab("Path", path.tab)
    box.add_tab("Class", QLabel())
    go(path, "A", "C")
    seen = set()
    for t in (1.0, 1.5):
        r = Reading(t, None, None, None, title("B"), minimap=MID)
        update_tools(box, Broken(), path, _Cls(), _Cls(), _Cls(), r, RECT, t, seen)
    assert path._header.text() == "To Cherry · 2 of 3"  # path still ran
    assert not box._tab_dots[1].isHidden()
    assert capsys.readouterr().err.count("ValueError: boom") == 1  # printed once

    def broken_path(*args):
        raise ValueError("bang")

    path.update = broken_path
    update_tools(box, Broken(), path, _Cls(), _Cls(), _Cls(), None, RECT, 2.0, seen)
    assert not path.arrow.isVisible()  # hidden, not frozen at its last spot


def test_clicking_a_match_picks_it(make):
    tool = make()
    feed(tool, title("C"))
    tool._search.setText("Twin")
    m = tool._matches
    second = m.item(1)
    m.itemClicked.emit(second)
    assert tool._search.text() == m.itemWidget(second).name  # the field shows the pick
    assert m.isHidden()  # and the list closes on it
    assert m.currentItem() is second  # what Start goes to
    assert tool._start.isEnabled()


def test_hidden_portal_hint(make):
    from maplelens.tools.path_arrow.ui import HIDDEN

    tool = make()
    go(tool, "H", "B")
    feed(tool, title("H"), 1.0)
    assert tool._message.text() == HIDDEN and tool._message.isVisibleTo(tool.tab)
    assert tool.arrow.isVisible()


def test_arrow_on_forest_north_middle_by_picture(make):
    # Real data and a real frame: mid-map, too few markers, so only the picture places us.
    from pathlib import Path

    import cv2

    from maplelens.readers.minimap_pos import read_view
    from maplelens.tools.path_arrow import ui
    from maplelens.tools.path_arrow.maps import load

    shot = Path(__file__).parent / "fixtures" / "screens" / "pos_fne_mid_2560x1440_100.png"
    view = read_view(cv2.imread(str(shot)))
    maps = load()
    tool = make()
    tool.maps = maps
    here = maps["010002070"]
    feed(tool, here.title, view=view)
    tool._search.setText("Tree Dungeon, Forest Up North I")
    tool._start.click()
    feed(tool, here.title, 1.0, view=view)
    assert tool.trip is not None and tool.arrow.isVisible()
    assert tool._message.text() in ("", ui.HIDDEN)


def test_read_but_unlisted_map_names_itself(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    feed(tool, "Road / Nowhere")  # read twice: confirmed, not in the data
    assert tool._header.text() == "From: Nowhere"
    assert tool._info.text() == ui.NOT_LISTED and tool._info.isVisibleTo(tool.tab)
    assert not tool._message.isVisibleTo(tool.tab)


def test_start_and_stop_kinds(make):
    tool = make()
    assert tool._start.property("kind") == "primary"
    assert tool._stop.property("kind") == "secondary"


def test_a_wider_tab_shows_more_of_a_long_name(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    feed(tool, title("L"))
    narrow = tool._header.text()
    tool.set_tab_w(480)  # redraws at once, without waiting for the next reading
    assert len(tool._header.text()) > len(narrow)
    assert tool.tab.maximumWidth() == 480
    tool._search.setText("Cherry")
    tool._start.click()
    wide_route = tool._route_list.text()
    tool.set_tab_w(ui.TAB_W)
    assert len(tool._route_list.text()) < len(wide_route)


def test_build_box_gives_every_tool_the_saved_width(make):
    from maplelens.app import build_box
    from maplelens.tools.exp_meter.history import open_db
    from maplelens.tools.exp_meter.ui import ExpMeterTool

    path, cls = make(), _Cls()
    exp = ExpMeterTool(dict(DEFAULTS, boxes={}), open_db(":memory:"))
    box = build_box({"boxes": {}, "tab_width": 300}, lambda: None, [exp, path, cls])
    assert [t.tab.maximumWidth() for t in (exp, path, cls)] == [300, 300, 300]
    box.close()


def _npc_world(tool, x, y):
    """A reading with the player at world (x, y) on the confirmed map."""
    return MinimapView((125, 62), (62.5 + x / 16, 31.0 + y / 16), ())


def test_npc_trip_points_then_arrives_once_on_screen(make):
    narrow = (0, 0, 400, 768)  # a 400 px view: the NPC at 0 is on screen 130..270 only
    tool = make()
    feed(tool, title("B"))
    tool.go("C", (0, 0), "Luke")
    feed(tool, title("C"), 1.0, view=_npc_world(tool, 400, 0), rect=narrow)  # NPC at -200
    assert tool.running and tool.arrow.isVisible()
    assert tool.heading() == ("C", (0, 0), 0)
    near_edge = _npc_world(tool, 100, -108)  # the NPC 100 px in from the left edge
    feed(tool, title("C"), 1.5, view=near_edge, rect=narrow)
    assert tool.running
    # Standing by the NPC: the dot reads ~108 px above its foothold (Henesys, in game),
    # so the model puts its feet at y 653 of 768, under the side margin.
    feed(tool, title("C"), 2.0, view=_npc_world(tool, 50, -108), rect=narrow)
    assert tool._header.text() == "Arrived at Luke"
    assert not tool.running


def test_npc_trip_without_minimap_arrives_on_map(make):
    from maplelens.tools.path_arrow import ui

    tool = make()
    feed(tool, title("B"))
    tool.go("M", (0, 0), "Luke")
    feed(tool, title("M"), 1.0)
    assert tool._header.text() == ui.ON_MAP.format("Luke")
    assert not tool.running


def test_heading_stop_hops(make):
    tool = make()
    assert tool.hops("C") is None  # map not known yet
    feed(tool, title("A"))
    assert tool.hops("C") == 2
    tool.go("C", (5, 6), "Luke")
    assert tool.heading() == ("C", (5, 6), 2)
    tool.stop()
    assert tool.heading() is None and not tool.running


def test_route_steps_with_a_long_shared_name_stay_apart(make):
    import re

    from maplelens.overlay import Layer
    from maplelens.tools.path_arrow.ui import PathArrowTool

    make()  # the app
    swamp = "The Very Long Swamp of Despair Past The Old Forest Gate"
    maps = {
        m.id: m
        for m in [
            mk("S0", "Start", [(0, 0, "S1")]),
            mk("S1", swamp + " I", [(0, 0, "S0"), (0, 0, "S2")]),
            mk("S2", swamp + " II", [(0, 0, "S1"), (0, 0, "S3")]),
            mk("S3", swamp + " III", [(0, 0, "S2")]),
        ]
    }
    layer = Layer()
    layer.show()
    tool = PathArrowTool(dict(DEFAULTS, boxes={}), lambda: None, layer, lambda on: None, maps)
    feed(tool, maps["S0"].title)
    tool._search.setText(maps["S3"].name)
    tool._start.click()
    rows = [re.sub("<[^>]+>", "", r) for r in tool._route_list.text().split("<br>")]
    for row, numeral in zip(rows[1:], (" I", " II", " III"), strict=True):
        assert "…" in row and row.endswith(numeral)  # cut, but the end that differs stays


def pick(tool, text, n=0):
    tool._search.setText(text)
    tool._matches.itemClicked.emit(tool._matches.item(n))


def test_search_shows_kinds(make):
    tool = make()
    tool._search.setText("cherry")
    got = [(m.kind, m.name, m.line) for m in matches(tool._matches)]
    assert got == [
        ("map", "Cherry", "Map · Road"),
        ("monster", "Cherry Ghost", "Monster · Lv 5 · 0 maps"),
        ("item", "Cherry Coin", "Item · dropped by Cherry Ghost"),
    ]
    assert names(tool._matches) == [n for _, n, _ in got]
    assert lines(tool._matches) == [line for _, _, line in got]
    tool._search.setText("faceless")
    (row,) = rows(tool._matches)
    assert row.line == "NPC · Cherry"
    assert row.picture.pixmap().isNull() and row.picture.width() == 28  # an empty slot
    tool._search.setText("snail")
    assert not rows(tool._matches)[0].picture.pixmap().isNull()  # the monster's icon


def test_pick_monster_lists_places(make):
    calls = []
    settings = dict(DEFAULTS, boxes={})
    tool = make(settings, lambda: calls.append(1))
    feed(tool, title("A"))
    pick(tool, "snail")
    assert not tool._search.isVisibleTo(tool.tab) and not tool._matches.isVisibleTo(tool.tab)
    assert tool._picked_row.name == "Snail"
    assert tool._where.text() == "Where it spawns"
    places = tool._places
    assert names(places) == ["Cherry", "Hush", "Apple"]  # Best: the most spawns first
    assert lines(places) == ["9 spawns · 2 away", "5 spawns · 2 away", "2 spawns · here"]
    assert places.currentRow() == 0
    tool._closest.click()
    assert names(places) == ["Apple", "Cherry", "Hush"]  # nearest first
    assert settings["path_best"] is False and calls == [1]
    assert places.currentRow() == 0
    tool._taxi.setChecked(False)
    assert names(places) == ["Apple", "Cherry", "Hush"]
    feed(tool, title("C"), 1.0)  # a new map re-sorts
    assert names(places) == ["Cherry", "Hush", "Apple"]
    assert lines(places) == ["9 spawns · here", "5 spawns · 2 away", "2 spawns · 2 away"]
    tool._best.click()
    assert settings["path_best"] is True and calls == [1, 1]


def test_drop_shop_and_npc_lines(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "snail shell")
    assert tool._where.text() == "Where to get it"
    assert names(tool._places) == ["Mina", "Cherry", "Apple", "Hush"]
    assert lines(tool._places) == [
        "1 away · Berry",
        "Snail ×9 · ~40% · 2 away · +1 more",
        "Snail ×2 · ~40% · here",
        "Pig ×1 · rate unknown · 2 away",
    ]
    tool._cross.click()
    pick(tool, "luna")  # an NPC on two listed maps
    assert tool._where.text() == "Where to find them"
    assert names(tool._places) == ["Apple", "Cherry"]
    assert lines(tool._places) == ["here", "2 away"]


def test_start_from_place(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "snail")
    tool._places.setCurrentRow(1)
    tool._start.click()
    assert tool.running and tool.trip.goal == "M" and tool.trip.at is None
    assert tool._header.text() == "To Hush · 1 of 3"


def test_shop_place_carries_npc_spot(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "snail shell")
    tool._start.click()  # the first row: Mina's shop
    assert tool.trip.goal == "B" and tool.trip.at == (10, 20)
    assert tool._header.text() == "To Mina · 1 of 2"


def test_one_place_npc_starts_like_a_map(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "faceless")
    assert tool._search.text() == "Faceless" and tool._matches.isHidden()
    assert tool._picked_row is None
    tool._start.click()
    assert tool.trip.goal == "C" and tool.trip.at == (5, 6)
    assert tool._header.text() == "To Faceless · 1 of 3"


def test_unknown_position_lists_best_without_hops(make):
    tool = make()
    pick(tool, "snail")  # no map read yet
    assert names(tool._places) == ["Cherry", "Hush", "Apple"]
    assert lines(tool._places) == ["9 spawns", "5 spawns", "2 spawns"]
    tool._closest.click()  # nothing to be close to: still Best
    assert names(tool._places) == ["Cherry", "Hush", "Apple"]
    assert not tool._start.isEnabled()
    feed(tool, title("A"))
    assert names(tool._places) == ["Apple", "Cherry", "Hush"]  # now Closest holds
    assert tool._start.isEnabled()


def test_all_unreachable_or_unknown(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "lonely")
    assert names(tool._places) == ["Date"] and lines(tool._places) == ["4 spawns · no route"]
    assert rows(tool._places)[0].dim
    tool._start.click()
    assert not tool.running and tool._info.text() == "No route from here to Date"
    for text, where in [
        ("cherry coin", "Where to get it: unknown"),
        ("cherry ghost", "Where it spawns: unknown"),
    ]:
        tool._cross.click()
        pick(tool, text)
        assert tool._where.text() == where
        assert tool._places.count() == 0 and not tool._places.isVisibleTo(tool.tab)
        assert not tool._start.isEnabled()
        tool._start.click()
        assert not tool.running


def test_cross_returns_to_search_and_new_pick_replaces(make):
    tool = make()
    feed(tool, title("A"))
    tool._search.setText("snail")
    before = matches(tool._matches)
    tool._matches.itemClicked.emit(tool._matches.item(0))
    assert tool._places.count() == 3
    tool._cross.click()
    assert tool._search.isVisibleTo(tool.tab) and tool._search.text() == "snail"
    assert tool._matches.isVisibleTo(tool.tab) and matches(tool._matches) == before
    assert not tool._places.isVisibleTo(tool.tab) and not tool._where.isVisibleTo(tool.tab)
    tool._matches.itemClicked.emit(tool._matches.item(1))  # the shell
    assert names(tool._places) == ["Mina", "Cherry", "Apple", "Hush"]  # replaced, not added
    tool._cross.click()
    pick(tool, "luna")
    assert tool._places.count() == 2


def test_go_leaves_a_pick(make):
    tool = make()
    feed(tool, title("A"))
    pick(tool, "snail")
    tool.go("C")
    assert tool.running and tool.trip.goal == "C"
    tool.stop()
    assert tool._search.isVisibleTo(tool.tab) and not tool._places.isVisibleTo(tool.tab)


def test_rows_elide_to_the_tab(make):
    tool = make()
    tool._search.setText("the very long")
    narrow = rows(tool._matches)[0].name_label.text()
    assert "…" in narrow
    tool.set_tab_w(480)
    assert len(rows(tool._matches)[0].name_label.text()) > len(narrow)
