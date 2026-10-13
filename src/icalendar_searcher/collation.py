"""Text collation support for string comparisons.

This module provides collation (text comparison) functionality with optional
PyICU support for advanced Unicode collation. Falls back to simple binary
and case-insensitive comparisons when PyICU is not available.

Text comparison has two independent axes, ``case_sensitive`` and
``accent_sensitive``, both True by default.  Under the ICU collations
they map onto collator strength and the ``CASE_LEVEL`` attribute:

=================  ==================  ===============================
case_sensitive     accent_sensitive    ICU collator
=================  ==================  ===============================
True               True                TERTIARY
False              True                SECONDARY
False              False               PRIMARY
True               False               PRIMARY with CASE_LEVEL on
=================  ==================  ===============================

What counts as an accent is locale-dependent: in ``nb_NO`` "ø" and "å" are
letters of their own and never match "o" and "a", while the root collation
treats them as accented.  Under ``Collation.SIMPLE`` accents are folded by
stripping combining marks after NFD decomposition, which knows nothing of
locales and leaves letters without a decomposition (ø, æ, ß) alone.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from enum import Enum
from functools import lru_cache
from typing import Any

# Try to import PyICU for advanced collation support
try:
    from icu import Collator as ICUCollator
    from icu import Locale as ICULocale
    from icu import StringSearch as ICUStringSearch
    from icu import (
        UCollAttribute,
        UCollAttributeValue,
        UnicodeString,
        USearchAttribute,
        USearchAttributeValue,
    )

    HAS_PYICU = True
except ImportError:
    HAS_PYICU = False


class Collation(str, Enum):
    """Text comparison collation strategies.

    For most users, use the case_sensitive and accent_sensitive parameters
    in add_property_filter() instead of working with Collation directly.

    Examples:
        # Simple API (recommended for most users):
        searcher.add_property_filter("SUMMARY", "meeting", case_sensitive=False)

        # Advanced API (for power users):
        searcher.add_property_filter("SUMMARY", "Müller",
                                    collation=Collation.LOCALE,
                                    locale="de_DE")
    """

    SIMPLE = "simple"
    """Simple Python-based collation (no PyICU required).

    - case_sensitive=False: Python's str.lower() comparison
    - accent_sensitive=False: combining marks stripped after NFD decomposition
    """

    UNICODE = "unicode"
    """Unicode Collation Algorithm (UCA) root collation.

    Collator strength follows case_sensitive and accent_sensitive, see the
    module documentation.  Requires PyICU to be installed."""

    LOCALE = "locale"
    """Locale-aware collation using CLDR rules.

    Collator strength follows case_sensitive and accent_sensitive, see the
    module documentation.  Requires PyICU to be installed and locale
    parameter."""


class CollationError(Exception):
    """Raised when collation operation cannot be performed."""

    pass


def get_collation_function(
    collation: Collation = Collation.SIMPLE,
    case_sensitive: bool = True,
    locale: str | None = None,
    accent_sensitive: bool = True,
) -> Callable[[str, str], bool]:
    """Get a collation function for substring matching.

    Args:
        collation: The collation strategy to use
        case_sensitive: Whether comparison should be case-sensitive
        locale: Locale string (e.g., "de_DE", "en_US") for LOCALE collation
        accent_sensitive: Whether comparison should be accent-sensitive

    Returns:
        A function that takes (needle, haystack) and returns True if needle
        is found in haystack according to the collation rules.

    Raises:
        CollationError: If PyICU is required but not available, or if
                       invalid parameters are provided.

    Examples:
        >>> match_fn = get_collation_function(Collation.SIMPLE, case_sensitive=False)
        >>> match_fn("test", "This is a TEST")
        True
    """
    if collation == Collation.SIMPLE:
        fold = _simple_fold(case_sensitive, accent_sensitive)
        return lambda needle, haystack: fold(needle) in fold(haystack)
    collator = _icu_collator(collation, case_sensitive, locale, accent_sensitive)
    return lambda needle, haystack: _icu_contains(collator, needle, haystack)


def get_equality_function(
    collation: Collation = Collation.SIMPLE,
    case_sensitive: bool = True,
    locale: str | None = None,
    accent_sensitive: bool = True,
) -> Callable[[str, str], bool]:
    """Get a collation function for equality comparison.

    Takes the same arguments as :func:`get_collation_function`, and returns
    a function that takes two strings and returns True if they are equal
    according to the collation rules.

    Examples:
        >>> eq_fn = get_equality_function(Collation.SIMPLE, case_sensitive=False)
        >>> eq_fn("Test", "TEST")
        True
    """
    key = get_sort_key_function(collation, case_sensitive, locale, accent_sensitive)
    return lambda a, b: key(a) == key(b)


def get_sort_key_function(
    collation: Collation = Collation.SIMPLE,
    case_sensitive: bool = True,
    locale: str | None = None,
    accent_sensitive: bool = True,
) -> Callable[[str], bytes]:
    """Get a collation function for generating sort keys.

    Args:
        collation: The collation strategy to use
        case_sensitive: Whether comparison should be case-sensitive
        locale: Locale string (e.g., "de_DE", "en_US") for LOCALE collation
        accent_sensitive: Whether comparison should be accent-sensitive

    Returns:
        A function that takes a string and returns a sort key (bytes) that
        can be used for sorting according to the collation rules.

    Raises:
        CollationError: If PyICU is required but not available, or if
                       invalid parameters are provided.

    Examples:
        >>> sort_key_fn = get_sort_key_function(Collation.SIMPLE, case_sensitive=False)
        >>> sorted(["Zebra", "apple", "Banana"], key=sort_key_fn)
        ['apple', 'Banana', 'Zebra']
    """
    if collation == Collation.SIMPLE:
        fold = _simple_fold(case_sensitive, accent_sensitive)
        return lambda s: fold(s).encode("utf-8")
    return _icu_collator(collation, case_sensitive, locale, accent_sensitive).getSortKey


# ============================================================================
# Internal implementation functions
# ============================================================================


def _simple_fold(case_sensitive: bool, accent_sensitive: bool) -> Callable[[str], str]:
    """The string normalisation that implements SIMPLE collation."""

    def fold(s: str) -> str:
        if not accent_sensitive:
            s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
        if not case_sensitive:
            s = s.lower()
        return s

    return fold


def _icu_collator(
    collation: Collation, case_sensitive: bool, locale: str | None, accent_sensitive: bool
) -> Any:
    """Validate the ICU collation arguments and return a configured collator."""
    if collation not in (Collation.UNICODE, Collation.LOCALE):
        raise CollationError(f"Unknown collation: {collation}")
    if not HAS_PYICU:
        raise CollationError(
            f"Collation '{collation}' requires PyICU to be installed. "
            "Install with: pip install 'icalendar-searcher[collation]'"
        )
    if collation == Collation.LOCALE:
        if not locale:
            raise CollationError("LOCALE collation requires a locale parameter")
    else:
        # UNICODE collation uses root locale
        locale = None
    return _make_icu_collator(locale, case_sensitive, accent_sensitive)


@lru_cache(maxsize=64)
def _make_icu_collator(locale: str | None, case_sensitive: bool, accent_sensitive: bool) -> Any:
    """Create an ICU collator; cached, as filters ask for one per component.

    PRIMARY compares base letters, SECONDARY adds accents, TERTIARY adds
    case.  Case without accents is PRIMARY with the separate case level.
    """
    icu_locale = ICULocale(locale) if locale else ICULocale.getRoot()
    collator = ICUCollator.createInstance(icu_locale)
    if accent_sensitive:
        collator.setStrength(ICUCollator.TERTIARY if case_sensitive else ICUCollator.SECONDARY)
    else:
        collator.setStrength(ICUCollator.PRIMARY)
        if case_sensitive:
            collator.setAttribute(UCollAttribute.CASE_LEVEL, UCollAttributeValue.ON)
    return collator


def _icu_contains(collator: Any, needle: str, haystack: str) -> bool:
    """Collation-aware substring match on ICU StringSearch."""
    if not needle:
        return True
    if not haystack:
        ## StringSearch refuses an empty text
        return False
    search = ICUStringSearch(needle, haystack, collator)
    if collator.getAttribute(UCollAttribute.CASE_LEVEL) != UCollAttributeValue.ON:
        return search.first() != -1
    ## StringSearch matches on collation elements and ignores CASE_LEVEL,
    ## so each match is checked again with the full collator.  A rejected
    ## match may overlap the right one, and the offsets are UTF-16.
    search.setAttribute(USearchAttribute.OVERLAP, USearchAttributeValue.ON)
    text = UnicodeString(haystack)
    for start in search:
        match = str(text[start : start + search.getMatchedLength()])
        if collator.compare(needle, match) == 0:
            return True
    return False
