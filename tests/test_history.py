from pytest import approx

from maplelens.tools.exp_meter.history import (
    best_maps,
    best_rate,
    history,
    open_db,
    save_segment,
)
from maplelens.tools.exp_meter.meter import Segment


def _seg(start, exp=0, active_s=60.0, level=44, map_name="Henesys", job="Hero", pct=0.0):
    return Segment(start, start + 300, map_name, job, level, exp, pct, active_s)


def test_history_groups_and_averages(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, exp=600, pct=1.2))
    save_segment(conn, _seg(100, exp=0))
    (row,) = history(conn)
    assert row.exp_per_min == approx(300)
    assert row.pct_per_min == approx(0.6)
    assert row.active_s == 120
    assert row.last == 400


def test_level_split_rows(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, level=44))
    save_segment(conn, _seg(100, level=45))
    assert len(history(conn)) == 2


def test_resave_same_segment_replaces(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, exp=100))
    save_segment(conn, _seg(0, exp=900))
    (row,) = history(conn)
    assert row.exp_per_min == approx(900)


def test_order_newest_first(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, map_name="Old"))
    save_segment(conn, _seg(100, map_name="New"))
    assert [r.map_name for r in history(conn)] == ["New", "Old"]


def test_zero_active_excluded(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, active_s=0.0))
    assert history(conn) == []


def test_best_rate(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, exp=600, level=44))
    save_segment(conn, _seg(100, exp=900, level=45))
    assert best_rate(conn, "Henesys") == approx(900)
    assert best_rate(conn, "Nowhere") is None


def test_short_visits_hidden(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, Segment(0, 299, "Henesys", "Hero", 44, 600, 1.2, 60.0))
    assert history(conn) == []
    assert best_rate(conn, "Henesys") is None
    assert best_maps(conn, {"Hero"}, 44) == []


def test_best_maps_job_line_level_range_top_three(tmp_path):
    conn = open_db(tmp_path / "t.db")
    visits = [
        ("A", "Rogue", 28, 600),
        ("B", "Thief", 29, 900),
        ("C", "Assassin", 31, 300),
        ("D", "Assassin", 32, 1200),
        ("E", "Bandit", 30, 5000),  # other branch
        ("F", "Assassin", 35, 5000),  # out of the level range
    ]
    for i, (m, job, lvl, exp) in enumerate(visits):
        save_segment(conn, _seg(i * 1000, exp=exp, level=lvl, map_name=m, job=job))
    rows = best_maps(conn, {"Rogue", "Thief", "Assassin"}, 31)
    assert [r[0] for r in rows] == ["D", "B", "A"]
    assert rows[0][1] == approx(1200)


def test_best_maps_skips_maps_with_under_a_minute_of_training(tmp_path):
    conn = open_db(tmp_path / "t.db")
    save_segment(conn, _seg(0, exp=500, active_s=10.0, map_name="One lucky kill"))
    save_segment(conn, _seg(1000, exp=600, map_name="Real"))
    assert [r[0] for r in best_maps(conn, {"Hero"}, 44)] == ["Real"]
