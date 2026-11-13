from pathlib import Path

import cv2
import numpy as np
import pytest
from pytest import approx

from maplelens.readers.minimap_pos import MinimapView, read_view
from maplelens.tools.path_arrow import camera
from maplelens.tools.path_arrow.camera import (
    by_size,
    can_place,
    picture_scroll,
    player_world,
    to_screen,
    to_world,
)
from maplelens.tools.path_arrow.maps import MapInfo, Minimap, Portal, load, picture

MM = Minimap(2000, 1000, 1000, 500)
VIEW = (1366, 768)
SCREENS = Path(__file__).parent / "fixtures" / "screens"


def test_to_world_inverts_minimap_formula():
    x, y = 300, -120
    f = ((x + MM.cx) / MM.w, (y + MM.cy) / MM.h)
    assert to_world(f, MM) == approx((x, y))


def test_to_screen_centres_player_mid_map():
    assert to_screen((0, 0), (0, 0), MM, VIEW)[0] == approx(683)


def test_to_screen_clamps_at_left_edge():
    player = (-950, 0)  # 50 from the map's left edge
    assert to_screen(player, player, MM, VIEW)[0] == approx(50)


def test_to_screen_narrow_map_centres_map():
    mm = Minimap(1000, 1000, 400, 500)  # map centre at world x 100
    for px in (-300, 100, 500):
        assert to_screen((100, 0), (px, 0), mm, VIEW)[0] == approx(683)


def test_to_screen_no_clamp_at_map_top():
    player = (0, -MM.cy - 200)  # above the minimap's top: the camera still follows
    assert to_screen(player, player, MM, VIEW)[1] == approx(384 - camera.CAM_DY)


def test_to_screen_clamps_at_map_bottom():
    player = (0, MM.h - MM.cy - 10)
    assert to_screen(player, player, MM, VIEW)[1] == approx(768 - 10)


def test_camera_constants_from_spike():
    # Name-tag ground truth over 76 grabs on Transfer Area, Construction Site North,
    # Sunset Sky and Line 1 (1366, 1920, 2560): portal x within ~5 px of the visible
    # portal, feet settle at y 545 = 384 + 161. NPC marker offset: Construction Site North
    # and Henesys Townstreet; clipped-map scroll checked on Kerning City, Henesys, Perion
    # and Lith Harbor (all 26 frames within 0.2 minimap px of the picture shift).
    assert camera.WORLD_PER_PX == 1.0
    assert camera.CAM_DY == -161.0
    assert camera.SCALE == 16
    assert (camera.NPC_DX, camera.NPC_DY) == (-0.6, -6.9)


# A clipped map: picture 400x100 px, window 200x100 px.
BIG_MM = Minimap(6400, 1600, 800, 800)
NPCS = ((-400, 0), (800, -320), (1600, 160), (2400, -480), (4000, 0))


def marks(scroll, npcs=NPCS, mm=BIG_MM):
    """Where the window shows each NPC, scrolled by `scroll` px, if inside it."""
    out = []
    for x, y in npcs:
        mx = (x + mm.cx) / 16 + camera.NPC_DX - scroll
        my = (y + mm.cy) / 16 + camera.NPC_DY
        if 0 <= mx < 200 and 0 <= my < 100:
            out.append((mx, my))
    return tuple(out)


def big(npcs=NPCS):
    return MapInfo("1", "s", "n", True, BIG_MM, (), None, npcs)


def test_player_world_unclipped_uses_fraction():
    info = MapInfo("1", "s", "n", True, MM, (), None)
    view = MinimapView((125, 62), (62.5, 31.0), ())
    assert player_world(view, info) == approx(to_world((0.5, 0.5), MM))


def test_player_world_clipped_from_npc_markers():
    view = MinimapView((200, 100), (100.0, 50.0), marks(37))
    assert player_world(view, big()) == approx(((100 + 37) * 16 - 800, 50 * 16 - 800))


def test_player_world_too_few_markers_is_none():
    view = MinimapView((200, 100), (100.0, 50.0), marks(37)[:1])
    assert player_world(view, big()) is None


def test_player_world_ambiguous_is_none():
    # NPCs every 800 units: a shift of 50 px matches as well as the true one.
    npcs = tuple((x, 0) for x in range(-400, 5600, 800))
    view = MinimapView((200, 100), (100.0, 50.0), marks(60, npcs))
    assert player_world(view, big(npcs)) is None


def test_player_world_lith_harbor_fixture():
    # pos_e (s2560b_023): window 209 of 391 px, scrolled 146 px (picture shift vs a
    # frame scrolled 77 px: 69 px).
    view = read_view(cv2.imread(str(SCREENS / "pos_e_2560x1440_100.png")))
    info = load()["010000000"]
    assert len(view.npcs) >= 5
    x, _ = player_world(view, info)
    assert x == approx((view.dot[0] + 146) * 16 - info.minimap.cx, abs=16)


