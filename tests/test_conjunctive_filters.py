"""
Property filters are conjunctive, whatever order they were added in.

Every filter that matches the component is combined with every filter that
does not, in both orders, across the property classes: ordinary properties,
comma-list plural (``categories``) and singular (``category``), ``undef``,
and non-SIMPLE collation.  Expanded recurrences (where ``skip_undef`` comes
into play) are tested end to end at the bottom.
"""

from datetime import date, datetime
from itertools import permutations
from typing import Any, NamedTuple

import pytest
from icalendar import Event

from icalendar_searcher import Searcher
from icalendar_searcher.collation import HAS_PYICU, Collation


class F(NamedTuple):
    key: str
    value: Any
    operator: str
    kwargs: dict[str, Any] = {}


def _event() -> Event:
    event = Event()
    event.add("uid", "123")
    event.add("summary", "Training session")
    event.add("location", "Oslo")
    event.add("status", "CONFIRMED")
    event.add("categories", ["work", "home"])
    event.add("dtstart", datetime(2025, 1, 1, 10))
    return event


_unicode = {"collation": Collation.UNICODE, "case_sensitive": False}

## Filters that match _event()
MATCHING = {
    "summary-contains": F("SUMMARY", "rain", "contains"),
    "location-eq": F("LOCATION", "Oslo", "=="),
    "status-eq": F("STATUS", "CONFIRMED", "=="),
    "categories-contains": F("categories", "work", "contains"),
    "categories-contains-set": F("categories", "work,home", "contains"),
    "categories-eq": F("categories", "home,work", "=="),
    "category-contains": F("category", "ork", "contains"),
    "category-eq": F("category", "home", "=="),
    "dtend-undef": F("DTEND", None, "undef"),
    "location-def": F("LOCATION", None, "def"),
    "location-ne": F("LOCATION", "Berlin", "!="),
    "categories-ne": F("categories", "work", "!="),
    "category-ne": F("category", "play", "<>"),
    "summary-contains-unicode": F("SUMMARY", "TRAINING", "contains", _unicode),
    "category-contains-unicode": F("category", "WOR", "contains", _unicode),
}

## Filters that do not match _event()
FAILING = {
    "summary-contains": F("SUMMARY", "nomatch", "contains"),
    "location-eq": F("LOCATION", "Berlin", "=="),
    "status-eq": F("STATUS", "CANCELLED", "=="),
    "categories-contains": F("categories", "play", "contains"),
    "categories-eq": F("categories", "work", "=="),
    "category-contains": F("category", "xyz", "contains"),
    "category-eq": F("category", "wor", "=="),
    "location-undef": F("LOCATION", None, "undef"),
    "categories-undef": F("categories", None, "undef"),
    "dtend-def": F("DTEND", None, "def"),
    "location-ne": F("LOCATION", "Oslo", "!="),
    "dtend-ne": F("DTEND", datetime(2025, 1, 1, 11), "!="),
    "categories-ne": F("categories", "home,work", "!="),
    "category-ne": F("category", "home", "<>"),
    "summary-contains-unicode": F("SUMMARY", "xyz", "contains", _unicode),
    "category-contains-unicode": F("category", "XYZ", "contains", _unicode),
}


def _needs_icu(*filters: F) -> bool:
    return any(f.kwargs.get("collation") == Collation.UNICODE for f in filters)


def _check(filters: tuple[F, ...]) -> bool:
    if _needs_icu(*filters) and not HAS_PYICU:
        pytest.skip("PyICU not installed")
    searcher = Searcher(event=True)
    for f in filters:
        searcher.add_property_filter(f.key, f.value, operator=f.operator, **f.kwargs)
    return bool(searcher.check_component(_event()))


@pytest.mark.parametrize("name", MATCHING)
def test_single_matching_filter(name: str) -> None:
    assert _check((MATCHING[name],))


@pytest.mark.parametrize("name", FAILING)
def test_single_failing_filter(name: str) -> None:
    assert not _check((FAILING[name],))


