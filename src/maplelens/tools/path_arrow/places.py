"""The Path tab's picture rows: a match or a place, its 28 px picture, a bold name, a grey line."""

from functools import cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from maplelens.gamedata import GameData, Match, Source, SpotData
from maplelens.overlay import LABEL_COLOR, LABEL_PT, VALUE_COLOR, text_label
from maplelens.tools.path_arrow.maps import MapInfo

PIC = 28  # a row's picture square
_GAP, _PAD = 6, 4  # between the picture and the text; the row's side padding
DIM = "#6f7d93"  # an unreachable place's line
WHERE = {"monster": "Where it spawns", "item": "Where to get it", "npc": "Where to find them"}


@cache
def _pixmap(path: Path | None, crop: bool) -> QPixmap:
    """The picture fit to PIC; `crop` takes a map picture's centre square first."""
    pix = QPixmap(str(path)) if path else QPixmap()
    if pix.isNull():
        return pix
    if crop:
        s = min(pix.width(), pix.height())
        pix = pix.copy((pix.width() - s) // 2, (pix.height() - s) // 2, s, s)
    if crop or pix.width() > PIC or pix.height() > PIC:
        pix = pix.scaled(PIC, PIC, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pix


class PictureRow(QWidget):
    """A list row; its labels are cut to `fit`'s width, the name in the middle (a repeated
    map name keeps its street)."""

    def __init__(self, name: str, line: str, pixmap: QPixmap, width: int, dim: bool = False):
        super().__init__()
        self.name, self.line, self.dim = name, line, dim
        row = QHBoxLayout(self)
        row.setContentsMargins(_PAD, 3, _PAD, 3)
        row.setSpacing(_GAP)
        self.picture = QLabel()
        self.picture.setFixedSize(PIC, PIC)  # empty without a picture: the text stays in line
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setPixmap(pixmap)
        row.addWidget(self.picture)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name_label = text_label("", LABEL_PT, LABEL_COLOR if dim else VALUE_COLOR, bold=True)
        self.line_label = text_label("", LABEL_PT, DIM if dim else LABEL_COLOR)
        col.addWidget(self.name_label)
        col.addWidget(self.line_label)
        row.addLayout(col, 1)
        self.fit(width)

    def fit(self, width: int) -> None:
        room = max(width - PIC - _GAP - 2 * _PAD, 0)
        for label, text, mode in (
            (self.name_label, self.name, Qt.ElideMiddle),
            (self.line_label, self.line, Qt.ElideRight),
        ):
            label.setText(QFontMetrics(label.font()).elidedText(text, mode, room))


def match_row(game: GameData, spots: SpotData, m: Match, name: str, width: int) -> PictureRow:
    if m.kind == "monster":
        path = next(filter(None, (spots.icon(str(i)) for i in m.ids)), None)
    elif m.kind == "item":
        path = game.item_icon(m.ids[0])
    elif m.kind == "npc":
        path = game.npc_icon(m.ids[0])
    else:
        path = spots.picture(m.ids[0])
    return PictureRow(name, m.line, _pixmap(path, m.kind == "map"), width)


def _away(hops: int | None, known: bool) -> str | None:
    """None while the position is unknown."""
    if not known:
        return None
    return "no route" if hops is None else "here" if hops == 0 else f"{hops} away"


def place_row(  # noqa: PLR0913, PLR0917 - what a place's row is made of
    game: GameData,
    spots: SpotData,
    maps: dict[str, MapInfo],
    kind: str,
    s: Source,
    known: bool,
    width: int,
) -> PictureRow:
    """A place of a picked monster, item or NPC (`kind`); `known`: where you are is."""
    away, where = _away(s.hops, known), maps[s.map_id].name
    if s.shop:
        name, parts, path = game.npcs[s.via].name, [away, where], game.npc_icon(s.via)
    elif kind == "item":
        rate = "rate unknown" if s.rate is None else f"~{s.rate:g}%"
        more = f"+{s.others} more" if s.others else None
        parts = [f"{game.mobs[s.via].name} \N{MULTIPLICATION SIGN}{s.count}", rate, away, more]
        name, path = where, spots.icon(str(s.via))
    else:
        spawns = f"{s.count} spawn{'s' * (s.count != 1)}" if kind == "monster" else None
        name, parts, path = where, [spawns, away], spots.picture(s.map_id)
    line = " · ".join(p for p in parts if p)
    crop = not s.shop and kind != "item"
    return PictureRow(name, line, _pixmap(path, crop), width, dim=known and s.hops is None)
