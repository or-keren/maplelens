import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplelens.readers import ExpValue, Reading, glyphs, job, map_name, ocr, read_all, skill_window
from maplelens.readers.exp import EXP_DX, EXP_DY, EXP_H, EXP_INK_HI, EXP_INK_LO, EXP_W, read_exp
from maplelens.readers.job import JOB_DX, JOB_DY, JOB_H, read_job
from maplelens.readers.level import LV_DX, LV_DY, LV_H, LV_INK_HI, LV_INK_LO, LV_W, read_level
from maplelens.readers.map_name import known_titles, read_map_name, snap_title
from maplelens.readers.minimap_pos import read_player, read_view
from maplelens.readers.quest_tracker import (
    PARTLY,
    Tracker,
    TrackerLine,
    TrackerQuest,
    read_quest_tracker,
)
from maplelens.readers.quest_window import NAME_UNREADABLE, QuestOpen, read_quest_window
from maplelens.readers.skill_window import SkillRow, SkillWindow, read_skill_window
from maplelens.readers.stat_window import UNREADABLE, StatWindow, parse_stat, read_stat_window

SCREENS = Path(__file__).parent / "fixtures" / "screens"

# One entry per fixture file; None where the value is covered. Fixtures are crops of
# frames already passed through glyphs.normalize. A new resolution = new files + entries.
EXPECTED = {
    "exp_a_2560x1440_100.png": ExpValue(13616, 39.67),
    "exp_b_2560x1440_100.png": ExpValue(20297, 59.14),
    "exp_c_2560x1440_100.png": ExpValue(20842, 60.73),
    "exp_d_2560x1440_100.png": ExpValue(20472, 59.65),
    "exp_covered_2560x1440_100.png": None,  # inventory window over the EXP text
    "level_a_2560x1440_100.png": 23,
    "level_covered_2560x1440_100.png": None,  # grey rectangle pasted over the digits
    "exp_a_1366x768_100.png": ExpValue(29183, 85.03),
    "exp_b_1366x768_100.png": ExpValue(30000, 87.41),
    "exp_c_1366x768_100.png": ExpValue(30684, 89.41),
    "exp_d_1366x768_100.png": ExpValue(29257, 85.25),
    "exp_covered_1366x768_100.png": None,  # grey rectangle pasted over the value
    "level_a_1366x768_100.png": 23,
    "level_covered_1366x768_100.png": None,  # grey rectangle pasted over the digits
    "exp_a_1920x1080_100.png": ExpValue(33764, 98.38),
    "exp_b_1920x1080_100.png": ExpValue(34214, 99.69),  # last frame before the level-up
    "exp_c_1920x1080_100.png": ExpValue(2, 0.0),  # first frame after it
    "exp_d_1920x1080_100.png": ExpValue(409, 1.01),
    "exp_e_1920x1080_100.png": ExpValue(33133, 96.54),
    "exp_f_1920x1080_100.png": ExpValue(506, 1.25),
    "exp_g_1920x1080_100.png": ExpValue(8931, 12.22),  # its "]" sits on the ink cutoff
    "exp_covered_1920x1080_100.png": None,  # grey rectangle pasted over the value
    "level_a_1920x1080_100.png": 23,
    "level_b_1920x1080_100.png": 24,
    "level_covered_1920x1080_100.png": None,  # grey rectangle pasted over the digits
    # Job crops: LV label + class line; the name line below is painted over.
    "job_a_2560x1440_100.png": "Rogue",
    "job_a_1366x768_100.png": "Rogue",
    "job_a_1920x1080_100.png": "Rogue",
    "job_covered_2560x1440_100.png": None,  # grey rectangle pasted over the class line
    "job_covered_1366x768_100.png": None,  # grey rectangle pasted over the class line
    "job_covered_1920x1080_100.png": None,  # grey rectangle pasted over the class line
    # Minimap crops: title bar + title lines only, never the map area.
    "minimap_a_2560x1440_100.png": "Victoria Road / Kerning City",
    "minimap_b_2560x1440_100.png": "Victoria Road / Construction Site North of Kerning City",
    "minimap_c_2560x1440_100.png": "Victoria Road / Sunset Sky",
    "minimap_d_2560x1440_100.png": "Victoria Road / Perion",
    "minimap_e_2560x1440_100.png": "Victoria Road / Lith Harbor",
    "minimap_f_2560x1440_100.png": "Victoria Road / Henesys",
    "minimap_g_2560x1440_100.png": "Victoria Road / Henesys Townstreet",
    "minimap_h_2560x1440_100.png": "Warning Street / The Swamp of Despair I",
    "minimap_i_2560x1440_100.png": "Kerning City Subway / Line 1 <Area 1>",
    "minimap_j_2560x1440_100.png": "Kerning City Subway / Transfer Area",
    "minimap_bar_a_2560x1440_100.png": "Victoria Road / Thieves' Hideout",
    "minimap_bar_b_2560x1440_100.png": "Victoria Road / Subway Ticketing Booth",
    "minimap_bar_c_2560x1440_100.png": "Victoria Road / Perion Department Store",
    "minimap_covered_2560x1440_100.png": None,  # inventory window over the title lines
    "minimap_nominimap_2560x1440_100.png": None,  # game scene pasted over the minimap
    "minimap_a_1366x768_100.png": "Kerning City Subway / Transfer Area",
    "minimap_a_1920x1080_100.png": "Kerning City Subway / Transfer Area",
    # macOS: the Retina capture, 2732x1536 in the game, normalized to 768 rows.
    "exp_mac_2732x1536_100.png": ExpValue(23749, 43.26),
    "level_mac_2732x1536_100.png": 26,
    "job_mac_2732x1536_100.png": "Rogue",
    "minimap_mac_2732x1536_100.png": "Dungeon / Sleepywood",
}

