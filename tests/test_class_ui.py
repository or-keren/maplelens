from pathlib import Path

import pytest

from maplelens import overlay
from maplelens.readers import Reading
from maplelens.readers.skill_window import SkillRow, SkillWindow
from maplelens.readers.stat_window import StatWindow
from maplelens.readers.window import UNREADABLE
from maplelens.store import DEFAULTS
from maplelens.tools.class_helper.data import MAPS, load, load_spots

SMALL = Path(__file__).parent / "fixtures" / "classes_small.json"
SPOTS_SMALL = Path(__file__).parent / "fixtures" / "spots_small.json"
RECT = (0, 0, 1366, 768)


def R(job="Rogue", level=12, stats=None, skills=None):
    return Reading(0.0, None, level, job, None, stats=stats, skills=skills)


PLUS = {"STR": (170, 100), "DEX": (170, 120), "INT": (170, 140), "LUK": (170, 160)}
NIMBLE = 4000000


def s(str_, dex, int_, luk):
    return {"STR": str_, "DEX": dex, "INT": int_, "LUK": luk}


def SW(level=12, ap=0, base=None, plus=None):
    base = base or s(4, 25, 4, 4)
    return StatWindow(level, ap, base, dict(base), PLUS if plus is None else plus)


def KW(tab="Rogue", sp=0, rows=()):
    return SkillWindow(tab, sp, tuple(rows))


ALL_ROGUE = [SkillRow(NIMBLE, 0, (150, 120))]
ALL_BANDIT = [SkillRow(4200000, 0, (150, 120))]
LATER_ROWS_ONLY = [SkillRow(4000001, 0, (150, 120))]


def pos(x, y):
    return (x, y)  # RECT is 768 high at dpr 1


