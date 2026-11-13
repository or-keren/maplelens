from pathlib import Path

from maplelens.tools.class_helper.data import DATA, MAPS, STATS, Place, load

SMALL = Path(__file__).parent / "fixtures" / "classes_small.json"


def test_aliases_and_titles():
    d = load(SMALL, MAPS)
    assert d.plan("Thief") is d.plan("Rogue")
    assert d.plan("Hermit") is None and d.plan(None) is None
    row = d.plan("Rogue").training[0]
    assert row.place.title == "Maple Road / Mushroom Town - West Entrance"


def test_missing_map_keeps_its_name_and_no_title():
    row = load(SMALL, MAPS).plan("Rogue").training[1]
    assert row.place == Place(None, "A map not in maps.json", None)


def test_unknown_build_falls_back_to_main():
    p = load(SMALL, MAPS).plan("Rogue")
    assert p.build("Gone") is p.builds[0] and p.build(None) is p.builds[0]
    assert p.build("Sindit").name == "Sindit"


def test_band_targets_grow_with_level():
    band = load(SMALL, MAPS).plan("Rogue").build("Sindit").ap[0]  # hold DEX base 0, per_level 1
    assert band.targets(30) == {"DEX": 30}


# Checks on the shipped data.
D = load(DATA, MAPS)


def _places():
    for job, plan in D.jobs.items():
        for r in plan.training:
            yield job, r.place
        if plan.advance and plan.advance.where:
            yield job, plan.advance.where
        for b in plan.builds:
            if b.advance and b.advance.where:
                yield job, b.advance.where
            for g in b.gear:
                if g.where:
                    yield job, g.where


def test_every_map_id_is_in_maps_json():
    import json

    known = {m["id"] for m in json.loads(MAPS.read_text("utf-8"))}
    for job, p in _places():
        if p.map_id is None:
            assert p.name, f"{job}: a null map_id needs a name"
        else:
            assert p.map_id in known, f"{job}: map {p.map_id} not in maps.json"


def test_every_plan_skill_is_known_and_on_its_tab():
    for job, plan in D.jobs.items():
        for b in plan.builds:
            for s in b.sp:
                assert s.skill in D.skills, f"{job}/{b.name}: skill {s.skill} unknown"
                sk = D.skills[s.skill]
                assert sk.job == job, f"{job}/{b.name}: skill {s.skill} is a {sk.job} skill"
                assert s.up_to <= sk.max, (
                    f"{job}/{b.name}: skill {s.skill} up_to {s.up_to} > {sk.max}"
                )
    for sk in D.skills.values():
        for r in sk.requires:
            assert r in D.skills, f"skill {sk.id} requires unknown {r}"


def test_skill_names_are_unique():
    # The skill window matches rows by name on one job tab, so names must be unique per job
    # (Assassin and Bandit both have a "Haste", on different tabs).
    pairs = [(s.job, s.name) for s in D.skills.values()]
    assert len(pairs) == len(set(pairs)), sorted(p for p in set(pairs) if pairs.count(p) > 1)


def test_every_gear_item_is_known():
    for job, plan in D.jobs.items():
        for b in plan.builds:
            for g in b.gear:
                assert g.item.id in D.items, f"{job}/{b.name}: item {g.item.id} unknown"


def test_bands_cover_from_level_to_200():
    for job, plan in D.jobs.items():
        for b in plan.builds:
            assert b.ap, f"{job}/{b.name}: no bands"
            assert b.ap[0].from_level == plan.from_level, f"{job}/{b.name}: first band start"
            assert b.ap[-1].to_level == 200, f"{job}/{b.name}: last band end"
            for a, c in zip(b.ap, b.ap[1:], strict=False):
                assert a.to_level == c.from_level, f"{job}/{b.name}: gap at {a.to_level}"
            lv = [g.from_level for g in b.gear]
            assert lv == sorted(lv), f"{job}/{b.name}: gear rows out of order"
            for band in b.ap:
                assert band.rest in STATS and band.rest not in band.hold, f"{job}/{b.name}"
                assert set(band.hold) <= set(STATS), f"{job}/{b.name}"


def test_records_cover_the_owners_path():
    assert {"Beginner", "Rogue", "Assassin", "Bandit"} <= set(D.jobs)


def test_sp_plans_only_ever_raise_a_skill_and_meet_prerequisites():
    for job, plan in D.jobs.items():
        for b in plan.builds:
            have: dict[int, int] = {}
            for s in b.sp:
                where = f"{job}/{b.name}: skill {s.skill}"
                assert s.up_to > have.get(s.skill, 0), f"{where} up_to {s.up_to} does not raise it"
                for need, lv in D.skills[s.skill].requires.items():
                    # a prerequisite on an earlier job's tab would be treated as met; none exist
                    assert have.get(need, 0) >= lv, f"{where} needs skill {need} at {lv} first"
                have[s.skill] = s.up_to


def test_reset_at_is_inside_the_record():
    for job, plan in D.jobs.items():
        for b in plan.builds:
            if b.reset_at is not None:
                assert plan.from_level <= b.reset_at <= 200, (
                    f"{job}/{b.name}: reset_at {b.reset_at}"
                )


FIRST_AND_SECOND = [
    "Beginner", "Warrior", "Magician", "Bowman", "Rogue", "Fighter", "Page",
    "Spearman", "Wizard (Fire, Poison)", "Wizard (Ice, Lightning)", "Cleric", "Hunter",
    "Crossbowman", "Assassin", "Bandit",
]  # fmt: skip


def test_every_first_and_second_job_has_a_plan():
    assert [j for j in FIRST_AND_SECOND if load().plan(j) is None] == []


def test_line_includes_aliases_and_tree():
    d = load()
    assassin = {"Beginner", "Rogue", "Thief", "Assassin", "Hermit"}
    assert d.line("Assassin") == assassin
    assert d.line("Hermit") == assassin
    assert d.line("Thief") >= {"Beginner", "Rogue", "Assassin", "Bandit", "Hermit", "Chief Bandit"}
    assert "Bandit" not in d.line("Assassin")
    assert d.line("Nobody") == {"Nobody"}