## A Searcher holds one filter per property, so pairs on the same key are left out
@pytest.mark.parametrize(
    ("matching", "failing"),
    [
        (m, f)
        for m in MATCHING
        for f in FAILING
        if MATCHING[m].key.lower() != FAILING[f].key.lower()
    ],
)
@pytest.mark.parametrize("failing_first", [False, True], ids=["match-first", "fail-first"])
def test_matching_and_failing_filter(matching: str, failing: str, failing_first: bool) -> None:
    filters = (MATCHING[matching], FAILING[failing])
    if failing_first:
        filters = filters[::-1]
    assert not _check(filters)


@pytest.mark.parametrize(
    ("first", "second"),
    [p for p in permutations(MATCHING, 2) if MATCHING[p[0]].key != MATCHING[p[1]].key],
)
def test_two_matching_filters(first: str, second: str) -> None:
    assert _check((MATCHING[first], MATCHING[second]))


def test_skip_undef_does_not_skip_later_filters() -> None:
    """With skip_undef, an undef filter is skipped, but the next filter still applies.

    Not reachable with a failing second filter through ``check_component``,
    since the base element of a recurrence set is rejected before expansion.
    """
    event = _event()
    event.add("dtend", datetime(2025, 1, 1, 11))

    searcher = Searcher(event=True)
    searcher.add_property_filter("DTEND", None, operator="undef")
    searcher.add_property_filter("SUMMARY", "rain", operator="contains")
    assert not searcher._check_property_filters(event)
    assert searcher._check_property_filters(event, skip_undef=True)

    searcher.add_property_filter("SUMMARY", "nomatch", operator="contains")
    assert not searcher._check_property_filters(event, skip_undef=True)


@pytest.mark.parametrize("undef_first", [False, True], ids=["undef-first", "undef-last"])
@pytest.mark.parametrize(("summary", "expected"), [("Stand", 3), ("nomatch", 0)])
def test_expanded_recurrence_undef(undef_first: bool, summary: str, expected: int) -> None:
    """undef on DTEND combined with another filter, on an expanded all-day recurrence.

    recurring_ical_events adds DTEND to the occurrences; the master has none.
    """
    event = Event()
    event.add("uid", "r1")
    event.add("summary", "Standup")
    event.add("dtstart", date(2025, 1, 1))
    event.add("rrule", {"freq": "daily", "count": 3})

    filters = [F("DTEND", None, "undef"), F("SUMMARY", summary, "contains")]
    if not undef_first:
        filters.reverse()
    searcher = Searcher(
        event=True, start=datetime(2025, 1, 1), end=datetime(2025, 1, 10), expand=True
    )
    for f in filters:
        searcher.add_property_filter(f.key, f.value, operator=f.operator)
    result = searcher.check_component(event)
    assert len(list(result or [])) == expected


@pytest.mark.parametrize(
    ("f", "expected"),
    [
        ## the master has no DTEND; the expanded occurrences gain a computed one
        (F("DTEND", None, "def"), 0),
        (F("DTEND", date(2025, 1, 2), "!="), 0),
        (F("SUMMARY", None, "def"), 3),
        (F("SUMMARY", "Stand", "!="), 3),
        (F("SUMMARY", "Standup", "!="), 0),
    ],
    ids=repr,
)
def test_expanded_recurrence_negation(f: F, expected: int) -> None:
    """def and the negations on an expanded all-day recurrence.

    Unlike undef, these are not skipped on the occurrences: the master's
    verdict on DTEND has to stand, not the computed DTEND of an occurrence.
    """
    event = Event()
    event.add("uid", "r1")
    event.add("summary", "Standup")
    event.add("dtstart", date(2025, 1, 1))
    event.add("rrule", {"freq": "daily", "count": 3})

    searcher = Searcher(
        event=True, start=datetime(2025, 1, 1), end=datetime(2025, 1, 10), expand=True
    )
    searcher.add_property_filter(f.key, f.value, operator=f.operator)
    result = searcher.check_component(event)
    assert len(list(result or [])) == expected