@pytest.fixture
def make(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication

    from maplelens.overlay import Layer
    from maplelens.tools.class_helper.ui import ClassHelperTool

    QApplication.instance() or QApplication([])
    pics, icons = tmp_path / "pics", tmp_path / "icons"
    pics.mkdir()
    icons.mkdir()
    picture, icon = QImage(40, 20, QImage.Format_ARGB32), QImage(8, 8, QImage.Format_ARGB32)
    picture.fill(QColor("#5a7a3a"))
    icon.fill(QColor("#e08040"))
    assert picture.save(str(pics / "000000001.webp")) and picture.save(str(pics / "000000002.webp"))
    assert icon.save(str(icons / "2.png")) and icon.save(str(icons / "3.png"))
    spots = load_spots.__wrapped__(SPOTS_SMALL, pics, icons)  # uncached: a SpotData per test

    def build(on_changed=lambda: None, best_rate=lambda t: None):
        layer = Layer()
        layer.show()
        gone = []
        settings = dict(DEFAULTS, class_builds={})
        tool = ClassHelperTool(
            settings, on_changed, layer, gone.append, best_rate, load(SMALL, MAPS), spots
        )
        tool.gone = gone
        return tool

    return build


def texts(tool):
    from PySide6.QtWidgets import QLabel

    from maplelens.overlay import InfoLine

    shown = [w for w in tool.tab.findChildren(QLabel) if w.isVisibleTo(tool.tab)]
    infos = [w for w in tool.tab.findChildren(InfoLine) if w.isVisibleTo(tool.tab)]
    return [w.text() for w in shown] + [w.text() for w in infos]


def rows(tool):
    from maplelens.tools.class_helper.ui import Row

    shown = [r for r in tool.tab.findChildren(Row) if r.isVisibleTo(tool.tab)]
    return sorted(shown, key=lambda r: r.mapTo(tool.tab, r.rect().topLeft()).y())


def test_unknown_class_says_so(make):
    from maplelens.tools.class_helper.ui import NO_CLASS

    tool = make()
    tool.update(R(job=None, level=None), RECT, 0)
    assert NO_CLASS in texts(tool)


def test_no_plan_for_job(make):
    from maplelens.tools.class_helper.ui import NO_PLAN

    tool = make()
    tool.update(R(job="Hermit", level=72), RECT, 0)
    assert NO_PLAN.format("Hermit") in texts(tool)


def test_training_rows_click_to_go_and_best_rate(make):
    tool = make(best_rate=lambda t: 1234.0 if t else None)
    tool.update(R(level=12), RECT, 0)
    first, *rest = [r for r in rows(tool) if not r.name.startswith(("Lv ", "Build: "))]
    assert first.sub == "your best · 1,234/min" and first.clickable and first.best
    assert rest and all(r.sub.startswith("mobs Lv ") and not r.best for r in rest)
    first.click()
    assert tool.gone == ["000000001"]


def test_with_path_off_no_row_goes_until_its_back_on(make):
    tool = make(best_rate=lambda t: 1234.0 if t else None)
    tool.update(R(level=12), RECT, 0)
    tool.set_can_go(False)
    trips = [r for r in rows(tool) if r.sub.startswith(("your best", "mobs Lv "))]
    assert trips and not any(r.clickable for r in trips)
    trips[0].click()
    assert tool.gone == []
    tool.set_can_go(True)  # live: no reading needed
    first = next(r for r in rows(tool) if r.sub.startswith("your best"))
    assert first.clickable
    first.click()
    assert tool.gone == ["000000001"]


def test_row_without_a_map_is_not_clickable(make):
    tool = make()
    tool.update(R(level=15), RECT, 0)
    plain = [r for r in rows(tool) if r.name == "A map not in maps.json"]
    assert plain and not plain[0].clickable
    plain[0].click()
    assert tool.gone == []


def test_chip_counts_points(make):
    tool = make()
    tool.update(R(level=12, stats=SW(level=12, ap=5), skills=KW(sp=3, rows=ALL_ROGUE)), RECT, 0)
    assert "5 AP · 3 SP" in texts(tool)
    tool.update(R(level=13), RECT, 1)
    assert not any(t.endswith((" AP", " SP")) for t in texts(tool))


def test_advance_ready_row_on_top_and_out_of_footer(make):
    from maplelens.tools.class_helper.ui import READY

    tool = make(best_rate=lambda t: 1234.0 if t else None)
    tool.update(R(level=30), RECT, 0)
    assert rows(tool)[0].name == READY
    assert not any("Advance:" in t for t in texts(tool))
    assert not any(r.best for r in rows(tool))


def test_footer_lists_milestones(make):
    from maplelens.tools.class_helper.ui import NEXT

    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert NEXT in texts(tool)
    steps = [(r.name, r.sub) for r in rows(tool)]
    assert ("Lv 15 · Gear", "Second Claw") in steps  # a short line each: never cut off
    assert ("Lv 30 · Advance", "Assassin or Bandit") in steps


def test_no_spots_says_so(make):
    from maplelens.tools.class_helper.ui import NO_SPOTS

    tool = make()
    tool.update(R(level=25), RECT, 0)  # no Rogue training row covers 25 in the small data
    assert NO_SPOTS.format(25) in texts(tool)


def test_long_name_stays_one_line(make):
    from maplelens.tools.class_helper.ui import Row

    make()  # the app
    long = Row("Victoria Road / " + "X" * 60, "mobs Lv 1–2", None)
    short = Row("Short", "mobs Lv 1–2", None)
    assert long.sizeHint().height() == short.sizeHint().height()
    assert (
        long.sizeHint().width() <= short.sizeHint().width()
        or long.sizeHint().width() <= overlay.TAB_W
    )


def test_no_build_picker_or_marks_box_in_the_tab(make):
    from PySide6.QtWidgets import QCheckBox, QComboBox

    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert not tool.tab.findChildren(QComboBox) and not tool.tab.findChildren(QCheckBox)


def test_pick_build_saves_and_tells(make):
    saved, told = [], []
    tool = make(on_changed=lambda: saved.append(1))
    tool.builds_changed = lambda: told.append(1)
    tool.update(R(level=12), RECT, 0)
    assert tool.build_names() == ["LUK", "Sindit"] and tool.build_name() == "LUK"
    tool.pick_build("Sindit")
    assert tool._settings["class_builds"] == {"Rogue": "Sindit"} and saved and told
    assert tool.build_name() == "Sindit"
    tool.update(R(job="Hermit", level=72), RECT, 1)
    assert tool.build_names() == []


def click(row):
    from PySide6.QtWidgets import QApplication

    row.click()
    QApplication.processEvents()  # the tab redraws after the click, not inside it


def named(tool, name):
    return next(r for r in rows(tool) if r.name == name)


def test_beginner_picks_a_class_in_the_tab(make):
    from maplelens.tools.class_helper.ui import CHOOSE

    tool = make()
    tool.update(R("Beginner", 5, stats=SW(level=5, ap=5, base=s(4, 4, 4, 4))), RECT, 0)
    assert CHOOSE in texts(tool)
    assert tool.marks() == []  # no class assumed, so no stat to point at
    assert not any(r.name.startswith("Lv ") for r in rows(tool))  # nor its advance
    assert named(tool, "Snail Field")  # training doesn't depend on the class
    click(named(tool, "Magician"))
    assert tool._settings["class_builds"] == {"Beginner": "Magician"}
    assert CHOOSE not in texts(tool)
    assert tool.marks() == [("5 here", pos(*PLUS["INT"]))]
    assert named(tool, "Lv 8 · Advance").sub == "Magician"


def test_build_row_opens_the_choices(make):
    from maplelens.tools.class_helper.ui import CHANGE

    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert named(tool, "Build: LUK").sub == CHANGE
    click(named(tool, "Build: LUK"))
    assert named(tool, "LUK").best and not named(tool, "Sindit").best
    click(named(tool, "Sindit"))
    assert tool._settings["class_builds"] == {"Rogue": "Sindit"}
    assert named(tool, "Build: Sindit")
    assert not any(r.name == "LUK" for r in rows(tool))


def test_stats_never_read_then_badge_until_level_changes(make):
    from maplelens.tools.class_helper.ui import OPEN_STATS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    assert OPEN_STATS in texts(tool)
    tool.update(R(level=12, stats=SW(level=12, ap=3)), RECT, 1)
    assert "3 AP" in texts(tool)
    tool.update(R(level=13), RECT, 2)
    assert "3 AP" not in texts(tool)


def test_stat_window_of_another_level_is_unread(make):
    from maplelens.tools.class_helper.ui import STAT_UNREAD

    tool = make()
    tool.update(R(level=12, stats=SW(level=11, ap=3)), RECT, 0)
    assert STAT_UNREAD in texts(tool)
    assert "3 AP" not in texts(tool)


def test_job_flicker_keeps_tab(make):
    from maplelens.tools.class_helper.ui import NO_CLASS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    tool.update(R(job=None, level=12), RECT, 1)
    assert NO_CLASS not in texts(tool) and not tool.dot


def test_character_switch_forgets(make):
    from maplelens.tools.class_helper.ui import OPEN_STATS

    tool = make()
    tool.update(R(level=25, stats=SW(level=25, ap=0)), RECT, 0)
    tool.update(R(job="Magician", level=20), RECT, 1)
    assert OPEN_STATS in texts(tool)


def test_level_up_dot_until_opened(make):
    tool = make()
    tool.update(R(level=14), RECT, 0)  # tab not shown
    tool.update(R(level=15), RECT, 1)  # a new map or gear at 15
    assert tool.dot
    tool.tab.show()
    tool.update(R(level=15), RECT, 2)
    assert not tool.dot


def test_bad_class_builds_setting_is_reset(make):
    tool = make()
    tool._settings["class_builds"] = "oops"
    tool.update(R(level=12), RECT, 0)
    assert tool._settings["class_builds"] == {}


def test_rings_on_the_plus_buttons(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30))), RECT, 0)
    assert tool.marks() == [("5 here", pos(*PLUS["LUK"]))]


