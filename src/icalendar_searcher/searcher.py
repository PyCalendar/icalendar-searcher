"""Main Searcher class for icalendar component filtering and sorting."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

import recurring_ical_events
from icalendar import Calendar, Component, Timezone, error
from recurring_ical_events import DATE_MAX_DT, DATE_MIN_DT

from . import comma_list
from .collation import Collation, get_sort_key_function
from .filters import FilterMixin
from .utils import (
    DT_MAX,
    DT_MIN,
    PRESENCE_OPERATORS,
    SUPPORTED_OPERATORS,
    _iterable_or_false,
    _normalize_dt,
    _shift,
    types_factory,
)

## recurring_ical_events widens the expansion window by the duration of an
## occurrence (and by how far a modification moved), which overflows near the
## ends of the datetime range.  Only search bounds this close to an end get
## the window narrowed; ordinary searches are expanded as given.
_EDGE_ZONE = timedelta(days=2 * 366)
## The margin when a component is too odd to compute one from
_FALLBACK_MARGIN = timedelta(days=366)


def _as_kind_of(value: date | datetime, limit: datetime) -> date | datetime:
    """The aware ``limit`` as the same kind as ``value``: aware, naive or date."""
    if isinstance(value, datetime):
        return limit if value.tzinfo else limit.replace(tzinfo=None)
    return limit.date()


def _near_edge(value: date | datetime) -> bool:
    return value < _as_kind_of(value, _shift(DT_MIN, _EDGE_ZONE)) or value > _as_kind_of(
        value, _shift(DT_MAX, -_EDGE_ZONE)
    )


def _expansion_margin(components: list[Component]) -> timedelta:
    """How far inside the ends of the datetime range to keep the window.

    That is as far as recurring_ical_events may widen it, plus a day, since
    naive and date bounds are read in the event's time zone.
    """
    margin = timedelta(0)
    try:
        for component in components:
            start, end = _normalize_dt(component.start), _normalize_dt(component.end)
            margin = max(margin, end - start)
            recurrence_id = component.get("RECURRENCE-ID")
            if recurrence_id is not None and recurrence_id.params.get("RANGE") == "THISANDFUTURE":
                margin = max(margin, end - start + abs(start - _normalize_dt(recurrence_id.dt)))
    except (error.IncompleteComponent, OverflowError, TypeError, ValueError):
        return _FALLBACK_MARGIN
    return margin + timedelta(days=1)


if TYPE_CHECKING:
    from caldav.calendarobjectresource import CalendarObjectResource


@dataclass
class Searcher(FilterMixin):
    """This class will:

    * Allow to build up a calendar search query.
    * Help filterering or sorting a list of calendar components

    Primarily VJOURNAL, VTODO and VEVENT Calendar components are
    intended to be supported, but we should consider if there is any
    point supporting FREEBUSY as well.

    This class is a bit stubbed as of 2025-11, many things not working
    yet.  This class was split out from the CalDAV library and is
    intended for generic search logic not related to the CalDAV
    protocol.  As of 2025-11, the first priority is to make the bare
    minimum of support needed for supporting refactorings of the
    CalDAV library.

    Long-term plan is to also allow for adding subqueries that can be
    bound together with logical AND or OR.  (Will AND every be needed?
    After all, add different criterias to one Searcher object, and all
    of them has to match)

    Properties (like SUMMARY, CATEGORIES, etc) are not meant to be
    sent through the constructor, use the :func:`icalendar_searcher.Searcher.add_property_filter`
    method.  Same goes with sort keys, they can be added through the
    `func:icalendar_searcher.Searcher.add_sort_key` method.

    The ``todo``, ``event`` and ``journal`` parameters are booleans
    for filtering the component type.  If i.e. both todo and
    journal is set to True, everything but events should be returned.
    If none is given (the default), all objects should be returned.

    If ``todo`` is given ``include_completed`` defaults to False,
    which means completed tasks will be tfiltered out.

    ``start`` and ``end`` is giving a time range.  RFC4791, section
    9.9 gives a very clear and sane definitions of what should be
    returned when searching a CalDAV calendar for contents over a time
    span.  While this package is not related to CalDAV pper se, the
    logic seems sane, so we will stick to that one.  Timestamps should
    ideally be with a time zone, if not given the local time zone will
    be assumed.  All-day events may be tricky to get correct when
    timestamps are given and calendar data covers multiple time zones.

    ``alarm_start`` and ``alarm_end`` is similar for alarm searching

    If ``expand`` is set to True, recurring objects will be expanded
    into reccurence objects for the time period specified by ``start``
    and ``end``.  Generators are used, so ``expand`` may even work
    without ``start`` and ``end`` set if care is taken
    (i.e. converting the generator to a list may cause problems)

    Unless you now what you are doing, ``expand`` should probably be
    set to true, and start and end should be given and shouldn't be
    too far away from each other.  Currently the sorting algorithm
    will blow up if the expand yields infinite number of events.  It
    may probably blow up even if expand yields millions of events.  Be
    careful.

    For filtering an icalendar instance ``mycal`` containing a
    VCALENDAR with multiple independent events, one may do
    ``searcher.filter([mycal])``.  The CalDAV library contains a
    CalDAVSearcher class inheritating this class and including a
    ``.search(caldav_calendar)`` method.  The idea is that it may be
    done in the same way also for searching other calendars or
    calendar-like systems using other protocols.

    The filtering and sorting methods should accept both wrapper
    objects (for the CalDAV library, those are called
    CalendarObjectResource and contains extra information like the URL
    and the client object) and ``icalendar.Calendar`` objects from the
    icalendar library.  Wrapper objects should have the
    ``icalendar.Calendar`` object available through a property
    ``icalendar_instance``.  Even for methods expecting a simple
    component, a ``Calendar`` should be given.  This is of
    imporantance for recurrences with exceptions (like, "daily meeting
    is held at 10:00, except today the meeting is postponed until
    12:00" may be represented through a calendar with two
    subcomponents)

    Methods expecting multiple components will always expect a list of
    calendars (CalDAV-style) - but the algorithms should also be
    robust enough to handle multiple independent components embedded
    in a single Calendar.

    Other ideas that one may consider implementing:
    * limit, offset.
    * fuzzy matching

    """

    todo: bool = None
    event: bool = None
    journal: bool = None
    start: datetime = None
    end: datetime = None
    alarm_start: datetime = None
    alarm_end: datetime = None
    include_completed: bool = None

    expand: bool = False

    _sort_keys: list = field(default_factory=list)
    _sort_collation: dict = field(default_factory=dict)
    _sort_locale: dict = field(default_factory=dict)
    _sort_case_sensitive: dict = field(default_factory=dict)
    _sort_accent_sensitive: dict = field(default_factory=dict)
    _property_filters: dict = field(default_factory=dict)
    _property_operator: dict = field(default_factory=dict)
    _property_collation: dict = field(default_factory=dict)
    _property_locale: dict = field(default_factory=dict)
    _property_case_sensitive: dict = field(default_factory=dict)
    _property_accent_sensitive: dict = field(default_factory=dict)

    def add_property_filter(
        self,
        key: str,
        value: Any,
        operator: str = "contains",
        case_sensitive: bool = True,
        collation: Collation | None = None,
        locale: str | None = None,
        accent_sensitive: bool = True,
    ) -> None:
        """Adds a filter for some specific iCalendar property.

        Examples of valid iCalendar properties: SUMMARY,
        LOCATION, DESCRIPTION, DTSTART, STATUS, CLASS, etc

        :param key: must be an icalendar property, i.e. SUMMARY
                   Special virtual property "category" (singular) is also supported
                   for substring matching within category names
        :param value: should adhere to the type defined in the RFC
        :param operator: Comparision operator ("contains", "==", etc)
        :param case_sensitive: If False, text comparisons are case-insensitive.
        :param collation: Advanced collation strategy for text comparison.
                         Only needed by power users for Unicode or
                         locale-aware collation.
        :param locale: Locale string (e.g., "de_DE") for locale-aware collation.
                      Only used with collation=Collation.LOCALE.
        :param accent_sensitive: If False, text comparisons ignore accents,
                      so "muller" matches "Müller".  What counts as an
                      accent depends on the collation and locale, see
                      the collation module.

        The case_sensitive and accent_sensitive parameters only apply
        to text properties, and to all the text operators alike.
        The default has been made for case sensitive searches.  This
        is contrary to the CalDAV standard, where case insensitive
        searches are considered the default, but it's in accordance
        with the CalDAV library, where case sensitive searches has
        been the default.

        **Special handling for categories:**

        - **"categories"** (plural): Exact category name matching
          - "contains": subset check (all filter categories must be in component)
          - "==": exact set equality (same categories, order doesn't matter)
          - Commas in filter values split into multiple categories

        - **"category"** (singular): Substring matching within category names
          - "contains": substring match (e.g., "out" matches "outdoor")
          - "==": exact match to at least one category name
          - Commas in filter values treated as literal characters

        The following operators are supported:

        * contains - will do a substring match (A search for "summary"
          "contains" "rain" will return both events with summary
          "Training session" and "Singing in the rain")

        * == - exact match is required

        * !contains - the negation of contains: no substring match.
          Like contains, it requires the property to be defined.  For
          ordinary properties this is what a negated text-match means in
          RFC 4791 section 9.7.5.  For "categories" it negates the exact
          token match (not a substring match), so it has no server-side
          equivalent.

        * != or <> - the negation of ==.  Both spellings are accepted;
          the filter is stored as !=.  Like == and contains, it requires
          the property to be defined, so a component without the
          property does not match.  Use undef to find those.

        * def, undef - will match if the property is (not) defined.
          The value is ignored and may be set to None.

        Not implemented yet (raise NotImplementedError): ~ (regexp
        match) and the comparisons <, <=, >, >=.

        Examples:
            # Case-insensitive search (simple API)
            searcher.add_property_filter("SUMMARY", "meeting", case_sensitive=False)

            # Case-sensitive search (default)
            searcher.add_property_filter("SUMMARY", "Meeting")

            # Advanced: locale-aware collation (requires PyICU)
            searcher.add_property_filter("SUMMARY", "Müller",
                                        collation=Collation.LOCALE,
                                        locale="de_DE")

        """
        ## Comma-token-list properties ("category"/"categories"; see
        ## comma_list.py) carry their own plural-vs-singular semantics: the
        ## plural form splits on commas and matches exactly, the singular form
        ## keeps commas literal and matches substrings.
        key = key.lower()
        if operator == "<>":
            operator = "!="
        if operator not in SUPPORTED_OPERATORS:
            raise NotImplementedError(f"The operator {operator} is not supported yet.")
        if operator not in PRESENCE_OPERATORS:
            if value is None:
                raise ValueError(f"The operator {operator} needs a value, got None")
            if comma_list.is_comma_list_key(key):
                self._property_filters[key] = comma_list.store_filter_value(key, value)
            else:
                self._property_filters[key] = types_factory.for_property(key)(value)
        self._property_operator[key] = operator

        # Determine collation strategy
        if collation is not None:
            # Power user specified explicit collation
            self._property_collation[key] = collation
            self._property_locale[key] = locale
        else:
            # Simple API: use SIMPLE collation
            self._property_collation[key] = Collation.SIMPLE
            self._property_locale[key] = None
        self._property_case_sensitive[key] = case_sensitive
        self._property_accent_sensitive[key] = accent_sensitive

    def add_sort_key(
        self,
        key: str,
        reversed: bool = None,
        case_sensitive: bool = True,
        collation: Collation | None = None,
        locale: str | None = None,
        accent_sensitive: bool = True,
    ) -> None:
        """Add a sort key for sorting components.

        Special keys "isnt_overdue" and "hasnt_started" is
        supported, those will compare the DUE (for a task) or the
        DTSTART with the current wall clock and return a bool.

        Except for that, the sort key should be an icalendar property.

        :param key: The property name to sort by
        :param reversed: If True, sort in reverse order
        :param case_sensitive: If False, text sorting is case-insensitive.
                              Only applies to text properties. Default is True.
        :param collation: Advanced collation strategy for text sorting.
        :param locale: Locale string (e.g., "de_DE") for locale-aware sorting.
                      Only used with collation=Collation.LOCALE.
        :param accent_sensitive: If False, text sorting ignores accents.

        Examples:
            # Case-insensitive sorting (simple API)
            searcher.add_sort_key("SUMMARY", case_sensitive=False)

            # Case-sensitive sorting (default)
            searcher.add_sort_key("SUMMARY")

            # Advanced: locale-aware sorting (requires PyICU)
            searcher.add_sort_key("SUMMARY", collation=Collation.LOCALE, locale="de_DE")
        """
        key = key.lower()
        assert key in types_factory.types_map or key in (
            "isnt_overdue",
            "hasnt_started",
        )
        self._sort_keys.append((key, reversed))

        # Determine collation strategy for sorting
        if collation is not None:
            # Power user specified explicit collation
            self._sort_collation[key] = collation
            self._sort_locale[key] = locale
        else:
            # Simple API
            self._sort_collation[key] = Collation.SIMPLE
            self._sort_locale[key] = None
        self._sort_case_sensitive[key] = case_sensitive
        self._sort_accent_sensitive[key] = accent_sensitive

    def check_component(
        self,
        component: Calendar | Component | CalendarObjectResource,
        expand_only: bool = False,
        _ignore_rrule_and_time: bool = False,
    ) -> Iterable[Component]:
        """Checks if one component (or recurrence set) matches the
        filters.  If the component parameter is a calendar containing
        several independent components, an Exception may be raised,
        though recurrence sets should be suppored.

        * If there is no match, ``None`` or ``False`` will be returned
          (the exact return value is currently not clearly defined,
          but ``bool(return_value)`` should yield False).

        * If a time specification is given and the component given is
          a recurring component, it will be expanded internally to
          check if it matches the given time specification.

        * If there is a match, the component should be returned
          (wrapped in a tuple) - unless ``expand`` is set, in which
          case all matching recurrences will be returned (as a
          generator object).

        :param component: Todo, Event, Calendar or such
        :param expand_only: Don't do any filtering, just expand

        """
        ## For consistant and predictable return value, we need to
        ## transform the component in the very start.  We need to make
        ## it into a list so we can iterate on it without throwing
        ## away data.  TODO: This will break badly if the
        ## component already is a generator with infinite amount of
        ## recurrences.  It should be possible to fix this in a smart
        ## way.  I.e., make a new wrappable class ListLikeGenerator
        ## that stores the elements we've taken out from the
        ## generator.  Such a class would also eliminate the need of
        ## _generator_or_false.
        orig_recurrence_set = self._validate_and_normalize_component(component)

        ## Early return if no work needed
        if expand_only and not self.expand:
            return orig_recurrence_set

        ## Ensure timezone is set.  Ensure start and end are datetime objects.
        ## Compute normalised copies locally — do NOT mutate self, as check_component()
        ## must be idempotent and safe to call multiple times on the same Searcher.
        def _normalise_dt_local(value: datetime | None) -> datetime | None:
            if not value:
                return value
            if not isinstance(value, datetime):
                logging.warning(
                    "Date-range searches not well supported yet; use datetime rather than dates"
                )
            return _normalize_dt(value)

        _start = _normalise_dt_local(self.start)
        _end = _normalise_dt_local(self.end)
        _alarm_start = _normalise_dt_local(self.alarm_start)
        _alarm_end = _normalise_dt_local(self.alarm_end)

        ## Dates and floating datetimes in the component are interpreted in the
        ## time zone of the search range when it is timezone-aware, otherwise in
        ## the time zone of the Python process.  If start and end are in
        ## different time zones, the time zone of start is used.
        def _tz_of(*values: datetime | None) -> tzinfo | None:
            for value in values:
                if isinstance(value, datetime) and value.tzinfo is not None:
                    return value.tzinfo
            return None

        _tz = _tz_of(self.start, self.end)
        _alarm_tz = _tz_of(self.alarm_start, self.alarm_end) or _tz

        ## recurrence_set is our internal generator/iterator containing
        ## everything that hasn't been filtered out yet (in most
        ## cases, the generator will yield either one or zero
        ## components - but recurrences are tricky).  orig_recurrence_set
        ## is a list, so iterations on recurrence_set will not affect
        ## orig_recurrence_set
        recurrence_set = orig_recurrence_set

        ## Recurrences may be a night-mare.
        ## I'm not sure if this is very well thought through, but my thoughts now are:

        ## 1) we need to check if the not-expanded base element
        ## matches any non-date-related search-filters before doing
        ## anything else.  We do this with a recursive call with an
        ## internal parameter _ignore_rrule_and_time set.

        ## 2) If the base element does not match, we may probably skip
        ## expansion (only problem I can see with it is some filtering
        ## like "show me all events happening on a Monday" - which is
        ## anyway not supported as for now).  It's important to skip
        ## expansion, otherwise we may end up doing an infinite (or
        ## very-huge) expansion just to verify that we can return
        ## None/False

        ## 3) if the base element does not match, there may still be
        ## special cases matching.  We solve this by running the
        ## filter logics on all but the

        ## 4) if the base element matches, we may need to expand it

        ## When the base element passes property filters (including undef checks),
        ## expanded occurrences should skip undef checks.  Libraries like
        ## recurring_ical_events add computed properties (e.g. DTEND for
        ## all-day events) to individual occurrences even when the master
        ## event does not have them explicitly set, causing false negatives.
        skip_undef_for_expanded = False

        first = orig_recurrence_set[0]
        if not expand_only and "RRULE" in first and not _ignore_rrule_and_time:
            ## TODO: implement logic above
            base_element_match = self.check_component(first, _ignore_rrule_and_time=True)
            if not base_element_match:
                ## Base element is to be ignored.  recurrence_set is still a list
                recurrence_set = recurrence_set[1:]  # Remove first element (base), keep exceptions
            else:
                ## Base element passed all filters (including undef checks).  Flag
                ## that expanded occurrences should skip undef checks to avoid
                ## filtering out occurrences with properties added by expansion.
                skip_undef_for_expanded = True

        ## include_completed should default to False if todo is explicitly set, otherwise True.
        ## Compute locally — do NOT mutate self.include_completed so the Searcher stays reusable.
        _include_completed = self.include_completed
        if _include_completed is None:
            _include_completed = not self.todo

        ## Component type flags are a bit difficult.  In the CalDAV library,
        ## if all of them are None, everything should be returned.  If only
        ## one of them is True, then only this kind of component type is
        ## returned.  In any other case, no guarantees of correctness are given.

        ## Let's skip the last remark and try to make a generic and
        ## correct solution from the start: 1) if any flags are True,
        ## then consider flags set as None as False.  2) if any flags
        ## are still None, then consider those to be True.  3) List
        ## the flags that are True as acceptable component types.
        ## Computed locally — do NOT mutate self.todo / self.event / self.journal.

        comptypesl = ("todo", "event", "journal")
        if any(getattr(self, x) for x in comptypesl):
            ## At least one type is explicitly True: treat remaining Nones as False (opt-in mode)
            _compflags = {x: bool(getattr(self, x)) for x in comptypesl}
        else:
            ## No type is explicitly True: treat Nones as True, but respect explicit Falses (opt-out mode)
            _compflags = {x: getattr(self, x) is not False for x in comptypesl}

        comptypesu = set([f"V{x.upper()}" for x in comptypesl if _compflags[x]])

        ## if expand_only, expand all comptypes, otherwise only the comptypes specified in the filters
        comptypes_for_expansion = ["VTODO", "VEVENT", "VJOURNAL"] if expand_only else comptypesu

        if not _ignore_rrule_and_time and "RRULE" in first:
            recurrence_set = self._expand_recurrences(recurrence_set, comptypes_for_expansion)

        if not expand_only:
            ## OPTIMIZATION TODO: If the object was recurring, we should
            ## probably trust recur.between to do the right thing?
            if not _ignore_rrule_and_time and (_start or _end):
                recurrence_set = (
                    x
                    for x in recurrence_set
                    if self._check_range(x, _start=_start, _end=_end, _tz=_tz)
                )

            ## This if is just to save some few CPU cycles - skip filtering if it's not needed
            if not all(_compflags[x] for x in comptypesl):
                recurrence_set = (x for x in recurrence_set if x.name in comptypesu)

            ## Filter based on include_completed setting
            recurrence_set = (
                x
                for x in recurrence_set
                if self._check_completed_filter(x, _include_completed=_include_completed)
            )

            ## Apply property filters
            if self._property_filters or self._property_operator:
                recurrence_set = (
                    x
                    for x in recurrence_set
                    if self._check_property_filters(x, skip_undef=skip_undef_for_expanded)
                )

            ## Apply alarm filters
            if not _ignore_rrule_and_time and (_alarm_start or _alarm_end):
                recurrence_set = (
                    x
                    for x in recurrence_set
                    if self._check_alarm_range(
                        x, _alarm_start=_alarm_start, _alarm_end=_alarm_end, _tz=_alarm_tz
                    )
                )

        if self.expand:
            ## TODO: fix wrapping, if needed
            return _iterable_or_false(recurrence_set)
        else:
            if next(recurrence_set, None):
                return orig_recurrence_set
            else:
                return None

    def filter(
        self, components: list[Calendar | Component], split_expanded: bool = False
    ) -> list[Calendar | Component]:
        """Filter components according to the search criteria, optionally expanding recurrences.

        This method does not modify the input list. It returns a new list with
        filtered components.

        :param components: List of Calendar or Component objects to filter
        :param split_expanded: If True and recurrences are expanded, return each
            recurrence as a separate Calendar object. If False, all matching
            recurrences from a single input will be returned in one Calendar.
        :return: New list containing only components that match the filter criteria

        Examples:
            searcher = Searcher(event=True, start=datetime(2025, 1, 1))
            searcher.add_property_filter("SUMMARY", "meeting", operator="contains")
            filtered = searcher.filter(calendars)  # Returns matching calendars

            # With split_expanded=True, each recurrence becomes a separate Calendar
            searcher.expand = True
            split_results = searcher.filter(calendars, split_expanded=True)
        """
        results: list[Calendar | Component] = []

        for component in components:
            # check_component returns an iterable of matching components (possibly expanded)
            matched = self.check_component(component)

            # Convert to list to check if we got any results
            if matched:
                matched_list = list(matched)
                if not matched_list:
                    continue

                if split_expanded and len(matched_list) > 1:
                    # Split expanded recurrences into separate Calendar objects
                    # Each recurrence becomes its own Calendar
                    for comp in matched_list:
                        if isinstance(comp, Timezone):
                            continue

                        # Create new Calendar for this recurrence
                        new_cal = Calendar()

                        # If original was a Calendar, copy its properties
                        if isinstance(component, Calendar):
                            for key, value in component.items():
                                new_cal[key] = value

                            # Preserve timezone components
                            timezones = [
                                tz for tz in component.subcomponents if isinstance(tz, Timezone)
                            ]
                            for tz in timezones:
                                from copy import deepcopy

                                new_cal.add_component(deepcopy(tz))

                        # Add the matched component
                        from copy import deepcopy

                        new_cal.add_component(deepcopy(comp))
                        results.append(new_cal)
                else:
                    # Return as-is, or create a Calendar with all matched components
                    if isinstance(component, Calendar):
                        # Create new Calendar with matched components
                        new_cal = Calendar()
                        for key, value in component.items():
                            new_cal[key] = value

                        # Preserve timezone components
                        timezones = [
                            tz for tz in component.subcomponents if isinstance(tz, Timezone)
                        ]
                        for tz in timezones:
                            from copy import deepcopy

                            new_cal.add_component(deepcopy(tz))

                        # Add all matched components
                        for comp in matched_list:
                            if not isinstance(comp, Timezone):
                                from copy import deepcopy

                                new_cal.add_component(deepcopy(comp))

                        results.append(new_cal)
                    else:
                        # Component was passed directly, return matched components
                        for comp in matched_list:
                            from copy import deepcopy

                            results.append(deepcopy(comp))

        return results

    def filter_calendar(self, calendar: Calendar) -> Calendar:
        """Filter subcomponents within a Calendar object according to search criteria.

        This method does not modify the input Calendar. It returns a new Calendar
        containing only the subcomponents that match the filter criteria.

        :param calendar: Calendar object containing multiple subcomponents to filter
        :return: New Calendar object with only matching subcomponents, or None if no matches

        Examples:
            searcher = Searcher(event=True, start=datetime(2025, 1, 1))
            searcher.add_property_filter("SUMMARY", "meeting", operator="contains")
            filtered_cal = searcher.filter_calendar(calendar)  # Returns Calendar with matching events
        """
        from copy import deepcopy

        # Separate timezone components from other components
        timezones = [comp for comp in calendar.subcomponents if isinstance(comp, Timezone)]
        other_components = [
            comp for comp in calendar.subcomponents if not isinstance(comp, Timezone)
        ]

        # Filter each component
        matching_components = []
        for comp in other_components:
            matched = self.check_component(comp)
            if matched:
                matched_list = list(matched)
                if matched_list:
                    # Add all matching occurrences (expanded or not)
                    matching_components.extend(matched_list)

        # If no matches, return None or empty calendar
        if not matching_components:
            return None

        # Create new calendar with matching components
        new_calendar = Calendar()

        # Copy calendar-level properties
        for key, value in calendar.items():
            new_calendar[key] = value

        # Add timezone components first
        for tz in timezones:
            new_calendar.add_component(deepcopy(tz))

        # Add matching components
        for comp in matching_components:
            if not isinstance(comp, Timezone):
                new_calendar.add_component(deepcopy(comp))

        return new_calendar

    def sort(
        self, components: list[Component | CalendarObjectResource]
    ) -> list[Component | CalendarObjectResource]:
        """Sort calendar objects according to configured sort keys.

        This method does not modify the input list. It returns a new sorted list.

        (the idea with this is that the input may be a generator)

        :param components: List of Calendar or CalendarObjectResource objects to sort
        :return: New sorted list

        Examples:
            searcher = Searcher()
            searcher.add_sort_key("DTSTART")
            sorted_events = searcher.sort(events)  # Returns new sorted list
        """
        if self._sort_keys:
            return sorted(components, key=self.sorting_value)
        else:
            return components.copy()

    def sort_calendar(self, calendar: Calendar) -> Calendar:
        """Sort subcomponents within a Calendar object according to configured sort keys.

        This method does not modify the input Calendar. It returns a new Calendar
        with sorted subcomponents (excluding VTIMEZONE components).

        :param calendar: Calendar object containing multiple subcomponents to sort
        :return: New Calendar object with sorted subcomponents

        Examples:
            searcher = Searcher()
            searcher.add_sort_key("DTSTART")
            sorted_cal = searcher.sort_calendar(calendar)  # Returns new Calendar with sorted events
        """
        if not self._sort_keys:
            # No sorting needed, return a copy
            from copy import deepcopy

            return deepcopy(calendar)

        # Separate timezone components from other components
        from icalendar import Timezone

        timezones = [comp for comp in calendar.subcomponents if isinstance(comp, Timezone)]
        other_components = [
            comp for comp in calendar.subcomponents if not isinstance(comp, Timezone)
        ]

        # Sort the non-timezone components
        sorted_components = sorted(other_components, key=self.sorting_value)

        # Create new calendar with sorted components
        from copy import deepcopy

        new_calendar = Calendar()

        # Copy calendar-level properties
        for key, value in calendar.items():
            new_calendar[key] = value

        # Add timezone components first
        for tz in timezones:
            new_calendar.add_component(deepcopy(tz))

        # Add sorted components
        for comp in sorted_components:
            new_calendar.add_component(deepcopy(comp))

        return new_calendar

    def sorting_value(self, component: Component | CalendarObjectResource) -> tuple:
        """Returns a sortable value from the component, based on the sort keys

        The component may be an icalendar.Calendar, an
        icalendar.Component (i.e. icalendar.Event) or an
        caldav.CalendarObjectResource (i.e. caldav.Event).
        """
        ret = []
        ## TODO: this logic has been moved more or less as-is from the
        ## caldav library.  It may need some rethinking and QA work.

        ## TODO: we disregard any complexity wrg of recurring events
        component = self._unwrap(component)
        if isinstance(component, Calendar):
            not_tz_components = (x for x in component.subcomponents if not isinstance(x, Timezone))
            comp = next(not_tz_components)
        else:
            comp = component

        defaults = {
            ## TODO: all possible non-string sort attributes needs to be listed here, otherwise we will get type errors when comparing objects with the property defined vs undefined (or maybe we should make an "undefined" object that always will compare below any other type?  Perhaps there exists such an object already?)
            "due": "2050-01-01",
            "dtstart": "1970-01-01",
            "priority": 0,
            "status": {
                "VTODO": "NEEDS-ACTION",
                "VJOURNAL": "FINAL",
                "VEVENT": "TENTATIVE",
            }[comp.name],
            "category": "",
            ## Usage of strftime is a simple way to ensure there won't be
            ## problems if comparing dates with timestamps
            "isnt_overdue": not (
                "due" in comp
                and comp["due"].dt.strftime("%F%H%M%S") < datetime.now().strftime("%F%H%M%S")
            ),
            "hasnt_started": (
                "dtstart" in comp
                and comp["dtstart"].dt.strftime("%F%H%M%S") > datetime.now().strftime("%F%H%M%S")
            ),
        }
        for sort_key, reverse in self._sort_keys:
            if comma_list.is_plural_sort_key(sort_key):
                val = comma_list.sort_value(sort_key, comp)
            else:
                val = comp.get(sort_key, None)
            if val is None:
                ret.append(defaults.get(sort_key, ""))
                continue

            # Track if this is a text property (for collation)
            # Apply collation BEFORE datetime/category conversion
            is_text_property = isinstance(val, str) and sort_key in self._sort_collation

            if hasattr(val, "dt"):
                val = val.dt
            if hasattr(val, "strftime"):
                val = val.strftime("%F%H%M%S")

            ## TODO: I don't have time to fix test code for this at
            ## the moment (but the bug in v1.0.0 was caught by cyrus
            ## test code in caldav library, cyrus splits the
            ## categories field, and this is allowed according to RFC
            ## 7986, section 5.6) TODO: we should fix tests not only
            ## for sorting lists and categories, but also filtering on
            ## lists and multi-line categories.
            if isinstance(val, list):
                ## sorting lists may be difficult.  As I understand
                ## the standard, the order of the list is not
                ## significant - the order of the elements may be
                ## reshuffled, and the icalendar component will
                ## semantically be equivalent.  To get deterministic
                ## sorting of semantically equivalent components, I've
                ## decided to sort the list (TODO: collation support?)
                val = sorted(val)

                ## TODO: what if the list contains numbers?
                val = ",".join([str(x) for x in val])

            # Apply collation only to text properties (not datetime strings)
            if is_text_property and isinstance(val, str):
                collation = self._sort_collation[sort_key]
                locale = self._sort_locale.get(sort_key)
                case_sensitive = self._sort_case_sensitive.get(sort_key, True)
                accent_sensitive = self._sort_accent_sensitive.get(sort_key, True)
                sort_key_fn = get_sort_key_function(
                    collation, case_sensitive, locale, accent_sensitive
                )
                val = sort_key_fn(val)

            if reverse:
                if isinstance(val, (str, bytes)):
                    if isinstance(val, str):
                        val = val.encode()
                    val = bytes(b ^ 0xFF for b in val)
                else:
                    val = -val
            ret.append(val)

        return ret

    def _unwrap(self, component: Calendar | CalendarObjectResource) -> Calendar:
        """
        To support the caldav library (and possibly other libraries where the
        icalendar component is wrapped)
        """
        try:
            component = component.icalendar_instance
        except AttributeError:
            pass
        if isinstance(component, Component) and not isinstance(component, Calendar):
            cal = Calendar()
            cal.add_component(component)
            component = cal
        return component

    def _validate_and_normalize_component(
        self, component: Calendar | Component | CalendarObjectResource
    ) -> list[Component]:
        """This method serves two purposes:

        1) Be liberal in what "component" it accepts and return
        something well-defined.  For instance, coponent may be a
        wrapped object (caldav.Event), an icalendar.Calendar or an
        icalendar.Event.  The return value will always be a list of
        icalendar components (i.e. Event), and Timezone components will
        be removed.

        2) Do some verification that the "component" is as expected
        and raise a ValueError if not.  The "component" should either
        be one single component or a recurrence set.  A recurrence set
        should conform to those rules:

        2.1) All components in the recurrence set should have the same UID

        2.2) Exactly one element ("master") of the recurrence set may
        have the RRULE property set.  RFC 5545 does not mandate any
        particular ordering inside a VCALENDAR, so the master may
        appear in any position; this method will move it to the head
        of the returned list so downstream expansion code can rely on
        ``components[0]`` being the master.

        2.3) Any non-master elements of a recurrence set ("exception
        recurrences") should have the RECURRENCE-ID property set and
        must not have RRULE.

        2.4) (there are more properties that may only be set in the
        master or only in the recurrences, but currently we don't do
        more checking than this)

        As for now, we do not support component to be a generator or a
        list, and things will blow up if component.subcomponents is a
        generator yielding infinite or too many subcomponents.

        """

        component = self._unwrap(component)
        components = [x for x in component.subcomponents if not isinstance(x, Timezone)]

        ## We shouldn't get here.  There should always be a valid component.
        if not len(components):
            raise ValueError("Empty component?")

        ## A recurrence set should be exactly one "master" (with RRULE) plus zero
        ## or more "exception recurrences" (with RECURRENCE-ID and without RRULE),
        ## OR zero masters plus one-or-more standalone occurrences (all with
        ## RECURRENCE-ID).  RFC 5545 does not mandate an ordering inside the
        ## VCALENDAR, so we accept the master in any position and reorder it to
        ## the head.  Some servers (notably calendar.mail.ru) emit overrides
        ## before the master.
        if len(components) > 1:
            masters = [c for c in components if "rrule" in c and "recurrence-id" not in c]
            non_masters = [c for c in components if c not in masters]
            if len(masters) > 1 or any("rrule" in c for c in non_masters):
                raise ValueError(
                    "Expected a valid recurrence set, either with one master component followed with special recurrences or with only occurrences"
                )
            if not all("recurrence-id" in c for c in non_masters):
                raise ValueError(
                    "Expected a valid recurrence set, either with one master component followed with special recurrences or with only occurrences"
                )
            if masters:
                components = masters + non_masters

        ## components should typically be a list with only one component.
        ## if there are more components, it should be a recurrence set
        ## one of the things identifying a recurrence set is that the
        ## uid is the same for all components in the set
        first = components[0]
        if any(x for x in components if x["uid"] != first["uid"]):
            raise ValueError(
                "Input parameter component is supposed to contain a single component or a recurrence set - but multiple UIDs found"
            )
        return components

    def _expand_recurrences(
        self, recurrence_set: list[Component], comptypesu: set[str]
    ) -> Iterable[Component]:
        """Expand recurring events within the searcher's time range.

        Ensures expanded occurrences comply with RFC 5545:
        - Each occurrence has RECURRENCE-ID set
        - Each occurrence does NOT have RRULE (RRULE and RECURRENCE-ID are mutually exclusive)

        :param recurrence_set: List of calendar components to expand
        :param comptypesu: Set of component type strings (e.g., {"VEVENT", "VTODO"})
        :return: Iterable of expanded component instances
        """
        cal = Calendar()
        for x in recurrence_set:
            cal.add_component(x)
        recur = recurring_ical_events.of(cal, components=comptypesu)

        # Use local variables for start/end to avoid modifying searcher state
        start = self.start if self.start else _normalize_dt(DATE_MIN_DT)
        end = self.end if self.end else _normalize_dt(DATE_MAX_DT)

        if _near_edge(start) or _near_edge(end):
            ## See _EDGE_ZONE.  Occurrences within the margin of the ends
            ## of the datetime range are left out.
            margin = _expansion_margin(recurrence_set)
            start = max(start, _as_kind_of(start, _shift(DT_MIN, margin)))
            end = min(end, _as_kind_of(end, _shift(DT_MAX, -margin)))
            try:
                if start >= end:
                    return []
            except TypeError:  ## a date and a datetime bound
                pass

        return recur.between(start, end)
