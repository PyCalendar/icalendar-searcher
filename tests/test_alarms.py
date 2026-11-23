"""
Tests for alarm (VALARM) searching functionality.

Tests the alarm_start and alarm_end parameters for finding events/todos
with alarms that trigger within a specific time range.
"""

from datetime import datetime, timedelta, timezone

import pytest
from icalendar import Alarm, Calendar, Event, Todo

from icalendar_searcher import Searcher


def test_event_with_alarm_relative_trigger() -> None:
    """Event with alarm (relative trigger) should match when alarm fires in range."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-with-alarm")
    event.add("summary", "Meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 11, 0))

    # Add alarm 15 minutes before event (fires at 09:45)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(minutes=-15))
    alarm.add("description", "Reminder")
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarms firing between 09:40 and 09:50
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 9, 40),
        alarm_end=datetime(2025, 1, 15, 9, 50),
    )
    result = searcher.check_component(cal)
    assert result, "Event with alarm firing in range should match"


def test_event_with_alarm_not_in_range() -> None:
    """Event with alarm outside search range should not match."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-with-alarm")
    event.add("summary", "Meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 11, 0))

    # Add alarm 15 minutes before event (fires at 09:45)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(minutes=-15))
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarms firing between 10:00 and 11:00 (alarm already fired)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 10, 0),
        alarm_end=datetime(2025, 1, 15, 11, 0),
    )
    result = searcher.check_component(cal)
    assert not result, "Event with alarm outside range should not match"


def test_event_with_alarm_absolute_trigger() -> None:
    """Event with alarm (absolute trigger) should match when alarm fires in range."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-with-absolute-alarm")
    event.add("summary", "Appointment")
    event.add("dtstart", datetime(2025, 1, 15, 14, 0))
    event.add("dtend", datetime(2025, 1, 15, 15, 0))

    # Add alarm with absolute trigger time
    alarm = Alarm()
    alarm.add("action", "AUDIO")
    alarm.add("trigger", datetime(2025, 1, 15, 13, 30))  # Absolute time
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarms firing at 13:30
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 13, 25),
        alarm_end=datetime(2025, 1, 15, 13, 35),
    )
    result = searcher.check_component(cal)
    assert result, "Event with absolute alarm in range should match"


def test_event_with_multiple_alarms() -> None:
    """Event with multiple alarms should match if any alarm is in range."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-multi-alarms")
    event.add("summary", "Important Meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 11, 0))

    # First alarm: 1 hour before (09:00)
    alarm1 = Alarm()
    alarm1.add("action", "DISPLAY")
    alarm1.add("trigger", timedelta(hours=-1))
    event.add_component(alarm1)

    # Second alarm: 15 minutes before (09:45)
    alarm2 = Alarm()
    alarm2.add("action", "AUDIO")
    alarm2.add("trigger", timedelta(minutes=-15))
    event.add_component(alarm2)

    cal.add_component(event)

    # Search for alarms firing between 09:40 and 09:50 (should match second alarm)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 9, 40),
        alarm_end=datetime(2025, 1, 15, 9, 50),
    )
    result = searcher.check_component(cal)
    assert result, "Event with one alarm in range should match"


