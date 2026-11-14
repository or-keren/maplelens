"""MapleLens's own windows: a click-through layer over the game and small draggable boxes."""

import sys
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_INSET = 40  # px from the game's top-right corner for a box with no saved position

# The box's look (mockup 1), shared by every tab: grey labels, larger bold values.
FONT = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
LABEL_PT, LABEL_COLOR = 10, "#aebdd3"
NOTICE_PT = 9  # the notice line keeps its size: the longest one must fit TAB_W
VALUE_PT, VALUE_COLOR = 12, "#ffffff"
ACCENT = "#ffcc33"  # "do this": the selected tab, the main button, points to spend
FIELD, DARK, HERE_BG, EDGE = "#0b0f15", "#2a1d00", "#2c3a50", "#3d4b63"
CHIP_BG, INFO_ICON = "#3a2e08", "#7fa8ff"
BOX_FILL = (16, 18, 24, 224)  # RGBA: the box, and the marks' tags over the game
BOX_EDGE = (255, 255, 255, 20)  # RGBA: a thin edge, so the box reads on any map
FIELD_STYLE = f"""
QLineEdit {{ background: {FIELD}; color: {VALUE_COLOR}; border: 1px solid {EDGE};
    border-radius: 4px; padding: 2px 6px; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QListWidget {{ background: {FIELD}; color: {VALUE_COLOR}; border: 0; border-radius: 4px; }}
QListWidget::item:selected {{ background: {HERE_BG}; color: {VALUE_COLOR}; }}
"""
_BUTTON = {
    "primary": f"""
QPushButton {{ background: {ACCENT}; color: {DARK}; font-weight: bold; border: 0;
    border-radius: 4px; padding: 4px; }}
QPushButton:disabled {{ background: {HERE_BG}; color: {LABEL_COLOR}; }}""",
    "secondary": f"""
QPushButton {{ background: transparent; color: #e6edf7; border: 1px solid {EDGE};
    border-radius: 4px; padding: 3px; }}""",
}
# Every tab's width at first, and at least: the box's width less its 12 px side margins.
# It fits four tab titles and the Path tab's dot at the strip's 14 px spacing, in FONT:
# on a real Windows window (Segoe UI) the strip wants a 237 px box, so 238; Helvetica Neue
# on the Mac CI wants 244.
TAB_W = 220 if sys.platform == "darwin" else 214
MAX_TAB_W = 480  # the widest the player can drag the tabs
_GRIP = 12  # the corner handle's side: the box's right margin, so it never covers a tab
# The box's menu button: three bullets. The midline ellipsis isn't in Segoe UI, and
# the font Qt falls back to draws it faint and makes the box taller.
MENU_MARK = "•••"
ABOUT = "About MapleLens"  # the About view's title, and its menu item


def text_label(text: str, pt: int, color: str, *, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setFont(QFont(FONT, pt, QFont.Bold if bold else QFont.Normal))
    label.setStyleSheet(f"color: {color};")
    return label


def mark_button(
    text: str, pt: int, on_click: Callable[[], None], *, color: str = LABEL_COLOR
) -> QPushButton:
    """A flat mark (grey unless `color`) that acts on a click and never takes the game's
    keyboard."""
    button = QPushButton(text)
    button.setFlat(True)
    button.setFocusPolicy(Qt.NoFocus)
    button.setCursor(Qt.PointingHandCursor)
    button.setFont(QFont(FONT, pt))
    button.setStyleSheet(f"color: {color}; border: 0; padding: 0; text-align: left;")
    button.clicked.connect(on_click)
    return button


def _kind_button(kind: str, text: str, on_click: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("kind", kind)
    button.setFocusPolicy(Qt.NoFocus)
    button.setCursor(Qt.PointingHandCursor)
    button.setFont(QFont(FONT, LABEL_PT))
    button.setStyleSheet(_BUTTON[kind])
    button.clicked.connect(on_click)
    return button


def primary_button(text: str, on_click: Callable[[], None]) -> QPushButton:
    """The tab's main action: yellow."""
    return _kind_button("primary", text, on_click)


def secondary_button(text: str, on_click: Callable[[], None]) -> QPushButton:
    """Any other action: an outline."""
    return _kind_button("secondary", text, on_click)


class _InfoMark(QWidget):
    """A small circled i, drawn: the font's own glyph comes from a fallback font, taller."""

    def __init__(self):
        super().__init__()
        side = QFontMetrics(QFont(FONT, LABEL_PT)).ascent()
        self.setFixedSize(side, side)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(INFO_ICON), 1.2))
        side = self.width()
        p.drawEllipse(QRectF(0.6, 0.6, side - 1.2, side - 1.2))
        p.drawLine(QPointF(side / 2, side * 0.45), QPointF(side / 2, side * 0.75))
        p.drawPoint(QPointF(side / 2, side * 0.28))


