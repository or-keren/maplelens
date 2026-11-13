from dataclasses import replace

import pytest

from maplelens.readers import ExpValue, Reading
from maplelens.tools.exp_meter.meter import ExpMeter, monster_free_maps

MAP = "Dungeon / Ant Tunnel III"


def R(t, raw, pct, level=22, job="Rogue", map_name=MAP):
    return Reading(t, ExpValue(raw, pct), level, job, map_name)


def feed(m, *args, **kw):
    """Feed a reading twice (t and t+0.5) so it confirms at t+0.5."""
    r = R(*args, **kw)
    m.feed(r)
    m.feed(replace(r, t=r.t + 0.5))


def steady(m, n, step_s=30, start_pct=10.0):
    for i in range(n):
        feed(m, i * step_s, int((start_pct + 0.5 * i) * 100), start_pct + 0.5 * i)


def test_steady_gain_rate():
    m = ExpMeter()
    for i in range(13):
        feed(m, i * 30, 1000 + 100 * i, 10 + 0.5 * i)
    rate = m.rate(360.5)
    assert rate.exp_per_min == pytest.approx(200)
    assert rate.pct_per_min == pytest.approx(1.0)
    assert rate.minutes_to_level == pytest.approx((100 - 16.0) / 1.0)


def test_rate_from_the_second_gain_marked_early_under_a_minute():
    def meter(kills):
        m = ExpMeter()
        steady(m, kills, step_s=20)
        return m.rate(20 * kills)

    assert meter(1) is None  # one reading only sets the baseline
    assert meter(2) is None  # the first gain only starts the clock
    rate = meter(3)  # 40 s of active time
    assert rate.early and rate.exp_per_min == pytest.approx(150)
    assert not meter(5).early  # 80 s


def test_short_gaps_count_long_gaps_dont():
    m = ExpMeter()
    for i, t in enumerate([0, 60, 300, 330]):
        feed(m, t, 1000 + 100 * i, 10 + 0.5 * i)
    assert m.open_segment().active_s == pytest.approx(60 + 30)


def test_level_up_counts_across_wrap():
    m = ExpMeter()
    for i, pct in enumerate([94, 95, 96, 97, 98]):
        feed(m, i * 30, pct * 1000, pct)
    feed(m, 150, 1000, 1.0, level=23)
    # 4 gains of 1.0 at level 22, then (100 - 98) + 1 = 3.0 across the wrap;
    # the first gain only starts the clock, so 6.0 over 120 s
    assert m.rate(150.5).pct_per_min == pytest.approx(6.0 / (120 / 60))
    closed = m.pop_closed()
    assert len(closed) == 1
    assert closed[0].level == 22
    assert closed[0].pct == pytest.approx(7.0)
    assert closed[0].exp == 4000 + 3000
    seg = m.open_segment()
    assert seg.level == 23
    assert seg.pct == 0


def test_death_not_counted():
    m = ExpMeter()
    for i, pct in enumerate([47, 48, 49, 50]):
        feed(m, i * 30, pct * 1000, pct)
    before = (m.open_segment().pct, m.rate(130).pct_per_min)
    feed(m, 120, 45000, 45)
    assert (m.open_segment().pct, m.rate(130).pct_per_min) == before


def test_jump_not_counted():
    m = ExpMeter()
    steady(m, 13)  # 12 gains of 0.5, last pct 16.0
    feed(m, 390, 2600, 26.0)  # +10 jump
    feed(m, 420, 2650, 26.5)  # counts from the new baseline
    assert m.open_segment().pct == pytest.approx(6.5)
    # window (121, 421]: gains at i = 5..12 and i = 14, nine of 0.5 over 300 s
    assert m.rate(421).pct_per_min == pytest.approx(0.9)


def test_single_frame_misread_ignored():
    m = ExpMeter()
    feed(m, 0, 500, 5.0)
    m.feed(R(30, 999, 9.99))
    feed(m, 60, 500, 5.0)
    assert m.open_segment().pct == 0
    assert m.rate(100) is None  # no gains, so no active time