def test_marks_can_be_turned_off(make):
    saved = []
    tool = make(on_changed=lambda: saved.append(dict(tool._settings)))
    tool.update(R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30))), RECT, 0)
    tool.set_marks(False)
    assert tool.marks() == [] and saved[-1]["class_marks"] is False
    tool.update(R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30))), RECT, 1)
    assert tool.marks() == []  # stays off; the tab still reads the window
    tool.set_marks(True)
    assert tool.marks() == [("5 here", pos(*PLUS["LUK"]))]


def test_the_settings_section_turns_the_marks_off(make):
    from PySide6.QtWidgets import QCheckBox

    from maplelens.tools.class_helper.ui import MARKS

    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30))), RECT, 0)
    section = tool.settings_section()  # held: the checkbox lives as long as its section
    (box,) = section.findChildren(QCheckBox)
    assert box.text() == MARKS and box.isChecked()
    box.setChecked(False)
    assert tool.marks() == [] and tool._settings["class_marks"] is False


def test_marks_follow_and_hide(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5)), RECT, 0)
    moved = SW(level=20, ap=5, plus={k: (x + 40, y) for k, (x, y) in PLUS.items()})
    tool.update(R(level=20, stats=moved), RECT, 1)
    assert [p for _, p in tool.marks()] == [pos(PLUS["LUK"][0] + 40, PLUS["LUK"][1])]
    tool.update(R(level=20), RECT, 2)
    assert tool.marks() == []


