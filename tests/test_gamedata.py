import json
from pathlib import Path

from maplelens.gamedata import (
    SEARCH_LIMIT,
    GameData,
    Item,
    Mob,
    Npc,
    item_places,
    load_game,
    mob_places,
    npc_places,
    search,
)
from maplelens.tools.class_helper.data import MAPS

FIX = Path(__file__).parent / "fixtures" / "gamedata"


def test_loads_fixture():
    g = load_game(FIX / "monsters.json", FIX / "game.json")
    assert g.npcs[9] == Npc(9, "Rina", (("1", None, None),))
    assert g.npcs[10].places == ()
    assert g.items[100] == Item(100, "Shell", ((7, None),), (9,))
    assert g.mobs[7] == Mob(7, "Snail", {"1": 2, "2": 4}, 3)


def test_shipped_references_resolve():
    g = load_game()
    maps = {m["id"] for m in json.loads(MAPS.read_text("utf-8"))}
    for it in g.items.values():
        assert all(mob in g.mobs for mob, _ in it.drops)
        assert all(n in g.npcs for n in it.shops)
    for n in g.npcs.values():
        assert all(m in maps for m, _, _ in n.places)


def test_shipped_examples():
    g = load_game()
    assert (5, 40.0) in g.items[4000004].drops
    assert 109 in g.items[2010004].shops
    assert g.mobs[57].spawns
    assert g.mobs[5].level == 4


def _world():
    maps = {str(i): (f"Field {i}", "Victoria") for i in range(60)}
    maps["100"] = ("Maple Road", "Maple Island")
    maps["101"] = ("Henesys Department Store", "Henesys")
    maps["102"] = ("Snail Garden", "Victoria")
    mobs = {
        1: Mob(1, "Snail", {str(i): 1 for i in range(48)} | {"999": 3}, 4),
        2: Mob(2, "Red Snail", {"1": 1}, 9),
        3: Mob(3, "Jr. Necki", {"1": 1, "2": 1}, 20),
        4: Mob(4, "Jr. Necki", {"2": 1, "3": 1, "4": 0}, 17),
        5: Mob(5, "Pig", {"1": 1}, 5),
        6: Mob(6, "Ribbon Pig", {"1": 1}, 5),
    }
    npcs = {
        9: Npc(9, "Mina", (("101", 1, 2),)),
        10: Npc(10, "Snail Keeper", (("101", None, None), ("102", None, None), ("998", 0, 0))),
        11: Npc(11, "Nobody", ()),
        12: Npc(12, "Roger", (("100", None, None), ("101", None, None))),
    }
    items = {
        50: Item(50, "Snail Shell", ((2, 1.0),), ()),
        51: Item(51, "Shell Snail", ((1, None), (2, None), (5, None)), ()),
        52: Item(52, "Necki Thing", ((3, 2.0), (4, 1.0)), (9, 10, 11, 12, 9, 10, 11, 12)),
        53: Item(53, "Pig Thing", ((5, None),), (9,)),
        54: Item(54, "Lost Thing", (), ()),
        55: Item(55, "Mixed Thing", ((5, None),), (9, 10)),
    }
    return GameData(npcs, mobs, items), maps


def _lines(text, **kw):
    g, maps = _world()
    return {m.name: m.line for m in search(g, maps, text, **kw)}


def test_search_order():
    g, maps = _world()
    got = [(m.kind, m.name) for m in search(g, maps, "snail")]
    assert got == [
        ("monster", "Snail"),
        ("npc", "Snail Keeper"),
        ("item", "Snail Shell"),
        ("map", "Snail Garden"),
        ("monster", "Red Snail"),
        ("item", "Shell Snail"),
    ]


def test_search_lines():
    one = _lines("")  # blank
    assert one == {}
    ln = _lines("snail")
    assert ln["Snail"] == "Monster · Lv 4 · 48 maps"
    assert ln["Snail Shell"] == "Item · dropped by Red Snail"
    assert ln["Shell Snail"] == "Item · dropped by 3 monsters"
    assert ln["Snail Keeper"] == "NPC · 2 maps"
    assert _lines("necki thing")["Necki Thing"] == "Item · 8 shops · dropped by Jr. Necki"
    assert _lines("lost")["Lost Thing"] == "Item · no known place"
    assert _lines("pig thing")["Pig Thing"] == "Item · sold by Mina · dropped by Pig"
    assert _lines("mixed")["Mixed Thing"] == "Item · 2 shops · dropped by Pig"
    assert _lines("mina")["Mina"] == "NPC · Henesys Department Store"
    assert _lines("nobody")["Nobody"] == "NPC · no known place"
    assert _lines("maple road")["Maple Road"] == "Map · Maple Island"  # the street
    assert _lines("maple island")["Maple Road"] == "Map · Maple Island"
    assert _lines("roger")["Roger"] == "NPC · 2 maps"


