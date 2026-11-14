from dataclasses import replace

from maplelens.readers.quest_tracker import TrackerLine, TrackerQuest
from maplelens.tools.quest_helper.data import Item, Mob, Npc, Quest, QuestData
from maplelens.tools.quest_helper.plan import (
    SEVERAL,
    TIMES,
    UNKNOWN,
    Target,
    also_for,
    done_parts,
    find_quest,
    match_block,
    shared_name,
    show_giver,
    starts_closest,
    targets,
)

TL, TQ = TrackerLine, TrackerQuest
NAMES = {"a": "Map A", "b": "Map B", "c": "Map C"}


def NONE(m):
    return None


def mob_row(spawns, hops=NONE, closest=False):
    d = QuestData({}, {}, {1: Mob(1, "M", spawns)}, {}, {m: m.upper() for m in "abc"})
    q = quest(mobs=((1, 1),))
    d = replace(d, quests={1: q})
    (t,) = targets(d, q, giver=False, hops=hops, closest=closest)
    return t.map_id


def test_best_map_most_spawns():
    assert mob_row({"a": 10, "b": 4}) == "a"


def test_near_tie_goes_to_fewer_hops():
    assert mob_row({"a": 10, "b": 8}, {"a": 3, "b": 1}.get) == "b"
    assert mob_row({"a": 10, "b": 7}, {"a": 3, "b": 1}.get) == "a"


def test_best_map_skips_unlisted():
    assert mob_row({"x": 50, "a": 2}) == "a"
    assert mob_row({"y": 5}) is None


def data(quest: Quest) -> QuestData:
    return QuestData(
        {quest.id: quest},
        {1: Npc(1, "Luke", (("a", 10, 20),)), 2: Npc(2, "Sera", (("b", 30, 40),))},
        {
            1: Mob(1, "Jr. Necki", {"a": 5}),
            2: Mob(2, "Slime", {"b": 3}),
            3: Mob(3, "Ghost", {}),
            4: Mob(4, "Ufo", {"x": 9}),
            5: Mob(5, "Pig", {"a": 10, "c": 1}),
        },
        {
            10: Item(10, "Jr. Necki Skin", ((1, None),), ()),
            11: Item(11, "Slime Gel", ((2, None),), ()),
            12: Item(12, "Mirror", (), (2,)),
            13: Item(13, "Mystery", (), ()),
            14: Item(14, "Start", (), ()),
            15: Item(15, "Hide", ((1, None), (2, None)), ()),
        },
        NAMES,
    )


def quest(**kw) -> Quest:
    f = {
        "id": 1,
        "name": "Q",
        "giver": None,
        "taker": None,
        "mobs": (),
        "items": (),
        "start_items": (),
    }
    return Quest(**{**f, **kw})


def test_monster_row_carries_its_items():
    q = quest(mobs=((1, 20),), items=((10, 10),))
    (t,) = targets(data(q), q, giver=False, hops=NONE)
    assert t == Target("Jr. Necki ×20 · Skin ×10", "Map A", "a", None, None, False)


def test_other_drop_and_shop_rows():
    q = quest(items=((11, 2), (12, 1)))
    drop, shop = targets(data(q), q, giver=False, hops=NONE)
    assert (drop.sub, drop.map_id, drop.at) == ("Slime · Map B", "b", None)
    assert (shop.title, shop.sub, shop.at, shop.npc) == (
        "Mirror ×1",
        "Sera · Map B",
        (30, 40),
        "Sera",
    )


def test_unknown_cases_are_info_rows():
    q = quest(mobs=((3, 1), (4, 1)), items=((13, 1),))
    ghost, ufo, item = targets(data(q), q, giver=False, hops=NONE)
    assert ghost == Target("Ghost ×1", "Where it spawns: unknown", None, None, None, True)
    assert ufo.sub == "Not in the map list yet" and ufo.info and ufo.map_id is None
    assert item == Target("Mystery ×1", "Where to get it: unknown", None, None, None, True)


def test_start_items_get_no_row():
    q = quest(items=((14, 1),), start_items=(14,))
    assert targets(data(q), q, giver=False, hops=NONE) == []


