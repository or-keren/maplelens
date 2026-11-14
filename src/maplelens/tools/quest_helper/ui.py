"""The quest helper's Quests tab: the quest open in the game, then the tracked ones."""

import functools
import html
import re
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import delete

from maplelens.overlay import (
    ACCENT,
    EDGE,
    FONT,
    HERE_BG,
    LABEL_COLOR,
    LABEL_PT,
    TAB_W,
    VALUE_COLOR,
    InfoLine,
    Row,
    mark_button,
    primary_button,
    secondary_button,
    text_label,
)
from maplelens.readers import Reading
from maplelens.readers.quest_tracker import PARTLY, Tracker
from maplelens.readers.quest_window import NAME_UNREADABLE, QuestOpen
from maplelens.readers.window import UNREADABLE
from maplelens.tools.quest_helper.data import ICONS, Quest, QuestData, load
from maplelens.tools.quest_helper.plan import (
    SEVERAL,
    Part,
    Target,
    also_for,
    asked,
    block_candidates,
    done_parts,
    find_quest,
    match_block,
    shared_name,
    show_giver,
    starts_closest,
    targets,
)
from maplelens.tools.quest_helper.plan import (
    UNKNOWN as NO_MATCH,
)
from maplelens.tools.quest_helper.rewards import Group, Shown, branch, details, summary

EMPTY = "Open a quest in the game to see where to go"
UNKNOWN = "This quest isn't in MapleLens's list yet"
SHARED_NAME = "Several quests have this name; MapleLens can't tell which yet"
UNREAD = "Can't read the quest window: move it fully into view"
NAME_UNREAD = "Can't read the quest's name: scroll its text to the top"
OPEN = "Open in the game"
TRACK = "Track"
TRACKED = "Tracked ✓"
STOP = "Stop"
CLOSEST, BEST = "Closest", "Best"  # the quest's switch: the nearest maps, or the most spawns
TRACKING = "Tracking · {n} quests"
TRACKING_ONE = "Tracking · 1 quest"
GOING = "Going · {n} maps away"
GOING_ONE = "Going · 1 map away"
GOING_HERE = "Going · on this map"
UNREAD_PANEL = "Can't read the game's Quest Helper: move it fully into view"
PARTLY_PANEL = "Can't read all of the game's Quest Helper"
NOT_LISTED_Q = "{name}: not in MapleLens's list yet"
SEVERAL_Q = "{name}: several quests have this name"
PARTLY_SHOWN = 5  # PARTLY readings in a row before the line shows: a busy map flickers it
GONE = 2  # panel readings in a row without a followed quest before it is untracked
ALSO = "also for {quest}"
SHUT, SHOWN = "▸", "▾"
CLOSE = "\u00d7"  # the multiplication sign, the box's close mark

TOP = 4  # the tab's top margin, as the Class tab's
# The tallest Class tab state test_class_ui builds (box_with_tools, STATES): Rogue Lv 28,
# 302 px laid out at TAB_W in the box (its sizeHint says 319, before its wrapped lines
# get their width). Past it, the tab scrolls.
MAX_H = 302
BAR = 4  # the scroll bar's width; the tab's own lines leave room for it
_BAR_STYLE = f"""
QScrollBar:vertical {{ width: {BAR}px; background: transparent; margin: 0; }}
QScrollBar::handle:vertical {{ background: {EDGE}; border-radius: 2px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}"""


def _fit(widget, text: str, room: int) -> None:
    """Set `text` cut to `room` px; the full text is the tooltip."""
    widget.setText(QFontMetrics(widget.font()).elidedText(text, Qt.ElideRight, room))
    widget.setToolTip(text)


def _line(left: QWidget, *right: QWidget) -> QWidget:
    line = QWidget()
    row = QHBoxLayout(line)
    row.setContentsMargins(0, 2, 0, 0)
    row.setSpacing(6)
    row.addWidget(left)
    row.addStretch()
    for w in right:
        row.addWidget(w, 0, Qt.AlignVCenter)
    return line


def _room(*right: QWidget) -> int:
    """The width the widgets right of a name take, with the line's spacing."""
    return sum(w.sizeHint().width() + 6 for w in right)


