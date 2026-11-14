from dataclasses import replace
from pathlib import Path

import pytest

from maplelens.readers import Reading
from maplelens.readers.quest_tracker import PARTLY, Tracker, TrackerLine, TrackerQuest
from maplelens.readers.quest_window import QuestOpen
from maplelens.readers.window import UNREADABLE
from maplelens.store import DEFAULTS
from maplelens.tools.quest_helper.data import MAPS, Item, Quest, Reward, Rewards, load
from maplelens.tools.quest_helper.plan import TIMES

SMALL = Path(__file__).parent / "fixtures" / "quests_small.json"
RECT = (0, 0, 1366, 768)
MIRROR = "Bringing a Mirror to Heena"  # 1001: Sera gives it, Snail x3, Heena takes it
SNAILS = 1002  # Snail Hunt: Snail x5 (the same map as 1001's), hand in to Heena
BIG = 1003  # Big Hunt: Sera gives it, four Snail rows, Heena takes it: 6 rows
SHARED = "Test of Qualification"  # 1004 and 1005
MYSTERY = 1006  # Mystery Quest: one item nobody drops or sells, hand in to Heena
TALK = 1007  # Small Talk: Sera gives it, Heena takes it, nothing to hunt
PRIDE = 1009  # Town Pride: as Small Talk, its only reward a Henesys contribution
SNAIL_MAP, TOWN = "000000040", "000000001"


def data():
    d = load(SMALL, MAPS)
    q = d.quests[1001]
    extra = [
        Quest(SNAILS, "Snail Hunt", None, 1, ((2, 5),), (), ()),
        Quest(BIG, "Big Hunt", 2, 1, ((2, 1), (2, 2), (2, 3), (2, 4)), (), ()),
        replace(q, id=1004, name=SHARED),
        replace(q, id=1005, name=SHARED),
        Quest(MYSTERY, "Mystery Quest", None, 1, (), ((9, 1),), ()),
        Quest(TALK, "Small Talk", 2, 1, (), (), ()),
        Quest(1008, "Mirror Two", None, 1, (), (), (), Rewards(100, 50), "Mirror", (1001,)),
        Quest(PRIDE, "Town Pride", 2, 1, (), (), (), Rewards(contribution=("Henesys", 100, 325))),
    ]
    items = {**d.items, 9: Item(9, "Odd Stone", (), ())}
    snail = replace(d.mobs[2], spawns={**d.mobs[2].spawns, TOWN: 1})  # a few in town too
    ores = (Reward(9, 7, "random"), Reward(4031000, 7, "random"), Reward(4000001, 2, "random"))
    paid = replace(q, rewards=Rewards(7020, 1140, ores), chain="Mirror")
    quests = {**d.quests, **{x.id: x for x in extra}, 1001: paid}
    return replace(d, quests=quests, mobs={**d.mobs, 2: snail}, items=items)


def R(quest=None, tracker=None):
    return Reading(0.0, None, None, None, None, quest=quest, tracker=tracker)


SNAIL, SHELL = "Snail", "Snail Shell"  # 1001's targets: Snail x3, Snail Shell x10


def panel(*blocks):
    return R(tracker=Tracker(len(blocks), False, tuple(blocks)))


def mirror(snails=0, shells=0):
    return TrackerQuest(MIRROR, (TrackerLine(snails, 3, SNAIL), TrackerLine(shells, 10, SHELL)))


def opened(name=MIRROR, taken=False):
    return R(QuestOpen(name, taken))


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.tools.quest_helper.ui import QuestHelperTool

    QApplication.instance() or QApplication([])

    def build(tracked=(), expanded=None, heading=None, closest=None, hops=lambda m: None, **more):
        calls = {"go": [], "stop": 0, "changed": 0, "heading": heading}
        settings = dict(
            DEFAULTS,
            quests_tracked=tracked if isinstance(tracked, str) else list(tracked),
            quests_expanded=expanded,
            quests_closest={} if closest is None else closest,
            **more,
        )

        def changed():
            calls["changed"] += 1

        def stop():
            calls["stop"] += 1
            calls["heading"] = None

        def go(map_id, at, label):
            calls["go"].append((map_id, at, label))

        tool = QuestHelperTool(
            settings,
            changed,
            go,
            lambda: calls["heading"],
            stop,
            hops,
            data(),
        )
        tool.settings, tool.calls = settings, calls
        return tool

    return build