class InfoLine(QWidget):
    """A grey line for your information, after a blue info mark: why something isn't there."""

    def __init__(self, text: str = ""):
        super().__init__()
        self._icon = _InfoMark()
        self._text = text_label(text, LABEL_PT, LABEL_COLOR)
        self._text.setWordWrap(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(self._icon, 0, Qt.AlignTop)
        row.addWidget(self._text, 1)

    def setText(self, text: str) -> None:  # noqa: N802 - as QLabel
        self._text.setText(text)

    def text(self) -> str:
        return self._text.text()


def fit_tab_w(saved: object) -> int:
    """A tab width within the limits; TAB_W for anything else a hand-edited file may hold."""
    if not isinstance(saved, int) or isinstance(saved, bool):
        return TAB_W
    return min(max(saved, TAB_W), MAX_TAB_W)


_PAD = 6  # a row's side padding


class Row(QWidget):
    """One line to act on: a name, a grey line under it, and a yellow \u203a when a click goes
    somewhere. Names never wrap: they're cut to fit, the full one is the tooltip."""

    def __init__(  # noqa: PLR0913 - the row's parts; all but three are keywords
        self,
        name: str,
        sub: str,
        on_click: Callable[[], None] | None,
        *,
        best: bool = False,
        outline: bool = False,
        trailing: QWidget | None = None,  # in place of the arrow, e.g. a button
        info: bool = False,  # the grey line is why it can't be clicked: an info mark leads it
        width: int = TAB_W,  # what the names are cut to
        on_hover: Callable[[bool], None] | None = None,  # True on enter, False on leave or hide
    ):
        super().__init__()
        self.name, self.sub, self.best, self.outline = name, sub, best, outline
        self._on_hover = on_hover
        self.info = info and bool(sub)
        self.clickable, self._on_click = on_click is not None, on_click
        self.setObjectName("row")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        bg = HERE_BG if best or outline else "transparent"
        edge = f"1px solid {ACCENT}" if outline else f"1px solid {bg}"
        self.setStyleSheet(f"#row {{ background: {bg}; border: {edge}; border-radius: 4px; }}")
        if self.clickable:
            self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(_PAD, 3, _PAD, 3)
        row.setSpacing(6)
        col = QVBoxLayout()
        col.setSpacing(0)
        arrow = text_label("\u203a", LABEL_PT + 2, ACCENT, bold=True)  # single right angle
        end = trailing or (arrow if self.clickable else None)
        room = width - 2 * _PAD - 2 - (end.sizeHint().width() + 6 if end else 0)
        title = text_label(name, LABEL_PT, VALUE_COLOR, bold=best or outline)
        title.setText(QFontMetrics(title.font()).elidedText(name, Qt.ElideRight, room))
        title.setToolTip(name)
        col.addWidget(title)
        if sub:
            under = text_label(sub, LABEL_PT, LABEL_COLOR)
            line = QHBoxLayout()
            line.setSpacing(5)
            if self.info:
                mark = _InfoMark()
                line.addWidget(mark, 0, Qt.AlignVCenter)
                room -= mark.width() + line.spacing()
            under.setText(QFontMetrics(under.font()).elidedText(sub, Qt.ElideRight, room))
            line.addWidget(under, 1)
            col.addLayout(line)
        row.addLayout(col, 1)
        if end:
            row.addWidget(end, 0, Qt.AlignVCenter)

    def click(self) -> None:
        if self._on_click:
            self._on_click()

    # A clickable row takes its press, as a button does, so the box doesn't start a drag;
    # any other row leaves press and release to the box, which drags.
    def mousePressEvent(self, event):
        event.setAccepted(self.clickable and event.button() == Qt.LeftButton)

    def mouseReleaseEvent(self, event):
        if not (self.clickable and event.button() == Qt.LeftButton):
            event.ignore()
            return
        if self.rect().contains(event.position().toPoint()):
            self.click()

    def _hover(self, inside: bool) -> None:
        if self._on_hover:
            self._on_hover(inside)

    def enterEvent(self, event):
        self._hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(False)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._hover(False)
        super().hideEvent(event)


def game_to_layer(px: float, py: float, dpr: float) -> tuple[float, float]:
    """Game-client physical pixels to layer-local Qt logical coordinates."""
    return px / dpr, py / dpr


def native_setup(widget: QWidget) -> None:
    """Platform setup for one of MapleLens's own windows, run each time it's shown.

    Mac: a panel that stays visible over the game and leaves it the keyboard. Nothing on
    Windows: capture grabs the game window alone, so the readers never see these windows,
    and streams and screenshots do.
    """
    if sys.platform == "darwin" and QGuiApplication.platformName() == "cocoa":
        from maplelens import overlay_mac  # AppKit only exists on the Mac

        overlay_mac.make_panel(widget)


DIM = "#5b6678"  # a setting greyed out: its tool is off


class _PaintedCheck(QCheckBox):
    """A checkbox drawn in the box's colours; its whole row takes the click, and it never
    takes focus."""

    _MARK_W = 14  # the drawn mark's width; the text starts after it and a gap
    _GAP = 8
    _BOLD = False
    _PT = LABEL_PT

    def __init__(self, text: str):
        super().__init__(text)
        self.setFont(QFont(FONT, self._PT, QFont.Bold if self._BOLD else QFont.Normal))
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):  # noqa: N802 - Qt's name
        fm = QFontMetrics(self.font())
        w = self._MARK_W + self._GAP + fm.horizontalAdvance(self.text()) + 2
        return QSize(w, max(fm.height(), 16) + 4)

    def minimumSizeHint(self):  # noqa: N802 - Qt's name
        return self.sizeHint()

    def hitButton(self, pos) -> bool:  # noqa: N802 - Qt's name
        return self.rect().contains(pos)

    def _text_color(self) -> str:
        return VALUE_COLOR if self.isEnabled() else DIM

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._paint_mark(p, (self.height() - 16) / 2)
        p.setPen(QColor(self._text_color()))
        p.setFont(self.font())
        x = self._MARK_W + self._GAP
        p.drawText(QRectF(x, 0, self.width() - x, self.height()), Qt.AlignVCenter, self.text())

    def _paint_mark(self, p: QPainter, top: float) -> None:
        on, live = self.isChecked(), self.isEnabled()
        fill = (ACCENT if live else DIM) if on else FIELD
        p.setPen(QPen(QColor(fill if on else (EDGE if live else DIM)), 1))
        p.setBrush(QColor(fill))
        p.drawRoundedRect(QRectF(0.5, top + 1.5, 13, 13), 3, 3)
        if on:
            p.setPen(QPen(QColor(DARK), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(3.5, top + 8), QPointF(6, top + 10.5), QPointF(10.5, top + 5)])


