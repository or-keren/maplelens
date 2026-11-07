import hashlib
import importlib
import json
from pathlib import Path

import pytest

from maplelens import update
from maplelens.update import Release, can_update, digest_ok, is_newer, parse_latest

FIXTURES = Path(__file__).parent / "fixtures" / "github"
H = "a" * 64


def reply(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def release(version: str) -> Release:
    return Release(version, f"https://example.invalid/MapleLens-Setup-{version}.exe", None)


# parse_latest


def test_newer_release_picks_the_setup_exe_by_name():
    r = parse_latest(reply("newer.json"))
    assert r == Release(
        "0.2.0",
        "https://github.com/or-keren/maplelens/releases/download/v0.2.0/MapleLens-Setup-0.2.0.exe",
        "sha256:" + H,
    )


def test_same_version_still_parses():
    assert parse_latest(reply("same.json")).version == "0.1.0"


@pytest.mark.parametrize(
    "name",
    [
        "no_asset.json",
        "wrong_asset_name.json",
        "tag_two_parts.json",
        "tag_no_v.json",
        "tag_beta.json",
    ],
)
def test_no_update(name):
    assert parse_latest(reply(name)) is None


def test_missing_digest_gives_a_release_that_cant_be_verified():
    r = parse_latest(reply("no_digest.json"))
    assert r.version == "0.2.0"
    assert r.digest is None


@pytest.mark.parametrize(
    "junk",
    [
        None,
        [],
        "v0.2.0",
        {},
        {"tag_name": 2},
        {"tag_name": "v0.2.0"},
        {"tag_name": "v0.2.0", "assets": "x"},
        {"tag_name": "v0.2.0", "assets": [None, 3, "x"]},
        {"tag_name": "v0.2.0", "assets": [{"name": "MapleLens-Setup-0.2.0.exe"}]},
        {"tag_name": "v٣.2.0", "assets": []},  # non-ASCII digit
    ],
)
def test_junk_reply_is_no_update(junk):
    assert parse_latest(junk) is None


def test_non_string_digest_is_treated_as_missing():
    data = reply("newer.json")
    data["assets"][1]["digest"] = 5
    assert parse_latest(data).digest is None


# is_newer


@pytest.mark.parametrize(
    "latest, running, want",
    [
        ("0.2.0", "0.1.0", True),
        ("0.10.0", "0.9.0", True),
        ("1.0.0", "0.99.99", True),
        ("0.1.0", "0.1.0", False),
        ("0.1.0", "0.2.0", False),
        ("0.2.0", "", False),
        ("0.2.0", "junk", False),
        ("0.2.0", "0.1", False),
        ("0.2.0", "0.1.0.dev3", False),
        ("junk", "0.1.0", False),
    ],
)
def test_is_newer(latest, running, want):
    assert is_newer(release(latest), running) is want


def test_is_newer_never_raises_on_junk():
    assert is_newer(release("0.2.0"), None) is False


# digest_ok


@pytest.fixture
def setup_file(tmp_path):
    p = tmp_path / "MapleLens-Setup-0.2.0.exe"
    p.write_bytes(b"MZ" + bytes(range(256)) * 1000)
    return p


def sha(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def test_digest_match(setup_file):
    assert digest_ok(setup_file, sha(setup_file)) is True


def test_digest_match_ignores_hex_case(setup_file):
    assert digest_ok(setup_file, sha(setup_file).upper().replace("SHA256", "sha256")) is True


def test_one_changed_byte_fails(setup_file):
    good = sha(setup_file)
    data = bytearray(setup_file.read_bytes())
    data[1000] ^= 1
    setup_file.write_bytes(bytes(data))
    assert digest_ok(setup_file, good) is False


@pytest.mark.parametrize("digest", [None, "", "md5:" + "0" * 32, "sha256:", "sha256:zz", 5])
def test_bad_digest_fails(setup_file, digest):
    assert digest_ok(setup_file, digest) is False


def test_md5_of_the_right_file_still_fails(setup_file):
    md5 = "md5:" + hashlib.md5(setup_file.read_bytes()).hexdigest()
    assert digest_ok(setup_file, md5) is False


def test_missing_file_fails(tmp_path):
    assert digest_ok(tmp_path / "gone.exe", "sha256:" + H) is False


# REPO


def test_repo_defaults_to_upstream(monkeypatch):
    monkeypatch.delenv("MAPLELENS_UPDATE_REPO", raising=False)
    assert importlib.reload(update).REPO == "or-keren/maplelens"


def test_repo_can_point_at_a_fork(monkeypatch):
    monkeypatch.setenv("MAPLELENS_UPDATE_REPO", "dbeilin/maplelens")
    try:
        assert importlib.reload(update).REPO == "dbeilin/maplelens"
    finally:
        monkeypatch.delenv("MAPLELENS_UPDATE_REPO")
        importlib.reload(update)


# can_update: only the installed Windows app; the toggle is read by the app on each tick


@pytest.mark.parametrize(
    "frozen, platform, want",
    [
        (True, "win32", True),
        (False, "win32", False),  # from source
        (True, "darwin", False),
        (True, "linux", False),
    ],
)
def test_can_update(frozen, platform, want):
    assert can_update(frozen, platform) is want
