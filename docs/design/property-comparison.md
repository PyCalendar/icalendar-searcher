# Comparing property values (ROADMAP 5.3)

What `FilterMixin._values_equal()` in `src/icalendar_searcher/filters.py` asks of
the `icalendar` library, and where it gets a different answer than it should.

## What the code does

1. `add_property_filter(key, value)` coerces the value with
   `types_factory.for_property(key)(value)`, so the filter value and the
   component's property are normally the *same icalendar type* (`vText`,
   `vInt`, `vDDDTypes`, `vCalAddress`, ...).
2. `_values_equal(comp, filter)` then does `comp == filter` and nothing more,
   plus two special cases: `str in set`, and a collation-aware comparison when
   both sides are `str` (`vText`, `vUri` and `vCalAddress` are `str`
   subclasses).  A TODO in the code says "we should add more logic for the
   different property types.  Maybe get it into the icalendar library."
3. A property that occurs more than once (`ATTENDEE`, `COMMENT`) comes back as a
   list and matches if any instance matches.  `CATEGORIES` is handled by
   `comma_list.py` and is not covered here.

So the verdict for every non-text type is whatever `icalendar`'s `__eq__`
says.  That is the question for upstream: **what should `==` mean for each
property type, so that a client can ask "is this property equal to that value"?**

## Observed behaviour (icalendar 7.3.x development build, `==` operator, via `Searcher`)

| Type | Example | Result | Verdict |
|---|---|---|---|
| `vText` | `SUMMARY`, `STATUS`, `CLASS` | equal, case-sensitive by default | fine; collation is ours |
| `vInt` | `PRIORITY`, `SEQUENCE` | `3`, `"3"` and `3.0` all match | fine |
| `vUri` | `URL` | exact string; `http://Example.com/a` != `http://example.com/a` | RFC 3986 says scheme/host are case-insensitive |
| `vCalAddress` | `ORGANIZER`, `ATTENDEE` | exact string; `a@example.com` != `mailto:a@example.com`; `mailto:A@..` != `mailto:a@..` | same; the mailto scheme is case-insensitive, the local part arguably is not |
| `vDDDTypes` datetime | `DTSTART` | aware vs aware compares the instant (UTC == Oslo +2h: match) | fine |
| | | floating vs aware: never equal; floating vs floating: wall clock | defensible, but inconsistent with the time-range code, which interprets floating times in a caller-supplied zone |
| | | `date` vs midnight `datetime`: never equal | defensible |
| `vDDDTypes` duration | `DURATION`, `TRIGGER` | equal to `timedelta` | fine |
| `vGeo` | `GEO` | equal to a `(lat, lon)` tuple | exact float comparison |
| `vDDDLists` | `EXDATE` | equal to a single `datetime` | fine |
| `vDDDLists` with `VALUE=PERIOD` | `RDATE` | a `(start, duration)` tuple is *not* equal to the parsed property, even with the same value | see below |
| `vRecur` | `RRULE` | `vRecur == dict` is True | but see the last bullet below |

Specific problems:

* **PERIOD values cannot be constructed from a Python tuple.**
  `types_factory.for_property("RDATE")((start, timedelta))` treats the tuple as
  a list of two values (a datetime and a duration), not as one period, so the
  result has two entries and never equals the parsed `RDATE;VALUE=PERIOD`.
  A caller has no unambiguous way to say "one period".
* **No normalised comparison key.**  Everything above would be answered by one
  function on the property: "a hashable, order-insensitive value that two
  properties have iff they are equal as defined by RFC 5545".  That would also
  make `in` (set membership) and sorting well-defined.
* **Ordering is not defined at all** for most types (`<`, `>`), which is why
  the comparison operators listed under *Beyond the funded scope* in the roadmap
  are blocked on this.
* *Unverified:* an `==` filter on `RRULE`, `RDATE` or `EXDATE` of a recurring
  event did not match through `Searcher.check_component()` although the
  property values compare equal.  Probably the check runs against expanded
  occurrences, which carry no `RRULE`; it is ours to look into, not upstream's.

## What this library needs from `icalendar`

For each property type, in order of importance:

1. A documented `__eq__` that follows RFC 5545 (and RFC 3986 for URI-valued
   properties), including: floating vs aware datetimes, DATE vs DATE-TIME,
   case-insensitivity of the `mailto:` scheme, parameter handling (does
   `DTSTART;TZID=Europe/Oslo:...` equal the same instant in UTC? it does today
   for datetimes - keep it).
2. An unambiguous way to build a PERIOD value in Python.
3. Optional: ordering (`<`) for the types that have one in RFC 5545
   (integers, dates, date-times, durations, periods).

This library should keep only the *policy* layer: collation for text, the
`category`/`categories` distinction, and any-of-many for repeated properties.

TODO: post an issue in the icalendar library.