def test_same_name_monsters_merge():
    g, maps = _world()
    (m,) = search(g, maps, "jr. necki")
    assert m.kind == "monster" and m.ids == (3, 4)
    assert m.line == "Monster · Lv 17 · 3 maps"


def test_search_ids_and_street_tier():
    g, maps = _world()
    m = search(g, maps, "maple road")[0]
    assert m.ids == ("100",) and m.kind == "map"
    # a street-only match ranks after a name match
    got = [x.name for x in search(g, maps, "henesys")]
    assert got == ["Henesys Department Store"]


def test_search_caps_and_blank():
    g, maps = _world()
    assert search(g, maps, "") == [] and search(g, maps, "  ") == []
    assert len(search(g, maps, "a")) <= SEARCH_LIMIT
    big = GameData({}, {i: Mob(i, f"a{i}", {}) for i in range(50)}, {})
    assert len(search(big, {}, "a")) == SEARCH_LIMIT


def _gd(mobs, drops, shops=(), npcs=()):
    return GameData(
        {n.id: n for n in npcs},
        {m.id: m for m in mobs},
        {1: Item(1, "Thing", tuple(drops), tuple(shops))},
    )


def _ids(places):
    return [p.map_id for p in places]


def _hops(table):
    return table.get


def test_item_score_sums_droppers():
    d = _gd([Mob(1, "A", {"m": 10}), Mob(2, "B", {"m": 5})], [(1, 40.0), (2, 10.0)])
    (s,) = item_places(d, 1, {"m"}, _hops({"m": 2}), False)
    assert (s.score, s.via, s.others, s.count, s.rate, s.shop, s.hops) == (
        4.5,
        1,
        1,
        10,
        40.0,
        False,
        2,
    )


def test_rate_beats_spawns():
    d = _gd([Mob(1, "A", {"A": 20}), Mob(2, "B", {"B": 5})], [(1, 1.0), (2, 40.0)])
    assert _ids(item_places(d, 1, {"A", "B"}, _hops({"A": 1, "B": 5}), False)) == ["B", "A"]


def _near(a_score, b_score):
    d = _gd(
        [Mob(1, "A", {"A": 1}), Mob(2, "B", {"B": 1})],
        [(1, a_score * 100.0), (2, b_score * 100.0)],
    )
    return _ids(item_places(d, 1, {"A", "B"}, _hops({"A": 3, "B": 1}), False))


def test_near_tie_nearer_wins():
    assert _near(10, 8.5) == ["B", "A"]
    assert _near(10, 7) == ["A", "B"]


def test_shops_first_both_modes():
    d = _gd(
        [Mob(1, "A", {"drop": 5})],
        [(1, 50.0)],
        shops=[9],
        npcs=[Npc(9, "Rina", (("shop", 3, None),))],
    )
    h = _hops({"drop": 1, "shop": 6})
    for closest in (False, True):
        out = item_places(d, 1, {"drop", "shop"}, h, closest)
        assert _ids(out) == ["shop", "drop"]
        assert (out[0].shop, out[0].at, out[0].via, out[0].count) == (True, None, 9, 0)


def test_shop_per_listed_map_sorted_with_spot():
    npcs = [Npc(9, "R", (("b", 1, 2), ("a", None, 2), ("x", 1, 1)))]
    d = _gd([], [], shops=[9], npcs=npcs)
    out = item_places(d, 1, {"a", "b"}, _hops({"a": 4, "b": 4}), False)
    assert [(p.map_id, p.at) for p in out] == [("a", None), ("b", (1, 2))]


def test_unrated_after_rated():
    d = _gd([Mob(1, "A", {"A": 50}), Mob(2, "B", {"B": 1})], [(1, None), (2, 1.0)])
    for closest in (False, True):
        assert _ids(item_places(d, 1, {"A", "B"}, _hops({"A": 1, "B": 9}), closest)) == ["B", "A"]


