import json
from pathlib import Path

from maplelens.gamedata import Item, Mob, Npc, load_game
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
