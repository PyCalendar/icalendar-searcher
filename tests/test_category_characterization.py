"""Characterization tests pinning the current behavior of the
``category``/``categories`` property handling.

These tests exist to make the upcoming refactor (consolidating the scattered
category special-casing into a single comma-list-property abstraction)
provably behavior-preserving.  They deliberately target *observable* behavior
(matching, undef, sorting) rather than the internal storage representation,
since that representation is exactly what the refactor is allowed to change.

The ``resources`` cases pin that ``resources`` stays a plain text property
(no comma-splitting / list semantics) -- it is intentionally left out of the
comma-list abstraction for now.
"""

from icalendar import Calendar, Component

from icalendar_searcher import Searcher


def _todo(categories: str | None = None, resources: str | None = None) -> Component:
    """Build a VTODO subcomponent with optional CATEGORIES/RESOURCES."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//icalendar-searcher//characterization//en",
        "BEGIN:VTODO",
        "UID:char-1",
        "SUMMARY:characterization",
    ]
    if categories is not None:
        lines.append(f"CATEGORIES:{categories}")
    if resources is not None:
        lines.append(f"RESOURCES:{resources}")
    lines += ["END:VTODO", "END:VCALENDAR"]
    return Calendar.from_ical("\n".join(lines)).subcomponents[0]


def _matches(prop_filter: tuple, component: Component, case_sensitive: bool = True) -> bool:
    searcher = Searcher()
    searcher.add_property_filter(*prop_filter, case_sensitive=case_sensitive)
    return searcher._check_property_filters(component)


# --------------------------------------------------------------------------
# category (singular): substring matching, commas treated literally
# --------------------------------------------------------------------------


def test_char_category_singular_substring() -> None:
    comp = _todo("outdoor,family,winter")
    # "contains" -> substring within any single category name
    assert _matches(("category", "out"), comp)  # substring of "outdoor"
    assert _matches(("category", "fam"), comp)  # substring of "family"
    assert _matches(("category", "outdoor"), comp)
    assert not _matches(("category", "xyz"), comp)
    # commas are literal for the singular form (NOT split) -> no such category
    assert not _matches(("category", "family,outdoor,winter"), comp)


def test_char_category_singular_equals() -> None:
    comp = _todo("outdoor,family,winter")
    # "==" -> exact match to at least one whole category name
    assert _matches(("category", "outdoor", "=="), comp)
    assert _matches(("category", "family", "=="), comp)
    assert not _matches(("category", "out", "=="), comp)  # substring is not exact
    assert not _matches(("category", "family,outdoor,winter", "=="), comp)


def test_char_category_singular_case_sensitivity() -> None:
    comp = _todo("outdoor,family,winter")
    assert not _matches(("category", "OUT"), comp, case_sensitive=True)
    assert _matches(("category", "OUT"), comp, case_sensitive=False)


# --------------------------------------------------------------------------
# categories (plural): exact matching, commas split into a set
# --------------------------------------------------------------------------


def test_char_categories_plural_subset_contains() -> None:
    comp = _todo("outdoor,family,winter")
    # "contains" -> filter categories must be a subset of the component's
    assert _matches(("categories", "winter,outdoor"), comp)
    assert _matches(("categories", ("winter", "outdoor")), comp)
    assert _matches(("categories", "outdoor"), comp)
    assert not _matches(("categories", "outdoor,summer"), comp)  # summer absent
    assert not _matches(("categories", "out"), comp)  # exact, not substring


def test_char_categories_plural_exact_equality_order_independent() -> None:
    comp = _todo("outdoor,family,winter")
    assert _matches(("categories", ["family", "outdoor", "winter"], "=="), comp)
    assert _matches(("categories", "family,outdoor,winter", "=="), comp)
    assert _matches(("categories", "winter,outdoor,family", "=="), comp)  # order irrelevant
    assert not _matches(("categories", "outdoor", "=="), comp)  # missing two
    assert not _matches(("categories", "outdoor,winter", "=="), comp)  # missing one
    # a single-element tuple whose lone value contains a comma is one literal
    # category for "==" -> does not equal the 3-category component
    assert not _matches(("categories", ("outdoor,winter",), "=="), comp)


def test_char_categories_plural_single_category_component() -> None:
    comp = _todo("outdoor")
    assert _matches(("categories", "outdoor", "=="), comp)
    assert not _matches(("categories", "out", "=="), comp)
    assert not _matches(("categories", "outdoors"), comp)


def test_char_categories_plural_case_sensitivity() -> None:
    comp = _todo("outdoor,family,winter")
    assert not _matches(("categories", "OUTDOOR,WINTER,FAMILY", "=="), comp, case_sensitive=True)
    assert _matches(("categories", "OUTDOOR,WINTER,FAMILY", "=="), comp, case_sensitive=False)


# --------------------------------------------------------------------------
# undef: present vs absent (icalendar >=6 supplies an empty vCategory default)
# --------------------------------------------------------------------------


def test_char_categories_undef() -> None:
    present = _todo("outdoor")
    absent = _todo(None)
    for key in ("category", "categories"):
        assert not _matches((key, None, "undef"), present)
        assert _matches((key, None, "undef"), absent)


def test_char_categories_empty_line_is_undefined() -> None:
    """A stored ``CATEGORIES:`` line (written by icalendar's mutating
    ``component.categories`` accessor, see
    https://github.com/collective/icalendar/issues/1722) holds no category."""
    damaged = _todo("")
    for key in ("category", "categories"):
        assert _matches((key, None, "undef"), damaged)
        assert not _matches((key, None, "def"), damaged)


def test_char_categories_set_as_plain_text() -> None:
    """CATEGORIES set programmatically as a comma-separated string."""
    task = _todo(None)
    task["CATEGORIES"] = "outdoor,sports"
    assert _matches(("categories", "sports", "contains"), task)
    assert _matches(("category", "door", "contains"), task)
    assert not _matches(("categories", "outdoor,sports", "!="), task)


# --------------------------------------------------------------------------
# sort: deterministic ordering by categories
# --------------------------------------------------------------------------


def test_char_categories_sort_order() -> None:
    a = _todo("apple")
    m = _todo("mango")
    z = _todo("zucchini")
    none = _todo(None)
    searcher = Searcher()
    searcher.add_sort_key("categories")
    ordered = searcher.sort([z, none, m, a])
    # empty (no categories) sorts first, then alphabetical
    assert ordered == [none, a, m, z]


# --------------------------------------------------------------------------
# resources: stays a plain text property (NOT comma-split) -- pin unchanged
# --------------------------------------------------------------------------


def test_char_resources_plain_text_unchanged() -> None:
    comp = _todo(resources="Projector,Easel")
    # whole value matched as one escaped text -> substring works
    assert _matches(("resources", "Proj"), comp)
    assert _matches(("resources", "Projector"), comp)
    # exact match only against the whole literal value, not a split element
    assert not _matches(("resources", "Projector", "=="), comp)
    assert _matches(("resources", "Projector,Easel", "=="), comp)
