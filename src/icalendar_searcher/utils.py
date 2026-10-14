"""Utility functions for icalendar-searcher."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from itertools import tee

from icalendar.prop import TypesFactory

## We need an instance of the icalendar.prop.TypesFactory class.
## We'll make a global instance rather than instantiate it for
## every loop iteration
types_factory = TypesFactory()

## Negated operators, mapped to the positive operator they negate.  A
## negation matches when the property is defined and the positive
## operator does not match.
NEGATED_OPERATORS = {"!=": "==", "!contains": "contains"}

## Operators that take no value, only checking whether the property is set
PRESENCE_OPERATORS = ("def", "undef")

SUPPORTED_OPERATORS = ("contains", "==", *NEGATED_OPERATORS, *PRESENCE_OPERATORS)


## Helper to normalize date/datetime for comparison
## (I feel this one is duplicated over many projects ...)
def _normalize_dt(dt_value: date | datetime, tz: tzinfo | None = None) -> datetime:
    """Convert date to datetime for comparison, or return datetime as-is with timezone.

    Dates and floating (naive) datetimes have no time zone of their own.
    They are interpreted in ``tz`` if given, otherwise in the time zone
    of the Python process.
    """
    if dt_value is None:
        return None
    ## If it's a date (not datetime), convert to datetime at midnight
    if hasattr(dt_value, "year") and not hasattr(dt_value, "hour"):
        dt_value = datetime.combine(dt_value, time.min)
    if tz is not None and dt_value.tzinfo is None:
        ## pytz tzinfo objects carry a fixed offset and must be applied with localize()
        if hasattr(tz, "localize"):
            try:
                dt_value = tz.localize(dt_value)
            except (OverflowError, ValueError):
                dt_value = dt_value.replace(
                    tzinfo=_edge_offset(dt_value, lambda d: tz.localize(d).utcoffset())
                )
        else:
            dt_value = dt_value.replace(tzinfo=tz)
    ## A fixed offset makes timedelta arithmetic exact, also across DST changes
    try:
        return dt_value.astimezone()
    except (OverflowError, ValueError):
        ## Within a day of datetime.min / datetime.max, the value may not
        ## exist in the process time zone.  Aware datetimes compare fine
        ## across time zones, so keep it in its own.
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(
                tzinfo=_edge_offset(dt_value, lambda d: d.astimezone().utcoffset())
            )
        return dt_value


def _edge_offset(dt_value: datetime, offset_at: Callable[[datetime], timedelta]) -> timezone:
    """The UTC offset for a naive value at the end of the datetime range,
    taken from a value two days further inside it, as that one still has one."""
    inwards = timedelta(days=-2 if dt_value.year == datetime.max.year else 2)
    return timezone(offset_at(dt_value + inwards))


## The ends of the datetime range, as aware values
DT_MIN = datetime.min.replace(tzinfo=timezone.utc)
DT_MAX = datetime.max.replace(tzinfo=timezone.utc)


def _shift(dt_value: date | datetime, delta: timedelta) -> date | datetime:
    """``dt_value + delta``, clamped to DT_MIN / DT_MAX instead of overflowing."""
    try:
        return dt_value + delta
    except OverflowError:
        return DT_MAX if delta > timedelta(0) else DT_MIN


## Helper - generators are generally more neat than lists,
## but bool(x) will always return True.  I'd like to verify
## that a generator is not empty, without side effects.
def _iterable_or_false(g: Iterable, _debug_print_peek: bool = False) -> bool | Iterable:
    """This method will return False if it's not possible to get an
    item from the iterable (which can only be done by utilizing
    `next`).  It will then return a new iterator that behaves like
    the original iterator (like if `next` wasn't used).

    Uses itertools.tee to create two independent iterators: one for
    checking if the iterator is empty, and one to return.
    """
    if not isinstance(g, Iterator):
        return bool(g) and g

    # Create two independent iterators from the input
    check_it, result_it = tee(g)

    try:
        my_value = next(check_it)
        if _debug_print_peek:
            print(my_value)
        return result_it  # Return the untouched iterator
    except StopIteration:
        return False
