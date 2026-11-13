"""Build MapleLens: freeze it, then (Windows) wrap it in dist/MapleLens-Setup-X.Y.Z.exe.

Usage: uv run --group build python scripts/build_installer.py
           [--freeze-only | --sign-only | --dmg-only]
Before the freeze it writes the exe's version info from pyproject.toml; after it, it copies
the license texts into dist/MapleLens/licenses/. The build fails if the app holds fewer
templates or minimap pictures than src/, lacks Qt's Windows platform plugin, or if
MapleLens.exe --self-check exits non-zero or takes over SELF_CHECK_S seconds.
Then Inno Setup 6 (ISCC.exe: the ISCC environment variable, PATH, or its default install
folders) builds the installer; --freeze-only stops before that step.
On the Mac the freeze makes dist/MapleLens.app instead: licenses go in, the app gets an
ad-hoc signature (the licenses invalidate PyInstaller's), then the same checks run.
Then it is signed with $MAPLELENS_SIGN_IDENTITY (ad-hoc without it), verified and wrapped
in dist/MapleLens-X.Y.Z.dmg. --sign-only and --dmg-only run just that stage, with the
standard library alone, so CI can split the stages into jobs.
"""

import argparse
import importlib.metadata
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGING = REPO / "packaging" / "windows"
SPEC = PACKAGING / "maplelens.spec"
ISS = PACKAGING / "maplelens.iss"
MAC_SPEC = REPO / "packaging" / "mac" / "maplelens.spec"
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
# Files, relative to the app folder, the bundle must have. The self-check opens no
# window, so it can't miss Qt's Windows platform plugin, without which the app can't show
# its box. The icon it does load; checking it here names the missing file.
REQUIRED = [
    "_internal/PySide6/plugins/platforms/qwindows.dll",
    "_internal/maplelens/data/icon.ico",
]
# A frozen app whose import fails shows an error box and waits for a click: on CI, until
# the job's timeout. The self-check takes a few seconds.
SELF_CHECK_S = 120
MAC_APP = DIST / "MapleLens.app"
MAC_EXE = MAC_APP / "Contents/MacOS/MapleLens"
MAC_BUNDLE_PKG = MAC_APP / "Contents/Resources/maplelens"
MAC_LICENSES = MAC_APP / "Contents/Resources/licenses"
# Qt's Cocoa platform plugin: without it the app can't show its box. The icon, as on
# Windows: the self-check loads it, and this names the missing file.
MAC_REQUIRED = [
    "Contents/Frameworks/PySide6/Qt/plugins/platforms/libqcocoa.dylib",
    "Contents/Resources/maplelens/data/icon.ico",
]
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


# The Mac set: no winrt; pyobjc-core's wheel carries no license file, but its sibling
# pyobjc-framework-cocoa ships the project's MIT text. The uv-managed Python keeps
# LICENSE.txt in its stdlib folder, not in sys.base_prefix itself.
MAC_LICENSE_SOURCES: dict[str, Callable[[], Path]] = {
    **{k: v for k, v in LICENSE_SOURCES.items() if k != "winrt-LICENSE.txt"},
    "pyobjc-LICENSE.txt": _dist_file("pyobjc-framework-cocoa", "dist-info/licenses/LICENSE.txt"),
    "Python-LICENSE.txt": lambda: _existing(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"),
}


def _existing(path: Path) -> Path:
    if not path.is_file():
        sys.exit(f"no {path}")
    return path


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


def copy_licenses(dest: Path, sources: dict[str, Callable[[], Path]] = LICENSE_SOURCES) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        shutil.copyfile(source(), dest / name)


def _run(cmd: list[str], timeout: float | None = None) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def freeze_cmd(spec: Path = SPEC) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
    ]


def sign_cmd(app: Path, identity: str) -> list[str]:
    return ["codesign", "--force", "--deep", "--timestamp=none", "--sign", identity, str(app)]


IDENTITY_ENV = "MAPLELENS_SIGN_IDENTITY"


def sign_identity() -> str:
    if identity := os.environ.get(IDENTITY_ENV):
        return identity
    print(f"no {IDENTITY_ENV}: signing ad-hoc")
    return "-"


def verify_cmd(app: Path) -> list[str]:
    return ["codesign", "--verify", "--deep", "--strict", str(app)]


