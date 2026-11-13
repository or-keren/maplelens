from pathlib import Path

from maplelens.tools.class_helper.data import (
    MAPS,
    STATS,
    Band,
    Build,
    Skill,
    SpStep,
    load,
)
from maplelens.tools.class_helper.plan import (
    Advice,
    advance_ready,
    ap_advice,
    band_at,
    gear,
    milestones,
    short,
    short_name,
    sp_advice,
    training,
)

SMALL = Path(__file__).parent / "fixtures" / "classes_small.json"

B = Band(1, 200, {"DEX": (25, 0.0)}, "LUK")


def s(str_, dex, int_, luk):
    return dict(zip(STATS, (str_, dex, int_, luk), strict=True))


def test_holds_fill_first_then_the_main_stat():
    a = ap_advice(B, 20, s(4, 20, 4, 30), 10)
    assert a["DEX"] == Advice(add=5) and a["LUK"] == Advice(add=5)
    assert a["STR"] == a["INT"] == Advice()


def test_over_a_hold_puts_the_main_stat_behind():
    a = ap_advice(B, 20, s(4, 35, 4, 20), 0)
    assert a["DEX"] == Advice(over=10) and a["LUK"] == Advice(behind=10)


def test_short_points_still_go_to_the_hold_first():
    a = ap_advice(B, 20, s(4, 20, 4, 30), 3)
    assert a["DEX"] == Advice(add=3, behind=2) and a["LUK"] == Advice(over=2)


def test_stats_outside_the_plan_never_get_points_or_tags():
    a = ap_advice(B, 20, s(4, 25, 9, 30), 5)  # INT rolled 9 at the start
    assert a["INT"] == Advice() and a["LUK"] == Advice(add=5)


def test_growing_hold_and_band_lookup():
    grow = Band(1, 200, {"DEX": (0, 1.0)}, "LUK")
    assert ap_advice(grow, 30, s(4, 28, 4, 40), 2)["DEX"] == Advice(add=2)
    late = Band(30, 200, {"DEX": (0, 1.0)}, "LUK")
    build = Build("x", (Band(1, 30, {}, "LUK"), late), (), (), None, None)
    assert band_at(build, 29).to_level == 30 and band_at(build, 30) is late  # [from, to)
    assert band_at(build, 200) is late


def test_shipped_band_edges():
    from maplelens.tools.class_helper.data import load

    d = load()
    rogue = d.jobs["Rogue"].builds[0]
    assert band_at(rogue, 13).targets(13)["DEX"] == 5
    assert band_at(rogue, 14).targets(14)["DEX"] == 10
    for plan in d.jobs.values():
        for b in plan.builds:
            assert band_at(b, 200) is not None
            for c in b.ap[1:]:
                assert band_at(b, c.from_level) is c


SK = {
    1: Skill(1, "A", "T", 3, {}),
    2: Skill(2, "B", "T", 2, {1: 1}),
    3: Skill(3, "C", "T", 1, {}),
}
STEPS = [SpStep(1, 1), SpStep(2, 2), SpStep(1, 3), SpStep(3, 1)]


def test_points_go_to_the_first_unmet_steps():
    a = sp_advice(STEPS, {1: 0, 2: 0, 3: 0}, 3, SK, "T")
    assert (a[1].add, a[2].add, a[3].add) == (1, 2, 0)


def test_a_step_waits_for_its_prerequisite():
    a = sp_advice([SpStep(2, 2), SpStep(1, 1)], {1: 0, 2: 0, 3: 0}, 2, SK, "T")
    assert (a[1].add, a[2].add) == (1, 1)


def test_off_plan_points_show_and_the_plan_falls_behind():
    sk = {**SK, 4: Skill(4, "D", "T", 5, {})}
    a = sp_advice(STEPS, {1: 0, 2: 0, 3: 0, 4: 2}, 0, sk, "T")
    assert a[4] == Advice(over=2) and a[1] == Advice(behind=1) and a[2] == Advice(behind=1)


def test_unknown_earlier_skill_needs_a_scroll():
    assert sp_advice(STEPS, {2: 0, 3: 0}, 1, SK, "T") is None


def test_unknown_later_skill_still_marks_without_tags():
    a = sp_advice(STEPS, {1: 0, 2: 0}, 3, SK, "T")
    assert (a[1], a[2]) == (Advice(add=1), Advice(add=2))


def test_finished_plan_places_nothing():
    a = sp_advice(STEPS, {1: 3, 2: 2, 3: 1}, 2, SK, "T")
    assert all(v == Advice() for v in a.values())


def test_unknown_prerequisite_needs_a_scroll():
    assert sp_advice([SpStep(2, 2), SpStep(3, 1)], {2: 0, 3: 0}, 1, SK, "T") is None


ROGUE = load(SMALL, MAPS).plan("Rogue")


def test_up_to_three_maps_in_guide_order():
    rows = training(ROGUE, 12)
    assert len(rows) == 3 and all(r.from_level <= 12 <= r.to_level for r in rows)
    assert [r.place.name for r in rows][1:] == ["Third", "Fourth"]


def test_gear_now_next_and_shortfall():
    now, nxt = gear(ROGUE.build("LUK"), 12)
    assert (now.from_level, nxt.from_level) == (10, 15)
    assert short(nxt.item, {"STR": 4, "DEX": 25, "INT": 4, "LUK": 40}) == {"DEX": 5}
    assert short(nxt.item, None) == {}
    assert gear(ROGUE.build("LUK"), 5) == (None, now)


def test_milestones_in_level_order():
    luk, sindit = ROGUE.build("LUK"), ROGUE.build("Sindit")
    assert [(m.level, m.text) for m in milestones(ROGUE, luk, 12)] == [
        (15, "Gear: Second Claw"),
        (30, "Advance: Assassin or Bandit"),
    ]
    gear_step = milestones(ROGUE, luk, 12)[0]
    assert gear_step.item.name == "Second Claw" and gear_step.where is not None
    # a ready advance is left out; Sindit has no gear
    assert [(m.level, m.text) for m in milestones(ROGUE, sindit, 30)] == [
        (30, "Reset AP: Sindit build")
    ]
    assert milestones(ROGUE, sindit, 31) == []


def test_advance_ready_only_at_its_level():
    assert advance_ready(ROGUE, ROGUE.builds[0], 29) is None
    assert advance_ready(ROGUE, ROGUE.builds[0], 30).level == 30


def test_short_name():
    assert short_name("Kerning City Subway / Transfer Area") == "Transfer Area"
    assert short_name("Henesys") == "Henesys"
