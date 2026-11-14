"""The path arrow tool: a Path tab to pick a destination, and an arrow over the character."""

import math
from collections.abc import Callable
from html import escape

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from maplelens.gamedata import (
    Card,
    GameData,
    Match,
    Source,
    SpotData,
    item_places,
    load_game,
    load_spots,
    map_card,
    mob_places,
    npc_card,
    npc_places,
    search,
)
from maplelens.overlay import (
    ACCENT,
    DARK,
    EDGE,
    FIELD_STYLE,
    LABEL_COLOR,
    LABEL_PT,
    TAB_W,
    VALUE_COLOR,
    InfoLine,
    Layer,
    game_to_layer,
    mark_button,
    primary_button,
    secondary_button,
    text_label,
)
from maplelens.readers import Reading, glyphs
from maplelens.spot_card import SpotCard
from maplelens.tools.path_arrow.camera import by_size, can_place, fits, player_world, to_screen
from maplelens.tools.path_arrow.maps import MapInfo, find, load, picture
from maplelens.tools.path_arrow.places import WHERE, PictureRow, match_row, place_row
from maplelens.tools.path_arrow.route import Trip, distances

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
MATCH_ROWS = 3  # visible matches, or places; the list scrolls for the rest
CROSS = "\u00d7"  # the multiplication sign: back to the search
SHOW_MS, HIDE_MS = 150, 80  # as on the Class tab: no flash on a sweep; swap in place
Goal = tuple[str, tuple[int, int] | None, str | None]  # (map, NPC spot, the NPC's name)
_DONE, _AHEAD, _NUM = "#6f7d93", "#c9d3e3", "#7b8aa3"  # mockup 3's route list
_STYLE = FIELD_STYLE + f"QCheckBox {{ color: {VALUE_COLOR}; }}"


class _Leave(QObject):
    """Calls `gone` when a list's viewport is left or hidden (the list, the page or the tab)."""

    def __init__(self, parent: QObject, gone: Callable[[QEvent.Type], None]):
        super().__init__(parent)
        self._gone = gone

    def eventFilter(self, _obj, event):  # noqa: N802
        if event.type() in (QEvent.Leave, QEvent.Hide):
            self._gone(event.type())
        return False


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


def _hline(*widgets: QWidget | None, spacing: int = 6) -> QWidget:
    """The widgets side by side; None is a stretch."""
    box = QWidget()
    line = QHBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    for w in widgets:
        if w is None:
            line.addStretch()
        else:
            line.addWidget(w, 0, Qt.AlignVCenter)
    return box