# Player position fixtures: the whole minimap panel, map area included; other players'
# markers painted out. Values: the dot's centre as fractions of the map area, measured
# by hand (map area = the opaque map picture, centred on see-through padding).
EXPECTED_POS = {
    "pos_a_1920x1080_100.png": (0.482, 0.626),  # Transfer Area, map narrower than window
    "pos_b_2560x1440_100.png": (0.392, 0.229),  # Construction Site North, long title
    "pos_c_2560x1440_100.png": (0.552, 0.661),  # Henesys Townstreet, small map
    "pos_d_1366x768_100.png": (0.518, 0.626),  # Transfer Area, native pixels
    "pos_e_2560x1440_100.png": (0.500, 0.795),  # Lith Harbor, map as wide as the window
    "pos_f_2560x1440_100.png": (0.305, 0.777),  # Perion, map taller than the window
    "pos_g_2560x1440_100.png": (0.492, 0.446),  # The Forest of Wisdom, taller, no NPCs
    # The Forest North of Ellinia: 130 px of a 428 px tall picture, hidden portals.
    "pos_fne_bottom_2560x1440_100.png": (0.246, 0.518),
    "pos_fne_mid_2560x1440_100.png": (0.300, 0.446),
    "pos_fne_top_2560x1440_100.png": (0.469, 0.304),
    "pos_fne_bottom_1366x768_100.png": (0.223, 0.830),
    "pos_fne_mid_1366x768_100.png": (0.515, 0.446),  # a monster shows through the minimap
    "pos_fne_top_1366x768_100.png": (0.485, 0.295),
    "pos_tunnel_2560x1440_100.png": (0.493, 0.446),  # Tree Tunnel; a dot painted out
    "pos_bar_2560x1440_100.png": None,  # minimap minimized to its bar
    "pos_covered_2560x1440_100.png": None,  # inventory window over the map area
    "pos_nominimap_1920x1080_100.png": None,  # game scene, no minimap
}

# Stat window crops are native (not normalized): the window plus 3 px of margin. Level 28,
# AP 5, STR 4 / DEX 25 / INT 4 / LUK 122 (+2 gear). `plus`: the single-arrow + button
# centres in the normalized frame, measured at 768 and within 1 px at the other sizes.
_STAT = {
    "level": 28,
    "ap": 5,
    "base": {"STR": 4, "DEX": 25, "INT": 4, "LUK": 122},
    "total": {"STR": 4, "DEX": 25, "INT": 4, "LUK": 124},
}
_PLUS = {"STR": (155, 184), "DEX": (155, 202), "INT": (155, 220), "LUK": (155, 238)}
EXPECTED_STAT = {
    "stat_a_1366x768_100.png": StatWindow(**_STAT, plus=_PLUS),
    "stat_a_1920x1080_100.png": StatWindow(
        **_STAT, plus={k: (x + 1, y) for k, (x, y) in _PLUS.items()}
    ),
    "stat_a_2560x1440_100.png": StatWindow(**_STAT, plus=_PLUS),
    "stat_covered_1366x768_100.png": UNREADABLE,  # inventory over the left half of the rows
    "stat_edge_1366x768_100.png": None,  # window mostly off the left edge: no anchor found
}

# Skill window crops: native, window plus 3 px of margin. Rogue tab, 3 SP; `plus`: the
# single-arrow + centres in the normalized frame (768 measured, within 1 px elsewhere).
_SKILL_ROWS = (
    (4000000, 15),
    (4000001, 15),
    (4001000, 2),
    (4001001, 0),
    (4001002, 0),
    (4001003, 20),
)
_SKILL = SkillWindow(
    "Rogue", 3, tuple(SkillRow(i, lv, (148, 125 + 40 * n)) for n, (i, lv) in enumerate(_SKILL_ROWS))
)
EXPECTED_SKILL = {
    "skill_a_1366x768_100.png": _SKILL,
    "skill_a_1920x1080_100.png": _SKILL,
    "skill_a_2560x1440_100.png": _SKILL,
    "skill_covered_2560x1440_100.png": UNREADABLE,  # title covered, SKILL POINT label visible
    "skill_edge_2560x1440_100.png": None,  # window mostly off the left edge
}

# Quest window crops: native, the window only. The read name is the details body's bold
# line (the quest's own name), never the header or list row, which show its chain's name
# ("Caretaker's Ledger"). A quest with no chain has no bold line: its name is read from
# the selected list row ("Arwen and the Glass Shoe").
EXPECTED_QUEST = {
    "quest_progress_1366x768_100.png": QuestOpen("The Filing Error", True),
    "quest_progress_1920x1080_100.png": QuestOpen("The Filing Error", True),
    "quest_available_1366x768_100.png": QuestOpen("Make a Match Cards Set", False),
    "quest_available_1920x1080_100.png": QuestOpen("Make a Match Cards Set", False),
    "quest_offscreen_1366x768_100.png": UNREADABLE,  # the details pane cut by the screen edge
    "quest_nochain_2560x1440_100.png": QuestOpen("Arwen and the Glass Shoe", False),
}


def screen(name: str):
    return cv2.imread(str(SCREENS / name), cv2.IMREAD_COLOR)


@pytest.fixture(autouse=True)
def fresh_cache():
    glyphs.clear_cache()


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("exp_*.png")))
def test_read_exp(name):
    assert read_exp(screen(name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("level_*.png")))
def test_read_level(name):
    assert read_level(screen(name)) == EXPECTED[name]


def test_exp_partial_text_is_none():
    img = screen("exp_a_2560x1440_100.png")
    x, _ = glyphs.find_anchor(img, "exp_label")
    x0 = x + EXP_DX
    img[:, x0 + int(EXP_W * 0.7) : x0 + EXP_W] = 0
    assert read_exp(img) is None


def _three_plus_two_px(g):
    """A '3' with its upper-left stroke filled in: 2 px off, nearer a '9' than a '3'."""
    g = g.copy()
    g[2, :2] = g[1, :2]
    return g


@pytest.mark.parametrize(
    "name", [n for n, v in EXPECTED.items() if n.startswith("level_") and v == 23]
)
def test_level_digit_2px_off_is_none(name):
    """A digit 2 px off every template reads None, never a neighbouring digit."""
    img = screen(name)
    x, y = glyphs.find_anchor(img, "lv_label")
    x, y = x + LV_DX, y + LV_DY
    box = img[y : y + LV_H, x : x + LV_W]
    m = glyphs.mask(box, LV_INK_LO, LV_INK_HI)
    cols = np.flatnonzero(m.any(axis=0))
    gx = cols[np.flatnonzero(np.diff(cols) > 1)[-1] + 1]  # left edge of the last glyph, the 3
    gy = np.flatnonzero(m[:, gx:].any(axis=1))[0]
    g = m[gy : gy + 7, gx : gx + 7]
    box[gy : gy + 7, gx : gx + 7][_three_plus_two_px(g) & ~g] = 255
    assert read_level(img) is None