def test_map_change_closes_segment():
    m = ExpMeter()
    steady(m, 3)
    feed(m, 90, 1100, 11.0, map_name="Other Map")
    closed = m.pop_closed()
    assert [s.map_name for s in closed] == [MAP]
    assert closed[0].pct == pytest.approx(1.0)
    assert m.open_segment().map_name == "Other Map"
    assert m.pop_closed() == []


def test_death_then_map_change_counts_nothing():
    m = ExpMeter()
    steady(m, 4)
    feed(m, 120, 500, 5.0, map_name="Town")
    closed = m.pop_closed()
    assert [s.pct for s in closed] == [pytest.approx(1.5)]
    seg = m.open_segment()
    assert seg.map_name == "Town"
    assert seg.pct == 0
    assert seg.exp == 0
    assert m.rate(100).pct_per_min == pytest.approx(1.0)


def test_paused_stretch_adds_no_active_time():
    m = ExpMeter()
    feed(m, 0, 1000, 10.0)
    for _ in range(4):
        m.feed(None)
    feed(m, 50, 1100, 10.5)
    seg = m.open_segment()
    assert seg.active_s == 0
    assert seg.pct == 0  # the first gain after the stretch only starts the clock, as live


def test_unreadable_map_keeps_the_segment():
    m = ExpMeter()
    steady(m, 2)
    feed(m, 60, 1000, 11.0, map_name=None)
    feed(m, 90, 1100, 11.5)
    assert m.pop_closed() == []
    assert m.open_segment().start == 0.5


def test_close_closes_open_segment():
    m = ExpMeter()
    steady(m, 2)
    m.close(100)
    assert len(m.pop_closed()) == 1
    assert m.open_segment() is None


def test_covered_bar_keeps_baseline():
    m = ExpMeter()
    steady(m, 3)  # last pct 11.0
    for i in range(4):
        r = Reading(90 + i * 10, None, 22, "Rogue", MAP)
        m.feed(r)
    feed(m, 130, 1150, 11.5)
    assert m.open_segment().pct == pytest.approx(1.5)
    assert m.rate(131).pct_per_min == pytest.approx(1.0 / (100 / 60))


def test_covered_level_up_never_negative():
    m = ExpMeter()
    feed(m, 0, 50000, 50.0)
    feed(m, 30, 51000, 51.0)
    for t, level in [(60, 22), (90, 23)]:
        for dt in (0, 0.5):
            m.feed(Reading(t + dt, None, level, "Rogue", MAP))
    feed(m, 120, 60000, 30.0, level=23)
    segs = [*m.pop_closed(), m.open_segment()]
    assert all(s.pct >= 0 and s.exp >= 0 for s in segs)
    assert segs[0].pct == pytest.approx(1.0)
    assert m.rate(150).pct_per_min > 0


def _no_map(m, t0, t1, raw, pct):
    """Readings every 10 s from t0 to t1 with no gain and the map unreadable."""
    for t in range(t0, t1, 10):
        m.feed(R(t, raw, pct, map_name=None))


def test_paused_gain_not_credited_to_segment():
    m = ExpMeter()
    steady(m, 3)  # segment pct 1.0, counted live from the gain at 60.5
    _no_map(m, 70, 200, 1100, 11.0)  # longer than HOLD_S
    feed(m, 200, 1150, 11.5, map_name=None)  # after an idle stretch: starts the clock
    feed(m, 230, 1200, 12.0, map_name=None)
    assert m.open_segment().pct == pytest.approx(1.0)
    assert m.rate(231).pct_per_min == pytest.approx(1.0)  # 60.5's and 230.5's gains, 1 min


