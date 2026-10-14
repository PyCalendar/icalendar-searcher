# icalendar-searcher

This library should contain logic for searching, filtering and sorting icalendar data, as well as logic for storing and representing an icalendar search query.

## Audience

* This will be used for the python CalDAV client library, both for bundling search parameters together in one object, for doing client-side filtering when the server does not support the desired search query.
* This may be useful in any kind of software handling collections of calendar content and needing to do filtering or searches on it.
* This may also be useful by calendar server developers.

## Maturity

I've decided to release 1.0 now as I think it's getting more or less feature-complete (with the exception of advanced operators).  However, the library has not been battle-tested.

`sort` and `check_component` is used by the caldav project.  It has not been used much in the wild yet, but they have been through some QA and is also tested by test-code from the caldav project.

`filter`, `filter_calendar` and `sort_calendar` has not been tested yet, is AI-generated and is only covered by AI-generated test code.  There may be dragons.

## Maturity

I've decided to release 1.0 now as I think it's getting more or less feature-complete (with the exception of advanced operators). The API is considered stable and will follow semantic versioning going forward.

`sort` and `check_component` is used by the caldav project, it has not been used much in the wild yet, but has been through quite some testing.

`filter`, `filter_calendar` and `sort_calendar` has not been tested yet, is AI-generated and is only covered by AI-generated test code.  There may be dragons.

**Operators**: `contains`, `==`, `!contains`, `!=` (alias `<>`), `def` and `undef`.  The negations require the property to be defined; a component without it does not match (use `undef` for that).

**Not yet implemented**: `<`, `<=`, `>`, `>=`, `~` (regex).

## Usage

No proper usage documentation has been written yet, sorry.  There are tons of inline comments and docstrings though.  The AI has contributed with quite some verbose comments in the test code, but little of it has been exposed to any proper QA.

### Basic Example

```python
from icalendar_searcher import Searcher
from datetime import datetime

# Create a searcher with filters
searcher = Searcher(
    event=True,  # Only events
    start=datetime(2025, 1, 1),
    end=datetime(2025, 12, 31)
)

# Add property filters
searcher.add_property_filter("SUMMARY", "meeting", operator="contains")
searcher.add_property_filter("LOCATION", "Office", operator="contains", case_sensitive=False)

# Check if a single component matches
result = searcher.check_component(calendar)

# Filter a list of components
calendars = [cal1, cal2, cal3]
matching = searcher.filter(calendars)

# Sort components
searcher.add_sort_key("DTSTART")
sorted_calendars = searcher.sort(calendars)
```

### Case-Sensitive vs Case-Insensitive Filtering

By default, text filtering is **case-sensitive**. You can make it case-insensitive:

```python
# Case-insensitive search (simple API)
searcher.add_property_filter("SUMMARY", "meeting", case_sensitive=False)

# Case-sensitive search (default)
searcher.add_property_filter("SUMMARY", "Meeting")
```

Case-insensitivity is not straight-forward.  It may cause non-deterministic sort results, and there may be problems with unicode characters - i.e., according to the CalDAV standard, case-insensitivity should only apply to ASCII-characters - causing mismatches between naïve and NAÏVE, cliché and CLICHÉ, smörgåsbord and SMÖRGÅSBORD, not to forget millions of words in non-English languages, complete non-latin scripts, etc.  By default this library in itself handles Unicode relatively well - but for CalDAV searches, one may experience that case-insensitivity only applies to ASCII letters.

### Category Filtering

Two virtual properties are available for filtering by categories:

- **"categories"** (plural): Categories is considered to be a set of categories to be matched with the set of categories found in the event.  If categories is given as a string, it will be split by the commas.
- **"category"** (singular): Category is considered to be a string, to be matched literally towards at least one of the categories in the event.

Examples:

```python
# Match events with both "WORK" and "URGENT" categories (exact match)
searcher.add_property_filter("categories", "WORK,URGENT", operator="contains")

# Match events where any category contains "out" (e.g., "outdoor", "outing")
searcher.add_property_filter("category", "out", operator="contains")
```

### Accents

Accent sensitivity is a separate axis from case sensitivity.  With `accent_sensitive=False`, "muller" matches "Müller":

```python
searcher.add_property_filter("SUMMARY", "muller", case_sensitive=False, accent_sensitive=False)
```

Both parameters default to `True`, and both apply to all the text operators alike (`contains`, `==`, their negations, and `category`/`categories`), as well as to `add_sort_key()`.

Without PyICU, accents are folded by stripping combining marks after Unicode NFD decomposition.  That knows nothing about languages, and leaves letters without a decomposition (ø, æ, ß, ł) alone.

### Advanced Collation (requires PyICU)

For Unicode and locale-aware text comparison, install with:

