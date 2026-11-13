from maplelens.capture import pick_window

WINDOWS = [(1, "MapleStory Classic Thief Guide - Chrome"), (2, "MapleStory"), (3, "Notepad")]


def test_pick_window_prefers_exact():
    assert pick_window(WINDOWS, "MapleStory") == 2


def test_pick_window_falls_back_to_substring():
    assert pick_window(WINDOWS, "Thief Guide") == 1


def test_pick_window_none():
    assert pick_window(WINDOWS, "Nope") is None


def test_pick_window_exact_only():
    assert pick_window(WINDOWS, "MapleStory", exact=True) == 2
    assert pick_window(WINDOWS[:1], "MapleStory", exact=True) is None


def _letterboxed(top, bottom, left=0, right=0, h=360, w=640):
    import numpy as np

    f = np.full((h + top + bottom, w + left + right, 3), 60, np.uint8)
    f[:top] = f[f.shape[0] - bottom :] = 0
    f[:, :left] = 0
    f[:, f.shape[1] - right :] = 0
    return f


def test_picture_box_cuts_bars():
    from maplelens.capture import picture_box

    assert picture_box(_letterboxed(128, 132)) == (0, 128, 640, 360)
    assert picture_box(_letterboxed(0, 0, 30, 30)) == (30, 0, 640, 360)
    assert picture_box(_letterboxed(0, 0)) == (0, 0, 640, 360)


def test_picture_box_keeps_a_black_sky():
    from maplelens.capture import picture_box

    f = _letterboxed(0, 0)
    f[:20] = 0  # the top of a map, no bar under the status bar
    assert picture_box(f) == (0, 0, 640, 360)
    f = _letterboxed(10, 10)
    f[10:40] = 0  # black sky under the top bar: cut only to the bottom bar's height + slack
    assert picture_box(f) == (0, 14, 640, 356)


def test_picture_box_takes_a_loading_screen_for_no_bars():
    from maplelens.capture import picture_box

    f = _letterboxed(0, 0)
    f[:] = 0
    f[160:180, 200:440] = 200  # only the map's title lit, mid-fade
    assert picture_box(f) == (0, 0, 640, 360)


def _dark_map(left=0, right=0):
    """A dark cave over a narrow status bar: the art beside the bar stops short of the
    picture's edges, by a few px that a lit-column read would take for side bars."""
    f = _letterboxed(0, 0, left, right)
    f[:, left : left + 640] = 0
    f[340:, left + 160 : left + 480] = 120  # the status bar, narrower than the picture
    f[345:350, left + 6 : left + 636] = 90  # cave art, black at both edges
    return f


def test_picture_box_takes_a_dark_maps_edges_for_picture():
    from maplelens.capture import picture_box

    assert picture_box(_dark_map()) == (0, 0, 640, 360)
    assert picture_box(_dark_map(30, 30)) == (30, 0, 640, 360)


def test_picture_box_takes_a_narrow_loading_title_for_no_bars():
    from maplelens.capture import picture_box

    f = _letterboxed(0, 0)
    f[:] = 0
    f[170:190, 305:335] = 200  # a short title, black all round it
    assert picture_box(f) == (0, 0, 640, 360)


def test_picture_box_keeps_a_small_maps_sides():
    # a small map: the status bar is narrower than the picture, the minimap stays at its edge
    from maplelens.capture import picture_box

    f = _letterboxed(128, 132)
    f[128:488, :100] = f[128:488, 540:] = 0
    f[130:140, 10:60] = 200  # the minimap's title
    assert picture_box(f) == (0, 128, 640, 360)
