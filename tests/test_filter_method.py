"""Tests for the Searcher.filter() method.

Tests that the filter() method correctly filters different types of inputs:
- List of Calendar objects
- List of Component objects (Event, Todo, Journal)
- Handles recurrence expansion
- Handles split_expanded parameter
"""

from datetime import datetime, timezone

from icalendar import Calendar, Event, Todo
from icalendar.prop import vRecur

from icalendar_searcher import Searcher


def test_filter_returns_new_list() -> None:
    """Test that filter() returns a new list, not modifying the original."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Meeting")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Training")
    event2.add("dtstart", datetime(2025, 1, 2))

    events = [event1, event2]
    original_order = events.copy()

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Meeting")
    filtered_events = searcher.filter(events)

    # Original list should be unchanged
    assert events == original_order
    assert len(events) == 2

    # Filtered list should only contain matching events
    assert len(filtered_events) == 1
    assert filtered_events[0]["SUMMARY"] == "Meeting"


def test_filter_components_with_property_filter() -> None:
    """Test filtering Event components by property."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Team Meeting")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Training Session")
    event2.add("dtstart", datetime(2025, 1, 2))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Client Meeting")
    event3.add("dtstart", datetime(2025, 1, 3))

    events = [event1, event2, event3]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Meeting", operator="contains")
    filtered_events = searcher.filter(events)

    assert len(filtered_events) == 2
    summaries = {e["SUMMARY"] for e in filtered_events}
    assert summaries == {"Team Meeting", "Client Meeting"}


def test_filter_calendars_with_property_filter() -> None:
    """Test filtering Calendar objects by property."""
    cal1 = Calendar()
    cal1.add("prodid", "-//Test//Test//EN")
    cal1.add("version", "2.0")
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Work Task")
    event1.add("dtstart", datetime(2025, 1, 1))
    cal1.add_component(event1)

    cal2 = Calendar()
    cal2.add("prodid", "-//Test//Test//EN")
    cal2.add("version", "2.0")
    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Personal Task")
    event2.add("dtstart", datetime(2025, 1, 2))
    cal2.add_component(event2)

    cal3 = Calendar()
    cal3.add("prodid", "-//Test//Test//EN")
    cal3.add("version", "2.0")
    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Work Meeting")
    event3.add("dtstart", datetime(2025, 1, 3))
    cal3.add_component(event3)

    calendars = [cal1, cal2, cal3]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Work", operator="contains")
    filtered_cals = searcher.filter(calendars)

    assert len(filtered_cals) == 2
    # Extract events to verify
    events = [cal.walk("VEVENT")[0] for cal in filtered_cals]
    summaries = {e["SUMMARY"] for e in events}
    assert summaries == {"Work Task", "Work Meeting"}


def test_filter_with_time_range() -> None:
    """Test filtering events by time range."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Early Event")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Mid Event")
    event2.add("dtstart", datetime(2025, 1, 15))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Late Event")
    event3.add("dtstart", datetime(2025, 1, 30))

    events = [event1, event2, event3]

    searcher = Searcher(event=True, start=datetime(2025, 1, 10), end=datetime(2025, 1, 20))
    filtered_events = searcher.filter(events)

    assert len(filtered_events) == 1
    assert filtered_events[0]["SUMMARY"] == "Mid Event"


def test_filter_no_matches_returns_empty_list() -> None:
    """Test that filter() returns empty list when no matches."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Meeting")

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Training")

    events = [event1, event2]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Conference")
    filtered_events = searcher.filter(events)

    assert len(filtered_events) == 0
    assert filtered_events == []


def test_filter_todos() -> None:
    """Test filtering Todo components."""
    todo1 = Todo()
    todo1.add("uid", "1")
    todo1.add("summary", "Urgent Task")
    todo1.add("priority", 1)

    todo2 = Todo()
    todo2.add("uid", "2")
    todo2.add("summary", "Normal Task")
    todo2.add("priority", 5)

    todo3 = Todo()
    todo3.add("uid", "3")
    todo3.add("summary", "Urgent Issue")
    todo3.add("priority", 1)

    todos = [todo1, todo2, todo3]

    searcher = Searcher(todo=True)
    searcher.add_property_filter("SUMMARY", "Urgent", operator="contains")
    filtered_todos = searcher.filter(todos)

    assert len(filtered_todos) == 2
    summaries = {t["SUMMARY"] for t in filtered_todos}
    assert summaries == {"Urgent Task", "Urgent Issue"}


