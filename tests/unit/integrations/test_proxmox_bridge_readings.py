"""One binding per process for a node's bridge readings, same shape as
``integrations/_base/access.py``: a tool either has it or reports itself
unavailable, and there is exactly one way to set it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from integrations.proxmox import bridge_readings

pytestmark = pytest.mark.unit


async def _reader(node: str) -> Mapping[str, Any]:
    return {"node": node}


@pytest.fixture(autouse=True)
def _clean_binding() -> Iterator[None]:
    bridge_readings.clear()
    yield
    bridge_readings.clear()


def test_nothing_is_bound_by_default() -> None:
    assert bridge_readings.current() is None


def test_bind_makes_current_return_it() -> None:
    bridge_readings.bind(_reader)

    assert bridge_readings.current() is _reader


def test_bind_returns_the_previous_binding() -> None:
    async def other(node: str) -> Mapping[str, Any]:
        return {}

    bridge_readings.bind(_reader)

    previous = bridge_readings.bind(other)

    assert previous is _reader
    assert bridge_readings.current() is other


def test_restore_puts_back_what_bind_replaced() -> None:
    previous = bridge_readings.bind(_reader)

    bridge_readings.restore(previous)

    assert bridge_readings.current() is None


def test_clear_unbinds() -> None:
    bridge_readings.bind(_reader)

    bridge_readings.clear()

    assert bridge_readings.current() is None
