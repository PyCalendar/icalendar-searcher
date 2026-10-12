# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-12

### Added

- **`!=` / `<>`, `!contains` and `def` operators** for `add_property_filter()`.  `!=` is the negation of `==` (`<>` is accepted and stored as `!=`), `!contains` the negation of `contains`.  Like the other value operators, both require the property to be defined - a component without the property does not match; `undef` covers that case.  For `categories` and `category` they negate the plural and singular matching rules respectively.  `def` is the inverse of `undef`.  The `add_property_filter()` docstring no longer lists unimplemented operators as if they worked.  Requested in https://github.com/python-caldav/caldav/issues/568

### Changed

- **License changed from AGPL-3.0-or-later to `GPL-3.0-or-later OR Apache-2.0`**, matching the python caldav library.  caldav has a hard dependency on this package, and an AGPL-only dependency would subject caldav users to AGPL terms, defeating caldav's Apache-2.0 option.  Releases up to 1.0.8 remain available under AGPL-3.0.

- **`add_property_filter()` refuses `None` as the value of a value operator** (`==`, `contains` and the negations) with `ValueError`.  It used to be stored as the text "None".

### Fixed

- **`==` never matched a property occurring more than once** (`COMMENT`, `ATTENDEE`, `CONTACT`, ...): such a component has a list of values, which was compared as a whole.  It now matches if any instance equals the value.

## [1.0.8] - 2026-10-12

### Changed

- **Requires icalendar >= 6.2.0**: with icalendar 6.1.x (the oldest version `recurring-ical-events` allows), importing icalendar-searcher failed with `ImportError`.

### Fixed

- **All-day events were matched in the time zone of the Python process**: dates (`VALUE=DATE`) and floating datetimes in a component were anchored to the process-local time zone, so the result of a time-range or alarm search depended on `TZ`.  An all-day event on Oct 11 matched a search for Oct 12 in Europe/Berlin when the process ran in UTC.  When the search range is timezone-aware, such values are now interpreted in the time zone of the search range.  Naive search ranges behave as before.  Note that caldav turns `date` search bounds into UTC midnights, so in such searches floating (naive) times in components are now read as UTC.  https://github.com/pycalendar/icalendar-searcher/issues/17

- **All-day journals only matched at midnight**: a `VJOURNAL` with a date `DTSTART` was treated as a single instant at the start of the day instead of spanning the whole day (RFC 4791 section 9.9), so a time-range search later that day did not find it.  Recurring all-day journals expanded by the search are not fixed yet.

## [1.0.7] - 2026-10-11

### Fixed

- **A matching property filter skipped all remaining property filters**: `check_component()` / `filter()` accepted a component as soon as one property filter matched with `contains` on `category`/`categories`, or with `==` on any property; filters added after it were never evaluated.  A search with a category filter followed by a summary filter returned every item in that category regardless of summary.  All property filters are now required to match.

## [1.0.6] - 2026-05-29

### Fixed

- **Recurrence sets with master in non-first position were rejected**: RFC 5545 does not mandate that the master VEVENT (carrying `RRULE`) appears first in a VCALENDAR.  Some CalDAV servers (notably `calendar.mail.ru`) emit override VEVENTs (with `RECURRENCE-ID`) before the master.  The previous validation assumed `components[0]` was always the master and raised `ValueError` for any other ordering, which caused `caldav._filter_search_results` to silently drop all expanded recurring instances.  The master is now located by content (has `RRULE`, no `RECURRENCE-ID`) regardless of position, and the list is reordered so it sits at index 0 for downstream expansion.  Also reduced duplicated error-check code in the same function.