class PathArrowTool:
    def __init__(  # noqa: PLR0913 - the data are keywords, for tests to pass their own
        self,
        settings: dict,
        on_settings_changed: Callable[[], None],
        layer: Layer,
        allow_typing: Callable[[bool], None],
        maps: dict[str, MapInfo] | None = None,
        *,
        game: GameData | None = None,
        spots: SpotData | None = None,
    ):
        self.maps = load() if maps is None else maps
        self.game = load_game() if game is None else game
        self.spots = load_spots() if spots is None else spots
        self._picked: Match | None = None  # the monster, item or NPC whose places are listed
        self._picked_row: PictureRow | None = None
        self._places_for: tuple | None = None  # what the places list was sorted for
        self._dist: tuple = (None, {})  # ((here, taxi), hops to every map)
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
        self._card = SpotCard()
        self._pending: tuple[Card, QWidget] | None = None  # the card the show timer will show
        self._show_timer = QTimer(singleShot=True, interval=SHOW_MS, timeout=self._show_card)
        self._hide_timer = QTimer(singleShot=True, interval=HIDE_MS, timeout=self._card.hide)
        self.tab = self._build_tab(settings["path_taxi"])
        self._render()

    def set_tab_w(self, width: int) -> None:
        self._tab_w = width
        self.tab.setFixedWidth(width)
        for lst in (self._matches, self._places):
            for i in range(lst.count()):
                lst.itemWidget(lst.item(i)).fit(self._row_w())
        if self._picked_row:
            self._picked_row.fit(self._picked_w())
        self._render()  # the names are cut to the width

    def _row_w(self) -> int:
        """A list row's width: the tab less the list's frame and a scroll bar's room."""
        bar = self._matches.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        return self._tab_w - 2 * self._matches.frameWidth() - bar

    def _picked_w(self) -> int:
        return self._tab_w - self._cross.sizeHint().width() - 6

    def _list(self) -> QListWidget:
        lst = QListWidget()
        lst.setMouseTracking(True)  # itemEntered without a button down
        lst.itemEntered.connect(lambda item, lst=lst: self._hover(lst, item))
        lst.viewport().installEventFilter(_Leave(lst, self._left))
        lst.setFocusPolicy(Qt.NoFocus)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # names elide
        # Its own 256 px width hint would widen the box past the tab (the box's page stack
        # sizes from raw hints, ignoring the tab's fixed width).
        lst.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        lst.hide()
        return lst

    @staticmethod
    def _add(lst: QListWidget, row: PictureRow, data) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, data)
        item.setSizeHint(row.sizeHint())
        lst.addItem(item)
        lst.setItemWidget(item, row)
        return item

    @staticmethod
    def _show_rows(lst: QListWidget) -> None:
        """Shown when it has rows, MATCH_ROWS high at most, the first one current."""
        n = lst.count()
        lst.setVisible(n > 0)
        if n:
            rows = lst.sizeHintForRow(0) * min(n, MATCH_ROWS)
            lst.setFixedHeight(rows + 2 * lst.frameWidth())
            lst.setCurrentRow(0)

    def _card_for(self, data) -> Card | None:
        """The hover card of a match or a place; None for the rows with no card."""
        if isinstance(data, Match):
            if data.kind != "map":
                return None
            m = self.maps[data.ids[0]]
            return map_card(self.spots, m.id, m.name, m.street)
        if not isinstance(data, Source) or self._picked is None:
            return None
        m, kind = self.maps[data.map_id], self._picked.kind
        if data.shop:
            return npc_card(self.game, data.via, m.title, shop=True)
        if kind == "npc":
            return npc_card(self.game, self._picked.ids[0], m.title)
        extra = f"≈ {data.score:.1f} drops per clear" if kind == "item" else None
        return map_card(self.spots, m.id, m.name, m.street, str(data.via), extra)

    def _hover(self, lst: QListWidget, item: QListWidgetItem | None) -> None:
        card = self._card_for(item.data(Qt.UserRole)) if item else None
        if card is None:
            self._left()
            return
        row = lst.itemWidget(item)
        if self._card.isVisible():  # straight from another row: swap it in place
            self._hide_timer.stop()
            self._card.fill(card, self.spots)
            self._card.put(row)
        else:
            self._pending = (card, row)
            self._show_timer.start()

    def _left(self, kind=QEvent.Leave) -> None:
        """The mouse left the rows: hide after a beat, so the next row swaps it in place; a
        hidden list hides it at once."""
        # The viewports report hiding while the tool is torn down too: at exit Python deletes
        # the card and timers first.
        parts = [getattr(self, n, None) for n in ("_card", "_show_timer", "_hide_timer")]
        if not all(p is not None and isValid(p) for p in parts):
            return
        if kind == QEvent.Hide:
            self._no_card()
            return
        self._show_timer.stop()
        self._pending = None
        if self._card.isVisible():
            self._hide_timer.start()

    def _show_card(self) -> None:
        if self._pending is None:
            return
        (card, row), self._pending = self._pending, None
        self._card.fill(card, self.spots)
        self._card.put(row)
        self._card.show()

    def _no_card(self) -> None:
        """Gone at once: the rows it was for are gone, or the trip starts."""
        self._show_timer.stop()
        self._hide_timer.stop()
        self._pending = None
        self._card.hide()

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
        self._matches = self._list()
        self._matches.currentItemChanged.connect(lambda *_: self._render())
        self._matches.itemClicked.connect(self._pick)
        picked = self._build_picked()
        self._taxi = QCheckBox("Use taxi")
        self._taxi.setFocusPolicy(Qt.NoFocus)
        self._taxi.setChecked(taxi)
        self._taxi.toggled.connect(lambda _: self._render())  # re-sorts the places
        self._start = primary_button("Start", self._on_start)
        self._route_list = text_label("", LABEL_PT + 1, _AHEAD)
        self._route_list.setTextFormat(Qt.RichText)
        self._stop = secondary_button("Stop", self.stop)

        self._choose, self._running = QWidget(), QWidget()
        for page, widgets in [
            (self._choose, [self._search, self._matches, *picked, self._taxi, self._start]),
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

    def _build_picked(self) -> list[QWidget]:
        """The picked state's lines, in place of the field and the matches: the picked row
        with its cross, "Where …" with Best | Closest, the places."""
        self._cross = mark_button(CROSS, LABEL_PT + 2, self._unpick)
        self._picked_box = _hline(self._cross)  # the picked row goes in before the cross
        self._where = text_label("", LABEL_PT, LABEL_COLOR)
        self._best = mark_button("Best", LABEL_PT, lambda: self._set_best(True))
        self._closest = mark_button("Closest", LABEL_PT, lambda: self._set_best(False))
        bar = text_label("|", LABEL_PT, EDGE)
        self._switch = _hline(self._best, bar, self._closest, spacing=4)
        self._where_line = _hline(self._where, None, self._switch)
        self._places = self._list()
        self._places.currentItemChanged.connect(lambda *_: self._render())
        self._style_switch()
        self._picked_box.hide()
        self._where_line.hide()
        return [self._picked_box, self._where_line, self._places]

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
        self._no_card()
        self._matches.clear()
        names = {i: (m.name, m.street) for i, m in self.maps.items()}
        hits = search(self.game, names, text)
        for m in hits:
            self._add(self._matches, match_row(self.game, self.spots, m, self._row_w()), m)
        self._show_rows(self._matches)
        self._render()

    def _pick(self, item: QListWidgetItem) -> None:
        """A map (or an NPC on one map) fills the field and the list closes on it; Start
        goes there. A monster, an item or any other NPC lists its places instead."""
        self._set_typing(False)
        self._no_card()
        self._matches.setCurrentItem(item)
        if self._goal() is not None:
            self._search.blockSignals(True)  # re-searching could make another row current
            self._search.setText(item.data(Qt.UserRole).name)
            self._search.blockSignals(False)
            self._matches.hide()
        else:
            self._picked = item.data(Qt.UserRole)
            if self._picked_row:
                self._picked_row.hide()  # out of the line now, deleted soon
                self._picked_row.deleteLater()
            self._picked_row = match_row(self.game, self.spots, self._picked, self._picked_w())
            self._picked_box.layout().insertWidget(0, self._picked_row, 1)
            for w in (self._search, self._matches):
                w.hide()
            for w in (self._picked_box, self._where_line):
                w.show()
            self._fill_places()
        self._render()

    def _unpick(self) -> None:
        """Back to the search, its text and matches as they were."""
        self._picked = None
        self._no_card()
        self._places.clear()
        for w in (self._picked_box, self._where_line, self._places):
            w.hide()
        self._search.show()
        self._matches.setVisible(self._matches.count() > 0)
        self._render()

    def _places_key(self) -> tuple:
        here = self._here.id if self._here else None
        return self._picked, here, self._taxi.isChecked(), self._settings["path_best"]

    @staticmethod
    def _place_id(s) -> tuple:
        return s.map_id, s.via, s.shop

    def _fill_places(self) -> None:
        m, closest = self._picked, not self._settings["path_best"]
        if m.kind == "monster":
            found = mob_places(self.game, m.ids, self.maps, self.hops, closest)
        elif m.kind == "item":
            found = item_places(self.game, m.ids[0], self.maps, self.hops, closest)
        else:
            found = npc_places(self.game, m.ids[0], self.maps, self.hops)
        self._places_for = self._places_key()
        self._no_card()
        known, lst = self._here is not None, self._places
        cur = lst.currentItem()
        kept = cur and self._place_id(cur.data(Qt.UserRole))
        lst.blockSignals(True)  # the caller renders once it's filled
        lst.clear()
        for s in found:
            row = place_row(self.game, self.spots, self.maps, m.kind, s, known, self._row_w())
            self._add(lst, row, s)
        self._show_rows(lst)
        if kept:  # a re-sort keeps the place the player chose
            for i in range(lst.count()):
                if self._place_id(lst.item(i).data(Qt.UserRole)) == kept:
                    lst.setCurrentRow(i)
                    break
        lst.blockSignals(False)
        self._where.setText(WHERE[m.kind] if found else f"{WHERE[m.kind]}: unknown")
        self._switch.setVisible(bool(found) and m.kind != "npc")  # an NPC's go by hops only

    def _set_best(self, best: bool) -> None:
        if self._settings["path_best"] != best:
            self._settings["path_best"] = best
            self._changed()
            self._style_switch()
            self._render()  # re-sorts

    def _style_switch(self) -> None:
        """Best | Closest: the side that's on in yellow and bold."""
        best = self._settings["path_best"]
        for button, on in ((self._best, best), (self._closest, not best)):
            color, weight = (ACCENT, "bold") if on else (LABEL_COLOR, "normal")
            button.setStyleSheet(f"color: {color}; font-weight: {weight}; border: 0; padding: 0;")

    def _goal(self) -> Goal | None:
        """Where Start goes: the current place, or the current match when that is a map or
        an NPC on one map."""
        if self._picked:
            item = self._places.currentItem()
            if item is None:
                return None
            s = item.data(Qt.UserRole)
            named = s.shop or self._picked.kind == "npc"
            return s.map_id, s.at, self.game.npcs[s.via].name if named else None
        item = self._matches.currentItem()
        m = item.data(Qt.UserRole) if item else None
        if m is None or m.kind in ("monster", "item"):
            return None
        if m.kind == "map":
            return m.ids[0], None, None
        places = npc_places(self.game, m.ids[0], self.maps, lambda _: None)
        return (places[0].map_id, places[0].at, m.name) if len(places) == 1 else None

    def go(self, map_id: str, at: tuple[int, int] | None = None, label: str | None = None) -> None:
        """Fill the field with that map and start, as picking it and pressing Start do.

        With `at`, the trip goes on to that spot on the map; `label` names it.
        """
        m = self.maps[map_id]
        self._unpick()
        self._search.setText(m.name)  # fills the match list
        item = next(
            (
                i
                for i in (self._matches.item(n) for n in range(self._matches.count()))
                if (i.data(Qt.UserRole).kind, i.data(Qt.UserRole).ids) == ("map", (map_id,))
            ),
            None,
        )
        if item is None:
            match = Match("map", (map_id,), m.name, f"Map · {m.street}")
            row = match_row(self.game, self.spots, match, self._row_w())
            item = self._add(self._matches, row, match)
        self._pick(item)
        self._begin((map_id, at, label))

    def _on_start(self) -> None:
        self._begin(self._goal())

    def _begin(self, goal: Goal | None) -> None:
        self._set_typing(False)
        self._no_card()
        if self._here is None or self._unread() or goal is None:
            return
        map_id, at, label = goal
        taxi = self._taxi.isChecked()
        if self._settings.get("path_taxi") != taxi:
            self._settings["path_taxi"] = taxi
            self._changed()
        self._note = ""
        self._label = label
        self.trip = Trip(self.maps, self._here.id, map_id, taxi, at)
        self._settle()
        self._render()

    def stop(self) -> None:
        self._no_card()
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
        key = (self._here.id, self._taxi.isChecked())
        if self._dist[0] != key:
            self._dist = (key, distances(self.maps, *key))
        return self._dist[1].get(map_id)

    def _render(self) -> None:
        if self._picked and self._places_for != self._places_key():
            self._fill_places()  # a new map, taxi or Best | Closest
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
        self._start.setEnabled(known and self._goal() is not None)
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