def test_player_world_perion_fixture():
    # pos_f (s2560b_021): window 112 of 193 px tall, stopped at the picture's bottom
    # (scrolled 80 px down); 203 of 204 px wide, so not scrolled sideways.
    view = read_view(cv2.imread(str(SCREENS / "pos_f_2560x1440_100.png")))
    mm = load()["010004000"].minimap
    got = player_world(view, load()["010004000"])
    want = (view.dot[0] * 16 - mm.cx, (view.dot[1] + 80) * 16 - mm.cy)
    assert got == approx(want, abs=16)


def test_player_world_by_portals_forest_of_wisdom_fixture():
    # pos_g: 112 of 200 px tall, no NPCs; its two portal spirals give the scroll.
    view = read_view(cv2.imread(str(SCREENS / "pos_g_2560x1440_100.png")))
    info = load()["010002020"]
    assert can_place(view, info)
    got = player_world(view, info)
    assert got is not None
    assert got[0] == approx(view.dot[0] * 16 - info.minimap.cx, abs=16)  # not scrolled sideways


def test_player_world_perion_by_portals_alone():
    view = read_view(cv2.imread(str(SCREENS / "pos_f_2560x1440_100.png")))
    info = load()["010004000"]
    mm = info.minimap
    got = player_world(MinimapView(view.size, view.dot, (), view.portals), info)
    assert got == approx((view.dot[0] * 16 - mm.cx, (view.dot[1] + 80) * 16 - mm.cy), abs=16)


def test_can_place():
    clipped = MinimapView((200, 100), (100.0, 50.0), ())
    assert can_place(clipped, big())
    assert not can_place(clipped, big(NPCS[:1]))  # too few markers to ever match the scroll
    fits = MinimapView((125, 62), (62.5, 31.0), ())
    assert can_place(fits, MapInfo("1", "s", "n", True, MM, (), None))
    assert not can_place(fits, MapInfo("1", "s", "n", True, None, (), None))


def test_player_world_bigger_view_is_none():
    # 10 px wider than MM's 125x62 picture: another map's minimap, not this one.
    view = MinimapView((135, 62), (67.5, 31.0), ())
    assert player_world(view, MapInfo("1", "s", "n", True, MM, (), None)) is None


def test_by_size_tells_same_title_maps_apart():
    maps = {
        "a": MapInfo("a", "s", "n", True, Minimap(1408, 760, 0, 0), (), None),  # 88x47.5
        "b": MapInfo("b", "s", "n", True, Minimap(1498, 850, 0, 0), (), None),  # 93.6x53.1
        "c": MapInfo("c", "s", "other", True, Minimap(1408, 760, 0, 0), (), None),
    }
    assert by_size(maps, "s / n", MinimapView((88, 47), (1.0, 1.0), ())).id == "a"
    assert by_size(maps, "s / n", MinimapView((94, 53), (1.0, 1.0), ())).id == "b"
    assert by_size(maps, "s / n", MinimapView((60, 40), (1.0, 1.0), ())) is None
    twins = dict(maps, d=MapInfo("d", "s", "n", True, Minimap(1408, 760, 0, 0), (), None))
    assert by_size(twins, "s / n", MinimapView((88, 47), (1.0, 1.0), ())) is None


def test_hidden_portals_predict_no_spiral():
    # Two portals in view at scroll 37: as spirals they place the player; hidden, they
    # draw nothing, so spirals seen there can't be theirs.
    spots = ((400, 0), (1600, -320))
    seen = tuple(
        ((x + BIG_MM.cx) / 16 + camera.PORTAL_DX - 37, (y + BIG_MM.cy) / 16 + camera.PORTAL_DY)
        for x, y in spots
    )
    view = MinimapView((200, 100), (100.0, 50.0), (), seen)

    def info(hidden):
        portals = tuple(Portal(x, y, "2", hidden) for x, y in spots)
        return MapInfo("1", "s", "n", True, BIG_MM, portals, None)

    assert player_world(view, info(False)) == approx(((100 + 37) * 16 - 800, 50 * 16 - 800))
    assert player_world(view, info(True)) is None
    assert can_place(view, info(False)) and not can_place(view, info(True))


# The Forest North of Ellinia (010002070): 130x428 px picture, 19 hidden portals. Scrolls
# found by the picture match and checked by eye against the picture; the bottom ones also
# by its two portal spirals. Mid frames show no NPC and at most one spiral.
FNE = "010002070"
EXPECTED_SCROLL = {
    "pos_fne_bottom_2560x1440_100.png": (0, 316),
    "pos_fne_mid_2560x1440_100.png": (0, 271),
    "pos_fne_top_2560x1440_100.png": (0, 0),
    "pos_fne_bottom_1366x768_100.png": (0, 316),
    "pos_fne_mid_1366x768_100.png": (0, 263),  # a monster shows through the minimap
    "pos_fne_top_1366x768_100.png": (0, 0),
}


