"""Quest rows: the places to go for one quest. Pure logic, no Qt."""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from functools import lru_cache

from maplelens.readers.map_name import snap_title
from maplelens.readers.quest_tracker import TrackerLine, TrackerQuest

from .data import Item, Mob, Npc, Quest, QuestData

NEAR_TIE = 0.8  # a map with this share of the top spawn count counts as tied
QUICK = 30  # a quest asking for this many kills and items or fewer starts on Closest

NO_ITEM = "Where to get it: unknown"
NO_SPAWN = "Where it spawns: unknown"
NOT_LISTED = "Not in the map list yet"

TIMES = chr(0xD7)  # the multiplication sign

UNKNOWN = "unknown"  # the name is no single quest in the data
SEVERAL = "several"  # several quests fit the name and their targets can't settle it

Part = tuple[str, int]  # ("mob", monster id) or ("item", item id)

Hops = Callable[[str], int | None]  # map changes from the player; None: unknown or no route


@dataclass(frozen=True)
class Target:
    title: str
    sub: str
    map_id: str | None  # None: not clickable
    at: tuple[int, int] | None
    npc: str | None  # the NPC's name, for the arrival line
    info: bool  # sub is a grey info line


def _hops(hops: Hops, map_id: str) -> float:
    h = hops(map_id)
    return float("inf") if h is None else h


def best_map(spawns: dict[str, int], listed: Collection[str], hops: Hops) -> str | None:
    here = {m: c for m, c in spawns.items() if m in listed}
    if not here:
        return None
    top = max(here.values())
    near = [m for m, c in here.items() if c >= NEAR_TIE * top]
    return min(near, key=lambda m: (_hops(hops, m), -here[m], m))


def closest_map(spawns: dict[str, int], listed: Collection[str], hops: Hops) -> str | None:
    here = {m: c for m, c in spawns.items() if m in listed}
    return min(here, key=lambda m: (_hops(hops, m), -here[m], m), default=None)


def asked(quest: Quest) -> int:
    """The kills and items the quest asks for, added up; 0: nothing to hunt."""
    return sum(n for _, n in quest.mobs) + sum(
        n for i, n in quest.items if i not in quest.start_items
    )


def starts_closest(quest: Quest) -> bool:
    return asked(quest) <= QUICK


def npc_place(npc: Npc, listed: Collection[str], hops: Hops) -> tuple[str, int, int] | None:
    here = [p for p in npc.places if p[0] in listed]
    return min(here, key=lambda p: (_hops(hops, p[0]), p), default=None)


def find_quest(data: QuestData, name: str) -> Quest | None:
    found = [q for q in data.quests.values() if q.name == name]
    return found[0] if len(found) == 1 else None


def shared_name(data: QuestData, name: str) -> bool:
    return sum(q.name == name for q in data.quests.values()) > 1


def show_giver(taken: bool | None, tracked: bool) -> bool:
    return not taken if taken is not None else not tracked


def also_for(map_id: str, others: list[tuple[str, list[Target]]]) -> list[str]:
    return [name for name, ts in others if any(t.map_id == map_id for t in ts)]


def _mob_map(data: QuestData, mob: Mob, hops: Hops, closest: bool) -> str | None:
    return (closest_map if closest else best_map)(mob.spawns, data.map_names.keys(), hops)


def _info(title: str, why: str) -> Target:
    return Target(title, why, None, None, None, True)


def _npc_row(data: QuestData, npc_id: int, suffix: str, hops: Hops) -> Target:
    npc = data.npcs[npc_id]
    p = npc_place(npc, data.map_names.keys(), hops)
    if p is None:
        return Target(npc.name, NOT_LISTED, None, None, npc.name, True)
    sub = f"{data.map_names[p[0]]} · {suffix}" if suffix else data.map_names[p[0]]
    return Target(npc.name, sub, p[0], (p[1], p[2]), npc.name, False)


def _top_dropper(data: QuestData, ids: list[int], hops: Hops, closest: bool) -> Mob:
    # most spawns on its map (Closest: fewest hops first); one with no listed map comes last
    def key(m: Mob) -> tuple[int, float, int]:
        b = _mob_map(data, m, hops, closest)
        return (0, _hops(hops, b) if closest else 0, -m.spawns[b]) if b else (1, 0, 0)

    return min((data.mobs[i] for i in ids), key=key)


