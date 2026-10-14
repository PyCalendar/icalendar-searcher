"""The two collation axes: case sensitivity and accent sensitivity.

``case_sensitive`` and ``accent_sensitive`` are independent.  Under the ICU
collations they map onto collator strength and ``CASE_LEVEL``; under
``Collation.SIMPLE`` accents are folded by stripping combining marks after
NFD decomposition.  ``contains`` and ``==`` (and their negations) must agree
with each other, also for ``category``/``categories``.
"""

from __future__ import annotations

import pytest
from icalendar import Event

from icalendar_searcher import Collation, Searcher
from icalendar_searcher.collation import (
    HAS_PYICU,
    get_collation_function,
    get_equality_function,
    get_sort_key_function,
)

needs_icu = pytest.mark.skipif(not HAS_PYICU, reason="PyICU not installed")

## (case_sensitive, accent_sensitive) shorthands
CS_AS = (True, True)
CI_AS = (False, True)
CI_AI = (False, False)
CS_AI = (True, False)


def _event(summary: str, categories: list[str] | None = None) -> Event:
    event = Event()
    event.add("uid", "1")
    event.add("summary", summary)
    if categories:
        event.add("categories", categories)
    return event


## needle, haystack, locale (None = root), axes, expected
ICU_CONTAINS = [
    ## de_DE: ü is an accented u
    ("muller", "Herr Müller", "de_DE", CS_AS, False),
    ("muller", "Herr Müller", "de_DE", CI_AS, False),
    ("muller", "Herr Müller", "de_DE", CI_AI, True),
    ("muller", "Herr Müller", "de_DE", CS_AI, False),
    ("Muller", "Herr Müller", "de_DE", CS_AI, True),
    ("müller", "Herr Müller", "de_DE", CI_AS, True),
    ("müller", "Herr Müller", "de_DE", CS_AS, False),
    ("Müller", "Herr Müller", "de_DE", CS_AS, True),
    ## root behaves the same for ü
    ("muller", "Herr Müller", None, CI_AI, True),
    ("muller", "Herr Müller", None, CI_AS, False),
    ## tr_TR: İ is the capital of i, not an I with a dot
    ("istanbul", "İstanbul'da", "tr_TR", CI_AS, True),
    ("istanbul", "İstanbul'da", "tr_TR", CS_AS, False),
    ("istanbul", "İstanbul'da", "tr_TR", CS_AI, False),
    ("istanbul", "İstanbul'da", None, CI_AI, True),
    ## Scandinavian: å, æ/ä and ø/ö are letters of their own, not decorated
    ## a and o; root folds æ to "ae"
    ("smorgasbord", "et smörgåsbord", "nb_NO", CI_AI, False),
    ("smorgasbord", "et smörgåsbord", "sv_SE", CI_AI, False),
    ("smorgasbord", "et smörgåsbord", None, CI_AI, True),
    ("blabaersyltetoy", "Blåbærsyltetøy", "nb_NO", CI_AI, False),
    ("blabaersyltetoy", "Blåbærsyltetøy", "da_DK", CI_AI, False),
    ("blabaersyltetoy", "Blåbærsyltetøy", None, CI_AI, True),
    ("blabarsyltetoy", "Blåbærsyltetøy", None, CI_AI, False),
    ("smørbrød", "Smørbrød", "nb_NO", CI_AS, True),
    ("smorbrod", "Smørbrød", "nb_NO", CI_AI, False),
    ## no match at all
    ("tennis", "Herr Müller", None, CI_AI, False),
    ## case-only re-check: astral characters before the match (UTF-16
    ## offsets), and a match overlapping a rejected one
    ("Muller", "😀😀 Müller", None, CS_AI, True),
    ("muller", "😀😀 Müller", None, CS_AI, False),
    ("aA", "aaA", None, CS_AI, True),
    ## degenerate inputs
    ("", "anything", None, CI_AI, True),
    ("x", "", None, CI_AI, False),
    ("", "", None, CS_AS, True),
]


@needs_icu
@pytest.mark.parametrize("needle,haystack,locale,axes,expected", ICU_CONTAINS)
def test_icu_contains(
    needle: str, haystack: str, locale: str | None, axes: tuple[bool, bool], expected: bool
) -> None:
    collation = Collation.LOCALE if locale else Collation.UNICODE
    fn = get_collation_function(collation, axes[0], locale, accent_sensitive=axes[1])
    assert fn(needle, haystack) is expected


## a, b, locale, axes, expected
ICU_EQUALS = [
    ("muller", "Müller", "de_DE", CS_AS, False),
    ("muller", "Müller", "de_DE", CI_AS, False),
    ("muller", "Müller", "de_DE", CI_AI, True),
    ("muller", "Müller", "de_DE", CS_AI, False),
    ("Muller", "Müller", "de_DE", CS_AI, True),
    ("MÜLLER", "Müller", "de_DE", CI_AS, True),
    ("istanbul", "İstanbul", "tr_TR", CI_AS, True),
    ("smorgasbord", "smörgåsbord", "nb_NO", CI_AI, False),
    ("smorgasbord", "smörgåsbord", None, CI_AI, True),
]


@needs_icu
@pytest.mark.parametrize("a,b,locale,axes,expected", ICU_EQUALS)
def test_icu_equals(
    a: str, b: str, locale: str | None, axes: tuple[bool, bool], expected: bool
) -> None:
    collation = Collation.LOCALE if locale else Collation.UNICODE
    fn = get_equality_function(collation, axes[0], locale, accent_sensitive=axes[1])
    assert fn(a, b) is expected