def fixture_view(name):
    return read_view(cv2.imread(str(SCREENS / name)))


@pytest.mark.parametrize("name", sorted(EXPECTED_SCROLL))
def test_player_world_by_picture_fixtures(name):
    view, info = fixture_view(name), load()[FNE]
    sx, sy = EXPECTED_SCROLL[name]
    want = ((view.dot[0] + sx) * 16 - info.minimap.cx, (view.dot[1] + sy) * 16 - info.minimap.cy)
    assert player_world(view, info, picture(FNE)) == approx(want, abs=32)  # 2 minimap px


def test_forest_north_mid_has_too_few_markers():
    # Why the picture is needed: the markers alone can't place the player here.
    assert player_world(fixture_view("pos_fne_mid_2560x1440_100.png"), load()[FNE]) is None


def test_picture_scroll_ignores_painted_dots():
    view = fixture_view("pos_fne_mid_2560x1440_100.png")
    painted = view.pixels.copy()
    disc = np.ones((6, 6), bool)  # a 24 px dot, like ours
    for cy, cx in ((0, 0), (0, 5), (5, 0), (5, 5)):
        disc[cy, cx] = disc[cy, abs(cx - 1)] = disc[abs(cy - 1), cx] = False
    # Other players' red and a party member's orange, away from our own dot.
    for (x, y), bgr in (
        ((90, 20), (40, 40, 230)),
        ((100, 80), (30, 140, 250)),
        ((15, 70), (40, 40, 230)),
    ):
        painted[y - 3 : y + 3, x - 3 : x + 3][disc] = bgr
    other = MinimapView(view.size, view.dot, view.npcs, view.portals, painted)
    assert picture_scroll(other, picture(FNE)) == approx(
        picture_scroll(view, picture(FNE)), abs=0.5
    )


def test_picture_scroll_repeating_picture_is_none():
    rng = np.random.default_rng(1)
    tile = rng.integers(0, 256, (40, 40, 4), dtype=np.uint8)
    tile[:, :, 3] = 255
    pic = np.tile(tile, (10, 3, 1))  # 400 x 120, the same 40x40 tile everywhere
    view = MinimapView((100, 60), (50.0, 30.0), (), (), pic[85:145, 10:110, :3].copy())
    assert picture_scroll(view, pic) is None


def test_picture_scroll_wrong_map_is_none():
    view = fixture_view("pos_fne_mid_2560x1440_100.png")
    assert picture_scroll(view, picture("010004000")) is None  # Perion's picture


def test_picture_and_markers_agree():
    # Perion's red and orange rocks must not be mistaken for other players' dots.
    for name, id in (
        ("pos_e_2560x1440_100.png", "010000000"),
        ("pos_f_2560x1440_100.png", "010004000"),
    ):
        view, info = fixture_view(name), load()[id]
        s = picture_scroll(view, picture(id))
        assert s is not None, name
        assert player_world(view, info, picture(id)) == approx(player_world(view, info), abs=16)


def test_can_place_with_picture():
    view = MinimapView((200, 100), (100.0, 50.0), ())
    assert not can_place(view, big(npcs=()))
    assert can_place(view, big(npcs=()), np.zeros((100, 400, 4), np.uint8))


def test_player_world_tree_tunnel_by_picture():
    # The Tree Tunnel's walls are one even texture: the best scroll scores 0.0033, the
    # next one (the tunnel's top) only 0.0116. Clearly worse by ratio, not by a fixed gap.
    view, info = fixture_view("pos_tunnel_2560x1440_100.png"), load()["010002071"]
    assert player_world(view, info) is None  # one spiral in view: markers can't
    want = (view.dot[0] * 16 - info.minimap.cx, (view.dot[1] + 75) * 16 - info.minimap.cy)
    assert player_world(view, info, picture(info.id)) == approx(want, abs=32)


def test_player_world_henesys_on_a_mac_fullscreen():
    # The Mac's 1.107x stretch blurs the minimap: the dot is a yellow roof's size, and the
    # picture's best scroll (191, 0) scores over PIC_MAX_MSE; the NPCs and portals place it.
    view, info = fixture_view("pos_henesys_3024x1700_100.png"), load()["010001000"]
    want = ((view.dot[0] + 191) * 16 - info.minimap.cx, view.dot[1] * 16 - info.minimap.cy)
    assert player_world(view, info, picture(info.id)) == approx(want, abs=16)