def test_event_no_alarm_with_alarm_search() -> None:
    """Event without alarm should not match alarm search."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-no-alarm")
    event.add("summary", "Meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 11, 0))
    # No alarm added

    cal.add_component(event)

    # Search for alarms
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 9, 0),
        alarm_end=datetime(2025, 1, 15, 10, 0),
    )
    result = searcher.check_component(cal)
    assert not result, "Event without alarm should not match alarm search"


def test_todo_with_alarm_relative_to_due() -> None:
    """Todo with alarm relative to DUE should match when alarm fires in range."""
    task = Todo()
    task.add("uid", "task-with-alarm")
    task.add("summary", "Submit Report")
    task.add("due", datetime(2025, 1, 15, 17, 0))

    # Add alarm 1 day before due (fires at Jan 14, 17:00)
    alarm = Alarm()
    alarm.add("action", "EMAIL")
    alarm.add("trigger", timedelta(days=-1))
    alarm.add("description", "Report due tomorrow!")
    alarm["TRIGGER"].params["RELATED"] = "END"
    task.add_component(alarm)

    cal = Calendar()
    cal.add_component(task)

    # Search for alarms firing on Jan 14
    searcher = Searcher(
        todo=True,
        alarm_start=datetime(2025, 1, 14, 16, 0),
        alarm_end=datetime(2025, 1, 14, 18, 0),
    )
    result = searcher.check_component(cal)
    assert result, "Todo with alarm firing in range should match"


def test_todo_with_alarm_relative_to_dtstart() -> None:
    """Todo with alarm relative to DTSTART should match when alarm fires in range."""
    task = Todo()
    task.add("uid", "task-alarm-start")
    task.add("summary", "Start Project")
    task.add("dtstart", datetime(2025, 1, 15, 9, 0))

    # Add alarm at start time
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(0))  # At start
    task.add_component(alarm)

    cal = Calendar()
    cal.add_component(task)

    # Search for alarms at start time
    searcher = Searcher(
        todo=True,
        alarm_start=datetime(2025, 1, 15, 8, 55),
        alarm_end=datetime(2025, 1, 15, 9, 5),
    )
    result = searcher.check_component(cal)
    assert result, "Todo with alarm at start should match"


def test_alarm_with_repeat() -> None:
    """Alarm with REPEAT and DURATION should match for any repetition in range."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-repeating-alarm")
    event.add("summary", "Wake Up")
    event.add("dtstart", datetime(2025, 1, 15, 7, 0))

    # Alarm that repeats 3 times, every 5 minutes
    # First: 07:00, Second: 07:05, Third: 07:10
    alarm = Alarm()
    alarm.add("action", "AUDIO")
    alarm.add("trigger", timedelta(0))  # At event start
    alarm.add("repeat", 2)  # Repeat 2 more times (3 total)
    alarm.add("duration", timedelta(minutes=5))
    event.add_component(alarm)

    cal.add_component(event)

    # Search for second repetition (07:05)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 7, 3).astimezone(),
        alarm_end=datetime(2025, 1, 15, 7, 8).astimezone(),
    )
    result = searcher._check_alarm_range(event)
    assert result, "Event with repeating alarm should match any repetition"
    result = searcher.check_component(cal)
    assert result, "Event with repeating alarm should match any repetition"


def test_alarm_search_with_recurring_event() -> None:
    """Recurring event with alarm should match when alarm fires in any occurrence."""
    from icalendar.prop import vRecur

    cal = Calendar()
    event = Event()
    event.add("uid", "recurring-with-alarm")
    event.add("summary", "Daily Standup")
    event.add("dtstart", datetime(2025, 1, 15, 9, 0))
    event.add("dtend", datetime(2025, 1, 15, 9, 30))
    event.add("rrule", vRecur(FREQ="DAILY", COUNT=5))

    # Alarm 5 minutes before each occurrence
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(minutes=-5))
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarm on second occurrence (Jan 16 at 08:55)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 16, 8, 50),
        alarm_end=datetime(2025, 1, 16, 9, 0),
    )
    result = searcher.check_component(cal)
    assert result, "Recurring event alarm should match for any occurrence"


def test_alarm_only_search_no_event_range() -> None:
    """Alarm search without event time range should work."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-alarm-only")
    event.add("summary", "Future Event")
    event.add("dtstart", datetime(2025, 2, 1, 10, 0))

    # Alarm 1 week before
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(weeks=-1))
    event.add_component(alarm)

    cal.add_component(event)

    # Search only by alarm time, not event time
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 25, 9, 0),
        alarm_end=datetime(2025, 1, 25, 11, 0),
    )
    result = searcher.check_component(cal)
    assert result, "Should match based on alarm time alone"


def test_alarm_and_event_range_both_specified() -> None:
    """Search with both alarm range and event range should match both criteria."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-both-ranges")
    event.add("summary", "Specific Event")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 11, 0))

    # Alarm 30 minutes before (09:30)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(minutes=-30))
    event.add_component(alarm)

    cal.add_component(event)

    # Search for events on Jan 15 with alarms around 09:30
    searcher = Searcher(
        event=True,
        start=datetime(2025, 1, 15, 0, 0),
        end=datetime(2025, 1, 16, 0, 0),
        alarm_start=datetime(2025, 1, 15, 9, 25),
        alarm_end=datetime(2025, 1, 15, 9, 35),
    )
    result = searcher.check_component(cal)
    assert result, "Should match when both event and alarm are in their respective ranges"


