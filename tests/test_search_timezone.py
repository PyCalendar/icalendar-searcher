"""
Tests for matching date-only and floating values against a timezone-aware search range.

Date-only (all-day) values and floating datetimes have no time zone of
their own.  When the search range is timezone-aware, they should be
interpreted in the time zone of the search range, not in the time zone
of the Python process.  See
https://github.com/pycalendar/icalendar-searcher/issues/17
"""

import os
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from icalendar import Alarm, Calendar, Event, Journal, Todo

from icalendar_searcher import Searcher

PROCESS_TIMEZONES = ["Europe/Berlin", "UTC", "America/New_York", "Asia/Tokyo"]
SEARCH_TIMEZONES = ["Europe/Berlin", "America/Los_Angeles", "Asia/Kolkata"]


@pytest.fixture(params=PROCESS_TIMEZONES)
def process_tz(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run the test with the process local time zone set to each of PROCESS_TIMEZONES."""
    orig = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield request.param
    finally:
        if orig is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = orig
        time.tzset()


def _cal(*components: Event | Todo | Journal) -> Calendar:
    cal = Calendar()
    for comp in components:
        cal.add_component(comp)
    return cal


def _all_day_event(day: date, uid: str = "allday") -> Event:
    event = Event()
    event.add("uid", uid)
    event.add("dtstamp", datetime(2026, 10, 1))
    event.add("dtstart", day)
    event.add("dtend", day + timedelta(days=1))
    return event


def _day_search(day: date, tz: ZoneInfo, **kwargs: object) -> Searcher:
    """A searcher covering the whole day in the time zone tz."""
    return Searcher(
        event=True,
        start=datetime.combine(day, datetime.min.time(), tzinfo=tz),
        end=datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz),
        **kwargs,
    )


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_event_not_matching_next_day(process_tz: str, search_tz: str) -> None:
    """The reproduction from issue 17: an Oct 11 event must not match an Oct 12 search."""
    cal = _cal(_all_day_event(date(2026, 10, 11)))
    searcher = _day_search(date(2026, 10, 12), ZoneInfo(search_tz))
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_event_not_matching_previous_day(process_tz: str, search_tz: str) -> None:
    cal = _cal(_all_day_event(date(2026, 10, 11)))
    searcher = _day_search(date(2026, 10, 10), ZoneInfo(search_tz))
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_event_matching_same_day(process_tz: str, search_tz: str) -> None:
    cal = _cal(_all_day_event(date(2026, 10, 11)))
    searcher = _day_search(date(2026, 10, 11), ZoneInfo(search_tz))
    assert searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_event_short_range_at_midnight(process_tz: str, search_tz: str) -> None:
    """A 15 minute search just after midnight on the day of the event should match."""
    tz = ZoneInfo(search_tz)
    cal = _cal(_all_day_event(date(2026, 10, 11)))
    searcher = Searcher(
        event=True,
        start=datetime(2026, 10, 11, 0, 0, tzinfo=tz),
        end=datetime(2026, 10, 11, 0, 15, tzinfo=tz),
    )
    assert searcher.check_component(cal)
    searcher = Searcher(
        event=True,
        start=datetime(2026, 10, 12, 0, 0, tzinfo=tz),
        end=datetime(2026, 10, 12, 0, 15, tzinfo=tz),
    )
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_floating_event(process_tz: str, search_tz: str) -> None:
    """A floating (naive) DTSTART is interpreted as wall time in the search time zone."""
    tz = ZoneInfo(search_tz)
    event = Event()
    event.add("uid", "floating")
    event.add("dtstamp", datetime(2026, 10, 1))
    event.add("dtstart", datetime(2026, 10, 11, 9, 0))
    event.add("dtend", datetime(2026, 10, 11, 10, 0))
    cal = _cal(event)
    searcher = Searcher(
        event=True,
        start=datetime(2026, 10, 11, 9, 30, tzinfo=tz),
        end=datetime(2026, 10, 11, 9, 45, tzinfo=tz),
    )
    assert searcher.check_component(cal)
    searcher = Searcher(
        event=True,
        start=datetime(2026, 10, 11, 10, 0, tzinfo=tz),
        end=datetime(2026, 10, 11, 11, 0, tzinfo=tz),
    )
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_todo(process_tz: str, search_tz: str) -> None:
    todo = Todo()
    todo.add("uid", "allday-todo")
    todo.add("dtstamp", datetime(2026, 10, 1))
    todo.add("dtstart", date(2026, 10, 11))
    todo.add("due", date(2026, 10, 12))
    cal = _cal(todo)
    tz = ZoneInfo(search_tz)
    searcher = Searcher(
        todo=True,
        start=datetime(2026, 10, 12, 0, 1, tzinfo=tz),
        end=datetime(2026, 10, 13, tzinfo=tz),
    )
    assert not searcher.check_component(cal)
    searcher = Searcher(
        todo=True,
        start=datetime(2026, 10, 11, 23, 0, tzinfo=tz),
        end=datetime(2026, 10, 11, 23, 59, tzinfo=tz),
    )
    assert searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
@pytest.mark.parametrize("expand", [True, False])
def test_recurring_all_day_event(process_tz: str, search_tz: str, expand: bool) -> None:
    """A weekly all-day event on Sundays should match Sunday, but not Monday."""
    event = _all_day_event(date(2026, 10, 4), uid="weekly-allday")
    event.add("rrule", {"FREQ": "WEEKLY"})
    cal = _cal(event)
    tz = ZoneInfo(search_tz)

    searcher = _day_search(date(2026, 10, 12), tz, expand=expand)
    assert not list(searcher.check_component(cal) or [])

    searcher = _day_search(date(2026, 10, 11), tz, expand=expand)
    result = list(searcher.check_component(cal) or [])
    assert result
    if expand:
        assert len(result) == 1
        assert result[0]["RECURRENCE-ID"].dt == date(2026, 10, 11)


def test_naive_search_range_uses_process_timezone(process_tz: str) -> None:
    """Without an aware search range, behaviour is unchanged: the process time zone is used."""
    cal = _cal(_all_day_event(date(2026, 10, 11)))
    searcher = Searcher(
        event=True, start=datetime(2026, 10, 11, 12, 0), end=datetime(2026, 10, 11, 13, 0)
    )
    assert searcher.check_component(cal)
    searcher = Searcher(event=True, start=datetime(2026, 10, 12), end=datetime(2026, 10, 13))
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_alarm_on_all_day_event(process_tz: str, search_tz: str) -> None:
    """An alarm one hour before an all-day event fires at 23:00 the day before, in the search tz."""
    event = _all_day_event(date(2026, 10, 11))
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(hours=-1))
    event.add_component(alarm)
    cal = _cal(event)
    tz = ZoneInfo(search_tz)
    searcher = Searcher(
        alarm_start=datetime(2026, 10, 10, 22, 30, tzinfo=tz),
        alarm_end=datetime(2026, 10, 10, 23, 30, tzinfo=tz),
    )
    assert searcher.check_component(cal)
    searcher = Searcher(
        alarm_start=datetime(2026, 10, 10, 23, 30, tzinfo=tz),
        alarm_end=datetime(2026, 10, 11, 0, 30, tzinfo=tz),
    )
    assert not searcher.check_component(cal)


def test_pytz_search_range_across_dst(process_tz: str) -> None:
    """With a pytz search range starting in winter, a summer all-day event uses the summer offset."""
    pytz = pytest.importorskip("pytz")
    berlin = pytz.timezone("Europe/Berlin")
    cal = _cal(_all_day_event(date(2026, 7, 12)))
    searcher = Searcher(
        event=True,
        start=berlin.localize(datetime(2026, 1, 1)),
        end=berlin.localize(datetime(2026, 7, 12, 0, 30)),
    )
    assert searcher.check_component(cal)
    searcher = Searcher(
        event=True,
        start=berlin.localize(datetime(2026, 1, 1)),
        end=berlin.localize(datetime(2026, 7, 11, 23, 30)),
    )
    assert not searcher.check_component(cal)


def test_alarm_on_all_day_event_across_dst(process_tz: str) -> None:
    """A TRIGGER of -PT24H is an exact duration, also across the end of DST."""
    tz = ZoneInfo("Europe/Berlin")
    ## DST ends 2026-10-25 03:00 CEST.  Midnight Oct 26 CET minus exactly
    ## 24 hours is 01:00 CEST on Oct 25.
    event = _all_day_event(date(2026, 10, 26))
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(hours=-24))
    event.add_component(alarm)
    cal = _cal(event)
    searcher = Searcher(
        alarm_start=datetime(2026, 10, 25, 0, 30, tzinfo=tz),
        alarm_end=datetime(2026, 10, 25, 1, 30, tzinfo=tz),
    )
    assert searcher.check_component(cal)
    searcher = Searcher(
        alarm_start=datetime(2026, 10, 24, 23, 30, tzinfo=tz),
        alarm_end=datetime(2026, 10, 25, 0, 30, tzinfo=tz),
    )
    assert not searcher.check_component(cal)


@pytest.mark.parametrize("search_tz", SEARCH_TIMEZONES)
def test_all_day_journal(process_tz: str, search_tz: str) -> None:
    """A journal with a date DTSTART spans that whole day (RFC 4791 section 9.9)."""
    journal = Journal()
    journal.add("uid", "allday-journal")
    journal.add("dtstamp", datetime(2026, 10, 1))
    journal.add("dtstart", date(2026, 10, 25))
    cal = _cal(journal)
    tz = ZoneInfo(search_tz)
    for day, expected in ((24, False), (25, True), (26, False)):
        searcher = Searcher(
            journal=True,
            start=datetime(2026, 10, day, 12, 0, tzinfo=tz),
            end=datetime(2026, 10, day, 13, 0, tzinfo=tz),
        )
        assert bool(searcher.check_component(cal)) is expected, day
    ## 23:30 on the day itself; Oct 25 is 25 hours long in Europe/Berlin
    searcher = Searcher(
        journal=True,
        start=datetime(2026, 10, 25, 23, 30, tzinfo=tz),
        end=datetime(2026, 10, 25, 23, 45, tzinfo=tz),
    )
    assert searcher.check_component(cal)
