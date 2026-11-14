"""The game's data: NPCs, monsters and items (game.json, monsters.json), and the spawn spots."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    return SpotData(maps, monsters, pictures, icons)


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
