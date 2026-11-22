## As of 2025-11-17, this comments and the comments on
## test_sorting_value_mixed_types_and_reverse was added by Tobias
## Brox.  Almost everything else was made by GitHub Copilot, but
## it failed to take credits for it as well as providing a pull request
## for it.

from collections.abc import Callable
from datetime import datetime as real_datetime

from icalendar import Calendar, Event, Todo

import icalendar_searcher.searcher
from icalendar_searcher import Searcher
from icalendar_searcher.searcher import _Reversed


## TODO: This is a fragile test - there is no requirement that the
## values turn out the way they do, the only requiement is that they
## can be sorted correctly.  I think it would be a good idea to
## replace this with a test that creates several events and verifies
## that the sorting_value delivers things that can be sorted in the
## correct order.
## TODO: Currently we're only testing the passing of an
## icalendar.Calendar object as the component.  We should also verify
## that those works:
##
## 1) A wrapped Calendar object (i.e. caldav.calendarobjectresource.Event)
##
## 2) the icalendar.Event object directly, without being part of an
## icalendar (this probably breaks now, but it should be acceptable)
def test_sorting_value_mixed_types_and_reverse() -> None:
    """Check dtstart -> formatted string, priority numeric, reversed summary -> wrapped,
    and categories -> joined string."""
    cal = Calendar()
    ev = Event()
    ev.add("dtstart", real_datetime(2025, 1, 2, 9, 0))
    ev.add("priority", 5)
    ev.add("summary", "abc")
    ev.add("categories", ["x", "y"])
    cal.add_component(ev)

    s = Searcher()
    s.add_sort_key("dtstart", reversed=False)
    s.add_sort_key("priority", reversed=False)
    s.add_sort_key("summary", reversed=True)
    s.add_sort_key("categories", reversed=False)

    vals = s.sorting_value(cal)

    assert vals[0] == "2025-01-02090000"
    assert vals[1] == 5
    assert vals[2] == _Reversed(b"abc")
    assert vals[2] < _Reversed(b"ab")
    assert vals[3] == "x,y"


def test_sorting_value_status_default_for_component_types() -> None:
    """If STATUS is not set, defaults should be used based on component type."""
    cases = [
        (Event, "TENTATIVE"),  # VEVENT default status
        (Todo, "NEEDS-ACTION"),  # VTODO default status
    ]

    for cls, expected in cases:
        cal = Calendar()
        comp = cls()
        cal.add_component(comp)

        s = Searcher()
        s.add_sort_key("status", reversed=False)

        vals = s.sorting_value(cal)
        assert vals == [expected.encode()]


def test_special_sort_keys_isnt_overdue_and_hasnt_started(monkeypatch: Callable) -> None:
    """Test the special keys 'isnt_overdue' and 'hasnt_started' by fixing 'now'."""
    # Create a TODO with due in the past and dtstart in the future relative to fake now.
    cal = Calendar()
    todo = Todo()
    todo.add("due", real_datetime(2025, 1, 1, 12, 0))  # yesterday
    todo.add("dtstart", real_datetime(2025, 1, 3, 12, 0))  # tomorrow
    cal.add_component(todo)

    s = Searcher()
    s.add_sort_key("isnt_overdue", reversed=False)
    s.add_sort_key("hasnt_started", reversed=False)

    # Freeze "now" to 2025-01-02 12:00:00
    class FakeDatetime:
        @classmethod
        def now(cls) -> real_datetime:
            return real_datetime(2025, 1, 2, 12, 0)

    # Patch the datetime used inside the icalendar_searcher.searcher module
    monkeypatch.setattr(icalendar_searcher.searcher, "datetime", FakeDatetime)

    vals = s.sorting_value(cal)
    # due < now -> isnt_overdue should be False
    # dtstart > now -> hasnt_started should be True
    assert vals == [False, True]
