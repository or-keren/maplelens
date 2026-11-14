from pathlib import Path

import pytest

from maplelens.store import DEFAULTS, data_dir, load_settings, save_settings


def test_missing_settings_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "x.json") == DEFAULTS


def test_settings_roundtrip_keeps_defaults(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, {"window_title": "Maple"})
    s = load_settings(p)
    assert s["window_title"] == "Maple"
    assert s["idle_cutoff_s"] == 90


def test_corrupt_settings_gives_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert load_settings(p) == DEFAULTS


def test_data_dir_mac(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # HOME is ignored on Windows
    want = tmp_path / "Library/Application Support/MapleLens"
    assert data_dir() == want
    assert want.is_dir()


def test_data_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert data_dir() == tmp_path / "MapleLens"


def test_settings_without_the_tool_switches_load_them_on(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, {"window_title": "Maple"})  # an older file: no exp_on, path_on…
    s = load_settings(p)
    assert all(s[k] is True for k in ("exp_on", "path_on", "class_on", "quests_on"))


def test_a_tool_switch_that_isnt_a_boolean_falls_back_on(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, {"exp_on": "no", "path_on": 0, "class_on": None, "quests_on": False})
    s = load_settings(p)
    assert (s["exp_on"], s["path_on"], s["class_on"]) == (True, True, True)
    assert s["quests_on"] is False  # a real boolean is kept


def test_clean_leaves_keys_it_doesnt_check_alone(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, {"boxes": "odd", "tab_width": "wide"})
    s = load_settings(p)
    assert (s["boxes"], s["tab_width"]) == ("odd", "wide")


@pytest.mark.parametrize(
    "saved, loaded",
    [(36, 36), (60, 60), (10, 24), (500, 72), (37, 36), (39, 40), (50.0, 52), ("big", 36),
     (True, 36), (None, 36)],
)  # fmt: skip
def test_arrow_size_is_clamped_to_the_offered_sizes(tmp_path, saved, loaded):
    p = tmp_path / "s.json"
    save_settings(p, {"arrow_size": saved})
    assert load_settings(p)["arrow_size"] == loaded


def test_the_arrow_switch_falls_back_on(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, {"arrow_on": "yes"})
    assert load_settings(p)["arrow_on"] is True


@pytest.mark.parametrize(
    "saved, loaded",
    [("#ff5a5a", "#ff5a5a"), ("#123456", "#ffcc33"), (["#ff5a5a"], "#ffcc33"), (7, "#ffcc33")],
)
def test_arrow_colour_must_be_one_offered(tmp_path, saved, loaded):
    p = tmp_path / "s.json"
    save_settings(p, {"arrow_color": saved})
    assert load_settings(p)["arrow_color"] == loaded