def dmg_path(version: str, machine: str | None = None) -> Path:
    """One dmg per CPU, named as maplelens.update.asset_name names it (this script runs
    where maplelens can't be imported). The build's CPU is the Mac it runs on."""
    machine = machine or _platform.machine()
    suffix = "-intel" if machine == "x86_64" else ""
    return DIST / f"MapleLens-{version}{suffix}.dmg"


def make_dmg(app: Path, dmg: Path, run: Callable[..., None] = _run) -> None:
    """A dmg holding `app` and a link to /Applications to drag it onto."""
    stage = DIST / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    run(["ditto", str(app), str(stage / app.name)])  # keeps symlinks and signatures
    (stage / "Applications").symlink_to("/Applications")
    create = ["hdiutil", "create", "-volname", "MapleLens", "-srcfolder", str(stage)]
    run([*create, "-fs", "HFS+", "-format", "UDZO", "-ov", str(dmg)])


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


def check_bundle(src: Path, bundle: Path, app: Path = APP, required: list[str] = REQUIRED) -> None:
    """Exit if `bundle` holds fewer PNGs than `src` in any COUNTED folder, or `app` lacks
    a REQUIRED file."""
    for rel in COUNTED:
        want = len(list((src / rel).rglob("*.png")))
        have = len(list((bundle / rel).rglob("*.png")))
        if have < want:
            sys.exit(f"bundle has {have} of {want} PNGs in {rel}")
    for rel in required:
        if not (app / rel).is_file():
            sys.exit(f"bundle has no {rel}")


def _self_check(exe: Path, run: Callable[..., None]) -> None:
    try:
        run([str(exe), "--self-check"], timeout=SELF_CHECK_S)
    except subprocess.CalledProcessError:
        sys.exit(f"{exe.name} --self-check failed")
    except subprocess.TimeoutExpired:
        sys.exit(f"{exe.name} --self-check took over {SELF_CHECK_S} s (an error box?)")


def _freeze_mac(run: Callable[..., None]) -> None:
    run(freeze_cmd(MAC_SPEC))
    copy_licenses(MAC_LICENSES, MAC_LICENSE_SOURCES)
    run(sign_cmd(MAC_APP, "-"))  # the licenses broke PyInstaller's own signature
    check_bundle(SRC_PKG, MAC_BUNDLE_PKG, MAC_APP, MAC_REQUIRED)
    _self_check(MAC_EXE, run)


def _sign_mac(run: Callable[..., None]) -> None:
    run(sign_cmd(MAC_APP, sign_identity()))
    run(verify_cmd(MAC_APP))


def _dmg_mac(run: Callable[..., None]) -> None:
    dmg = dmg_path(read_version())
    make_dmg(MAC_APP, dmg, run)
    report_size(dmg)


def _main_mac(args: argparse.Namespace, run: Callable[..., None]) -> int:
    if args.freeze_only:
        _freeze_mac(run)
    elif args.sign_only:
        _sign_mac(run)
    elif args.dmg_only:
        _self_check(MAC_EXE, run)
        _dmg_mac(run)
    else:
        _freeze_mac(run)
        _sign_mac(run)
        _self_check(MAC_EXE, run)  # the real signature must not break the app
        _dmg_mac(run)
    return 0


def main(
    argv: list[str] | None = None,
    run: Callable[..., None] = _run,
    platform: str = sys.platform,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--freeze-only", action="store_true", help="build the app folder only")
    stage.add_argument("--sign-only", action="store_true", help="Mac: sign and verify the app")
    stage.add_argument("--dmg-only", action="store_true", help="Mac: wrap the app in a dmg")
    args = parser.parse_args(argv)
    if platform == "darwin":
        return _main_mac(args, run)
    if args.sign_only or args.dmg_only:
        parser.error("--sign-only and --dmg-only are for the Mac")
    iscc = None if args.freeze_only else find_iscc()  # missing Inno Setup fails fast
    version = read_version()
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(version_info(version), encoding="utf-8")
    run(freeze_cmd())
    check_bundle(SRC_PKG, BUNDLE_PKG)
    copy_licenses(LICENSES, LICENSE_SOURCES)
    _self_check(EXE, run)
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