```bash
pip install 'icalendar-searcher[collation]'
```

`Collation.UNICODE` uses the root collation of the Unicode Collation Algorithm, and `Collation.LOCALE` the CLDR rules of the given locale.  The two axes map onto the ICU collator like this:

| `case_sensitive` | `accent_sensitive` | ICU collator |
|---|---|---|
| `True` (default) | `True` (default) | TERTIARY strength |
| `False` | `True` | SECONDARY strength |
| `False` | `False` | PRIMARY strength |
| `True` | `False` | PRIMARY strength, `CASE_LEVEL` on |

**There is no language-independent right answer** to what is an accent and what is a letter of its own, and the locale decides:

```python
from icalendar_searcher.collation import Collation

# German: ü is an accented u - "muller" matches "Müller"
searcher.add_property_filter("SUMMARY", "muller", collation=Collation.LOCALE, locale="de_DE",
                             case_sensitive=False, accent_sensitive=False)

# Scandinavian: å, æ/ä and ø/ö are letters of their own - under nb_NO (or sv_SE,
# da_DK), "smorgasbord" does NOT match "smörgåsbord", nor "blabaersyltetoy"
# "blåbærsyltetøy".  Under Collation.UNICODE (root) both match - note that root
# folds æ to "ae", so "blabarsyltetoy" does not.
searcher.add_property_filter("SUMMARY", "smorgasbord", collation=Collation.LOCALE, locale="nb_NO",
                             case_sensitive=False, accent_sensitive=False)

# Turkish: İ is the capital of i (and I the capital of ı) - "istanbul" matches "İstanbul",
# but "ISTANBUL" does not.  Under Collation.UNICODE, İ is an I with an accent, so
# "istanbul" only matches with accent_sensitive=False.
searcher.add_property_filter("LOCATION", "istanbul", collation=Collation.LOCALE, locale="tr_TR",
                             case_sensitive=False)

# Locale-aware sorting (e.g., Norwegian sorts æ, ø, å after z)
searcher.add_sort_key("SUMMARY", collation=Collation.LOCALE, locale="nb_NO")
```

Substring matching (`contains`) uses ICU's `StringSearch` with the same collator as `==`, so the two operators agree.

**CalDAV servers cannot do this.**  The collations CalDAV servers are required to support (RFC 4791 section 7.5) are `i;octet` (case- and accent-sensitive) and `i;ascii-casemap` (case-insensitive for ASCII letters only); `i;unicode-casemap` (RFC 5051) folds case but not accents.  None of them is accent-insensitive, and none is locale-aware, so a client like `caldav` has to filter such searches client-side.

## Related projects

* The project depends on the [icalendar](https://github.com/collective/icalendar) library, all calendar contents handled by this library is coming in and out as ``icalendar.Component`` or ``icalendar.Calendar``.  However, the library should also support wrapped objects (like instances of the ``caldav.Event`` class).
* The project depends on the [recurring-ical-events](https://github.com/niccokunzmann/python-recurring-ical-events) library for expanding recurrence sets.
* The project is used by the [Python CalDAV client library](https://github.com/python-caldav/caldav)

## History

This is a spin-off from the python caldav project, started by Tobias Brox in 2025-11, the maintainer of the Python CalDAV client library at that time, in collaboration with the main contributors of the icalendar library.

## AI

The author has been experimenting a bit with AI usage while creating this project, both GitHub Copilot and Claude has been tested.  Most of the test code has been created by the AI.  AI has also been utilized a bit for refactoring, bug hunting, and a little bit code generation (particularly wrg of the collations support), but most of the "business logic" was written by me.

While all the AI-generated changes in the business logic has been looked through thoroughly, very little QA has been done on the test code.

## Performance

In the early versions, the filter method will take the calendar contents one by one and check if it matches or not.  This will work out well enough for small calendar sets.  If lots of searches are to be done on fairly static data (like what typically may happen at the server side in a calendaring system), then it would be an idea to add indexes.

The expansion part may cause millions of recurrences to be created.  It even supports open-ended intervals.  It's possible by returning generators.  However, things will most likely blow up and eat all the CPU and memory it gets the hands on whenever one wants to do sorting of such a thing.

## License

This library is dual-licensed under the [GNU General Public License v3.0 or later](https://www.gnu.org/licenses/gpl-3.0.html) or the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0), the same as the python caldav library which depends on it.

Releases up to and including 1.0.8 were published under the GNU Affero General Public License v3.0.  The README of those releases stated that the code might later be dual-licensed under a more permissive license; the relicensing was needed because the caldav library has a hard dependency on this package, and an AGPL-only dependency would subject caldav users to AGPL terms, defeating caldav's Apache-2.0 option.

By contributing you agree that your contributions are released under both licenses.
