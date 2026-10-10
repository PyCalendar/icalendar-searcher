"""
The ``!=`` / ``<>`` and ``def`` operators.

``!=`` (spelled ``<>`` too) is the negation of ``==``, and like every other
value operator it requires the property to be defined: a component without
the property does not match.  This follows RFC 4791 section 9.7.2, where a
``prop-filter`` holding a ``text-match`` (negated or not) only matches a
defined property.  "Not defined" is the job of ``undef``.

``def`` is the inverse of ``undef``.
"""

from datetime import datetime

import pytest
from icalendar import Calendar, Event, vRecur

from icalendar_searcher import Searcher


def _event(**props: object) -> Event:
    event = Event()
    event.add("uid", "123")
    for key, value in props.items():
        event.add(key, value)
    return event


def _matches(event: Event, key: str, value: object, operator: str, **kwargs: object) -> bool:
    searcher = Searcher(event=True)
    searcher.add_property_filter(key, value, operator=operator, **kwargs)
    return bool(searcher.check_component(event))


NEGATIONS = ("!=", "<>")


@pytest.mark.parametrize("operator", NEGATIONS)
@pytest.mark.parametrize(
    ("props", "key", "value", "expected"),
    [
        ## ordinary property
        ({"summary": "Training session"}, "SUMMARY", "Training session", False),
        ({"summary": "Training session"}, "SUMMARY", "Training", True),
        ({"summary": "Training session"}, "SUMMARY", "training session", True),
        ({}, "SUMMARY", "Training session", False),
        ## plural: negation of exact set equality
        ({"categories": ["work", "home"]}, "categories", "home,work", False),
        ({"categories": ["work", "home"]}, "categories", "work", True),
        ({"categories": ["work"]}, "categories", "work", False),
        ({"categories": ["work"]}, "categories", "home", True),
        ({}, "categories", "work", False),
        ## singular: no token equals the value
        ({"categories": ["work", "home"]}, "category", "home", False),
        ({"categories": ["work", "home"]}, "category", "hom", True),
        ({"categories": ["work", "home"]}, "category", "play", True),
        ({}, "category", "work", False),
    ],
)
def test_negation(props: dict, key: str, value: object, expected: bool, operator: str) -> None:
    assert _matches(_event(**props), key, value, operator) is expected


@pytest.mark.parametrize("operator", NEGATIONS)
def test_negation_case_insensitive(operator: str) -> None:
    event = _event(summary="Training session", categories=["Work"])
    assert not _matches(event, "SUMMARY", "training SESSION", operator, case_sensitive=False)
    assert _matches(event, "SUMMARY", "training", operator, case_sensitive=False)
    assert not _matches(event, "category", "WORK", operator, case_sensitive=False)
    assert not _matches(event, "categories", "work", operator, case_sensitive=False)


def test_negation_spellings_are_stored_alike() -> None:
    a = Searcher()
    a.add_property_filter("SUMMARY", "x", operator="<>")
    b = Searcher()
    b.add_property_filter("SUMMARY", "x", operator="!=")
    assert a._property_operator == b._property_operator == {"summary": "!="}


def test_multi_instance_property() -> None:
    """A property occurring more than once matches if any instance does."""
    event = _event()
    event.add("comment", "alpha")
    event.add("comment", "beta")
    assert _matches(event, "COMMENT", "alpha", "==")
    assert _matches(event, "COMMENT", "beta", "==")
    assert not _matches(event, "COMMENT", "gamma", "==")
    assert not _matches(event, "COMMENT", "alpha", "!=")
    assert _matches(event, "COMMENT", "gamma", "!=")


def test_resources_is_one_text_value() -> None:
    """RESOURCES is not a comma-token list: the value is matched as one string."""
    event = _event(resources="projector,room")
    assert _matches(event, "RESOURCES", "projector,room", "==")
    assert _matches(event, "RESOURCES", "projector", "!=")


@pytest.mark.parametrize("operator", ("==", "contains", "!=", "<>"))
def test_value_operators_refuse_none(operator: str) -> None:
    with pytest.raises(ValueError):
        Searcher().add_property_filter("SUMMARY", None, operator=operator)


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("def", None, 1),
        ("!=", "Oslo", 0),
        ("!=", "Bergen", 1),
    ],
)
def test_negation_on_override(operator: str, value: object, expected: int) -> None:
    """An override (RECURRENCE-ID) adding a property the master lacks."""
    cal = Calendar()
    master = Event()
    master.add("uid", "weekly")
    master.add("summary", "Weekly")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=3))
    cal.add_component(master)
    override = Event()
    override.add("uid", "weekly")
    override.add("summary", "Weekly")
    override.add("location", "Oslo")
    override.add("dtstart", datetime(2025, 1, 13, 10, 0))
    override.add("dtend", datetime(2025, 1, 13, 11, 0))
    override.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(override)

    searcher = Searcher(
        event=True, start=datetime(2025, 1, 1), end=datetime(2025, 2, 1), expand=True
    )
    searcher.add_property_filter("LOCATION", value, operator=operator)
    assert len(list(searcher.check_component(cal) or [])) == expected


@pytest.mark.parametrize(
    ("props", "key", "expected"),
    [
        ({"location": "Oslo"}, "LOCATION", True),
        ({}, "LOCATION", False),
        ({"categories": ["work"]}, "categories", True),
        ({"categories": ["work"]}, "category", True),
        ({}, "categories", False),
        ({}, "category", False),
    ],
)
def test_def(props: dict, key: str, expected: bool) -> None:
    event = _event(**props)
    assert _matches(event, key, None, "def") is expected
    assert _matches(event, key, None, "undef") is not expected


def test_def_stores_no_value() -> None:
    searcher = Searcher()
    searcher.add_property_filter("LOCATION", None, operator="def")
    assert searcher._property_filters == {}
    assert searcher._property_operator == {"location": "def"}


@pytest.mark.parametrize("operator", ("~", "<", "<=", ">", ">=", "bogus"))
def test_unimplemented_operators_raise(operator: str) -> None:
    with pytest.raises(NotImplementedError):
        Searcher().add_property_filter("SUMMARY", "x", operator=operator)