def test_filter_preserves_calendar_properties() -> None:
    """Test that filtering preserves Calendar-level properties."""
    # Create two separate calendars, each with one event
    cal1 = Calendar()
    cal1.add("prodid", "-//My Product//My Company//EN")
    cal1.add("version", "2.0")
    cal1.add("x-wr-calname", "My Calendar")
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Keep This")
    cal1.add_component(event1)

    cal2 = Calendar()
    cal2.add("prodid", "-//My Product//My Company//EN")
    cal2.add("version", "2.0")
    cal2.add("x-wr-calname", "My Calendar")
    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Filter This")
    cal2.add_component(event2)

    calendars = [cal1, cal2]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Keep This")
    filtered_cals = searcher.filter(calendars)

    # Should only get the calendar with "Keep This"
    assert len(filtered_cals) == 1
    result_cal = filtered_cals[0]

    # Check Calendar properties preserved
    assert result_cal["PRODID"] == "-//My Product//My Company//EN"
    assert result_cal["VERSION"] == "2.0"
    assert result_cal["X-WR-CALNAME"] == "My Calendar"

    # Check correct event included
    events = result_cal.walk("VEVENT")
    assert len(events) == 1
    assert events[0]["SUMMARY"] == "Keep This"


def test_filter_case_insensitive() -> None:
    """Test case-insensitive filtering."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "IMPORTANT MEETING")

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "casual chat")

    events = [event1, event2]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "important", operator="contains", case_sensitive=False)
    filtered_events = searcher.filter(events)

    assert len(filtered_events) == 1
    assert filtered_events[0]["SUMMARY"] == "IMPORTANT MEETING"


def test_filter_multiple_property_filters() -> None:
    """Test filtering with multiple property filters (AND logic)."""
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Team Meeting")
    event1.add("location", "Office")

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Team Building")
    event2.add("location", "Park")

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Client Meeting")
    event3.add("location", "Office")

    events = [event1, event2, event3]

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Team", operator="contains")
    searcher.add_property_filter("LOCATION", "Office")
    filtered_events = searcher.filter(events)

    # Only event1 matches both filters
    assert len(filtered_events) == 1
    assert filtered_events[0]["SUMMARY"] == "Team Meeting"


def test_filter_with_component_type() -> None:
    """Test that component type filtering works."""
    event = Event()
    event.add("uid", "1")
    event.add("summary", "Event")

    todo = Todo()
    todo.add("uid", "2")
    todo.add("summary", "Task")

    # Mix events and todos
    components = [event, todo]

    # Filter for events only
    searcher = Searcher(event=True)
    filtered = searcher.filter(components)

    assert len(filtered) == 1
    assert filtered[0].name == "VEVENT"

    # Filter for todos only
    searcher = Searcher(todo=True)
    filtered = searcher.filter(components)

    assert len(filtered) == 1
    assert filtered[0].name == "VTODO"


def test_filter_empty_input_returns_empty_list() -> None:
    """Test that filtering empty list returns empty list."""
    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "test")

    filtered = searcher.filter([])

    assert filtered == []
    assert isinstance(filtered, list)


def test_filter_with_expand() -> None:
    """Test filtering with recurrence expansion."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    event = Event()
    event.add("uid", "recurring-event")
    event.add("summary", "Weekly Meeting")
    event.add("dtstart", datetime(2025, 1, 6))  # Monday
    event.add("rrule", vRecur(FREQ="WEEKLY", COUNT=3))  # 3 occurrences
    cal.add_component(event)

    calendars = [cal]

    # Enable expansion
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 31),
        expand=True,
    )

    # Without split_expanded, should get one Calendar with all occurrences
    filtered = searcher.filter(calendars, split_expanded=False)

    assert len(filtered) == 1
    result_cal = filtered[0]
    # Should have 3 event components (3 occurrences)
    events = result_cal.walk("VEVENT")
    assert len(events) == 3


