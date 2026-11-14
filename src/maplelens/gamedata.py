"""The game's data: NPCs, monsters and items (game.json, monsters.json), and the spawn spots."""

import json
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
SPOTS = DATA / "monsters.json"
GAME = DATA / "game.json"
PICTURES = DATA / "map_pictures"
ICONS = DATA / "monster_icons"
NPC_ICONS = DATA / "npc_icons"
ITEM_ICONS = DATA / "item_icons"
Hops = Callable[[str], int | None]


@dataclass(frozen=True)
class Monster:
    name: str
    level: int
    hp: int
    exp: int


@dataclass(frozen=True)
class MapSpawns:
    size: tuple[int, int]  # the shipped picture's pixels
    cap: int | None
    spawns: tuple[tuple[str, int, int], ...]  # (monster id, x, y) in the picture's pixels
    respawn: dict[str, tuple[float, float]]  # monster id -> (shortest, longest) seconds


@dataclass(frozen=True)
class SpotData:
    maps: dict[str, MapSpawns]
    monsters: dict[str, Monster]
    pictures: Path
    icons: Path
    counts: dict[str, dict[str, int]] = field(default_factory=dict)  # maps with no spawn spots

    def picture(self, map_id: str) -> Path | None:
        p = self.pictures / f"{map_id}.webp"
        return p if p.is_file() else None

    def icon(self, monster: str) -> Path | None:
        p = self.icons / f"{monster}.png"
        return p if p.is_file() else None


@cache
def load_spots(path: Path = SPOTS, pictures: Path = PICTURES, icons: Path = ICONS) -> SpotData:
    raw = json.loads(path.read_text("utf-8"))
    maps = {
        i: MapSpawns(
            (m["size"][0], m["size"][1]),
            m.get("cap"),
            tuple((mob, x, y) for mob, x, y in m["spawns"]),
            {mob: (lo, hi) for mob, (lo, hi) in m.get("respawn", {}).items()},
        )
        for i, m in raw["maps"].items()
    }
    monsters = {
        i: Monster(m["name"], m["level"], m["hp"], m["exp"]) for i, m in raw["monsters"].items()
    }
    return SpotData(maps, monsters, pictures, icons, raw.get("counts", {}))


@dataclass(frozen=True)
class Npc:
    id: int
    name: str
    places: tuple[tuple[str, int | None, int | None], ...]  # (map id, x, y)


@dataclass(frozen=True)
class Mob:
    id: int
    name: str
    spawns: dict[str, int]  # map id -> spawn count
    level: int = 0


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    drops: tuple[tuple[int, float | None], ...]  # (monster id, drop rate %)
    shops: tuple[int, ...]  # NPC ids that sell it


@dataclass(frozen=True)
class GameData:
    npcs: dict[int, Npc]
    mobs: dict[int, Mob]
    items: dict[int, Item]
    npc_icons: Path = NPC_ICONS
    item_icons: Path = ITEM_ICONS

    def npc_icon(self, npc: int) -> Path | None:
        p = self.npc_icons / f"{npc}.png"
        return p if p.is_file() else None

    def item_icon(self, item: int) -> Path | None:
        p = self.item_icons / f"{item}.png"
        return p if p.is_file() else None


@cache
def load_game(monsters: Path = SPOTS, game: Path = GAME) -> GameData:
    mon = json.loads(monsters.read_text("utf-8"))
    raw = json.loads(game.read_text("utf-8"))
    spawns: dict[int, dict[str, int]] = {}
    for map_id, m in mon["maps"].items():
        for mob, _, _ in m["spawns"]:
            row = spawns.setdefault(int(mob), {})
            row[map_id] = row.get(map_id, 0) + 1
    for map_id, counts in mon.get("counts", {}).items():
        for mob, n in counts.items():
            spawns.setdefault(int(mob), {})[map_id] = n
    mobs = {
        int(i): Mob(int(i), m["name"], spawns.get(int(i), {}), m["level"])
        for i, m in mon["monsters"].items()
    }
    npcs = {
        int(i): Npc(int(i), n["name"], tuple((m, x, y) for m, x, y in n["places"]))
        for i, n in raw["npcs"].items()
    }
    items = {
        int(i): Item(
            int(i),
            it["name"],
            tuple((mob, rate) for mob, rate in it["drops"]),
            tuple(it["shops"]),
        )
        for i, it in raw["items"].items()
    }
    return GameData(npcs, mobs, items)


DOT_COLOURS = ("#ffcc33", "#7fa8ff", "#8ce678", "#ff8cc8")
CAP = "Up to {} monsters at once"


@dataclass(frozen=True)
class CardMob:
    id: str
    name: str
    stats: str
    spots: str
    colour: str


@dataclass(frozen=True)
class Card:
    title: str
    street: str
    picture: Path | None
    size: tuple[int, int]
    mobs: tuple[CardMob, ...]
    cap: str | None
    dots: tuple[tuple[int, int, str], ...]  # (x, y, colour) in picture pixels
    lines: tuple[str, ...] = ()  # extra lines after `cap`