SIMPLE_CONTAINS = [
    ("muller", "Herr Müller", CS_AS, False),
    ("muller", "Herr Müller", CI_AS, False),
    ("muller", "Herr Müller", CI_AI, True),
    ("muller", "Herr Müller", CS_AI, False),
    ("Muller", "Herr Müller", CS_AI, True),
    ## decomposed ü
    ("Muller", "Herr Mu\u0308ller", CS_AI, True),
    ## ø has no decomposition, so SIMPLE cannot fold it
    ("smorbrod", "Smørbrød", CI_AI, False),
]


@pytest.mark.parametrize("needle,haystack,axes,expected", SIMPLE_CONTAINS)
def test_simple_contains(
    needle: str, haystack: str, axes: tuple[bool, bool], expected: bool
) -> None:
    fn = get_collation_function(Collation.SIMPLE, axes[0], accent_sensitive=axes[1])
    assert fn(needle, haystack) is expected


@pytest.mark.parametrize(
    "a,b,axes,expected",
    [
        ("muller", "Müller", CI_AS, False),
        ("muller", "Müller", CI_AI, True),
        ("Muller", "Müller", CS_AI, True),
        ("muller", "Müller", CS_AI, False),
        ("MÜLLER", "Müller", CI_AS, True),
    ],
)
def test_simple_equals(a: str, b: str, axes: tuple[bool, bool], expected: bool) -> None:
    fn = get_equality_function(Collation.SIMPLE, axes[0], accent_sensitive=axes[1])
    assert fn(a, b) is expected


def test_default_is_accent_sensitive() -> None:
    """Leaving accent_sensitive out keeps the 1.1 behaviour."""
    searcher = Searcher(event=True)
    searcher.add_property_filter("SUMMARY", "muller", operator="contains", case_sensitive=False)
    assert not searcher.check_component(_event("Herr Müller"))


def test_searcher_accent_insensitive_simple() -> None:
    searcher = Searcher(event=True)
    searcher.add_property_filter(
        "SUMMARY", "muller", operator="contains", case_sensitive=False, accent_sensitive=False
    )
    assert searcher.check_component(_event("Herr Müller"))


@needs_icu
@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("contains", "muller", True),
        ("!contains", "muller", False),
        ("==", "herr muller", True),
        ("!=", "herr muller", False),
        ("==", "muller", False),
        ("!=", "muller", True),
    ],
)
def test_searcher_operators_agree(operator: str, value: str, expected: bool) -> None:
    """contains, == and their negations all use the same collator."""
    searcher = Searcher(event=True)
    searcher.add_property_filter(
        "SUMMARY",
        value,
        operator=operator,
        collation=Collation.LOCALE,
        locale="de_DE",
        case_sensitive=False,
        accent_sensitive=False,
    )
    assert bool(searcher.check_component(_event("Herr Müller"))) is expected


@needs_icu
@pytest.mark.parametrize(
    "key,operator,value,locale,axes,expected",
    [
        ## plural: whole tokens, compared under the collation
        ("categories", "contains", "istanbul", "tr_TR", CI_AS, True),
        ("categories", "contains", "istanbul", "tr_TR", CS_AS, False),
        ("categories", "==", "istanbul,müller", "tr_TR", CI_AS, True),
        ("categories", "==", "istanbul,muller", "tr_TR", CI_AS, False),
        ## ü is a letter of its own in Turkish, an accented u in German
        ("categories", "==", "istanbul,muller", "tr_TR", CI_AI, False),
        ("categories", "==", "istanbul,muller", "de_DE", CI_AI, True),
        ("categories", "!=", "istanbul,muller", "de_DE", CI_AI, False),
        ("categories", "!=", "istanbul,muller", "de_DE", CI_AS, True),
        ## singular: substring within a token, or a whole token
        ("category", "contains", "mull", "de_DE", CI_AI, True),
        ("category", "contains", "mull", "tr_TR", CI_AI, False),
        ("category", "==", "muller", "de_DE", CI_AI, True),
        ("category", "==", "muller", "de_DE", CI_AS, False),
        ("category", "!=", "muller", "de_DE", CI_AI, False),
        ## I is the capital of ı, not of i, in Turkish
        ("category", "==", "ISTANBUL", "tr_TR", CI_AS, False),
        ("category", "==", "İSTANBUL", "tr_TR", CI_AS, True),
    ],
)
def test_categories_honour_collation(
    key: str, operator: str, value: str, locale: str, axes: tuple[bool, bool], expected: bool
) -> None:
    searcher = Searcher(event=True)
    searcher.add_property_filter(
        key,
        value,
        operator=operator,
        collation=Collation.LOCALE,
        locale=locale,
        case_sensitive=axes[0],
        accent_sensitive=axes[1],
    )
    event = _event("x", categories=["İstanbul", "Müller"])
    assert bool(searcher.check_component(event)) is expected


@needs_icu
def test_sort_key_accent_insensitive() -> None:
    fn = get_sort_key_function(Collation.UNICODE, False, accent_sensitive=False)
    assert fn("Müller") == fn("muller")
    fn = get_sort_key_function(Collation.UNICODE, False)
    assert fn("Müller") != fn("muller")


def test_sort_accent_insensitive_simple() -> None:
    searcher = Searcher(event=True)
    searcher.add_sort_key("SUMMARY", case_sensitive=False, accent_sensitive=False)
    events = [_event(s) for s in ("Mz", "Mü", "Ma")]
    assert [str(e["summary"]) for e in searcher.sort(events)] == ["Ma", "Mü", "Mz"]
