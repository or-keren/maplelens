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


def test_picture_box_keeps_a_small_maps_sides():
    # a small map: the status bar is narrower than the picture, the minimap stays at its edge
    from maplelens.capture import picture_box

    f = _letterboxed(128, 132)
    f[128:488, :100] = f[128:488, 540:] = 0
    f[130:140, 10:60] = 200  # the minimap's title
    assert picture_box(f) == (0, 128, 640, 360)