SPRITES = Path(__file__).parent.parent / "scripts" / "level_sprites"


@pytest.mark.parametrize("d", "0123456789")
def test_level_reads_every_digit(d):
    """At 1366x768 the game draws the digit images 1:1: each one put in the ones box of
    a level 23 reads as 2<d>."""
    img = screen("level_a_1366x768_100.png")
    three = cv2.imread(str(SPRITES / "3.png"), cv2.IMREAD_UNCHANGED)
    sp = cv2.imread(str(SPRITES / f"{d}.png"), cv2.IMREAD_UNCHANGED)
    opaque = three[..., 3] == 255
    res = cv2.matchTemplate(img, np.ascontiguousarray(three[..., :3]), cv2.TM_SQDIFF)
    _, _, (bx, by), _ = cv2.minMaxLoc(res)
    box = img[by : by + 13, bx : bx + 11]
    box[opaque] = sp[..., :3][opaque]
    assert read_level(img) == int(f"2{d}")


def test_expected_matches_fixture_files():
    native_map = {  # test_map_name_native_ellinia, test_map_name_native_rain_forest
        "title_ellinia_1920x1080_100.png",
        "title_rainforest_1920x1080_100.png",
    }
    assert set(EXPECTED) | set(EXPECTED_POS) | set(EXPECTED_STAT) | set(EXPECTED_SKILL) | set(
        EXPECTED_QUEST
    ) | set(EXPECTED_TRACKER) | native_map == {p.name for p in SCREENS.glob("*.png")}


def test_exp_one_px_noise_is_never_another_value():
    """R17: flip each pixel of an '8' (1366 look); the read is None or the true value."""
    name = "exp_a_1366x768_100.png"
    img = screen(name)
    x, y = glyphs.find_anchor(img, "exp_label")
    x, y = x + EXP_DX, y + EXP_DY
    m = glyphs.mask(img[y : y + EXP_H, x : x + EXP_W], EXP_INK_LO, EXP_INK_HI)
    eight = next(t for c, t in glyphs._font("exp_font") if c == "8" and t.shape[1] < 7)
    th, tw = eight.shape
    gy, gx = next(
        (r, c)
        for r in range(m.shape[0] - th + 1)
        for c in range(m.shape[1] - tw + 1)
        if (m[r : r + th, c : c + tw] == eight).all()
    )
    for yy in range(y + gy, y + gy + th):
        for xx in range(x + gx, x + gx + tw):
            out = img.copy()
            out[yy, xx] = (0, 0, 0) if m[yy - y, xx - x] else (255, 255, 255)
            assert read_exp(out) in (None, EXPECTED[name]), (xx, yy)


needs_ocr = pytest.mark.skipif(ocr.engine() is None, reason="no OCR engine")


def test_crop_maps_the_normalized_box_onto_the_native_shot():
    img = screen("minimap_a_1366x768_100.png")
    native = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    box = (40, 18, 120, 31)
    want = ocr.crop(img, img, box).astype(int)
    got = ocr.crop(img, native, box)
    assert got.shape == want.shape
    assert np.abs(got - want).mean() < 8  # a 1-px shift gives about 18
    assert np.abs(ocr.crop(img, native, (41, 18, 120, 31)) - want).mean() > 15


def test_read_lines_without_engine_is_none(monkeypatch):
    monkeypatch.setattr(ocr, "engine", lambda: None)
    assert ocr.read_lines(np.ones((5, 5), bool)) is None


@needs_ocr
def test_read_lines_empty_mask_has_no_lines():
    assert ocr.read_lines(np.zeros((30, 90), bool)) == []


@needs_ocr
@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("job_*.png")))
def test_read_job(name):
    assert read_job(screen(name)) == EXPECTED[name]


@needs_ocr
@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("minimap_*.png")))
def test_read_map_name(name):
    assert read_map_name(screen(name)) == EXPECTED[name]


@pytest.mark.parametrize(
    "lines, want",
    [
        (["Rogue"], "Rogue"),
        (["Roque"], "Rogue"),
        (["Xyzzy"], None),
        (["Chief"], None),  # "Chief Bandit" with a word dropped, not "Thief"
        (["Herm"], None),  # "Hermit" cut short
        (["Mage (Fire, Poison)"], "Mage (Fire, Poison)"),
        (["Mage (Fire, Poisn)"], "Mage (Fire, Poison)"),
        (["Night", "Lord"], "Night Lord"),
        ([], None),
        (None, None),
    ],
)
def test_job_snaps_to_known_job(monkeypatch, lines, want):
    monkeypatch.setattr(job.ocr, "read_lines", lambda m: lines)
    assert read_job(screen("job_a_1366x768_100.png")) == want


@pytest.mark.parametrize(
    "name, lines, want",
    [
        ("minimap_a_1366x768_100.png", ["A b", "C"], "A b / C"),
        ("minimap_a_1366x768_100.png", ["A b"], None),
        ("minimap_a_1366x768_100.png", ["A", "B", "C"], None),
        ("minimap_a_1366x768_100.png", ["A", "B\ufffd"], None),
        ("minimap_a_1366x768_100.png", ["A", "B\x07"], None),
        ("minimap_a_1366x768_100.png", None, None),
        ("minimap_bar_a_2560x1440_100.png", ["A b : C"], "A b / C"),
        ("minimap_bar_a_2560x1440_100.png", ["A b :", "C"], "A b / C"),
        ("minimap_bar_a_2560x1440_100.png", ["A b C"], None),
        ("minimap_bar_a_2560x1440_100.png", ["A : b : C"], None),
        ("minimap_bar_a_2560x1440_100.png", [": C"], None),
    ],
)
def test_map_name_from_ocr_lines(monkeypatch, name, lines, want):
    monkeypatch.setattr(map_name.ocr, "read_lines", lambda m: lines)
    assert read_map_name(screen(name)) == want


V = "Victoria Road / "


