"""macOS: MapleLens's own windows float over the game without taking the keyboard from it."""

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSPanel,
    NSPopUpMenuWindowLevel,
    NSWindowStyleMaskNonactivatingPanel,
)
from PySide6.QtWidgets import QWidget


def make_panel(widget: QWidget) -> None:
    """Keep the widget's window visible while the game is active, and out of the keyboard."""
    window = objc.objc_object(c_void_p=int(widget.winId())).window()  # winId is an NSView
    if window is None:
        return
    if isinstance(window, NSPanel):
        window.setStyleMask_(window.styleMask() | NSWindowStyleMaskNonactivatingPanel)
        window.setBecomesKeyOnlyIfNeeded_(True)  # clicks and drags leave the keyboard alone
    window.setHidesOnDeactivate_(False)
    # The game lifts its window to level 26 while it's active; stay above it, below menus.
    window.setLevel_(NSPopUpMenuWindowLevel - 1)


def make_accessory() -> None:
    """No Dock icon or app menu, also for a plain python process (run from source).

    Only the policy: it never brings MapleLens or any other app to the front.
    """
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def release_keyboard() -> None:
    """Step back if typing made MapleLens the active app; macOS hands the keyboard back."""
    app = NSApplication.sharedApplication()
    if app.isActive():
        app.deactivate()  # activation returns to the previous app; nothing touches the game
