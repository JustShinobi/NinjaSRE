"""The scheduled job that fills the estate's signals.

The last unconnected link in the chain: ``OBSERVATION_TICK_JOB_KIND`` exists,
``tick_job`` builds a job of that kind, ``ObservationTickRunner`` polls sources
and stores what they say — and nothing dispatched the kind, so a deployment with
a metrics system configured had every number it needed one call away and no
number in it.

The guests map is built here rather than at composition because it needs two
things that live apart: the estate's resources, which change every sweep, and
the exporter's spelling of a guest, which the integration owns.
"""

from __future__ import annotations

import pytest

from gateway.http.observation_job import guests_of

pytestmark = pytest.mark.unit


class _Resource:
    def __init__(self, resource_id: str, kind: str, vmid: object = None) -> None:
        self.resource_id = resource_id
        self.kind = kind
        self.attributes = {} if vmid is None else {"vmid": vmid}


def test_a_guest_maps_to_the_identifier_its_host_publishes_it_under() -> None:
    from platform.estate.kinds import KIND_CONTAINER, KIND_VIRTUAL_MACHINE

    mapped = guests_of(
        (
            _Resource("res-a", KIND_CONTAINER, 100),
            _Resource("res-b", KIND_VIRTUAL_MACHINE, 9000),
        )
    )

    assert mapped == {"res-a": "lxc/100", "res-b": "qemu/9000"}


def test_a_resource_with_no_vmid_is_left_out_rather_than_guessed() -> None:
    """A matcher built from an empty identity matches every guest on the
    cluster, and the number that comes back belongs to somebody else."""
    from platform.estate.kinds import KIND_CONTAINER

    assert guests_of((_Resource("res-a", KIND_CONTAINER),)) == {}


def test_a_kind_the_host_publishes_no_guest_series_for_is_left_out() -> None:
    """A node is the host. Its own series are a different shape."""
    assert guests_of((_Resource("res-a", "node", 0),)) == {}


def test_a_vmid_that_is_not_a_number_is_left_out_rather_than_raised() -> None:
    """An attribute an integration wrote is not a schema this can rely on."""
    from platform.estate.kinds import KIND_CONTAINER

    assert guests_of((_Resource("res-a", KIND_CONTAINER, "not a number"),)) == {}


def test_the_observation_tick_kind_is_dispatched() -> None:
    """The defect: the kind was registerable and no runner answered it."""
    from config.constants.observation import OBSERVATION_TICK_JOB_KIND
    from gateway.http.scheduled_work import dispatcher_for

    class _State:
        gateway = object()
        estate_kinds = ()
        knowledge_sources: dict[str, object] = {}
        corpus_sources: dict[str, object] = {}
        discovery_sources: dict[str, object] = {}
        enrichment_plans: dict[str, object] = {}
        signal_sources: tuple[object, ...] = ()
        guardrails = None

    assert OBSERVATION_TICK_JOB_KIND in dispatcher_for(_State()).kinds  # type: ignore[arg-type]


async def test_composing_a_metrics_client_also_schedules_the_tick_that_uses_it() -> None:
    """tick_job builds the recurring job and had no caller, so a deployment that
    composed a metrics client still polled nothing.

    Registered where the client is composed, because those are one decision: a
    deployment pointed at a metrics system is one that wants its numbers.
    """
    from config.constants.observation import OBSERVATION_TICK_JOB_KIND
    from gateway.http.discovery_sources import schedule_observation_tick

    class _Schedules:
        def __init__(self) -> None:
            self.upserted: list[object] = []

        async def upsert_job(self, job: object) -> object:
            self.upserted.append(job)
            return job

    schedules = _Schedules()

    class _Uow:
        def __init__(self) -> None:
            self.schedules = schedules

        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    class _Gateway:
        def begin(self, _scope: object) -> object:
            return _Uow()

    class _State:
        gateway = _Gateway()

    await schedule_observation_tick(_State(), org_id="acme")  # type: ignore[arg-type]

    assert [job.kind for job in schedules.upserted] == [OBSERVATION_TICK_JOB_KIND]