- **`check_component()` mutated `self` on every call**: The method resolved `None` fields (`include_completed`, `todo`, `event`, `journal`) and normalised `start`/`end`/`alarm_start`/`alarm_end` date objects to datetimes by writing back to `self`.  This made a `Searcher` instance stateful: calling `check_component()` twice could produce different results, and reusing a `Searcher` across multiple search operations (e.g. in the python-caldav library) could silently change behaviour after the first call.  All these values are now computed as local variables inside `check_component()` and threaded to the internal filter methods via new keyword parameters (`_start`, `_end`, `_alarm_start`, `_alarm_end`, `_include_completed`), keeping `self` immutable throughout.  (Triggered by https://github.com/python-caldav/caldav/issues/650)

- **VTODO with only `COMPLETED` (no `DTSTART`/`DUE`/`CREATED`) crashed on time-range search**: A time-range filter on a `VTODO` that has `COMPLETED` but no `DTSTART`, `DUE`, or `CREATED` would crash.  The RFC 4791 §9.9 matrix was also re-read and the implementation now correctly handles all VTODO timestamp combinations: a task with only `CREATED` is treated as open-ended (matches any search interval ending after `CREATED`); a task with only `COMPLETED` is treated as a point event; and a task with both `CREATED` and `COMPLETED` uses them as the time bounds when no `DTSTART`/`DUE` is present.

## [1.0.5] - 2026-02-19

### Changes

Replace Poetry with Hatch.  Version 1.0.4 never got as far as pypi due to a silly lock file problem.

## [1.0.4] - 2026-02-19

### Fixed

- **`undef` filter for CATEGORIES was broken with icalendar >= 6.x**: `icalendar` 6.x provides a default empty `vCategory` object for the `CATEGORIES` property even when it is not explicitly present in the iCalendar data, making `"categories" in component` always return `True`.  This caused searches like `no_category=True` (or `add_property_filter("categories", ..., operator="undef")`) to incorrectly filter out *all* events instead of only those that actually have categories.  Fixed by checking the computed category set (empty → not defined) rather than the unreliable `in` test.

- **`undef` filter for DTEND was broken for recurring all-day events**: `recurring_ical_events` adds a computed `DTEND = DTSTART + 1 day` to individual occurrences of all-day recurring events, even when the master event does not have an explicit `DTEND`.  This caused searches for events without `DTEND` (e.g. `no_dtend=True`) to incorrectly filter out recurring all-day events.  Fixed by skipping `undef` checks when filtering expanded recurrence occurrences whose master element has already passed the `undef` check.

## [1.0.3] - 2025-11-30

### Fixed

Support for RFC7986-style CATEGORIES split over multiple lines.  https://github.com/pycalendar/icalendar-searcher/issues/6
- The sort method did not handle lists very well.  In particular, RFC 7986 section 5.6 defines that the categories field may be split over multiple lines in the icalendar object, this could cause an exception to be raised.  Now lists are sorted and converted to a comma-separated string prior to sorting.
- The filter method would also run into problems, it has also been fixed

## [1.0.0] - 2025-11-27

### Added
- **`filter()` method**: Implemented filtering for lists of Calendar/Component objects
  - Accepts `list[Calendar | Component]` as input
  - Optional `split_expanded` parameter for splitting expanded recurrences into separate Calendar objects
  - Returns new list without modifying input (immutability guarantee)
  - Preserves Calendar properties and VTIMEZONE components
  - Applies all configured property filters and component type filters
  - Handles recurrence expansion when `self.expand` is True
  - Deep copies all returned objects for safety

- **`sort()` method**: Implemented sorting for lists of components/calendars
  - Accepts `list[Component | CalendarObjectResource]` as input
  - Returns new sorted list without modifying input
  - Uses configured sort keys (via `add_sort_key()`)
  - Supports multiple sort keys with proper precedence
  - Supports case-sensitive/case-insensitive sorting
  - Supports reversed sorting
  - Handles Calendar, Component, and CalendarObjectResource objects

- **`filter_calendar()` method**: Implemented filtering of subcomponents within a Calendar object
  - Filters all subcomponents (events/todos/journals) within a single Calendar
  - Returns new Calendar with only matching subcomponents, or None if no matches
  - Preserves VTIMEZONE components
  - Preserves all Calendar-level properties
  - Handles recurrence expansion when `self.expand` is True
  - Deep copies to ensure immutability

- **`sort_calendar()` method**: Implemented sorting of subcomponents within a Calendar object
  - Sorts all subcomponents (events/todos/journals) within a single Calendar
  - Preserves VTIMEZONE components in their original position
  - Returns new Calendar without modifying input
  - Preserves all Calendar-level properties
  - Deep copies to ensure immutability

- **Comprehensive test suites**:
  - 15 tests for `filter()` method covering filtering, expansion, splitting, and edge cases
  - 5 tests for `filter_calendar()` method covering basic filtering, no matches, timezones, expansion, and mixed types
  - 12 tests for `sort()` and `sort_calendar()` methods covering various sorting scenarios

### Changed
- **Core functionality now complete**: The library's main methods (`filter()`, `filter_calendar()`, `sort()`, `sort_calendar()`) are now fully implemented and no longer stubs
- **README updated**: Added usage examples for `filter()` and `sort()` methods, updated status section to reflect completion of core functionality

### Notes
- This is the first stable 1.0 release
- The API is considered stable and will follow semantic versioning going forward
- Breaking changes in future versions will require a major version bump (2.0, 3.0, etc.)

## [0.5.0] - 2025-11-26

### Changed
- **BREAKING: Collation system redesigned**: Simplified collation architecture to use three collation strategies (SIMPLE, UNICODE, LOCALE), each supporting a `case_sensitive` parameter
  - Removed `Collation.BINARY` - use `Collation.SIMPLE` with `case_sensitive=True` instead
  - Removed `Collation.CASE_INSENSITIVE` - use `Collation.SIMPLE` with `case_sensitive=False` instead
  - All collation strategies (SIMPLE, UNICODE, LOCALE) now accept `case_sensitive` boolean parameter
  - UNICODE and LOCALE collations can now be case-sensitive or case-insensitive
  - PyICU collator strength is configured based on `case_sensitive` parameter (TERTIARY for case-sensitive, SECONDARY for case-insensitive)

### Migration Guide
- Replace `collation=Collation.BINARY` with `collation=Collation.SIMPLE, case_sensitive=True`
- Replace `collation=Collation.CASE_INSENSITIVE` with `collation=Collation.SIMPLE, case_sensitive=False`
- UNICODE/LOCALE collations now require explicit `case_sensitive` parameter if you want case-sensitive behavior

## [0.4.1] - 2025-11-26

### Added
- **UNICODE and LOCALE collation support for "==" operator**: The == operator now properly supports UNICODE and LOCALE collations using ICU sort key comparison. Previously only BINARY and CASE_INSENSITIVE collations were supported for exact match operations.

### Fixed
- PyICU-based tests now pass in CI environments where PyICU is installed

## [0.3.1] - 2025-11-26

Some wheel files etc that shouldn't be in the repository has accidentally been added.  Either I've done some silly mistake while sleeping, or perhaps it was a mistake giving the AI access to my computer.

## [0.3.0] - 2025-11-26

Categories are a mess.  I've tried to make a predictable behaviour by making a distinction between `categories` (handling the property filter value as a list that should match or be a subset of the event category set)  and `category` (handling the property filter value as a string that should match towards at least one of the categories in the event).

### Added
- **"category" (singular) property filter**: New virtual property for substring matching within category names
  - `"category"` with "contains" operator does substring matching (e.g., "out" matches "outdoor")
  - `"category"` with "==" operator matches if value exactly equals at least one category name
  - Commas in filter values are treated as literal characters, not split into multiple categories
  - Complements existing `"categories"` (plural) which does exact category name matching

### Fixed
- Category filtering now properly respects collation settings for case-insensitive matching
- Category "contains" operator now correctly checks for subset (exact category names) rather than substring matching
- Category "==" operator now properly supports case-insensitive exact matching
- Text properties with "==" operator now support case-insensitive comparison when `case_sensitive=False`
- Category preprocessing now correctly handles tuples with comma-separated strings

## [0.2.0] - 2025-11-24

Text filtering can be done both case-sensitive and case-insensitive - we need to support both of them.  And we also may need to support various collations.  DISCLAIMER: While I could easily add case insensitive/sensitive filtering myself, as soon as collations was tossed into the equation I considered the AI could do it better and faster than me.  So 0.2.0 is AI-generated code, but curated by a human.

### Added
- **Collation support for text searches and sorting**: Added comprehensive support for both case-sensitive and case-insensitive text comparisons
  - New `case_sensitive` parameter in `add_property_filter()` and `add_sort_key()` methods for simple API
  - New `Collation` enum for power users with support for `BINARY`, `CASE_INSENSITIVE`, `UNICODE`, and `LOCALE` collation strategies
  - Optional PyICU integration for advanced Unicode and locale-aware collation (install with `pip install 'icalendar-searcher[collation]'`)
  - Collation support for all text properties (SUMMARY, LOCATION, DESCRIPTION, etc.)
  - Collation support for CATEGORIES property with special handling
  - Graceful fallback when PyICU is not installed

### Changed
- **BREAKING**: Default text search behavior is now case-sensitive (was case-insensitive)
- Category searches are now case-sensitive by default (was implicitly case-sensitive, now explicit)

### Fixed
- Improved type handling in property filters to correctly distinguish between text properties and other types

## [0.1.10] - Previous Release