@pytest.mark.parametrize(
    "text, want",
    [
        (V + "Sumset Sky", V + "Sunset Sky"),
        (V + "Lithı Harhor", V + "Lith Harbor"),
        (V + "Lith Harlor", V + "Lith Harbor"),
        (
            V + "Construction Site Nortlı of Kerning City",
            V + "Construction Site North of Kerning City",
        ),
        (V + "kerning City", V + "Kerning City"),
        ("Hidden Street / ist Accompaniment <Bonus>", "Hidden Street / 1st Accompaniment <Bonus>"),
        (V + "The Forest North of", V + "The Forest North of Ellinia"),  # last word dropped
        (V + "The field Up North of", V + "The Field Up North of Ellinia"),  # and a case slip
        # One wrong letter, with a very similar title next to the right one.
        (V + "The Rafn-Forest East of Henesys", V + "The Rain-Forest East of Henesys"),
        ("Dungeon / Ant Tunmel II", "Dungeon / Ant Tunnel II"),
    ],
)
def test_snap_misreads(text, want):
    assert snap_title(text, known_titles()) == want


@pytest.mark.parametrize(
    "text",
    [
        "El Nath / Ice Valley U",  # could be II: one letter from I must not make it I
        "Dungeon / Ant Tunnel N",  # could be IV
        "El Nath / Ice Valley 2",
        "Dungeon / Ant Tunnel 3",
        "El Nath / Ice Valley III",  # not in the map data: not II either
        "Hidden Street / Free Market <27",  # could be <12>
        "Orbis / Orbis Tower <4th Floor7",  # could be <14th Floor>
        "Kerning City Subway / Line 1 <Area 13",
    ],
)
def test_snap_one_letter_never_changes_a_number(text):
    assert snap_title(text, known_titles()) == text


def test_snap_one_letter_from_two_titles_is_kept():
    text = "Dungeon / Ant Tunnel Il"  # one letter from both Ant Tunnel I and Ant Tunnel II
    assert snap_title(text, known_titles()) == text


@pytest.mark.parametrize(
    "text, want",
    [
        ("Warning Street / The Swamp of Despair 1", "Warning Street / The Swamp of Despair I"),
        ("Warning Street / The Swamp of Despair 11", "Warning Street / The Swamp of Despair II"),
        ("Warning Street / The Swamp of Despair I", "Warning Street / The Swamp of Despair I"),
        ("Warning Street / The Swamp of Despair II", "Warning Street / The Swamp of Despair II"),
    ],
)
def test_snap_roman_siblings(text, want):
    assert snap_title(text, known_titles()) == want


@pytest.mark.parametrize(
    "text", [V + "Zzyzx Hollow", "A b / C", V + "Tree Dungeon, Forest Up North", V + "The Forest"]
)
def test_snap_unknown_map_keeps_text(text):
    assert snap_title(text, known_titles()) == text


def test_snap_exact_is_kept():
    text = "Kerning City Subway / Line 1 <Area 1>"
    assert snap_title(text, known_titles()) == text


def test_snap_needs_a_lead_over_runner_up():
    # near-tie between <Area 1>/<Area 3> style siblings must stay unsnapped (SNAP_LEAD)
    text = "Kerning City Subway / Line 1 cArea 13"
    assert snap_title(text, known_titles()) == text


def test_map_name_snaps_misreads(monkeypatch):
    monkeypatch.setattr(map_name.ocr, "read_lines", lambda m: ["Victoria Road", "Sumset Sky"])
    assert read_map_name(screen("minimap_a_1366x768_100.png")) == V + "Sunset Sky"


@needs_ocr
def test_map_name_native_ellinia():
    """Native crop: Windows OCR reads 'Eflinia' from it; the snap fixes it."""
    frame, native, _ = _window_args("title_ellinia_1920x1080_100.png")
    assert read_map_name(frame, native) == V + "Ellinia"


@needs_ocr
def test_map_name_native_rain_forest():
    """Native crop: Windows OCR reads 'Rafn-Forest' from it; the snap fixes it."""
    frame, native, _ = _window_args("title_rainforest_1920x1080_100.png")
    assert read_map_name(frame, native) == V + "The Rain-Forest East of Henesys"


def _job_box(img):
    x, y = glyphs.find_anchor(img, "lv_label")
    return x + JOB_DX, y + JOB_DY


def _flips(img, x0, y0, x1, y1, on, off):
    """Copies of img, each with one pixel in the box flipped: ink -> `off`, else -> `on`."""
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            out = img.copy()
            out[yy, xx] = off if (img[yy, xx] == on).all() or img[yy, xx].min() >= 128 else on
            yield out


@needs_ocr
def test_job_one_px_noise_is_never_another_job():
    name = "job_a_2560x1440_100.png"
    img = screen(name)
    x, y = _job_box(img)
    # Every pixel of the word "Rogue" (5 glyphs, about 37 px wide).
    for out in _flips(img, x, y, x + 40, y + JOB_H, on=(255, 255, 255), off=(60, 60, 60)):
        assert read_job(out) in (None, "Rogue")


@needs_ocr
def test_map_one_px_noise_is_never_another_name():
    name = "minimap_a_2560x1440_100.png"
    img = screen(name)
    # The "K" of "Kerning City": normal-form name line, normalized coordinates.
    for out in _flips(img, 48, 43, 58, 54, on=(255, 255, 255), off=(204, 187, 153)):
        assert read_map_name(out) in (None, EXPECTED[name])


def test_read_all_normalizes_once(monkeypatch):
    from maplelens.readers import exp, job, level, map_name

    seen, calls = [], []
    real = glyphs.normalize
    monkeypatch.setattr(glyphs, "normalize", lambda f: calls.append(1) or real(f))
    for mod, fn, value in [
        (exp, "read_exp", ExpValue(1, 0.5)),
        (level, "read_level", 7),
        (job, "read_job", "Rogue"),
        (map_name, "read_map_name", "A / B"),
    ]:
        monkeypatch.setattr(
            mod, fn, lambda *frames, v=value: seen.append([f.shape for f in frames]) or v
        )
    got = read_all(np.zeros((1440, 2560, 3), np.uint8), 12.5)
    assert got == Reading(12.5, ExpValue(1, 0.5), 7, "Rogue", "A / B")
    assert calls == [1]
    # The word readers (OCR) also get the native frame: they crop their text from it.
    small, native = (768, 1365, 3), (1440, 2560, 3)
    assert seen == [[small], [small], [small, native], [small, native]]


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("pos_*.png")))
def test_read_player(name):
    got, want = read_player(screen(name)), EXPECTED_POS[name]
    if want is None:
        assert got is None
    else:
        assert got is not None
        assert abs(got[0] - want[0]) <= 0.02 and abs(got[1] - want[1]) <= 0.02, got


