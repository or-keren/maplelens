import json
from pathlib import Path

from maplelens.gamedata import load_game
from maplelens.readers.quest_tracker import target_names
from maplelens.tools.quest_helper.data import DATA, ICONS, MAPS, load

SMALL = Path(__file__).parent / "fixtures" / "quests_small.json"
SMALL_GAME = Path(__file__).parent / "fixtures" / "quests_small_game"
NO_ICON: list[int] = []  # reward items OSMS has no icon for (meowdb-only)
MAP_JSON = json.loads(MAPS.read_text("utf-8"))


def test_loads_small_fixture():
    d = load(SMALL, MAPS, load_game(SMALL_GAME / "monsters.json", SMALL_GAME / "game.json"))
    q = d.quests[1001]
    assert (q.giver, q.taker) == (2, 1)
    assert q.mobs == ((2, 3),) and q.items == ((4000001, 10), (4031000, 1))
    assert q.start_items == (4031000,)
    assert d.npcs[1].places == (("000000001", -46, 280),)
    assert d.mobs[2].spawns == {"000000040": 6}
    assert d.items[4000001].drops == ((2, None),) and d.items[4031000].shops == (1,)
    assert d.map_names["000000001"] == "Mushroom Town - West Entrance"


def test_every_reference_resolves():
    d = load()
    for q in d.quests.values():
        assert {q.giver, q.taker} - {None} <= d.npcs.keys()
        assert {m for m, _ in q.mobs} <= d.mobs.keys()
        assert {i for i, _ in q.items} | set(q.start_items) <= d.items.keys()
    for i in d.items.values():
        assert {m for m, _ in i.drops} <= d.mobs.keys() and set(i.shops) <= d.npcs.keys()


def test_npc_places_are_map_markers():
    marks = {m["id"]: {(n["x"], n["y"]) for n in m["npcs"]} for m in MAP_JSON}
    for n in load().npcs.values():
        for map_id, x, y in n.places:
            assert (x, y) in marks[map_id], (n.name, map_id)


def test_kept_quests():
    d = load()
    names = {q.name for q in d.quests.values()}
    assert len(d.quests) > 300  # Classic's quests, citizenship and crafting included, not events
    assert not [n for n in names if n.startswith("[Event]")]  # event quests stay out
    assert 80000 not in d.quests  # "Mar" the Fairy: no source names its NPC
    q = d.quests[506001]  # citizenship (owner, 2026-11-09): Community Board -> Rina
    assert (d.npcs[q.giver].name, d.npcs[q.taker].name) == ("Community Board", "Rina")
    q = d.quests[80008]  # crafting: Silas Irons
    assert (d.npcs[q.giver].name, d.npcs[q.taker].name) == ("Silas Irons", "Silas Irons")
    q = d.quests[1001]
    assert q.start_items == (4031000,)
    assert (q.giver, q.taker) == (2, 1)
    assert d.npcs[1].name == "Heena"


def test_every_quest_has_somewhere_to_go():
    for q in load().quests.values():
        assert q.giver or q.taker or q.mobs or q.items, q.id


def test_default_path_is_the_shipped_file():
    assert DATA.name == "quests.json"


def test_rewards_from_osms():
    q = load().quests[10201]  # Collecting 50 Cursed Dolls: the issue's screenshot
    assert (q.rewards.exp, q.rewards.mesos) == (7020, 1140)
    assert [(r.item, r.count, r.kind) for r in q.rewards.items][:2] == [
        (4010000, 7, "random"),
        (4010001, 7, "random"),
    ]
    assert q.chain == "Rowen the Fairy and the Cursed Doll"
    assert q.after == (10508,)  # every prerequisite, whatever its chain


def test_pick_class_and_contribution():
    d = load()
    assert {r.kind for r in d.quests[10401].rewards.items} == {"pick"}  # Blackbull: choose one
    assert {r.cls for r in d.quests[10205].rewards.items} == {
        "Beginner",
        "Warrior",
        "Magician",
        "Bowman",
        "Thief",
    }
    assert d.quests[506001].rewards.contribution == ("Henesys", 100, 325)
    assert d.quests[506019].rewards.contribution == ("Henesys", 700, 700)


def test_rewards_from_meowdb():
    d = load()
    q = d.quests[10600]  # Zelya's Map: not in OSMS
    assert (q.rewards.exp, q.rewards.mesos) == (5062, 1140)
    assert [(r.item, r.count, r.kind) for r in q.rewards.items] == [(2000003, 20, "always")]
    # Round one of the Abyss story (10613-10616) is its own quests, not round two's
    # (10617-10620, same names, from OSMS): Matters of the Heart pays 5,255, not 10,400.
    assert (d.quests[10613].rewards.exp, d.quests[10617].rewards.exp) == (5255, 10400)


def test_chain_links():
    d = load()
    assert d.quests[10202].after == (10201,)
    # the Abyss story runs 10611 -> 10612 -> ... -> 10620, switching chains as it goes
    assert [d.quests[i].after for i in range(10612, 10621)] == [
        (i - 1,) for i in range(10612, 10621)
    ]
    for q in d.quests.values():
        assert set(q.after) <= d.quests.keys(), q.id


def test_every_reward_item_has_a_name_and_most_an_icon():
    d = load()
    ids = {r.item for q in d.quests.values() for r in q.rewards.items}
    assert ids <= d.items.keys()
    missing = sorted(i for i in ids if not (ICONS / f"{i}.png").exists())
    assert missing == NO_ICON  # the converter's list of meowdb-only items, pinned


def test_target_names_are_quest_monsters_and_every_quest_item():
    d = load()
    qs = d.quests.values()
    mobs = {d.mobs[m].name for q in qs for m, _ in q.mobs}
    items = {d.items[i].name for q in qs for i, _ in q.items}  # start items too
    names = target_names()
    assert names == mobs | items
    assert items < {i.name for i in load_game().items.values()}  # a subset, not every item
    start = d.items[d.quests[1001].start_items[0]].name
    assert start in names  # a delivery item the tracker can show
    used = {i for q in qs for i, _ in q.items}
    reward_only = {r.item for q in qs for r in q.rewards.items} - used
    assert reward_only and any(d.items[i].name not in names for i in reward_only)
