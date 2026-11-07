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
