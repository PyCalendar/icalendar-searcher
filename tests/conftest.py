"""Shared test fixtures."""

import os
import time
from collections.abc import Iterator

import pytest

PROCESS_TIMEZONES = ["Europe/Berlin", "UTC", "America/New_York", "Asia/Tokyo"]


@pytest.fixture(params=PROCESS_TIMEZONES)
def process_tz(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run the test with the process local time zone set to each of PROCESS_TIMEZONES."""
    orig = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield request.param
    finally:
        if orig is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = orig
        time.tzset()
