"""classes.json: per-job advice (training maps, AP/SP plans, gear), read into typed rows."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA = Path(__file__).parents[2] / "data" / "classes.json"
MAPS = Path(__file__).parents[2] / "data" / "maps.json"
# The job reader may say "Thief"; the records say "Rogue".
ALIASES = {"Thief": "Rogue"}
STATS = ("STR", "DEX", "INT", "LUK")


@dataclass(frozen=True)
class Place:
    map_id: str | None
    name: str
    title: str | None  # "Street / Name" from maps.json; None without a map_id


@dataclass(frozen=True)
class Band:
    from_level: int
    to_level: int
    hold: dict[str, tuple[int, float]]  # stat -> (base, per_level)
    rest: str

    def targets(self, level: int) -> dict[str, int]:
        return {s: int(base + per * level) for s, (base, per) in self.hold.items()}


@dataclass(frozen=True)
class SpStep:
    skill: int
    up_to: int


@dataclass(frozen=True)
class Skill:
    id: int
    name: str
    job: str
    max: int
    requires: dict[int, int]


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    req: dict[str, int]


@dataclass(frozen=True)
class TrainRow:
    place: Place
    from_level: int
    to_level: int
    mobs: tuple[int, int]


@dataclass(frozen=True)
class GearRow:
    item: Item
    from_level: int
    where: Place | None


@dataclass(frozen=True)
class Advance:
    level: int
    next_jobs: tuple[str, ...]
    npc: str | None
    where: Place | None


@dataclass(frozen=True)
class Build:
    name: str
    ap: tuple[Band, ...]
    sp: tuple[SpStep, ...]
    gear: tuple[GearRow, ...]
    reset_at: int | None
    advance: Advance | None


@dataclass(frozen=True)
class JobPlan:
    job: str
    tier: int
    from_level: int
    source: str
    training: tuple[TrainRow, ...]
    advance: Advance | None
    builds: tuple[Build, ...]

    def build(self, name: str | None) -> Build:
        return next((b for b in self.builds if b.name == name), self.builds[0])

    def advance_for(self, build: Build) -> Advance | None:
        return build.advance or self.advance


@dataclass(frozen=True)
class ClassData:
    jobs: dict[str, JobPlan]
    skills: dict[int, Skill]
    items: dict[int, Item]

    def plan(self, job: str | None) -> JobPlan | None:
        return self.jobs.get(ALIASES.get(job, job))

    def line(self, job: str) -> frozenset[str]:
        """The job, every job before and after it on the advancement tree, and their aliases."""
        children: dict[str, set[str]] = {}
        parent: dict[str, str] = {}
        for p in self.jobs.values():
            for adv in (p.advance, *(b.advance for b in p.builds)):
                for nxt in adv.next_jobs if adv else ():
                    children.setdefault(p.job, set()).add(nxt)
                    parent[nxt] = p.job
        start = ALIASES.get(job, job)
        if start not in children and start not in parent:
            return frozenset({job})
        found, todo = {start}, [start]
        while todo:  # descendants
            found |= (new := children.get(todo.pop(), set()) - found)
            todo += new
        j = start
        while j in parent:  # ancestors
            found.add(j := parent[j])
        found |= {alias for alias, name in ALIASES.items() if name in found}
        return frozenset(found)


def _hold(v) -> tuple[int, float]:
    return (v["base"], v["per_level"]) if isinstance(v, dict) else (v, 0)


@cache
def load(path: Path = DATA, maps_path: Path = MAPS) -> ClassData:
    raw = json.loads(path.read_text("utf-8"))
    titles = {
        m["id"]: f"{m['street']} / {m['name']}" for m in json.loads(maps_path.read_text("utf-8"))
    }

    def place(o: dict) -> Place | None:
        mid = o.get("map_id")
        if mid is None:
            return Place(None, o["name"], None) if "name" in o else None
        return Place(mid, o.get("name") or titles.get(mid, mid), titles.get(mid))

    skills = {
        int(i): Skill(
            int(i), s["name"], s["job"], s["max"], {int(k): v for k, v in s["requires"].items()}
        )
        for i, s in raw["skills"].items()
    }
    items = {int(i): Item(int(i), s["name"], s["req"]) for i, s in raw["items"].items()}

    def advance(o: dict | None) -> Advance | None:
        if not o:
            return None
        return Advance(o["level"], tuple(o["next_jobs"]), o.get("npc"), place(o))

    def build(o: dict) -> Build:
        return Build(
            o["name"],
            tuple(
                Band(b["from"], b["to"], {s: _hold(v) for s, v in b["hold"].items()}, b["rest"])
                for b in o["ap"]
            ),
            tuple(SpStep(s["skill"], s["up_to"]) for s in o["sp"]),
            tuple(GearRow(items[g["item"]], g["from_level"], place(g)) for g in o["gear"]),
            o.get("reset_at"),
            advance(o.get("advance")),
        )

    jobs = {
        j["job"]: JobPlan(
            j["job"],
            j["tier"],
            j["from_level"],
            j["source"],
            tuple(
                TrainRow(place(t), t["from_level"], t["to_level"], tuple(t["mobs"]))
                for t in j["training"]
            ),
            advance(j.get("advance")),
            tuple(build(b) for b in j["builds"]),
        )
        for j in raw["jobs"]
    }
    return ClassData(jobs, skills, items)
