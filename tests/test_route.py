from maplelens.tools.path_arrow.maps import Cab, MapInfo, Portal
from maplelens.tools.path_arrow.route import Step, Trip, plan


def mk(id, portals=(), cab=None):
    return MapInfo(id, "S", id, False, None, tuple(Portal(x, 0, t) for x, t in portals), cab)


def graph():
    ms = [
        mk("A", [(0, "B")], Cab(5, 6, ("D",))),
        mk("B", [(0, "A"), (0, "C")]),
        mk("C", [(0, "B"), (0, "D")]),
        mk("D", [(0, "C")]),
        mk("E"),
        mk("X", [(0, "B")]),
    ]
    return {m.id: m for m in ms}


def ids(steps):
    return [s.map_id for s in steps]


def test_plan_fewest_hops():
    s = plan(graph(), "A", "D", False)
    assert ids(s) == ["A", "B", "C", "D"] and not any(x.cab for x in s)
    assert plan(graph(), "A", "D", True) == [Step("A", True), Step("D", False)]


def test_plan_unreachable_is_none():
    assert plan(graph(), "A", "E", False) is None
    assert plan(graph(), "A", "E", True) is None


def test_trip_advance():
    t = Trip(graph(), "A", "D", False)
    t.on_map("B")
    assert t.index == 1 and not t.arrived


def test_trip_jump_ahead():
    t = Trip(graph(), "A", "D", False)
    t.on_map("D")
    assert t.arrived


def test_trip_back_to_earlier_map_rewinds():
    t = Trip(graph(), "A", "D", False)
    steps = t.steps
    t.on_map("C")
    t.on_map("B")
    assert t.index == 1 and t.steps is steps


def test_trip_reroutes_off_route_keeping_taxi():
    t = Trip(graph(), "A", "D", False)
    t.on_map("X")
    assert ids(t.steps) == ["X", "B", "C", "D"] and t.index == 0 and not t.taxi


def test_trip_start_at_goal_arrives():
    t = Trip(graph(), "D", "D", False)
    assert t.arrived and t.target((0, 0)) is None


def test_target_nearest_portal():
    ms = {"B": mk("B", [(0, "C"), (1000, "C")]), "C": mk("C")}
    assert Trip(ms, "B", "C", False).target((900, 0)) == (1000, 0)


def test_target_cab_step():
    assert Trip(graph(), "A", "D", True).target((0, 0)) == (5, 6)


def hidden_trip(portals):
    here = MapInfo(
        "H", "S", "H", False, None, tuple(Portal(x, 0, "B", h) for x, h in portals), None
    )
    maps = {"H": here, "B": mk("B", [(0, "H")])}
    return Trip(maps, "H", "B", False)


def test_hidden_next_follows_the_target():
    trip = hidden_trip([(0, True), (1000, False)])
    assert trip.hidden_next((10, 0)) is True
    assert trip.hidden_next((990, 0)) is False
    assert trip.hidden_next(None) is False  # not every portal to B is hidden


def test_hidden_next_unknown_position_all_hidden():
    assert hidden_trip([(0, True)]).hidden_next(None) is True


def test_hidden_next_cab_step_or_arrived_is_false():
    cab = Trip(graph(), "A", "D", True)  # leaves A by cab
    assert cab.steps[0].cab and cab.hidden_next(None) is False
    there = hidden_trip([(0, True)])
    there.on_map("B")
    assert there.arrived and there.hidden_next(None) is False


def test_target_is_the_npc_on_arrival():
    t = Trip(graph(), "A", "B", False, at=(50, 60))
    assert t.target((0, 0)) == (0, 0)  # en route: the portal
    t.on_map("B")
    assert t.arrived and t.target((0, 0)) == (50, 60)
    u = Trip(graph(), "A", "B", False)
    u.on_map("B")
    assert u.target((0, 0)) is None
