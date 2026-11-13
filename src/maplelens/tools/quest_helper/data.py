"""quests.json: quests, the NPCs, monsters and items they name, and where to find each."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA = Path(__file__).parents[2] / "data" / "quests.json"
MAPS = Path(__file__).parents[2] / "data" / "maps.json"


@dataclass(frozen=True)
class Npc:
    id: int
    name: str
    places: tuple[tuple[str, int, int], ...]  # (map id, world x, world y)


@dataclass(frozen=True)
class Mob:
    id: int
    name: str
    spawns: dict[str, int]  # map id -> spawn count


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    drops: tuple[int, ...]  # monster ids that drop it
    shops: tuple[int, ...]  # NPC ids that sell it


@dataclass(frozen=True)
class Quest:
    id: int
    name: str
    giver: int | None
    taker: int | None
    mobs: tuple[tuple[int, int], ...]  # (monster id, count), in the quest's order
    items: tuple[tuple[int, int], ...]  # (item id, count)
    start_items: tuple[int, ...]


@dataclass(frozen=True)
class QuestData:
    quests: dict[int, Quest]
    npcs: dict[int, Npc]
    mobs: dict[int, Mob]
    items: dict[int, Item]
    map_names: dict[str, str]


def _load(path: Path, maps: Path) -> QuestData:
    raw = json.loads(path.read_text("utf-8"))
    return QuestData(
        {
            q["id"]: Quest(
                q["id"],
                q["name"],
                q["giver"],
                q["taker"],
                tuple(map(tuple, q["mobs"])),
                tuple(map(tuple, q["items"])),
                tuple(q["start_items"]),
            )
            for q in raw["quests"]
        },
        {
            int(i): Npc(int(i), n["name"], tuple(map(tuple, n["places"])))
            for i, n in raw["npcs"].items()
        },
        {int(i): Mob(int(i), m["name"], m["spawns"]) for i, m in raw["mobs"].items()},
        {
            int(i): Item(int(i), t["name"], tuple(t["drops"]), tuple(t["shops"]))
            for i, t in raw["items"].items()
        },
        {m["id"]: m["name"] for m in json.loads(maps.read_text("utf-8"))},
    )


_default = cache(_load)


def load(path: Path = DATA, maps: Path = MAPS) -> QuestData:
    # only the default paths are cached; a test's own files are read fresh
    return _default(path, maps) if (path, maps) == (DATA, MAPS) else _load(path, maps)