@pytest.mark.parametrize(
    "name, n",
    [
        ("pos_a_1920x1080_100.png", 0),  # Transfer Area has no NPCs
        ("pos_c_2560x1440_100.png", 1),  # Henesys Townstreet
        ("pos_e_2560x1440_100.png", 5),  # Lith Harbor: 6 shown, 1 hit by the inpainting
    ],
)
def test_read_view_npc_markers(name, n):
    view = read_view(screen(name))
    assert len(view.npcs) == n
    assert read_player(screen(name)) == (view.dot[0] / view.size[0], view.dot[1] / view.size[1])


@pytest.mark.parametrize(
    "name, n",
    [
        ("pos_c_2560x1440_100.png", 0),  # Henesys Townstreet: none in view
        ("pos_d_1366x768_100.png", 1),  # Transfer Area, native pixels
        ("pos_e_2560x1440_100.png", 3),  # Lith Harbor: the sea isn't a spiral
        ("pos_f_2560x1440_100.png", 5),  # Perion: 2 more cut by the window's edge
        ("pos_g_2560x1440_100.png", 2),  # The Forest of Wisdom
    ],
)
def test_read_view_portal_spirals(name, n):
    assert len(read_view(screen(name)).portals) == n


# The minimap's other markers, BGR, sampled from the owner's grabs.
OTHER_DOTS = [
    (0, 0, 255),  # other player (red)
    (0, 142, 254),  # party member (orange)
    (3, 222, 241),  # the party marker's "+" (yellow-orange)
    (70, 104, 255),  # faded player dot (salmon)
    (255, 221, 17),  # cyan player dot
    (0, 228, 0),  # NPC (green)
    (165, 192, 8),  # portal spiral (blue)
    (226, 0, 226),  # magenta NPC
    (221, 255, 0),  # cyan triangle
]


def test_read_player_ignores_other_dots():
    """The dot, recoloured to each other marker and pasted elsewhere, changes nothing."""
    img = screen("pos_a_1920x1080_100.png")
    want = read_player(img)
    assert want is not None
    # The "you" dot with its ring (dot pixels x 82..87, y 141..146 in this fixture).
    patch = img[138:150, 79:91].copy()
    fill = glyphs.mask(patch, (25, 180, 200), (110, 255, 255))
    spots = [(25, 80), (60, 80), (120, 80), (140, 100), (30, 120), (100, 120), (30, 160)]
    spots += [(120, 160), (60, 170)]
    for colour, (x, y) in zip(OTHER_DOTS, spots, strict=True):
        dot = patch.copy()
        dot[fill] = colour
        img[y : y + 12, x : x + 12] = dot
    assert read_player(img) == want


def test_read_player_two_you_dots_is_none():
    """A second dot-shaped yellow blob (e.g. map art): no guessing which one is you."""
    img = screen("pos_a_1920x1080_100.png")
    assert read_player(img) is not None
    img[80:92, 25:37] = img[138:150, 79:91].copy()  # the dot and its ring, top-left of the map
    assert read_player(img) is None


def test_read_player_window_over_map_edge_is_none():
    """A window over the map's edge and the frame, dot still visible: the map area is
    unknown, so no position rather than a wrong one."""
    img = screen("pos_a_1920x1080_100.png")
    img[150:199, 0:60] = (200, 200, 200)
    assert read_player(img) is None


def test_read_all_fills_player():
    frame = np.zeros((768, 1366, 3), np.uint8)
    fixture = screen("pos_a_1920x1080_100.png")
    frame[: fixture.shape[0], : fixture.shape[1]] = fixture
    got = read_all(frame, 1.0)
    assert got.player is not None
    assert got.player == read_player(frame)
    assert got.minimap is not None and got.minimap == read_view(frame)


def test_mac_vision_request_failure_raises(monkeypatch):
    vision = pytest.importorskip("Vision")
    from maplelens.readers import ocr_mac

    class Failing:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithData_options_(self, data, options):
            return self

        def performRequests_error_(self, requests, error):
            return False, "boom"

    monkeypatch.setattr(vision, "VNImageRequestHandler", Failing)
    with pytest.raises(RuntimeError, match="boom"):
        ocr_mac.recognize(np.full((40, 40), 255, np.uint8))


@pytest.mark.parametrize(
    "text, want",
    [
        ("25", (25, 25)),
        ("124(122+2)", (122, 124)),
        ("4(4+0)", (4, 4)),
        ("25(20+4)", None),
        ("", None),
        ("2a", None),
        ("25(20+", None),
    ],
)
def test_parse_stat(text, want):
    assert parse_stat(text) == want


def _window_args(name):
    """(frame, native, scale) of a native crop: frame is the 768-scale resize."""
    native = screen(name)
    scale = int(re.search(r"_\d+x(\d+)_", name)[1]) / 768
    return _scaled(native, scale), native, scale


def _scaled(native, scale):
    if scale == 1:
        return native
    return cv2.resize(native, None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("stat_*.png")))
def test_read_stat_window(name):
    got, want = read_stat_window(*_window_args(name)), EXPECTED_STAT[name]
    if isinstance(want, StatWindow) and isinstance(got, StatWindow):
        assert (got.level, got.ap, got.base, got.total) == (
            want.level,
            want.ap,
            want.base,
            want.total,
        )
        for k, (x, y) in want.plus.items():
            assert abs(got.plus[k][0] - x) <= 1 and abs(got.plus[k][1] - y) <= 1, (k, got.plus)
    else:
        assert got == want


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("exp_a_*.png")))
def test_no_stat_window_reads_none(name):
    assert read_stat_window(*_window_args_any(name)) is None


def _window_args_any(name):
    native = screen(name)
    scale = native.shape[0] / 768
    return _scaled(native, scale), native, scale


