"""quests.json: the quests; the NPCs, monsters and items they name come from gamedata."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from maplelens.gamedata import GameData, Item, Mob, Npc, load_game

DATA = Path(__file__).parents[2] / "data" / "quests.json"
MAPS = Path(__file__).parents[2] / "data" / "maps.json"
ICONS = Path(__file__).parents[2] / "data" / "item_icons"


@dataclass(frozen=True)
class Reward:
    item: int
    count: int
    kind: str  # "always" | "pick" | "random"
    cls: str | None = None  # Beginner, Warrior, Magician, Bowman, Thief
    gender: str | None = None  # "male" | "female"


@dataclass(frozen=True)
class Rewards:
    exp: int = 0
    mesos: int = 0
    items: tuple[Reward, ...] = ()
    contribution: tuple[str, int, int] | None = None  # (town, low, high)


@dataclass(frozen=True)
class Quest:
    id: int
    name: str
    giver: int | None
    taker: int | None
    mobs: tuple[tuple[int, int], ...]  # (monster id, count), in the quest's order
    items: tuple[tuple[int, int], ...]  # (item id, count)
    start_items: tuple[int, ...]
    rewards: Rewards = Rewards()
    chain: str | None = None
    after: tuple[int, ...] = ()  # prerequisite quest ids in the same chain


@dataclass(frozen=True)
class QuestData:
    quests: dict[int, Quest]
    npcs: dict[int, Npc]
    mobs: dict[int, Mob]
    items: dict[int, Item]
    map_names: dict[str, str]

    @property
    def game(self) -> GameData:
        return GameData(self.npcs, self.mobs, self.items)


def _rewards(r: dict) -> Rewards:
    c = r.get("contribution")
    return Rewards(
        r.get("exp", 0),
        r.get("mesos", 0),
        tuple(Reward(*i) for i in r.get("items", ())),
        tuple(c) if c else None,
    )


def _load(path: Path, maps: Path, game: GameData | None = None) -> QuestData:
    game = game or load_game()
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
                _rewards(q.get("rewards", {})),
                q.get("chain"),
                tuple(q.get("after", ())),
            )
            for q in raw["quests"]
        },
        game.npcs,
        game.mobs,
        game.items,
        {m["id"]: m["name"] for m in json.loads(maps.read_text("utf-8"))},
    )


_default = cache(_load)


def load(path: Path = DATA, maps: Path = MAPS, game: GameData | None = None) -> QuestData:
    # only the default paths are cached; a test's own files are read fresh
    if game is None and (path, maps) == (DATA, MAPS):
        return _default(path, maps)
    return _load(path, maps, game)
