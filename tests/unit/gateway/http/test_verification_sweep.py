"""The obligation a change writes down, and the pass that comes back for it.

The executor writes a row saying "read these signals about this resource at
14:05 and compare them to these values", and returns. Everything that turns that
row into a verdict was written — the claim, the readback, the comparison, the
rollback, the escalation, the episode write — and no deployment had any of it:
the scheduler knew two kinds of job, and neither was this one. A staging
deployment therefore held a remediation in ``awaiting_verification`` from one
midnight to the next, with a due time forty seconds after the change and nothing
that reads a due time.

That is worse than never having verified. The screen says "awaiting
verification", which means "ask again shortly", and nobody was going to.

So these tests are about the path rather than about the arithmetic. The
arithmetic already has a contract suite over the real objects. What is asserted
here is that a deployment which composed a desk also schedules the sweep, that
the scheduler can dispatch the kind, and that one action taken through the
approval route reaches a verdict, an incident and an episode without anything in
the test calling the closed loop by hand.

**Time is passed in, never waited for.** The settle period is five minutes, and
a test that slept for it would be a test people delete. Every clock the sweep
reads comes off the job's fire time.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from config.constants.closed_loop import VERIFICATION_SWEEP_JOB_KIND
from gateway.http.remediation import compose_remediation
from gateway.http.scheduled_work import dispatcher_for
from platform.identity.permissions import Role
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.memory.models import MemoryEpisode
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    TenantScope,
)
from platform.persistence.ports.remediation_ledger import (
    VerificationState,
    VerificationVerdict,
)
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key
from platform.remediation.closed_loop import SWEEP_JOB_ID
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    StateSnapshot,
    SubTargetResult,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

PROXY = "http://127.0.0.1:8787"
SCALE = "scale_workload"
RESOURCE = "checkout"
READY_REPLICAS = "workload.ready_replicas"

#: A fixed instant, so the settle period is arithmetic rather than a wait.
ACTED_AT = datetime(2026, 8, 26, 0, 55, tzinfo=UTC)

#: What ``scale_workload`` declares, and what the sweep must therefore respect.
SETTLE_SECONDS = 300


class _Plane:
    """Reads a replica count and records every change it is asked to make."""

    def __init__(self) -> None:
        self.changes: list[RemediationAction] = []

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=(RESOURCE,))

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        del desired, before
        self.changes.append(action)
        return (SubTargetResult(identifier=RESOURCE, changed=True),)


@pytest.fixture
def plane() -> Any:
    bound = _Plane()
    previous = control_plane.bind(bound)
    yield bound
    control_plane.restore(previous)


def _action(run_id: str = "run-1") -> RemediationAction:
    """Return the write a finished investigation would have proposed."""
    from core.capability.metadata import SideEffectLevel

    return RemediationAction(
        action_id="action-1",
        capability=SCALE,
        target=RemediationTarget(
            identifier=RESOURCE, environment="production", node_id=TEAM_PAYMENTS
        ),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ana",
        intent="checkout is saturating its replicas",
        arguments={"workload": RESOURCE, "environment": "production", "replicas": 4},
        run_id=run_id,
        team_node_id=TEAM_PAYMENTS,
        risk_class="low",
        rollback_planned=True,
    )


async def _observe(deployment: Deployment, value: float, *, at: datetime) -> None:
    """Write one reading of the signal the capability declares its effect in."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.signals.append(
            (
                Signal(
                    signal_id=signal_key(READY_REPLICAS, RESOURCE, at),
                    name=READY_REPLICAS,
                    resource_id=RESOURCE,
                    source="prometheus",
                    kind=SignalKind.NUMBER,
                    observed_at=at,
                    value=value,
                ),
            )
        )


