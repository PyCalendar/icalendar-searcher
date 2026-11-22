"""Date-time sort keys compare instants, not wall-clock times.

Dates and floating date-times have no time zone of their own; like the
time-range filters, the sorting reads them in the time zone of the Python
process.  The tests below hold for any process time zone.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from icalendar import Event, Todo

from icalendar_searcher import Searcher

UTC = timezone.utc
OSLO = ZoneInfo("Europe/Oslo")
## UTC+14, ahead of every other time zone
KIRITIMATI = ZoneInfo("Pacific/Kiritimati")


def _comp(uid: str, cls: type = Event, **props: Any) -> Any:
    comp = cls()
    comp.add("uid", uid)
    for key, value in props.items():
        comp.add(key, value)
    return comp


def _order(key: str, comps: list, reversed: bool = False) -> list[str]:
    searcher = Searcher()
    searcher.add_sort_key(key, reversed=reversed)
    return [str(c["UID"]) for c in searcher.sort(comps)]


@pytest.mark.parametrize("reversed", [False, True])
def test_dtstart_in_different_time_zones(reversed: bool) -> None:
    ## 11:00 in Oslo is 10:00 UTC, before 10:30 UTC
    comps = [
        _comp("utc", dtstart=datetime(2025, 1, 1, 10, 30, tzinfo=UTC)),
        _comp("oslo", dtstart=datetime(2025, 1, 1, 11, 0, tzinfo=OSLO)),
    ]
    expected = ["oslo", "utc"]
    assert _order("DTSTART", comps, reversed) == (expected[::-1] if reversed else expected)


def test_due_in_different_time_zones() -> None:
    ## 23:00 on the 1st in Kiritimati is 09:00 UTC, before 12:00 UTC
    comps = [
        _comp("utc", Todo, due=datetime(2025, 1, 1, 12, 0, tzinfo=UTC)),
        _comp("kiritimati", Todo, due=datetime(2025, 1, 1, 23, 0, tzinfo=KIRITIMATI)),
    ]
    assert _order("DUE", comps) == ["kiritimati", "utc"]


def test_date_against_date_time() -> None:
    ## Midnight starting the 2nd is after 08:00 UTC on the 1st in every time zone
    comps = [
        _comp("date", dtstart=date(2025, 1, 2)),
        _comp("kiritimati", dtstart=datetime(2025, 1, 1, 22, 0, tzinfo=KIRITIMATI)),
    ]
    assert _order("DTSTART", comps) == ["kiritimati", "date"]


def test_isnt_overdue_compares_instants() -> None:
    """A task due half an hour ago is overdue, even if its wall-clock DUE,
    in a time zone ahead of this one, is still in the future."""
    due = (datetime.now(UTC) - timedelta(minutes=30)).astimezone(KIRITIMATI)
    overdue = _comp("overdue", Todo, due=due)
    fine = _comp("fine", Todo, due=datetime.now(UTC) + timedelta(days=1))
    assert _order("isnt_overdue", [fine, overdue]) == ["overdue", "fine"]


def test_hasnt_started_compares_instants() -> None:
    """A task that started half an hour ago has started, even if its
    wall-clock DTSTART, in a time zone ahead of this one, is in the future."""
    dtstart = (datetime.now(UTC) - timedelta(minutes=30)).astimezone(KIRITIMATI)
    started = _comp("started", Todo, dtstart=dtstart)
    future = _comp("future", Todo, dtstart=datetime.now(UTC) + timedelta(days=1))
    assert _order("hasnt_started", [future, started]) == ["started", "future"]


def test_extreme_floating_dates_do_not_overflow() -> None:
    """Year 1 and year 9999 in local time may fall outside the datetime
    range in UTC; they sort at its ends instead of overflowing."""
    comps = [
        _comp("max", dtstart=datetime(9999, 12, 31, 23, 59)),
        _comp("min", dtstart=datetime(1, 1, 1, 0, 0)),
        _comp("mid", dtstart=datetime(2025, 1, 1, 0, 0)),
    ]
    assert _order("DTSTART", comps) == ["min", "mid", "max"]
    assert _order("DTSTART", comps, reversed=True) == ["max", "mid", "min"]


def test_extreme_floating_due_sorts_before_a_missing_due() -> None:
    """Year 9999 read in a time zone behind UTC lies past DT_MAX, the
    default of a missing DUE; a missing DUE still sorts last."""
    comps = [
        _comp("none", Todo),
        _comp("y9999", Todo, due=datetime(9999, 12, 31, 23, 59)),
    ]
    assert _order("DUE", comps) == ["y9999", "none"]
