"""No surface presents "investigating" for an incident whose run could not start.

Two claims, asserted separately because one proves nothing about the other:
the pendency has to be nameable somewhere an operator can read it, and the
run this incident references has to actually stop reading as "in progress"
once the attempt to drive it has finished. A screen could show the first
sentence while the second stayed wrong underneath it, and that combination —
a pending state displayed beside a lie — is exactly what this file rules out.
"""

from __future__ import annotations

import pytest

from gateway.http.asgi import UnconfiguredInvestigator
from gateway.http.orchestration import start_investigation
from gateway.http.runtime import runtime_composed
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.startup.checklist import _runtime_step
from tests.unit.gateway.http.conftest import ORG, TEAM_PLATFORM, Deployment

pytestmark = pytest.mark.unit


async def test_the_pendency_is_named_when_no_runtime_is_composed(deployment: Deployment) -> None:
    """One half of the claim: the setup checklist's own runtime step names it.

    Text a console screen renders verbatim, from the same source the
    investigation route consults — never a variable name.
    """
    deployment.state.investigator = UnconfiguredInvestigator()

    step = _runtime_step(runtime_composed(deployment.state), blocked=False)

    assert step.state != "done"
    assert "NINJASRE_INVESTIGATOR" not in step.detail
    assert "runtime" in step.detail.lower() or "investigat" in step.detail.lower()


async def test_an_incident_whose_investigation_could_not_start_never_reads_as_investigating(
    deployment: Deployment,
) -> None:
    """The other half: the run itself must not be left, or later read, as running.

    ``start_investigation`` writes the run row ``RUNNING`` before anything is
    attempted (acceptance scenario 1 — the caller is told the run's identity
    immediately). What this test pins is what happens *after*: once the
    background attempt has actually run its course against a deployment with
    no runtime, the row must no longer say ``RUNNING`` — the one word that
    would read, on any surface consulting it, as "investigating".
    """
    deployment.state.investigator = UnconfiguredInvestigator()
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PLATFORM)

    run_id = await start_investigation(
        deployment.state,
        scope=scope,
        trigger="alert",
        objective="disk on host-1 is at 98%",
        principal_id="system",
        alert_source="prometheus",
    )

    # The background task orchestration.start_investigation scheduled has not
    # had a chance to run yet — nothing between the call above and here has
    # awaited anything — so capturing it now and awaiting it here is
    # deterministic rather than a race with its own completion.
    scheduled = tuple(deployment.state.background_runs)
    assert len(scheduled) == 1
    await scheduled[0]

    async with deployment.gateway.begin(scope) as uow:
        run = await uow.run_traces.get_run(run_id)

    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.status is not RunStatus.RUNNING
    assert run.summary is not None and "InvestigatorNotConfigured" in run.summary