async def _raise_incident(deployment: Deployment, *, run_id: str) -> str:
    """Open the incident the investigation belongs to, and attach its run."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key=f"{RESOURCE}:saturated",
                title="checkout is saturating its replicas",
                summary="request latency is tracking replica saturation",
                origin=IncidentOrigin.ALERT,
                origin_id="alert-1",
                severity="high",
                team_node_id=TEAM_PAYMENTS,
                subjects=(IncidentSubject(resource_id=RESOURCE),),
            ),
            now=ACTED_AT - timedelta(minutes=5),
        )
        await lifecycle.attach_run(
            incident.incident_id, run_id=run_id, now=ACTED_AT - timedelta(minutes=4)
        )
    return incident.incident_id


async def _leave_episode(deployment: Deployment, *, run_id: str) -> None:
    """Write the episode a finished investigation leaves behind.

    The root cause is the half only the investigation knows. What the sweep has
    to add is the other half — that a change was made and whether it worked —
    and the assertion below is that both are on one record rather than two.
    """
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        await uow.episodes.save(
            MemoryEpisode(
                correlation_id=run_id,
                org_id=ORG,
                team_node_id=TEAM_PAYMENTS,
                issue_type="saturation",
                issue_description="checkout is saturating its replicas",
                root_cause="the deployment was sized for half the traffic it now takes",
                summary="scale checkout out",
                run_id=run_id,
                occurred_at=ACTED_AT - timedelta(minutes=5),
            ).to_stored()
        )


async def _approve(deployment: Deployment, client: AsyncClient) -> str:
    """Queue the write the way the gate does, approve it, and return its id."""
    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, "the test deployment could not compose a remediation desk"
    request = await desk.requests.queue(_action())
    assert request.change_id

    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )
    response = await client.post(
        f"/v1/approvals/{request.change_id}/decision",
        json={"verdict": "approve", "reason": ""},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    return request.change_id


async def _sweep(deployment: Deployment, *, at: datetime) -> Any:
    """Run the sweep the way the scheduler runs it, at ``at``."""
    from platform.persistence.ports.schedule_store import JobClaim
    from platform.scheduler.dispatch import JobContext

    dispatcher = dispatcher_for(deployment.state)
    job = await _sweep_job(deployment)
    assert job is not None, (
        "composing a remediation desk did not schedule the sweep that settles its "
        "obligations, so every verdict it owes waits for ever"
    )
    return await dispatcher.dispatch(
        JobContext(
            claim=JobClaim(
                claim_id="claim-1",
                job_id=job.job_id,
                org_id=ORG,
                worker_id="test",
                claimed_at=at,
                lease_expires_at=at + timedelta(seconds=120),
                payload=dict(job.payload),
            ),
            job=job,
            scope=TenantScope(org_id=ORG),
            fire_time=at,
        )
    )


async def _sweep_job(deployment: Deployment) -> Any:
    """Return the scheduled sweep this deployment registered, or ``None``."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.schedules.get_job(SWEEP_JOB_ID)