def test_a_map_unread_for_a_while_still_counts():
    m = ExpMeter()
    steady(m, 5)  # counted gains at 30..120: 120 s
    for i in range(1, 4):  # a minute of kills with the minimap's title covered
        feed(m, 120 + 30 * i, 1200 + 50 * i, 12 + 0.5 * i, map_name=None)
    assert m.session().active_s == pytest.approx(210)
    assert m.open_segment().active_s == pytest.approx(210)


def test_single_dropped_frame_keeps_accrual():
    m = ExpMeter()
    feed(m, 0, 1000, 10.0)
    feed(m, 30, 1050, 10.5)
    m.feed(None)
    feed(m, 60, 1100, 11.0)
    assert m.open_segment().active_s == pytest.approx(60)


def test_rate_after_a_minute_of_active_time_even_if_app_started_earlier():
    m = ExpMeter()
    m.feed(None)  # app running long before any game reading
    for i in range(4):  # baseline at 1000.5; 1030.5 starts the clock; 1060.5, 1090.5 count
        feed(m, 1000 + i * 30, 1000 + 100 * i, 10 + 0.5 * i)
    rate = m.rate(1091)
    assert rate.pct_per_min == pytest.approx(1.0)
    assert not rate.paused


def test_afk_gap_neither_counts_nor_decays():
    m = ExpMeter()
    steady(m, 5)  # gains of 0.5 at 30.5 .. 120.5, active 120 s
    before = m.rate(121).pct_per_min
    assert m.rate(400).pct_per_min == pytest.approx(before)
    assert m.rate(400).paused
    feed(m, 600, 1300, 13.0)  # first gain after AFK: 1.0, gap 479.5 s, not counted
    assert m.rate(601).pct_per_min == pytest.approx(before)
    feed(m, 630, 1350, 13.5)
    assert m.rate(631).pct_per_min == pytest.approx(2.5 / (150 / 60))


def test_window_is_last_five_active_minutes_across_a_gap():
    m = ExpMeter()
    steady(m, 11)  # 10 gains of 0.5 over 300 active s, ending 300.5 at 15.0%
    for i in range(1, 5):  # 4 gains of 1.0; the one at 900.5 follows AFK, so it starts a stretch
        feed(m, 900 + (i - 1) * 30, 1500 + 100 * i, 15.0 + i)
    # window: the 3 counted 1.0 gains (90 s) + the last 7 old 0.5 gains (210 s)
    assert m.rate(991).pct_per_min == pytest.approx((3.0 + 3.5) / 5)


def test_walk_from_town_is_not_training_time():
    m = ExpMeter()
    feed(m, 0, 1000, 10.0)  # app started in town
    for i in range(1, 5):  # first kill 80 s later, then one every 30 s
        feed(m, 50 + i * 30, 1000 + 100 * i, 10 + 0.5 * i)
    # only the 3 gains after the first kill count: 1.5 % over 90 s
    assert m.rate(171).pct_per_min == pytest.approx(1.0)


def test_lasting_jump_is_learned_after_three_kills():
    """A 2x event or a richer map: every kill is suddenly 6x the old size, and stays so."""
    m = ExpMeter()
    steady(m, 13)  # 12 gains of 0.5 at 30.5 .. 360.5, last pct 16.0
    for i in range(1, 6):  # 5 gains of 3.0 at 390.5 .. 510.5
        feed(m, 360 + i * 30, 1600 + 300 * i, 16.0 + 3.0 * i)
    # the first two look like misreads; the third agrees, so it and the rest count
    assert m.open_segment().pct == pytest.approx(6.0 + 3 * 3.0)
    # window: the 3 counted 3.0 gains (gaps 90, 30, 30) + the last 5 old 0.5 gains (150 s)
    rate = m.rate(511)
    assert rate.pct_per_min == pytest.approx((9.0 + 2.5) / 5)
    assert not rate.paused