class ToolSwitch(_PaintedCheck):
    """A tool's on/off switch, heading its card in Settings: a small toggle, then its name.
    Disabled, it keeps its look (the last tool on is locked, not off)."""

    _MARK_W = 28
    _BOLD = True
    _PT = LABEL_PT + 1

    def _text_color(self) -> str:
        return VALUE_COLOR

    def _paint_mark(self, p: QPainter, top: float) -> None:
        on = self.isChecked()
        p.setPen(QPen(QColor(ACCENT if on else EDGE), 1))
        p.setBrush(QColor(ACCENT if on else FIELD))
        p.drawRoundedRect(QRectF(0.5, top + 0.5, 27, 15), 7.5, 7.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(DARK if on else LABEL_COLOR))
        p.drawEllipse(QRectF(15 if on else 3, top + 3, 10, 10))


def setting_box(text: str, checked: bool, on_change: Callable[[bool], None]) -> QCheckBox:
    """A checkbox for the Settings window: each click applies at once."""
    box = _PaintedCheck(text)
    box.setChecked(checked)
    box.toggled.connect(on_change)
    return box


def tool_switch(text: str, checked: bool, on_change: Callable[[bool], None]) -> QCheckBox:
    """A tool's on/off switch for the Settings window: each click applies at once."""
    box = ToolSwitch(text)
    box.setChecked(checked)
    box.toggled.connect(on_change)
    return box


