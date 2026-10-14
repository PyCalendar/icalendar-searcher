"""
Tests for dates at the edges of the ``datetime`` range.

Converting a value within a day of ``datetime.min`` / ``datetime.max`` to
the time zone of the Python process, or adding a duration to it, overflows.
A search over the whole range, or a single component dated in year 1 or
year 9999, must neither make the search raise nor give a wrong answer.  See
https://github.com/pycalendar/icalendar-searcher/issues/19
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from icalendar import Alarm, Calendar

from icalendar_searcher import Searcher
from icalendar_searcher.utils import _normalize_dt

## Search ranges, by the kind of the bounds
FULL_RANGE = {
    "aware": (datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)),
    "naive": (datetime.min, datetime.max),
    "date": (date.min, date.max),
}
YEAR_2026 = {
    "aware": (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc)),
    "naive": (datetime(2026, 1, 1), datetime(2027, 1, 1)),
    "date": (date(2026, 1, 1), date(2027, 1, 1)),
}

EXTREME_DTSTARTS = [
    "DTSTART;VALUE=DATE:00010101",
    "DTSTART:00010101T000000",
    "DTSTART:00010101T000000Z",
    "DTSTART;VALUE=DATE:99991231",
    "DTSTART:99991231T235959",
    "DTSTART:99991231T235959Z",
]


def _cal(comp: str, *lines: str) -> Calendar:
    body = "\r\n".join(lines)
    return Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\n"
        f"BEGIN:{comp}\r\nUID:x\r\nDTSTAMP:20261001T000000Z\r\n{body}\r\n"
        f"END:{comp}\r\nEND:VCALENDAR\r\n"
    )


def _searcher(comp: str, bounds: tuple, **kwargs: object) -> Searcher:
    kind = {"VEVENT": "event", "VTODO": "todo", "VJOURNAL": "journal"}[comp]
    return Searcher(**{kind: True}, start=bounds[0], end=bounds[1], **kwargs)


@pytest.mark.parametrize("bounds", FULL_RANGE)
def test_full_range_search(process_tz: str, bounds: str) -> None:
    """The case from the issue: a search from datetime.min to datetime.max."""
    cal = _cal("VEVENT", "DTSTART:20261012T100000Z", "DTEND:20261012T110000Z")
    assert _searcher("VEVENT", FULL_RANGE[bounds]).check_component(cal)


@pytest.mark.parametrize("bounds", FULL_RANGE)
def test_full_range_search_recurring(process_tz: str, bounds: str) -> None:
    cal = _cal(
        "VEVENT", "DTSTART:20261012T100000Z", "DTEND:20261012T110000Z", "RRULE:FREQ=YEARLY;COUNT=3"
    )
    assert len(list(_searcher("VEVENT", FULL_RANGE[bounds], expand=True).check_component(cal))) == 3


@pytest.mark.parametrize(
    ("lines", "count"),
    [
        (("DTSTART:00010108T100000Z", "RRULE:FREQ=DAILY;COUNT=2"), 2),
        (("DTSTART:20250101T100000Z", "RRULE:FREQ=YEARLY;COUNT=1", "RDATE:99990601T100000Z"), 2),
        (("DTSTART:99991220T100000Z", "RRULE:FREQ=DAILY;COUNT=3"), 3),
        (("DTSTART;VALUE=DATE:99991220", "RRULE:FREQ=DAILY;COUNT=3"), 3),
        (("DTSTART:20260101T000000Z", "DURATION:P1000D", "RRULE:FREQ=YEARLY;COUNT=2"), 2),
    ],
)
@pytest.mark.parametrize("expand", [True, False])
def test_full_range_search_occurrences_near_the_ends(
    process_tz: str, lines: tuple, count: int, expand: bool
) -> None:
    """Occurrences a week inside year 1 or 9999, and long durations, are not lost."""
    cal = _cal("VEVENT", *lines)
    result = _searcher("VEVENT", FULL_RANGE["aware"], expand=expand).check_component(cal)
    if expand:
        assert len(list(result)) == count
    else:
        assert result


@pytest.mark.parametrize(
    ("lines", "count"),
    [
        (("DTSTART:00010101T100000Z", "RRULE:FREQ=DAILY;COUNT=2"), 2),
        (("DTSTART:99991229T100000Z", "RRULE:FREQ=DAILY"), 3),
        ## the occurrence on 9999-12-31 would end in year 10000
        (("DTSTART;VALUE=DATE:99991230", "RRULE:FREQ=DAILY"), 1),
    ],
)
def test_full_range_search_occurrences_at_the_ends(
    process_tz: str, lines: tuple, count: int
) -> None:
    """Occurrences within days of the ends of the range may be left out, but must not raise."""
    cal = _cal("VEVENT", *lines)
    result = _searcher("VEVENT", FULL_RANGE["aware"], expand=True).check_component(cal)
    assert len(list(result) if result else []) <= count


@pytest.mark.parametrize("bounds", YEAR_2026)
@pytest.mark.parametrize("dtstart", EXTREME_DTSTARTS)
@pytest.mark.parametrize("comp", ["VEVENT", "VTODO", "VJOURNAL"])
def test_extreme_component_date(process_tz: str, comp: str, dtstart: str, bounds: str) -> None:
    """A component dated at the edge of the range matches the full range only.

    Naive and date bounds are local time (and a date end is exclusive), so
    the very edges may fall outside them; those only must not raise.
    """
    cal = _cal(comp, dtstart)
    assert not _searcher(comp, YEAR_2026[bounds]).check_component(cal)
    full_range_match = _searcher(comp, FULL_RANGE[bounds]).check_component(cal)
    if bounds == "aware":
        assert full_range_match


@pytest.mark.parametrize("dtstart", EXTREME_DTSTARTS)
def test_extreme_component_date_pytz_search(process_tz: str, dtstart: str) -> None:
    pytz = pytest.importorskip("pytz")
    tz = pytz.timezone("America/New_York")
    searcher = Searcher(
        event=True, start=tz.localize(datetime(2026, 1, 1)), end=tz.localize(datetime(2027, 1, 1))
    )
    assert not searcher.check_component(_cal("VEVENT", dtstart))


@pytest.mark.parametrize("dtstart", ["DTSTART:00010101T000000Z", "DTSTART;VALUE=DATE:99991231"])
def test_extreme_component_date_alarm_search(process_tz: str, dtstart: str) -> None:
    cal = _cal("VEVENT", dtstart)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(hours=-1))
    alarm.add("repeat", 2)
    alarm.add("duration", timedelta(days=1))
    cal.subcomponents[0].add_component(alarm)
    year_2026 = YEAR_2026["aware"]
    assert not Searcher(
        event=True, alarm_start=year_2026[0], alarm_end=year_2026[1]
    ).check_component(cal)
    full_range = FULL_RANGE["aware"]
    assert Searcher(event=True, alarm_start=full_range[0], alarm_end=full_range[1]).check_component(
        cal
    )


def test_date_bounds_with_expansion() -> None:
    cal = _cal(
        "VEVENT", "DTSTART:20261012T100000Z", "DTEND:20261012T110000Z", "RRULE:FREQ=MONTHLY;COUNT=3"
    )
    searcher = Searcher(event=True, start=date(2026, 1, 1), end=date(2027, 1, 1), expand=True)
    assert len(list(searcher.check_component(cal))) == 3


@pytest.mark.parametrize("process_tz", ["America/New_York", "Europe/Berlin"], indirect=True)
def test_floating_value_at_the_end_keeps_its_neighbours_offset(process_tz: str) -> None:
    """Near datetime.max, a floating value gets the offset values just before it
    get, not the current offset of the process time zone (which may be DST)."""
    near_end = _normalize_dt(datetime(9999, 12, 31, 23, 0))
    day_before = _normalize_dt(datetime(9999, 12, 29, 23, 0))
    assert near_end.utcoffset() == day_before.utcoffset()
    assert near_end - day_before == timedelta(days=2)


@pytest.mark.parametrize(
    "lines",
    [
        ("DTSTART;VALUE=DATE:20260105", "DTEND:20260106T100000Z"),
        ("DTSTART:20260105T100000Z", "DTEND:20260105T110000"),
    ],
)
def test_ordinary_recurring_event_with_mixed_start_and_end_kinds(
    process_tz: str, lines: tuple
) -> None:
    """Expansion of ordinary dates must not depend on DTSTART and DTEND being of one kind."""
    cal = _cal("VEVENT", *lines, "RRULE:FREQ=WEEKLY;COUNT=60")
    searcher = Searcher(
        event=True,
        start=datetime(2026, 12, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 10, tzinfo=timezone.utc),
    )
    assert searcher.check_component(cal)


@pytest.mark.parametrize(
    ("dtstart", "bounds"),
    [
        (
            "DTSTART:99991201T000000Z",
            (datetime(9999, 12, 30, tzinfo=timezone.utc), FULL_RANGE["aware"][1]),
        ),
        (
            "DTSTART:00010101T000000Z",
            (FULL_RANGE["aware"][0], datetime(1, 1, 2, tzinfo=timezone.utc)),
        ),
        ("DTSTART:99991201T000000Z", (date(9999, 12, 30), date.max)),
    ],
)
def test_narrow_search_window_at_the_ends(process_tz: str, dtstart: str, bounds: tuple) -> None:
    """A search window close to the ends of the range must not raise."""
    cal = _cal("VEVENT", dtstart, "DURATION:P2D", "RRULE:FREQ=DAILY")
    _searcher("VEVENT", bounds, expand=True).check_component(cal)


@pytest.mark.parametrize(
    "lines", [("DTSTART:00010101T000000Z", "DURATION:P1D"), ("DTSTART;VALUE=DATE:00010101",)]
)
def test_full_range_search_occurrences_with_duration_at_the_start(
    process_tz: str, lines: tuple
) -> None:
    """Occurrences ending within a few days of datetime.min may be left out, but must not raise."""
    cal = _cal("VEVENT", *lines, "RRULE:FREQ=DAILY;COUNT=10")
    occurrences = list(_searcher("VEVENT", FULL_RANGE["aware"], expand=True).check_component(cal))
    assert 7 <= len(occurrences) <= 10


def test_naive_full_range_far_east_event_near_year_1(process_tz: str) -> None:
    cal = _cal("VEVENT", "DTSTART;TZID=Asia/Tokyo:00010101T050000", "RRULE:FREQ=DAILY;COUNT=2")
    _searcher("VEVENT", FULL_RANGE["naive"], expand=True).check_component(cal)


def test_negative_duration_at_the_start_does_not_reach_forward(process_tz: str) -> None:
    cal = _cal("VTODO", "DTSTART:00010101T000000Z", "DURATION:-PT1H")
    assert not _searcher("VTODO", YEAR_2026["aware"]).check_component(cal)
