"""``proxmox_node_health``: the three readings the Proxmox API cannot answer,
read through the ``bridge_readings`` binding and reported the way an
investigation reads any tool.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from core.capability.result import CapabilityErrorClass
from integrations.proxmox import bridge_readings
from integrations.proxmox.tools.node_health import proxmox_node_health

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_binding() -> Iterator[None]:
    bridge_readings.clear()
    yield
    bridge_readings.clear()


def _reader(
    published: Mapping[str, Any] = {}, *, fails: bool = False
) -> tuple[bridge_readings.NodeReadings, list[str]]:
    asked: list[str] = []

    async def read(node: str) -> Mapping[str, Any]:
        asked.append(node)
        if fails:
            raise bridge_readings.NodeReadingsUnavailable("connection refused")
        return published

    return read, asked


async def test_an_unbound_bridge_is_reported_as_unavailable_by_name() -> None:
    result = await proxmox_node_health("pve01")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert "metrics" in result.error.message.lower()


async def test_a_bridge_down_is_reported_unhealthy_with_the_bridge_named() -> None:
    reader, _ = _reader({"bridges": {"vmbr0": False}})
    bridge_readings.bind(reader)

    result = await proxmox_node_health("pve01")

    assert result.succeeded
    assert result.value["health"] == "unhealthy"
    assert result.value["signals"]["bridges_down"] == "vmbr0"


async def test_nothing_published_is_reported_unknown_never_healthy() -> None:
    reader, _ = _reader({})
    bridge_readings.bind(reader)

    result = await proxmox_node_health("pve01")

    assert result.succeeded
    assert result.value["health"] == "unknown"


async def test_the_reader_is_asked_about_this_node() -> None:
    reader, asked = _reader({})
    bridge_readings.bind(reader)

    await proxmox_node_health("pve01")

    assert asked == ["pve01"]


async def test_an_unreachable_metrics_system_is_an_upstream_error_not_a_crash() -> None:
    reader, _ = _reader(fails=True)
    bridge_readings.bind(reader)

    result = await proxmox_node_health("pve01")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UPSTREAM_ERROR
