"""What the isolation layer writes down, and where it cannot be edited afterwards.

Two claims. A lifecycle event carries nothing that could be a credential, and a
refused connection carries everything an operator needs to act on it — which are
the two halves of an audit trail being worth having.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.security import (
    SANDBOX_AUDIT_RESOURCE_KIND,
    SANDBOX_EGRESS_AUDIT_ACTION,
    SANDBOX_LIFECYCLE_AUDIT_ACTION,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope
from platform.sandbox import EgressPolicy, LimitKind, SandboxInstance, SandboxProfile
from platform.sandbox.egress import record_blocked_egress
from platform.sandbox.port import SandboxState
from platform.sandbox.trace import (
    AuditingSandboxEvents,
    CollectingSandboxEvents,
    NullSandboxEvents,
    SandboxEvent,
    SandboxEventKind,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _instance() -> SandboxInstance:
    """Return a provisioned instance to record events against."""
    return SandboxInstance(
        sandbox_id="sbx-1",
        profile=SandboxProfile.KUBERNETES,
        org_id="acme",
        team_id="platform",
        investigation_id="inv-1",
        state=SandboxState.CLAIMED,
        created_at=NOW,
        expires_at=NOW,
        scratch_path="/scratch",
        content_path="/opt/ninjasre/content",
    )


async def test_a_blocked_connection_is_audited_with_target_capability_and_investigation() -> None:
    """Field by field: each one is what an operator's next action needs."""
    events = CollectingSandboxEvents()
    policy = EgressPolicy(proxy_url="http://127.0.0.1:8081", hosts=("api.datadoghq.com",))

    error = await record_blocked_egress(
        events,
        instance=_instance(),
        policy=policy,
        host="attacker.example",
        capability="datadog.query_metrics",
    )

    assert error.host == "attacker.example"
    assert error.allowed == ("127.0.0.1", "api.datadoghq.com")
    assert "not on its egress allow-list" in str(error)

    recorded = events.of_kind(SandboxEventKind.EGRESS_DENIED)
    assert len(recorded) == 1
    detail = recorded[0].detail()
    assert detail["host"] == "attacker.example"
    assert detail["capability"] == "datadog.query_metrics"
    assert detail["investigation_id"] == "inv-1"


async def test_a_refusal_is_returned_rather_than_raised() -> None:
    """The caller decides whether a refusal ends the tool call or is a value."""
    error = await record_blocked_egress(
        NullSandboxEvents(),
        instance=_instance(),
        policy=EgressPolicy(proxy_url="http://127.0.0.1:8081"),
        host="attacker.example",
    )
    assert isinstance(error, Exception)


def test_a_lifecycle_event_carries_only_scalars_that_cannot_hold_a_secret() -> None:
    event = SandboxEvent(
        kind=SandboxEventKind.LIMIT_EXCEEDED,
        sandbox_id="sbx-1",
        profile=SandboxProfile.PROCESS,
        org_id="acme",
        team_id="platform",
        investigation_id="inv-1",
        capability="run_analysis_code",
        limit=LimitKind.MEMORY_BYTES,
        duration_seconds=1.23456789,
    )
    detail = event.detail()

    assert detail["limit"] == "memory_bytes"
    assert detail["duration_seconds"] == 1.234568
    # There is no field a payload could arrive in. That is the design, not an
    # omission: a free-form detail is where a rejected request body lands.
    assert set(detail) <= {
        "kind",
        "profile",
        "team_id",
        "investigation_id",
        "capability",
        "host",
        "content_digest",
        "reason",
        "limit",
        "duration_seconds",
    }


@pytest.mark.parametrize(
    ("kind", "outcome"),
    [
        (SandboxEventKind.PROVISIONED, AuditOutcome.ALLOWED),
        (SandboxEventKind.EGRESS_DENIED, AuditOutcome.DENIED),
        (SandboxEventKind.LIMIT_EXCEEDED, AuditOutcome.DENIED),
        (SandboxEventKind.PROVISIONING_FAILED, AuditOutcome.FAILED),
    ],
)
def test_each_event_kind_reads_correctly_in_the_audit_trail(
    kind: SandboxEventKind, outcome: AuditOutcome
) -> None:
    event = SandboxEvent(
        kind=kind,
        sandbox_id="sbx-1",
        profile=SandboxProfile.CONTAINER,
        org_id="acme",
        team_id="platform",
        investigation_id="inv-1",
    )
    audit = event.audit_event()
    assert audit.outcome is outcome
    assert audit.actor_kind is ActorKind.AGENT
    assert audit.actor_id == "inv-1"
    assert audit.resource_kind == SANDBOX_AUDIT_RESOURCE_KIND
    assert audit.resource_id == "sbx-1"
    expected_action = (
        SANDBOX_EGRESS_AUDIT_ACTION
        if kind is SandboxEventKind.EGRESS_DENIED
        else SANDBOX_LIFECYCLE_AUDIT_ACTION
    )
    assert audit.action == expected_action


async def test_events_land_in_the_tenants_append_only_audit_trail() -> None:
    """Where the record is kept is the part that makes it a record."""
    gateway = FakePersistence()
    await _create_org(gateway, "acme")
    mirror = CollectingSandboxEvents()
    sink = AuditingSandboxEvents(gateway=gateway, mirror=mirror)

    await sink.record(
        SandboxEvent(
            kind=SandboxEventKind.PROVISIONED,
            sandbox_id="sbx-1",
            profile=SandboxProfile.KUBERNETES,
            org_id="acme",
            team_id="platform",
            investigation_id="inv-1",
            duration_seconds=0.04,
        )
    )

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        stored = await uow.audit.query(action=SANDBOX_LIFECYCLE_AUDIT_ACTION)

    assert len(stored) == 1
    assert stored[0].resource_id == "sbx-1"
    assert stored[0].detail["investigation_id"] == "inv-1"
    assert len(mirror.events) == 1


async def test_the_null_sink_discards_without_a_branch_at_every_call_site() -> None:
    await NullSandboxEvents().record(
        SandboxEvent(
            kind=SandboxEventKind.RELEASED,
            sandbox_id="sbx-1",
            profile=SandboxProfile.PROCESS,
            org_id="acme",
            team_id="platform",
            investigation_id="inv-1",
        )
    )


async def _create_org(gateway: FakePersistence, org_id: str) -> None:
    """Create the organisation the audit rows will belong to."""
    async with gateway.begin_system() as uow:
        await uow.orgs.create_organisation(org_id, org_id)