@pytest.mark.parametrize("first", [3, 15])  # the break right after the first kills, or later
def test_a_break_between_kills_is_not_training_time(first):
    """Buffing, walking to the spot, looting: a minute with no kill, under the idle cutoff."""
    m = ExpMeter()
    before = [2 * i for i in range(first)]
    kills = before + [before[-1] + 60 + 2 * i for i in range(60)]  # then 2 min of a kill / 2 s
    for i, t in enumerate(kills):
        feed(m, t, 1000 + 10 * i, 10 + 0.01 * i)
    # one kill per 2 s is 300 EXP/min; the break used to cut it until it left the window
    assert m.rate(kills[-1] + 1).exp_per_min == pytest.approx(300)
    seg = m.open_segment()  # the History row: the same sums
    assert seg.active_s == pytest.approx(2 * (len(kills) - 2))
    assert seg.exp / seg.active_s * 60 == pytest.approx(300)


def every(step, n, start=0):
    return [start + step * i for i in range(n)]


def pulls(kills, gap, wait, n):
    """n pulls of `kills` kills `gap` s apart, `wait` s between pulls."""
    return [((kills - 1) * gap + wait) * c + gap * i for c in range(n) for i in range(kills)]


def with_break(before, brk, after):
    b = every(2, before)
    return b + every(2, after, b[-1] + brk)


@pytest.mark.parametrize(
    "kills, live, history",
    [
        pytest.param(every(2, 150), 18000, 18000, id="steady"),
        pytest.param(with_break(3, 60, 40), 18000, 18000, id="60s setup after 3 kills"),
        pytest.param(with_break(60, 45, 30), 18000, 18000, id="45s loot stop"),
        # History is a little above the live rate: it starts and ends partway through a pull
        pytest.param(pulls(4, 1, 28, 30), 4645, 4749, id="4 per pull, 28s wait"),
        pytest.param(pulls(4, 1, 32, 30), 4114, 4208, id="4 per pull, 32s wait"),
        pytest.param(pulls(4, 1, 40, 30), 3349, 3427, id="4 per pull, 40s wait"),
        pytest.param(pulls(8, 2, 20, 15), 8471, 8743, id="8 per pull, 20s respawn"),
        pytest.param(every(40, 30), 900, 900, id="slow killer"),
        # breaks are 20% of the gaps, over the 10% the rule can find: they count, as on main
        pytest.param(pulls(5, 2, 60, 12), 2647, 2810, id="60s break every 5 kills"),
    ],
)
def test_rate_by_play_pattern(kills, live, history):
    """Kills of 10 EXP: the live rate and the History row, in EXP per hour."""
    m = ExpMeter()
    for i, t in enumerate(kills):
        feed(m, t, 1000 + 10 * i, 10 + 0.01 * i)
    assert m.rate(kills[-1] + 1).exp_per_min * 60 == pytest.approx(live, abs=1)
    seg = m.open_segment()
    assert seg.exp / seg.active_s * 3600 == pytest.approx(history, abs=1)


TOWN = "Victoria Road / Henesys"


def test_quest_reward_in_town_not_counted():
    m = ExpMeter()
    steady(m, 20, step_s=10)  # last pct 19.5 at t=190
    before = m.rate(190.5).pct_per_min
    feed(m, 230, 2190, 21.9, map_name=TOWN)  # a +2.4% reward after a 40 s walk
    assert m.rate(230.5).pct_per_min == pytest.approx(before)
    assert m.open_segment().pct == 0


def test_quests_in_a_row_dont_teach_the_jump_filter():
    m = ExpMeter()
    steady(m, 20, step_s=10)
    before = m.rate(190.5).pct_per_min
    for i in range(3):  # three +10% rewards: a lasting jump if they were kills
        feed(m, 230 + 5 * i, 2950 + 1000 * i, 29.5 + 10 * i, map_name=TOWN)
    feed(m, 300, 4950, 49.5)  # back on the field: the walk only starts the clock
    feed(m, 310, 6950, 69.5)  # and a +20% misread is still a misread
    assert m.rate(310.5).pct_per_min == pytest.approx(before)


