"""Tests for the Searcher.sort() method.

Tests that the sort() method correctly sorts different types of inputs:
- List of Calendar objects
- List of Component objects (Event, Todo, Journal)
- List of CalendarObjectResource objects (caldav)
"""

from datetime import datetime

import pytest
from icalendar import Calendar, Event, FreeBusy, Todo

from icalendar_searcher import Searcher


def test_sort_returns_new_list() -> None:
    """Test that sort() returns a new list, not modifying the original."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event 1")
    event1.add("dtstart", datetime(2025, 1, 3))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event 2")
    event2.add("dtstart", datetime(2025, 1, 1))

    events = [event1, event2]
    original_order = events.copy()

    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    sorted_events = searcher.sort(events)

    # Original list should be unchanged
    assert events == original_order
    assert events[0] is event1
    assert events[1] is event2

    # Sorted list should be different
    assert sorted_events != events
    assert sorted_events[0] is event2  # Earlier date first
    assert sorted_events[1] is event1


def test_sort_with_no_sort_keys_returns_copy() -> None:
    """Test that sort() without sort keys returns a copy of the input."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event 1")

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event 2")

    events = [event1, event2]

    searcher = Searcher()
    # No sort keys added
    result = searcher.sort(events)

    # Should be a copy, not the same list
    assert result is not events
    assert result == events
    assert len(result) == 2


def test_sort_components_event() -> None:
    """Test sorting a list of Event components."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Zebra")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Apple")
    event2.add("dtstart", datetime(2025, 1, 1))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Banana")
    event3.add("dtstart", datetime(2025, 1, 1))

    events = [event1, event2, event3]

    searcher = Searcher()
    searcher.add_sort_key("SUMMARY")
    sorted_events = searcher.sort(events)

    assert len(sorted_events) == 3
    assert sorted_events[0]["SUMMARY"] == "Apple"
    assert sorted_events[1]["SUMMARY"] == "Banana"
    assert sorted_events[2]["SUMMARY"] == "Zebra"


def test_sort_components_todo() -> None:
    """Test sorting a list of Todo components."""
    todo1 = Todo()
    todo1.add("uid", "1")
    todo1.add("summary", "Task C")
    todo1.add("priority", 5)

    todo2 = Todo()
    todo2.add("uid", "2")
    todo2.add("summary", "Task A")
    todo2.add("priority", 1)

    todo3 = Todo()
    todo3.add("uid", "3")
    todo3.add("summary", "Task B")
    todo3.add("priority", 3)

    todos = [todo1, todo2, todo3]

    searcher = Searcher()
    searcher.add_sort_key("PRIORITY")
    sorted_todos = searcher.sort(todos)

    assert len(sorted_todos) == 3
    assert sorted_todos[0]["PRIORITY"] == 1
    assert sorted_todos[1]["PRIORITY"] == 3
    assert sorted_todos[2]["PRIORITY"] == 5


def test_sort_calendars() -> None:
    """Test sorting a list of Calendar objects (each containing one event)."""
    cal1 = Calendar()
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event C")
    event1.add("dtstart", datetime(2025, 1, 3))
    cal1.add_component(event1)

    cal2 = Calendar()
    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event A")
    event2.add("dtstart", datetime(2025, 1, 1))
    cal2.add_component(event2)

    cal3 = Calendar()
    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Event B")
    event3.add("dtstart", datetime(2025, 1, 2))
    cal3.add_component(event3)

    calendars = [cal1, cal2, cal3]

    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    sorted_calendars = searcher.sort(calendars)

    assert len(sorted_calendars) == 3
    # Extract events from calendars to check order
    events = [cal.walk("VEVENT")[0] for cal in sorted_calendars]
    assert events[0]["DTSTART"].dt == datetime(2025, 1, 1)
    assert events[1]["DTSTART"].dt == datetime(2025, 1, 2)
    assert events[2]["DTSTART"].dt == datetime(2025, 1, 3)


def test_sort_multiple_keys() -> None:
    """Test sorting with multiple sort keys."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Meeting")
    event1.add("dtstart", datetime(2025, 1, 2))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Meeting")
    event2.add("dtstart", datetime(2025, 1, 1))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Conference")
    event3.add("dtstart", datetime(2025, 1, 3))

    events = [event1, event2, event3]

    searcher = Searcher()
    # Sort by SUMMARY first, then by DTSTART
    searcher.add_sort_key("SUMMARY")
    searcher.add_sort_key("DTSTART")
    sorted_events = searcher.sort(events)

    assert len(sorted_events) == 3
    # Conference comes first alphabetically
    assert sorted_events[0]["SUMMARY"] == "Conference"
    # Both Meetings, but earlier date first
    assert sorted_events[1]["SUMMARY"] == "Meeting"
    assert sorted_events[1]["DTSTART"].dt == datetime(2025, 1, 1)
    assert sorted_events[2]["SUMMARY"] == "Meeting"
    assert sorted_events[2]["DTSTART"].dt == datetime(2025, 1, 2)


