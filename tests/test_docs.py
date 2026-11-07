"""AGENTS.md's Layout must name files that exist, including the build and release ones."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PKG = ROOT / "src" / "maplelens"


def _layout() -> str:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    return text.split("## Layout", 1)[1].split("\n## ", 1)[0]


def _named_paths() -> list[Path]:
    """The first `path` of each Layout bullet; nested bullets are inside src/maplelens/."""
    paths = []
    for line in _layout().splitlines():
        if m := re.match(r"( *)- `([^`]+)`", line):
            indent, name = m.groups()
            paths.append((PKG if indent else ROOT) / name)
    return paths


def test_every_layout_path_exists():
    paths = _named_paths()
    assert len(paths) > 10
    missing = [str(p.relative_to(ROOT)) for p in paths if not p.exists()]
    assert not missing


def test_layout_lists_the_build_and_release_files():
    named = {p.relative_to(ROOT).as_posix().rstrip("/") for p in _named_paths()}
    for path in ["packaging/windows", "scripts/build_installer.py", ".github/workflows"]:
        assert path in named, path
    layout = _layout()
    for workflow in ["ci.yml", "release.yml", "prepare-release.yml"]:
        assert workflow in layout, workflow
