"""Text for the EXP meter box and history window. Pure: no Qt."""

from datetime import date, datetime

from maplelens.tools.exp_meter.meter import Rate, SessionRate


def format_duration(minutes: float) -> str:
    m = round(minutes)
    if m < 1:
        return "<1m"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def format_clock(seconds: float) -> str:
    """A stopwatch: "4:05", or "1:04:05" from an hour."""
    m, sec = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


Column = tuple[str, list[str]]  # (grey label, value lines)

# The left label in manual mode while nothing is measured, by the session's state
PRESS_START, PAUSED = "Press Start", "Paused"
IDLE = "Idle"  # the live rate stopped for a break: no EXP for a while


def box_lines(  # noqa: PLR0913 - the tick's state, each part named
    rate: Rate | None,
    session: SessionRate | None,
    waiting: bool,
    unread: bool = False,
    held: str | None = None,
    *,
    timer: float | None = None,
) -> list[list[Column]]:
    """The EXP tab's content as rows of side-by-side columns; `unread`: the bar is unreadable;
    `held`: PRESS_START or PAUSED in manual mode. Before Start the live values are all "—";
    while paused, `rate` is the one at the Pause, kept on screen with the session's. `timer`:
    manual mode's seconds tracked since Start (pauses left out), in place of active time."""
    if waiting:
        return [[("waiting for game", [])]]
    if held == PRESS_START:
        rate = None
    if rate is None:
        exp, pct, eta = "— /h", "—% /h", "—"
    else:
        exp = f"{rate.exp_per_min * 60:,.0f} /h"
        pct = f"{rate.pct_per_min * 60:.2f}% /h"
        eta = "—" if rate.minutes_to_level is None else format_duration(rate.minutes_to_level)
    if held:
        label = held
    elif unread:
        label = "Can't read bar"
    elif rate is None or rate.early:
        label = "Measuring"
    else:
        label = IDLE if rate.paused else "Last 5 min"
    s_label, s_exp = _session_column(session, timer)
    # the session has no %/h: a percent doesn't add up across levels
    return [[(label, [exp, pct]), (s_label, [s_exp, ""])], [("Level up in", [eta])]]


def _session_column(session: SessionRate | None, timer: float | None) -> tuple[str, str]:
    """The session's label and EXP/h: manual mode's timer, else its active time."""
    label, exp = "Session", "— /h"
    if timer is not None:
        label += f" · {format_clock(timer)}"
    elif session:
        hours = session.active_s / 3600
        # from 10 h, hours only: "Session · 12h 10m" fills half the box to the pixel
        label += f" · {int(hours)}h" if hours >= 10 else f" · {format_duration(hours * 60)}"
    if session and session.exp_per_min is not None:
        exp = f"{session.exp_per_min * 60:,.0f} /h"
    return label, exp


def pin_text(
    rate: Rate | None, waiting: bool, unread: bool = False, held: str | None = None
) -> tuple[str, bool]:
    """The pinned EXP line on the other tabs: (text, in the accent colour)."""
    if waiting:
        return "Waiting for game", False
    if held == PAUSED and rate is not None and not rate.early:
        return f"{PAUSED} · {rate.pct_per_min * 60:.2f}%/h", False
    if held:
        return held, False
    if unread:
        return "Can't read bar", True
    if rate is None or rate.early:
        return "Measuring…", False
    if rate.paused:
        return IDLE, False
    eta = "—" if rate.minutes_to_level is None else format_duration(rate.minutes_to_level)
    return f"{rate.pct_per_min * 60:.2f}%/h · Lvl in {eta}", False


def format_last(ts: float, now: float) -> str:
    day = datetime.fromtimestamp(ts).date()
    days_ago = (date.fromtimestamp(now) - day).days
    if days_ago == 0:
        return "today"
    if days_ago == 1:
        return "yesterday"
    return f"{day:%b} {day.day}"


def short_name(title: str) -> str:
    """A map title without its street: "Victoria Island / Henesys" -> "Henesys"."""
    return title.rpartition(" / ")[2]


def best_lines(
    job: str | None, level: int | None, rows: list[tuple[str, float, float]]
) -> tuple[str, list[tuple[str, str, str]]]:
    """The History strip: a header and (map, EXP/h, %/h) per row of `history.best_maps`."""
    if job is None or level is None:
        return "Best maps: waiting for your class and level", []
    head = f"Best for {job}, Lv {level} (±3)"
    if not rows:
        return f"{head}: no 5-minute visits yet", []
    return head, [
        (short_name(m), f"{exp * 60:,.0f} EXP/h", f"{pct * 60:.2f}% /h") for m, exp, pct in rows
    ]
