from pathlib import Path

from maplelens.spawns import MapSpawns, Monster, SpotData, load_spots
from maplelens.tools.path_arrow.maps import MapInfo, load
from maplelens.tools.path_arrow.monsters import Haunt, MonsterHit, find_monsters, haunts


def M(id, name, street="Road"):
    return MapInfo(id, street, name, False, None, (), None)


MAPS = {
    m.id: m
    for m in [
        M("1", "Apple"),
        M("2", "Berry"),
        M("3", "Cherry"),
        M("4", "Date"),
        M("5", "Snail Park"),
        M("6", "Pie Hill", street="Snail Street"),
    ]
}
MONSTERS = {
    "s": Monster("Snail", 1, 15, 1),
    "b": Monster("Blue Snail", 2, 30, 2),
    "m": Monster("Mushroom", 5, 80, 4),
    "g": Monster("Ghost", 9, 200, 9),  # spawns only on a map we have no route data for
    "800001": Monster("Snail", 30, 700, 50),  # a special copy (a quest map's)
}


def spots(**by_map: str) -> SpotData:
    """Each map's spawns as monster ids, one per spot (a string: one letter per spot)."""
    maps = {
        i: MapSpawns((10, 10), None, tuple((m, 0, 0) for m in s), {}) for i, s in by_map.items()
    }
    return SpotData(maps, MONSTERS, Path("."), Path("."))


SPOTS = spots(**{"1": "sssb", "2": "sss", "3": "sm", "4": "sb", "5": ["800001"], "9": "sssssg"})


def test_haunts_counts_and_sorts():
    # most spots first; equal counts: higher share first; then A-Z by map name
    assert haunts(SPOTS, MAPS, "s") == [
        Haunt("2", 3, 3, 1),
        Haunt("1", 3, 4, 2),
        Haunt("3", 1, 2, 2),
        Haunt("4", 1, 2, 2),
    ]
    assert [h.share for h in haunts(SPOTS, MAPS, "s")] == [100, 75, 50, 50]


def test_haunts_skips_maps_without_route_data():
    assert all(h.map_id != "9" for h in haunts(SPOTS, MAPS, "s"))
    assert haunts(SPOTS, MAPS, "g") == []
    assert haunts(SPOTS, MAPS, "nobody") == []


def test_find_monsters_ranks_names_starting_with_the_text_first():
    assert find_monsters(MAPS, SPOTS, "snail") == [
        MonsterHit("s", MONSTERS["s"]),
        MonsterHit("b", MONSTERS["b"]),
    ]
    assert find_monsters(MAPS, SPOTS, "") == find_monsters(MAPS, SPOTS, "  ") == []


def test_find_monsters_hides_special_copies():
    # the Lv 30 Snail spawns on a routable map, but it's a quest copy (id 800000 and up)
    assert all(h.id != "800001" for h in find_monsters(MAPS, SPOTS, "snail"))


def test_find_monsters_skips_monsters_without_haunts():
    assert find_monsters(MAPS, SPOTS, "ghost") == []
    assert find_monsters(MAPS, SPOTS, "mush") == [MonsterHit("m", MONSTERS["m"])]


def test_find_monsters_limit():
    assert len(find_monsters(MAPS, SPOTS, "snail", limit=1)) == 1


def test_real_data_lists_one_fire_boar_and_the_field_bosses():
    spots, maps = load_spots(), load()
    assert [h.id for h in find_monsters(maps, spots, "fire boar")] == ["30"]  # not 800016
    assert [h.monster.name for h in find_monsters(maps, spots, "mano")] == ["Mano"]


def test_fire_boar_matches_meowdb():
    # meowdb.com/msclassic/monsters/30 lists 14 maps, The Burnt Land V first: 26/48, 3 types
    found = haunts(load_spots(), load(), "30")
    assert len(found) == 14
    assert found[0] == Haunt("010004115", 26, 48, 3)
    assert found[0].share == 54
    assert found[-1].count == 4