def test_alarm_in_range_event_not_in_range() -> None:
    """Alarm in range but event not in range should still match (if only alarm range specified)."""
    cal = Calendar()
    event = Event()
    event.add("uid", "future-event")
    event.add("summary", "Far Future Event")
    event.add("dtstart", datetime(2025, 2, 15, 10, 0))

    # Alarm 30 days before (fires Jan 16, 10:00)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(days=-30))
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarms in January (event is in February)
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 16, 9, 0),
        alarm_end=datetime(2025, 1, 16, 11, 0),
    )
    result = searcher.check_component(cal)
    assert result, "Should match when alarm is in range, even if event is not"


def test_alarm_trigger_related_end() -> None:
    """Alarm with TRIGGER related to END should work correctly."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event-alarm-at-end")
    event.add("summary", "Conference")
    event.add("dtstart", datetime(2025, 1, 15, 9, 0))
    event.add("dtend", datetime(2025, 1, 15, 17, 0))

    # Alarm at event end (17:00)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(0))
    alarm["TRIGGER"].params["RELATED"] = "END"
    # Note: TRIGGER can have RELATED parameter (START or END)
    # For this test, we assume it's related to END
    event.add_component(alarm)

    cal.add_component(event)

    # Search for alarms at end time
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 16, 55),
        alarm_end=datetime(2025, 1, 15, 17, 5),
    )
    # Note: This test may need adjustment based on actual implementation
    # of RELATED parameter handling
    result = searcher.check_component(cal)
    # This assertion depends on implementation details
    assert result


def test_todo_alarm_no_dtstart_no_due() -> None:
    """Todo with alarm but no DTSTART/DUE should handle alarm appropriately."""
    task = Todo()
    task.add("uid", "floating-task")
    task.add("summary", "Floating Task")

    # Alarm with absolute trigger (since no DTSTART/DUE to relate to)
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", datetime(2025, 1, 15, 10, 0))
    task.add_component(alarm)

    cal = Calendar()
    cal.add_component(task)

    # Search for the absolute alarm time
    searcher = Searcher(
        todo=True,
        alarm_start=datetime(2025, 1, 15, 9, 55),
        alarm_end=datetime(2025, 1, 15, 10, 5),
    )
    result = searcher.check_component(cal)
    assert result, "Todo with absolute alarm trigger should match"


ALARM_RELATED_CASE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:{comp}
UID:related-case-{comp}
DTSTART:20250115T100000Z
{end_prop}:20250115T120000Z
SUMMARY:Alarm RELATED case test
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Reminder
TRIGGER;RELATED={related}:-PT15M
END:VALARM
END:{comp}
END:VCALENDAR
"""


@pytest.mark.parametrize("related", ["END", "end", "End", "eNd"])
@pytest.mark.parametrize(("comp", "end_prop"), [("VEVENT", "DTEND"), ("VTODO", "DUE")])
def test_alarm_related_param_is_case_insensitive(comp: str, end_prop: str, related: str) -> None:
    """RFC 5545 3.2: parameter values are case-insensitive, so RELATED=end means END.

    The alarm fires 15 minutes before the end (11:45), not before the start (09:45).
    """
    cal = Calendar.from_ical(
        ALARM_RELATED_CASE_ICS.format(comp=comp, end_prop=end_prop, related=related)
    )
    kwargs = {"event": True} if comp == "VEVENT" else {"todo": True}

    end_anchored = Searcher(
        alarm_start=datetime(2025, 1, 15, 11, 40, tzinfo=timezone.utc),
        alarm_end=datetime(2025, 1, 15, 11, 50, tzinfo=timezone.utc),
        **kwargs,
    )
    assert end_anchored.check_component(cal), f"RELATED={related} should anchor on {end_prop}"

    start_anchored = Searcher(
        alarm_start=datetime(2025, 1, 15, 9, 40, tzinfo=timezone.utc),
        alarm_end=datetime(2025, 1, 15, 9, 50, tzinfo=timezone.utc),
        **kwargs,
    )
    assert not start_anchored.check_component(cal), (
        f"RELATED={related} must not be treated as START"
    )


def test_alarm_multi_value_related_does_not_crash() -> None:
    """RELATED takes one value, but TRIGGER;RELATED=END,START parses to a list.
    The filter must not crash on it; it falls back to the default, START."""
    cal = Calendar.from_ical(
        ALARM_RELATED_CASE_ICS.format(comp="VEVENT", end_prop="DTEND", related="END,START")
    )
    searcher = Searcher(
        event=True,
        alarm_start=datetime(2025, 1, 15, 9, 40, tzinfo=timezone.utc),
        alarm_end=datetime(2025, 1, 15, 9, 50, tzinfo=timezone.utc),
    )
    assert searcher.check_component(cal)
