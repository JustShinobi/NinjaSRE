"""Contract: incidents, and the four things a backend must never get wrong.

``open_for`` returns the *live* incident for a cause and never a closed one, the
timeline is append-only and reads oldest first, retention removes closed
incidents and only closed ones, and one tenant's incidents are invisible from
another.

The first is the one everything else rests on. A store whose correlation lookup
could return a resolved incident would revive last week's history every time a
condition recurred, and the recurrence — the thing anybody actually wants to
know about — would have no timestamp of its own.
"""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import (
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    PersistenceGateway,
    TenantScope,
    TimelineEntry,
    TimelineKind,
)
from platform.persistence.ports.incident_store import (
    incident_key,
    public_incident_id,
    timeline_key,
)

pytestmark = pytest.mark.contract


def incident(
    *,
    correlation_key: str = "detector:datastore-near-full",
    minutes: float = 0.0,
    state: IncidentState = IncidentState.OPEN,
    subjects: tuple[str, ...] = ("store-cove",),
    severity: str = "critical",
    team_node_id: str = "team-payments",
    closed: float | None = None,
) -> Incident:
    """Return one incident as the lifecycle would construct it."""
    internal_id = incident_key(correlation_key, at(minutes))
    return Incident(
        incident_id=internal_id,
        correlation_key=correlation_key,
        title="Datastore near full",
        summary="store-cove is 95.65% full",
        origin=IncidentOrigin.DETECTOR,
        origin_id="datastore-near-full",
        severity=severity,
        state=state,
        opened_at=at(minutes),
        subjects=tuple(
            IncidentSubject(
                resource_id=resource_id,
                detail=f"{resource_id} is 95.65% full",
                evidence={"used_percent": "95.65"},
                observed_at=at(minutes),
            )
            for resource_id in subjects
        ),
        closed_at=None if closed is None else at(closed),
        team_node_id=team_node_id,
        public_id=public_incident_id(internal_id),
    )


def entry(
    incident_id: str,
    kind: TimelineKind = TimelineKind.OPENED,
    *,
    minutes: float = 0.0,
    actor: str = "system:observation",
    cause: str = "the condition held for its declared duration",
    query: str = "",
    result: str = "",
) -> TimelineEntry:
    """Return one timeline entry."""
    return TimelineEntry(
        entry_id=timeline_key(incident_id, kind, at(minutes)),
        incident_id=incident_id,
        kind=kind,
        at=at(minutes),
        actor=actor,
        cause=cause,
        query=query,
        result=result,
    )


# --- Evidence is structural -------------------------------------------------------


def test_an_incident_with_nothing_to_point_at_cannot_be_constructed() -> None:
    """Article I, in the type: a conclusion carries the observations behind it."""
    with pytest.raises(ValueError, match="at least one subject"):
        Incident(
            incident_id="i-1",
            correlation_key="k",
            title="t",
            summary="s",
            origin=IncidentOrigin.DETECTOR,
            origin_id="d",
            severity="high",
            state=IncidentState.OPEN,
            opened_at=at(),
            subjects=(),
            public_id=public_incident_id("i-1"),
        )


def test_an_incident_without_a_correlation_key_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="correlation key"):
        Incident(
            incident_id="i-1",
            correlation_key="",
            title="t",
            summary="s",
            origin=IncidentOrigin.DETECTOR,
            origin_id="d",
            severity="high",
            state=IncidentState.OPEN,
            opened_at=at(),
            subjects=(IncidentSubject(resource_id="r"),),
            public_id=public_incident_id("i-1"),
        )


# --- Correlation ------------------------------------------------------------------


async def test_the_live_incident_for_a_cause_is_the_one_returned(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(minutes=0))

        found = await uow.incidents.open_for("detector:datastore-near-full")

    assert found is not None
    assert found.state is IncidentState.OPEN


