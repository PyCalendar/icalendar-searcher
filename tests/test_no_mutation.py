"""
Tests that check_component() does not mutate the Searcher object.

A Searcher must be reusable: calling check_component() (or filter()) multiple
times must produce consistent results and must not change the Searcher's own
fields as a side effect.

Ref: https://github.com/python-caldav/caldav/issues/650
"""

from datetime import date, datetime, timezone

import pytest
from icalendar import Calendar, Todo

from icalendar_searcher import Searcher


def _pending_todo(uid: str = "pending") -> Todo:
    task = Todo()
    task.add("uid", uid)
    task.add("summary", "Pending task")
    task.add("status", "NEEDS-ACTION")
    return task


def _completed_todo(uid: str = "done") -> Todo:
    task = Todo()
    task.add("uid", uid)
    task.add("summary", "Done task")
    task.add("status", "COMPLETED")
    task.add("completed", datetime(2000, 1, 2, tzinfo=timezone.utc))
    return task


def test_include_completed_none_not_mutated() -> None:
    """include_completed=None must remain None after check_component()."""
    searcher = Searcher(todo=True)
    assert searcher.include_completed is None

    searcher.check_component(_pending_todo())

    assert searcher.include_completed is None, (
        "check_component() mutated include_completed from None — "
        "this breaks reuse of the Searcher object"
    )


def test_include_completed_none_not_mutated_on_completed_todo() -> None:
    """include_completed=None must remain None even after filtering a completed todo."""
    searcher = Searcher(todo=True)
    assert searcher.include_completed is None

    searcher.check_component(_completed_todo())

    assert searcher.include_completed is None, (
        "check_component() mutated include_completed from None"
    )


def test_component_type_flags_not_mutated() -> None:
    """todo/event/journal flags that are None must remain None after check_component()."""
    searcher = Searcher(todo=True)
    assert searcher.event is None
    assert searcher.journal is None

    searcher.check_component(_pending_todo())

    assert searcher.event is None, "check_component() mutated event flag from None"
    assert searcher.journal is None, "check_component() mutated journal flag from None"


def test_all_none_flags_not_mutated() -> None:
    """When all of todo/event/journal are None, they must remain None after check_component()."""
    searcher = Searcher()  # all type flags None
    assert searcher.todo is None
    assert searcher.event is None
    assert searcher.journal is None

    cal = Calendar()
    cal.add_component(_pending_todo())
    searcher.check_component(cal)

    assert searcher.todo is None, "check_component() mutated todo flag from None"
    assert searcher.event is None, "check_component() mutated event flag from None"
    assert searcher.journal is None, "check_component() mutated journal flag from None"


def test_start_date_not_mutated_to_datetime() -> None:
    """start/end given as date objects must not be replaced with datetime after check_component()."""
    start = date(2020, 1, 1)
    end = date(2030, 1, 1)
    searcher = Searcher(todo=True, start=start, end=end)
    assert type(searcher.start) is date
    assert type(searcher.end) is date

    task = _pending_todo()
    task.add("dtstart", datetime(2025, 6, 1, tzinfo=timezone.utc))
    task.add("due", datetime(2025, 7, 1, tzinfo=timezone.utc))
    searcher.check_component(task)

    assert type(searcher.start) is date, (
        f"check_component() replaced start with {searcher.start!r} (type {type(searcher.start).__name__})"
    )
    assert type(searcher.end) is date, (
        f"check_component() replaced end with {searcher.end!r} (type {type(searcher.end).__name__})"
    )


## The component being checked must not be mutated either.  icalendar's
## ``component.categories`` accessor inserts an empty CATEGORIES property when
## none is present, so reading it from a filter or a sort key left an empty
## ``CATEGORIES:`` line behind - and a client that then added a category and
## saved the component ended up with two CATEGORIES lines.


@pytest.mark.parametrize("key", ["categories", "category"])
@pytest.mark.parametrize("operator", ["undef", "contains", "=="])
def test_category_filter_does_not_mutate_component(key: str, operator: str) -> None:
    task = _pending_todo()
    before = task.to_ical()
    searcher = Searcher(todo=True)
    searcher.add_property_filter(key, None if operator == "undef" else "foo", operator=operator)
    searcher.check_component(task)
    assert "CATEGORIES" not in task
    assert task.to_ical() == before


def test_category_sort_does_not_mutate_component() -> None:
    task = _pending_todo()
    before = task.to_ical()
    searcher = Searcher(todo=True)
    searcher.add_sort_key("categories")
    searcher.sorting_value(task)
    assert task.to_ical() == before


def test_category_filter_multiple_properties_not_merged() -> None:
    """Several CATEGORIES lines must still be matched, but left as they are."""
    task = _pending_todo()
    task.add("categories", ["foo"])
    task.add("categories", ["bar"])
    before = task.to_ical()
    searcher = Searcher(todo=True)
    searcher.add_property_filter("categories", "bar", operator="contains")
    assert searcher.check_component(task)
    assert task.to_ical() == before
