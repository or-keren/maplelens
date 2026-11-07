"""Build MapleLens for Windows: freeze it, then wrap it in dist/MapleLens-Setup-X.Y.Z.exe.

Usage: uv run --group build python scripts/build_installer.py [--freeze-only]
Before the freeze it writes the exe's version info from pyproject.toml; after it, it copies
the license texts into dist/MapleLens/licenses/. The build fails if the app holds fewer
templates or minimap pictures than src/, lacks Qt's Windows platform plugin, or if
MapleLens.exe --self-check exits non-zero or takes over SELF_CHECK_S seconds.
Then Inno Setup 6 (ISCC.exe: the ISCC environment variable, PATH, or its default install
folders) builds the installer; --freeze-only stops before that step.
"""

import argparse
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGING = REPO / "packaging" / "windows"
SPEC = PACKAGING / "maplelens.spec"
ISS = PACKAGING / "maplelens.iss"
DIST = REPO / "dist"
WORK = REPO / "build"
# maplelens.spec reads the version info from here
VERSION_FILE = WORK / "version_info.txt"
APP = DIST / "MapleLens"
EXE = APP / "MapleLens.exe"
LICENSES = DIST / "MapleLens" / "licenses"
SRC_PKG = REPO / "src" / "maplelens"
BUNDLE_PKG = DIST / "MapleLens" / "_internal" / "maplelens"
# Data folders, relative to the package, whose PNG count must survive the freeze.
COUNTED = ["readers/templates", "data/minimaps"]
# Files, relative to the app folder, the self-check can't miss: it opens no window, and
# without Qt's Windows platform plugin the app can't show its box.
REQUIRED = ["_internal/PySide6/plugins/platforms/qwindows.dll"]
# A frozen app whose import fails shows an error box and waits for a click: on CI, until
# the job's timeout. The self-check takes a few seconds.
SELF_CHECK_S = 120
# Where Inno Setup 6 installs ISCC.exe: for all users, and per user (winget --scope user).
ISCC_PLACES = [
    Path(folder) / "Inno Setup 6" / "ISCC.exe"
    for folder in [
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs",
    ]
]


def _dist_file(dist: str, name: str) -> Callable[[], Path]:
    """The file of installed distribution `dist` whose path ends with `name`."""

    def find() -> Path:
        for f in importlib.metadata.distribution(dist).files or []:
            if str(f).replace("\\", "/").endswith(name):
                return Path(f.locate())
        sys.exit(f"no {name} in the installed {dist}")

    return find


# license file shipped in licenses/ -> where it comes from
LICENSE_SOURCES: dict[str, Callable[[], Path]] = {
    "NOTICE.txt": lambda: PACKAGING / "NOTICE.txt",
    "MapleLens-LICENSE.txt": lambda: REPO / "LICENSE",
    # the PySide6 wheels carry only Qt's commercial license text, so the GNU texts live here
    "PySide6-Qt-LGPL-3.0.txt": lambda: PACKAGING / "licenses" / "lgpl-3.0.txt",
    "PySide6-Qt-GPL-3.0.txt": lambda: PACKAGING / "licenses" / "gpl-3.0.txt",
    "OpenCV-LICENSE.txt": _dist_file("opencv-python-headless", "dist-info/LICENSE.txt"),
    "OpenCV-LICENSE-3RD-PARTY.txt": _dist_file(
        "opencv-python-headless", "dist-info/LICENSE-3RD-PARTY.txt"
    ),
    "numpy-LICENSE.txt": _dist_file("numpy", "dist-info/licenses/LICENSE.txt"),
    "winrt-LICENSE.txt": _dist_file("winrt-runtime", "dist-info/licenses/LICENSE"),
    "Python-LICENSE.txt": lambda: Path(sys.base_prefix) / "LICENSE.txt",
}


def read_version(pyproject: Path = REPO / "pyproject.toml") -> str:
    with pyproject.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def version_info(version: str) -> str:
    """PyInstaller's version-info file for `version` (X.Y.Z): Properties -> Details."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"version {version} isn't X.Y.Z, which the exe's file version needs")
    nums = (*map(int, version.split(".")), 0)
    strings = {
        "FileDescription": "MapleLens",
        "FileVersion": version,
        "InternalName": "MapleLens",
        "LegalCopyright": "Copyright (c) or-keren. MIT License.",
        "OriginalFilename": "MapleLens.exe",
        "ProductName": "MapleLens",
        "ProductVersion": version,
    }
    structs = ",\n        ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={nums},
    prodvers={nums},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        {structs},
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def copy_licenses(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, source in LICENSE_SOURCES.items():
        shutil.copyfile(source(), dest / name)


def _run(cmd: list[str], timeout: float | None = None) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def freeze_cmd() -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
    ]


def find_iscc() -> Path:
    if env := os.environ.get("ISCC"):
        return Path(env)
    if found := shutil.which("ISCC"):
        return Path(found)
    for place in ISCC_PLACES:
        if place.is_file():
            return place
    sys.exit("Inno Setup 6 not found: install it, or set ISCC to its ISCC.exe")


def installer_cmd(iscc: Path, version: str) -> list[str]:
    return [
        str(iscc),
        "/Q",
        f"/DAppVersion={version}",
        f"/DSourceDir={APP}",
        f"/O{DIST}",
        str(ISS),
    ]


def check_bundle(src: Path, bundle: Path, app: Path = APP) -> None:
    """Exit if `bundle` holds fewer PNGs than `src` in any COUNTED folder, or `app` lacks
    a REQUIRED file."""
    for rel in COUNTED:
        want = len(list((src / rel).rglob("*.png")))
        have = len(list((bundle / rel).rglob("*.png")))
        if have < want:
            sys.exit(f"bundle has {have} of {want} PNGs in {rel}")
    for rel in REQUIRED:
        if not (app / rel).is_file():
            sys.exit(f"bundle has no {rel}")


def main(argv: list[str] | None = None, run: Callable[..., None] = _run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze-only", action="store_true", help="build dist/MapleLens/ only")
    args = parser.parse_args(argv)
    iscc = None if args.freeze_only else find_iscc()  # missing Inno Setup fails fast
    version = read_version()
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(version_info(version), encoding="utf-8")
    run(freeze_cmd())
    check_bundle(SRC_PKG, BUNDLE_PKG)
    copy_licenses(LICENSES)
    try:
        run([str(EXE), "--self-check"], timeout=SELF_CHECK_S)
    except subprocess.CalledProcessError:
        sys.exit(f"{EXE.name} --self-check failed")
    except subprocess.TimeoutExpired:
        sys.exit(f"{EXE.name} --self-check took over {SELF_CHECK_S} s (an error box?)")
    if iscc:
        run(installer_cmd(iscc, version))
        report_size(DIST / f"MapleLens-Setup-{version}.exe")
    return 0


def report_size(setup: Path) -> None:
    """Print the installer's size; over 150 MB is a budget to explain, not a failure."""
    if not setup.is_file():
        return
    mb = setup.stat().st_size / 1_000_000
    note = " (over the 150 MB budget)" if mb > 150 else ""
    print(f"{setup.name}: {mb:.0f} MB{note}")


if __name__ == "__main__":
    sys.exit(main())
