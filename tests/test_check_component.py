from datetime import datetime

import pytest
from icalendar import Calendar, Event, Todo

from icalendar_searcher import Searcher
from icalendar_searcher.utils import _iterable_or_false


def test_include_completed() -> None:
    ## Status Needs Action
    task_sna = Todo()
    task_sna["STATUS"] = "NEEDS-ACTION"

    ## No Status
    task_ns = Todo()

    ## No Status, Completed
    task_nsc = Todo()
    task_nsc["COMPLETED"] = datetime(2000, 1, 2)

    ## Status cancelled
    task_sc = Todo()
    task_sc["STATUS"] = "CANCELLED"

    for component in (task_sna, task_ns, task_nsc, task_sc):
        component["uid"] = "123"

    onlypending = Searcher(todo=True)
    all1 = Searcher(todo=True, include_completed=True)
    all2 = Searcher()
    for component in (task_nsc, task_sc):
        assert not onlypending.check_component(component)
        assert all1.check_component(component)
        assert all2.check_component(component)

    for component in (task_ns, task_sna):
        assert onlypending.check_component(component)
        assert all1.check_component(component)
        assert all2.check_component(component)


def test_check_empty() -> None:
    """Test that an empty calendar (no components) raises a ValueError."""
    searcher = Searcher(start=datetime(1970, 1, 1), end=datetime.now())

    # Create an empty calendar (no VEVENT, VTODO, or VJOURNAL components)
    empty_calendar = Calendar()

    # An empty calendar should raise a ValueError
    # See _validate_and_normalize_component() at line 498
    with pytest.raises(ValueError, match="Empty component"):
        searcher.check_component(empty_calendar)


def test_filter_component_types() -> None:
    cal = Calendar()
    comp = Event()
    comp["uid"] = "someuid"
    cal.add_component(comp)
    for searcher in (
        Searcher(todo=True),
        Searcher(event=False),
        Searcher(event=False, journal=True),
    ):
        assert not searcher.check_component(cal)
    for searcher in (Searcher(), Searcher(event=True), Searcher(todo=False)):
        assert searcher.check_component(cal)


## _iterable_or_false() was defined to support return values evaluating into False,
## but still support generators
def test_iterable_or_false() -> None:
    assert _iterable_or_false(["a", "b", "c"])
    assert "b" in _iterable_or_false(["a", "b", "c"])
    assert _iterable_or_false([]) is False
    assert _iterable_or_false(range(1, 4))
    assert _iterable_or_false(range(0, 0)) is False
    mygen1 = (x for x in range(1, 8) if x > 2)
    mygen2 = (x for x in range(1, 8) if x < 0)
    assert next(_iterable_or_false(mygen1)) == 3
    assert _iterable_or_false(mygen2) is False


def test_yule_tree1() -> None:
    """
    In caldav, the basic usage example stopped working
    """
    data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VTODO
