"""Virtual clock. Phase 1.

One tick = 6 virtual hours. 112 ticks = 28 virtual days. The six-hour
granularity exists so that intra-day contact-window rules have something to
bite on.

Why the grid is offset to 08:00
-------------------------------
The epoch is 08:00, not midnight, so the four ticks of a day fall at
**08:00, 14:00, 20:00 and 02:00**. That offset is deliberate and it is the
difference between one demonstrable rule and two:

    tick hour   RBI contact window 08:00-19:00   TRAI promotional 10:00-21:00
    --------    ------------------------------   ----------------------------
    02:00       blocked                          blocked
    08:00       allowed                          blocked
    14:00       allowed                          allowed
    20:00       blocked                          allowed

On a midnight-anchored grid (00/06/12/18) the two windows admit exactly the
same two ticks and become indistinguishable on screen. Offset by eight hours,
they disagree at 08:00 and at 20:00, so each rule gets its own visible moment
in the timeline view.

Neither window is encoded here. Both are unverified (docs/ISSUES.md ISS-007,
ISS-008) and Phase 1 has no policy engine. This module exposes `hour_of_day`
and stops there; Phase 2 writes the rules, after verifying them at the source.

NO WALL CLOCK. There is no `datetime.now()` and no `date.today()` anywhere
below, and a test enforces that across the whole package.
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from recoup.domain.models import VIRTUAL_EPOCH, Tick, VirtualDate

#: Virtual hours in one tick.
HOURS_PER_TICK: int = 6

#: Ticks in one virtual day.
TICKS_PER_DAY: int = 24 // HOURS_PER_TICK

#: Hour of day at tick 0. See the module docstring for why this is not midnight.
EPOCH_HOUR: int = 8

#: A full run: 112 ticks, 28 virtual days.
DEFAULT_HORIZON: int = 112


def hours_since_epoch(tick: Tick) -> int:
    """Virtual hours elapsed from tick 0."""
    return EPOCH_HOUR + HOURS_PER_TICK * tick


def virtual_date(tick: Tick) -> VirtualDate:
    """The virtual calendar date a tick falls on."""
    return VIRTUAL_EPOCH + timedelta(days=hours_since_epoch(tick) // 24)


def hour_of_day(tick: Tick) -> int:
    """Hour of the virtual day, one of 2, 8, 14 or 20."""
    return hours_since_epoch(tick) % 24


def weekday(tick: Tick) -> int:
    """Virtual weekday. Monday is 0, matching `datetime.date.weekday()`."""
    return virtual_date(tick).weekday()


def first_tick_on(day: VirtualDate) -> Tick:
    """Earliest tick falling on `day`, clamped at tick 0 for the epoch date."""
    offset = (day - VIRTUAL_EPOCH).days
    return max(0, TICKS_PER_DAY * offset - 1)


def last_tick_on(day: VirtualDate) -> Tick:
    """Latest tick falling on `day` -- its 20:00 slot.

    A promise made "by Friday" is honoured at any point on Friday, so a
    deadline resolves to the end of the day, not the start of it.
    """
    offset = (day - VIRTUAL_EPOCH).days
    return TICKS_PER_DAY * offset + 2


def ticks_for_days(days: int) -> int:
    """Convert a whole number of virtual days into ticks."""
    return days * TICKS_PER_DAY


@dataclass
class VirtualClock:
    """The run's position in virtual time. The only mutable time in the system."""

    tick: Tick = 0
    horizon: int = DEFAULT_HORIZON

    @property
    def date(self) -> VirtualDate:
        """Today, virtually."""
        return virtual_date(self.tick)

    @property
    def hour(self) -> int:
        """Hour of the virtual day at the current tick."""
        return hour_of_day(self.tick)

    @property
    def exhausted(self) -> bool:
        """True once the run has advanced past its horizon."""
        return self.tick >= self.horizon

    def advance(self) -> Tick:
        """Move one tick forward and return the new tick."""
        self.tick += 1
        return self.tick

    def isoformat(self) -> str:
        """Human-readable virtual timestamp, e.g. `2026-04-07 14:00`."""
        return f"{self.date.isoformat()} {self.hour:02d}:00"


def format_tick(tick: Tick) -> str:
    """Render a tick as a virtual timestamp for logs and the dashboard."""
    return f"{virtual_date(tick).isoformat()} {hour_of_day(tick):02d}:00"