async def test_a_closed_incident_is_never_returned_as_the_live_one(
    gateway: PersistenceGateway,
) -> None:
    """A recurrence must open its own incident rather than revive last week's."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(minutes=0, state=IncidentState.RESOLVED, closed=10))

        assert await uow.incidents.open_for("detector:datastore-near-full") is None


async def test_a_recurrence_after_a_resolution_is_a_second_incident(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(minutes=0, state=IncidentState.RESOLVED, closed=10))
        await uow.incidents.upsert(incident(minutes=60))

        both = await uow.incidents.query(IncidentQuery())
        live = await uow.incidents.open_for("detector:datastore-near-full")

    assert len(both) == 2
    assert live is not None
    assert live.opened_at == at(60)


async def test_one_incident_carries_every_subject_rather_than_a_count(
    gateway: PersistenceGateway,
) -> None:
    subjects = tuple(f"ct-{index:03d}" for index in range(50))
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(subjects=subjects))

        stored = await uow.incidents.open_for("detector:datastore-near-full")

    assert stored is not None
    assert stored.subject_ids == subjects


# --- Listing ------------------------------------------------------------------------


async def test_a_listing_comes_back_most_recently_opened_first(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(correlation_key="a", minutes=0))
        await uow.incidents.upsert(incident(correlation_key="b", minutes=30))
        await uow.incidents.upsert(incident(correlation_key="c", minutes=15))

        listed = await uow.incidents.query(IncidentQuery())

    assert [entry.opened_at for entry in listed] == [at(30), at(15), at(0)]


async def test_a_listing_filters_by_state_severity_team_and_subject(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(incident(correlation_key="a", subjects=("store-cove",)))
        await uow.incidents.upsert(
            incident(
                correlation_key="b",
                subjects=("store-ridge",),
                severity="low",
                state=IncidentState.RESOLVED,
                closed=1,
                team_node_id="team-search",
            )
        )

        live = await uow.incidents.query(IncidentQuery(live_only=True))
        low = await uow.incidents.query(IncidentQuery(severities=("low",)))
        team = await uow.incidents.query(IncidentQuery(team_node_id="team-search"))
        subject = await uow.incidents.query(IncidentQuery(subject_id="store-cove"))

    assert [entry.correlation_key for entry in live] == ["a"]
    assert [entry.correlation_key for entry in low] == ["b"]
    assert [entry.correlation_key for entry in team] == ["b"]
    assert [entry.correlation_key for entry in subject] == ["a"]


async def test_a_listing_above_the_page_bound_is_refused(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        with pytest.raises(BoundExceeded, match="MAX_INCIDENT_PAGE_SIZE"):
            await uow.incidents.query(IncidentQuery(limit=100_000))


# --- The timeline ---------------------------------------------------------------------


async def test_a_timeline_reads_oldest_first(gateway: PersistenceGateway) -> None:
    """A narrative told backwards is not one."""
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append(
            (
                entry(stored.incident_id, TimelineKind.CLOSED, minutes=10),
                entry(stored.incident_id, TimelineKind.OPENED, minutes=0),
                entry(stored.incident_id, TimelineKind.RUN_STARTED, minutes=1),
            )
        )

        history = await uow.incidents.timeline(stored.incident_id)

    assert [item.kind for item in history] == [
        TimelineKind.OPENED,
        TimelineKind.RUN_STARTED,
        TimelineKind.CLOSED,
    ]


async def test_appending_the_same_entry_twice_is_one_entry(
    gateway: PersistenceGateway,
) -> None:
    """A retried transition must not double-record: a timeline that does is untrusted."""
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append((entry(stored.incident_id),))
        await uow.incidents.append((entry(stored.incident_id),))

        history = await uow.incidents.timeline(stored.incident_id)

    assert len(history) == 1


async def test_every_entry_names_an_actor_and_a_cause(
    gateway: PersistenceGateway,
) -> None:
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append(
            (entry(stored.incident_id, actor="ada@example.test", cause="it was noise"),)
        )

        history = await uow.incidents.timeline(stored.incident_id)

    assert history[0].actor == "ada@example.test"
    assert history[0].cause == "it was noise"


async def test_an_evidence_entrys_query_and_result_survive_the_round_trip(
    gateway: PersistenceGateway,
) -> None:
    """Both are asserted, separately: an entry carrying one without the other
    must fail this claim rather than pass it looking at only one field.
    """
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append(
            (
                entry(
                    stored.incident_id,
                    TimelineKind.EVIDENCE,
                    minutes=1,
                    cause="cedar has not answered its own probe in 6 minutes",
                    query='up{instance="cedar"}',
                    result="0 (last seen 1 at 06:41 UTC, 6m ago)",
                ),
            )
        )

        history = await uow.incidents.timeline(stored.incident_id)

    assert len(history) == 1
    assert history[0].kind is TimelineKind.EVIDENCE
    assert history[0].query == 'up{instance="cedar"}'
    assert history[0].result == "0 (last seen 1 at 06:41 UTC, 6m ago)"


async def test_a_lifecycle_entrys_query_and_result_are_empty_not_absent(
    gateway: PersistenceGateway,
) -> None:
    """Every entry has somewhere to carry them; a lifecycle entry just carries
    nothing there, the same as it already does for an unused ``detail``.
    """
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append((entry(stored.incident_id, TimelineKind.OPENED),))

        history = await uow.incidents.timeline(stored.incident_id)

    assert history[0].query == ""
    assert history[0].result == ""


async def test_all_five_reasoning_kinds_round_trip_through_the_store(
    gateway: PersistenceGateway,
) -> None:
    """The four reasoning kinds the evidence round-trip above did not exercise.

    ``IncidentLifecycle``'s reasoning-recording methods are thin wrappers over
    exactly this ``append``/``timeline`` pair — this is the backend claim
    underneath every one of them, kind by kind, rather than trusting that
    ``EVIDENCE`` (already covered above) stands in for the other four.
    """
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append(
            (
                entry(
                    stored.incident_id,
                    TimelineKind.ALERT_RECEIVED,
                    minutes=1,
                    cause="the delivery was authenticated by delivery token am-cluster",
                ),
                entry(
                    stored.incident_id,
                    TimelineKind.HYPOTHESES_DRAWN,
                    minutes=2,
                    cause="the datastore is over-provisioned; a snapshot is holding blocks",
                ),
                entry(
                    stored.incident_id,
                    TimelineKind.DIAGNOSIS,
                    minutes=3,
                    cause="a snapshot from last Tuesday is holding the freed blocks",
                ),
                entry(
                    stored.incident_id,
                    TimelineKind.REPORT_DELIVERED,
                    minutes=4,
                    cause="the investigation's report was delivered",
                ),
            )
        )

        history = await uow.incidents.timeline(stored.incident_id)

    assert [item.kind for item in history] == [
        TimelineKind.ALERT_RECEIVED,
        TimelineKind.HYPOTHESES_DRAWN,
        TimelineKind.DIAGNOSIS,
        TimelineKind.REPORT_DELIVERED,
    ]
    assert history[1].cause == "the datastore is over-provisioned; a snapshot is holding blocks"


# --- Retention -------------------------------------------------------------------------


async def test_retention_removes_closed_incidents_and_only_closed_ones(
    gateway: PersistenceGateway,
) -> None:
    """An open incident is somebody's current problem whatever its age."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(
            incident(correlation_key="old", state=IncidentState.RESOLVED, minutes=-200, closed=-190)
        )
        await uow.incidents.upsert(incident(correlation_key="ancient-and-open", minutes=-200))

        removed = await uow.incidents.purge(before=at(-100))
        left = await uow.incidents.query(IncidentQuery())

    assert removed == 1
    assert [entry.correlation_key for entry in left] == ["ancient-and-open"]


