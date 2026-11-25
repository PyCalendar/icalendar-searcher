from datetime import datetime, timedelta, timezone

import pytest
from icalendar import Calendar, Event
from icalendar.prop import vRecur

from icalendar_searcher import Searcher
from icalendar_searcher.searcher import _expansion_margin


def test_recurrence_simple_matches_exact_date() -> None:
    """Simple yearly recurrence should match when date range covers the first occurrence."""
    cal = Calendar()
    event = Event()
    event.add("uid", "yearly-event")
    event.add("summary", "New Year Celebration")
    event.add("dtstart", datetime(2025, 1, 1, 10, 0))
    event.add("dtend", datetime(2025, 1, 1, 12, 0))
    event.add("rrule", vRecur(FREQ="YEARLY"))
    cal.add_component(event)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1, 0, 0),
        end=datetime(2025, 1, 2, 0, 0),
    )
    assert searcher.check_component(cal)


def test_recurrence_simple_matches_future_occurrence() -> None:
    """Simple yearly recurrence should match when date range covers a future occurrence."""
    cal = Calendar()
    event = Event()
    event.add("uid", "yearly-event")
    event.add("summary", "New Year Celebration")
    event.add("dtstart", datetime(2025, 1, 1, 10, 0))
    event.add("dtend", datetime(2025, 1, 1, 12, 0))
    event.add("rrule", vRecur(FREQ="YEARLY"))
    cal.add_component(event)

    searcher = Searcher(
        event=True,
        start=datetime(2026, 1, 1, 0, 0),
        end=datetime(2026, 1, 2, 0, 0),
    )
    assert searcher.check_component(cal)


def test_recurrence_unlimited_matches_multi_year_range() -> None:
    """Unlimited yearly recurrence should match when date range spans multiple years."""
    cal = Calendar()
    event = Event()
    event.add("uid", "yearly-event")
    event.add("summary", "New Year Celebration")
    event.add("dtstart", datetime(2025, 1, 1, 10, 0))
    event.add("dtend", datetime(2025, 1, 1, 12, 0))
    event.add("rrule", vRecur(FREQ="YEARLY"))  # Unlimited recurrence (no COUNT/UNTIL)
    cal.add_component(event)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1, 0, 0),
        end=datetime(2027, 12, 31, 23, 59),  # Bounded range covering 3 years
    )
    assert searcher.check_component(cal)


def test_recurrence_simple_matches_no_range() -> None:
    """Simple yearly recurrence should match when no date range is specified."""
    cal = Calendar()
    event = Event()
    event.add("uid", "yearly-event")
    event.add("summary", "New Year Celebration")
    event.add("dtstart", datetime(2025, 1, 1, 10, 0))
    event.add("dtend", datetime(2025, 1, 1, 12, 0))
    event.add("rrule", vRecur(FREQ="YEARLY"))
    cal.add_component(event)

    searcher = Searcher(event=True)
    assert searcher.check_component(cal)


def test_recurrence_exception_original_summary_matches() -> None:
    """Recurrence with exception should match when filtering on original summary."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Weekly Team Meeting", operator="==")
    assert searcher.check_component(cal), "Should match base event with original summary"


def test_recurrence_exception_original_summary_matches_first_occurrence() -> None:
    """Recurrence with exception should match original summary with range covering first occurrence."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 6, 0, 0),
        end=datetime(2025, 1, 7, 0, 0),
    )
    searcher.add_property_filter("SUMMARY", "Weekly Team Meeting", operator="==")
    assert searcher.check_component(cal)


def test_recurrence_exception_original_summary_not_match_exception_only() -> None:
    """Recurrence with exception should NOT match original summary when range only covers exception."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 13, 0, 0),
        end=datetime(2025, 1, 14, 0, 0),
    )
    searcher.add_property_filter("SUMMARY", "Weekly Team Meeting", operator="==")
    assert not searcher.check_component(cal), "Should not match when range only covers exception"


def test_recurrence_exception_modified_summary_matches() -> None:
    """Recurrence with exception should match when filtering on modified summary."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Special Planning Session", operator="==")
    assert searcher.check_component(cal), "Should match the exception with modified summary"