@pytest.mark.parametrize(
    "name, ks",
    [
        ("stat_a_2560x1440_100.png", range(0, 15, 2)),
        ("stat_a_1920x1080_100.png", range(0, 12, 2)),  # to ceil(2s) = 3 frame px
    ],
)
def test_stat_reads_at_every_offset(name, ks):
    """Dropping native rows and columns moves the window to another sub-pixel offset."""
    scale = int(name.split("_")[2].split("x")[1]) / 768
    want = EXPECTED_STAT[name]
    for k in ks:
        native = screen(name)[k:, k:]
        got = read_stat_window(_scaled(native, scale), native, scale)
        assert isinstance(got, StatWindow), k
        assert (got.level, got.ap, got.base, got.total) == (
            want.level,
            want.ap,
            want.base,
            want.total,
        )
        for key, (x, y) in want.plus.items():
            assert abs(got.plus[key][0] - (x - k / scale)) <= 1, (k, key, got.plus)
            assert abs(got.plus[key][1] - (y - k / scale)) <= 1, (k, key, got.plus)


def test_stat_ap_check(monkeypatch):
    from maplelens.readers import stat_window

    args = _window_args("stat_a_1366x768_100.png")
    assert isinstance(read_stat_window(*args), StatWindow)
    real = stat_window.window.read_number_text
    monkeypatch.setattr(
        stat_window.window,
        "read_number_text",
        lambda win, box: "7" if box[0] == stat_window.AP_X else real(win, box),
    )
    assert read_stat_window(*args) == UNREADABLE  # 4 + 25 + 4 + 122 + 7 > 25 + 5 * 27


def test_stat_light_overlay_over_a_tail_is_not_read():
    """A light, borderless patch over "(122+2)" must not read as a plain "124" LUK."""
    native = screen("stat_a_1366x768_100.png")
    native[3 + 228 : 3 + 243, 3 + 90 : 3 + 140] = 222  # the LUK strip's tail, field grey
    assert read_stat_window(native) == UNREADABLE


def test_stat_plus_off_frame_is_unreadable():
    """Fields all read, but the frame's right edge cuts through the + buttons."""
    native = screen("stat_a_1366x768_100.png")[:, :155]
    assert read_stat_window(native) == UNREADABLE


def test_number_text_ambiguous_glyph_is_none(monkeypatch):
    """Two chars that match a glyph about equally: no guess."""
    from maplelens.readers import window

    win = np.full((20, 40, 3), 222, np.uint8)
    g = next(t for c, t in window.font() if c == "8")
    win[3:16, 5 : 5 + g.shape[1]] = g[..., None].astype(np.uint8)
    box = (0, 0, 40, 20)
    assert window.read_number_text(win, box) == "8"
    # An "8" that is mostly a "0": blend the middle row in.
    win[3 + 6, 5:12] = 222
    assert window.read_number_text(win, box) in (None, "0")  # never a confident wrong read
    monkeypatch.setitem(window._fonts, "window_font", [("8", g), ("B", g)])
    assert window.read_number_text(win, box) is None  # identical scores: no margin


def test_number_text_light_patch_off_the_glyphs_is_none():
    """The background check: a non-ink patch that differs from the field voids the read."""
    from maplelens.readers import window

    win = np.full((20, 40, 3), 222, np.uint8)
    g = next(t for c, t in window.font() if c == "8")
    win[3:16, 5 : 5 + g.shape[1]] = g[..., None].astype(np.uint8)
    box = (0, 0, 40, 20)
    assert window.read_number_text(win, box) == "8"
    win[2:4, 30:36] = 222 - window.BG_TOL - 8  # darker than the field, but above INK
    assert window.read_number_text(win, box) is None


def test_every_known_skill_name_snaps_to_itself():
    from maplelens.readers import skill_window

    names = list(skill_window.known_skills())
    assert [n for n in names if skill_window._snap(n, names) != n] == []


def test_skill_name_near_twins_do_not_snap():
    from maplelens.readers import skill_window

    twins = ["Blunt Weapon Mastery", "Blunt Weapon Booster"]
    assert skill_window._snap("Blunt Weapon Maoster", twins) is None  # 0.95 vs 0.90
    assert skill_window._snap("Blunt Weapon Mastery", twins) == twins[0]  # clean read
    assert skill_window._snap(
        "Final Attack: Spear", ["Final Attack: Spear", "Final Attack: Polearm"]
    )


def _same_skills(got, want, k=0, scale=1):
    assert isinstance(got, SkillWindow), got
    assert (got.tab, got.sp) == (want.tab, want.sp)
    assert [(r.skill, r.level) for r in got.rows] == [(r.skill, r.level) for r in want.rows]
    for g, w in zip(got.rows, want.rows, strict=True):
        assert abs(g.plus[0] - (w.plus[0] - k / scale)) <= 1, (k, g)
        assert abs(g.plus[1] - (w.plus[1] - k / scale)) <= 1, (k, g)


@needs_ocr
@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("skill_*.png")))
def test_read_skill_window(name, monkeypatch):
    read, seen = skill_window.ocr.read_lines, []
    monkeypatch.setattr(skill_window.ocr, "read_lines", lambda m: seen.append(read(m)) or seen[-1])
    got, want = read_skill_window(*_window_args(name)), EXPECTED_SKILL[name]
    if isinstance(want, SkillWindow):
        assert isinstance(got, SkillWindow), (got, seen)  # seen: the names as the OCR read them
        _same_skills(got, want)
    else:
        assert got == want, seen


def test_a_name_with_ink_read_as_nothing_is_unreadable(monkeypatch):
    """A covered name the OCR reads as nothing is not a blank row."""
    calls = []
    monkeypatch.setattr(skill_window.ocr, "read_lines", lambda m: calls.append(m) and [])
    assert read_skill_window(*_window_args("skill_a_1366x768_100.png")) == UNREADABLE
    assert len(calls) == 1  # the first row's ink, and no further


@needs_ocr
def test_unknown_skill_name_is_unreadable(monkeypatch):
    monkeypatch.setattr(skill_window, "known_skills", dict)
    assert read_skill_window(*_window_args("skill_a_1366x768_100.png")) == UNREADABLE


