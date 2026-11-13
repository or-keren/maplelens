"""The path arrow tool: a Path tab to pick a destination, and an arrow over the character."""

import math
from collections.abc import Callable
from html import escape

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from maplelens.overlay import (
    ACCENT,
    DARK,
    FIELD_STYLE,
    LABEL_COLOR,
    LABEL_PT,
    TAB_W,
    VALUE_COLOR,
    InfoLine,
    Layer,
    game_to_layer,
    primary_button,
    secondary_button,
    text_label,
)
from maplelens.readers import Reading, glyphs
from maplelens.tools.path_arrow.camera import by_size, can_place, fits, player_world, to_screen
from maplelens.tools.path_arrow.maps import MapInfo, find, load, picture, search
from maplelens.tools.path_arrow.route import Trip, plan

# Normalized px from the feet (the dot's world spot) up to the arrow's centre: just above
# the head, under the 768-high frame the camera model works in.
ARROW_DY = 100
ARROW_SIZE = 36  # logical px, the arrow's square
# Arrived once the NPC's spot is on screen this many normalized px inside the side edges:
# the camera can sit ~128 px off the model's sideways (see to_screen).
SEEN_MARGIN = 130
ARRIVED_S = 5.0  # "Arrived at …" stays this long
UNREAD_S = 3.0  # map name unreadable this long before asking for the minimap
OPEN = "Open your minimap to see the arrow"
HIDDEN = "Hidden portal: stand on it and press ↑"
ON_MAP = "{} is on this map"
NOT_LISTED = "Not in the map list yet, so no route from here"
ACTIONS = (OPEN, HIDDEN)  # yellow: the player can act on these now; the rest are information
MATCH_ROWS = 3  # visible matches; the list scrolls for the rest
_DONE, _AHEAD, _NUM = "#6f7d93", "#c9d3e3", "#7b8aa3"  # mockup 3's route list
_STYLE = FIELD_STYLE + f"QCheckBox {{ color: {VALUE_COLOR}; }}"