def test_all_unrated_falls_back_to_spawns():
    d = _gd([Mob(1, "A", {"A": 3}), Mob(2, "B", {"B": 9})], [(1, None), (2, None)])
    out = item_places(d, 1, {"A", "B"}, _hops({"A": 1, "B": 1}), False)
    assert _ids(out) == ["B", "A"]
    assert (out[0].score, out[0].rate, out[0].via) == (9, None, 2)


def test_mixed_map_scores_only_rated():
    d = _gd(
        [Mob(1, "A", {"m": 50}), Mob(2, "B", {"m": 2}), Mob(3, "C", {"m": 4})],
        [(1, None), (2, 10.0), (3, 10.0)],
    )
    (s,) = item_places(d, 1, {"m"}, _hops({"m": 1}), False)
    assert (s.via, s.score, s.others) == (3, 0.6000000000000001, 2)


def test_unreachable_last():
    d = _gd(
        [Mob(1, "A", {"A": 5}), Mob(2, "B", {"B": 1}), Mob(3, "C", {"C": 1})],
        [(1, 90.0), (2, None), (3, 1.0)],
    )
    h = _hops({"B": 1, "C": 2})
    for closest in (False, True):
        assert _ids(item_places(d, 1, {"A", "B", "C"}, h, closest)) == ["C", "B", "A"]


def test_unknown_position_closest_is_best():
    d = _gd([Mob(1, "A", {"A": 1}), Mob(2, "B", {"B": 2})], [(1, 100.0), (2, 100.0)])
    h = _hops({})
    best = item_places(d, 1, {"A", "B"}, h, False)
    assert _ids(best) == ["B", "A"]
    assert item_places(d, 1, {"A", "B"}, h, True) == best


def test_unlisted_maps_dropped():
    d = _gd(
        [Mob(1, "A", {"A": 1, "Z": 9})], [(1, 5.0)], shops=[9], npcs=[Npc(9, "R", (("Z", 1, 1),))]
    )
    assert _ids(item_places(d, 1, {"A"}, _hops({}), False)) == ["A"]
    assert _ids(mob_places(d, [1], {"A"}, _hops({}), False)) == ["A"]
    assert npc_places(d, 9, {"A"}, _hops({})) == []


def test_unknown_dropper_ignored():
    d = _gd([Mob(1, "A", {"A": 1})], [(1, 5.0), (77, 50.0)])
    (s,) = item_places(d, 1, {"A"}, _hops({}), False)
    assert (s.via, s.others) == (1, 0)


def test_mob_places_merged_ids():
    d = _gd([Mob(1, "A", {"m": 3, "n": 1}), Mob(2, "A", {"m": 4})], [])
    out = mob_places(d, [1, 2], {"m", "n"}, _hops({"m": 2, "n": 1}), False)
    assert _ids(out) == ["m", "n"]
    m = out[0]
    assert (m.count, m.score, m.via, m.others, m.rate, m.shop) == (7, 7, 2, 0, None, False)


def test_npc_places():
    npcs = [Npc(9, "R", (("b", 1, 2), ("a", 5, None), ("c", 0, 0), ("x", 1, 1)))]
    d = _gd([], [], npcs=npcs)
    out = npc_places(d, 9, {"a", "b", "c"}, _hops({"a": 2, "b": 2}))
    assert [(p.map_id, p.at, p.via, p.hops) for p in out] == [
        ("a", None, 9, 2),
        ("b", (1, 2), 9, 2),
        ("c", (0, 0), 9, None),
    ]


def test_closest_orders_by_hops_best_by_score():
    h = _hops({"A": 3, "B": 1})
    d = _gd([Mob(1, "A", {"A": 1}), Mob(2, "B", {"B": 1})], [(1, 1000.0), (2, 200.0)])
    assert _ids(item_places(d, 1, {"A", "B"}, h, False)) == ["A", "B"]
    assert _ids(item_places(d, 1, {"A", "B"}, h, True)) == ["B", "A"]
    d = _gd([Mob(1, "M", {"A": 10, "B": 2})], [])
    assert _ids(mob_places(d, [1], {"A", "B"}, h, False)) == ["A", "B"]
    assert _ids(mob_places(d, [1], {"A", "B"}, h, True)) == ["B", "A"]
