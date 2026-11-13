from datetime import datetime

from maplelens.tools.exp_meter.meter import Rate, SessionRate
from maplelens.tools.exp_meter.text import (
    best_lines,
    box_lines,
    format_duration,
    format_last,
    short_name,
)


def test_box_lines_values():
    assert box_lines(Rate(12480, 0.42, 137), SessionRate(10000, 7800), False) == [
        [("Last 5 min", ["748,800 /h", "25.20% /h"]), ("Session · 2h 10m", ["600,000 /h", ""])],
        [("Level up in", ["2h 17m"])],
    ]


def test_box_lines_no_rate():
    assert box_lines(None, None, False) == [
        [("Measuring", ["— /h", "—% /h"]), ("Session", ["— /h", ""])],
        [("Level up in", ["—"])],
    ]


def test_box_lines_early_rate():
    assert box_lines(Rate(12480, 0.42, 137, early=True), None, False)[0][0] == (
        "Measuring",
        ["748,800 /h", "25.20% /h"],
    )


def test_box_lines_session_under_a_minute():
    assert box_lines(None, SessionRate(None, 20), False)[0][1] == ("Session · <1m", ["— /h", ""])


def test_box_lines_left_label_states():
    assert box_lines(Rate(100, 0.1, 5), None, False)[0][0][0] == "Last 5 min"
    assert box_lines(Rate(100, 0.1, 5, paused=True), None, False)[0][0][0] == "Paused"
    assert box_lines(Rate(100, 0.1, 5), None, False, unread=True)[0][0][0] == "Can't read bar"


def test_box_lines_no_level_eta():
    assert box_lines(Rate(100, 0.1, None), None, False)[1] == [("Level up in", ["—"])]


def test_box_lines_waiting():
    assert box_lines(None, None, True) == [[("waiting for game", [])]]


def test_format_duration():
    assert format_duration(137) == "2h 17m"
    assert format_duration(45) == "45m"
    assert format_duration(0.4) == "<1m"


def test_format_last():
    now = datetime(2026, 11, 1, 15, 0).timestamp()
    assert format_last(datetime(2026, 11, 1, 1, 0).timestamp(), now) == "today"
    assert format_last(datetime(2026, 10, 31, 23, 0).timestamp(), now) == "yesterday"
    assert format_last(datetime(2026, 10, 29, 12, 0).timestamp(), now) == "Oct 29"
    assert format_last(datetime(2026, 10, 5, 12, 0).timestamp(), now) == "Oct 5"


def test_box_lines_unread_wins_over_paused():
    rate = Rate(100, 0.1, None, paused=True)
    assert box_lines(rate, None, False, True)[0][0][0] == "Can't read bar"


def test_short_name():
    assert short_name("Victoria Island / Henesys Hunting Ground I") == "Henesys Hunting Ground I"
    assert short_name("No Street") == "No Street"


def test_best_lines_waiting():
    assert best_lines(None, 28, []) == ("Best maps: waiting for your class and level", [])


def test_best_lines_empty_and_rows():
    assert best_lines("Rogue", 28, [])[0] == "Best for Rogue, Lv 28 (±3): no 5-minute visits yet"
    head, rows = best_lines("Rogue", 28, [("Hidden Street / Pig Beach", 700.0, 0.03)])
    assert head == "Best for Rogue, Lv 28 (±3)"
    assert rows == [("Pig Beach", "42,000 EXP/h", "1.80% /h")]


def test_box_lines_long_session_drops_minutes():
    # "Session · 12h 10m" fills the column to the pixel at 214 px: from 10 h, hours only
    assert box_lines(None, SessionRate(100, 9.99 * 3600), False)[0][1][0] == "Session · 9h 59m"
    assert box_lines(None, SessionRate(100, 12.2 * 3600), False)[0][1][0] == "Session · 12h"