def test_row_order_and_giver():
    q = quest(giver=1, taker=2, mobs=((2, 3),), items=((12, 1),))
    rows = targets(data(q), q, giver=True, hops=NONE)
    assert [r.title for r in rows] == ["Luke", "Slime ×3", "Mirror ×1", "Sera"]
    assert rows[0].sub == "Map A · gives the quest" and rows[3].sub == "Map B · hand in"
    assert targets(data(q), q, giver=False, hops=NONE)[0].title == "Slime ×3"
    q = quest(giver=1, taker=1)
    (one,) = targets(data(q), q, giver=True, hops=NONE)
    assert (one.title, one.sub) == ("Luke", "Map A")
    (back,) = targets(data(q), q, giver=False, hops=NONE)
    assert back.sub == "Map A · hand in"


def test_show_giver():
    assert show_giver(True, False) is False
    assert show_giver(False, True) is True
    assert show_giver(None, False) is True
    assert show_giver(None, True) is False


def test_shared_name_finds_nothing():
    a, b = quest(id=1, name="Test"), quest(id=2, name="Test")
    d = QuestData({1: a, 2: b}, {}, {}, {}, {})
    assert find_quest(d, "Test") is None and shared_name(d, "Test")
    assert find_quest(d, "Nope") is None and not shared_name(d, "Nope")
    assert find_quest(QuestData({1: a}, {}, {}, {}, {}), "Test") is a


def test_also_for():
    t = Target("x", "y", "a", None, None, False)
    assert also_for("a", [("Q2", [t]), ("Q3", [])]) == ["Q2"]


FAR_A = {"a": 3, "b": 1, "c": 1}.get


def test_closest_map_fewest_hops_then_most_spawns():
    assert mob_row({"a": 10, "b": 1}, FAR_A, True) == "b"
    assert mob_row({"b": 1, "c": 4}, FAR_A, True) == "c"
    assert mob_row({"a": 10, "b": 1}, NONE, True) == "a"  # no route known
    assert mob_row({"y": 5}, NONE, True) is None


def test_closest_targets_a_monster_and_a_drop():
    q = quest(mobs=((5, 10),), items=((15, 3),))
    pig, hide = targets(data(q), q, giver=False, hops=FAR_A)
    assert (pig.map_id, hide.map_id, hide.sub) == ("a", "a", "Jr. Necki · Map A")
    pig, hide = targets(data(q), q, giver=False, hops=FAR_A, closest=True)
    assert (pig.map_id, hide.map_id, hide.sub) == ("c", "b", "Slime · Map B")


def test_starts_closest_up_to_30():
    assert starts_closest(quest(mobs=((1, 20),), items=((10, 10),)))
    assert not starts_closest(quest(mobs=((1, 20),), items=((10, 11),)))
    assert starts_closest(quest(mobs=((1, 30),), items=((14, 50),), start_items=(14,)))


def test_match_block_by_name():
    d = data(quest(id=7, name="The Filing Error"))
    assert match_block(d, TQ("The Filing Error", ())) == 7
    assert match_block(d, TQ("The Fiiing Error", ())) == 7  # one letter off snaps
    assert match_block(d, TQ("Nobody's Quest", ())) == UNKNOWN


def test_cut_name_matches_by_prefix():
    d = data(quest(id=7, name="A rainbow snail shell that makes wishes come true!?"))
    assert match_block(d, TQ("A rainbow snail shell that makes...", ())) == 7
    assert match_block(d, TQ("A rainbow snail shell that makes…", ())) == 7


def test_shared_name_told_apart_by_lines():
    a = quest(id=7, name="Donating", items=((10, 30),))
    b = quest(id=8, name="Donating", items=((11, 30),))
    d = replace(data(a), quests={7: a, 8: b})
    assert match_block(d, TQ("Donating", (TL(0, 30, "Slime Gel"),))) == 8
    assert match_block(d, TQ("Donating", ())) == SEVERAL


def test_same_targets_are_several():
    a = quest(id=7, name="Home", taker=1)
    b = quest(id=8, name="Home", taker=2)
    d = replace(data(a), quests={7: a, 8: b})
    assert match_block(d, TQ("Home", ())) == SEVERAL