def test_filter_with_split_expanded() -> None:
    """Test filtering with split_expanded=True splits recurrences into separate Calendars."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    event = Event()
    event.add("uid", "recurring-event")
    event.add("summary", "Weekly Meeting")
    event.add("dtstart", datetime(2025, 1, 6))  # Monday
    event.add("rrule", vRecur(FREQ="WEEKLY", COUNT=3))  # 3 occurrences
    cal.add_component(event)

    calendars = [cal]

    # Enable expansion and split_expanded
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 31),
        expand=True,
    )

    # With split_expanded=True, should get 3 separate Calendars
    filtered = searcher.filter(calendars, split_expanded=True)

    assert len(filtered) == 3

    # Each Calendar should have one event
    for result_cal in filtered:
        events = result_cal.walk("VEVENT")
        assert len(events) == 1
        assert events[0]["SUMMARY"] == "Weekly Meeting"

    # Check that each has the original Calendar properties
    for result_cal in filtered:
        assert result_cal["PRODID"] == "-//Test//Test//EN"
        assert result_cal["VERSION"] == "2.0"


def test_filter_split_expanded_preserves_timezones() -> None:
    """Test that split_expanded preserves VTIMEZONE components."""
    from icalendar import Timezone

    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    # Add timezone
    tz = Timezone()
    tz.add("tzid", "America/New_York")
    cal.add_component(tz)

    # Add recurring event
    event = Event()
    event.add("uid", "recurring-event")
    event.add("summary", "Meeting")
    event.add("dtstart", datetime(2025, 1, 6))
    event.add("rrule", vRecur(FREQ="WEEKLY", COUNT=2))
    cal.add_component(event)

    calendars = [cal]

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 31),
        expand=True,
    )

    # With split_expanded, each Calendar should preserve the timezone
    filtered = searcher.filter(calendars, split_expanded=True)

    assert len(filtered) == 2

    for result_cal in filtered:
        # Check timezone is preserved
        timezones = result_cal.walk("VTIMEZONE")
        assert len(timezones) == 1
        assert timezones[0]["TZID"] == "America/New_York"

        # Check one event
        events = result_cal.walk("VEVENT")
        assert len(events) == 1


def test_filter_split_expanded_without_expansion() -> None:
    """Test that split_expanded has no effect when expand is False."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    event = Event()
    event.add("uid", "recurring-event")
    event.add("summary", "Weekly Meeting")
    event.add("dtstart", datetime(2025, 1, 6))
    event.add("rrule", vRecur(FREQ="WEEKLY", COUNT=3))
    cal.add_component(event)

    calendars = [cal]

    # No expansion, so split_expanded should have no effect
    searcher = Searcher(event=True, expand=False)

    filtered = searcher.filter(calendars, split_expanded=True)

    # Should still return just one Calendar (not expanded, so nothing to split)
    assert len(filtered) == 1
    events = filtered[0].walk("VEVENT")
    # Should have just the master event, not expanded
    assert len(events) == 1


def test_filter_calendar_basic() -> None:
    """Test filtering subcomponents within a Calendar object."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")

    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Team Meeting")
    event1.add("dtstart", datetime(2025, 1, 1))

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Training Session")
    event2.add("dtstart", datetime(2025, 1, 2))

    event3 = Event()
    event3.add("uid", "3")
    event3.add("summary", "Team Building")
    event3.add("dtstart", datetime(2025, 1, 3))

    cal.add_component(event1)
    cal.add_component(event2)
    cal.add_component(event3)

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Team", operator="contains")
    filtered_cal = searcher.filter_calendar(cal)

    # Original calendar should be unchanged
    assert len(cal.walk("VEVENT")) == 3

    # Filtered calendar should have only matching events
    assert filtered_cal is not None
    events = filtered_cal.walk("VEVENT")
    assert len(events) == 2
    summaries = {e["SUMMARY"] for e in events}
    assert summaries == {"Team Meeting", "Team Building"}

    # Calendar properties should be preserved
    assert filtered_cal["PRODID"] == "-//Test//Test//EN"
    assert filtered_cal["VERSION"] == "2.0"


def test_filter_calendar_no_matches() -> None:
    """Test that filter_calendar returns None when no matches."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    event = Event()
    event.add("uid", "1")
    event.add("summary", "Meeting")
    cal.add_component(event)

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "NoMatch")
    filtered_cal = searcher.filter_calendar(cal)

    assert filtered_cal is None