INDENT = 13  # the reward details, under the reward line
SLOT, ICON_MAX, SLOT_GAP = 26, 24, 3  # an item's square, the largest icon in it, between two


@functools.cache
def _icon(item: int) -> QPixmap | None:
    """The item's icon, scaled down to fit a slot if it must; None without a file."""
    pix = QPixmap(str(ICONS / f"{item}.png"))
    if pix.isNull():
        return None
    if pix.width() > ICON_MAX or pix.height() > ICON_MAX:
        pix = pix.scaled(ICON_MAX, ICON_MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pix


class Slot(QWidget):
    """One reward item: its icon on a dark square, the count in the corner, the name on hover."""

    def __init__(self, shown: Shown, corner: bool = True):
        super().__init__()
        self.setFixedSize(SLOT, SLOT)
        self.setToolTip(shown.tip)
        # in the list form the name beside the slot carries the count
        self._pix, self._count = _icon(shown.item), shown.count if corner else 0

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(HERE_BG))
        p.drawRoundedRect(self.rect(), 4, 4)
        if self._pix is not None:
            x, y = (SLOT - self._pix.width()) // 2, (SLOT - self._pix.height()) // 2
            p.drawPixmap(x, y, self._pix)
        if self._count > 1:
            p.setFont(QFont(FONT, 7, QFont.Bold))
            corner = self.rect().adjusted(0, 0, -1, 1)
            p.setPen(QColor("#000000"))  # a shadow, so the count reads over the icon
            p.drawText(corner.translated(1, 1), Qt.AlignRight | Qt.AlignBottom, str(self._count))
            p.setPen(QColor(VALUE_COLOR))
            p.drawText(corner, Qt.AlignRight | Qt.AlignBottom, str(self._count))


class RewardLine(QLabel):
    """The closed reward line: grey words, white numbers, cut to `room`; the full text is the
    tooltip. With `on_click`, a left click acts, as a Row's does."""

    def __init__(self, text: str, room: int, on_click: Callable[[], None] | None = None):
        super().__init__()
        self.clickable, self._on_click = on_click is not None, on_click
        self.setFont(QFont(FONT, LABEL_PT))
        self.setStyleSheet(f"color: {LABEL_COLOR};")
        self.setTextFormat(Qt.RichText)
        self.setFocusPolicy(Qt.NoFocus)
        if self.clickable:
            self.setCursor(Qt.PointingHandCursor)
        cut = html.escape(self.fontMetrics().elidedText(text, Qt.ElideRight, room), quote=False)
        self.setText(re.sub(r"\d[\d,]*", rf'<span style="color: {VALUE_COLOR};">\g<0></span>', cut))
        self.setToolTip(text)

    def click(self) -> None:
        if self._on_click:
            self._on_click()

    def mousePressEvent(self, event):  # taken when clickable, so the box doesn't start a drag
        event.setAccepted(self.clickable and event.button() == Qt.LeftButton)

    def mouseReleaseEvent(self, event):
        if not (self.clickable and event.button() == Qt.LeftButton):
            event.ignore()
            return
        if self.rect().contains(event.position().toPoint()):
            self.click()


def _wrapped(text: str, color: str = LABEL_COLOR):
    label = text_label(text, LABEL_PT, color)
    label.setWordWrap(True)
    return label


