"""The class helper's Class tab: where to train now, then what's next."""

from collections.abc import Callable
from math import sqrt
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from shiboken6 import delete, isValid

from maplelens.overlay import (
    ACCENT,
    BOX_FILL,
    CHIP_BG,
    FIELD,
    FONT,
    HERE_BG,
    LABEL_COLOR,
    LABEL_PT,
    OVERLAY,
    TAB_W,
    VALUE_COLOR,
    VALUE_PT,
    InfoLine,
    Layer,
    Row,
    game_to_layer,
    native_setup,
    paint_box,
    setting_box,
    text_label,
)
from maplelens.readers import Reading, glyphs
from maplelens.readers.skill_window import SkillWindow
from maplelens.readers.stat_window import StatWindow
from maplelens.readers.window import UNREADABLE
from maplelens.tools.class_helper.data import ClassData, Place, SpotData, load, load_spots
from maplelens.tools.class_helper.plan import (
    Card,
    advance_ready,
    ap_advice,
    band_at,
    gear,
    milestones,
    short,
    short_name,
    sp_advice,
    spot_card,
    training,
)

MARKS = "AP/SP marks on game windows"
NO_CLASS = "Can't read your class yet"
NO_PLAN = "No plan for {} yet"
TRAIN = "Train here · click to go"
NO_SPOTS = "No training spots in the guide for Lv {}"
READY = "Job advance is ready"
NEXT = "Next"
OPEN_STATS = "Open your stat window once"
STAT_UNREAD = "Can't read your stat window: move it fully into view"
SKILL_UNREAD = "Can't read your skill window: move it fully into view"
SCROLL = "scroll the list once"
CHOOSE = "Which class are you heading for?"
BUILD = "Build: {}"
CHANGE = "click to change"
TIERS = {0: "Beginner", 1: "1st job", 2: "2nd job"}
# Ring radius, and where the tag starts from the ring's left edge: past the pair of + buttons,
# which ends 20 px right of the ring's centre. Game base size; both grow with its buttons.
RING_R, TAG_GAP = 11, 36
MARK_PT = 9  # the tags over the game's windows keep their size; the box's labels grew

DASH = "\u2013"

# The hover card: its width, the picture's most height, its gap from the box, and the
# delays before it shows (so a sweep across the tab doesn't flash it) and hides (so moving
# to the next spot swaps it in place).
CARD_W, PICTURE_H, GAP, SHOW_MS, HIDE_MS = 300, 240, 8, 150, 80
_MARGIN, ICON, ICON_FIT, DOT_R, DOT_EDGE = 10, 48, 44, 4, "#141414"


class _Mark(QWidget):
    """A ring of ACCENT with a tag beside it, or a quiet tag alone. Never takes a click."""

    def __init__(self, layer: Layer):
        super().__init__(layer)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFont(QFont(FONT, MARK_PT, QFont.Bold))
        self.tag, self.centre, self.ring, self.scale = "", (0, 0), False, 1.0
        self.hide()

    def put(self, tag: str, centre: tuple[float, float], ring: bool, scale: float = 1.0) -> None:
        """`scale`: layer px per base game px, so the ring and gap follow the + buttons."""
        self.tag, self.centre, self.ring, self.scale = tag, centre, ring, scale
        r, gap = round(RING_R * scale), round(TAG_GAP * scale)
        w = gap + QFontMetrics(self.font()).horizontalAdvance(tag) + 6
        self.setGeometry(round(centre[0]) - r, round(centre[1]) - r, w, 2 * r)
        self.show()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self.font())
        r, gap = self.height() / 2, round(TAG_GAP * self.scale)
        colour = QColor(ACCENT if self.ring else LABEL_COLOR)
        if self.ring:
            pen = 3 * self.scale
            p.setPen(QPen(colour, pen))
            p.drawEllipse(QRectF(pen / 2 + 0.5, pen / 2 + 0.5, 2 * r - pen - 1, 2 * r - pen - 1))
        th = QFontMetrics(self.font()).height() + 2
        back = QRectF(gap - 4, r - th / 2, self.width() - gap + 3, th)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*BOX_FILL))  # readable over any game art
        p.drawRoundedRect(back, 4, 4)
        p.setPen(colour)
        p.drawText(QRectF(gap, 0, self.width() - gap, self.height()), Qt.AlignVCenter, self.tag)


def _tag(stat: str, a) -> str:
    if a.add:
        return f"{a.add} here"
    if a.over:
        return f"{stat}{a.over} over plan"
    return f"{stat}{a.behind} behind plan" if a.behind else ""


