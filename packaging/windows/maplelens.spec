# PyInstaller spec: MapleLens as a one-folder, windowed app (dist/MapleLens/MapleLens.exe).
# Run through scripts/build_installer.py, not directly.
#
# Hooks do the rest: PySide6's hooks collect only the Qt modules MapleLens imports
# (QtCore, QtGui, QtWidgets) plus their plugins, and winrt-runtime ships its own hook
# that collects every installed projection with its _table.pywinrt.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

HERE = Path(SPECPATH)
ROOT = HERE.parent.parent
# written by build_installer.py from pyproject.toml's version
VERSION_FILE = ROOT / "build" / "version_info.txt"

a = Analysis(
    [str(ROOT / "src" / "maplelens" / "app.py")],
    pathex=[str(ROOT / "src")],
    # templates, maps.json and minimap pictures, at their module-relative paths;
    # the metadata is where --self-check and the app read the version
    datas=collect_data_files("maplelens") + copy_metadata("maplelens"),
    excludes=["tkinter", "unittest", "pydoc", "PyInstaller"],
)

# Files the hooks collect that MapleLens never uses (~60 MB): OpenCV's video backend,
# Qt's translations (the UI is English), and the PDF and virtual-keyboard plugins with
# the Qt libraries only they load (Pdf, Quick, Qml).
UNUSED = (
    "cv2/opencv_videoio_ffmpeg",
    "PySide6/translations/",
    "PySide6/plugins/imageformats/qpdf",
    "PySide6/plugins/platforminputcontexts/",
    "PySide6/Qt6Pdf",
    "PySide6/Qt6VirtualKeyboard",
    "PySide6/Qt6Quick",
    "PySide6/Qt6Qml",
    "PySide6/Qt6OpenGL.",
)


def _used(entries):
    return [e for e in entries if not e[0].replace("\\", "/").startswith(UNUSED)]


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
    icon=str(HERE / "icon.ico"),
    version=str(VERSION_FILE),
)
coll = COLLECT(exe, a.binaries, a.datas, name="MapleLens", upx=False)
