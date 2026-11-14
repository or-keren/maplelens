"""The game's data: NPCs, monsters and items (game.json, monsters.json), and the spawn spots."""

import json
from collections.abc import Callable
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
