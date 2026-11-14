"""RFC 4791 section 9.9 time-range tables, transcribed from the RFC text.

The oracles below are the conditions of the tables *verbatim* (including the
``<`` / ``<=`` differences), written without reference to ``filters.py``.  Each
component state is exercised against a grid of search ranges whose boundaries
touch the component's own timestamps, because the ``<`` versus ``<=`` choices
are exactly where an implementation derived from the code (rather than the
RFC) goes wrong.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from icalendar import Event, Journal, Todo

from icalendar_searcher import Searcher

UTC = timezone.utc
H = timedelta(hours=1)
T0 = datetime(2025, 6, 10, 12, 0, tzinfo=UTC)

## Search boundaries: every offset from -2h to +4h around T0, so that range
## edges coincide with, fall just before and just after each timestamp used.
OFFSETS = range(-2, 5)
RANGES = [(T0 + a * H, T0 + b * H) for a, b in itertools.product(OFFSETS, OFFSETS) if a < b]


def _searcher(cls: str, start: datetime, end: datetime) -> Searcher:
    return Searcher(**{cls: True}, start=start, end=end, include_completed=True)


def _make(cls: type, **props: Any) -> Any:
    comp = cls()
    comp.add("uid", "matrix-test")
    comp.add("dtstamp", T0)
    for key, value in props.items():
        comp.add(key, value)
    return comp


## ---- VEVENT (table 1) --------------------------------------------------

Oracle = Callable[[datetime, datetime], bool]

EVENT_CASES: dict[str, tuple[dict[str, Any], Oracle]] = {
    "dtstart+dtend": (
        {"dtstart": T0, "dtend": T0 + 2 * H},
        lambda s, e: s < T0 + 2 * H and e > T0,
    ),
    "dtstart+duration>0": (
        {"dtstart": T0, "duration": 2 * H},
        lambda s, e: s < T0 + 2 * H and e > T0,
    ),
    "dtstart+duration=0": (
        {"dtstart": T0, "duration": timedelta(0)},
        lambda s, e: s <= T0 and e > T0,
    ),
    "dtstart only (date-time)": (
        {"dtstart": T0},
        lambda s, e: s <= T0 and e > T0,
    ),
}


@pytest.mark.parametrize("name", EVENT_CASES)
@pytest.mark.parametrize("start,end", RANGES)
def test_vevent_matrix(name: str, start: datetime, end: datetime) -> None:
    props, oracle = EVENT_CASES[name]
    assert bool(_searcher("event", start, end).check_component(_make(Event, **props))) == (
        oracle(start, end)
    )


## ---- VTODO (table 2) ---------------------------------------------------

## Keys: (DTSTART, DURATION, DUE, COMPLETED, CREATED) presence.
## Timestamps are chosen so DTSTART <= DUE, as the RFC requires.
DTSTART = T0
DUE = T0 + 2 * H
DURATION = 2 * H
COMPLETED = T0 + 1 * H
CREATED = T0

TODO_CASES: dict[str, tuple[dict[str, Any], Oracle]] = {
    "DTSTART+DURATION": (
        {"dtstart": DTSTART, "duration": DURATION},
        lambda s, e: s <= DTSTART + DURATION and (e > DTSTART or e >= DTSTART + DURATION),
    ),
    "DTSTART+DUE": (
        {"dtstart": DTSTART, "due": DUE},
        lambda s, e: (s < DUE or s <= DTSTART) and (e > DTSTART or e >= DUE),
    ),
    "DTSTART only": (
        {"dtstart": DTSTART},
        lambda s, e: s <= DTSTART and e > DTSTART,
    ),
    "DUE only": (
        {"due": DUE},
        lambda s, e: s < DUE and e >= DUE,
    ),
    "COMPLETED+CREATED": (
        {"completed": COMPLETED, "created": CREATED},
        lambda s, e: (s <= CREATED or s <= COMPLETED) and (e >= CREATED or e >= COMPLETED),
    ),
    "COMPLETED only": (
        {"completed": COMPLETED},
        lambda s, e: s <= COMPLETED and e >= COMPLETED,
    ),
    "CREATED only": (
        {"created": CREATED},
        lambda s, e: e > CREATED,
    ),
    ## Not valid per RFC 5545, but the table's OR-forms are written for it
    "DUE before DTSTART": (
        {"dtstart": DTSTART + 2 * H, "due": DTSTART},
        lambda s, e: (
            (s < DTSTART or s <= DTSTART + 2 * H) and (e > DTSTART + 2 * H or e >= DTSTART)
        ),
    ),
    "negative DURATION": (
        {"dtstart": DTSTART + 2 * H, "duration": -2 * H},
        lambda s, e: s <= DTSTART and (e > DTSTART + 2 * H or e >= DTSTART),
    ),
    "zero DURATION": (
        {"dtstart": DTSTART, "duration": timedelta(0)},
        lambda s, e: s <= DTSTART and (e > DTSTART or e >= DTSTART),
    ),
    "DUE equal to DTSTART": (
        {"dtstart": DTSTART, "due": DTSTART},
        lambda s, e: (s < DTSTART or s <= DTSTART) and (e > DTSTART or e >= DTSTART),
    ),
    "COMPLETED before CREATED": (
        {"completed": T0, "created": T0 + 1 * H},
        lambda s, e: (s <= T0 + 1 * H or s <= T0) and (e >= T0 + 1 * H or e >= T0),
    ),
    "no timestamps": (
        {},
        lambda s, e: True,
    ),
}


@pytest.mark.parametrize("name", TODO_CASES)
@pytest.mark.parametrize("start,end", RANGES)
def test_vtodo_matrix(name: str, start: datetime, end: datetime) -> None:
    props, oracle = TODO_CASES[name]
    assert bool(_searcher("todo", start, end).check_component(_make(Todo, **props))) == (
        oracle(start, end)
    )


## ---- VJOURNAL (table 3) ------------------------------------------------


@pytest.mark.parametrize("start,end", RANGES)
def test_vjournal_datetime(start: datetime, end: datetime) -> None:
    journal = _make(Journal, dtstart=T0)
    assert bool(_searcher("journal", start, end).check_component(journal)) == (
        start <= T0 and end > T0
    )


@pytest.mark.parametrize("start,end", RANGES)
def test_vjournal_without_dtstart_is_never_found(start: datetime, end: datetime) -> None:
    assert not _searcher("journal", start, end).check_component(_make(Journal))


## ---- open-ended ranges -------------------------------------------------
## RFC 4791 section 9.9: "start" and "end" are both optional on the wire; an
## open bound must behave as minus/plus infinity in every table row.

NEG_INF = datetime(1, 1, 2, tzinfo=UTC)
POS_INF = datetime(9998, 1, 1, tzinfo=UTC)
CLASSES = {Event: "event", Todo: "todo"}


@pytest.mark.parametrize("name", EVENT_CASES)
@pytest.mark.parametrize("offset", OFFSETS)
def test_vevent_open_ended(name: str, offset: int) -> None:
    props, oracle = EVENT_CASES[name]
    comp = _make(Event, **props)
    point = T0 + offset * H
    only_start = Searcher(event=True, start=point)
    only_end = Searcher(event=True, end=point)
    assert bool(only_start.check_component(comp)) == oracle(point, POS_INF)
    assert bool(only_end.check_component(comp)) == oracle(NEG_INF, point)


@pytest.mark.parametrize("name", TODO_CASES)
@pytest.mark.parametrize("offset", OFFSETS)
def test_vtodo_open_ended(name: str, offset: int) -> None:
    props, oracle = TODO_CASES[name]
    comp = _make(Todo, **props)
    point = T0 + offset * H
    only_start = Searcher(todo=True, start=point, include_completed=True)
    only_end = Searcher(todo=True, end=point, include_completed=True)
    assert bool(only_start.check_component(comp)) == oracle(point, POS_INF)
    assert bool(only_end.check_component(comp)) == oracle(NEG_INF, point)


## ---- DATE values: effective duration P1D -------------------------------

DAY = datetime(2025, 6, 10, tzinfo=UTC)
D = timedelta(days=1)


@pytest.mark.parametrize(
    "offset_a,offset_b", [(a, b) for a in range(-2, 4) for b in range(-1, 5) if a < b]
)
def test_all_day_event_and_journal_cover_one_day(offset_a: int, offset_b: int) -> None:
    start, end = DAY + offset_a * D / 2, DAY + offset_b * D / 2
    event = _make(Event, dtstart=DAY.date())
    journal = _make(Journal, dtstart=DAY.date())
    expected = start < DAY + D and end > DAY
    assert bool(_searcher("event", start, end).check_component(event)) == expected
    assert bool(_searcher("journal", start, end).check_component(journal)) == expected


def test_vevent_without_dtstart_is_an_error() -> None:
    from icalendar import error

    comp = _make(Event)
    with pytest.raises(error.IncompleteComponent):
        _searcher("event", T0, T0 + H).check_component(comp)


@pytest.mark.parametrize("year", [1960, 2040])
def test_vtodo_open_ended_beyond_1970_2038(year: int) -> None:
    """An open bound is infinite, not 1970 or 2038."""
    when = datetime(year, 1, 1, tzinfo=UTC)
    todo = _make(Todo, dtstart=when)
    assert Searcher(todo=True, start=when - H).check_component(todo)
    assert Searcher(todo=True, end=when + H).check_component(todo)