def _go_map(place: Place | None) -> str | None:
    return place.map_id if place else None


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
    """The hover card beside the box: a training spot's map with its spawn spots marked, and
    its monsters. Never takes the game's focus or a click."""

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
            k = min((CARD_W - 2 * _MARGIN) / w, PICTURE_H / h)
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
        if card.cap:
            col.addWidget(_words(card.cap, LABEL_PT, LABEL_COLOR))
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


class ClassHelperTool:
    def __init__(  # noqa: PLR0913, PLR0917 - the tool's collaborators, as the other tools take
        self,
        settings: dict,
        on_settings_changed: Callable[[], None],
        layer: Layer,
        go: Callable[[str], None],
        best_rate: Callable[[str], float | None],
        data: ClassData | None = None,
        spots: SpotData | None = None,
    ):
        self.title = "Class"
        self.dot = False
        self.builds_changed: Callable[[], None] = lambda: None  # the menu's Build item follows
        self._builds_seen: tuple | None = None  # (job, build names, build) last told
        self._settings, self._changed = settings, on_settings_changed
        self._layer, self._go, self._best_rate = layer, go, best_rate
        self._can_go = True  # trips can start: the Path tab is on
        self._data = load() if data is None else data
        self._job: str | None = None
        self._level: int | None = None
        self._stats: tuple[StatWindow, int] | None = None  # the window, the level it was read at
        self.skills: dict[str, dict[int, int]] = {}  # tab -> {skill id: level}
        self.sp: dict[str, tuple[int, int]] = {}  # tab -> (unspent SP, level it was read at)
        self._shown: tuple | None = None  # the items now drawn
        self._content: tuple | None = None  # the level-up dot's key
        self._plan_job: str | None = None
        self._picking = False  # the build row is open on the list of builds
        self._r: Reading | None = None
        self._seen_at = 0  # the level at the last update
        self._rect: tuple | None = None
        self._pool: list[_Mark] = []  # the layer owns them; they are hidden and reused
        self._marks: list[tuple[str, tuple[float, float], bool]] = []
        self._tab_w = TAB_W
        self.tab = QWidget()
        self.tab.setFixedWidth(self._tab_w)
        self._body = QWidget()
        col = QVBoxLayout(self.tab)
        col.setContentsMargins(0, 4, 0, 0)
        col.addWidget(self._body)
        self._spots = load_spots() if spots is None else spots
        self._places: dict[str, Place] = {}  # map id -> the training spot's place
        self._card = SpotCard()
        self._pending: tuple[Card, Row] | None = None  # the card the show timer will show
        self._show_timer = QTimer(singleShot=True, interval=SHOW_MS, timeout=self._show_card)
        self._hide_timer = QTimer(singleShot=True, interval=HIDE_MS, timeout=self._card.hide)
        self._render([("info", NO_CLASS)])

    def set_tab_w(self, width: int) -> None:
        if width == self._tab_w:
            return  # the box tells each tab its width at the start: nothing to redraw yet
        self._tab_w = width
        self.tab.setFixedWidth(width)
        items, self._shown = self._shown, None  # the names are cut to the width
        self._render(items)

    def set_can_go(self, on: bool) -> None:
        """Whether a row's click can start a trip; with Path off it can't, so no row is
        clickable and none shows the yellow angle."""
        if on == self._can_go:
            return
        self._can_go = on
        items, self._shown = self._shown, None
        if items is not None:
            self._render(items)

    def hide_marks(self) -> None:
        for m in self._pool:
            m.hide()

    def settings_section(self) -> QWidget:
        """The Class section of the Settings window."""
        section = QWidget()
        rows = QVBoxLayout(section)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.addWidget(setting_box(MARKS, self._settings.get("class_marks", True), self.set_marks))
        return section

    def set_marks(self, on: bool) -> None:
        """Turn the marks on the game's windows on or off (Settings' checkbox); the tab stays."""
        if self._settings.get("class_marks", True) == on:
            return
        self._settings["class_marks"] = on
        self._changed()
        self._draw_marks()

    def marks(self) -> list[tuple[str, tuple[int, int]]]:
        return [(m.tag, m.centre) for m in self._pool if not m.isHidden()]

    def _draw_marks(self) -> None:
        self.hide_marks()
        r, rect = self._r, self._rect
        if not self._settings.get("class_marks", True):
            return
        if r is None or rect is None or self._job is None or self._level is None:
            return
        k = rect[3] / glyphs.BASE_H  # normalized px -> client px
        dpr = self._layer.devicePixelRatioF()
        found = self._ap_marks(r) + self._sp_marks(r)
        while len(self._pool) < len(found):
            self._pool.append(_Mark(self._layer))
        for m, (tag, (x, y), ring) in zip(self._pool, found, strict=False):
            m.put(tag, game_to_layer(x * k, y * k, dpr), ring, k / dpr)

    def _ap_marks(self, r: Reading) -> list:
        st, level = r.stats, self._level
        plan = self._data.plan(self._job)
        if not isinstance(st, StatWindow) or st.level != level or plan is None:
            return []
        if self._asking(plan):
            return []
        band = band_at(plan.build(self._choices().get(plan.job)), level)
        if band is None:
            return []
        out = []
        for stat, a in ap_advice(band, level, st.base, st.ap).items():
            if stat in st.plus:
                tag = _tag(stat + " ", a)
                if tag:
                    out.append((tag, st.plus[stat], a.add > 0))
        return out

    def _sp_marks(self, r: Reading) -> list:
        sk = r.skills
        plan = self._data.plan(sk.tab) if isinstance(sk, SkillWindow) else None
        if plan is None or not sk.rows:
            return []
        steps = plan.build(self._choices().get(plan.job)).sp
        advice = sp_advice(steps, self.skills[sk.tab], sk.sp, self._data.skills, sk.tab)
        if advice is None:
            return [(SCROLL, sk.rows[0].plus, False)]
        planned = {s.skill for s in steps}
        out = []
        for row in sk.rows:
            a = advice.get(row.skill)
            tag = _tag("", a) if row.skill in planned else ("off plan" if a and a.over else "")
            if a and tag:
                out.append((tag, row.plus, a.add > 0))
        return out

    def _plan(self):
        return self._data.plan(self._plan_job) if self._plan_job else None

    def build_names(self) -> list[str]:
        """The current plan's builds, when there's a choice to make."""
        plan = self._plan()
        names = [b.name for b in plan.builds] if plan else []
        return names if len(names) > 1 else []

    def build_name(self) -> str | None:
        plan = self._plan()
        return plan.build(self._choices().get(plan.job)).name if plan else None

    def pick_build(self, name: str) -> None:
        if self._plan_job is None or not name:
            return
        self._choices()[self._plan_job] = name
        self._changed()
        self._picking = False
        self._render_last()

    def _asking(self, plan) -> bool:
        """A Beginner's class is theirs to pick: nothing assumed until they do."""
        return plan.tier == 0 and len(plan.builds) > 1 and plan.job not in self._choices()

    def _open_builds(self) -> None:
        self._picking = True
        self._render_last()

    def _tell_builds(self) -> None:
        seen = (self._plan_job, tuple(self.build_names()), self.build_name())
        if seen != self._builds_seen:
            self._builds_seen = seen
            self.builds_changed()

    # --- memory -----------------------------------------------------------

    def _remember(self, r: Reading | None) -> None:
        job = r.job if r else None
        level = r.level if r else None
        sk = r.skills if r else None
        lower = isinstance(sk, SkillWindow) and any(
            row.level < self.skills.get(sk.tab, {}).get(row.skill, 0) for row in sk.rows
        )  # skill levels never fall within one character
        if (
            (job and self._job and job != self._job)
            or (level is not None and self._level is not None and level < self._level)
            or lower
        ):
            self._stats, self._content = None, None
            self.skills, self.sp = {}, {}
        self._job = job or self._job
        self._level = level if level is not None else self._level
        if r is None:
            return
        st = r.stats
        if isinstance(st, StatWindow) and (r.level is None or st.level == r.level):
            self._stats = (st, st.level)
        if isinstance(sk, SkillWindow) and self._level is not None:
            self.skills.setdefault(sk.tab, {}).update({row.skill: row.level for row in sk.rows})
            self.sp[sk.tab] = (sk.sp, self._level)

    def _stats_now(self) -> StatWindow | None:
        if self._stats and self._stats[1] == self._level:
            return self._stats[0]
        return None

    def _points(self) -> tuple[int, int]:
        st = self._stats_now()
        sp = sum(n for n, at in self.sp.values() if at == self._level)
        return (st.ap if st else 0, sp)

    # --- view -------------------------------------------------------------

    def update(self, r: Reading | None, game_rect: tuple | None, _now: float) -> None:
        self._remember(r)
        self._r, self._rect = r, game_rect
        self._render_last()

    def _render_last(self) -> None:
        was = self._content
        items, content = self._items(self._r)
        self._render(items)
        self._draw_marks()
        self._tell_builds()
        level = self._level
        if self.tab.isVisible():
            self.dot = False
        elif was is not None and content != was and level is not None and level > self._seen_at:
            self.dot = True
        self._content = content
        self._seen_at = level if level is not None else 0

    def _items(self, r: Reading | None):  # -> (items, dot key)
        """Items are tuples, drawn in order: ("info", text), ("label", text, colour),
        ("header", job, level, chip), ("row", name, sub, go map, best, outline), ("divider",);
        ("spot", ...) is a training row: a "row" that shows its card on hover."""
        if self._job is None or self._level is None:
            return [("info", NO_CLASS)], None
        job, level = self._job, self._level
        plan = self._data.plan(job)
        self._plan_job = plan.job if plan else None
        hints = [("info", t) for t in self._tab_lines(r) + self._reasons(r)]
        if plan is None:  # the hints stay: a 1st-job tab's SP still needs placing
            return [("info", NO_PLAN.format(job)), *hints], (job,)
        build = plan.build(self._choices().get(plan.job))
        ap, sp = self._points()
        chip = " · ".join(f"{n} {w}" for n, w in ((ap, "AP"), (sp, "SP")) if n)
        out = [("header", job, level, chip)]
        if self._asking(plan):  # the class first; training is the same for every class
            return [
                *out,
                *self._build_items(plan, build),
                *self._train_items(plan, level, best=True),
                *hints,
            ], (job,)
        adv = advance_ready(plan, build, level)
        if adv:
            where = short_name(adv.where.name) if adv.where else None
            sub = " · ".join(p for p in (adv.npc, where) if p)
            out.append(("row", READY, sub, _go_map(adv.where), False, True))
        out += self._train_items(plan, level, best=adv is None)
        out += self._next_items(plan, build, level)
        out += self._build_items(plan, build)
        out += hints
        tkey = tuple(t.place.map_id or t.place.name for t in training(plan, level) if t.place)
        gkey = tuple(g.item.id for g in gear(build, level) if g)
        return out, (job, tkey, gkey, adv is not None, ap + sp)

    def _train_items(self, plan, level: int, *, best: bool) -> list:
        rows = [t for t in training(plan, level) if t.place]
        if not rows:
            return [("label", TRAIN, LABEL_COLOR), ("info", NO_SPOTS.format(level))]
        rates = [self._best_rate(t.place.title) if t.place.title else None for t in rows]
        known = [(rate, i) for i, rate in enumerate(rates) if rate]
        top = max(known)[1] if best and known else None
        out = [("label", TRAIN, LABEL_COLOR)]
        for i, (t, rate) in enumerate(zip(rows, rates, strict=True)):
            sub = (
                f"your best · {rate:,.0f}/min" if rate else f"mobs Lv {t.mobs[0]}{DASH}{t.mobs[1]}"
            )
            if t.place.map_id:
                self._places[t.place.map_id] = t.place
            out.append(("spot", short_name(t.place.name), sub, t.place.map_id, i == top, False))
        return out

    def _spot_hover(self, map_id: str, row: Row, inside: bool) -> None:
        # The rows report hiding while the tool is torn down too: garbage collection clears
        # its attributes first, and at exit Python deletes the card and timers first.
        parts = [getattr(self, n, None) for n in ("_card", "_show_timer", "_hide_timer")]
        if not all(p is not None and isValid(p) for p in parts):
            return
        if not inside:
            self._show_timer.stop()
            if self._card.isVisible():
                self._hide_timer.start()
            return
        card = spot_card(self._places[map_id], self._spots)
        if card is None:
            return
        if self._card.isVisible():  # straight from another spot: swap it in place
            self._hide_timer.stop()
            self._card.fill(card, self._spots)
            self._card.put(row)
        else:
            self._pending = (card, row)
            self._show_timer.start()

    def _show_card(self) -> None:
        if self._pending is None:
            return
        (card, row), self._pending = self._pending, None
        self._card.fill(card, self._spots)
        self._card.put(row)
        self._card.show()

    def _build_items(self, plan, build) -> list:
        """("pick", name, sub, build or None to open the list, current): a row per build."""
        if len(plan.builds) < 2:
            return []
        if not (self._asking(plan) or self._picking):
            return [("divider",), ("pick", BUILD.format(build.name), CHANGE, None, False)]
        if self._asking(plan):  # right under the header: no divider
            return [("label", CHOOSE, LABEL_COLOR)] + [
                ("pick", b.name, "", b.name, False) for b in plan.builds
            ]
        picks = [("pick", b.name, "", b.name, b is build) for b in plan.builds]
        return [("divider",), ("label", "Build", LABEL_COLOR), *picks]

    def _next_items(self, plan, build, level: int) -> list:
        steps = milestones(plan, build, level)
        if not steps:
            return []
        out = [("divider",), ("label", NEXT, LABEL_COLOR)]
        st = self._stats_now()
        for m in steps:  # "Lv 30 · Advance" over "Assassin or Bandit": short lines, never cut
            kind, _, detail = m.text.partition(": ")
            out.append(("row", f"Lv {m.level} · {kind}", detail, _go_map(m.where), False, False))
            lack = short(m.item, st.total if st else None) if m.item else {}
            if lack:
                out.append(
                    ("label", ", ".join(f"{n} {k} short" for k, n in lack.items()), LABEL_COLOR)
                )
        return out

    def _tab_lines(self, r: Reading | None) -> list[str]:
        """A skill tab left with SP, other than the one open now."""
        open_tab = r.skills.tab if r and isinstance(r.skills, SkillWindow) else None
        out = []
        for tab, (n, at) in self.sp.items():
            plan = self._data.plan(tab)
            if tab != open_tab and n > 0 and at == self._level and plan:
                out.append(f"{TIERS.get(plan.tier, tab)} tab: {n} SP to place")
        return out

    def _reasons(self, r: Reading | None) -> list[str]:
        st = r.stats if r else None
        bad = st == UNREADABLE or (
            isinstance(st, StatWindow) and r.level is not None and st.level != r.level
        )
        out = []
        if bad:
            out.append(STAT_UNREAD)
        elif self._stats_now() is None:
            out.append(OPEN_STATS)
        if r and r.skills == UNREADABLE:
            out.append(SKILL_UNREAD)
        return out

    def _choices(self) -> dict:
        """The saved build per job; a hand-edited non-dict value is replaced by an empty one."""
        if not isinstance(self._settings.get("class_builds"), dict):
            self._settings["class_builds"] = {}
        return self._settings["class_builds"]

    def _widget(self, item) -> QWidget:
        kind = item[0]
        if kind == "info":
            return InfoLine(item[1])
        if kind == "label":
            label = text_label(item[1], LABEL_PT, item[2])
            label.setWordWrap(True)
            return label
        if kind == "divider":
            line = QWidget()
            line.setFixedHeight(1)
            line.setAttribute(Qt.WA_StyledBackground, True)
            line.setStyleSheet(f"background: {HERE_BG};")
            return line
        if kind == "pick":
            _, name, sub, choice, current = item
            act = self._open_builds if choice is None else (lambda c=choice: self.pick_build(c))
            # after the click: the redraw deletes the row the click is still in
            return Row(
                name, sub, lambda: QTimer.singleShot(0, act), best=current, width=self._tab_w
            )
        if kind in {"row", "spot"}:
            _, name, sub, map_id, best, outline = item
            go = (lambda m=map_id: self._go(m)) if map_id and self._can_go else None
            hover = None
            if kind == "spot" and map_id:

                def hover(on: bool) -> None:
                    self._spot_hover(map_id, row, on)

            row = Row(name, sub, go, best=best, outline=outline, width=self._tab_w, on_hover=hover)
            return row
        _, job, level, chip = item  # the header
        head = QWidget()
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(6)
        room = self._tab_w
        badge = None
        if chip:
            badge = text_label(chip, LABEL_PT, ACCENT, bold=True)
            badge.setObjectName("chip")
            badge.setStyleSheet(
                f"#chip {{ color: {ACCENT}; background: {CHIP_BG}; border-radius: 8px;"
                " padding: 0 7px; }"
            )
            room -= badge.sizeHint().width() + row.spacing()
        label = text_label("", LABEL_PT, LABEL_COLOR)
        fm, tail = label.fontMetrics(), f" · Lv {level}"  # the level always shows; the job is cut
        label.setText(fm.elidedText(job, Qt.ElideRight, room - fm.horizontalAdvance(tail)) + tail)
        label.setToolTip(job)
        row.addWidget(label)
        row.addStretch()
        if badge:
            row.addWidget(badge)
        return head

    def _render(self, items) -> None:
        """Redraw only when the items changed."""
        if self._shown == items:
            return
        self._shown = items
        old, self._body = self._body, QWidget()
        col = QVBoxLayout(self._body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        for item in items:
            col.addWidget(self._widget(item))
        parent = self.tab.layout()
        parent.insertWidget(parent.indexOf(old), self._body)
        parent.removeWidget(old)
        delete(old)  # at once: a widget left to deleteLater still shows in the tab's children
        # Last: the old rows may report a leave as they go.
        self._show_timer.stop()
        self._hide_timer.stop()
        self._pending = None
        self._card.hide()
