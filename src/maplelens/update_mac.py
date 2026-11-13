"""macOS: replace MapleLens's own app bundle with the one in a downloaded dmg.

The app hands over to HELPER, a detached /bin/sh script, and quits. The helper waits
for MapleLens to exit, copies the new bundle next to the old one, swaps them with
renames (so a failure leaves the old app at its path), and reopens MapleLens in the
background (`open -g`, so the game keeps focus). It only touches MapleLens's bundle, the
dmg and the updates folder.
"""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

RESULT = "result.txt"  # in the updates folder: "blocked" or "failed" when the swap didn't happen

# $1 MapleLens's PID, $2 the dmg, $3 the bundle to replace, $4 the result file.
# The "blocked" line is how macOS's App Management protection refuses the rename.
HELPER = """\
set -u
pid=$1 dmg=$2 app=$3 result=$4
while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
rm -rf "$app.new" "$app.old"  # left by an update that was cut off; ditto/mv would nest into them
mnt=
fail() {
  echo "$1" > "$result"
  hdiutil detach -quiet "$mnt" 2>/dev/null
  rmdir "$mnt" 2>/dev/null
  rm -rf "$app.new"
  open -g "$app"
  exit 1
}
mnt=$(mktemp -d) || fail failed
hdiutil attach -quiet -nobrowse -readonly -mountpoint "$mnt" "$dmg" || fail failed
ditto "$mnt/MapleLens.app" "$app.new" || fail failed
hdiutil detach -quiet "$mnt"
rmdir "$mnt" 2>/dev/null
if ! err=$(mv "$app" "$app.old" 2>&1); then
  case $err in *"not permitted"*) fail blocked ;; *) fail failed ;; esac
fi
mv "$app.new" "$app" || { mv "$app.old" "$app"; fail failed; }
rm -rf "$app.old" "$dmg"
open -g "$app"
"""


def bundle_path(executable: str) -> Path | None:
    """The .app holding `executable`, or None when running from source."""
    return next((p for p in Path(executable).parents if p.suffix == ".app"), None)


def can_replace(bundle: Path) -> bool:
    """False on the mounted dmg, a translocated copy, or in a folder we can't write."""
    s = str(bundle)
    return (
        not s.startswith("/Volumes/")
        and "/AppTranslocation/" not in s
        and os.access(bundle.parent, os.W_OK)
    )


def helper_cmd(pid: int, dmg: Path, bundle: Path, result: Path) -> list[str]:
    # the paths are arguments, never pasted into the script text
    return [
        "/bin/sh",
        "-c",
        HELPER,
        "maplelens-update",
        str(pid),
        str(dmg),
        str(bundle),
        str(result),
    ]


def install_update(dmg: Path) -> None:
    """Start the helper on its own, then quit the way Quit does (aboutToQuit saves the
    session). If there's no bundle or the helper can't start, the error propagates and
    MapleLens keeps running.
    """
    bundle = bundle_path(sys.executable)
    if bundle is None:
        raise RuntimeError(f"{sys.executable} isn't inside a .app: nothing to replace")
    cmd = helper_cmd(os.getpid(), dmg, bundle, dmg.parent / RESULT)
    subprocess.Popen(cmd, start_new_session=True)
    QApplication.quit()


def read_result(folder: Path) -> str | None:
    """The last helper's result, once: the file is deleted after reading."""
    path = folder / RESULT
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    path.unlink()
    return text
