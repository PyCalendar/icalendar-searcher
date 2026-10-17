"""A recurrence set may be defined by RDATE alone, without any RRULE.

RFC 5545 section 3.8.5.2: the recurrence set is the complete set of
recurrence instances, built from the RRULE, RDATE and EXDATE properties.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from icalendar import Alarm, Calendar, Event, Todo

from icalendar_searcher import Searcher

UTC = timezone.utc


def rdate_master() -> Event:
    event = Event()
    event.add("uid", "rdate-series")
    event.add("summary", "Dentist")
    event.add("dtstart", datetime(2025, 1, 6, 10, 0, tzinfo=UTC))
    event.add("dtend", datetime(2025, 1, 6, 11, 0, tzinfo=UTC))
    event.add(
        "rdate",
        [datetime(2025, 2, 3, 10, 0, tzinfo=UTC), datetime(2025, 3, 3, 10, 0, tzinfo=UTC)],
    )
    return event


def override() -> Event:
    event = Event()
    event.add("uid", "rdate-series")
    event.add("summary", "Dentist, moved")
    event.add("recurrence-id", datetime(2025, 2, 3, 10, 0, tzinfo=UTC))
    event.add("dtstart", datetime(2025, 2, 4, 14, 0, tzinfo=UTC))
    event.add("dtend", datetime(2025, 2, 4, 15, 0, tzinfo=UTC))
    return event


def calendar(*events: Event) -> Calendar:
    cal = Calendar()
    for event in events:
        cal.add_component(event)
    return cal


@pytest.mark.parametrize("override_first", [False, True])
def test_rdate_master_with_override_is_a_valid_recurrence_set(override_first: bool) -> None:
    events = (override(), rdate_master()) if override_first else (rdate_master(), override())
    components = Searcher()._validate_and_normalize_component(calendar(*events))
    assert "recurrence-id" not in components[0]
    assert "recurrence-id" in components[1]


def test_rdate_master_with_override_can_be_searched() -> None:
    searcher = Searcher(event=True)
    assert searcher.check_component(calendar(rdate_master(), override()))


def test_time_range_finds_an_rdate_occurrence() -> None:
    searcher = Searcher(
        event=True,
        start=datetime(2025, 3, 1, tzinfo=UTC),
        end=datetime(2025, 3, 31, tzinfo=UTC),
    )
    assert searcher.check_component(calendar(rdate_master()))


def test_time_range_finds_an_override_of_an_rdate_series() -> None:
    searcher = Searcher(
        event=True,
        expand=True,
        start=datetime(2025, 2, 1, tzinfo=UTC),
        end=datetime(2025, 2, 28, tzinfo=UTC),
    )
    found = list(searcher.check_component(calendar(rdate_master(), override())))
    assert [str(x["summary"]) for x in found] == ["Dentist, moved"]


def test_expand_lists_every_rdate_occurrence() -> None:
    searcher = Searcher(
        event=True,
        expand=True,
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 12, 31, tzinfo=UTC),
    )
    found = list(searcher.check_component(calendar(rdate_master())))
    assert [x.start for x in found] == [
        datetime(2025, 1, 6, 10, 0, tzinfo=UTC),
        datetime(2025, 2, 3, 10, 0, tzinfo=UTC),
        datetime(2025, 3, 3, 10, 0, tzinfo=UTC),
    ]


@pytest.mark.parametrize(("text", "matches"), [("moved", True), ("cancelled", False)])
def test_override_may_match_when_master_does_not(text: str, matches: bool) -> None:
    searcher = Searcher(event=True)
    searcher.add_property_filter("summary", text, operator="contains")
    assert bool(searcher.check_component(calendar(rdate_master(), override()))) is matches


def test_time_range_finds_an_rdate_occurrence_of_a_task() -> None:
    task = Todo()
    task.add("uid", "rdate-task")
    task.add("summary", "Water the plants")
    task.add("dtstart", datetime(2025, 1, 6, 10, 0, tzinfo=UTC))
    task.add("due", datetime(2025, 1, 6, 11, 0, tzinfo=UTC))
    task.add("rdate", [datetime(2025, 3, 3, 10, 0, tzinfo=UTC)])
    cal = Calendar()
    cal.add_component(task)
    searcher = Searcher(
        todo=True,
        start=datetime(2025, 3, 1, tzinfo=UTC),
        end=datetime(2025, 3, 31, tzinfo=UTC),
    )
    assert searcher.check_component(cal)


def test_time_range_finds_an_all_day_rdate_occurrence() -> None:
    event = Event()
    event.add("uid", "rdate-all-day")
    event.add("summary", "Holiday")
    event.add("dtstart", date(2025, 1, 6))
    event.add("dtend", date(2025, 1, 7))
    event.add("rdate", [date(2025, 3, 3)])
    searcher = Searcher(
        event=True,
        start=datetime(2025, 3, 1, tzinfo=UTC),
        end=datetime(2025, 3, 31, tzinfo=UTC),
    )
    assert searcher.check_component(calendar(event))


def test_alarm_range_finds_an_alarm_of_an_rdate_occurrence() -> None:
    event = rdate_master()
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", "Dentist")
    alarm.add("trigger", timedelta(minutes=-15))
    event.add_component(alarm)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 3, 3, 9, 40, tzinfo=UTC),
        alarm_end=datetime(2025, 3, 3, 9, 50, tzinfo=UTC),
    )
    assert searcher.check_component(calendar(event))