CATEGORIES:outdoor
DTSTAMP:20251119T133355Z
DTSTART;VALUE=DATE:20201213
DUE;VALUE=DATE:20201220
PRIORITY:2
RRULE:FREQ=YEARLY
STATUS:NEEDS-ACTION
SUMMARY:Chop down a tree and drag it into the living room
UID:652e3718-c54c-11f0-9203-1c1bb5134174
END:VTODO
END:VCALENDAR"""
    cal = Calendar.from_ical(data)
    for prop_filter in (("categories", "outdoor", "=="),):
        for searcher in (Searcher(), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert searcher._check_property_filters(cal.subcomponents[0])
            assert searcher.check_component(cal)
    for prop_filter in (
        ("categories", "out", "=="),
        ("categories", "outdoors"),
        ("categories", "out"),
    ):
        for searcher in (Searcher(), Searcher(event=True), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert not searcher._check_property_filters(cal.subcomponents[0])
            assert not searcher.check_component(cal)


def test_yule_tree2() -> None:
    """
    categories are difficult
    """
    data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//python-caldav//caldav//en_DK
BEGIN:VTODO
CATEGORIES:outdoor,family,winter
DTSTAMP:20251119T133355Z
DTSTART;VALUE=DATE:20201213
DUE;VALUE=DATE:20201220
PRIORITY:2
RRULE:FREQ=YEARLY
STATUS:NEEDS-ACTION
SUMMARY:Chop down a tree and drag it into the living room
UID:652e3718-c54c-11f0-9203-1c1bb5134174
END:VTODO
END:VCALENDAR"""
    cal = Calendar.from_ical(data)
    for prop_filter in (
        ("categories", ["family", "outdoor", "winter"], "=="),
        ("categories", "family,outdoor,winter", "=="),
        ("categories", "winter,outdoor,family", "=="),
        ("categories", "winter,outdoor"),
        ("categories", ("winter", "outdoor")),
    ):
        for searcher in (Searcher(), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert searcher._check_property_filters(cal.subcomponents[0])
            assert searcher.check_component(cal)
    for prop_filter in (
        ("categories", "outdoor", "=="),
        ("categories", "out"),
        ("categories", "out", "=="),
        ("categories", "outdoors"),
        ("categories", "outdoor,summer"),
        ("categories", ("outdoor,winter"), "=="),
    ):
        for searcher in (Searcher(), Searcher(event=True), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert not searcher._check_property_filters(cal.subcomponents[0])
            assert not searcher.check_component(cal)
    # "category" (singular) does substring matching within category names
    for prop_filter in (
        ("category", "outdoor", "=="),  # Exact match to one category
        ("category", "out"),  # Substring match within "outdoor"
    ):
        for searcher in (Searcher(), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert searcher._check_property_filters(cal.subcomponents[0])
            assert searcher.check_component(cal)
    # "category" (singular) should NOT match these
    for prop_filter in (
        ("category", "family,outdoor,winter", "=="),  # No category literally equals this
        ("category", "out", "=="),  # No category exactly equals "out"
    ):
        for searcher in (Searcher(), Searcher(todo=True)):
            searcher.add_property_filter(*prop_filter)
            assert not searcher._check_property_filters(cal.subcomponents[0])
            assert not searcher.check_component(cal)


@pytest.mark.parametrize("rrule", [None, "RRULE:FREQ=DAILY\n"])
def test_vtodo_no_dtstart_range_check(rrule: str | None) -> None:
    """
    A VTODO with no DTSTART/DUE/CREATED must not crash on a time-range search,
    whether or not it has an RRULE.
    """
    rrule_line = rrule or ""
    data = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
COMPLETED:20231001T105204Z
DTSTAMP:20231001T124832Z
{rrule_line}STATUS:COMPLETED
SUMMARY:g\xe5 tur
UID:d432d0a2-6058-11ee-97c8-982cbcdd642c
END:VTODO
END:VCALENDAR"""
    cal = Calendar.from_ical(data)
    end = datetime(2026, 5, 28, 0, 0, 0)
    searcher = Searcher(todo=True, end=end, include_completed=True)
    result = searcher.check_component(cal)
    assert bool(result)


@pytest.mark.parametrize("status", ["completed", "Completed", "cancelled", "Cancelled"])
def test_include_completed_status_case_insensitive(status: str) -> None:
    """STATUS is an enumerated value, and RFC 5545 section 2 makes those
    case-insensitive: a task with STATUS:completed is completed."""
    data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VTODO
UID:status-case
DTSTAMP:20260101T000000Z
SUMMARY:task
STATUS:{status}
END:VTODO
END:VCALENDAR"""
    cal = Calendar.from_ical(data)
    assert not Searcher(todo=True).check_component(cal)
    assert Searcher(todo=True, include_completed=True).check_component(cal)


def test_include_completed_repeated_status_does_not_crash() -> None:
    """STATUS may occur only once (RFC 5545 3.6.2), but a server may send it twice.
    icalendar then returns a list; the filter must not crash on it."""
    data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VTODO
UID:status-twice
DTSTAMP:20260101T000000Z
SUMMARY:task
STATUS:NEEDS-ACTION
STATUS:IN-PROCESS
END:VTODO
END:VCALENDAR"""
    cal = Calendar.from_ical(data)
    assert Searcher(todo=True).check_component(cal)