def test_unreadable_window_hides_marks_and_says_why(make):
    from maplelens.tools.class_helper.ui import STAT_UNREAD

    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5)), RECT, 0)
    tool.update(R(level=20, stats=UNREADABLE), RECT, 1)
    assert tool.marks() == [] and STAT_UNREAD in texts(tool)


def test_over_and_behind_tags(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=0, base=s(4, 35, 4, 20))), RECT, 0)
    assert {t for t, _ in tool.marks()} == {"DEX 10 over plan", "LUK 10 behind plan"}


def test_scroll_the_list_once(make):
    from maplelens.tools.class_helper.ui import SCROLL

    tool = make()
    tool.update(R(level=20, skills=KW(rows=LATER_ROWS_ONLY, sp=2)), RECT, 0)
    assert [t for t, _ in tool.marks()] == [SCROLL]


def test_skill_ring_and_merged_memory(make):
    tool = make()
    tool.update(R(level=20, skills=KW(rows=ALL_ROGUE, sp=2)), RECT, 0)
    assert tool.marks() == [("2 here", pos(150, 120))]
    tool.update(R(level=20, skills=KW(rows=LATER_ROWS_ONLY, sp=2)), RECT, 1)
    assert tool.skills["Rogue"] == {NIMBLE: 0, 4000001: 0}


def test_tabs_are_remembered_apart(make):
    tool = make()
    tool.update(R(level=32, job="Bandit", skills=KW(tab="Rogue", sp=2, rows=ALL_ROGUE)), RECT, 0)
    tool.update(R(level=32, job="Bandit", skills=KW(tab="Bandit", sp=0, rows=ALL_BANDIT)), RECT, 1)
    tool.update(R(level=32, job="Bandit"), RECT, 2)
    assert "1st job tab: 2 SP to place" in texts(tool)


def test_lower_skill_level_means_another_character(make):
    tool = make()
    first = [SkillRow(NIMBLE, 5, (150, 120)), SkillRow(4000001, 3, (150, 160))]
    tool.update(R(level=20, skills=KW(rows=first, sp=2)), RECT, 0)
    tool.update(R(level=20, skills=KW(rows=[SkillRow(NIMBLE, 2, (150, 120))], sp=2)), RECT, 1)
    assert tool.skills["Rogue"] == {NIMBLE: 2}


def test_marks_scale_with_client_and_dpr(make, monkeypatch):
    from maplelens.overlay import Layer, game_to_layer

    monkeypatch.setattr(Layer, "devicePixelRatioF", lambda self: 2.0)
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5)), (0, 0, 2560, 1440), 0)
    k = 1440 / 768
    x, y = PLUS["LUK"]
    assert tool.marks() == [("5 here", game_to_layer(x * k, y * k, 2.0))]


def test_stat_window_of_another_level_gets_no_marks(make):
    tool = make()
    tool.update(R(level=20, stats=SW(level=19, ap=5)), RECT, 0)
    assert tool.marks() == []


class _Quiet:
    running = False
    dot = False
    open = False

    def update(self, *_):
        pass


class _Box:
    def set_tab_dot(self, *_):
        pass


