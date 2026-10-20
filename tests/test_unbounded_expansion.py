"""
Tests for expanding recurrences when the search has no ``start`` or ``end``.

Such searches used to expand recurrences between 1970 and 2038 only, so
occurrences outside that window were never seen.  See
https://github.com/pycalendar/icalendar-searcher/issues/23
"""

from datetime import datetime, timezone

import pytest
from icalendar import Calendar

from icalendar_searcher import Searcher


def _cal(*lines: str) -> Calendar:
    body = "\r\n".join(lines)
    return Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:x\r\nDTSTAMP:20261001T000000Z\r\n{body}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


DAILY = ("DTSTART:20260101T100000Z", "DURATION:PT1H", "RRULE:FREQ=DAILY")
YEARLY_FROM_1900 = ("DTSTART:19000101T100000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY")
ALARM = ("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:x", "TRIGGER:-PT15M", "END:VALARM")


@pytest.mark.parametrize("expand", [True, False])
def test_start_only_after_2038(expand: bool) -> None:
    """With only start given, the expansion used to end in 2038, before the start."""
    searcher = Searcher(event=True, start=_utc(2040, 1, 1), expand=expand)
    result = searcher.check_component(_cal(*DAILY))
    assert result
    if expand:
        assert next(iter(result)).start == _utc(2040, 1, 1, 10)


@pytest.mark.parametrize("expand", [True, False])
def test_end_only_before_1970(expand: bool) -> None:
    searcher = Searcher(event=True, end=_utc(1960, 1, 1), expand=expand)
    result = searcher.check_component(_cal(*YEARLY_FROM_1900))
    assert result
    if expand:
        assert len(list(result)) == 60


def test_no_bounds_finite_before_1970() -> None:
    cal = _cal("DTSTART:19000101T100000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY;COUNT=3")
    result = Searcher(event=True, expand=True).check_component(cal)
    assert [x.start.year for x in result] == [1900, 1901, 1902]


def test_no_bounds_finite_after_2038() -> None:
    cal = _cal("DTSTART:20500101T100000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY;COUNT=3")
    result = Searcher(event=True, expand=True).check_component(cal)
    assert [x.start.year for x in result] == [2050, 2051, 2052]


@pytest.mark.parametrize("max_occurrences", [1825, 3])
def test_no_bounds_expands_around_now(max_occurrences: int) -> None:
    """An unbounded rule without start or end gives at least max_occurrences
    occurrences, but not many more, about a third of them before now."""
    cal = _cal("DTSTART:20000101T100000Z", "DURATION:PT1H", "RRULE:FREQ=DAILY")
    result = list(
        Searcher(event=True, expand=True, max_occurrences=max_occurrences).check_component(cal)
    )
    assert max_occurrences <= len(result) <= 2 * max_occurrences
    now = datetime.now(timezone.utc)
    before = sum(1 for x in result if x.start < now)
    assert 0.2 <= before / len(result) <= 0.5


def test_no_end_counts_from_start() -> None:
    searcher = Searcher(event=True, start=_utc(2030, 1, 1), expand=True, max_occurrences=10)
    result = list(searcher.check_component(_cal(*DAILY)))
    assert 10 <= len(result) <= 20
    assert result[0].start == _utc(2030, 1, 1, 10)
    assert all(x.start >= _utc(2030, 1, 1) for x in result)


def test_max_occurrences_none() -> None:
    cal = _cal("DTSTART:20500101T100000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY;COUNT=3000")
    result = Searcher(event=True, expand=True, max_occurrences=None).check_component(cal)
    assert len(list(result)) == 3000


@pytest.mark.parametrize(
    ("alarm_start", "alarm_end", "match"),
    [
        ## The case from the issue: an alarm search over occurrences after 2037
        (_utc(2045, 6, 1, 9), _utc(2045, 6, 1, 10), True),
        ## and before 1970
        (_utc(1950, 1, 1, 9), _utc(1950, 1, 1, 10), True),
        ## The alarm fires at 09:45, not in this range
        (_utc(2045, 6, 1, 9), _utc(2045, 6, 1, 9, 30), False),
    ],
)
def test_alarm_search_without_start_and_end(
    alarm_start: datetime, alarm_end: datetime, match: bool
) -> None:
    """Far beyond max_occurrences: the alarm range limits the expansion instead."""
    cal = _cal("DTSTART:19000101T100000Z", "DURATION:PT1H", "RRULE:FREQ=DAILY", *ALARM)
    searcher = Searcher(event=True, alarm_start=alarm_start, alarm_end=alarm_end)
    assert bool(searcher.check_component(cal)) == match


@pytest.mark.parametrize(
    ("dtstart", "duration"),
    [
        ## The case from the issue: the occurrences end beyond year 9999
        ("DTSTART:20260101T000000Z", "DURATION:P3650000D"),
        ## They end within the range, but no window within it absorbs them
        ("DTSTART:01000101T000000Z", "DURATION:P3000000D"),
    ],
)
@pytest.mark.parametrize("bounds", [{}, {"start": datetime.min.replace(tzinfo=timezone.utc)}])
@pytest.mark.parametrize("expand", [True, False])
def test_duration_longer_than_the_datetime_range(
    dtstart: str, duration: str, bounds: dict, expand: bool
) -> None:
    """Such a component cannot be expanded; the master is matched alone."""
    cal = _cal(dtstart, duration, "RRULE:FREQ=YEARLY;COUNT=2")
    if bounds:
        bounds["end"] = datetime.max.replace(tzinfo=timezone.utc)
    result = Searcher(event=True, expand=expand, **bounds).check_component(cal)
    assert result
    if expand:
        assert len(list(result)) == 1


@pytest.mark.parametrize(
    ("lines", "years"),
    [
        (
            ("DTSTART:99900101T100000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY"),
            list(range(9990, 10000)),
        ),
        ## An RDATE before DTSTART
        (("DTSTART:20260101T100000Z", "DURATION:PT1H", "RDATE:19000101T100000Z"), [1900, 2026]),
    ],
)
def test_no_bounds_far_from_now(lines: tuple, years: list) -> None:
    result = Searcher(event=True, expand=True).check_component(_cal(*lines))
    assert sorted(x.start.year for x in result) == years


def test_alarm_search_with_absolute_trigger() -> None:
    """An absolute alarm fires at the same time for every occurrence."""
    cal = _cal(
        *DAILY,
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:x",
        "TRIGGER;VALUE=DATE-TIME:20450601T094500Z",
        "END:VALARM",
    )
    searcher = Searcher(event=True, alarm_start=_utc(2045, 6, 1, 9), alarm_end=_utc(2045, 6, 1, 10))
    assert searcher.check_component(cal)


def test_alarm_search_recurring_todo_without_dtstart() -> None:
    """The alarm range also bounds a task with DUE but no DTSTART."""
    cal = Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n"
        "BEGIN:VTODO\r\nUID:x\r\nDTSTAMP:20261001T000000Z\r\n"
        "DUE:20260101T100000Z\r\nRRULE:FREQ=DAILY\r\n"
        "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:x\r\n"
        "TRIGGER;RELATED=END:-PT15M\r\nEND:VALARM\r\n"
        "END:VTODO\r\nEND:VCALENDAR\r\n"
    )
    searcher = Searcher(
        todo=True, alarm_start=_utc(2045, 6, 1, 9, 40), alarm_end=_utc(2045, 6, 1, 9, 50)
    )
    assert searcher.check_component(cal)
