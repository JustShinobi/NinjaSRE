"""Which source answers which question about one resource, and by what key.

The failure this exists to stop is not that an investigation cannot find a
number. It is that it finds the *wrong* number and reports it with confidence.

An LXC container shares its host's kernel. Counters read from inside it describe
the host's cgroup accounting through a namespace that was never designed to
report it, so "how much memory is this container using" answered from inside is
answered wrongly — plausibly, consistently, and by a tool that returned 200. The
correct answer is the host's own series for that guest, keyed by its numeric
identifier. That is a rule about correctness rather than about configuration,
and it belongs somewhere it can be tested rather than in a docstring.

The other half is the absences. A question with no configured source resolves to
a named gap rather than to nothing: "no log store is configured — loki or
openobserve would answer this" is a sentence an operator can act on, and an
empty field is a sentence that reads as "there are no logs".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.signals import (
    SIGNAL_KEY_INSTANCE,
    SIGNAL_KEY_NAME,
    SIGNAL_KEY_VMID,
    SIGNAL_QUESTION_DASHBOARDS,
    SIGNAL_QUESTION_FIRING,
    SIGNAL_QUESTION_LOGS,
    SIGNAL_QUESTION_PRESSURE,
    SIGNAL_QUESTION_TRACES,
    SIGNAL_QUESTION_UP,
    SIGNAL_QUESTIONS,
)
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
)
from platform.estate.signal_map import signal_map_for
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

SEEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

#: The six the specification names, plus the hypervisor that discovered the
#: estate in the first place — "is it up" is answered by whatever declares the
#: resource exists, so a deployment without it is a deployment that cannot say.
EVERYTHING = (
    "proxmox",
    "prometheus",
    "alertmanager",
    "grafana",
    "loki",
    "openobserve",
    "signoz",
)


def container(**attributes: object) -> Resource:
    """Return the AdGuard container as the estate holds it."""
    return Resource(
        resource_id="prox-ct-100",
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id="lxc/HAL9000/2025-01-01/100",
        display_name="adguard",
        correlation_key="HAL9000/lxc/100",
        attributes={"vmid": 100, "address": "10.20.20.4", **attributes},
        last_seen_at=SEEN,
    )


def node() -> Resource:
    return Resource(
        resource_id="prox-node-pve01",
        kind=KIND_NODE,
        source="proxmox",
        native_id="node/HAL9000/pve01",
        display_name="pve01",
        attributes={"address": "10.20.10.11"},
        last_seen_at=SEEN,
    )


def datastore() -> Resource:
    return Resource(
        resource_id="prox-store-local",
        kind=KIND_DATASTORE,
        source="proxmox",
        native_id="store/HAL9000/local",
        display_name="local",
        attributes={},
        last_seen_at=SEEN,
    )


# --- the rule that makes this feature worth having ------------------------------


class TestPressureOnAContainerComesFromTheHost:
    def test_it_resolves_to_prometheus_keyed_by_the_guests_own_identifier(self) -> None:
        found = signal_map_for(container(), configured=EVERYTHING)
        pressure = found.source_for(SIGNAL_QUESTION_PRESSURE)

        assert pressure is not None
        assert pressure.integration == "prometheus"
        assert pressure.keyed_by == SIGNAL_KEY_VMID
        assert pressure.key == "100"

    def test_the_entry_says_why_it_is_the_host_and_not_the_guest(self) -> None:
        """A rule nobody can read is a rule the next change deletes."""
        pressure = signal_map_for(container(), configured=EVERYTHING).source_for(
            SIGNAL_QUESTION_PRESSURE
        )

        assert pressure is not None
        assert "kernel" in pressure.detail
        assert "host" in pressure.detail

    def test_a_virtual_machine_is_keyed_the_same_way(self) -> None:
        guest = Resource(
            resource_id="prox-vm-201",
            kind=KIND_VIRTUAL_MACHINE,
            source="proxmox",
            native_id="qemu/HAL9000/2025-01-01/201",
            display_name="build",
            attributes={"vmid": 201, "address": "10.20.30.7"},
            last_seen_at=SEEN,
        )

        pressure = signal_map_for(guest, configured=EVERYTHING).source_for(SIGNAL_QUESTION_PRESSURE)

        assert pressure is not None
        assert pressure.keyed_by == SIGNAL_KEY_VMID
        assert pressure.key == "201"

    def test_a_node_is_keyed_by_its_address_because_it_is_the_host(self) -> None:
        pressure = signal_map_for(node(), configured=EVERYTHING).source_for(
            SIGNAL_QUESTION_PRESSURE
        )

        assert pressure is not None
        assert pressure.keyed_by == SIGNAL_KEY_INSTANCE
        assert pressure.key == "10.20.10.11"


def test_pressure_for_a_guest_with_no_identifier_is_a_named_gap() -> None:
    """Not a query built on an empty key: that returns an empty result and reads
    as a container under no pressure at all. A resource swept before ``vmid`` was
    declared is exactly this case."""
    unkeyed = Resource(
        resource_id="prox-ct-999",
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id="lxc/HAL9000/2025-01-01/999",
        display_name="mystery",
        attributes={"address": "10.20.20.9"},
        last_seen_at=SEEN,
    )

    found = signal_map_for(unkeyed, configured=EVERYTHING)

    assert found.source_for(SIGNAL_QUESTION_PRESSURE) is None
    gap = found.missing_for(SIGNAL_QUESTION_PRESSURE)
    assert gap is not None
    assert "vmid" in gap.why


# --- the other five questions ---------------------------------------------------


def test_up_is_answered_by_whatever_declares_the_resource_exists() -> None:
    """Not a rule naming Proxmox: the integration that discovered a resource is
    the one that reports its state, whatever provider it happens to be."""
    found = signal_map_for(container(), configured=EVERYTHING)
    up = found.source_for(SIGNAL_QUESTION_UP)

    assert up is not None
    assert up.integration == "proxmox"


def test_up_is_keyed_by_the_resource_s_own_name_not_its_internal_identity() -> None:
    """``keyed_by`` says "name", so the value has to be one — not the internal
    identity a discovery source uses for reconciliation. A guest with no
    recorded creation time carries a placeholder discriminator in that identity
    (see ``integrations.proxmox.identity.NO_DISCRIMINATOR``), and that
    placeholder must never reach a surface as part of what looks like the
    resource's own key."""
    guest = Resource(
        resource_id="prox-ct-111",
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id="lxc/HAL9000/unknown/111",
        display_name="signoz",
        attributes={"vmid": 111, "address": "10.20.20.5"},
        last_seen_at=SEEN,
    )

    up = signal_map_for(guest, configured=EVERYTHING).source_for(SIGNAL_QUESTION_UP)

    assert up is not None
    assert up.key == "signoz"
    assert "unknown" not in up.key