class FloatingWindow(QWidget):
    """One of MapleLens's own windows (History, Settings): over the game, leaving it the
    keyboard, as the box does. On the Mac, native_setup makes it a panel that does both.
    Closing it doesn't end the app."""

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setWindowFlag(Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        if sys.platform != "darwin":
            self.setWindowFlag(Qt.WindowStaysOnTopHint)
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus)

    def open(self) -> None:
        """Show it, or bring it forward if it's already open."""
        self.show()
        self.raise_()

    def showEvent(self, event):
        native_setup(self)
        super().showEvent(event)


OVERLAY = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus


def paint_box(widget: QWidget) -> None:
    """The box's look on a see-through window: dark fill, thin edge, round corners."""
    p = QPainter(widget)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(*BOX_EDGE))
    p.setBrush(QColor(*BOX_FILL))
    p.drawRoundedRect(QRectF(0.5, 0.5, widget.width() - 1, widget.height() - 1), 8, 8)


class Layer(QWidget):
    """Empty see-through window over the game's client area; tools draw on it later."""

    def __init__(self):
        super().__init__(None, OVERLAY | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def follow(self, rect: tuple[int, int, int, int]) -> None:
        left, top, w, h = rect  # physical pixels
        dpr = self.devicePixelRatioF()
        x, y = game_to_layer(left, top, dpr)
        pw, ph = game_to_layer(w, h, dpr)
        self.setGeometry(round(x), round(y), round(pw), round(ph))

    def showEvent(self, event):
        native_setup(self)
        super().showEvent(event)


class _Grip(QWidget):
    """The box's bottom-right corner: drag it sideways to make the tabs wider or narrower."""

    def __init__(self, box: "Box"):
        super().__init__(box)
        self._box = box
        self._from: tuple[float, int] | None = None  # the mouse's x and the width at the press
        self.setFixedSize(_GRIP, _GRIP)
        self.setCursor(Qt.SizeHorCursor)

    @property
    def dragging(self) -> bool:
        return self._from is not None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(LABEL_COLOR), 1.2))
        p.drawLine(QPointF(10, 2), QPointF(2, 10))  # inside the box's rounded corner
        p.drawLine(QPointF(10, 6), QPointF(6, 10))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._from = (event.globalPosition().x(), self._box.tab_w)

    def mouseMoveEvent(self, event):
        if self._from is not None:
            x, width = self._from
            self._box.set_tab_w(width + round(event.globalPosition().x() - x))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._from is not None:
            self._from = None
            self._box.save_size()