def test_recurrence_exception_modified_summary_matches_with_range() -> None:
    """Recurrence with exception should match modified summary when range covers exception."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 13, 0, 0),
        end=datetime(2025, 1, 14, 0, 0),
    )
    searcher.add_property_filter("SUMMARY", "Special Planning Session", operator="==")
    assert searcher.check_component(cal)


def test_recurrence_exception_modified_summary_not_match_wrong_range() -> None:
    """Recurrence with exception should NOT match modified summary when range doesn't cover exception."""
    cal = Calendar()
    event_base = Event()
    event_base.add("uid", "weekly-meeting")
    event_base.add("summary", "Weekly Team Meeting")
    event_base.add("dtstart", datetime(2025, 1, 6, 10, 0))
    event_base.add("dtend", datetime(2025, 1, 6, 11, 0))
    event_base.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(event_base)

    event_exception = Event()
    event_exception.add("uid", "weekly-meeting")
    event_exception.add("summary", "Special Planning Session")
    event_exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    event_exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    event_exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(event_exception)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 6, 0, 0),
        end=datetime(2025, 1, 7, 0, 0),
    )
    searcher.add_property_filter("SUMMARY", "Special Planning Session", operator="==")
    assert not searcher.check_component(cal), (
        "Should not match when exception is outside date range"
    )


def _this_and_future_cal(
    range_param: str,
    first: str = "20260101",
    moved: str = "20260103",
    moved_to: tuple[str, str] = ("20260103T140000Z", "20260103T150000Z"),
) -> Calendar:
    """Five daily 10:00 occurrences from ``first``; from ``moved`` on they are at ``moved_to``.

    By default the ones from 2026-01-03 on move four hours later.
    """
    return Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:daily\r\nDTSTAMP:20260101T000000Z\r\n"
        f"DTSTART:{first}T100000Z\r\nDTEND:{first}T110000Z\r\nRRULE:FREQ=DAILY;COUNT=5\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:daily\r\nDTSTAMP:20260101T000000Z\r\n"
        f"RECURRENCE-ID;RANGE={range_param}:{moved}T100000Z\r\n"
        f"DTSTART:{moved_to[0]}\r\nDTEND:{moved_to[1]}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


@pytest.mark.parametrize(
    "range_param",
    [
        "THISANDFUTURE",
        pytest.param(
            "thisandfuture",
            marks=pytest.mark.xfail(
                strict=True,
                reason="recurring_ical_events matches RANGE case-sensitively, see "
                "https://github.com/niccokunzmann/python-recurring-ical-events/issues/310",
            ),
        ),
    ],
)
def test_this_and_future_range_is_case_insensitive(range_param: str) -> None:
    """RFC 5545 section 3.2: unquoted parameter values are case-insensitive.

    The search is far from the ends of the datetime range, so this guards the
    expansion in recurring_ical_events only, not _expansion_margin.
    """
    searcher = Searcher(
        event=True,
        start=datetime(2026, 1, 4, tzinfo=timezone.utc),
        end=datetime(2026, 1, 5, tzinfo=timezone.utc),
        expand=True,
    )
    result = list(searcher.check_component(_this_and_future_cal(range_param)))
    assert [x.start for x in result] == [datetime(2026, 1, 4, 14, tzinfo=timezone.utc)]


@pytest.mark.parametrize(
    "range_param",
    [
        "THISANDFUTURE",
        "thisandfuture",
    ],
)
def test_this_and_future_widens_expansion_margin(range_param: str) -> None:
    """An override that moves later occurrences by four hours needs that much more margin."""
    components = list(_this_and_future_cal(range_param).walk("VEVENT"))
    assert _expansion_margin(components) == timedelta(days=1, hours=5)


@pytest.mark.parametrize(
    "range_param",
    [
        "THISANDFUTURE",
        pytest.param(
            "thisandfuture",
            marks=pytest.mark.xfail(
                strict=True,
                reason="recurring_ical_events matches RANGE case-sensitively, see "
                "https://github.com/niccokunzmann/python-recurring-ical-events/issues/310",
            ),
        ),
    ],
)
def test_this_and_future_near_start_of_datetime_range(range_param: str) -> None:
    """Occurrences moved two days later, searched near the start of the datetime range.

    recurring_ical_events widens the window by how far they moved, so the
    window has to stay that much further inside the range, or it overflows
    and the components come back unexpanded.  The two occurrences within
    that margin of the start of the range are left out, as designed.
    """
    cal = _this_and_future_cal(
        range_param,
        first="00010101",
        moved="00010103",
        moved_to=("00010105T100000Z", "00010105T110000Z"),
    )
    searcher = Searcher(
        event=True,
        start=datetime(1, 1, 1, tzinfo=timezone.utc),
        end=datetime(1, 1, 10, tzinfo=timezone.utc),
        expand=True,
    )
    result = list(searcher.check_component(cal))
    assert sorted(x.start for x in result) == [
        datetime(1, 1, day, 10, tzinfo=timezone.utc) for day in (5, 6, 7)
    ]