class TestTheRestOfTheMap:
    def test_logs_prefer_loki_and_fall_back_to_the_next_configured_store(self) -> None:
        both = signal_map_for(container(), configured=EVERYTHING)
        assert both.source_for(SIGNAL_QUESTION_LOGS).integration == "loki"  # type: ignore[union-attr]

        one = signal_map_for(container(), configured=("proxmox", "openobserve"))
        logs = one.source_for(SIGNAL_QUESTION_LOGS)
        assert logs is not None
        assert logs.integration == "openobserve"
        assert logs.keyed_by == SIGNAL_KEY_NAME
        assert logs.key == "adguard"

    def test_traces_firing_and_dashboards_resolve_to_their_own_vendors(self) -> None:
        found = signal_map_for(container(), configured=EVERYTHING)

        assert found.source_for(SIGNAL_QUESTION_TRACES).integration == "signoz"  # type: ignore[union-attr]
        assert found.source_for(SIGNAL_QUESTION_FIRING).integration == "alertmanager"  # type: ignore[union-attr]
        assert found.source_for(SIGNAL_QUESTION_DASHBOARDS).integration == "grafana"  # type: ignore[union-attr]

    def test_every_question_is_either_answered_or_named_exactly_once(self) -> None:
        found = signal_map_for(container(), configured=("proxmox",))

        answered = {source.question for source in found.sources}
        named = {gap.question for gap in found.missing}
        assert answered | named == set(SIGNAL_QUESTIONS)
        assert answered & named == set()


class TestAnAbsenceIsNamedRatherThanBlank:
    def test_an_unconfigured_question_names_what_would_answer_it(self) -> None:
        found = signal_map_for(container(), configured=("proxmox",))
        gap = found.missing_for(SIGNAL_QUESTION_LOGS)

        assert gap is not None
        assert gap.wanted == ("loki", "openobserve")
        assert "loki" in gap.why and "openobserve" in gap.why

    def test_a_resource_whose_own_source_went_away_says_that(self) -> None:
        found = signal_map_for(container(), configured=("loki",))
        gap = found.missing_for(SIGNAL_QUESTION_UP)

        assert gap is not None
        assert gap.wanted == ("proxmox",)

    def test_a_question_that_does_not_apply_to_this_kind_is_still_accounted_for(self) -> None:
        """A datastore has no pressure series of its own here, and saying nothing
        about it would leave the page with a blank nobody can interpret."""
        found = signal_map_for(datastore(), configured=EVERYTHING)

        assert found.source_for(SIGNAL_QUESTION_PRESSURE) is None
        assert found.missing_for(SIGNAL_QUESTION_PRESSURE) is not None


# --- what acceptance 3 asks for -------------------------------------------------


@pytest.mark.parametrize("resource", [container(), node(), datastore()])
def test_every_resource_answers_or_names_up_and_logs(resource: Resource) -> None:
    found = signal_map_for(resource, configured=EVERYTHING)

    assert found.answers(SIGNAL_QUESTION_UP)
    assert found.answers(SIGNAL_QUESTION_LOGS)


@pytest.mark.parametrize("resource", [container(), node(), datastore()])
def test_with_nothing_configured_up_and_logs_are_named_gaps_rather_than_silence(
    resource: Resource,
) -> None:
    found = signal_map_for(resource, configured=())

    assert not found.answers(SIGNAL_QUESTION_UP)
    for question in (SIGNAL_QUESTION_UP, SIGNAL_QUESTION_LOGS):
        gap = found.missing_for(question)
        assert gap is not None
        assert gap.wanted, f"{question}: a gap that names nothing is a blank with a schema"
        assert gap.why.strip()


class TestTheRecordASurfaceRenders:
    def test_it_carries_every_question_with_its_answer_or_its_absence(self) -> None:
        record = signal_map_for(container(), configured=EVERYTHING).to_record()

        assert record["resource_id"] == "prox-ct-100"
        by_question = {entry["question"]: entry for entry in record["sources"]}  # type: ignore[union-attr,index]
        assert set(by_question) | {
            entry["question"]  # type: ignore[index]
            for entry in record["missing"]  # type: ignore[union-attr]
        } == set(SIGNAL_QUESTIONS)
        assert by_question[SIGNAL_QUESTION_PRESSURE]["keyed_by"] == SIGNAL_KEY_VMID
        assert by_question[SIGNAL_QUESTION_PRESSURE]["key"] == "100"

    def test_it_holds_no_credential_and_nothing_a_vendor_would_reject(self) -> None:
        record = signal_map_for(container(), configured=EVERYTHING).to_record()

        assert "token" not in repr(record)
        assert "password" not in repr(record)