class QuestHelperTool:
    def __init__(  # noqa: PLR0913, PLR0917 - the tool's collaborators, as the other tools take
        self,
        settings: dict,
        on_settings_changed: Callable[[], None],
        go: Callable[[str, tuple[int, int] | None, str | None], None],
        heading: Callable[[], tuple[str, tuple[int, int] | None, int] | None],
        stop: Callable[[], None],
        hops: Callable[[str], int | None],
        data: QuestData | None = None,
    ):
        self.title = "Quests"
        self.open = False  # the quest window is in this reading
        self._settings, self._changed = settings, on_settings_changed
        self._go, self._heading, self._stop, self._hops = go, heading, stop, hops
        self._can_go = True  # trips can start: the Path tab is on
        self._data = load() if data is None else data
        self._clean()
        self._progress: dict[int, frozenset[Part]] = {}  # done targets, from the panel
        self._missing: dict[int, int] = {}  # panel readings in a row without a followed quest
        self._notes: list[str] = []  # the panel's blocks MapleLens can't place
        self._panel_line: tuple[str, str] | None = None  # the panel's warning item
        self._no_panel = 0  # readings in a row without the panel
        self._partly = 0  # readings in a row that were PARTLY
        self._quest: QuestOpen | str | None = None  # the quest window, as shown
        self._misses = 0  # readings in a row without it
        self._shown: list | None = None  # the items now drawn
        self._job: str | None = None  # the last job read: a tick can miss it
        self._tab_w = TAB_W
        self.tab = QWidget()
        self.tab.setFixedWidth(self._tab_w)
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedWidth(self._tab_w)
        self._scroll.viewport().setAutoFillBackground(False)  # the box shows through
        self._scroll.verticalScrollBar().setStyleSheet(_BAR_STYLE)
        for w in (self._scroll, self._scroll.verticalScrollBar()):
            w.setFocusPolicy(Qt.NoFocus)
        self._holder = QWidget()  # the scrolled widget; each redraw swaps the body in it
        QVBoxLayout(self._holder).setContentsMargins(0, 0, 0, 0)
        self._scroll.setWidget(self._holder)
        self._holder.setAutoFillBackground(False)  # setWidget turned it on
        self._body: QWidget | None = None
        self._old: QWidget | None = None
        col = QVBoxLayout(self.tab)
        col.setContentsMargins(0, TOP, 0, 0)
        col.addWidget(self._scroll)
        self._render()

    def set_can_go(self, on: bool) -> None:
        """Whether a target row's click can start a trip; with Path off it can't."""
        if on == self._can_go:
            return
        self._can_go = on
        self._shown = None
        self._render()

    def set_tab_w(self, width: int) -> None:
        if width == self._tab_w:
            return  # the box tells each tab its width at the start: nothing to redraw yet
        self._tab_w = width
        self.tab.setFixedWidth(width)
        self._scroll.setFixedWidth(width)
        self._shown = None  # the names are cut to the width
        self._render()

    def _clean(self) -> None:
        """Keep the quest ids the data still has; a hand-edited bad value is replaced."""
        s, quests = self._settings, self._data.quests
        ids = s.get("quests_tracked")
        ids = ids if isinstance(ids, list) else []
        s["quests_tracked"] = list(dict.fromkeys(i for i in ids if type(i) is int and i in quests))
        if s.get("quests_expanded") not in s["quests_tracked"]:
            s["quests_expanded"] = None
        picks = s.get("quests_closest")
        picks = picks if isinstance(picks, dict) else {}
        s["quests_closest"] = {
            k: v for k, v in picks.items() if type(v) is bool and k.isdigit() and int(k) in quests
        }
        ids = s.get("quests_followed")
        ids = ids if isinstance(ids, list) else []
        s["quests_followed"] = list(
            dict.fromkeys(i for i in ids if type(i) is int and i in s["quests_tracked"])
        )
        if type(s.get("quest_rewards_open")) is not bool:
            s["quest_rewards_open"] = False

    def update(self, r: Reading | None, _game_rect, _now: float) -> None:
        if r is not None and r.job is not None:
            self._job = r.job
        quest = r.quest if r is not None else None
        self.open = quest is not None
        if quest is not None:
            self._quest, self._misses = quest, 0
        else:
            self._misses += 1
            if self._misses >= 2:  # one missed reading keeps it
                self._quest = None
        self._read_panel(r.tracker if r is not None else None)
        self._render()

    def _read_panel(self, t: Tracker | str | None) -> None:
        """Follow the game's Quest Helper; the states are in
        docs/superpowers/specs/2026-11-11-quest-tracker-sync-design.md."""
        if t is None:
            self._no_panel += 1
            if self._no_panel >= GONE:  # one missed reading keeps everything
                self._progress, self._notes, self._panel_line, self._partly = {}, [], None, 0
            return
        self._no_panel = 0
        self._partly = self._partly + 1 if t == PARTLY else 0
        if t == PARTLY:  # half read: nothing changes but the line, once it lasts
            shown = self._partly >= PARTLY_SHOWN
            self._panel_line = ("info", PARTLY_PANEL) if shown else None
        elif t == UNREADABLE:
            self._notes, self._panel_line = [], ("action", UNREAD_PANEL)
        elif isinstance(t, Tracker) and t.minimized:
            self._notes, self._panel_line = [], None
        elif isinstance(t, Tracker):
            self._notes, self._panel_line = [], None
            self._follow(t)

    def _follow(self, t: Tracker) -> None:
        d, s = self._data, self._settings
        seen: set[int] = set()
        several: set[int] = set()  # quests a SEVERAL block may be
        changed = False
        for block in t.quests:
            m = match_block(d, block)
            if m == NO_MATCH:
                self._notes.append(NOT_LISTED_Q.format(name=block.name))
            elif m == SEVERAL:
                self._notes.append(SEVERAL_Q.format(name=block.name))
                several.update(q.id for q in block_candidates(d, block))
            else:
                seen.add(m)
                self._progress[m] = done_parts(d, d.quests[m], block.lines)
                self._missing.pop(m, None)
                for key in ("quests_tracked", "quests_followed"):
                    if m not in s[key]:
                        s[key].append(m)
                        changed = True
        for i in list(s["quests_followed"]):
            if i in seen or i in several:
                continue
            self._missing[i] = self._missing.get(i, 0) + 1
            if self._missing[i] >= GONE:
                self._forget(i)
                changed = True
        if changed:
            self._changed()

    def _forget(self, qid: int) -> None:
        """Drop a quest from every list and from memory."""
        s = self._settings
        for key in ("quests_tracked", "quests_followed"):
            if qid in s[key]:
                s[key].remove(qid)
        if s["quests_expanded"] == qid:
            s["quests_expanded"] = None
        self._progress.pop(qid, None)
        self._missing.pop(qid, None)

    # --- actions ----------------------------------------------------------

    def _save(self) -> None:
        self._changed()
        self._render()

    def _track(self, qid: int) -> None:
        self._settings["quests_tracked"].append(qid)
        self._settings["quests_expanded"] = qid  # shown open once the window closes
        self._save()

    def _untrack(self, qid: int) -> None:
        self._forget(qid)
        self._save()

    def _expand(self, qid: int) -> None:
        shown = self._settings["quests_expanded"] == qid
        self._settings["quests_expanded"] = None if shown else qid
        self._save()

    def _flip_rewards(self) -> None:
        self._settings["quest_rewards_open"] = not self._settings["quest_rewards_open"]
        self._save()

    def _pick(self, qid: int, closest: bool) -> None:
        self._settings["quests_closest"][str(qid)] = closest
        self._save()

    def _closest(self, quest: Quest) -> bool:
        return self._settings["quests_closest"].get(str(quest.id), starts_closest(quest))

    def _switch_at(self, quest: Quest) -> bool | None:
        """The switch's side for the quest's name line; None: no switch, nothing to hunt."""
        return self._closest(quest) if asked(quest) else None

    def _go_to(self, map_id: str, at: tuple[int, int] | None, npc: str | None) -> None:
        self._go(map_id, at, npc)
        self._render()  # outline the row now, not on the next tick

    def _stop_trip(self) -> None:
        self._stop()
        self._render()

    # --- view -------------------------------------------------------------

    def _items(self) -> list:
        """Items are tuples, drawn in order: ("info", text), ("label", text),
        ("open", id, name, tracked, closest), ("head", id, name, expanded, closest),
        ("row", title, sub, map id, at, npc, info), ("run", title, sub), ("action", text),
        ("reward", text, opens, open), ("detail", text), ("icons", label, items)."""
        d, q = self._data, self._quest
        tracked = self._settings["quests_tracked"]
        out, top = self._top(q, tracked) if q is not None else ([], None)
        listed = [i for i in tracked if top is None or i != top.id]

        def done(i: int) -> frozenset[Part]:
            return self._progress.get(i, frozenset())

        plans = {
            i: targets(
                d,
                d.quests[i],
                giver=False,
                hops=self._hops,
                done=done(i),
                closest=self._closest(d.quests[i]),
            )
            for i in listed
        }
        if top is not None:
            giver = show_giver(q.taken, top.id in tracked)
            plans[top.id] = targets(
                d,
                top,
                giver=giver,
                hops=self._hops,
                done=done(top.id),
                closest=self._closest(top),
            )
        going = self._heading()

        def rows(qid: int) -> list:
            others = [(d.quests[j].name, plans[j]) for j in tracked if j != qid]  # tracked only
            return [self._row(t, others, going) for t in plans[qid]]

        if top is not None:
            out += self._rewards(top) + rows(top.id)
        if self._panel_line is not None:
            out.append(self._panel_line)
        out += [("info", note) for note in self._notes]
        if listed:
            n = len(tracked)  # the open one too, though it shows only on top
            out.append(("label", TRACKING_ONE if n == 1 else TRACKING.format(n=n)))
        for i in listed:
            expanded = i == self._settings["quests_expanded"]
            out.append(("head", i, d.quests[i].name, expanded, self._switch_at(d.quests[i])))
            if expanded:
                out += self._rewards(d.quests[i]) + rows(i)
        return out or [("info", EMPTY)]

    def _rewards(self, quest: Quest) -> list:
        """The reward line, then its details while open; nothing for a quest with no rewards."""
        text = summary(self._data, quest)
        if not text:
            return []
        parts = details(self._data, quest, branch(self._job))
        shown = self._settings["quest_rewards_open"]
        opens = bool(parts) and parts != (text,)  # the details add something
        out: list = [("reward", text, opens, shown)]
        if opens and shown:
            out += [
                ("icons", p.label, p.items) if isinstance(p, Group) else ("detail", p)
                for p in parts
            ]
        return out

    def _top(self, q: QuestOpen | str, tracked: list[int]) -> tuple[list, Quest | None]:
        """The top part's first lines, and the quest it shows rows for, if any."""
        if q == NAME_UNREADABLE:
            return [("label", OPEN), ("info", NAME_UNREAD)], None
        if not isinstance(q, QuestOpen):  # UNREADABLE: one move fixes it, so yellow
            return [("label", OPEN), ("action", UNREAD)], None
        if shared_name(self._data, q.name):
            return [("label", OPEN), ("info", SHARED_NAME)], None
        top = find_quest(self._data, q.name)
        if top is None:
            return [("label", OPEN), ("info", UNKNOWN)], None
        line = ("open", top.id, top.name, top.id in tracked, self._switch_at(top))
        return [("label", OPEN), line], top

    @staticmethod
    def _row(t: Target, others: list, going) -> tuple:
        if going is not None and t.map_id is not None and (t.map_id, t.at) == going[:2]:
            n = going[2]
            return (
                "run",
                t.title,
                GOING_HERE if n == 0 else GOING_ONE if n == 1 else GOING.format(n=n),
            )
        sub = t.sub
        names = also_for(t.map_id, others) if t.map_id else []
        if names:
            sub = f"{sub} · {ALSO.format(quest=', '.join(names))}"
        return ("row", t.title, sub, t.map_id, t.at, t.npc, t.info)

    def _widget(self, item) -> QWidget:
        kind = item[0]
        if kind == "info":
            return InfoLine(item[1])
        if kind == "action":
            line = text_label(item[1], LABEL_PT, ACCENT)
            line.setWordWrap(True)
            return line
        if kind == "label":
            return text_label(item[1], LABEL_PT, LABEL_COLOR)
        if kind == "row":
            _, title, sub, map_id, at, npc, info = item
            go = (lambda: self._go_to(map_id, at, npc)) if map_id and self._can_go else None
            row = Row(title, sub, go, info=info, width=self._tab_w)
            row.setToolTip(sub)  # the sub-line is cut to fit
            return row
        if kind == "run":
            _, title, sub = item
            stop = secondary_button(STOP, self._stop_trip)
            return Row(title, sub, None, outline=True, trailing=stop, width=self._tab_w)
        if kind in ("reward", "detail", "icons"):
            return self._reward_widget(item)
        if kind == "open":
            _, qid, name, tracked, closest = item
            if tracked:
                end = text_label(TRACKED, LABEL_PT, LABEL_COLOR)
            else:
                end = primary_button(TRACK, lambda: self._track(qid))
            ends = [*self._switch(qid, closest), end]
            label = text_label("", LABEL_PT, VALUE_COLOR, bold=True)
            _fit(label, name, self._tab_w - BAR - _room(*ends))
            return _line(label, *ends)
        _, qid, name, expanded, closest = item  # a tracked quest's header
        close = mark_button(CLOSE, LABEL_PT, lambda: self._untrack(qid))
        ends = [*self._switch(qid, closest), close]
        head = mark_button("", LABEL_PT, lambda: self._expand(qid), color=VALUE_COLOR)
        head.setFont(QFont(FONT, LABEL_PT, QFont.Bold))
        mark = f"{SHOWN if expanded else SHUT} "
        room = self._tab_w - BAR - _room(*ends) - head.fontMetrics().horizontalAdvance(mark)
        _fit(head, name, room)
        head.setText(mark + head.text())
        return _line(head, *ends)

    def _reward_widget(self, item) -> QWidget:
        kind = item[0]
        if kind == "reward":
            _, text, opens, shown = item
            if not opens:
                return RewardLine(text, self._tab_w - BAR)
            mark = SHOWN if shown else SHUT
            return RewardLine(f"{mark} {text}", self._tab_w - BAR, self._flip_rewards)
        if kind == "detail":
            line = _wrapped(item[1])
            line.setContentsMargins(INDENT, 0, 0, 0)
            return line
        return self._icons(item[1], item[2])

    def _icons(self, label: str, items: tuple[Shown, ...]) -> QWidget:
        """A reward group: its label, then one or two items each with its name, or more in
        rows of slots, the names on hover."""
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(INDENT, 0, 0, 0)
        col.setSpacing(2)
        if label:
            col.addWidget(_wrapped(label))
        # an item with no icon is named beside its empty slot, in a group of any size
        row_of = [s for s in items if _icon(s.item) is not None] if len(items) > 2 else []
        if row_of:
            grid = QGridLayout()
            grid.setSpacing(SLOT_GAP)
            cols = max(1, (self._tab_w - BAR - INDENT) // (SLOT + SLOT_GAP))
            for i, s in enumerate(row_of):
                grid.addWidget(Slot(s), i // cols, i % cols)
            grid.setColumnStretch(cols, 1)  # the slots stay at the left
            col.addLayout(grid)
        for s in items:
            if s in row_of:
                continue
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(Slot(s, corner=False))
            row.addWidget(_wrapped(s.tip, VALUE_COLOR), 1)
            col.addLayout(row)
        return box

    def _switch(self, qid: int, closest: bool | None) -> list[QWidget]:
        """Closest | Best: the side that's on in yellow, the other a mark that picks it."""
        if closest is None:
            return []
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for word, side in ((CLOSEST, True), (BEST, False)):
            if not side:
                row.addWidget(text_label("|", LABEL_PT, EDGE))
            if side == closest:
                row.addWidget(text_label(word, LABEL_PT, ACCENT, bold=True))
            else:
                row.addWidget(mark_button(word, LABEL_PT, lambda: self._pick(qid, not closest)))
        return [box]

    def _render(self) -> None:
        """Redraw only when the items changed."""
        items = self._items()
        if self._shown == items:
            return
        self._shown = items
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        for item in items:
            col.addWidget(self._widget(item))
        # The body drawn before stays, hidden, until the next redraw: a click handler may
        # still be running in it. The one before that goes now.
        if self._old is not None:
            delete(self._old)
        self._old = self._body
        if self._body is not None:
            self._body.hide()
            self._holder.layout().removeWidget(self._body)
        self._body = body
        self._holder.layout().addWidget(body)
        wrapped = body.hasHeightForWidth()
        h = body.heightForWidth(self._tab_w) if wrapped else body.sizeHint().height()
        self._scroll.setFixedHeight(min(h, MAX_H - TOP))