class _Touches(QObject):
    """Counts mouse presses on `box` or its children; never swallows an event.

    A child of the box, so Qt unhooks it from the application when the box goes.
    """

    def __init__(self, box: "Box"):
        super().__init__(box)
        self._box = box
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        press = event.type() == QEvent.MouseButtonPress
        if press and isinstance(obj, QWidget) and obj.window() is self._box:
            self._box.touches += 1
        return False


class Box(QWidget):
    """A small dark box with a tab strip; drag it, its spot is saved per game window."""

    def __init__(self, name: str, settings: dict, on_moved: Callable[[], None]):
        super().__init__(None, OVERLAY)
        self._name, self._settings, self._on_moved = name, settings, on_moved
        self._tab_w = fit_tab_w(settings.get("tab_width"))
        self._tab_w_listeners: list[Callable[[int], None]] = []
        self._origin: QPoint | None = None  # game client top-left, logical px
        self._game_w = 0
        self._drag_from: QPoint | None = None
        self.touches = 0  # mouse presses on the box or anything in it, so far
        self._footer: QWidget | None = None  # a line under every tab but its owner's
        self._footer_tab = -1
        self._footer_on = False
        self._count = _Touches(self)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._tab_buttons: list[QPushButton] = []
        self._tab_dots: list[QLabel] = []
        self._tab_shown: list[bool] = []  # a tab turned off keeps its index, only hidden
        self._dot_on: list[bool] = []  # the dot each tab was given, shown while the tab is
        self._strip_row = QWidget()  # holds the strip, so it hides as one
        self._strip = QHBoxLayout(self._strip_row)
        self._strip.setContentsMargins(0, 0, 0, 0)
        self._strip.setSpacing(14)
        self._strip.addStretch()
        self._build_pages()
        self._status = QLabel()
        self._status.setFont(QFont(FONT, 10))
        self._status.setStyleSheet(f"color: {VALUE_COLOR};")
        self._status.hide()
        self._status_text: str | None = None  # the last set_status, shown once About closes
        self._about_open = False
        self._about_url = ""
        self._build_about()
        self._menu = QMenu(self)
        self.attach_menu(self._menu)
        self._menu_button = mark_button(MENU_MARK, 10, self._open_menu)  # the tabs' size
        # the strip, the status line or About's title and close mark; then the menu button
        self._top = QHBoxLayout()
        self._top.setSpacing(10)
        for part in (self._strip_row, self._status, self._about_title):
            self._top.addWidget(part, 1)
        self._top.addWidget(self._about_close, 0, Qt.AlignVCenter)
        self._top.addWidget(self._menu_button, 0, Qt.AlignVCenter | Qt.AlignRight)
        self._build_notice()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSizeConstraint(QLayout.SetFixedSize)  # the box hugs the current tab
        layout.addLayout(self._top)
        layout.addWidget(self._pages)
        layout.addWidget(self._about)
        layout.addWidget(self._notice)
        self._grip = _Grip(self)  # not in the layout: it sits on the corner, resizeEvent keeps it

    @property
    def tab_w(self) -> int:
        return self._tab_w

    def set_tab_w(self, width: int) -> None:
        """Make the tabs `width` wide, within the limits; the box hugs them, so it follows."""
        width = fit_tab_w(width)
        if width == self._tab_w:
            return
        self._tab_w = width
        self._pages.setFixedWidth(width)
        self._about.setFixedWidth(width)
        for listener in self._tab_w_listeners:
            listener(width)

    def on_tab_w(self, listener: Callable[[int], None]) -> None:
        """Tell `listener` the tabs' width: now, and whenever it changes."""
        self._tab_w_listeners.append(listener)
        listener(self._tab_w)

    def save_size(self) -> None:
        """Remember the width, and the spot: a default spot hangs from the box's right edge."""
        self._settings["tab_width"] = self._tab_w
        self._save_spot()
        self._on_moved()

    def _build_pages(self) -> None:
        """The tabs' pages in a column, only the current one shown: hidden pages never size
        the box. (A QStackedWidget sizes wrapped text by its tallest page, hidden ones too.)
        """
        self._pages = QWidget()
        self._page_col = QVBoxLayout(self._pages)
        self._page_col.setContentsMargins(0, 0, 0, 0)
        # Every tab is TAB_W wide, but the column sizes from its pages' raw hints, which a
        # page's fixed width doesn't bound (wrapped text hints wider): fix the column instead.
        self._pages.setFixedWidth(self._tab_w)
        self._current = 0

    def _build_notice(self) -> None:
        self._notice = QWidget()  # a line of its own, so it shows with the tabs or the status
        self._notice_text = text_label("", NOTICE_PT, ACCENT)
        # a multiplication sign, the close mark
        self._notice_close = mark_button("\u00d7", LABEL_PT, self._dismiss_notice)
        self._on_dismiss: Callable[[], None] | None = None
        row = QHBoxLayout(self._notice)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._notice_text)
        row.addStretch()
        row.addWidget(self._notice_close)
        self._notice.hide()

    def _build_about(self) -> None:
        """The About view: a title and a close mark for the top row, and the panel under it."""
        self._about_title = text_label(ABOUT, 10, VALUE_COLOR, bold=True)  # the tabs' size
        self._about_close = mark_button("\u00d7", 10, self.close_about)
        self._about = QWidget()
        self._about.setFixedWidth(self._tab_w)  # the tabs' width: opening About keeps the box's
        self._about_version = text_label("", 10, VALUE_COLOR)
        self._about_updates = text_label("", 10, VALUE_COLOR)
        self._about_link = mark_button("GitHub page \u2197", 10, self._open_link, color=ACCENT)
        column = QVBoxLayout(self._about)
        column.setContentsMargins(0, 6, 0, 0)
        column.setSpacing(2)
        for name, value in (("Version", self._about_version), ("Updates", self._about_updates)):
            column.addWidget(text_label(name, LABEL_PT, LABEL_COLOR))
            column.addWidget(value)
        column.addSpacing(4)
        column.addWidget(self._about_link, 0, Qt.AlignLeft)
        for part in (self._about_title, self._about_close, self._about):
            part.hide()

    def add_tab(self, title: str, widget: QWidget) -> int:
        """Add a tab; the first one added is shown. Returns its index."""
        i = self._page_col.count()
        self._page_col.addWidget(widget)
        button = QPushButton(title)
        button.setFlat(True)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.setFont(QFont(FONT, 10, QFont.Bold))
        button.clicked.connect(lambda: self.select(i))
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background: {ACCENT}; border-radius: 3px;")
        dot.hide()
        self._tab_buttons.append(button)
        self._tab_dots.append(dot)
        self._tab_shown.append(True)
        self._dot_on.append(False)
        at = self._strip.count() - 1  # before the trailing stretch
        self._strip.insertWidget(at, button)
        self._strip.insertWidget(at + 1, dot, 0, Qt.AlignVCenter)
        self.select(self._current)
        return i

    @property
    def current(self) -> int:
        return self._current

    def select(self, index: int) -> None:
        """Show tab `index`; a hidden tab can't be shown, and the box stays where it is."""
        if not self._tab_shown[index]:
            return
        self._current = index
        for j, b in enumerate(self._tab_buttons):
            color, line = (VALUE_COLOR, ACCENT) if j == index else (LABEL_COLOR, "transparent")
            b.setStyleSheet(
                f"QPushButton {{ color: {color}; border: 0; border-bottom: 2px solid {line};"
                " padding: 2px 0; }"
            )
        for j in range(self._page_col.count()):
            self._page_col.itemAt(j).widget().setVisible(j == index)
        self._show_footer()

    def add_footer(self, widget: QWidget, tab: int) -> None:
        """A line under the pages, kept hidden while tab `tab` (its owner's) is current."""
        layout = self.layout()
        layout.insertWidget(layout.indexOf(self._pages) + 1, widget)
        self._footer, self._footer_tab = widget, tab
        self._show_footer()

    def set_footer_shown(self, on: bool) -> None:
        self._footer_on = on
        self._show_footer()

    def _show_footer(self) -> None:
        if self._footer is not None:
            tabs = not self._about_open and self._status_text is None
            owner = self._footer_tab
            mine = 0 <= owner < len(self._tab_shown) and not self._tab_shown[owner]
            on = self._footer_on and not mine  # its tab turned off: the line goes with it
            self._footer.setVisible(on and tabs and self._current != owner)

    def set_status(self, text: str | None) -> None:
        """Show `text` in place of the tabs; None brings the tabs back.

        The menu button stays in both: level with the tab titles, or with the status's
        first line. While About is open, the text is kept for when it closes.
        """
        self._status_text = text
        self._show_current()

    @property
    def about_open(self) -> bool:
        return self._about_open

    def show_about(self, version: str, updates: str, url: str, *, accent: bool = False) -> None:
        """Show About in place of the tabs or the status line, until its close mark closes it.

        `updates` is a line about updates, in the accent colour if `accent`; `url` is what
        the "GitHub page" link opens. The box knows nothing more about either.
        """
        self._about_version.setText(version)
        self.set_about_updates(updates, accent=accent)
        self._about_url = url
        self._about_open = True
        self._show_current()

    def set_about_updates(self, text: str, *, accent: bool = False) -> None:
        self._about_updates.setText(text)
        self._about_updates.setStyleSheet(f"color: {ACCENT if accent else VALUE_COLOR};")

    def close_about(self) -> None:
        """Back to the tabs, or the status line if one was set meanwhile."""
        self._about_open = False
        self._show_current()

    def _open_link(self) -> None:
        QDesktopServices.openUrl(QUrl(self._about_url))  # the player's own click

    def _show_current(self) -> None:
        """About while it's open; else the status line if one is set, else the tabs."""
        about, text = self._about_open, self._status_text
        for part in (self._about_title, self._about_close, self._about):
            part.setVisible(about)
        status = not about and text is not None
        self._status.setText(text or "")
        self._status.setVisible(status)
        self._strip_row.setVisible(not about and text is None)
        self._pages.setVisible(not about and text is None)
        self._show_footer()
        self._grip.setVisible(not status)  # the status line sets its own width
        row = Qt.AlignTop if status else Qt.AlignVCenter
        self._top.setAlignment(self._menu_button, row | Qt.AlignRight)

    def set_notice(self, text: str | None, on_dismiss: Callable[[], None] | None = None) -> None:
        """Show `text` on a line under the pages; None hides it.

        The line's close mark hides it and calls `on_dismiss`.
        """
        self._notice_text.setText(text or "")
        self._on_dismiss = on_dismiss
        self._notice.setVisible(text is not None)

    def _dismiss_notice(self) -> None:
        on_dismiss, self._on_dismiss = self._on_dismiss, None
        self._notice.hide()
        if on_dismiss:
            on_dismiss()

    def set_tab_dot(self, index: int, on: bool) -> None:
        self._dot_on[index] = on
        self._tab_dots[index].setVisible(on and self._tab_shown[index])

    def set_tab_shown(self, index: int, on: bool) -> None:
        """Hide tab `index` (its button, dot and page), or show it again. The other tabs keep
        their indexes. Hiding the open tab shows the first one still shown."""
        self._tab_shown[index] = on
        self._tab_buttons[index].setVisible(on)
        self._tab_dots[index].setVisible(on and self._dot_on[index])
        if not on and self._current == index:
            first = next((i for i, shown in enumerate(self._tab_shown) if shown), None)
            if first is not None:
                self.select(first)
        self._show_footer()

    def allow_typing(self, on: bool) -> None:
        """Let the box take keyboard focus (only while a text field needs it).

        A box the player hid stays hidden.
        """
        shown = self.isVisible()
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, not on)
        if shown:
            self.show()  # changing a window flag hides a shown window
        if not on and sys.platform == "darwin":
            from maplelens import overlay_mac

            overlay_mac.release_keyboard()

    def attach_menu(self, menu: QMenu) -> None:
        """Make `menu` list the box's menu items, read again each time it opens.

        The menu button's menu and the tray's both use it, so neither keeps a list of its
        own. The items stay the box's, alive however often the menu opens.
        """
        menu.aboutToShow.connect(lambda: self._fill(menu))

    def _fill(self, menu: QMenu) -> None:
        # Not menu.clear(): PySide hands the cleared actions to Python, which then deletes
        # the box's own (nothing in Python holds them).
        for action in menu.actions():
            menu.removeAction(action)
        menu.addActions(self.actions())

    def _open_menu(self) -> None:
        """The menu, just under the button, with their right edges lined up."""
        self._fill(self._menu)  # now, so the width is known before it opens
        corner = self._menu_button.mapToGlobal(self._menu_button.rect().bottomRight())
        self._menu.popup(corner - QPoint(self._menu.sizeHint().width() - 1, -1))

    def add_menu_item(
        self, label: str, callback: Callable[[], None], *, at: int | None = None
    ) -> QAction:
        """An item in the box's menu; returns it, so its label can change.

        At the end, or before the item now at index `at` (as list.insert: -1 is before
        the last one).
        """
        action = QAction(label, self)
        action.triggered.connect(callback)
        self._insert(action, at)
        return action

    def add_toggle(
        self, label: str, checked: bool, on_change: Callable[[bool], None], *, at: int | None = None
    ) -> QAction:
        """A checkable item in the box's menu; `on_change` gets its new state."""
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(checked)
        action.toggled.connect(on_change)
        self._insert(action, at)
        return action

    def _insert(self, action: QAction, at: int | None) -> None:
        actions = self.actions()
        self.insertAction(actions[at] if at is not None and actions else None, action)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

    def add_submenu(
        self,
        label: str,
        choices: Callable[[], list[str]],
        on_pick: Callable[[str], None],
        *,
        at: int | None = None,
    ) -> QAction:
        """A submenu in the box's menu listing `choices()`, read again each time it opens.

        Placed as add_menu_item places an item; returns its action, so it can change.
        """
        menu = QMenu(label, self)

        def fill() -> None:
            menu.clear()
            for text in choices():
                menu.addAction(text).triggered.connect(lambda _=False, t=text: on_pick(t))

        menu.aboutToShow.connect(fill)
        self._insert(menu.menuAction(), at)
        return menu.menuAction()

    def place(self, game_rect: tuple[int, int, int, int]) -> None:
        if self._drag_from is not None or self._grip.dragging:
            return  # don't fight the user's drag
        left, top, w, _ = game_rect  # physical pixels
        dpr = self.devicePixelRatioF()
        x, y = game_to_layer(left, top, dpr)
        self._origin = QPoint(round(x), round(y))
        self._game_w = round(w / dpr)
        saved = self._settings.get("boxes", {}).get(self._name)
        if saved:
            target = self._origin + QPoint(*saved)
        else:
            target = self._origin + QPoint(self._game_w - self.width() - _INSET, _INSET)
        if target != self.pos():
            self.move(target)

    def showEvent(self, event):
        native_setup(self)
        super().showEvent(event)

    def resizeEvent(self, event):
        self._grip.move(self.width() - _GRIP, self.height() - _GRIP)
        super().resizeEvent(event)

    def paintEvent(self, _event):
        paint_box(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._drag_from is None:
            return
        self._drag_from = None
        if self._origin is not None:
            self._save_spot()
            self._on_moved()

    def _save_spot(self) -> None:
        if self._origin is not None:
            off = self.pos() - self._origin
            self._settings.setdefault("boxes", {})[self._name] = [off.x(), off.y()]