def respawn_text(lo: float, hi: float) -> str:
    unit, div = ("min", 60) if lo >= 120 else ("s", 1)
    a, b = lo / div, hi / div
    span = f"{a:g}" if a == b else f"{a:g}\N{EN DASH}{b:g}"
    return f"every {span} {unit}"


def map_card(  # noqa: PLR0913, PLR0917 - the card's own parts, as the tools call it
    spots: SpotData,
    map_id: str,
    name: str,
    street: str,
    only: str | None = None,
    extra: str | None = None,
) -> Card | None:
    """The hover card for a map; None when there is neither a picture nor monsters.
    `only` keeps one monster's line and dots."""
    m = spots.maps.get(map_id)
    picture = spots.picture(map_id) if m else None
    at: dict[str, list[tuple[int, int]]] = {}
    counts: dict[str, int] = {}
    if m:
        for mob, x, y in m.spawns:
            if mob in spots.monsters and only in (None, mob):
                at.setdefault(mob, []).append((x, y))
        counts = {i: len(v) for i, v in at.items()}
    else:
        counts = {
            i: n
            for i, n in spots.counts.get(map_id, {}).items()
            if i in spots.monsters and only in (None, i)
        }
    if not counts and picture is None:
        return None
    order = sorted(counts, key=lambda i: (-counts[i], spots.monsters[i].name))
    mobs, dots = [], []
    for n, i in enumerate(order):
        mon, colour = spots.monsters[i], DOT_COLOURS[0 if only else n % len(DOT_COLOURS)]
        if m:
            line = f"{counts[i]} spawn spot{'s' * (counts[i] != 1)}"
            if i in m.respawn:
                line += f" · respawns {respawn_text(*m.respawn[i])}"
            dots += [(x, y, colour) for x, y in at[i]]
        else:
            line = f"{counts[i]} spawn{'s' * (counts[i] != 1)}"
        stats = f"Lv {mon.level} · {mon.hp:,} HP · {mon.exp:,} EXP"
        mobs.append(CardMob(i, mon.name, stats, line, colour))
    cap = CAP.format(m.cap) if m and m.cap else None
    size = m.size if m else (0, 0)
    return Card(
        name, street, picture, size, tuple(mobs), cap, tuple(dots), (extra,) if extra else ()
    )


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]  # signature, IHDR length and tag, then width and height
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def npc_card(data: GameData, npc_id: int, map_title: str, shop: bool = False) -> Card | None:
    """An NPC's card: its picture at its own size, and where it stands."""
    npc = data.npcs.get(npc_id)
    if npc is None:
        return None
    picture = data.npc_icon(npc_id)
    size = _png_size(picture) if picture else (0, 0)
    return Card(npc.name, map_title, picture, size, (), None, (), ("Sells it",) if shop else ())


SEARCH_LIMIT = 20
KINDS = ("monster", "npc", "item", "map")  # tie order


@dataclass(frozen=True)
class Match:
    kind: str
    ids: tuple  # int ids, or (map_id,) for a map
    name: str
    line: str


def _item_line(data: GameData, item: Item) -> str:
    parts = []
    if item.shops:
        sold = data.npcs.get(item.shops[0])
        one = len(item.shops) == 1 and sold
        parts.append(f"sold by {sold.name}" if one else f"{len(item.shops)} shops")
    droppers = sorted({data.mobs[m].name for m, _ in item.drops if m in data.mobs})
    if droppers:
        many = f"dropped by {len(droppers)} monsters"
        parts.append(f"dropped by {droppers[0]}" if len(droppers) == 1 else many)
    return " · ".join(["Item", *parts]) if parts else "Item · no known place"


def _entries(data: GameData, maps: Mapping[str, tuple[str, str]]):
    """Every searchable thing as (kind, name, ids, line, street)."""
    by_name: dict[str, list[Mob]] = {}
    for mob in data.mobs.values():
        by_name.setdefault(mob.name, []).append(mob)
    for name, group in by_name.items():
        places = {m for g in group for m, n in g.spawns.items() if n > 0 and m in maps}
        line = f"Monster · Lv {min(g.level for g in group)} · {len(places)} maps"
        yield "monster", name, tuple(sorted(g.id for g in group)), line, ""
    for npc in data.npcs.values():
        places = sorted({m for m, _, _ in npc.places if m in maps})
        where = maps[places[0]][0] if len(places) == 1 else f"{len(places)} maps"
        yield "npc", npc.name, (npc.id,), f"NPC · {where}" if places else "NPC · no known place", ""
    for item in data.items.values():
        yield "item", item.name, (item.id,), _item_line(data, item), ""
    for map_id, (name, street) in maps.items():
        yield "map", name, (map_id,), f"Map · {name}", street


def search(
    data: GameData, maps: Mapping[str, tuple[str, str]], text: str, limit: int = SEARCH_LIMIT
) -> list[Match]:
    """Monsters, NPCs, items and maps whose name (a map's street too) contains the text."""
    q = text.strip().lower()
    found = []
    for kind, name, ids, line, street in _entries(data, maps) if q else ():
        n = name.lower()
        if q in n:
            tier = 0 if n == q else 1 if n.startswith(q) else 2
        elif q in street.lower():
            tier = 2
        else:
            continue
        found.append((tier, KINDS.index(kind), name, Match(kind, ids, name, line)))
    found.sort(key=lambda f: f[:3])
    return [f[3] for f in found[:limit]]