# ---------------------------------------------------------------------------
# Promise resolution
# ---------------------------------------------------------------------------
#
# INVARIANT 3, made concrete. The reasoner extracts the PHRASE a payer used and
# quotes the span it came from. It never computes a date. This function is the
# deterministic half: phrase in, tick out, or None when the phrase does not
# name a resolvable point in time.
#
# Returning None matters as much as returning a tick. "after the festival
# break" and "once the season picks up" are real things payers say and they are
# not dates. Suppressing contact on an unresolvable promise would be a bug that
# looks like a feature.

_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_ORDINAL_DAY = re.compile(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b")
_IN_N_DAYS = re.compile(r"\b(?:within|in the next|in)\s+(\d{1,2})\s+(?:working\s+)?days?\b")
_IN_N_WEEKS = re.compile(r"\b(?:within|in the next|in)\s+(\d{1,2})\s+weeks?\b")
_FORTNIGHT = re.compile(r"\bfortnight\b")
_MONTH_END = re.compile(r"\b(?:end of (?:this|the) month|month[- ]end|by month end)\b")
_NEXT_WEEK = re.compile(r"\bnext week\b")
_THIS_WEEK = re.compile(r"\bthis week\b")
_WEEKEND = re.compile(r"\b(?:before|by) the weekend\b")
_TOMORROW = re.compile(r"\btomorrow\b")


def _next_weekday(from_day: VirtualDate, target: int, *, allow_today: bool = False) -> VirtualDate:
    """The next occurrence of a weekday, strictly after `from_day` by default."""
    delta = (target - from_day.weekday()) % 7
    if delta == 0 and not allow_today:
        delta = 7
    return from_day + timedelta(days=delta)


def _next_day_of_month(from_day: VirtualDate, day_of_month: int) -> VirtualDate | None:
    """The next occurrence of a calendar day number, or None if it cannot exist."""
    if not 1 <= day_of_month <= 31:
        return None
    if day_of_month > from_day.day:
        try:
            return from_day.replace(day=day_of_month)
        except ValueError:
            return None
    year, month = (
        (from_day.year + 1, 1) if from_day.month == 12 else (from_day.year, from_day.month + 1)
    )
    if day_of_month > monthrange(year, month)[1]:
        return None
    return date(year, month, day_of_month)


def _end_of_month(from_day: VirtualDate) -> VirtualDate:
    """The last calendar day of the month `from_day` falls in."""
    return from_day.replace(day=monthrange(from_day.year, from_day.month)[1])


def resolve_promise_phrase(phrase: str, now_tick: Tick) -> Tick | None:
    """Turn a payer's relative phrase into a deadline tick. Deterministic. Pure.

    Returns None when the phrase names no resolvable point in time -- which is
    the correct answer for "after the festival break" and "in due course", and
    is why the caller must handle None rather than defaulting to a date.

    Resolution is anchored on `now_tick`, so the same phrase read on different
    ticks resolves differently. That is intended: "by Friday" means the coming
    Friday.
    """
    text = phrase.strip().lower()
    if not text:
        return None
    today = virtual_date(now_tick)

    if _TOMORROW.search(text):
        return last_tick_on(today + timedelta(days=1))

    if _MONTH_END.search(text):
        return last_tick_on(_end_of_month(today))

    if match := _IN_N_DAYS.search(text):
        return last_tick_on(today + timedelta(days=int(match.group(1))))

    if match := _IN_N_WEEKS.search(text):
        return last_tick_on(today + timedelta(weeks=int(match.group(1))))

    if _FORTNIGHT.search(text):
        return last_tick_on(today + timedelta(days=14))

    if _WEEKEND.search(text):
        return last_tick_on(_next_weekday(today, _WEEKDAYS["friday"], allow_today=True))

    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            return last_tick_on(_next_weekday(today, index))

    if _NEXT_WEEK.search(text):
        return last_tick_on(_next_weekday(today, _WEEKDAYS["sunday"]) + timedelta(days=7))

    if _THIS_WEEK.search(text):
        return last_tick_on(_next_weekday(today, _WEEKDAYS["sunday"], allow_today=True))

    if match := _ORDINAL_DAY.search(text):
        day = _next_day_of_month(today, int(match.group(1)))
        return last_tick_on(day) if day is not None else None

    return None
