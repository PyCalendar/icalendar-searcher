"""Tests for what the package ships beside its code."""

from importlib.resources import files


def test_ships_py_typed_marker() -> None:
    """PEP 561: without py.typed, type checkers skip the package's annotations."""
    assert files("icalendar_searcher").joinpath("py.typed").is_file()
