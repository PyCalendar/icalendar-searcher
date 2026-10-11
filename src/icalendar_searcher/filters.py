"""Filtering logic for icalendar components."""

from datetime import datetime, timedelta, tzinfo

from icalendar import Component, error
from icalendar.prop import vText
from recurring_ical_events import DATE_MAX_DT, DATE_MIN_DT

from . import comma_list
from .collation import Collation, get_collation_function
from .utils import _normalize_dt


class FilterMixin:
    """Mixin class providing filtering methods for calendar components.

    This class is meant to be mixed into the Searcher dataclass.
    It expects the following attributes to be available on self:
    - start, end: datetime range filters
    - alarm_start, alarm_end: alarm range filters
    - include_completed: bool for filtering completed todos
    - _property_filters: dict of property filters
    - _property_operator: dict of property operators
    - _property_collation: dict of property collations
    - _property_locale: dict of property locales
    """

    def _check_range(
        self,
        component: Component,
        _start: datetime | None = None,
        _end: datetime | None = None,
        _tz: tzinfo | None = None,
    ) -> bool:
        """Check if a component falls within the time range specified by self.start and self.end.

        Implements RFC4791 section 9.9 time-range filtering logic for VEVENT, VTODO, and VJOURNAL.

        :param component: A single calendar component (VEVENT, VTODO, or VJOURNAL)
        :param _start: Effective start datetime (defaults to self.start).  Pass a pre-normalised
            value from check_component() to avoid mutating self.
        :param _end: Effective end datetime (defaults to self.end).  See _start.
        :param _tz: Time zone for interpreting dates and floating datetimes in the component
            (defaults to the time zone of the Python process).
        :return: True if the component matches the time range, False otherwise
        """
        ## Resolve effective values — callers may pass pre-computed normalised datetimes
        ## so that self is not mutated during filtering.
        start = _start if _start is not None else self.start
        end = _end if _end is not None else self.end
        comp_name = component.name

        ## The logic below should correspond neatly with RFC4791 section 9.9

        ## fetch comp_end and comp_start
        ## note that comp_end is DTSTART + DURATION if DURATION is given.
        ## note that for tasks, comp_end is set to DUE
        ## This logic is all handled by the start/end properties in the
        ## icalendar library, and makes the logic here less complex

        try:
            comp_end = _normalize_dt(component.end, _tz)
        except error.IncompleteComponent:
            comp_end = None

        try:
            comp_start = _normalize_dt(component.start, _tz)
        except error.IncompleteComponent:
            if component.name == "VEVENT":
                ## for events, DTSTART is mandatory
                raise
            comp_start = None

        ## For a VEVENT without DTEND or DURATION, component.end already
        ## gives zero duration for a datetime DTSTART and one day for a
        ## date DTSTART (RFC 5545 section 3.6.1), so comp_end is always set.

        if comp_name == "VTODO":
            ## There is a long matrix for VTODO in the RFC4701,
            ## section 9.9, and it may seem complicated, but it isn't
            ## that bad:

            ## * A task with DTSTART and DURATION is equivalent with a
            ##   task with DTSTART and DUE.  This complexity is
            ##   already handled by the icalendar library, so all rows
            ##   in the matrix where "VTODO has the DURATION property?"
            ##   is "Y" may be removed.
            ##
            ## * The matrix says that if NEITHER DTSTART, DUE nor DURATION
            ##   is given, then CREATED and COMPLETED serve as the time bounds.
            ##   When both are present, treat them as a [CREATED, COMPLETED] range.
            ##   When only COMPLETED is present, treat it as a point event.
            ##   When only CREATED is present, the RFC condition is just (end > CREATED)
            ##   — the task is open-ended from CREATED onward, so comp_end = DATE_MAX_DT.
            if not comp_start and not comp_end:
                if "CREATED" in component:
                    comp_start = _normalize_dt(component["CREATED"].dt, _tz)
                if "COMPLETED" in component:
                    comp_end = _normalize_dt(component["COMPLETED"].dt, _tz)
                if comp_start and not comp_end:
                    comp_end = _normalize_dt(DATE_MAX_DT)

            ## * If only COMPLETED is given (no DTSTART/DUE/CREATED), treat as a point event
            if comp_end and not comp_start:
                comp_start = comp_end
            ## * If only DTSTART is given (no DUE/DURATION), treat as a zero-duration event
            if comp_start and not comp_end:
                comp_end = comp_start

            ## * A task may have the end before the start.  The
            ##   complicated OR-logic in the matrix may be eliminated
            ##   by swapping start/end if necessary:
            if comp_end and comp_start and comp_end < comp_start:
                tmp = comp_start
                comp_start = comp_end
                comp_end = tmp

            ## * A task with no timestamps is considered to be done "at any or all days",
            ##   and should always be found when doing a date search:
            if not comp_end and not comp_start:
                comp_start = _normalize_dt(DATE_MIN_DT)
                comp_end = _normalize_dt(DATE_MAX_DT)

        elif comp_name == "VJOURNAL":
            if not comp_start:
                ## Journal without DTSTART doesn't match time ranges
                return False
            if isinstance(comp_start, datetime):
                comp_end = comp_start
            else:
                comp_end = comp_start + timedelta(days=1)

        if comp_start == comp_end:
            ## Now the match requirement is start <= comp_end
            ## while otherwise the match requirement is start < comp_end
            ## minor detail, we'll work around it:
            comp_end += timedelta(seconds=1)

        ## After the logic above, all rows in the matrix boils down to
        ## this: (we could reduce it even more by defaulting
        ## start and end to DATE_MIN_DT etc)
        if start and end and comp_end:
            return start < comp_end and end > comp_start
        elif end:
            return end > comp_start
        elif start and comp_end:
            return start < comp_end
        return True

    def _check_completed_filter(
        self,
        component: Component,
        _include_completed: bool | None = None,
    ) -> bool:
        """Check if a component should be included based on the include_completed filter.

        :param component: A single calendar component
        :param _include_completed: Effective value (defaults to self.include_completed).  Pass a
            pre-resolved value from check_component() to avoid mutating self.
        :return: True if the component should be included, False if it should be filtered out
        """
        include_completed = (
            _include_completed if _include_completed is not None else self.include_completed
        )
        if include_completed:
            return True

        ## If include_completed is False, exclude completed/cancelled VTODOs
        ## Include everything that is not a VTODO, or VTODOs that are not completed/cancelled
        if component.name != "VTODO":
            return True

        ## For VTODOs, exclude if STATUS is COMPLETED or CANCELLED, or if COMPLETED property is set
        status = component.get("STATUS", "NEEDS-ACTION")
        if status in ("COMPLETED", "CANCELLED"):
            return False
        if "COMPLETED" in component:
            return False

        return True

    ## DISCLAIMER: partly AI-generated code.  Refactored a bit by human hands
    ## Should be refactored more, there is quite some code duplication here.
    ## Code duplication is bad, IMO.
    def _check_property_filters(self, component: Component, skip_undef: bool = False) -> bool:
        """Check if a component matches all property filters.

        :param component: A single calendar component
        :param skip_undef: If True, skip ``undef`` operator checks.  Used when
            filtering expanded recurrence occurrences whose base element has
            already passed the undef check.  Libraries like
            ``recurring_ical_events`` may add computed properties (e.g. DTEND)
            to individual occurrences even when the master event does not have
            them explicitly, which would otherwise cause false negatives.
        :return: True if the component matches all property filters, False otherwise
        """
        for key, operator in self._property_operator.items():
            if not self._check_property_filter(component, key, operator, skip_undef):
                return False
        return True

    def _check_property_filter(
        self, component: Component, key: str, operator: str, skip_undef: bool = False
    ) -> bool:
        """Check if a component matches a single property filter.

        Every ``return`` in here concerns this one filter only;
        :meth:`_check_property_filters` combines the results.
        """
        filter_value = self._property_filters.get(key)

        # Get collation settings for this property
        collation = self._property_collation.get(key, Collation.SIMPLE)
        locale = self._property_locale.get(key)
        case_sensitive = self._property_case_sensitive.get(key, True)

        ## Comma-token-list properties (CATEGORIES; see comma_list.py) carry
        ## their own plural/singular matching semantics.  Delegate the whole
        ## per-key decision so that logic lives in exactly one place.
        if comma_list.is_comma_list_key(key):
            if operator == "undef" and skip_undef:
                ## See the skip_undef note below.
                return True
            matched = comma_list.matches(
                key,
                operator,
                filter_value,
                component,
                collation=collation,
                case_sensitive=case_sensitive,
                locale=locale,
            )
            return matched

        comp_key = key
        comp_value = component.get(comp_key)
        if operator == "undef":
            if skip_undef:
                ## The base (master) element of this recurrence set already
                ## passed the undef check.  Expanded occurrences may have
                ## this property added as a computed value by
                ## recurring_ical_events (e.g. DTEND for all-day events), so
                ## we skip the check here to avoid false negatives.
                return True
            ## Property should NOT be defined
            if comp_key in component:
                return False
        elif operator == "contains":
            ## Property should contain the filter value (substring match)
            if comp_key not in component:
                return False

            ## Convert to string for substring matching
            comp_str = str(comp_value)
            filter_str = str(filter_value)

            # Use collation function for text matching
            collation_fn = get_collation_function(collation, case_sensitive, locale)
            if not collation_fn(filter_str, comp_str):
                return False
        elif operator == "==":
            ## Property should exactly match the filter value
            if comp_key not in component:
                return False

            ## Compare the values This is tricky, as the values
            ## may have different types.  TODO: we should add more
            ## logic for the different property types.  Maybe get
            ## it into the icalendar library.
            if comp_value == filter_value:
                return True
            if isinstance(filter_value, str) and isinstance(comp_value, set):
                return filter_value in comp_value

            # For text properties, use collation for exact match comparison
            if isinstance(filter_value, (str, vText)) and isinstance(comp_value, (str, vText)):
                comp_str = str(comp_value)
                filter_str = str(filter_value)

                # Use collation-specific comparison
                if collation == Collation.SIMPLE:
                    if case_sensitive:
                        return comp_str == filter_str
                    else:
                        return comp_str.lower() == filter_str.lower()
                elif collation in (Collation.UNICODE, Collation.LOCALE):
                    # For UNICODE/LOCALE collations, use sort keys for comparison
                    # Two strings are equal if they have the same sort key
                    from .collation import get_sort_key_function

                    sort_key_fn = get_sort_key_function(collation, case_sensitive, locale)
                    return sort_key_fn(comp_str) == sort_key_fn(filter_str)

            return False
        else:
            ## This shouldn't happen as add_property_filter validates operators
            raise NotImplementedError(f"Operator {operator} not implemented")
        return True

    ## DISCLAIMER: Mostly AI-generated code, with a touch of human polishing
    ## and bugfixing. Alarms are a bit complex.
    def _check_alarm_range(
        self,
        component: Component,
        _alarm_start: datetime | None = None,
        _alarm_end: datetime | None = None,
        _tz: tzinfo | None = None,
    ) -> bool:
        """Check if a component has alarms that fire within the alarm time range.

        Implements RFC 4791 section 9.9 alarm time-range filtering.

        :param component: A single calendar component (VEVENT, VTODO, or VJOURNAL)
        :param _alarm_start: Effective alarm start (defaults to self.alarm_start).  Pass a
            pre-normalised value from check_component() to avoid mutating self.
        :param _alarm_end: Effective alarm end (defaults to self.alarm_end).  See _alarm_start.
        :param _tz: Time zone for interpreting dates and floating datetimes in the component
            (defaults to the time zone of the Python process).
        :return: True if any alarm fires within the alarm range, False otherwise
        """
        from datetime import timedelta

        ## Resolve effective values — callers may pass pre-computed normalised datetimes
        alarm_start = _alarm_start if _alarm_start is not None else self.alarm_start
        alarm_end = _alarm_end if _alarm_end is not None else self.alarm_end

        ## Get all VALARM subcomponents
        alarms = [x for x in component.subcomponents if x.name == "VALARM"]

        if not alarms:
            ## No alarms - doesn't match alarm search
            return False

        ## Get component start/end for relative trigger calculations
        ## Use try/except because .start/.end may raise IncompleteComponent
        ## For VTODO, RFC 5545 says TRIGGER is relative to DUE if present, else DTSTART
        comp_start = None
        comp_end = None
        try:
            comp_start = _normalize_dt(component.start, _tz)
        except error.IncompleteComponent:
            pass
        try:
            comp_end = _normalize_dt(component.end, _tz)
        except error.IncompleteComponent:
            pass

        ## For each alarm, calculate when it fires
        for alarm in alarms:
            if "TRIGGER" not in alarm:
                continue

            trigger = alarm["TRIGGER"]

            ## The icalendar library stores trigger values in .dt attribute
            ## which can be either datetime (absolute) or timedelta (relative)
            if not hasattr(trigger, "dt"):
                continue

            trigger_value = trigger.dt

            ## Check if trigger is absolute (datetime) or relative (timedelta)
            if isinstance(trigger_value, timedelta):
                ## Relative trigger - timedelta from start or end
                trigger_delta = trigger_value

                ## Check TRIGGER's RELATED parameter (default is START)
                ## For VTODO, default anchor is DUE if present, else DTSTART
                related = "START"  # Default per RFC 5545
                if hasattr(trigger, "params") and "RELATED" in trigger.params:
                    related = trigger.params["RELATED"]

                ## Calculate alarm time based on RELATED and component type
                if related == "END" and comp_end:
                    alarm_time = comp_end + trigger_delta
                elif comp_start:
                    alarm_time = comp_start + trigger_delta
                else:
                    ## No start, end, or due to relate to
                    continue
            else:
                ## Absolute trigger - direct datetime
                alarm_time = _normalize_dt(trigger_value, _tz)

            ## Check for REPEAT and DURATION (repeating alarms/snooze functionality)
            ## Check all repetitions, not just the first alarm
            if "REPEAT" in alarm and "DURATION" in alarm:
                repeat_count = alarm["REPEAT"]
                duration = alarm["DURATION"].dt if hasattr(alarm["DURATION"], "dt") else None

                if duration:
                    ## Check each repetition
                    for i in range(int(repeat_count) + 1):
                        repeat_time = alarm_time + (duration * i)
                        ## Check if this repetition fires within the alarm range
                        if alarm_start and alarm_end:
                            if alarm_start <= repeat_time < alarm_end:
                                return True
                        elif alarm_start:
                            if repeat_time >= alarm_start:
                                return True
                        elif alarm_end:
                            if repeat_time < alarm_end:
                                return True
                    ## None of the repetitions matched
                    continue

            ## Check if this alarm (first occurrence) fires within the alarm range
            if alarm_start and alarm_end:
                if alarm_start <= alarm_time < alarm_end:
                    return True
            elif alarm_start:
                if alarm_time >= alarm_start:
                    return True
            elif alarm_end:
                if alarm_time < alarm_end:
                    return True

        return False
