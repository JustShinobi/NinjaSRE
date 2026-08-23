"""Reading a run says what it is linked to: its incident, and the resources it touched.

Both derived from what was recorded — the incident from a real lookup, never
from a client paging through ``/v1/incidents``; the resources from the calls
this run actually made, never from the alert's own declared subjects.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.runs import TRIGGER_ALERT
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject
from platform.persistence.ports.run_trace_store import RunStatus, ToolCallStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from tests.contract.runs._deployment import ORG, TEAM, Deployment, bearer

pytestmark = pytest.mark.contract


async def _seed_run(deployment: Deployment, *, run_id: str) -> None:
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with deployment.gateway.begin(scope) as uow:
        recorder = RunRecorder(store=uow.run_traces)
        await recorder.start_run(
            trigger=TRIGGER_ALERT, principal_id="alertmanager", team_node_id=TEAM, run_id=run_id
        )
        turn = await recorder.record_turn(RecordedTurn(run_id=run_id, index=0, model="m"))
        await recorder.record_call(
            RecordedCall(
                run_id=run_id,
                turn_id=turn.turn_id,
                name="kubernetes.list_pods",
                status=ToolCallStatus.SUCCEEDED,
                arguments={"namespace": "payments", "resource_id": "host-1"},
            )
        )
        await recorder.complete_run(run_id, status=RunStatus.COMPLETED, summary="done")


class TestARunLinkedToAnIncidentNamesIt:
    async def test_the_run_names_the_incident_it_belongs_to(self, deployment: Deployment) -> None:
        scope = TenantScope(org_id=ORG, team_node_id=TEAM)
        async with deployment.gateway.begin(scope) as uow:
            lifecycle = IncidentLifecycle(store=uow.incidents)
            incident = await lifecycle.raise_incident(
                IncidentRaise(
                    correlation_key="alert:instance-down:host-1",
                    title="InstanceDown",
                    summary="host-1 stopped responding",
                    origin=IncidentOrigin.ALERT,
                    origin_id="alertmanager",
                    severity="critical",
                    subjects=(IncidentSubject(resource_id="host-1"),),
                ),
                now=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            )
            await lifecycle.attach_run(
                incident.incident_id, "run-1", now=datetime(2026, 3, 1, 9, 1, tzinfo=UTC)
            )
        await _seed_run(deployment, run_id="run-1")

        response = await deployment.client.get(
            "/v1/runs/run-1", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        assert response.json()["incident_id"] == incident.incident_id

    async def test_a_run_with_no_incident_says_so_explicitly(self, deployment: Deployment) -> None:
        await _seed_run(deployment, run_id="run-solo")

        response = await deployment.client.get(
            "/v1/runs/run-solo", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        # Distinguishable from a failed read: the request still succeeded.
        assert response.json()["incident_id"] == ""


class TestARunListsTheResourcesItsCallsTouched:
    async def test_the_resource_named_in_a_calls_arguments_is_listed(
        self, deployment: Deployment
    ) -> None:
        await _seed_run(deployment, run_id="run-1")

        response = await deployment.client.get(
            "/v1/runs/run-1", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        assert "host-1" in response.json()["touched_resources"]

    async def test_a_run_that_called_nothing_lists_no_resources(
        self, deployment: Deployment
    ) -> None:
        scope = TenantScope(org_id=ORG, team_node_id=TEAM)
        async with deployment.gateway.begin(scope) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_ALERT,
                principal_id="alertmanager",
                team_node_id=TEAM,
                run_id="run-quiet",
            )
            await recorder.complete_run(
                "run-quiet", status=RunStatus.COMPLETED, summary="no capability could run"
            )

        response = await deployment.client.get(
            "/v1/runs/run-quiet", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["touched_resources"] == []