class _Arrow(QWidget):
    """A plain arrow on the layer, pointing `angle` degrees (screen axes, y down)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(ARROW_SIZE, ARROW_SIZE)
        self.angle = 0.0
        self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(ARROW_SIZE / 2, ARROW_SIZE / 2)
        p.rotate(self.angle)
        s = ARROW_SIZE / 2 - 2
        tip = [(s, 0), (0, -0.8 * s), (0, -0.35 * s), (-s, -0.35 * s)]
        tip += [(-s, 0.35 * s), (0, 0.35 * s), (0, 0.8 * s)]
        p.setPen(QPen(QColor(DARK), 2))
        p.setBrush(QColor(ACCENT))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in tip]))


class _Search(QLineEdit):
    """The one field that takes keyboard focus, and only while you type in it."""

    def __init__(self, typing: Callable[[bool], None]):
        super().__init__()
        self._typing = typing

    def mousePressEvent(self, event):
        self._typing(True)
        self.activateWindow()  # MapleLens's own box, never the game
        self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._typing(False)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._typing(False)
        super().focusOutEvent(event)


class PathArrowTool:
    def __init__(
        self,
        settings: dict,
        on_settings_changed: Callable[[], None],
        layer: Layer,
        allow_typing: Callable[[bool], None],
        maps: dict[str, MapInfo] | None = None,
    ):
        self.maps = load() if maps is None else maps
        self._settings, self._changed = settings, on_settings_changed
        self._layer, self._allow_typing = layer, allow_typing
        self.title = "Path"
        self.trip: Trip | None = None
        self._here: MapInfo | None = None  # the confirmed map, None if not in the data
        self._title: str | None = None  # the confirmed map's read title
        self._last: str | None = None  # the previous reading's title
        self._last_sized: MapInfo | None = None  # and the map its minimap size picked
        self._unread_since: float | None = None
        self._arrived: tuple[str, float] | None = None  # (header text, when)
        self._label: str | None = None  # the NPC the trip leads to
        self._note = ""  # why nothing started
        self._typing = False
        self._r: Reading | None = None
        self._rect: tuple | None = None
        self._now = 0.0
        self.arrow = _Arrow(layer)
        self._tab_w = TAB_W
        self.tab = self._build_tab(settings["path_taxi"])
        self._render()

    def set_tab_w(self, width: int) -> None:
        self._tab_w = width
        self.tab.setFixedWidth(width)
        self._render()  # the names are cut to the width

    def _build_tab(self, taxi: bool) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(_STYLE)
        tab.setFixedWidth(self._tab_w)  # long names elide instead of widening the box
        self._header = text_label("", LABEL_PT, LABEL_COLOR)
        self._message = text_label("", LABEL_PT, ACCENT)
        self._message.setWordWrap(True)
        self._info = InfoLine()
        self._search = _Search(self._set_typing)
        self._search.textChanged.connect(self._on_text)
        self._matches = QListWidget()
        self._matches.setFocusPolicy(Qt.NoFocus)
        self._matches.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # names elide
        self._matches.setTextElideMode(Qt.ElideMiddle)  # keeps a repeated name's street
        # Its own 256 px width hint would widen the box past the tab (the box's page stack
        # sizes from raw hints, ignoring the tab's fixed width).
        self._matches.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._matches.currentItemChanged.connect(lambda *_: self._render())
        self._matches.itemClicked.connect(self._pick)
        self._matches.hide()
        self._taxi = QCheckBox("Use taxi")
        self._taxi.setFocusPolicy(Qt.NoFocus)
        self._taxi.setChecked(taxi)
        self._start = primary_button("Start", self._on_start)
        self._route_list = text_label("", LABEL_PT + 1, _AHEAD)
        self._route_list.setTextFormat(Qt.RichText)
        self._stop = secondary_button("Stop", self.stop)

        self._choose, self._running = QWidget(), QWidget()
        for page, widgets in [
            (self._choose, [self._search, self._matches, self._taxi, self._start]),
            (self._running, [self._route_list, self._stop]),
        ]:
            col = QVBoxLayout(page)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(6)
            for w in widgets:
                col.addWidget(w)
        col = QVBoxLayout(tab)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)
        for w in (self._header, self._message, self._info, self._choose, self._running):
            col.addWidget(w)
        return tab

    @property
    def running(self) -> bool:
        return self.trip is not None

    def update(self, r: Reading | None, game_rect: tuple | None, now: float) -> None:
        self._r, self._rect, self._now = r, game_rect, now
        # No reading at all counts as an unreadable map name: the same 3 s clock.
        self._track(r.map_name if r else None, r.minimap if r else None, now)
        if self.trip and self._here:
            self._settle()
        self._render()

    def _unread(self) -> bool:
        """No map name for UNREAD_S: where you are is no longer known."""
        return self._unread_since is not None and self._now - self._unread_since >= UNREAD_S

    def _track(self, name: str | None, view, now: float) -> None:
        """Act on a map change only once the same title is read twice in a row.

        Same-title maps are told apart by the minimap's size first, so walking between
        two of them (Maple Road / Mushroom Town) still counts as a change.
        """
        sized = by_size(self.maps, name, view) if name and view else None
        if name is None:
            if self._unread_since is None:
                self._unread_since = now
        else:
            self._unread_since = None
            twice = sized if sized == self._last_sized else None  # same size match twice
            if (name == self._last and name != self._title) or (twice and twice != self._here):
                previous = self._here.id if self._here else None
                self._title, self._here = name, twice or find(self.maps, name, previous)
                self._note = ""  # a new place: an old "No route" no longer holds
                if self._here and self.trip:
                    self.trip.on_map(self._here.id)
        self._last, self._last_sized = name, sized

    def _settle(self) -> None:
        """End the trip on arrival (at the NPC, if any), or when no route is left."""
        trip, goal = self.trip, self.maps[self.trip.goal].name
        line = None
        if trip.steps is None:
            self._note = f"No route from here to {goal}"
            self.trip = None
        elif trip.arrived:
            name = self._label or goal
            world, r, here = self._world(), self._r, self._here
            if trip.at is None or self._seen(trip.at, world):
                line = f"Arrived at {name}"
            elif here.minimap is None or (
                r and r.minimap and not can_place(r.minimap, here, picture(here.id))
            ):
                line = ON_MAP.format(name)  # no arrow can lead there
            if line:
                self._arrived = (line, self._now)
                self.trip = None

    def _seen(self, at: tuple[int, int], world: tuple[float, float] | None) -> bool:
        """The NPC's spot is well inside the game's view."""
        if world is None or self._rect is None:
            return False
        _, _, w, h = self._rect
        view = (w * glyphs.BASE_H / h, glyphs.BASE_H)
        x, y = to_screen(at, world, self._here.minimap, view)
        # The spot is the NPC's feet, so only they need to be on screen vertically.
        return SEEN_MARGIN <= x <= view[0] - SEEN_MARGIN and 0 <= y <= view[1]

    def _set_typing(self, on: bool) -> None:
        if on == self._typing:
            return
        self._typing = on
        if not on:
            self._search.clearFocus()
        self._allow_typing(on)

    def _on_text(self, text: str) -> None:
        self._note = ""
        self._matches.clear()
        hits = search(self.maps, text)
        names = [m.name for m in hits]
        for m in hits:
            item = QListWidgetItem(f"{m.name} · {m.street}" if names.count(m.name) > 1 else m.name)
            item.setData(Qt.UserRole, m.id)
            item.setToolTip(m.title)
            self._matches.addItem(item)
        n = self._matches.count()
        self._matches.setVisible(n > 0)
        if n:
            rows = self._matches.sizeHintForRow(0) * min(n, MATCH_ROWS)
            self._matches.setFixedHeight(rows + 2 * self._matches.frameWidth())
            self._matches.setCurrentRow(0)
        self._render()

    def _pick(self, item: QListWidgetItem) -> None:
        """A clicked match fills the field and the list closes on it; Start goes there."""
        self._search.blockSignals(True)  # re-searching the name could make another row current
        self._search.setText(item.text())
        self._search.blockSignals(False)
        self._matches.setCurrentItem(item)
        self._matches.hide()
        self._set_typing(False)
        self._render()

    def go(self, map_id: str, at: tuple[int, int] | None = None, label: str | None = None) -> None:
        """Fill the field with that map and start, as picking it and pressing Start do.

        With `at`, the trip goes on to that spot on the map; `label` names it.
        """
        m = self.maps[map_id]
        self._search.setText(m.name)  # fills the match list
        item = next(
            (
                i
                for i in (self._matches.item(n) for n in range(self._matches.count()))
                if i.data(Qt.UserRole) == map_id
            ),
            None,
        )
        if item is None:
            item = QListWidgetItem(m.name)
            item.setData(Qt.UserRole, map_id)
            self._matches.addItem(item)
        self._pick(item)
        self._begin(at, label)

    def _on_start(self) -> None:
        self._begin(None, None)

    def _begin(self, at, label) -> None:
        item = self._matches.currentItem()
        self._set_typing(False)
        if self._here is None or self._unread() or item is None:
            return
        taxi = self._taxi.isChecked()
        if self._settings.get("path_taxi") != taxi:
            self._settings["path_taxi"] = taxi
            self._changed()
        self._note = ""
        self._label = label
        self.trip = Trip(self.maps, self._here.id, item.data(Qt.UserRole), taxi, at)
        self._settle()
        self._render()

    def stop(self) -> None:
        self.trip = None
        self._render()

    def heading(self) -> tuple[str, tuple[int, int] | None, int] | None:
        """(goal map, NPC spot, maps left) while a trip runs."""
        t = self.trip
        return (t.goal, t.at, len(t.steps) - 1 - t.index) if t else None

    def hops(self, map_id: str) -> int | None:
        """Maps to cross from the confirmed map to `map_id`, None if unknown or no route."""
        if self._here is None:
            return None
        steps = plan(self.maps, self._here.id, map_id, self._taxi.isChecked())
        return None if steps is None else len(steps) - 1

    def _render(self) -> None:
        if self._arrived and self._now - self._arrived[1] >= ARRIVED_S:
            self._arrived = None
        if self._arrived:
            head = self._fit("{}", self._arrived[0])
        elif self.trip:
            goal = self._label or self.maps[self.trip.goal].name
            n = f"{self.trip.index + 1} of {len(self.trip.steps)}"
            head = self._fit("To {} · " + n, goal)
            self._route_list.setText(self._route_html())
        elif self._here and not self._unread():
            head = self._fit("From: {} (where you are)", self._here.name)
        elif self._title and not self._unread():  # read, but not in the map data
            head = self._fit("From: {}", self._title.rsplit(" / ", 1)[-1])
        else:
            head = "From: (can't read your map yet)"
        self._header.setText(head)
        self._choose.setVisible(self.trip is None and self._arrived is None)
        self._running.setVisible(self.trip is not None)
        world = self._world()
        hint = HIDDEN if self.trip and self.trip.hidden_next(world) else ""
        texts = [t for t in (self._why(world), hint) if t]
        act = "\n".join(t for t in texts if t in ACTIONS)
        info = "\n".join(t for t in texts if t not in ACTIONS)
        self._message.setText(act)
        self._message.setVisible(bool(act))
        self._info.setText(info)
        self._info.setVisible(bool(info))
        known = self._here is not None and not self._unread()
        self._start.setEnabled(known and self._matches.currentItem() is not None)
        self._place_arrow(world)

    def _world(self) -> tuple[float, float] | None:
        """The player's world position, from a reading of the confirmed map only."""
        r, here = self._r, self._here
        # Never aim with another map's minimap, so the title must be the confirmed one.
        if self.trip and here and r and r.minimap and r.map_name == self._title:
            return player_world(r.minimap, here, picture(here.id))
        return None

    def _fit(self, template: str, name: str) -> str:
        """The header line, `name` elided so the line fits the tab."""
        fm = self._header.fontMetrics()
        room = self._tab_w - fm.horizontalAdvance(template.format(""))
        return template.format(fm.elidedText(name, Qt.ElideRight, max(room, 0)))

    def _route_html(self) -> str:
        bold = QFont(self._route_list.font())
        bold.setBold(True)  # the widest a row gets
        fm = QFontMetrics(bold)
        rows = []
        for i, s in enumerate(self.trip.steps):
            room = self._tab_w - fm.horizontalAdvance("00  " + (" taxi" if s.cab else ""))
            # Cut in the middle: neighbours often share a long start (The Swamp of Despair I, II)
            name = escape(fm.elidedText(self.maps[s.map_id].name, Qt.ElideMiddle, room))
            if i < self.trip.index:
                row = f'<span style="color:{_DONE}"><s>{i + 1}&nbsp;&nbsp;{name}</s></span>'
            elif i == self.trip.index:
                row = (
                    f'<span style="color:{ACCENT}">▸</span>&nbsp;&nbsp;'
                    f'<b style="color:{VALUE_COLOR}">{name}</b>'
                )
            else:
                row = f'<span style="color:{_NUM}">{i + 1}</span>&nbsp;&nbsp;{name}'
            if s.cab:
                row += f' <span style="color:{ACCENT}">taxi</span>'
            rows.append(row)
        return "<br>".join(rows)

    def _why(self, world: tuple[float, float] | None) -> str:
        """One line on why there's no arrow, or ""."""
        r, here = self._r, self._here
        if self._title is not None and here is None and not self._unread():
            return NOT_LISTED
        if self.trip is None:
            return "" if self._arrived else self._note
        if self._unread():
            return OPEN
        if here is None or r is None:
            return ""
        if here.minimap is None:
            return "No minimap on this map"
        if r.map_name is not None and r.minimap is None:
            return OPEN
        if r.minimap is not None and not can_place(r.minimap, here, picture(here.id)):
            return "No arrow on this map yet"
        on_map = world is None and r.minimap and r.map_name == self._title
        if on_map and not fits(r.minimap, here.minimap):  # too few NPC markers in the window
            return "No arrow on this part of the map yet"
        return ""  # a map that fits may still miss a frame: the arrow just hides

    def _place_arrow(self, world: tuple[float, float] | None) -> None:
        here, rect = self._here, self._rect
        target = None if world is None or rect is None else self.trip.target(world)
        if target is None:
            self.arrow.hide()
            return
        _, _, w, h = rect  # game client, physical px
        k = h / glyphs.BASE_H  # normalized px -> client px
        x, y = to_screen(world, world, here.minimap, (w / k, glyphs.BASE_H))
        x, y = game_to_layer(x * k, (y - ARROW_DY) * k, self._layer.devicePixelRatioF())
        self.arrow.angle = math.degrees(math.atan2(target[1] - world[1], target[0] - world[0]))
        self.arrow.move(round(x - ARROW_SIZE / 2), round(y - ARROW_SIZE / 2))
        self.arrow.show()
        self.arrow.update()