def test_sort_case_insensitive() -> None:
    """Test sorting with case-insensitive collation."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "zebra")

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Apple")

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Banana")

    events = [event1, event2, event3]

    searcher = Searcher()
    searcher.add_sort_key("SUMMARY", case_sensitive=False)
    sorted_events = searcher.sort(events)

    assert len(sorted_events) == 3
    # Case-insensitive sort: Apple, Banana, zebra
    assert sorted_events[0]["SUMMARY"] == "Apple"
    assert sorted_events[1]["SUMMARY"] == "Banana"
    assert sorted_events[2]["SUMMARY"] == "zebra"


def test_sort_reversed() -> None:
    """Test sorting in reverse order."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event")
    event2.add("dtstart", datetime(2025, 1, 2))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Event")
    event3.add("dtstart", datetime(2025, 1, 3))

    events = [event1, event2, event3]

    searcher = Searcher()
    searcher.add_sort_key("DTSTART", reversed=True)
    sorted_events = searcher.sort(events)

    assert len(sorted_events) == 3
    # Reversed order: latest first
    assert sorted_events[0]["DTSTART"].dt == datetime(2025, 1, 3)
    assert sorted_events[1]["DTSTART"].dt == datetime(2025, 1, 2)
    assert sorted_events[2]["DTSTART"].dt == datetime(2025, 1, 1)