def test_filter_calendar_preserves_timezones() -> None:
    """Test that filter_calendar preserves VTIMEZONE components."""
    from icalendar import Timezone

    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    # Add timezone
    tz = Timezone()
    tz.add("tzid", "America/New_York")
    cal.add_component(tz)

    # Add events
    event1 = Event()
    event1.add("uid", "1")
    event1.add("summary", "Keep This")
    cal.add_component(event1)

    event2 = Event()
    event2.add("uid", "2")
    event2.add("summary", "Filter This")
    cal.add_component(event2)

    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "Keep This")
    filtered_cal = searcher.filter_calendar(cal)

    assert filtered_cal is not None

    # Check timezone is preserved
    timezones = filtered_cal.walk("VTIMEZONE")
    assert len(timezones) == 1
    assert timezones[0]["TZID"] == "America/New_York"

    # Check correct event included
    events = filtered_cal.walk("VEVENT")
    assert len(events) == 1
    assert events[0]["SUMMARY"] == "Keep This"


def test_filter_calendar_with_expansion() -> None:
    """Test filter_calendar with recurrence expansion."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    # Add recurring event
    event = Event()
    event.add("uid", "recurring")
    event.add("summary", "Weekly Meeting")
    event.add("dtstart", datetime(2025, 1, 6))
    event.add("rrule", vRecur(FREQ="WEEKLY", COUNT=3))
    cal.add_component(event)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 31),
        expand=True,
    )

    filtered_cal = searcher.filter_calendar(cal)

    assert filtered_cal is not None
    events = filtered_cal.walk("VEVENT")
    # Should have 3 expanded occurrences
    assert len(events) == 3


def test_filter_calendar_mixed_component_types() -> None:
    """Test filter_calendar with mixed event and todo components."""
    cal = Calendar()
    cal.add("prodid", "-//Test//Test//EN")

    event = Event()
    event.add("uid", "1")
    event.add("summary", "Event")
    cal.add_component(event)

    todo = Todo()
    todo.add("uid", "2")
    todo.add("summary", "Task")
    cal.add_component(todo)

    # Filter for events only
    searcher = Searcher(event=True)
    filtered_cal = searcher.filter_calendar(cal)

    assert filtered_cal is not None
    events = filtered_cal.walk("VEVENT")
    todos = filtered_cal.walk("VTODO")

    assert len(events) == 1
    assert len(todos) == 0

    # Filter for todos only
    searcher = Searcher(todo=True)
    filtered_cal = searcher.filter_calendar(cal)

    assert filtered_cal is not None
    events = filtered_cal.walk("VEVENT")
    todos = filtered_cal.walk("VTODO")

    assert len(events) == 0
    assert len(todos) == 1


# A daily event whose 14th occurrence was moved from 10:00 to 15:00.  RFC 4791
# section 9.9 requires the effective value of a recurrence set to be inferred
# from the recurrence pattern *and* its overrides, so filter_calendar() must
# treat master and override as one unit rather than checking them one by one.
_MOVED_OCCURRENCE_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:daily-with-exception
DTSTART:20250101T100000Z
DTEND:20250101T110000Z
RRULE:FREQ=DAILY;COUNT=30
SUMMARY:daily
END:VEVENT
BEGIN:VEVENT
UID:daily-with-exception
RECURRENCE-ID:20250114T100000Z
DTSTART:20250114T150000Z
DTEND:20250114T160000Z
SUMMARY:moved
END:VEVENT
END:VCALENDAR
"""


def _moved_occurrence_calendar() -> Calendar:
    return Calendar.from_ical(_MOVED_OCCURRENCE_ICS)


def test_filter_calendar_moved_occurrence_not_matched_at_old_time() -> None:
    """The 14th occurrence no longer takes place at 10:00, so nothing matches."""
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 14, 9, tzinfo=timezone.utc),
        end=datetime(2025, 1, 14, 12, tzinfo=timezone.utc),
    )
    assert searcher.filter([_moved_occurrence_calendar()]) == []
    assert searcher.filter_calendar(_moved_occurrence_calendar()) is None


def test_filter_calendar_moved_occurrence_matched_at_new_time() -> None:
    """Control: the moved occurrence matches at its new time."""
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 14, 14, tzinfo=timezone.utc),
        end=datetime(2025, 1, 14, 17, tzinfo=timezone.utc),
    )
    assert len(searcher.filter([_moved_occurrence_calendar()])) == 1
    filtered_cal = searcher.filter_calendar(_moved_occurrence_calendar())
    assert filtered_cal is not None
    # Without expand, the whole recurrence set is returned, as filter() does
    assert [str(e["SUMMARY"]) for e in filtered_cal.walk("VEVENT")] == ["daily", "moved"]


