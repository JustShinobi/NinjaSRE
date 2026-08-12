"""Reading resource pressure for a whole estate, from the host's own series.

``pressure.py`` builds the right query and has never had a caller. This is the
source that asks it — the piece between "the query is correct" and "the estate
has a number in it".

**One call per series, not per guest.** Seventy-two guests asked one at a time
would be two hundred and sixteen provider calls a tick. The exporter labels each
series with the guest it is about, so one query with a matcher over the set
returns every guest at once and the source's cost stops depending on how many
resources a detector watches.

**A guest with no answer is absent rather than zero.** A nought that meant "no
data" would fire every below-threshold detector in the deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from integrations.prometheus.pressure_source import PressureSignalSource
from platform.estate.kinds import KIND_CONTAINER
from platform.observation.sources.port import PollBudget

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)


class _Prometheus:
    """Answers a PromQL expression with whatever was recorded for it."""

    def __init__(self, answers: dict[str, list[dict[str, object]]]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    async def evaluate(self, expression: str) -> list[dict[str, object]]:
        self.asked.append(expression)
        return self.answers.get(expression, [])


def _series(guest: str, value: float) -> dict[str, object]:
    return {"metric": {"id": guest}, "value": [1786000000, str(value)]}


async def test_one_call_per_series_covers_every_guest() -> None:
    """The property that keeps the cost independent of the estate's size."""
    prometheus = _Prometheus(
        {
            'pve_cpu_usage_ratio{id=~"lxc/(100|101)"}': [
                _series("lxc/100", 0.25),
                _series("lxc/101", 0.5),
            ]
        }
    )
    source = PressureSignalSource(
        client=prometheus, guests={"res-a": "lxc/100", "res-b": "lxc/101"}
    )

    page = await source.read(
        resource_ids=("res-a", "res-b"), at=NOW, budget=PollBudget(max_provider_calls=10)
    )

    cpu = [r for r in page.readings if r.name == "cpu"]
    assert {r.resource_id: r.value for r in cpu} == {"res-a": 0.25, "res-b": 0.5}
    # One call for this series whatever the number of guests.
    assert sum(1 for asked in prometheus.asked if "pve_cpu_usage_ratio" in asked) == 1


async def test_a_guest_with_no_data_is_absent_rather_than_zero() -> None:
    """A nought that meant "no data" fires every below-threshold detector."""
    prometheus = _Prometheus(
        {'pve_cpu_usage_ratio{id=~"lxc/(100|101)"}': [_series("lxc/100", 0.25)]}
    )
    source = PressureSignalSource(
        client=prometheus, guests={"res-a": "lxc/100", "res-b": "lxc/101"}
    )

    page = await source.read(
        resource_ids=("res-a", "res-b"), at=NOW, budget=PollBudget(max_provider_calls=10)
    )

    assert [r.resource_id for r in page.readings if r.name == "cpu"] == ["res-a"]


async def test_a_resource_nothing_knows_a_guest_id_for_is_not_asked_about() -> None:
    """A matcher built from an empty identity matches every guest on the cluster,
    and the number that comes back is somebody else's."""
    prometheus = _Prometheus({})
    source = PressureSignalSource(client=prometheus, guests={})

    page = await source.read(
        resource_ids=("res-a",), at=NOW, budget=PollBudget(max_provider_calls=10)
    )

    assert page.readings == ()
    assert prometheus.asked == []
    assert page.provider_calls == 0


async def test_the_page_reports_what_it_actually_cost() -> None:
    """The poller rations on this number, so an estimate would ration wrongly."""
    prometheus = _Prometheus({})
    source = PressureSignalSource(client=prometheus, guests={"res-a": "lxc/100"})

    page = await source.read(
        resource_ids=("res-a",), at=NOW, budget=PollBudget(max_provider_calls=10)
    )

    assert page.provider_calls == len(prometheus.asked)


async def test_it_declares_the_signals_it_produces() -> None:
    source = PressureSignalSource(client=_Prometheus({}), guests={})

    assert set(source.declaration.signals) == {"cpu", "memory", "disk"}
    assert source.declaration.source == "prometheus"


async def test_a_kind_with_no_pressure_series_contributes_nothing() -> None:
    """The signal map declines for a kind that has no resource-usage series, and
    declining is the point."""
    source = PressureSignalSource(client=_Prometheus({}), guests={"res-a": ""})

    page = await source.read(
        resource_ids=("res-a",), at=NOW, budget=PollBudget(max_provider_calls=10)
    )

    assert page.readings == ()


def test_the_guest_matcher_is_anchored_to_the_ids_it_was_given() -> None:
    """`id=~"lxc/.+"` would sweep in guests this deployment does not watch."""
    from integrations.prometheus.pressure_source import guest_matcher

    assert guest_matcher(("lxc/100", "lxc/101")) == "lxc/(100|101)"
    assert guest_matcher(("qemu/9000",)) == "qemu/(9000)"
    assert guest_matcher(()) == ""


def test_a_mixed_estate_is_asked_per_prefix() -> None:
    """Containers and virtual machines spell themselves differently, and one
    matcher over both would be a regular expression nobody can read."""
    from integrations.prometheus.pressure_source import guests_by_prefix

    assert guests_by_prefix(("lxc/100", "qemu/9000", "lxc/101")) == {
        "lxc": ("lxc/100", "lxc/101"),
        "qemu": ("qemu/9000",),
    }


def test_the_kind_a_guest_identifier_names_is_the_estate_s_own() -> None:
    from integrations.prometheus.pressure_source import guest_id_for

    assert guest_id_for(KIND_CONTAINER, vmid=100) == "lxc/100"
    assert guest_id_for("node", vmid=0) == ""
