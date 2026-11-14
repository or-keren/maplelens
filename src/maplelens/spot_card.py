"""The hover card beside the box: a map or NPC's picture, its monsters, and a few lines."""

from math import sqrt
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from shiboken6 import delete

from maplelens.gamedata import Card, SpotData
from maplelens.overlay import (
    FIELD,
    LABEL_COLOR,
    LABEL_PT,
    OVERLAY,
    VALUE_COLOR,
    VALUE_PT,
    native_setup,
    paint_box,
    text_label,
)

# The card's width, the picture's most height, and its gap from the box.
CARD_W, PICTURE_H, GAP = 300, 240, 8
_MARGIN, ICON, ICON_FIT, DOT_R, DOT_EDGE = 10, 48, 44, 4, "#141414"


def card_spot(box: QRect, row_top: int, size: QSize, screen: QRect) -> QPoint:
    """Where the card goes: left of the box, level with the row; right when the left has no
    room; then up or down to stay on the screen."""
    x = box.x() - GAP - size.width()
    if x < screen.x():
        x = box.x() + box.width() + GAP
    y = max(min(row_top, screen.y() + screen.height() - size.height()), screen.y())
    return QPoint(x, y)


def _words(text: str, pt: int, color: str, *, bold: bool = False) -> QLabel:
    label = text_label(text, pt, color, bold=bold)
    label.setWordWrap(True)
    return label


class _Art(QWidget):
    """A picture on a dark field, drawn into `where`, with dots on it: (centre, colour)."""

    def __init__(self, size: QSize, pixmap: QPixmap, where: QRectF, dots: list):
        super().__init__()
        self.setFixedSize(size)
        self._pixmap, self._where, self._dots = pixmap, where, dots

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(FIELD))
        p.drawPixmap(self._where, self._pixmap, QRectF(self._pixmap.rect()))  # a null one: nothing
        p.setPen(QPen(QColor(DOT_EDGE), 1))
        # Smaller on a busy map, so the platforms still show between the dots.
        r = max(2.0, min(DOT_R, DOT_R * sqrt(30 / len(self._dots)))) if self._dots else DOT_R
        for centre, colour in self._dots:
            p.setBrush(QColor(colour))
            p.drawEllipse(centre, r, r)


class SpotCard(QWidget):
    """The hover card beside the box: a map with its spawn spots marked, or an NPC, and its
    monsters. Never takes the game's focus or a click."""

    def __init__(self):
        # Clicks go through to the game: the attribute alone still lets the OS send them here.
        super().__init__(None, OVERLAY | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setFixedWidth(CARD_W)
        self._pixmaps: dict[Path, QPixmap] = {}
        self._title = QLabel()
        self._body = QWidget()
        col = QVBoxLayout(self)
        col.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        col.addWidget(self._body)

    def title(self) -> str:
        return self._title.text()

    def _pixmap(self, path: Path) -> QPixmap:
        if path not in self._pixmaps:
            self._pixmaps[path] = QPixmap(str(path))
        return self._pixmaps[path]

    def fill(self, card: Card, spots: SpotData) -> None:
        old, self._body = self._body, QWidget()
        col = QVBoxLayout(self._body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        self._title = _words(card.title, VALUE_PT, VALUE_COLOR, bold=True)
        head = QVBoxLayout()
        head.setSpacing(0)
        head.addWidget(self._title)
        if card.street:
            head.addWidget(_words(card.street, LABEL_PT, LABEL_COLOR))
        col.addLayout(head)
        if card.picture:
            w, h = card.size
            k = min((CARD_W - 2 * _MARGIN) / w, PICTURE_H / h, 1)  # never blown up
            size = QSize(round(w * k), round(h * k))
            dots = [(QPointF(x * k, y * k), c) for x, y, c in card.dots]
            picture = self._pixmap(card.picture)
            col.addWidget(_Art(size, picture, QRectF(QPointF(), size), dots), 0, Qt.AlignHCenter)
        for mob in card.mobs:
            path = spots.icon(mob.id)
            icon = self._pixmap(path) if path else QPixmap()
            where = QRectF(QPointF(), icon.size().scaled(ICON_FIT, ICON_FIT, Qt.KeepAspectRatio))
            where.moveCenter(QPointF(ICON / 2, ICON / 2))
            corner = QPointF(ICON - DOT_R - 3, ICON - DOT_R - 3)
            line = QHBoxLayout()
            line.setSpacing(8)
            art = _Art(QSize(ICON, ICON), icon, where, [(corner, mob.colour)])
            line.addWidget(art, 0, Qt.AlignTop)
            words = QVBoxLayout()
            words.setSpacing(0)
            words.addWidget(_words(mob.name, LABEL_PT, VALUE_COLOR, bold=True))
            words.addWidget(_words(mob.stats, LABEL_PT, LABEL_COLOR))
            words.addWidget(_words(mob.spots, LABEL_PT, LABEL_COLOR))
            line.addLayout(words, 1)
            col.addLayout(line)
        for text in (card.cap, *card.lines):
            if text:
                col.addWidget(_words(text, LABEL_PT, LABEL_COLOR))
        self.layout().replaceWidget(old, self._body)
        delete(old)
        self._body.show()  # now, not on the next pass: the layout skips a hidden widget
        self.resize(CARD_W, self.heightForWidth(CARD_W))  # as tall as the wrapped text

    def put(self, row: QWidget) -> None:
        box = row.window()
        top = row.mapToGlobal(QPoint(0, 0)).y()
        self.move(
            card_spot(box.frameGeometry(), top, self.size(), box.screen().availableGeometry())
        )

    def showEvent(self, event):
        native_setup(self)
        super().showEvent(event)

    def paintEvent(self, _event):
        paint_box(self)
