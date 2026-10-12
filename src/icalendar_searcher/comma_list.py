"""Centralised handling of "comma-token list" iCalendar properties.

RFC 5545 defines a handful of properties whose value is a COMMA-separated
list of short tokens (CATEGORIES, RESOURCES).  Such a property is exposed by
the searcher under two names:

* a *plural* canonical name (e.g. ``categories``) with **exact** matching and
  comma-splitting semantics:

  - ``contains`` -> subset check (all filter values must be present)
  - ``==``       -> exact set equality (order irrelevant)
  - commas split the filter value into several tokens

* a *singular* alias (e.g. ``category``) with **substring** matching and
  comma-literal semantics:

  - ``contains`` -> substring match within any single token
  - ``==``       -> exact match to at least one whole token
  - commas are kept literally (not split)

Previously this behaviour was hand-special-cased in three places
(``add_property_filter``, ``_check_property_filters`` and the sort path).  This
module concentrates it so the call sites only have to ask "is this a comma-list
key?" and delegate.

Only CATEGORIES is registered for now.  RESOURCES intentionally stays a plain
text property; registering it here is a one-line change (plus a deliberate
decision to give it these search semantics).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from icalendar import Component
from icalendar.prop import vCategory, vText

from .collation import Collation, get_collation_function
from .utils import NEGATED_OPERATORS, types_factory


@dataclass(frozen=True)
class _CommaListSpec:
    """A comma-list property family: its plural canonical name and singular alias.

    The iCalendar component value is read through ``getattr(component, plural)``
    (e.g. ``component.categories``), which the icalendar library exposes as a
    convenience accessor returning the list of tokens.
    """

    plural: str
    singular: str


_SPECS: tuple[_CommaListSpec, ...] = (_CommaListSpec(plural="categories", singular="category"),)

_BY_PLURAL: dict[str, _CommaListSpec] = {spec.plural: spec for spec in _SPECS}
_BY_SINGULAR: dict[str, _CommaListSpec] = {spec.singular: spec for spec in _SPECS}


def _spec_for(key: str) -> _CommaListSpec | None:
    key = key.lower()
    return _BY_PLURAL.get(key) or _BY_SINGULAR.get(key)


def is_comma_list_key(key: str) -> bool:
    """Whether ``key`` names a comma-list property (plural or singular form)."""
    return _spec_for(key) is not None


def is_plural_sort_key(key: str) -> bool:
    """Whether ``key`` is the plural canonical name (the form used for sorting)."""
    return key.lower() in _BY_PLURAL


def _component_value_set(spec: _CommaListSpec, component: Component) -> set[str]:
    """Return the component's tokens for this property as a set of strings."""
    return {str(x) for x in getattr(component, spec.plural)}


def sort_value(key: str, component: Component) -> object:
    """Return the raw value used when sorting by this comma-list property."""
    spec = _spec_for(key)
    assert spec is not None, f"{key!r} is not a comma-list property"
    return getattr(component, spec.plural)


def store_filter_value(key: str, value: object) -> object:
    """Return the value to store for a comma-list property filter.

    Plural string values are comma-split into a ``vCategory`` (via the
    icalendar types factory); singular values are kept as a raw string so they
    can be substring-matched; other plural values are run through the types
    factory for the canonical (plural) property.
    """
    spec = _spec_for(key)
    assert spec is not None, f"{key!r} is not a comma-list property"
    if key.lower() == spec.singular:
        ## singular: store as-is (raw string), enabling substring matching
        return value
    ## plural
    fact = types_factory.for_property(spec.plural)
    if isinstance(value, str):
        ## "FAMILY,FINANCE" means "has both categories", not one literal
        ## category named "FAMILY,FINANCE"
        return fact(fact.from_ical(value))
    return fact(value)


def _normalize_plural_filter(filter_value: object) -> str | set[str]:
    """Normalise a stored plural filter value to a single string or a set.

    A lone token is returned as a plain ``str`` (so a one-category ``==`` can be
    checked precisely); anything multi-valued becomes a ``set[str]``.
    """
    if isinstance(filter_value, vCategory):
        if len(filter_value.cats) == 1:
            single = str(filter_value.cats[0])
            return set(single.split(",")) if "," in single else single
        return {str(x) for x in filter_value.cats}
    ## The two branches below are defensive: in normal use a plural filter is
    ## always stored as a vCategory.  They are kept to preserve prior behaviour.
    if isinstance(filter_value, (str, vText)):
        text = str(filter_value)
        return set(text.split(",")) if "," in text else text
    if isinstance(filter_value, Iterable):
        result: set[str] = set()
        for item in filter_value:
            item_str = str(item)
            if "," in item_str:
                result.update(item_str.split(","))
            else:
                result.add(item_str)
        return result
    return filter_value  # type: ignore[return-value]


def _eq(a: str, b: str, case_sensitive: bool) -> bool:
    return a == b if case_sensitive else a.lower() == b.lower()


def matches(
    key: str,
    operator: str,
    filter_value: object,
    component: Component,
    *,
    collation: Collation,
    case_sensitive: bool,
    locale: str | None,
) -> bool:
    """Whether ``component`` matches a comma-list property filter.

    Handles the ``def``, ``undef``, ``contains``, ``==``, ``!contains`` and ``!=`` operators
    for both the plural (exact/subset) and singular (substring) forms.
    """
    spec = _spec_for(key)
    assert spec is not None, f"{key!r} is not a comma-list property"
    plural = key.lower() == spec.plural
    comp_values = _component_value_set(spec, component)

    ## icalendar >=6 supplies an empty vCategory default even when the
    ## property is absent, so presence is decided by the value set.
    if operator == "undef":
        return not comp_values
    if operator == "def":
        return bool(comp_values)
    if operator in NEGATED_OPERATORS:
        ## like the other value operators, a negation needs the property defined
        return bool(comp_values) and not matches(
            key,
            NEGATED_OPERATORS[operator],
            filter_value,
            component,
            collation=collation,
            case_sensitive=case_sensitive,
            locale=locale,
        )

    if not plural:
        ## singular: substring (contains) / exact-to-one-token (==)
        filter_str = str(filter_value)
        if operator == "contains":
            collation_fn = get_collation_function(collation, case_sensitive, locale)
            return any(collation_fn(filter_str, token) for token in comp_values)
        if operator == "==":
            return any(_eq(filter_str, token, case_sensitive) for token in comp_values)
        raise NotImplementedError(f"The operator {operator} is not supported yet.")

    ## plural: exact matching against the set of tokens
    normalized = _normalize_plural_filter(filter_value)
    if operator == "contains":
        if isinstance(normalized, str):
            return any(_eq(normalized, cv, case_sensitive) for cv in comp_values)
        ## subset check: every requested token must be present
        return all(any(_eq(fv, cv, case_sensitive) for cv in comp_values) for fv in normalized)
    if operator == "==":
        if isinstance(normalized, str):
            if len(comp_values) != 1:
                return False
            return _eq(normalized, next(iter(comp_values)), case_sensitive)
        ## exact set equality (order irrelevant)
        if len(normalized) != len(comp_values):
            return False
        return all(any(_eq(fv, cv, case_sensitive) for cv in comp_values) for fv in normalized)
    raise NotImplementedError(f"The operator {operator} is not supported yet.")