def _loose_item(data: QuestData, item: Item, n: int, hops: Hops, closest: bool) -> Target:
    """The row for a quest item that doesn't ride on one of the quest's monsters."""
    title = f"{item.name} {TIMES}{n}"
    if item.drops:
        m = _top_dropper(data, list(item.drops), hops, closest)
        b = _mob_map(data, m, hops, closest)
        if b is None:
            return _info(title, NOT_LISTED if m.spawns else NO_SPAWN)
        return Target(title, f"{m.name} · {data.map_names[b]}", b, None, None, False)
    if item.shops:
        listed = data.map_names.keys()
        shops = [(npc_place(data.npcs[i], listed, hops), data.npcs[i].name) for i in item.shops]
        shops = [(p, npc) for p, npc in shops if p]
        if not shops:
            return _info(title, NOT_LISTED)
        p, npc = min(shops, key=lambda s: (_hops(hops, s[0][0]), s[0]))
        return Target(title, f"{npc} · {data.map_names[p[0]]}", p[0], (p[1], p[2]), npc, False)
    return _info(title, NO_ITEM)


def _part(data: QuestData, quest: Quest, line: TrackerLine) -> Part | None:
    """The target of `quest` that `line` names (by name and need), if any."""
    named: dict[str, Part] = {}
    for i, n in quest.mobs:
        if n == line.need:
            named[data.mobs[i].name] = ("mob", i)
    for i, n in quest.items:
        if n == line.need and i not in quest.start_items:
            named[data.items[i].name] = ("item", i)
    return named.get(snap_title(line.text, named.keys()))


@lru_cache(maxsize=256)
def _snap_quest(name: str, names: frozenset[str]) -> str:
    """snap_title, cached: an unknown (event) name scans every title, every tick."""
    return snap_title(name, names)


def block_candidates(data: QuestData, block: TrackerQuest) -> list[Quest]:
    """The quests a block's name can be: by prefix when cut, else by the snapped name."""
    name = block.name
    if name.endswith((".", "…")):
        head = name.rstrip(".…")
        return [q for q in data.quests.values() if q.name.startswith(head)]
    name = _snap_quest(name, frozenset(q.name for q in data.quests.values()))
    return [q for q in data.quests.values() if q.name == name]


def match_block(data: QuestData, block: TrackerQuest) -> int | str:
    found = block_candidates(data, block)
    if not found:
        return UNKNOWN
    if len(found) > 1:
        found = [q for q in found if all(_part(data, q, ln) for ln in block.lines)]
    return found[0].id if len(found) == 1 else SEVERAL


def done_parts(data: QuestData, quest: Quest, lines: tuple[TrackerLine, ...]) -> frozenset[Part]:
    parts = ((_part(data, quest, ln), ln) for ln in lines)
    return frozenset(p for p, ln in parts if p and ln.have >= ln.need)


def targets(  # noqa: PLR0913 - the quest, its map ranking and its progress
    data: QuestData,
    quest: Quest,
    *,
    giver: bool,
    hops: Hops,
    done: frozenset[Part] = frozenset(),
    closest: bool = False,
) -> list[Target]:
    on_mob: dict[int, list[str]] = {i: [] for i, _ in quest.mobs}
    loose: list[Target] = []
    for item_id, n in quest.items:
        if item_id in quest.start_items or ("item", item_id) in done:
            continue
        item = data.items[item_id]
        mine = [i for i in item.drops if i in on_mob]
        if mine:
            m = _top_dropper(data, mine, hops, closest)
            name = item.name if ("mob", m.id) in done else item.name.removeprefix(m.name + " ")
            on_mob[m.id].append(f"{name} {TIMES}{n}")
        else:
            loose.append(_loose_item(data, item, n, hops, closest))

    rows: list[Target] = []
    same = quest.giver is not None and quest.giver == quest.taker
    if giver and quest.giver is not None:
        rows.append(_npc_row(data, quest.giver, "" if same else "gives the quest", hops))
    for mob_id, count in quest.mobs:
        mob = data.mobs[mob_id]
        gone = ("mob", mob_id) in done
        if gone and not on_mob[mob_id]:
            continue
        title = " · ".join(([] if gone else [f"{mob.name} {TIMES}{count}"]) + on_mob[mob_id])
        b = _mob_map(data, mob, hops, closest)
        if b:
            rows.append(Target(title, data.map_names[b], b, None, None, False))
        else:
            rows.append(_info(title, NOT_LISTED if mob.spawns else NO_SPAWN))
    rows += loose
    if quest.taker is not None and not (giver and same):
        rows.append(_npc_row(data, quest.taker, "hand in", hops))
    return rows