async def _outcome(deployment: Deployment) -> Any:
    """Return what the ledger holds for the action this suite takes."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.remediation.get("action-1")


def test_the_verification_sweep_kind_is_dispatched(deployment: Deployment) -> None:
    """The kind the sweep job is written under has a runner behind it.

    A job of a kind nothing dispatches is claimed, found unrunnable, rescheduled
    and claimed again for ever — which is a busier way of never verifying.
    """
    assert VERIFICATION_SWEEP_JOB_KIND in dispatcher_for(deployment.state).kinds


async def test_composing_a_desk_also_schedules_the_sweep_that_settles_its_obligations(
    plane: _Plane, deployment: Deployment
) -> None:
    """A deployment that can write can also find out whether the write worked.

    The two are one decision. A desk composed without the sweep is a deployment
    that changes production and then asks nobody.
    """
    await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)

    job = await _sweep_job(deployment)
    assert job is not None
    assert job.kind == VERIFICATION_SWEEP_JOB_KIND
    assert job.enabled
    assert job.next_run_at is not None


async def test_an_obligation_reaches_a_verdict_once_its_settle_period_has_passed(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """The whole point: the row leaves ``awaiting_verification`` by itself.

    Nothing here calls the closed loop. The approval route executes, the
    executor writes the obligation, and the scheduler's own dispatch is what
    settles it — which is the sequence a deployment actually runs.
    """
    await _observe(deployment, 2.0, at=ACTED_AT - timedelta(minutes=1))
    await _approve(deployment, client)

    owed = await _outcome(deployment)
    assert owed is not None
    assert owed.state is VerificationState.AWAITING
    assert owed.due_at == owed.executed_at + timedelta(seconds=SETTLE_SECONDS)

    # The scheduler placed the new instances and the exporter says so.
    await _observe(deployment, 4.0, at=owed.executed_at + timedelta(minutes=2))
    await _sweep(deployment, at=owed.due_at + timedelta(seconds=1))

    settled = await _outcome(deployment)
    assert settled is not None
    assert settled.state is VerificationState.VERIFIED, (
        "the obligation is still awaiting a verification nothing performs"
    )
    assert settled.verdict is VerificationVerdict.EFFECTIVE
    assert settled.before == {READY_REPLICAS: 2.0}
    assert settled.after == {READY_REPLICAS: 4.0}
    assert settled.verified_at is not None


async def test_a_verdict_before_the_settle_period_is_not_reached_early(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """A sweep that runs early leaves the obligation alone.

    The settle period exists because a scheduler needs time to place replicas.
    A sweep that read the signals a second after the change would call every
    slow rollout ineffective.
    """
    await _observe(deployment, 2.0, at=ACTED_AT - timedelta(minutes=1))
    await _approve(deployment, client)
    owed = await _outcome(deployment)
    assert owed is not None

    await _sweep(deployment, at=owed.due_at - timedelta(seconds=1))

    still_owed = await _outcome(deployment)
    assert still_owed is not None
    assert still_owed.state is VerificationState.AWAITING
    assert still_owed.verdict is None


async def test_the_verdict_lands_on_the_episode_the_investigation_left(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """The loop that closes by approval and execution deposits its episode too.

    The investigation's half is the root cause. The remediation's half is what
    was done about it and whether it worked. An episode carrying only the first
    teaches the next investigation to reach the same diagnosis and nothing about
    what to do with it.
    """
    run_id = "run-1"
    await _leave_episode(deployment, run_id=run_id)
    await _observe(deployment, 2.0, at=ACTED_AT - timedelta(minutes=1))
    await _approve(deployment, client)
    owed = await _outcome(deployment)
    assert owed is not None
    await _observe(deployment, 4.0, at=owed.executed_at + timedelta(minutes=2))

    await _sweep(deployment, at=owed.due_at + timedelta(seconds=1))

    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        episode = await uow.episodes.get_by_run(run_id)

    assert episode is not None, "the run that acted left no episode to learn from"
    assert episode.resolution and "sized for half the traffic" in episode.resolution
    recorded = list(episode.metadata.get("remediation", []))
    assert recorded, (
        "the episode records the diagnosis and not the remediation, so the next "
        "investigation of this failure learns what happened and not what worked"
    )
    assert recorded[0]["capability"] == SCALE
    assert recorded[0]["resource_id"] == RESOURCE
    assert recorded[0]["verdict"] == VerificationVerdict.EFFECTIVE.value
    assert f"remediation:{VerificationVerdict.EFFECTIVE.value}" in episode.tags


async def test_an_effective_verdict_closes_the_incident_the_run_belonged_to(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """The incident the change was taken for hears the answer.

    The obligation carries the run, and the run is attached to its incident.
    Without that join the verdict is written into a ledger nobody reads and the
    incident stays open, having in fact been resolved.
    """
    run_id = "run-1"
    incident_id = await _raise_incident(deployment, run_id=run_id)
    await _observe(deployment, 2.0, at=ACTED_AT - timedelta(minutes=1))
    await _approve(deployment, client)
    owed = await _outcome(deployment)
    assert owed is not None
    await _observe(deployment, 4.0, at=owed.executed_at + timedelta(minutes=2))

    await _sweep(deployment, at=owed.due_at + timedelta(seconds=1))

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        incident = await uow.incidents.get(incident_id)
        timeline = await uow.incidents.timeline(incident_id)

    assert incident is not None
    assert incident.state is IncidentState.RESOLVED, (
        "the change worked and the incident it was made for is still open"
    )
    assert any(SCALE in entry.cause for entry in timeline), (
        "nothing on the incident's own timeline says what was done about it"
    )