def test_filter_calendar_expand_does_not_duplicate_moved_occurrence() -> None:
    """Expanding the 14th must yield only the moved 15:00 occurrence."""
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 14, tzinfo=timezone.utc),
        end=datetime(2025, 1, 15, tzinfo=timezone.utc),
        expand=True,
    )
    expected = [("moved", datetime(2025, 1, 14, 15, tzinfo=timezone.utc))]

    filtered = searcher.filter([_moved_occurrence_calendar()])
    occurrences = [e for cal in filtered for e in cal.walk("VEVENT")]
    assert [(str(e["SUMMARY"]), e.start) for e in occurrences] == expected

    filtered_cal = searcher.filter_calendar(_moved_occurrence_calendar())
    assert filtered_cal is not None
    occurrences = filtered_cal.walk("VEVENT")
    assert [(str(e["SUMMARY"]), e.start) for e in occurrences] == expected


def test_filter_calendar_groups_interleaved_recurrence_set() -> None:
    """Override before its master, with an unrelated event in between."""
    source = _moved_occurrence_calendar()
    master, override = source.subcomponents
    other = Event()
    other.add("UID", "unrelated")
    other.add("DTSTART", datetime(2025, 1, 14, 10, tzinfo=timezone.utc))
    other.add("DTEND", datetime(2025, 1, 14, 11, tzinfo=timezone.utc))
    other.add("SUMMARY", "unrelated")
    cal = Calendar()
    for comp in (override, other, master):
        cal.add_component(comp)

    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 14, 9, tzinfo=timezone.utc),
        end=datetime(2025, 1, 14, 12, tzinfo=timezone.utc),
    )
    filtered_cal = searcher.filter_calendar(cal)
    assert filtered_cal is not None
    assert [str(e["SUMMARY"]) for e in filtered_cal.walk("VEVENT")] == ["unrelated"]


def _occurrence_window_searcher(**kwargs: object) -> Searcher:
    return Searcher(
        start=datetime(2025, 1, 14, 9, tzinfo=timezone.utc),
        end=datetime(2025, 1, 14, 12, tzinfo=timezone.utc),
        **kwargs,
    )


def test_filter_calendar_same_uid_different_types_not_grouped() -> None:
    """A VTODO sharing a UID with a recurring VEVENT is not part of its set."""
    source = _moved_occurrence_calendar()
    master, _override = source.subcomponents
    todo = Todo()
    todo.add("UID", "daily-with-exception")
    todo.add("RECURRENCE-ID", datetime(2025, 1, 14, 10, tzinfo=timezone.utc))
    todo.add("DUE", datetime(2025, 1, 20, tzinfo=timezone.utc))
    todo.add("SUMMARY", "todo")
    cal = Calendar()
    cal.add_component(master)
    cal.add_component(todo)

    filtered_cal = _occurrence_window_searcher(event=True).filter_calendar(cal)
    assert filtered_cal is not None
    assert [c.name for c in filtered_cal.subcomponents] == ["VEVENT"]
    assert _occurrence_window_searcher(todo=True).filter_calendar(cal) is None


def test_filter_calendar_duplicated_master_does_not_raise() -> None:
    """Two masters with one UID are not a valid recurrence set; check one by one."""
    source = _moved_occurrence_calendar()
    master, override = source.subcomponents
    duplicate = Calendar.from_ical(_MOVED_OCCURRENCE_ICS).subcomponents[0]
    cal = Calendar()
    for comp in (master, duplicate, override):
        cal.add_component(comp)

    filtered_cal = _occurrence_window_searcher(event=True).filter_calendar(cal)
    assert filtered_cal is not None
    assert [str(e["SUMMARY"]) for e in filtered_cal.walk("VEVENT")] == ["daily", "daily"]


def test_filter_calendar_components_without_uid() -> None:
    """Components without a UID are checked one by one."""
    cal = Calendar()
    for hour, summary in ((10, "inside"), (15, "outside")):
        event = Event()
        event.add("DTSTART", datetime(2025, 1, 14, hour, tzinfo=timezone.utc))
        event.add("DTEND", datetime(2025, 1, 14, hour + 1, tzinfo=timezone.utc))
        event.add("SUMMARY", summary)
        cal.add_component(event)

    searcher = _occurrence_window_searcher(event=True)
    filtered_cal = searcher.filter_calendar(cal)
    assert filtered_cal is not None
    assert [str(e["SUMMARY"]) for e in filtered_cal.walk("VEVENT")] == ["inside"]
    assert len(searcher.filter([cal.subcomponents[0]])) == 1