@needs_ocr
def test_skill_level_over_max_is_unreadable(monkeypatch):
    real = skill_window.known_skills()
    monkeypatch.setattr(skill_window, "known_skills", lambda: real)
    monkeypatch.setattr(skill_window, "_max", lambda skill: 14 if skill == 4000000 else 20)
    assert read_skill_window(*_window_args("skill_a_1366x768_100.png")) == UNREADABLE


@needs_ocr
def test_skill_tab_is_the_job_every_row_shares(monkeypatch):
    names = {"Nimble Body": [(1, "A")], "Keen Eyes": [(2, "B")]}
    monkeypatch.setattr(skill_window, "known_skills", lambda: names)
    assert read_skill_window(*_window_args("skill_a_1366x768_100.png")) == UNREADABLE


@needs_ocr
@pytest.mark.parametrize(
    "name, ks",
    [
        ("skill_a_2560x1440_100.png", range(0, 15, 2)),
        ("skill_a_1920x1080_100.png", range(0, 12, 2)),
    ],
)
def test_skill_reads_at_every_offset(name, ks):
    scale = int(name.split("_")[2].split("x")[1]) / 768
    for k in ks:
        native = screen(name)[k:, k:]
        got = read_skill_window(_scaled(native, scale), native, scale)
        _same_skills(got, EXPECTED_SKILL[name], k, scale)


def test_skill_plus_off_frame_is_unreadable():
    native = screen("skill_a_1366x768_100.png")[:, :140]
    assert read_skill_window(native) == UNREADABLE


@pytest.mark.parametrize("name", sorted(p.name for p in SCREENS.glob("stat_a_*.png")))
def test_no_skill_window_in_a_stat_window(name):
    assert read_skill_window(*_window_args(name)) is None


@needs_ocr
@pytest.mark.parametrize("name", [n for n, q in EXPECTED_QUEST.items() if q != UNREADABLE])
def test_read_quest_window(name, monkeypatch):
    from maplelens.readers import quest_window

    read, seen = quest_window.ocr.read_lines, []
    monkeypatch.setattr(quest_window.ocr, "read_lines", lambda m: seen.append(read(m)) or seen[-1])
    assert read_quest_window(*_window_args(name)) == EXPECTED_QUEST[name], seen


def test_quest_window_off_screen_is_unreadable():
    assert read_quest_window(*_window_args("quest_offscreen_1366x768_100.png")) == UNREADABLE


@pytest.mark.parametrize(
    "name", sorted(p.name for p in SCREENS.glob("*.png") if p.name not in EXPECTED_QUEST)
)
def test_no_quest_window(name):
    assert read_quest_window(*_window_args(name)) is None


def test_completed_tab_reads_none():
    """Nothing to help with on the Completed tab: the pink tab moved there reads None."""
    native = screen("quest_progress_1366x768_100.png")
    assert read_quest_window(native) is not None
    tabs = native[24:42].copy()
    native[24:42, 150:222] = tabs[:, 78:150]  # In Progress's pink onto Completed
    native[24:42, 78:150] = tabs[:, 4:76]  # Available's grey onto In Progress
    assert read_quest_window(native) is None


def test_known_quest_names():
    from maplelens.readers.quest_window import known_quest_names

    names = known_quest_names()
    assert "The Filing Error" in names and len(names) > 100
    assert "[Event] Trick or Treat!" in names  # left out of the quests on purpose
    assert "Arwen and the Glass Shoe" in names


def test_no_open_tab_reads_none():
    """No pink tab: not a quest window."""
    native = screen("quest_progress_1366x768_100.png")
    native[24:42, 78:150] = native[24:42, 4:76].copy()  # Available's grey onto In Progress
    assert read_quest_window(native) is None


@needs_ocr
def test_chainless_quest_with_no_row_selected_is_name_unreadable():
    """No bold name line and no selected list row: nothing to read the name from."""
    native, scale = screen("quest_nochain_2560x1440_100.png"), 1440 / 768
    native[130:175, 40:420] = 255  # the selected row
    assert read_quest_window(_scaled(native, scale), native, scale) == NAME_UNREADABLE


@needs_ocr
@pytest.mark.parametrize(
    "name, rows",
    [
        ("quest_available_1366x768_100.png", (147, 156)),
        ("quest_progress_1366x768_100.png", (199, 210)),
    ],
)
def test_quest_name_line_painted_white_is_name_unreadable(name, rows, monkeypatch):
    """Without its name line, the first white-body line is description text, and the
    selected list row shows the chain's name: neither is the quest's name."""
    from maplelens.readers import quest_window

    read, seen = quest_window.ocr.read_lines, []
    monkeypatch.setattr(quest_window.ocr, "read_lines", lambda m: seen.append(read(m)) or seen[-1])
    native = screen(name)
    native[rows[0] : rows[1], 256:524] = 255
    assert read_quest_window(native) == NAME_UNREADABLE
    assert any(line[0].startswith(("Caretaker's Ledger", "Maple World's")) for line in seen), seen


@pytest.mark.parametrize(
    "text, want",
    [
        ("Arwen and the Glass Shoe", "Arwen and the Glass Shoe"),
        ("Anwen and the Glass Shoe", "Arwen and the Glass Shoe"),  # snapped
        ("Arwen and the Glass S...", "Arwen and the Glass Shoe"),  # cut: a unique prefix
        ("Arwen and the Glass S…", "Arwen and the Glass Shoe"),
        # A name ending in "." reads like a cut one: still the one name it starts.
        (
            "Asking After Mrs. Ming Ming, the Town Resident.",
            "Asking After Mrs. Ming Ming, the Town Resident.",
        ),
        (
            "Asking After Mrs. Ming Ming, the Town Res..",
            "Asking After Mrs. Ming Ming, the Town Resident.",
        ),
        (
            "Asking After Mr. Pickall, the Town Resident",
            "Asking After Mr. Pickall, the Town Resident ",
        ),
        ("Caretaker's Ledger", None),  # a chain's name, no quest's
        ("Mai's Training", None),  # a chain's name and its first quest's: which one?
        ("Mai's...", None),  # the chain's, or Mai's Final Training's
        ("Icarus's...", None),  # prefix of a chain's name and of a quest's
        ("The...", None),  # many quests
        ("", None),
    ],
)
def test_quest_name_from_list_row(text, want):
    from maplelens.readers.quest_window import _listed

    assert _listed(text) == want


