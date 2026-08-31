"""A run is named by its subject from the moment it starts, never by a hash.

Before this, every live run read as "interactive investigation" or
"investigation triggered by <hex>" because nothing recorded the objective a
person typed or the alert that fired, and the read path invented a sentence
from ``trigger``/``alert_id`` because that was all it had. This is the
contract for what replaces that: the objective and the alert's own subject
are recorded when the run starts, named the same way a completed run's
headline already is, and the invented sentence is gone rather than bypassed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from config.constants.runs import MAX_HEADLINE_LENGTH, TRIGGER_ALERT, TRIGGER_INTERACTIVE
from gateway.http.orchestration import start_investigation
from gateway.http.state import GatewayState
from platform.guardrails.engine import GuardrailEngine
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes.run_trace_store import FakeRunTraceStore
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.headline import normalize_headline, synthesize_headline
from platform.runs.recorder import RunRecorder
from tests.contract.runs._deployment import ORG, TEAM, Deployment, bearer
from tests.unit.gateway.http.conftest import FakeInvestigationRunner

pytestmark = pytest.mark.contract

#: A real secret the shipped ruleset catches (``aws-access-key-id``), reused
#: verbatim from the recorder's own unit test so this contract exercises the
#: same rule an operator's deployment actually runs, not a stand-in pattern.
SECRET = "AKIAIOSFODNN7EXAMPLE"


def _scope() -> TenantScope:
    return TenantScope(org_id=ORG, team_node_id=TEAM)


class TestAManualRunIsNamedByWhatWasAsked:
    """A1 — the objective is the headline from the first read to the last one running."""

    async def test_the_post_response_already_carries_the_headline(
        self, deployment: Deployment
    ) -> None:
        response = await deployment.client.post(
            "/v1/investigations",
            json={"objective": "Investigate checkout latency"},
            headers=bearer(deployment.operator_secret),
        )

        assert response.status_code == 202
        assert response.json()["headline"] == "Investigate checkout latency"

    async def test_the_list_and_the_detail_agree_while_the_run_is_still_going(
        self, deployment: Deployment
    ) -> None:
        # Seeded directly through the recorder rather than through the HTTP
        # route: the route's own background task drives an
        # ``UnconfiguredInvestigator`` in this fixture, which fails the run
        # almost immediately, and this test's whole point is what the list
        # and the detail show *while it is still running* — a state a real
        # runtime can hold for minutes but this fixture cannot hold at all.
        # ``test_the_post_response_already_carries_the_headline`` above is
        # what actually exercises the live HTTP route.
        run_id = "run-still-running"
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id=run_id,
                objective="Investigate checkout latency",
            )

        listing = await deployment.client.get(
            "/v1/investigations", headers=bearer(deployment.operator_secret)
        )
        detail = await deployment.client.get(
            f"/v1/investigations/{run_id}", headers=bearer(deployment.operator_secret)
        )
        run_via_runs = await deployment.client.get(
            f"/v1/runs/{run_id}", headers=bearer(deployment.operator_secret)
        )

        listed = next(item for item in listing.json()["investigations"] if item["run_id"] == run_id)
        assert listed["status"] == "running"
        assert listed["headline"] == "Investigate checkout latency"
        assert detail.json()["headline"] == "Investigate checkout latency"
        assert run_via_runs.json()["headline"] == "Investigate checkout latency"

    async def test_completing_replaces_the_provisional_headline(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-completes",
                objective="Investigate checkout latency",
            )
            await recorder.complete_run(
                "run-completes",
                status=RunStatus.COMPLETED,
                summary="Full report.",
                headline="Connection pool exhaustion in checkout",
            )

        response = await deployment.client.get(
            "/v1/investigations/run-completes", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["headline"] == "Connection pool exhaustion in checkout"
        assert response.json()["report"] == "Full report."


class TestAnAlertTriggeredRunIsNamedByTheAlertAndTheResource:
    """A2 — never the alert's id, always the alert's own subject."""

    async def test_headline_is_alertname_on_resource(self, deployment: Deployment) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_ALERT,
                principal_id="alertmanager",
                team_node_id=TEAM,
                run_id="run-alert-1",
                alert_id="bc7bdbd452fae8f1c9d3a0e5b7461203",
                alert_labels={"alertname": "RedisExporterDown", "instance": "redis-1"},
            )

        response = await deployment.client.get(
            "/v1/investigations/run-alert-1", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["headline"] == "RedisExporterDown on redis-1"
        assert "bc7bdbd452fae8f1c9d3a0e5b7461203" not in response.json()["headline"]

    async def test_headline_is_alertname_alone_with_no_resource_label(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_ALERT,
                principal_id="alertmanager",
                team_node_id=TEAM,
                run_id="run-alert-2",
                alert_id="deadbeef",
                alert_labels={"alertname": "DiskFull"},
            )

        response = await deployment.client.get(
            "/v1/investigations/run-alert-2", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["headline"] == "DiskFull"


class TestAnOldRowNeverServesTheAlertIdAsATitle:
    """A6/A7 — a run recorded before this feature reads as subject-less, never as its hash."""

    async def test_a_pre_migration_row_synthesises_a_generic_headline(
        self, deployment: Deployment
    ) -> None:
        # Seeded directly on the store, the way a row from before this
        # feature actually looks: no objective, no headline, an alert_id
        # that is exactly the kind of hash the product used to print.
        async with deployment.gateway.begin(_scope()) as uow:
            await uow.run_traces.start_run(
                AgentRun(
                    run_id="run-legacy",
                    trigger=TRIGGER_ALERT,
                    status=RunStatus.RUNNING,
                    alert_id="a1b2c3d4e5f60718293041526374859",
                )
            )

        response = await deployment.client.get(
            "/v1/investigations/run-legacy", headers=bearer(deployment.operator_secret)
        )
        headline = response.json()["headline"]

        assert headline == synthesize_headline()
        assert "a1b2c3d4e5f60718293041526374859" not in headline
        assert "investigation triggered by" not in headline
        assert headline not in {"interactive investigation", "alert investigation"}


class TestASecretNeverReachesAnyTitleOrTheStartEvent:
    """R2/R3 — redaction happens before anything is written, not after."""

    async def test_a_secret_in_the_objective_never_appears_anywhere(
        self, deployment: Deployment
    ) -> None:
        # A real ``GuardrailEngine``, wired exactly as ``orchestration.py``
        # always wires one — a recorder built with none, the way a careless
        # helper elsewhere in this suite does, would prove nothing here.
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces, guardrails=GuardrailEngine())
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-secret-objective",
                objective=f"Rotate the key {SECRET} before it leaks further",
            )
            events = await uow.run_traces.events_for_run("run-secret-objective")

        response = await deployment.client.get(
            "/v1/investigations/run-secret-objective", headers=bearer(deployment.operator_secret)
        )

        assert SECRET not in response.json()["headline"]
        assert SECRET not in response.text
        start_events = [event for event in events if event.kind == "run_started"]
        assert start_events, "no run_started event was recorded"
        assert SECRET not in str(start_events[0].payload)
        # The internal start event's payload is exactly {trigger, team_node_id}
        # — untouched by this feature. Naming that here so a future change that
        # widens it is caught by this test, not discovered downstream.
        assert set(start_events[0].payload) == {"trigger", "team_node_id"}

    async def test_a_secret_in_an_alert_label_never_reaches_the_headline(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces, guardrails=GuardrailEngine())
            await recorder.start_run(
                trigger=TRIGGER_ALERT,
                principal_id="alertmanager",
                team_node_id=TEAM,
                run_id="run-secret-label",
                alert_labels={"alertname": "DiskFull", "instance": SECRET},
            )

        response = await deployment.client.get(
            "/v1/investigations/run-secret-label", headers=bearer(deployment.operator_secret)
        )

        assert SECRET not in response.json()["headline"]
        assert SECRET not in response.text


class TestSecretsFromOrchestrationNeverReachTheTimelineOrTheRuntime:
    """T015 — every consumer inside ``start_investigation`` sees the redacted
    value, not just ``start_run``.

    The two tests above only ever call ``RunRecorder.start_run`` directly,
    so they never exercised ``start_investigation`` itself — the function
    that computes ``sanitized_objective``/``sanitized_labels`` and, before
    this fix, used them for the recorder only. Three other consumers in the
    same function still read the raw parameter: ``IncidentLifecycle.
    attach_run`` (the incident timeline's ``cause``), ``IncidentLifecycle.
    record_alert_received`` (the timeline's ``detail``, rendered from the
    labels), and the ``InvestigationStart`` handed to the runtime — the
    actual prompt an investigation reasons over. This class calls
    ``start_investigation`` for real, with an incident and a credential name
    so all three fire, and checks all three destinations.
    """

    async def test_a_secret_in_the_objective_and_an_alert_label_never_reaches_the_incident_timeline_or_the_runtime(
        self, deployment: Deployment
    ) -> None:
        runner = FakeInvestigationRunner()
        state = GatewayState(
            gateway=deployment.gateway,
            tokens=TokenService(gateway=deployment.gateway),
            investigator=runner,
        )
        scope = _scope()
        async with deployment.gateway.begin(scope) as uow:
            incident = await IncidentLifecycle(store=uow.incidents).raise_incident(
                IncidentRaise(
                    correlation_key="alert:secret-test:host-9",
                    title="DiskFull",
                    summary="host-9 is full",
                    origin=IncidentOrigin.ALERT,
                    origin_id="alertmanager",
                    severity="critical",
                    subjects=(IncidentSubject(resource_id="host-9"),),
                    team_node_id=TEAM,
                ),
                now=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            )

        run_id = await start_investigation(
            state,
            scope=scope,
            trigger=TRIGGER_ALERT,
            objective=f"Investigate host-9. Rotate the key {SECRET} first.",
            principal_id="alertmanager",
            alert_id="alert-secret-9",
            incident_id=incident.incident_id,
            alert_labels={"alertname": "DiskFull", "instance": SECRET},
            credential_name="delivery-token-9",
        )

        # start_investigation only schedules the investigation as a
        # background task (acceptance scenario 1: the response comes back
        # before the run itself does) — wait for it, the same way a
        # graceful shutdown would, before reading what it produced.
        await asyncio.gather(*state.background_runs)

        async with deployment.gateway.begin(scope) as uow:
            timeline = await IncidentLifecycle(store=uow.incidents).timeline(incident.incident_id)

        rendered_timeline = " ".join(f"{entry.cause} {entry.detail}" for entry in timeline)
        assert SECRET not in rendered_timeline, (
            f"the incident timeline still carries the secret: {rendered_timeline!r}"
        )

        assert runner.started, "start_investigation never reached the runtime"
        request = runner.started[-1]
        assert request.run_id == run_id
        assert SECRET not in request.objective, (
            f"InvestigationStart.objective still carries the secret: {request.objective!r}"
        )
        assert SECRET not in str(request.alert_labels), (
            f"InvestigationStart.alert_labels still carries the secret: {request.alert_labels!r}"
        )


class TestTheListKnowsWhatStageALiveRunReached:
    """A5 — one summary field per run, from one query for the whole page."""

    async def test_a_run_that_completed_three_stages_reports_the_last_one(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-mid-flight",
                objective="Investigate node pressure",
            )
            for stage in ("resolve_integrations", "intake", "plan_evidence"):
                await recorder.record_stage(run_id="run-mid-flight", stage=stage)

        response = await deployment.client.get(
            "/v1/investigations/run-mid-flight", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["last_completed_stage"] == "plan_evidence"
        assert response.json()["stage_index"] == 3

    async def test_get_v1_runs_reports_the_same_stage_the_console_actually_reads(
        self, deployment: Deployment
    ) -> None:
        # The console's list screens (runs, agent, memory, incidents,
        # dashboard) all read GET /v1/runs, never GET /v1/investigations —
        # confirmed by grep across console/src/surfaces/screens/*.tsx and
        # console/src/shell/load.ts. A field that only reached
        # /v1/investigations would exist in the API and nowhere the product
        # actually shows it (Article XIV).
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-via-runs-list",
                objective="Investigate node pressure",
            )
            for stage in ("resolve_integrations", "intake"):
                await recorder.record_stage(run_id="run-via-runs-list", stage=stage)

        listing = await deployment.client.get(
            "/v1/runs", headers=bearer(deployment.operator_secret)
        )
        detail = await deployment.client.get(
            "/v1/runs/run-via-runs-list", headers=bearer(deployment.operator_secret)
        )

        listed = next(
            item for item in listing.json()["runs"] if item["run_id"] == "run-via-runs-list"
        )
        assert listed["last_completed_stage"] == "intake"
        assert listed["stage_index"] == 2
        assert detail.json()["last_completed_stage"] == "intake"
        assert detail.json()["stage_index"] == 2

    async def test_a_freshly_started_run_reports_no_stage_yet(self, deployment: Deployment) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-brand-new",
                objective="Investigate node pressure",
            )

        response = await deployment.client.get(
            "/v1/investigations/run-brand-new", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["last_completed_stage"] == ""
        assert response.json()["stage_index"] == 0

    async def test_the_list_reads_a_page_of_stages_in_exactly_two_store_calls(
        self, deployment: Deployment, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            for index in range(50):
                run_id = f"run-page-{index:02d}"
                await recorder.start_run(
                    trigger=TRIGGER_INTERACTIVE,
                    principal_id="operator-1",
                    team_node_id=TEAM,
                    run_id=run_id,
                    objective=f"Investigate host-{index}",
                )
                await recorder.record_stage(run_id=run_id, stage="resolve_integrations")

        calls = {"list_runs": 0, "last_completed_stages": 0}
        original_list_runs = FakeRunTraceStore.list_runs
        original_last_completed_stages = FakeRunTraceStore.last_completed_stages

        async def counting_list_runs(self: FakeRunTraceStore, **kwargs: object) -> object:
            calls["list_runs"] += 1
            return await original_list_runs(self, **kwargs)  # type: ignore[arg-type]

        async def counting_last_completed_stages(
            self: FakeRunTraceStore, run_ids: object
        ) -> object:
            calls["last_completed_stages"] += 1
            return await original_last_completed_stages(self, run_ids)  # type: ignore[arg-type]

        monkeypatch.setattr(FakeRunTraceStore, "list_runs", counting_list_runs)
        monkeypatch.setattr(
            FakeRunTraceStore, "last_completed_stages", counting_last_completed_stages
        )

        response = await deployment.client.get(
            "/v1/investigations",
            headers=bearer(deployment.operator_secret),
            params={"limit": 50},
        )

        assert response.status_code == 200
        assert len(response.json()["investigations"]) == 50
        assert all(
            item["last_completed_stage"] == "resolve_integrations"
            for item in response.json()["investigations"]
        )
        # Two calls total for fifty rows — one for the runs, one for their
        # stages — never one stage read per row, which is the shape an N+1
        # takes on a page this size.
        assert calls["list_runs"] == 1
        assert calls["last_completed_stages"] == 1


class TestEdgeCasesTheSynthesisAlreadyHandles:
    """Named in the plan as correct by construction; covered here for regression."""

    async def test_an_objective_of_only_whitespace_falls_back_to_the_generic_headline(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-blank-objective",
                objective="   ",
            )

        response = await deployment.client.get(
            "/v1/investigations/run-blank-objective", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["headline"] == synthesize_headline()

    async def test_an_objective_over_the_headline_ceiling_persists_whole_and_the_headline_is_cut(
        self, deployment: Deployment
    ) -> None:
        long_objective = "Investigate " + " ".join(f"node-{i:03d}" for i in range(30))
        assert len(long_objective) > MAX_HEADLINE_LENGTH

        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-long-objective",
                objective=long_objective,
            )
            stored = await uow.run_traces.get_run("run-long-objective")

        response = await deployment.client.get(
            "/v1/investigations/run-long-objective", headers=bearer(deployment.operator_secret)
        )

        assert stored is not None
        assert stored.objective == long_objective
        assert response.json()["headline"] == normalize_headline(long_objective)
        assert len(response.json()["headline"]) <= MAX_HEADLINE_LENGTH
        assert not response.json()["headline"].endswith("node-0")

    async def test_the_provisional_headline_survives_an_interrupted_run(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-interrupted",
                objective="Investigate checkout latency",
            )
            await recorder.mark_interrupted("run-interrupted", reason="replica restarted")

        response = await deployment.client.get(
            "/v1/investigations/run-interrupted", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["status"] == "interrupted"
        assert response.json()["headline"] == "Investigate checkout latency"

    async def test_the_provisional_headline_survives_a_failed_run(
        self, deployment: Deployment
    ) -> None:
        async with deployment.gateway.begin(_scope()) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_INTERACTIVE,
                principal_id="operator-1",
                team_node_id=TEAM,
                run_id="run-failed",
                objective="Investigate checkout latency",
            )
            # complete_run's own contract: ``headline=None`` leaves the
            # column exactly as it was — the provisional stays because the
            # delivery produced no sentence to replace it with.
            await recorder.complete_run(
                "run-failed", status=RunStatus.FAILED, summary="the pipeline raised"
            )

        response = await deployment.client.get(
            "/v1/investigations/run-failed", headers=bearer(deployment.operator_secret)
        )

        assert response.json()["status"] == "failed"
        assert response.json()["headline"] == "Investigate checkout latency"
