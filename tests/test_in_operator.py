"""The ``in`` operator: the property equals any one of several values."""

from datetime import date, datetime

import pytest
from icalendar import Calendar, Todo

from icalendar_searcher import Searcher


def _todo(**props: object) -> Todo:
    todo = Todo()
    todo.add("uid", "123")
    for key, value in props.items():
        todo.add(key, value)
    return todo


def _matches(component: Todo, key: str, values: object, **kwargs: object) -> bool:
    searcher = Searcher(todo=True)
    searcher.add_property_filter(key, values, operator="in", **kwargs)
    return bool(searcher.check_component(component))


@pytest.mark.parametrize(
    "priority,values,expected",
    [
        (5, [5], True),
        (2, range(1, 4), True),
        (4, range(1, 4), False),
        (9, {1, 5, 9}, True),
        (0, (0,), True),
    ],
)
def test_in_integer(priority: int, values: object, expected: bool) -> None:
    assert _matches(_todo(priority=priority), "PRIORITY", values) == expected


def test_in_requires_property_defined() -> None:
    """Like ==, a component without the property does not match - not
    even with PRIORITY 0, the RFC 5545 "undefined" value.  Use undef."""
    assert not _matches(_todo(), "PRIORITY", [0, 1])


def test_in_text_respects_case_sensitivity() -> None:
    todo = _todo(status="NEEDS-ACTION")
    assert _matches(todo, "STATUS", ["COMPLETED", "NEEDS-ACTION"])
    assert not _matches(todo, "STATUS", ["needs-action"])
    assert _matches(todo, "STATUS", ["needs-action"], case_sensitive=False)


def test_in_needs_a_collection() -> None:
    searcher = Searcher(todo=True)
    with pytest.raises(ValueError):
        searcher.add_property_filter("PRIORITY", None, operator="in")
    with pytest.raises(TypeError):
        searcher.add_property_filter("STATUS", "COMPLETED", operator="in")


def test_in_not_supported_for_categories() -> None:
    searcher = Searcher(todo=True)
    for key in ("categories", "category"):
        with pytest.raises(NotImplementedError):
            searcher.add_property_filter(key, ["work", "home"], operator="in")


def test_in_takes_a_generator() -> None:
    assert _matches(_todo(priority=2), "PRIORITY", (x for x in (1, 2)))


def test_in_empty_collection_matches_nothing() -> None:
    assert not _matches(_todo(priority=2), "PRIORITY", [])


def test_in_multi_instance_property() -> None:
    """A property occurring more than once matches if any instance does."""
    todo = _todo(comment="first")
    todo.add("comment", "second")
    assert _matches(todo, "COMMENT", ["second", "third"])
    assert not _matches(todo, "COMMENT", ["third"])


def test_in_date_property() -> None:
    todo = _todo(due=date(2026, 11, 13))
    assert _matches(todo, "DUE", [date(2026, 11, 12), date(2026, 11, 13)])
    assert not _matches(todo, "DUE", [date(2026, 11, 12)])


def test_in_through_filter_with_recurrence() -> None:
    """End to end: filter() with expansion keeps the occurrences of a
    recurring task whose priority is in the collection."""
    cal = Calendar()
    for uid, priority in (("in", 2), ("out", 5)):
        todo = _todo(
            priority=priority,
            dtstart=datetime(2026, 11, 1, 10),
            rrule={"FREQ": "DAILY", "COUNT": 3},
        )
        todo["uid"] = uid
        cal.add_component(todo)
    searcher = Searcher(
        todo=True, expand=True, start=datetime(2026, 11, 1), end=datetime(2026, 11, 10)
    )
    searcher.add_property_filter("PRIORITY", range(1, 4), operator="in")
    found = list(searcher.filter(cal.subcomponents))
    assert {str(x["uid"]) for x in found} == {"in"}
    assert len(found) == 3
