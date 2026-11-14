from maplelens.gamedata import MapSpawns, Monster, SpotData
from maplelens.tools.class_helper.data import Place
from maplelens.tools.class_helper.plan import DOT_COLOURS, respawn_text, spot_card

PLACE = Place("000000001", "Victoria Road / Snail Field", "Victoria Road / Snail Field")
MONSTERS = {
    "1": Monster("Snail", 1, 45, 2),
    "2": Monster("Blue Snail", 2, 1200, 3),
    "3": Monster("Blue Snail", 2, 1200, 3),
}


def make(tmp_path, spawns, cap=None, respawn=None, picture=True, monsters=MONSTERS):
    if picture:
        (tmp_path / "000000001.webp").touch()
    maps = {"000000001": MapSpawns((100, 50), cap, tuple(spawns), respawn or {})}
    return SpotData(maps, monsters, tmp_path, tmp_path)


def test_card_lists_monsters_most_spots_first_with_matching_dots(tmp_path):
    spots = make(tmp_path, [("1", 10, 10), ("1", 30, 10), ("3", 20, 15)], cap=5)
    c = spot_card(PLACE, spots)
    assert (
        c.title == "Snail Field"
        and c.street == "Victoria Road"
        and c.cap == "Up to 5 monsters at once"
    )
    assert [m.name for m in c.mobs] == ["Snail", "Blue Snail"]
    assert c.mobs[0].stats == "Lv 1 · 45 HP · 2 EXP" and c.mobs[0].spots == "2 spawn spots"
    assert c.mobs[1].spots == "1 spawn spot"
    assert c.dots == ((10, 10, "#ffcc33"), (30, 10, "#ffcc33"), (20, 15, "#7fa8ff"))
    assert c.picture == tmp_path / "000000001.webp"


def test_a_timer_shows_on_its_monster_line(tmp_path):
    spots = make(tmp_path, [("1", 10, 10), ("1", 30, 10), ("3", 20, 15)], respawn={"3": (60, 60)})
    c = spot_card(PLACE, spots)
    assert c.mobs[1].spots == "1 spawn spot · respawns every 60 s"


def test_respawn_text():
    assert respawn_text(60, 60) == "every 60 s"
    assert respawn_text(10, 20) == "every 10–20 s"
    assert respawn_text(300, 300) == "every 5 min"
    assert respawn_text(180, 1800) == "every 3–30 min"
    assert respawn_text(150, 150) == "every 2.5 min"


def test_no_spawn_data_keeps_the_picture(tmp_path):
    c = spot_card(PLACE, make(tmp_path, []))
    assert c.mobs == () and c.cap is None and c.picture


def test_no_picture_keeps_the_monsters(tmp_path):
    c = spot_card(PLACE, make(tmp_path, [("1", 10, 10)], picture=False))
    assert c.picture is None and c.mobs


def test_no_picture_and_no_spawns_is_no_card(tmp_path):
    assert spot_card(PLACE, make(tmp_path, [], picture=False)) is None


def test_a_map_we_have_no_data_for_is_no_card(tmp_path):
    assert spot_card(Place("999999999", "X", None), make(tmp_path, [("1", 1, 1)])) is None
    assert spot_card(Place(None, "X", None), make(tmp_path, [("1", 1, 1)])) is None


def test_dot_colours_repeat_past_the_list(tmp_path):
    monsters = {str(i): Monster(f"M{i}", 1, 1, 1) for i in range(5)}
    spots = make(tmp_path, [(str(i), i, i) for i in range(5)], monsters=monsters)
    c = spot_card(PLACE, spots)
    assert [m.colour for m in c.mobs] == [*DOT_COLOURS, DOT_COLOURS[0]]


def test_an_unknown_monster_is_skipped(tmp_path):
    c = spot_card(PLACE, make(tmp_path, [("9", 1, 1), ("1", 2, 2)]))
    assert [m.name for m in c.mobs] == ["Snail"]
    assert c.dots == ((2, 2, "#ffcc33"),)