def test_sort_calendar_basic() -> None:
    """Test sorting subcomponents within a Calendar object."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event C")
    event1.add("dtstart", datetime(2025, 1, 3))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event A")
    event2.add("dtstart", datetime(2025, 1, 1))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Event B")
    event3.add("dtstart", datetime(2025, 1, 2))

    cal.add_component(event1)
    cal.add_component(event2)
    cal.add_component(event3)

    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    sorted_cal = searcher.sort_calendar(cal)

    # Original calendar should be unchanged
    original_events = cal.walk("VEVENT")
    assert len(original_events) == 3
    assert original_events[0]["DTSTART"].dt == datetime(2025, 1, 3)

    # Sorted calendar should have events in order
    sorted_events = sorted_cal.walk("VEVENT")
    assert len(sorted_events) == 3
    assert sorted_events[0]["DTSTART"].dt == datetime(2025, 1, 1)
    assert sorted_events[1]["DTSTART"].dt == datetime(2025, 1, 2)
    assert sorted_events[2]["DTSTART"].dt == datetime(2025, 1, 3)

    # Calendar properties should be preserved
    assert sorted_cal["PRODID"] == "-//Test//Test//EN"
    assert sorted_cal["VERSION"] == "2.0"


def test_sort_calendar_preserves_timezones() -> None:
    """Test that sort_calendar preserves VTIMEZONE components."""
    from icalendar import Timezone

    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    # Add timezone
    tz = Timezone()
    tz.add("tzid", "America/New_York")
    cal.add_component(tz)

    # Add events
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event B")
    event1.add("dtstart", datetime(2025, 1, 2))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Event A")
    event2.add("dtstart", datetime(2025, 1, 1))

    cal.add_component(event1)
    cal.add_component(event2)

    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    sorted_cal = searcher.sort_calendar(cal)

    # Check timezone is preserved
    timezones = sorted_cal.walk("VTIMEZONE")
    assert len(timezones) == 1
    assert timezones[0]["TZID"] == "America/New_York"

    # Check events are sorted
    sorted_events = sorted_cal.walk("VEVENT")
    assert len(sorted_events) == 2
    assert sorted_events[0]["DTSTART"].dt == datetime(2025, 1, 1)
    assert sorted_events[1]["DTSTART"].dt == datetime(2025, 1, 2)


def test_sort_calendar_mixed_component_types() -> None:
    """Test sorting a Calendar with mixed component types (events, todos)."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Event")
    event1.add("dtstart", datetime(2025, 1, 3))

    todo1 = Todo()
    todo1.add("uid", "2")
    todo1.add("summary", "Task")
    todo1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "3")
    event2.add("summary", "Event")
    event2.add("dtstart", datetime(2025, 1, 2))

    cal.add_component(event1)
    cal.add_component(todo1)
    cal.add_component(event2)

    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    sorted_cal = searcher.sort_calendar(cal)

    # All components should be sorted by DTSTART
    all_components = [comp for comp in sorted_cal.subcomponents]
    # Skip timezone if any
    non_tz = [c for c in all_components if c.name != "VTIMEZONE"]

    assert len(non_tz) == 3
    assert non_tz[0]["DTSTART"].dt == datetime(2025, 1, 1)  # Todo
    assert non_tz[1]["DTSTART"].dt == datetime(2025, 1, 2)  # Event
    assert non_tz[2]["DTSTART"].dt == datetime(2025, 1, 3)  # Event


@pytest.mark.parametrize("key", ["SUMMARY", "DTSTART", "STATUS", "UID"])
def test_sort_calendar_other_component_types(key: str) -> None:
    """VFREEBUSY and X- components are sorted like any other component."""
    cal = Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//Test//EN\r\n"
        "BEGIN:VFREEBUSY\r\nUID:3\r\nSUMMARY:c\r\nSTATUS:c\r\n"
        "DTSTART:20250103T100000\r\nDTEND:20250103T110000\r\nEND:VFREEBUSY\r\n"
        "BEGIN:X-FOO\r\nUID:1\r\nSUMMARY:a\r\nSTATUS:a\r\n"
        "DTSTART:20250101T100000\r\nEND:X-FOO\r\n"
        "BEGIN:VEVENT\r\nUID:2\r\nSUMMARY:b\r\nSTATUS:b\r\n"
        "DTSTART:20250102T100000\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    searcher = Searcher()
    searcher.add_sort_key(key)
    sorted_cal = searcher.sort_calendar(cal)
    assert [str(c["UID"]) for c in sorted_cal.subcomponents] == ["1", "2", "3"]


def test_sort_vfreebusy_without_the_sort_key() -> None:
    """A VFREEBUSY without DTSTART gets the default instead of a KeyError."""
    busy = FreeBusy()
    busy.add("uid", "2")
    event = Event()
    event.add("uid", "1")
    event.add("dtstart", datetime(2025, 1, 1))
    searcher = Searcher()
    searcher.add_sort_key("DTSTART")
    assert [str(c["UID"]) for c in searcher.sort([event, busy])] == ["2", "1"]


def test_sort_calendar_no_sort_keys() -> None:
    """Test that sort_calendar returns a copy when no sort keys configured."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    event = Event()
    event.add("uid", "1")
    event.add("summary", "Event")
    cal.add_component(event)

    searcher = Searcher()
    # No sort keys added
    result = searcher.sort_calendar(cal)

    # Should be a different object (copy)
    assert result is not cal
    # Should have same content
    assert len(result.subcomponents) == len(cal.subcomponents)
    assert result["PRODID"] == cal["PRODID"]