def visible(tool, kind):
    shown = [w for w in tool.tab.findChildren(kind) if w.isVisibleTo(tool.tab)]
    return sorted(shown, key=lambda w: w.mapTo(tool.tab, w.rect().topLeft()).y())


def texts(tool):
    from PySide6.QtWidgets import QLabel, QPushButton, QWidget

    from maplelens.overlay import InfoLine

    # top to bottom; a name cut to fit has its full text as the tooltip
    kinds = (QLabel, QPushButton, InfoLine)
    return [w.toolTip() or w.text() for w in visible(tool, QWidget) if isinstance(w, kinds)]


def rows(tool):
    from maplelens.overlay import Row

    return visible(tool, Row)


def button(tool, text):
    from PySide6.QtWidgets import QPushButton

    found = [b for b in visible(tool, QPushButton) if text in (b.toolTip() or b.text())]
    assert found, (text, texts(tool))
    return found[0]


def test_empty_says_open_a_quest(make):
    from maplelens.tools.quest_helper.ui import EMPTY

    tool = make()
    tool.update(R(), RECT, 0)
    assert EMPTY in texts(tool) and not rows(tool) and not tool.open
    assert tool.title == "Quests"


def test_open_quest_shows_rows_and_track(make):
    from maplelens.tools.quest_helper.ui import OPEN, TRACK

    tool = make()
    tool.update(opened(taken=False), RECT, 0)
    assert tool.open
    assert OPEN in texts(tool) and MIRROR in texts(tool) and TRACK in texts(tool)
    assert [(r.name, r.sub) for r in rows(tool)] == [
        ("Sera", "Mushroom Town - West Entrance · gives the quest"),
        ("Snail ×3 · Shell ×10", "Snail Hunting Ground I"),
        ("Heena", "Mushroom Town - West Entrance · hand in"),
    ]
    assert all(r.clickable for r in rows(tool))
    tool.update(opened(taken=True), RECT, 1)  # in progress: no giver row
    assert [r.name for r in rows(tool)] == ["Snail ×3 · Shell ×10", "Heena"]


def test_track_saves_and_survives_close(make):
    from maplelens.tools.quest_helper.ui import TRACK, TRACKING_ONE

    tool = make()
    tool.update(opened(), RECT, 0)
    button(tool, TRACK).click()
    assert tool.settings["quests_tracked"] == [1001] and tool.calls["changed"] == 1
    for t in (1, 2):
        tool.update(R(), RECT, t)
    assert not tool.open
    assert TRACKING_ONE == "Tracking · 1 quest" and TRACKING_ONE in texts(tool)
    assert any(MIRROR in t for t in texts(tool))


def test_tracked_open_quest_shows_tracked_mark_once(make):
    from maplelens.tools.quest_helper.ui import TRACK, TRACKED, TRACKING

    tool = make(tracked=[1001, SNAILS])
    tool.update(opened(), RECT, 0)
    shown = texts(tool)
    assert TRACKED in shown and TRACK not in shown
    assert TRACKING.format(n=2) in shown  # the open one counts, though it shows only on top
    assert sum(MIRROR in t for t in shown) == 1  # on top, not again under Tracking
    assert any("Snail Hunt" in t for t in shown)


def test_one_expanded_and_remove(make):
    tool = make(tracked=[1001, SNAILS], expanded=1001)
    tool.update(R(), RECT, 0)
    assert "▾" in button(tool, MIRROR).text() and "▸" in button(tool, "Snail Hunt").text()
    assert [r.name for r in rows(tool)] == ["Snail ×3 · Shell ×10", "Heena"]  # no giver
    button(tool, "Snail Hunt").click()
    assert tool.settings["quests_expanded"] == SNAILS and tool.calls["changed"] == 1
    assert "▸" in button(tool, MIRROR).text() and "▾" in button(tool, "Snail Hunt").text()
    assert [r.name for r in rows(tool)] == ["Snail ×5", "Heena"]
    from PySide6.QtWidgets import QPushButton

    marks = [b for b in visible(tool, QPushButton) if b.text() == "×"]
    marks[-1].click()  # Snail Hunt's
    assert tool.settings["quests_tracked"] == [1001] and tool.settings["quests_expanded"] is None
    assert tool.calls["changed"] == 2
    assert not any("Snail Hunt" in t for t in texts(tool))