def test_marks_survive_the_app_tick(make):
    from maplelens import app

    tool = make()
    reading = R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30)))
    app.update_tools(
        _Box(), _Quiet(), _Quiet(), tool, _Quiet(), _Quiet(), reading, RECT, 0.0, set()
    )
    assert tool.marks() == [("5 here", pos(*PLUS["LUK"]))]


def test_marks_hide_when_the_class_tool_raises(make, monkeypatch):
    import sys

    from maplelens import app

    monkeypatch.setattr(sys, "stderr", None)
    tool = make()
    reading = R(level=20, stats=SW(level=20, ap=5, base=s(4, 25, 4, 30)))
    tool.update(reading, RECT, 0)
    assert tool.marks()
    monkeypatch.setattr(tool, "_draw_marks", lambda: (_ for _ in ()).throw(ValueError("x")))
    app.update_tools(
        _Box(), _Quiet(), _Quiet(), tool, _Quiet(), _Quiet(), reading, RECT, 1.0, set()
    )
    assert tool.marks() == []


STATES = [("Rogue", 28), ("Beginner", 8), ("Rogue", 30), ("Hunter", 34), (None, None)]


@pytest.fixture
def box_with_tools(monkeypatch, tmp_path):
    """The box as app.py builds it: EXP, Path and Class, with the real class data."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from maplelens.overlay import Box, Layer
    from maplelens.tools.class_helper.ui import ClassHelperTool
    from maplelens.tools.exp_meter.history import open_db
    from maplelens.tools.exp_meter.ui import ExpMeterTool
    from maplelens.tools.path_arrow.ui import PathArrowTool

    QApplication.instance() or QApplication([])
    settings = dict(DEFAULTS, class_builds={}, boxes={})
    layer = Layer()
    box = Box("t", settings, lambda: None)
    cls = ClassHelperTool(settings, lambda: None, layer, lambda m: None, lambda t: 290.0)
    tools = [
        ExpMeterTool(settings, open_db(tmp_path / "h.db")),
        PathArrowTool(settings, lambda: None, layer, lambda on: None),
        cls,
    ]
    for t in tools:
        box.add_tab(t.title, t.tab)
    box.show()  # a shown box's pages size from their raw hints
    box.path = tools[1]
    return box, cls


def settle(box, cls=None, job=None, level=None):
    """Feed the class tool, then let Qt show the widgets it built, as the running app does."""
    from PySide6.QtWidgets import QApplication

    if cls is not None:
        cls.update(R(job=job, level=level), RECT, 0)
    QApplication.processEvents()  # a visible parent shows new children on the next pass
    box.adjustSize()


def test_box_width_is_the_same_on_every_tab(box_with_tools):
    box, cls = box_with_tools
    widths = {}
    for job, level in STATES:
        for i in range(3):
            box.select(i)
            settle(box, cls, job, level)
            widths[(job, level, i)] = box.width()
    assert set(widths.values()) == {overlay.TAB_W + 24}, widths


def test_class_tab_text_never_overlaps(box_with_tools):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QLabel

    box, cls = box_with_tools
    box.select(2)
    for job, level in STATES:
        settle(box, cls, job, level)
        shown = [w for w in cls.tab.findChildren(QLabel) if w.isVisibleTo(cls.tab) and w.text()]
        assert len(shown) >= 3, (job, level)  # the check below really looked at something
        rects = [w.geometry().translated(w.parentWidget().mapTo(cls.tab, QPoint())) for w in shown]
        for i, a in enumerate(rects):
            for j in range(i + 1, len(rects)):
                assert not a.intersects(rects[j]), (job, level, shown[i].text(), shown[j].text())


def test_box_width_holds_with_an_info_line_on_the_path_tab(box_with_tools):
    box, _ = box_with_tools
    box.select(1)
    for t in (0.0, 0.5):  # read twice: confirmed, not in the map data
        box.path.update(Reading(t, None, None, None, "Road / Nowhere"), RECT, t)
    settle(box)
    assert box.path._info.isVisibleTo(box.path.tab)
    assert box.width() == overlay.TAB_W + 24


def test_a_row_click_never_leaves_the_box_dragging(box_with_tools):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    box, cls = box_with_tools
    box.select(2)
    settle(box, cls, "Rogue", 28)
    clickable = next(r for r in rows(cls) if r.clickable)
    plain = next(r for r in rows(cls) if not r.clickable)
    for row in (clickable, plain):
        QTest.mousePress(row, Qt.LeftButton)
        QTest.mouseRelease(row, Qt.LeftButton)
        assert box._drag_from is None, row.name  # the box still follows the game window


def test_header_keeps_the_level_when_points_crowd_it(make):
    from PySide6.QtWidgets import QLabel

    tool = make()
    tool.update(R(level=12, stats=SW(level=12, ap=12), skills=KW(sp=10, rows=ALL_ROGUE)), RECT, 0)
    (head,) = [w for w in tool.tab.findChildren(QLabel) if w.text().endswith("Lv 12")]
    (chip,) = [w for w in tool.tab.findChildren(QLabel) if w.objectName() == "chip"]
    assert chip.text() == "12 AP · 10 SP"
    # 6: the row's spacing
    used = head.sizeHint().width() + 6 + chip.sizeHint().width()
    assert used <= overlay.TAB_W


def test_a_long_job_name_is_cut_not_the_level(make):
    tool = make()
    tool._data.jobs["Wizard (Ice, Lightning) Wizard"] = tool._data.jobs["Rogue"]
    tool.update(
        R(job="Wizard (Ice, Lightning) Wizard", level=34, stats=SW(level=34, ap=12)), RECT, 0
    )
    (head,) = [t for t in texts(tool) if t.endswith(" · Lv 34")]
    assert "…" in head


def test_a_wider_tab_shows_more_of_a_long_row_name(make):
    from PySide6.QtWidgets import QLabel

    def title(tool):
        return rows(tool)[0].findChild(QLabel).text()

    tool = make()
    tool._render([("row", "A very long training map name " * 4, "", None, False, False)])
    narrow = title(tool)
    tool.set_tab_w(480)  # the same items: drawn again all the same
    assert len(title(tool)) > len(narrow)
    assert tool.tab.maximumWidth() == 480


def luk_mark(make, height):
    """The LUK mark in a 16:9 client `height` px tall at dpr 1, and the game's scale there."""
    tool = make()
    tool.update(R(level=20, stats=SW(level=20, ap=5)), (0, 0, height * 16 // 9, height), 0)
    (mark,) = [m for m in tool._pool if not m.isHidden()]
    return tool, mark, height / 768  # the tool keeps the layer, and so the mark, alive


@pytest.mark.parametrize("height", [768, 1440])
def test_mark_leaves_the_second_plus_button_uncovered(make, height):
    from PySide6.QtGui import QColor

    from maplelens.tools.class_helper.ui import RING_R

    _tool, mark, s = luk_mark(make, height)
    assert abs(mark.height() - 2 * RING_R * s) <= 1  # the ring grows with the + buttons
    img, r, mid = mark.grab().toImage(), mark.height() // 2, mark.height() // 2
    # Past the ring, up to where the pair ends (20 base px right of the + centre in
    # stat_a_1366x768_100.png), the mark draws nothing.
    clear = range(2 * r + 1, r + round(20 * s) + 1)
    assert all(QColor.fromRgba(img.pixel(x, mid)).alpha() == 0 for x in clear)


def test_mark_tag_has_a_dark_background(make):
    from PySide6.QtGui import QColor

    _tool, mark, _ = luk_mark(make, 1440)
    behind = QColor.fromRgba(mark.grab().toImage().pixel(mark.width() - 3, mark.height() // 2))
    assert behind.alpha() > 200 and behind.lightness() < 60


def hover(row, on):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication

    p = QPointF(1, 1)
    QApplication.sendEvent(row, QEnterEvent(p, p, p) if on else QEvent(QEvent.Leave))


def wait(ms):
    from PySide6.QtTest import QTest

    QTest.qWait(ms)


def test_hovering_a_spot_shows_its_card(make):
    from PySide6.QtWidgets import QLabel

    from maplelens.tools.class_helper.plan import short_name
    from maplelens.tools.class_helper.ui import HIDE_MS, SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    spot = rows(tool)[0]  # the 000000001 training row
    hover(spot, True)
    wait(SHOW_MS + 100)
    assert tool._card.isVisible() and tool._card.title() == short_name(spot.name)
    shown = [w.text() for w in tool._card.findChildren(QLabel)]
    assert {"Snail", "Blue Snail", "Up to 5 monsters at once"} <= set(shown)
    hover(spot, False)
    wait(HIDE_MS + 100)
    assert not tool._card.isVisible()


def test_a_quick_pass_shows_no_card(make):
    from maplelens.tools.class_helper.ui import SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    spot = rows(tool)[0]
    hover(spot, True)
    wait(50)
    hover(spot, False)
    wait(SHOW_MS + 150)
    assert not tool._card.isVisible()


def test_a_spot_without_data_shows_no_card(make):
    from maplelens.tools.class_helper.ui import SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    hover(named(tool, "Fourth"), True)  # a map id with no spot data: spot_card gives None
    wait(SHOW_MS + 100)
    assert not tool._card.isVisible()


def test_moving_to_another_spot_swaps_the_card_in_place(make):
    from maplelens.tools.class_helper.ui import HIDE_MS, SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    first, third = rows(tool)[0], named(tool, "Third")
    hidden = []
    tool._hide_timer.timeout.connect(lambda: hidden.append(1))
    hover(first, True)
    wait(SHOW_MS + 100)
    assert tool._card.isVisible()
    hover(first, False)
    hover(third, True)  # before HIDE_MS runs out
    assert tool._card.isVisible() and tool._card.title() == "Third"
    wait(max(SHOW_MS, HIDE_MS) + 100)
    assert tool._card.isVisible() and tool._card.title() == "Third" and not hidden


def test_hiding_the_tab_hides_the_card(make):
    from maplelens.tools.class_helper.ui import HIDE_MS, SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    tool.tab.show()
    hover(rows(tool)[0], True)
    wait(SHOW_MS + 100)
    assert tool._card.isVisible()
    tool.tab.hide()
    wait(HIDE_MS + 100)
    assert not tool._card.isVisible()


def test_redraw_hides_the_card_and_cancels_a_pending_show(make):
    from maplelens.tools.class_helper.ui import SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    spot = rows(tool)[0]
    hover(spot, True)
    tool._render([("info", "x")])
    wait(SHOW_MS + 150)
    assert not tool._card.isVisible()
    tool.update(R(level=12), RECT, 1)
    hover(rows(tool)[0], True)
    wait(SHOW_MS + 100)
    assert tool._card.isVisible()
    tool._render([("info", "x")])
    assert not tool._card.isVisible()


def test_the_card_never_takes_focus_or_clicks(make):
    from PySide6.QtCore import Qt

    c = make()._card
    assert c.testAttribute(Qt.WA_ShowWithoutActivating)
    assert c.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert c.windowFlags() & Qt.WindowTransparentForInput
    assert c.windowFlags() & Qt.WindowDoesNotAcceptFocus


def test_card_spot_flips_right_and_stays_on_screen():
    from PySide6.QtCore import QPoint, QRect, QSize

    from maplelens.tools.class_helper.ui import card_spot

    screen, size = QRect(0, 0, 1366, 768), QSize(300, 400)
    assert card_spot(QRect(900, 40, 238, 300), 100, size, screen) == QPoint(900 - 8 - 300, 100)
    assert card_spot(QRect(10, 40, 238, 300), 100, size, screen) == QPoint(10 + 238 + 8, 100)
    assert card_spot(QRect(900, 40, 238, 300), 600, size, screen).y() == 768 - 400


def test_a_card_filled_while_shown_fits_its_new_content(make):
    from dataclasses import replace

    from maplelens.tools.class_helper.plan import spot_card
    from maplelens.tools.class_helper.ui import SHOW_MS

    tool = make()
    tool.update(R(level=12), RECT, 0)
    hover(rows(tool)[0], True)
    wait(SHOW_MS + 100)
    tall = tool._card.height()
    card = spot_card(tool._places["000000001"], tool._spots)
    tool._card.fill(replace(card, picture=None), tool._spots)  # as moving to another spot does
    assert tool._card.height() == tool._card.heightForWidth(tool._card.width()) < tall - 100
