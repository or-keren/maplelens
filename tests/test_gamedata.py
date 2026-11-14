import json
from pathlib import Path

from maplelens.gamedata import SEARCH_LIMIT, GameData, Item, Mob, Npc, load_game, search
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
    assert _lines("maple road")["Maple Road"] == "Map · Maple Road"
    assert _lines("maple island")["Maple Road"] == "Map · Maple Road"
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