@pytest.mark.parametrize(
    "lines, want",
    [
        (["[Event] Trick or Treat!"], QuestOpen("[Event] Trick or Treat!", True)),  # left out
        (["[Event] Trick or Treat1"], QuestOpen("[Event] Trick or Treat!", True)),  # snapped
        (["The Filing Error"], QuestOpen("The Filing Error", True)),
        (["A Quest Nobody Ever Wrote"], NAME_UNREADABLE),  # name-shaped, in neither set
        (["It seems that Casey in Henesys Park knows"], NAME_UNREADABLE),  # a description line
        (["The Filing \ufffdrror"], NAME_UNREADABLE),
        ([], NAME_UNREADABLE),
        (None, NAME_UNREADABLE),  # no OCR engine
    ],
)
def test_quest_name_from_ocr_lines(monkeypatch, lines, want):
    from maplelens.readers import quest_window

    monkeypatch.setattr(quest_window.ocr, "read_lines", lambda m: lines)
    assert read_quest_window(screen("quest_progress_1366x768_100.png")) == want


@needs_ocr
def test_read_all_fills_quest():
    frame = np.zeros((768, 1366, 3), np.uint8)
    fixture = screen("quest_progress_1366x768_100.png")
    frame[100 : 100 + fixture.shape[0], 300 : 300 + fixture.shape[1]] = fixture
    assert read_all(frame, 1.0).quest == EXPECTED_QUEST["quest_progress_1366x768_100.png"]


@needs_ocr
@pytest.mark.parametrize("name", [n for n in EXPECTED_QUEST if "x768_" not in n])
def test_quest_reads_at_every_offset(name):
    scale = int(re.search(r"_\d+x(\d+)_", name)[1]) / 768
    for k in range(6):
        native = screen(name)[k:, k:]
        assert read_quest_window(_scaled(native, scale), native, scale) == EXPECTED_QUEST[name], k


# Quest Helper crops: native, the panel's corner (it touches the crop's top and right
# edges, as in the full frame). Names and targets are snapped to quests.json's, so a cut
# name reads as the full name; "Maple Leaf" isn't in the data and reads as is.
RAINBOW = "A rainbow snail shell that makes wishes come true!?"
ARWEN = TrackerQuest("Arwen and the Glass Shoe", (TrackerLine(0, 1, "Arwen's Glass Shoe"),))
FILING = TrackerQuest("The Filing Error", (TrackerLine(0, 25, "Torn Ledger Pages"),))
SHELL = TrackerQuest(RAINBOW, (TrackerLine(0, 1, "Rainbow-colored Snail Shell"),))
EVENT = TrackerQuest("[Event] The Journey Begins", (TrackerLine(0, 30, "Maple Leaf"),))


def donating(have):
    return TrackerQuest("Donating to Kerning City", (TrackerLine(have, 30, "Red Snail Shell"),))


EXPECTED_TRACKER = {
    "tracker_one_1920x1080_100.png": Tracker(1, False, (FILING,)),
    "tracker_three_1920x1080_100.png": Tracker(3, False, (FILING, SHELL, donating(0))),
    "tracker_min_1920x1080_100.png": Tracker(3, True, ()),
    "tracker_empty_1920x1080_100.png": Tracker(0, False, ()),
    "tracker_a_1366x768_100.png": Tracker(3, False, (ARWEN, FILING, SHELL)),
    "tracker_eight_1920x1080_100.png": Tracker(4, False, (ARWEN, FILING, SHELL, donating(28))),
    "tracker_event_1920x1080_100.png": Tracker(4, False, (ARWEN, FILING, SHELL, EVENT)),
    "tracker_dark_1920x1080_100.png": Tracker(
        5, False, (ARWEN, FILING, SHELL, donating(10), EVENT)
    ),
}


@needs_ocr
@pytest.mark.parametrize("name", sorted(EXPECTED_TRACKER))
def test_read_quest_tracker(name):
    assert read_quest_tracker(*_window_args(name)) == EXPECTED_TRACKER[name]


@pytest.mark.parametrize(
    "name",
    [
        "quest_progress_1920x1080_100.png",
        "stat_a_1920x1080_100.png",
        "title_ellinia_1920x1080_100.png",
        "minimap_a_1920x1080_100.png",
    ],
)
def test_no_tracker(name):
    assert read_quest_tracker(*_window_args(name)) is None


def test_tracker_cut_by_the_frame_edge_is_unreadable():
    native = screen("tracker_three_1920x1080_100.png")[:, :-120]  # the right edge cuts it
    scale = 1080 / 768
    assert read_quest_tracker(_scaled(native, scale), native, scale) == UNREADABLE


@needs_ocr
def test_tracker_block_painted_over_is_partly():
    """A block covered (here: painted with the panel's own colour) reads fewer than n."""
    native = screen("tracker_three_1920x1080_100.png")
    native[168:210, 40:340] = (130, 130, 142)  # the third block's name and line; title 3/5
    scale = 1080 / 768
    assert read_quest_tracker(_scaled(native, scale), native, scale) == PARTLY


@needs_ocr
@pytest.mark.parametrize(
    "name", ["tracker_three_1920x1080_100.png", "tracker_eight_1920x1080_100.png"]
)
def test_tracker_reads_at_every_offset(name):  # native drops 0-5: to ceil(2 * 1080/768) = 3 px
    """Dropping native rows and columns moves the panel to another sub-pixel offset."""
    from maplelens.readers import quest_tracker

    scale = 1080 / 768
    for k in range(6):
        quest_tracker._words.clear()  # OCR every offset, not just the first
        native = screen(name)[k:, k:]
        got = read_quest_tracker(_scaled(native, scale), native, scale)
        assert got == EXPECTED_TRACKER[name], k


@needs_ocr
def test_read_all_fills_tracker():
    frame = np.zeros((768, 1366, 3), np.uint8)
    fixture = screen("tracker_a_1366x768_100.png")
    frame[: fixture.shape[0], -fixture.shape[1] :] = fixture
    assert read_all(frame, 1.0).tracker == EXPECTED_TRACKER["tracker_a_1366x768_100.png"]