# --- Tenancy ----------------------------------------------------------------------------


async def test_one_tenants_incidents_are_invisible_from_another(
    gateway: PersistenceGateway,
) -> None:
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)
        await uow.incidents.append((entry(stored.incident_id),))

    async with gateway.begin(TenantScope(org_id="globex")) as other:
        assert await other.incidents.query(IncidentQuery()) == ()
        assert await other.incidents.open_for("detector:datastore-near-full") is None
        assert await other.incidents.get(stored.incident_id) is None
        assert await other.incidents.timeline(stored.incident_id) == ()
        assert await other.incidents.purge(before=at(100)) == 0


# --- Public address lookup ----------------------------------------------------------
#
# The forward direction (internal key to public address) is a pure function,
# proved without a database in `test_incident_public_id.py`. What only a store
# can prove is the *lookup*: given the public address alone, is the row it
# names the same row `get` returns for the internal key — in both backends,
# because a lookup that agreed with itself in memory and disagreed in
# PostgreSQL would make the console and a real deployment resolve different
# incidents for the same address.


async def test_get_by_public_id_returns_the_same_incident_get_does(
    gateway: PersistenceGateway,
) -> None:
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)

        by_internal_key = await uow.incidents.get(stored.incident_id)
        by_public_address = await uow.incidents.get_by_public_id(stored.public_id)

    assert by_internal_key is not None
    assert by_public_address is not None
    assert by_public_address.incident_id == by_internal_key.incident_id
    assert by_public_address.public_id == stored.public_id


async def test_get_by_public_id_of_an_address_nothing_carries_is_none(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        assert await uow.incidents.get_by_public_id("inc_0000000000000000") is None


async def test_get_by_public_id_does_not_cross_a_tenant_boundary(
    gateway: PersistenceGateway,
) -> None:
    stored = incident()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(stored)

    async with gateway.begin(TenantScope(org_id="globex")) as other:
        assert await other.incidents.get_by_public_id(stored.public_id) is None
