# PyInstaller spec: MapleLens as a one-folder, windowed Mac app (dist/MapleLens.app).
# Run through scripts/build_installer.py, not directly.
#
# Hooks do the rest: PySide6's hooks collect only the Qt modules MapleLens imports
# (QtCore, QtGui, QtWidgets) plus their plugins, and the pyobjc hooks collect the
# frameworks it imports.
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

HERE = Path(SPECPATH)
ROOT = HERE.parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

a = Analysis(
    [str(ROOT / "src" / "maplelens" / "app.py")],
    pathex=[str(ROOT / "src")],
    # templates, maps.json and minimap pictures, at their module-relative paths;
    # the metadata is where --self-check and the app read the version
    datas=collect_data_files("maplelens") + copy_metadata("maplelens"),
    excludes=["tkinter", "unittest", "pydoc", "PyInstaller"],
)

# Files the hooks collect that MapleLens never uses: OpenCV's video backend, Qt's
# translations (the UI is English), and the PDF and virtual-keyboard plugins with the Qt
# libraries only they load (Pdf, Quick, Qml).
UNUSED = (
    "cv2/opencv_videoio_ffmpeg",
    "PySide6/Qt/translations/",
    "PySide6/Qt/plugins/imageformats/libqpdf",
    "PySide6/Qt/plugins/platforminputcontexts/",
    "PySide6/Qt/lib/QtPdf.framework",
    "PySide6/Qt/lib/QtVirtualKeyboard.framework",
    "PySide6/Qt/lib/QtQuick.framework",
    "PySide6/Qt/lib/QtQml.framework",
    "PySide6/Qt/lib/QtOpenGL.framework",
)
# PyInstaller also links each framework's binary at the top of the bundle; those links
# would dangle once the framework is gone, and a signed bundle must not hold any.
UNUSED_LINKS = ("QtPdf", "QtQuick", "QtQml", "QtVirtualKeyboard", "QtOpenGL")


def _used(entries):
    return [e for e in entries if not e[0].startswith(UNUSED) and e[0] not in UNUSED_LINKS]


a.binaries = _used(a.binaries)
a.datas = _used(a.datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MapleLens",
    console=False,
    upx=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MapleLens", upx=False)
app = BUNDLE(
    coll,
    name="MapleLens.app",
    icon=str(HERE / "icon.icns"),
    # fixed forever: macOS keys the Screen Recording permission on it
    bundle_identifier="io.github.or-keren.maplelens",
    version=VERSION,
    info_plist={
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "14.4",
        "LSUIElement": True,  # in the menu bar, not the Dock
    },
)
