"""Sorting components where some lack the sort key.

A missing property sorts as its default: DTSTART as the earliest possible
time (first), DUE as the latest (last), text as the empty string (first),
other date-times as the earliest time, durations and integers as 0.  A reversed sort
key reverses all of that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from icalendar import Event, Todo

from icalendar_searcher import Searcher

UTC = timezone.utc


def _comp(uid: str, cls: type = Event, **props: Any) -> Any:
    comp = cls()
    comp.add("uid", uid)
    for key, value in props.items():
        comp.add(key.replace("_", "-"), value)
    return comp


def _order(key: str, comps: list, reversed: bool = False) -> list[str]:
    searcher = Searcher()
    searcher.add_sort_key(key, reversed=reversed)
    return [str(c["UID"]) for c in searcher.sort(comps)]


T1 = datetime(2025, 1, 1, 10, tzinfo=UTC)
T2 = datetime(2025, 1, 2, 10, tzinfo=UTC)

## (sort key, the components, the order with reversed=False)
CASES = {
    "text": (
        "SUMMARY",
        [_comp("b", summary="b"), _comp("none"), _comp("a", summary="a")],
        ["none", "a", "b"],
    ),
    "another text property": (
        "LOCATION",
        [_comp("x", location="x"), _comp("none")],
        ["none", "x"],
    ),
    "dtstart": (
        "DTSTART",
        [_comp("t2", dtstart=T2), _comp("none", Todo), _comp("t1", dtstart=T1)],
        ["none", "t1", "t2"],
    ),
    "dtstart before year 1970": (
        "DTSTART",
        [_comp("old", dtstart=datetime(1900, 1, 1, tzinfo=UTC)), _comp("none", Todo)],
        ["none", "old"],
    ),
    "due": (
        "DUE",
        [_comp("none", Todo), _comp("t2", Todo, due=T2), _comp("t1", Todo, due=T1)],
        ["t1", "t2", "none"],
    ),
    "due after year 2050": (
        "DUE",
        [_comp("none", Todo), _comp("late", Todo, due=datetime(2100, 1, 1, tzinfo=UTC))],
        ["late", "none"],
    ),
    "other date-time": (
        "COMPLETED",
        [_comp("t1", Todo, completed=T1), _comp("none", Todo)],
        ["none", "t1"],
    ),
    "integer": (
        "SEQUENCE",
        [_comp("s2", sequence=2), _comp("none"), _comp("s1", sequence=1)],
        ["none", "s1", "s2"],
    ),
    "duration": (
        "DURATION",
        [_comp("d1", Todo, duration=timedelta(hours=1)), _comp("none", Todo)],
        ["none", "d1"],
    ),
    "priority": (
        "PRIORITY",
        [_comp("p1", Todo, priority=1), _comp("none", Todo)],
        ["none", "p1"],
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_missing_value_sorts_as_its_default(name: str) -> None:
    key, comps, expected = CASES[name]
    assert _order(key, comps) == expected


@pytest.mark.parametrize("name", CASES)
def test_missing_value_reversed(name: str) -> None:
    key, comps, expected = CASES[name]
    assert _order(key, comps, reversed=True) == expected[::-1]


def test_status_default_per_component_type() -> None:
    """A VEVENT without STATUS sorts as TENTATIVE."""
    comps = [
        _comp("tentative", status="TENTATIVE"),
        _comp("none"),
        _comp("confirmed", status="CONFIRMED"),
    ]
    assert _order("STATUS", comps) == ["confirmed", "tentative", "none"]


@pytest.mark.parametrize("reversed", [False, True])
def test_reversed_text_with_common_prefix(reversed: bool) -> None:
    comps = [_comp("ab", summary="ab"), _comp("abc", summary="abc"), _comp("b", summary="b")]
    expected = ["ab", "abc", "b"]
    assert _order("SUMMARY", comps, reversed=reversed) == (expected[::-1] if reversed else expected)


def test_secondary_key_after_a_reversed_one() -> None:
    comps = [
        _comp("a2", summary="a", dtstart=T2),
        _comp("b1", summary="b", dtstart=T1),
        _comp("a1", summary="a", dtstart=T1),
    ]
    searcher = Searcher()
    searcher.add_sort_key("SUMMARY", reversed=True)
    searcher.add_sort_key("DTSTART")
    assert [str(c["UID"]) for c in searcher.sort(comps)] == ["b1", "a1", "a2"]