NEAR_TIE = 0.8  # Best: a place scoring this much of the top counts as tied with it


@dataclass(frozen=True)
class Source:
    map_id: str
    at: tuple[int, int] | None  # an NPC's spot
    via: int  # monster id, or the shop NPC's id
    shop: bool
    count: int  # spawns of `via` on the map; 0 for a shop
    rate: float | None  # `via`'s rate; None for a monster search or unknown
    others: int  # other droppers on the same map
    score: float  # expected drops per clear, or spawns
    hops: int | None


def _rank(group: list[Source], closest: bool) -> list[Source]:
    """One group's order. Hops are all known, or all None (then they count as equal)."""

    def near(s):
        return (s.hops or 0, -s.score, s.map_id)

    if closest or not group:
        return sorted(group, key=near)
    top = max(s.score for s in group)
    tied = [s for s in group if s.score >= NEAR_TIE * top]
    rest = [s for s in group if s.score < NEAR_TIE * top]
    return sorted(tied, key=near) + sorted(rest, key=lambda s: (-s.score, s.map_id))


def _arrange(shops, rated, unrated, closest: bool) -> list[Source]:
    """Shops, rated maps, unrated maps; places out of reach last when any place is in reach."""
    reach = any(s.hops is not None for s in shops + rated + unrated)

    def split(group):
        gone = [s for s in group if reach and s.hops is None]
        return [s for s in group if s not in gone], gone

    def shop_order(group):
        return sorted(group, key=lambda s: (s.hops is None, s.hops or 0, s.map_id))

    (sl, sd), (rl, rd), (ul, ud) = split(shops), split(rated), split(unrated)
    return (
        shop_order(sl)
        + _rank(rl, closest and reach)
        + _rank(ul, closest and reach)
        + shop_order(sd)
        + _rank(rd, False)
        + _rank(ud, False)
    )


def _shops(data: GameData, item: Item, listed: Collection[str], hops: Hops) -> list[Source]:
    out = []
    for npc_id in item.shops:
        for map_id, x, y in data.npcs[npc_id].places if npc_id in data.npcs else ():
            if map_id in listed:
                at = (x, y) if x is not None and y is not None else None
                out.append(Source(map_id, at, npc_id, True, 0, None, 0, 0, hops(map_id)))
    return out


def mob_places(
    data: GameData, mob_ids: Iterable[int], listed: Collection[str], hops: Hops, closest: bool
) -> list[Source]:
    """The maps these (same-name) monsters spawn on, spawns added up."""
    per_map: dict[str, list[tuple[int, int]]] = {}
    for mob_id in mob_ids:
        for map_id, n in (data.mobs[mob_id].spawns if mob_id in data.mobs else {}).items():
            if n > 0 and map_id in listed:
                per_map.setdefault(map_id, []).append((n, mob_id))
    unrated = []
    for map_id, rows in per_map.items():
        n, via = max(rows, key=lambda r: (r[0], -r[1]))
        total = sum(r[0] for r in rows)
        unrated.append(Source(map_id, None, via, False, total, None, 0, total, hops(map_id)))
    return _arrange([], [], unrated, closest)


def item_places(
    data: GameData, item_id: int, listed: Collection[str], hops: Hops, closest: bool
) -> list[Source]:
    """Where an item is sold, then where it drops, best first (see the design's ranking)."""
    item = data.items[item_id]
    per_map: dict[str, list[tuple[int, int, float | None]]] = {}  # (spawns, mob id, rate)
    for mob_id, rate in item.drops:
        for map_id, n in (data.mobs[mob_id].spawns if mob_id in data.mobs else {}).items():
            if n > 0 and map_id in listed:
                per_map.setdefault(map_id, []).append((n, mob_id, rate))
    rated, unrated = [], []
    for map_id, rows in per_map.items():
        with_rate = [(n * r / 100, -m, n, r) for n, m, r in rows if r is not None]
        if with_rate:
            _, neg, n, r = max(with_rate)
            total = sum(w[0] for w in with_rate)
            rated.append(
                Source(map_id, None, -neg, False, n, r, len(rows) - 1, total, hops(map_id))
            )
        else:
            n, m = max((n, -m) for n, m, _ in rows)
            total = sum(n for n, _, _ in rows)
            unrated.append(
                Source(map_id, None, -m, False, n, None, len(rows) - 1, total, hops(map_id))
            )
    return _arrange(_shops(data, item, listed, hops), rated, unrated, closest)


def npc_places(data: GameData, npc_id: int, listed: Collection[str], hops: Hops) -> list[Source]:
    """The listed maps an NPC stands on, nearest first."""
    out = []
    for map_id, x, y in data.npcs[npc_id].places:
        if map_id in listed:
            at = (x, y) if x is not None and y is not None else None
            out.append(Source(map_id, at, npc_id, False, 0, None, 0, 0, hops(map_id)))
    return sorted(out, key=lambda s: (s.hops is None, s.hops or 0, s.map_id))