def test_quests_only_no_rate():
    m = ExpMeter()
    for i in range(5):
        feed(m, i * 20, 1000 + 300 * i, 10 + 3 * i, map_name=TOWN)
    assert m.rate(80.5) is None


def test_town_with_monsters_counts_kills():
    assert TOWN in monster_free_maps()
    assert "Maple Road / East Entrance to Mushroom Town" not in monster_free_maps()


def test_session_none_before_first_counted_gain():
    m = ExpMeter()
    feed(m, 0, 1000, 10.0)  # the first reading is only the baseline
    assert m.session() is None
    feed(m, 20, 1100, 10.5)  # timed from the segment's open at 0.5
    s = m.session()
    assert s.active_s == pytest.approx(20)
    assert s.exp_per_min is None  # under a minute


def test_session_matches_open_segment():
    m = ExpMeter()
    steady(m, 13)
    s, seg = m.session(), m.open_segment()
    assert s.active_s == pytest.approx(seg.active_s)
    assert s.exp_per_min == pytest.approx(seg.exp / seg.active_s * 60)


def test_session_spans_level_up_and_map_change():
    m = ExpMeter()
    for i, pct in enumerate([94, 95, 96, 97, 98]):
        feed(m, i * 30, pct * 1000, pct)
    feed(m, 150, 1000, 1.0, level=23)  # level-up: closes the level-22 segment
    feed(m, 180, 2000, 2.0, level=23)
    feed(m, 210, 3000, 3.0, level=23, map_name="Other Map")  # map change
    feed(m, 240, 4000, 4.0, level=23, map_name="Other Map")
    segs = [*m.pop_closed(), m.open_segment()]
    assert len(segs) >= 3
    s = m.session()
    assert s.active_s == pytest.approx(sum(seg.active_s for seg in segs))
    assert s.exp_per_min * s.active_s / 60 == pytest.approx(sum(seg.exp for seg in segs))


@pytest.mark.parametrize("brk, active", [(1800, 120 + 30), (1801, 30)])
def test_session_split_boundary(brk, active):
    m = ExpMeter()
    steady(m, 5)  # counted gains at 30..120: 120 s
    last = 4 * 30
    feed(m, last + brk - 30, 5000, 50.0)  # after the break: starts the clock only
    feed(m, last + brk, 5100, 50.5)  # counted, `brk` s after the last counted gain
    assert m.session().active_s == pytest.approx(active)


def test_session_kept_while_game_gone():
    m = ExpMeter()
    steady(m, 5)
    for _ in range(200):  # the game closed for a while
        m.feed(None)
    feed(m, 730, 5000, 50.0)
    feed(m, 760, 5100, 50.5)
    assert m.session().active_s == pytest.approx(120 + 30)


def test_session_skips_paused_gains():
    m = ExpMeter()
    steady(m, 5)
    _no_map(m, 130, 260, 1200, 12.0)  # map unreadable longer than HOLD_S
    feed(m, 270, 1250, 12.5, map_name=None)  # not counted
    assert m.session().active_s == pytest.approx(120)


def test_session_skips_town_quest_rewards():
    m = ExpMeter()
    steady(m, 5)
    before = m.session()
    feed(m, 160, 9000, 40.0, map_name=TOWN)
    assert m.session() == before


def test_session_is_the_sum_of_its_segments_at_different_paces():
    # a fast map then a slow one, 10+ gains each so the break filter runs: the slow map's
    # kills must not look like breaks next to the fast map's
    m = ExpMeter()
    pct = 10.0
    for i in range(200):  # a kill every 3 s: over 90% of the gains
        feed(m, i * 3, int(pct * 100), pct)
        pct += 0.1
    for i in range(1, 21):  # a kill every 40 s on another map
        feed(m, 597 + i * 40, int(pct * 100), pct, map_name="Other Map")
        pct += 0.1
    segs = [*m.pop_closed(), m.open_segment()]
    assert m.session().active_s == pytest.approx(sum(s.active_s for s in segs))
    assert segs[-1].active_s > 600  # the slow map counts
