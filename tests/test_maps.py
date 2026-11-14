from maplelens.tools.path_arrow.maps import (
    PICTURES,
    MapInfo,
    Minimap,
    Portal,
    find,
    load,
    picture,
)

MINIMAP = Minimap(100, 100, 50, 50)


def M(id, street, name, portals=(), cab=None, minimap=MINIMAP):
    return MapInfo(id, street, name, False, minimap, tuple(portals), cab)


def test_shipped_data_loads():
    maps = load()
    assert len(maps) >= 450
    for m in maps.values():
        for p in m.portals:
            assert p.to in maps
        if m.cab:
            assert all(t in maps for t in m.cab.to)
    assert len(maps["010003000"].npcs) == 17  # Kerning City
    cab_titles = {m.title for m in maps.values() if m.cab}
    assert {
        "Victoria Road / Henesys",
        "Victoria Road / Ellinia",
        "Victoria Road / Kerning City",
        "Victoria Road / Perion",
        "Dungeon / Sleepywood",
    } <= cab_titles


def test_find_unique():
    assert find(load(), "Dungeon / Sleepywood", None).name == "Sleepywood"


def test_find_duplicate_uses_previous():
    a = M("A", "Maple Road", "Mushroom Town")
    b = M("B", "Maple Road", "Mushroom Town")
    p = M("P", "X", "P", portals=[Portal(0, 0, "B")])
    maps = {m.id: m for m in (a, b, p)}
    title = "Maple Road / Mushroom Town"
    assert find(maps, title, "P") is b
    assert find(maps, title, None) is None
    assert find(maps, title, "X") is None


def test_find_unknown_is_none():
    assert find(load(), "Nowhere / Nothing", None) is None


def test_shipped_pictures_match_minimap_size():
    maps = load()
    files = list(PICTURES.glob("*.png"))
    assert len(files) >= 250
    for f in files:
        mm = maps[f.stem].minimap
        h, w = picture(f.stem).shape[:2]
        assert abs(w - mm.w / 16) <= 1.5 and abs(h - mm.h / 16) <= 1.5, f.stem


def test_picture_missing_is_none():
    assert picture("999999999") is None


def test_forest_north_of_ellinia_hidden_portals():
    m = load()["010002070"]
    assert sum(p.hidden for p in m.portals) == 19
    assert {p.to for p in m.portals if not p.hidden} == {"010002060", "010004090"}
    assert picture("010002070").shape[:2] == (428, 130)
