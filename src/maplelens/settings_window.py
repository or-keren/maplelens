"""The Settings window: what the player sets once, in the box's dark look.

A card per tool, in the tabs' order, headed by the tool's own on/off switch; its settings
sit under the switch and grey out while it's off. Each tool builds its own settings
(`settings_section()`), so no tool knows about another; the app builds General. Every
control applies and saves the moment it changes: no OK button. Only mouse controls: the
window never takes the keyboard from the game.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from maplelens.overlay import (
    ACCENT,
    DIM,
    EDGE,
    FONT,
    LABEL_COLOR,
    LABEL_PT,
    VALUE_COLOR,
    FloatingWindow,
    secondary_button,
    setting_box,
    tool_switch,
)

TITLE = "MapleLens — Settings"
GENERAL = "General"
AUTO_UPDATES = "Check for updates automatically"
CHECK_NOW = "Check now"
NOTHING_YET = "Nothing to set yet"
LAST_ON = "At least one tool stays on"
_BG, _CARD = "#101218", "#171b24"  # the box's fill, opaque; a card on it
# The checkboxes and switches paint themselves (overlay.py); this styles the rest.
STYLE = f"""
#settings {{ background: {_BG}; }}
QScrollArea, #page {{ background: transparent; border: 0; }}
QLabel {{ color: {VALUE_COLOR}; font-family: "{FONT}"; font-size: {LABEL_PT}pt; }}
QLabel#head {{ font-size: {LABEL_PT + 1}pt; font-weight: bold; }}
#hint {{ color: {LABEL_COLOR}; }}
QLabel:disabled, QLabel#hint:disabled {{ color: {DIM}; }}
#card {{ background: {_CARD}; border: 1px solid {EDGE}; border-radius: 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {EDGE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -5px 0;
    border-radius: 7px; }}
QSlider::sub-page:horizontal:disabled, QSlider::handle:horizontal:disabled {{
    background: {DIM}; }}
"""
_INDENT = 36  # a card's settings sit under its switch's name, not its toggle


@dataclass
class ToolSection:
    title: str  # the tool's tab name: its switch's text
    on: bool
    body: QWidget | None  # its settings_section(), or None: nothing to set yet


class GeneralSection(QWidget):
    """The app's own settings, which belong to no tool."""

    def __init__(self):
        super().__init__()
        self._rows = QVBoxLayout(self)
        self._rows.setContentsMargins(0, 0, 0, 0)

    @property
    def empty(self) -> bool:
        return self._rows.count() == 0

    def add_updates(
        self, auto: bool, set_auto: Callable[[bool], None], check_now: Callable[[], None]
    ) -> None:
        """The automatic update check's checkbox, and a button that checks now (its answer
        shows in the box's notice line). Only the installed app has an update check."""
        row = QHBoxLayout()
        row.addWidget(setting_box(AUTO_UPDATES, auto, set_auto))
        row.addStretch()
        row.addWidget(secondary_button(CHECK_NOW, check_now))
        self._rows.addLayout(row)


def _card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    column = QVBoxLayout(card)
    column.setContentsMargins(12, 10, 12, 12)
    column.setSpacing(6)
    return card, column


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    return label


class SettingsWindow(FloatingWindow):
    """General (when it has anything), then a card per tool; `on_switch` gets a tool's index
    (its tab's) and its new state. The last tool still on can't be turned off: a box with
    no tabs would show nothing."""

    def __init__(
        self,
        tools: list[ToolSection],
        on_switch: Callable[[int, bool], None] = lambda _i, _on: None,
        general: GeneralSection | None = None,
    ):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setObjectName("settings")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self._on_switch = on_switch
        page = QWidget()
        page.setObjectName("page")
        column = QVBoxLayout(page)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(10)
        if general is not None and not general.empty:
            card, rows = _card()
            head = QLabel(GENERAL)
            head.setObjectName("head")
            rows.addWidget(head)
            rows.addWidget(general)
            column.addWidget(card)
        self.switches: list = []
        self._bodies: dict[str, QWidget] = {}
        for i, tool in enumerate(tools):
            card, rows = _card()
            switch = tool_switch(tool.title, tool.on, lambda on, i=i: self._switched(i, on))
            switch.setObjectName("head")
            rows.addWidget(switch)
            body = QWidget()
            under = QVBoxLayout(body)
            under.setContentsMargins(_INDENT, 0, 0, 0)
            under.addWidget(tool.body if tool.body is not None else _hint(NOTHING_YET))
            body.setEnabled(tool.on)
            rows.addWidget(body)
            column.addWidget(card)
            self.switches.append(switch)
            self._bodies[tool.title] = body
        column.addStretch()
        self._guard_last()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        self.resize(400, min(page.sizeHint().height() + 2, 640))  # past that, it scrolls

    def _switched(self, index: int, on: bool) -> None:
        self._guard_last()
        self._on_switch(index, on)

    def _guard_last(self) -> None:
        checked = [s for s in self.switches if s.isChecked()]
        for s in self.switches:
            last = len(checked) == 1 and s.isChecked()
            s.setEnabled(not last)
            s.setToolTip(LAST_ON if last else "")

    def set_section_enabled(self, title: str, on: bool) -> None:
        """Grey out a tool's settings (it's off), or bring them back; its switch stays."""
        if (body := self._bodies.get(title)) is not None:
            body.setEnabled(on)