def test_row_click_goes(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    by = {r.name: r for r in rows(tool)}
    by["Snail ×3 · Shell ×10"].click()
    by["Heena"].click()
    assert tool.calls["go"] == [(SNAIL_MAP, None, None), (TOWN, (-46, 280), "Heena")]


def test_with_path_off_no_target_row_goes(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    tool.set_can_go(False)
    assert rows(tool) and not any(r.clickable for r in rows(tool))
    for r in rows(tool):
        r.click()
    assert tool.calls["go"] == []
    tool.set_can_go(True)
    assert all(r.clickable for r in rows(tool))


@pytest.mark.parametrize(
    "n, sub", [(0, "Going · on this map"), (1, "Going · 1 map away"), (2, "Going · 2 maps away")]
)
def test_running_row_counts_maps(make, n, sub):
    tool = make(heading=(TOWN, (-46, 280), n))
    tool.update(opened(), RECT, 0)
    (run,) = [r for r in rows(tool) if r.outline]
    assert run.sub == sub


def test_running_row_outlined_with_stop(make):
    from maplelens.tools.quest_helper.ui import GOING, STOP

    tool = make(heading=(TOWN, (-46, 280), 3))
    tool.update(opened(), RECT, 0)
    (run,) = [r for r in rows(tool) if r.outline]
    assert run.name == "Heena" and run.sub == GOING.format(n=3)
    button(tool, STOP).click()
    assert tool.calls["stop"] == 1
    assert not any(r.outline for r in rows(tool))  # redrawn at once


def test_row_click_before_map_known_outlines_nothing(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    rows(tool)[1].click()
    assert tool.calls["go"] == [(SNAIL_MAP, None, None)]
    assert not any(r.outline for r in rows(tool))


def test_row_click_outlines_the_row_at_once(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    tool.calls["heading"] = (SNAIL_MAP, None, 2)  # the path tool starts the trip
    rows(tool)[1].click()
    assert [r.name for r in rows(tool) if r.outline] == ["Snail ×3 · Shell ×10"]


def test_also_for(make):
    from maplelens.tools.quest_helper.ui import ALSO

    tool = make(tracked=[SNAILS], expanded=SNAILS)
    tool.update(opened(taken=True), RECT, 0)
    snail = next(r for r in rows(tool) if r.name.startswith("Snail ×3"))
    assert snail.sub.endswith(" · " + ALSO.format(quest="Snail Hunt"))
    assert snail.toolTip() == snail.sub
    heena = next(r for r in rows(tool) if r.name == "Heena")  # the open quest's hand-in
    assert heena.sub.endswith(ALSO.format(quest="Snail Hunt"))  # Snail Hunt's is on that map
    hunt = next(r for r in rows(tool) if r.name == "Snail ×5")
    assert "also for" not in hunt.sub  # the open quest isn't tracked: it doesn't count
    tool = make(tracked=[SNAILS, 1001], expanded=SNAILS)
    tool.update(opened(taken=True), RECT, 0)
    hunt = next(r for r in rows(tool) if r.name == "Snail ×5")
    assert hunt.sub.endswith(" · " + ALSO.format(quest=MIRROR))  # tracked now


def test_row_with_no_source_is_an_info_row(make):
    from maplelens.tools.quest_helper.plan import NO_ITEM

    tool = make()
    tool.update(opened("Mystery Quest", taken=True), RECT, 0)
    stone = next(r for r in rows(tool) if r.name == "Odd Stone ×1")
    assert stone.sub == NO_ITEM and stone.info and not stone.clickable
    from maplelens.overlay import _InfoMark

    assert [m for m in stone.findChildren(_InfoMark) if m.isVisibleTo(stone)]
    stone.click()
    assert tool.calls["go"] == []
    heena = next(r for r in rows(tool) if r.name == "Heena")
    assert not heena.info and not heena.findChildren(_InfoMark)


def test_same_reading_keeps_the_same_body(make):
    tool = make(tracked=[SNAILS], expanded=SNAILS)
    tool.update(opened(), RECT, 0)
    body, first = tool._body, rows(tool)[0]
    tool.update(opened(), RECT, 1)
    assert tool._body is body and rows(tool)[0] is first


def test_unreadable_unknown_and_shared_lines(make):
    from maplelens.readers.quest_window import NAME_UNREADABLE
    from maplelens.tools.quest_helper.ui import (
        NAME_UNREAD,
        OPEN,
        SHARED_NAME,
        UNKNOWN,
        UNREAD,
    )

    tool = make()
    for quest, line in (
        (UNREADABLE, UNREAD),
        (NAME_UNREADABLE, NAME_UNREAD),
        (QuestOpen("Nobody's Quest", None), UNKNOWN),
        (QuestOpen(SHARED, None), SHARED_NAME),
    ):
        tool.update(R(quest), RECT, 0)
        assert line in texts(tool) and OPEN in texts(tool) and not rows(tool)


def test_unreadable_window_is_yellow_and_name_unreadable_is_grey(make):
    from PySide6.QtWidgets import QLabel

    from maplelens.overlay import ACCENT
    from maplelens.readers.quest_window import NAME_UNREADABLE
    from maplelens.tools.quest_helper.ui import NAME_UNREAD, UNREAD

    tool = make()
    tool.update(R(UNREADABLE), RECT, 0)
    (line,) = [w for w in visible(tool, QLabel) if w.text() == UNREAD]
    assert ACCENT in line.styleSheet()
    tool.update(R(NAME_UNREADABLE), RECT, 1)
    assert NAME_UNREAD in texts(tool) and UNREAD not in texts(tool)


def test_one_missed_reading_keeps_the_open_quest(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    tool.update(R(), RECT, 1)
    assert MIRROR in texts(tool) and not tool.open
    tool.update(opened(), RECT, 2)
    assert MIRROR in texts(tool) and tool.open
    tool.update(R(), RECT, 3)
    assert MIRROR in texts(tool)
    tool.update(None, RECT, 4)  # no frame at all counts as closed
    assert MIRROR not in texts(tool)


def test_unknown_tracked_id_is_dropped(make):
    tool = make(tracked=[999999, SNAILS], expanded=999999)
    tool.update(R(), RECT, 0)
    assert tool.settings["quests_tracked"] == [SNAILS]
    assert tool.settings["quests_expanded"] is None
    assert any("Snail Hunt" in t for t in texts(tool))


def test_bad_settings_are_replaced(make):
    tool = make(tracked="oops", expanded="x")
    tool.update(R(), RECT, 0)
    assert tool.settings["quests_tracked"] == [] and tool.settings["quests_expanded"] is None


def test_height_capped(make):
    from maplelens.tools.quest_helper.ui import MAX_H

    tool = make(tracked=[1001, SNAILS, 1004], expanded=1001)
    tool.update(R(QuestOpen("Big Hunt", False)), RECT, 0)
    assert len(rows(tool)) >= 6
    assert tool.tab.sizeHint().height() <= MAX_H


def test_nothing_takes_focus(make):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    tool = make(tracked=[SNAILS], heading=(SNAIL_MAP, None, 2))
    tool.update(opened(), RECT, 0)
    taking = [w for w in tool.tab.findChildren(QWidget) if w.focusPolicy() != Qt.NoFocus]
    assert taking == []


def test_a_wider_tab_shows_more_of_a_long_quest_name(make):
    from PySide6.QtWidgets import QLabel

    tool = make()
    item = ("open", 1001, "A very long quest name " * 6, True, None)

    def name():
        line = tool._widget(item)  # held: its label goes with it
        return line.findChildren(QLabel)[0].text()

    narrow = name()
    tool.set_tab_w(480)
    assert len(name()) > len(narrow)
    assert tool.tab.maximumWidth() == tool._scroll.maximumWidth() == 480


TOWN_FIRST = {TOWN: 0, SNAIL_MAP: 2}.get  # the town is nearer; most Snails are further


def test_switch_starts_from_the_quest_size_and_flips_its_rows(make):
    from maplelens.tools.quest_helper.ui import BEST, CLOSEST

    tool = make(hops=TOWN_FIRST)
    tool.update(opened(taken=True), RECT, 0)  # Snail x3, Shell x10: 13, a quick one
    assert rows(tool)[0].sub == "Mushroom Town - West Entrance"
    button(tool, BEST).click()
    assert tool.settings["quests_closest"] == {"1001": False} and tool.calls["changed"] == 1
    assert rows(tool)[0].sub == "Snail Hunting Ground I"
    button(tool, CLOSEST).click()
    assert tool.settings["quests_closest"] == {"1001": True}
    assert rows(tool)[0].sub == "Mushroom Town - West Entrance"


def test_a_saved_choice_wins_over_the_size(make):
    tool = make(closest={"1001": False}, hops=TOWN_FIRST)
    tool.update(opened(taken=True), RECT, 0)
    assert rows(tool)[0].sub == "Snail Hunting Ground I"


def test_each_tracked_quest_has_its_own_switch(make):
    from PySide6.QtWidgets import QPushButton

    from maplelens.tools.quest_helper.ui import BEST

    tool = make(tracked=[1001, SNAILS], expanded=SNAILS, hops=TOWN_FIRST)
    tool.update(R(), RECT, 0)
    assert rows(tool)[0].sub.startswith("Mushroom Town - West Entrance")
    bests = [b for b in visible(tool, QPushButton) if b.text() == BEST]
    assert len(bests) == 2
    bests[-1].click()  # Snail Hunt's
    assert tool.settings["quests_closest"] == {str(SNAILS): False}
    assert rows(tool)[0].sub.startswith("Snail Hunting Ground I")


def test_no_switch_on_a_quest_with_nothing_to_hunt(make):
    from maplelens.tools.quest_helper.ui import BEST, CLOSEST

    tool = make(tracked=[TALK, SNAILS])
    tool.update(R(), RECT, 0)
    shown = texts(tool)
    assert shown.count(BEST) + shown.count(CLOSEST) == 2  # Snail Hunt's only


def test_bad_switch_settings_are_dropped(make):
    tool = make(closest={"1001": False, "999999": True, "1002": "x", "abc": True})
    tool.update(R(), RECT, 0)
    assert tool.settings["quests_closest"] == {"1001": False}
    tool = make(closest="oops")
    assert tool.settings["quests_closest"] == {}


# --- following the game's Quest Helper ---------------------------------------------

DONE_ROWS = [f"Snail Shell {TIMES}10", "Heena"]  # 1001 with its Snails done, taken


def follow(tool, *blocks):
    tool.update(panel(*blocks), RECT, 0)


def titles(tool):
    return [r.name for r in rows(tool)]


def test_panel_quest_is_tracked_and_saved(make):
    tool = make()
    follow(tool, mirror())
    assert tool.settings["quests_tracked"] == [1001]
    assert tool.settings["quests_followed"] == [1001]
    assert tool.calls["changed"] >= 1 and MIRROR in texts(tool)


def test_done_targets_drop_off(make):
    tool = make(tracked=[1001], expanded=1001)
    follow(tool, mirror(snails=3, shells=2))
    assert titles(tool) == DONE_ROWS


def test_all_done_shows_only_hand_in(make):
    tool = make(tracked=[1001], expanded=1001)
    follow(tool, mirror(3, 10))
    assert titles(tool) == ["Heena"]


def test_leaving_the_panel_untracks_after_two_reads(make):
    tool = make()
    follow(tool, mirror())
    tool.update(panel(), RECT, 1)
    assert tool.settings["quests_tracked"] == [1001]
    tool.update(panel(), RECT, 2)
    assert tool.settings["quests_tracked"] == [] and tool.settings["quests_followed"] == []


def test_track_button_quest_stays(make):
    tool = make(tracked=[SNAILS])
    for t in (0, 1):
        tool.update(panel(), RECT, t)
    assert tool.settings["quests_tracked"] == [SNAILS]


def test_minimized_unreadable_and_partly_change_nothing(make):
    tool = make()
    follow(tool, mirror(3, 2))
    tool.settings["quests_expanded"] = 1001
    for reading in (R(tracker=Tracker(0, True, ())), R(tracker=UNREADABLE), R(tracker=PARTLY)):
        for _ in range(3):
            tool.update(reading, RECT, 1)
        assert tool.settings["quests_tracked"] == [1001]
        assert titles(tool) == DONE_ROWS
    tool.update(panel(), RECT, 2)  # the first of two: doesn't untrack on its own
    assert tool.settings["quests_tracked"] == [1001]


def test_panel_warnings(make):
    from PySide6.QtWidgets import QLabel

    from maplelens.overlay import ACCENT, InfoLine
    from maplelens.tools.quest_helper.ui import PARTLY_PANEL, PARTLY_SHOWN, UNREAD_PANEL

    tool = make()
    tool.update(R(tracker=UNREADABLE), RECT, 0)
    (line,) = [w for w in visible(tool, QLabel) if w.text() == UNREAD_PANEL]
    assert ACCENT in line.styleSheet()
    tool.update(R(tracker=PARTLY), RECT, 1)
    assert UNREAD_PANEL not in texts(tool) and PARTLY_PANEL not in texts(tool)
    for t in range(PARTLY_SHOWN - 2):  # PARTLY_SHOWN - 1 in a row so far
        tool.update(R(tracker=PARTLY), RECT, t)
    assert PARTLY_PANEL not in texts(tool)
    tool.update(R(tracker=PARTLY), RECT, 9)
    assert PARTLY_PANEL in [w.text() for w in visible(tool, InfoLine)]
    tool.update(panel(), RECT, 10)  # a whole read clears it, and the count starts again
    assert PARTLY_PANEL not in texts(tool)
    tool.update(R(tracker=PARTLY), RECT, 11)
    assert PARTLY_PANEL not in texts(tool)


def test_unknown_and_several_blocks_are_notes(make):
    from maplelens.tools.quest_helper.ui import PARTLY_PANEL, UNREAD_PANEL

    tool = make()
    follow(tool, TrackerQuest("Nobody's Quest", ()), TrackerQuest(SHARED, ()), mirror())
    shown = texts(tool)
    assert "Nobody's Quest: not in MapleLens's list yet" in shown
    assert f"{SHARED}: several quests have this name" in shown
    assert PARTLY_PANEL not in shown and UNREAD_PANEL not in shown
    assert tool.settings["quests_tracked"] == [1001]


def test_several_block_protects_a_followed_shared_quest(make):
    tool = make(tracked=[1004], quests_followed=[1004])
    for t in (0, 1):
        tool.update(panel(TrackerQuest(SHARED, ())), RECT, t)
    assert tool.settings["quests_tracked"] == [1004]


def test_cut_several_block_protects_a_followed_shared_quest(make):
    tool = make(tracked=[1004], quests_followed=[1004])
    for t in (0, 1):
        tool.update(panel(TrackerQuest("Test of Qual…", ())), RECT, t)
    assert tool.settings["quests_tracked"] == [1004]


def test_no_panel_restores_todays_rows(make):
    tool = make()
    follow(tool, mirror(3, 2))
    tool.settings["quests_expanded"] = 1001
    for t in (1, 2):
        tool.update(R(), RECT, t)
    assert titles(tool) == [f"Snail {TIMES}3 · Shell {TIMES}10", "Heena"]
    assert tool.settings["quests_tracked"] == [1001]


def test_one_missing_panel_keeps_progress(make):
    tool = make()
    follow(tool, mirror(3, 2))
    tool.settings["quests_expanded"] = 1001
    tool.update(R(), RECT, 1)
    assert titles(tool) == DONE_ROWS


def test_close_on_a_followed_quest_comes_back(make):
    from maplelens.tools.quest_helper.ui import CLOSE

    tool = make()
    follow(tool, mirror())
    button(tool, CLOSE).click()
    assert tool.settings["quests_tracked"] == [] and tool.settings["quests_followed"] == []
    follow(tool, mirror())
    assert tool.settings["quests_tracked"] == [1001]


def test_open_quest_window_uses_progress(make):
    tool = make()
    r = replace(panel(mirror(3, 2)), quest=QuestOpen(MIRROR, True))
    tool.update(r, RECT, 0)
    assert titles(tool) == DONE_ROWS


def test_bad_followed_setting_is_replaced(make):
    tool = make(quests_followed="x")
    assert tool.settings["quests_followed"] == []
    tool = make(tracked=[], quests_followed=[1001, 999999])
    assert tool.settings["quests_followed"] == []


# --- rewards ------------------------------------------------------------------------


def reward_line(tool):
    from maplelens.tools.quest_helper.ui import RewardLine

    (found,) = visible(tool, RewardLine)
    return found


def reward_button(tool):
    found = reward_line(tool)
    assert found.clickable and found.toolTip().startswith(("▸", "▾")), found.toolTip()
    return found


def slots(tool):
    from maplelens.tools.quest_helper.ui import Slot

    return visible(tool, Slot)


def test_reward_line_under_the_open_quest(make):
    tool = make()
    tool.update(opened(), RECT, 0)
    t = texts(tool)  # top to bottom
    assert t.index(MIRROR) < t.index("▸ 7,020 EXP · 1,140 mesos") < t.index("Sera")  # giver row


def test_reward_line_opens_and_is_saved(make):
    tool = make(tracked=[SNAILS], expanded=SNAILS)
    tool.update(opened(), RECT, 0)
    reward_button(tool).click()
    assert tool.settings["quest_rewards_open"] is True and tool.calls["changed"] == 1
    assert "Rest of chain (1 quest): +100 EXP · 50 mesos" in texts(tool)


def test_no_reward_line_without_rewards(make):  # Review Focus 3
    tool = make()
    tool.update(opened("Small Talk"), RECT, 0)
    assert not [x for x in texts(tool) if "EXP" in x]


def test_collapsed_tracked_quest_has_no_reward_line(make):
    tool = make(tracked=[1001])
    tool.update(R(), RECT, 0)
    assert not [x for x in texts(tool) if "EXP" in x]


def test_bad_setting_reads_closed(make):  # hand-edited settings
    tool = make(quest_rewards_open="yes")
    assert tool.settings["quest_rewards_open"] is False


def test_job_kept_when_a_tick_misses_it(make):  # Review Focus 1
    tool = make(quest_rewards_open=True)
    tool.update(replace(opened(), job="Rogue"), RECT, 0)
    tool.update(opened(), RECT, 0)  # job None this tick
    assert tool._job == "Rogue"


def test_missing_icon_draws_an_empty_slot(make):  # Review Focus 2
    tool = make(quest_rewards_open=True)
    tool.update(opened(), RECT, 0)  # fixture item ids have no icon files
    assert len(slots(tool)) == 3
    assert f"Odd Stone {TIMES}7" in texts(tool)  # its name beside it


def test_iconless_item_of_a_big_group_has_its_name(make):
    from PySide6.QtWidgets import QGridLayout, QLabel

    from maplelens.tools.quest_helper.rewards import Shown
    from maplelens.tools.quest_helper.ui import Slot

    tool = make()
    hats = [Shown(i, f"Hat {i}", 1, f"Hat {i}") for i in (1002000, 1002001, 1002003)]  # icons
    group = tool._widget(
        ("icons", "Random, 1 of:", (*hats, Shown(9, "Odd Stone", 7, f"Odd Stone {TIMES}7")))
    )
    (grid,) = group.findChildren(QGridLayout)
    assert grid.count() == 3  # the three with icons, in a row
    slots_ = group.findChildren(Slot)
    assert len(slots_) == 4
    assert f"Odd Stone {TIMES}7" in [w.text() for w in group.findChildren(QLabel)]
    assert [s._count for s in slots_] == [1, 1, 1, 0]  # the list form draws no corner count


def test_list_form_shows_the_tip_text(make):
    from PySide6.QtWidgets import QLabel

    from maplelens.tools.quest_helper.rewards import Shown
    from maplelens.tools.quest_helper.ui import Slot

    tool = make()
    robe = Shown(9, "Blue Sauna Robe", 1, "Blue Sauna Robe (male)")
    group = tool._widget(("icons", "", (robe,)))
    assert "Blue Sauna Robe (male)" in [w.text() for w in group.findChildren(QLabel)]
    assert [s._count for s in group.findChildren(Slot)] == [0]


def test_contribution_only_line_does_not_open(make):
    tool = make()
    tool.update(opened("Town Pride"), RECT, 0)
    line = reward_line(tool)
    assert line.toolTip() == "Henesys contribution +100–325" and not line.clickable
    assert "▸" not in line.text()
    line.click()
    assert tool.settings["quest_rewards_open"] is False and tool.calls["changed"] == 0


def test_closed_line_numbers_are_white(make):
    from maplelens.overlay import LABEL_COLOR, VALUE_COLOR

    tool = make()
    tool.update(opened(), RECT, 0)
    html = reward_button(tool).text()
    assert f'<span style="color: {VALUE_COLOR};">7,020</span>' in html
    assert LABEL_COLOR in reward_button(tool).styleSheet()


def test_icon_columns_follow_the_tab_width(make):  # Review Focus 4
    tool = make(quest_rewards_open=True)
    tool.update(opened(), RECT, 0)
    tool.set_tab_w(480)
    assert all(s.isVisibleTo(tool.tab) for s in slots(tool))


def test_same_reading_does_not_redraw(make):  # Review Focus 5
    tool = make(quest_rewards_open=True)
    tool.update(opened(), RECT, 0)
    body = tool._body
    tool.update(opened(), RECT, 1)
    assert tool._body is body