def test_line_matches_despite_one_wrong_letter():
    q = quest(mobs=((1, 20),), items=((10, 10),))
    assert done_parts(data(q), q, (TL(10, 10, "Jr. Necki SkIn"),)) == {("item", 10)}


def test_done_parts_need_have_at_least_need():
    q = quest(mobs=((1, 20),), items=((10, 10),))
    lines = (TL(20, 20, "Jr. Necki"), TL(9, 10, "Jr. Necki Skin"))
    assert done_parts(data(q), q, lines) == {("mob", 1)}
    assert done_parts(data(q), q, (TL(5, 7, "Jr. Necki"),)) == frozenset()  # need differs


def test_done_monster_leaves_its_items_with_full_names():
    q = quest(mobs=((1, 20),), items=((10, 10),), taker=1)
    rows = targets(data(q), q, giver=False, hops=NONE, done=frozenset({("mob", 1)}))
    assert [r.title for r in rows] == [f"Jr. Necki Skin {TIMES}10", "Luke"]


def test_all_done_leaves_only_the_hand_in():
    q = quest(mobs=((1, 20), (2, 5)), items=((10, 10), (12, 1)), taker=1)
    done = frozenset({("mob", 1), ("mob", 2), ("item", 10), ("item", 12)})
    assert [r.title for r in targets(data(q), q, giver=False, hops=NONE, done=done)] == ["Luke"]


def test_no_progress_is_todays_rows():
    q = quest(mobs=((1, 20),), items=((10, 10),), taker=1)
    d = data(q)
    assert targets(d, q, giver=False, hops=NONE, done=frozenset()) == targets(
        d, q, giver=False, hops=NONE
    )


def rated(drops, mobs, items=None, shops=()):
    """Item 20 'Gem', dropped by `drops` ((mob, rate)...) of `mobs` {id: {map: n}}."""
    npcs = {1: Npc(1, "Luke", (("a", 10, 20),)), 2: Npc(2, "Sera", (("b", 30, 40),))}
    gem = Item(20, "Gem", tuple(drops), tuple(shops))
    mob = {i: Mob(i, f"Mob{i}", sp) for i, sp in mobs.items()}
    return QuestData({}, npcs, mob, {20: gem}, NAMES)


def test_loose_item_rate_beats_spawns():
    d = rated([(1, 1.0), (2, 40.0)], {1: {"a": 20}, 2: {"b": 5}})
    q = quest(items=((20, 1),))
    (t,) = targets(d, q, giver=False, hops=NONE)
    assert (t.map_id, t.sub) == ("b", "Mob2 · Map B")


def test_sold_and_dropped_points_to_shop():
    d = rated([(1, 50.0)], {1: {"a": 20}}, shops=(2,))
    q = quest(items=((20, 1),))
    (t,) = targets(d, q, giver=False, hops=NONE)
    assert (t.map_id, t.at, t.sub, t.npc) == ("b", (30, 40), "Sera · Map B", "Sera")


def test_mine_path_uses_rate():
    d = rated([(1, 1.0), (2, 40.0)], {1: {"a": 20}, 2: {"b": 5}})
    q = quest(mobs=((1, 5), (2, 5)), items=((20, 1),))
    one, two = targets(d, q, giver=False, hops=NONE)
    assert one.title == "Mob1 ×5" and two.title == "Mob2 ×5 · Gem ×1"


def test_mine_path_without_rates_keeps_most_spawns():
    d = rated([(1, None), (2, None)], {1: {"a": 20}, 2: {"b": 5}})
    q = quest(mobs=((1, 5), (2, 5)), items=((20, 1),))
    one, two = targets(d, q, giver=False, hops=NONE)
    assert one.title == "Mob1 ×5 · Gem ×1" and two.title == "Mob2 ×5"


def test_empty_places_keep_their_messages():
    q = quest(items=((20, 1),))
    for drops, mobs, shops, sub in [
        ([(1, 5.0)], {1: {"x": 3}}, (), "Not in the map list yet"),
        ([(1, 5.0)], {1: {}}, (), "Where it spawns: unknown"),
        ([], {}, (3,), "Not in the map list yet"),
    ]:
        d = rated(drops, mobs, shops=shops)
        assert targets(d, q, giver=False, hops=NONE)[0].sub == sub
