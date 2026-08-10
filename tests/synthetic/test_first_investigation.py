"""The first investigation that closes the loop, and the three things it must be.

This is the measurable goal of the whole feature: an alert from the cluster
produces an investigation that cites evidence from more than one source, every
claim attributed to where it came from, proposing rather than acting, and
reproducible from its own recorded events.

The scenario is this cluster's own recurring failure — a container under memory
pressure — and it is deliberately built so that no single source can answer it.
The hypervisor knows the guest was killed and restarted; it does not know what
the memory looked like on the way there. The host-side exporter knows the
memory, keyed by the guest's own number, and knows nothing about restarts. The
log store holds the line the kernel wrote and cannot say what the guest's
ceiling was. A conclusion that draws on one of them is a conclusion about a
third of the problem, which is exactly the failure mode the product thesis is
about.

The ablation is the resolution itself, and it is mechanical rather than
declared: the same alert with the guest's number removed from its labels stops
resolving to a resource at all, and the host-side series it would have been
keyed by becomes a named gap. What that arm shows is that the multi-source
reading depends on the estate knowing what the alert was about, rather than on
the scenario having been written to succeed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from capabilities.registry.planning import CatalogueRanker
from config.constants.signals import SIGNAL_QUESTION_PRESSURE
from core.agent.react_loop import ReActLoop
from core.capability.metadata import SideEffectLevel
from core.domain.alerts.normalisation import RawAlert, adapter_for
from core.domain.alerts.sources import AlertSource
from core.domain.diagnosis.taxonomy import RootCauseCategory
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import PipelineRun
from core.pipeline.ports import FixedCatalogueResolver, InMemoryIncidentIndex
from core.pipeline.state_factory import initial_state
from core.pipeline.streaming import EventStream, RecordingSink, replay
from core.state.types import STAGE_ORDER
from platform.autonomy.audit import DecisionAuditor
from platform.autonomy.decision import AutonomyGate
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.estate.alert_resolution import AlertMatch, resolve_alert
from platform.estate.signal_map import signal_map_for
from platform.persistence.ports import TenantScope
from platform.remediation.gating import RemediationGate
from platform.remediation.models import RemediationAction, RemediationTarget
from tests.contract.autonomy.test_the_gate_obeys_the_policy import (
    CollectingRecorder,
    RecordingExecutor,
    StubRequests,
)
from tests.synthetic.conftest import (
    AT,
    CONTAINER_PRESSURE,
    PRESSURE_ESTATE,
    pressure_alert,
)

pytestmark = pytest.mark.synthetic


async def _investigate(sink: RecordingSink | None = None) -> PipelineRun:
    """Return the finished investigation of the container-pressure scenario."""
    scenario = CONTAINER_PRESSURE
    llm = scenario.llm()
    recorder = sink if sink is not None else RecordingSink()
    pipeline = build_pipeline(
        llm=llm,
        runtime=ReActLoop(llm=llm, tools=scenario.tools, hooks=investigation_hooks()),
        resolver=FixedCatalogueResolver(scenario.catalogue()),
        ranker=CatalogueRanker(),
        incidents=InMemoryIncidentIndex(),
        stream=EventStream(f"run-{scenario.key}", (recorder,)),
        strict=True,
    )
    return await pipeline.run(
        initial_state(scenario.raw, scenario.team, run_id=f"run-{scenario.key}")
    )


# --- The alert resolves to the guest the investigation is about --------------------


def test_the_alert_resolves_to_the_container_before_anything_is_investigated() -> None:
    """The identity everything downstream is keyed by, decided once at the door."""
    alert = adapter_for(AlertSource.ALERTMANAGER).normalise(
        RawAlert(payload=pressure_alert(), received_at=AT)
    )

    resolution = resolve_alert(alert, resources=PRESSURE_ESTATE)

    assert resolution.resolved is not None
    assert resolution.resolved.matched_on is AlertMatch.VMID
    assert resolution.resolved.display_name == "adguard"


# --- Three sources, every claim attributed ----------------------------------------


async def test_the_conclusion_draws_on_at_least_three_distinct_sources() -> None:
    """The measurable goal. Fewer than three is a conclusion about part of it."""
    run = await _investigate()

    sources = {entry.source for entry in run.state.evidence.entries}
    assert len(sources) >= 3, f"the run only reached {sorted(sources)}"
    assert {"proxmox", "prometheus", "loki"} <= sources


async def test_every_validated_claim_names_the_evidence_behind_it() -> None:
    """Article I, at the granularity of the claim rather than of the report."""
    run = await _investigate()
    diagnosis = run.state.investigation.diagnosis
    assert diagnosis is not None

    held = run.state.evidence.ids
    assert diagnosis.validated_claims
    for claim in diagnosis.validated_claims:
        assert claim.evidence_ids, f"{claim.statement!r} carries no evidence at all"
        assert claim.backed_by(held), f"{claim.statement!r} cites evidence the run does not hold"


async def test_the_claims_between_them_reach_every_source_the_run_used() -> None:
    """Three sources on the run and all three cited is what "multi-source" means.

    A run that read three systems and concluded from one of them is the failure
    this criterion exists to catch, and it is invisible in a source count taken
    off the run rather than off the claims.
    """
    run = await _investigate()
    diagnosis = run.state.investigation.diagnosis
    assert diagnosis is not None

    by_id = {entry.id: entry.source for entry in run.state.evidence.entries}
    cited = {
        by_id[evidence_id]
        for claim in diagnosis.validated_claims
        for evidence_id in claim.evidence_ids
        if evidence_id in by_id
    }
    assert {"proxmox", "prometheus", "loki"} <= cited


async def test_the_run_reached_the_category_its_answer_key_names() -> None:
    """A multi-source citation for the wrong conclusion is not an improvement."""
    run = await _investigate()
    diagnosis = run.state.investigation.diagnosis

    assert diagnosis is not None
    assert diagnosis.root_cause_category is RootCauseCategory.RESOURCE_EXHAUSTION


# --- The ablation: without resolution, the host-side series has no key --------------


def test_with_the_guests_number_absent_the_alert_resolves_to_nothing() -> None:
    """The mechanism removed, not the fixture rewritten."""
    payload = pressure_alert()
    del payload["alerts"][0]["labels"]["vmid"]  # type: ignore[index]
    alert = adapter_for(AlertSource.ALERTMANAGER).normalise(
        RawAlert(payload=payload, received_at=AT)
    )

    resolution = resolve_alert(alert, resources=PRESSURE_ESTATE)

    assert resolution.resolved is None
    assert resolution.unresolved is not None


def test_a_guest_with_no_identifier_turns_the_pressure_source_into_a_named_gap() -> None:
    """What the ablation costs: the one source that answers the question at all.

    An estate that cannot key the host-side series does not fall back to a
    worse answer — it says so. That is 054's rule, and this is where the two
    features meet: resolution is what supplies the key the map asks for.
    """
    guest = PRESSURE_ESTATE[0]
    without = type(guest)(
        **{
            **{
                name: getattr(guest, name)
                for name in (
                    "resource_id",
                    "kind",
                    "source",
                    "native_id",
                    "display_name",
                    "labels",
                )
            },
            "attributes": {key: value for key, value in guest.attributes.items() if key != "vmid"},
        }
    )

    mapped = signal_map_for(without, configured=("proxmox", "prometheus", "loki"))

    assert not mapped.answers(SIGNAL_QUESTION_PRESSURE)
    gap = mapped.missing_for(SIGNAL_QUESTION_PRESSURE)
    assert gap is not None
    assert "vmid" in gap.why


# --- Proposing, never acting -------------------------------------------------------


async def test_the_run_executed_nothing_with_a_side_effect() -> None:
    """Acceptance 5's first half, asserted against the catalogue's own levels."""
    run = await _investigate()

    levels = {
        tool.metadata.name: tool.metadata.side_effect_level for tool in CONTAINER_PRESSURE.tools
    }
    for entry in run.state.evidence.entries:
        assert levels[entry.capability] is SideEffectLevel.READ


async def test_the_conclusion_proposes_a_remediation_rather_than_reporting_one_done() -> None:
    """A remediation-class conclusion, which is what makes the next assertion mean anything."""
    run = await _investigate()
    diagnosis = run.state.investigation.diagnosis

    assert diagnosis is not None
    assert diagnosis.remediation_steps


async def test_with_dry_run_on_the_proposal_is_recorded_and_nothing_runs() -> None:
    """The whole of acceptance 5: what it *would* have done, readable, and undone."""
    recorder = CollectingRecorder()
    executor = RecordingExecutor()
    gate = RemediationGate(
        requests=StubRequests(),  # type: ignore[arg-type]
        executor=executor,
        autonomy=AutonomyGate(
            policies=PolicySet(
                rules=(
                    PolicyRule(
                        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                        level=AutonomyLevel.ACT_AND_REPORT,
                    ),
                ),
                dry_run=True,
            ),
            auditor=DecisionAuditor(scope=TenantScope(org_id="acme"), recorder=recorder),
            clock=lambda: AT,
        ),
        clock=lambda: AT,
    )

    outcome = await gate.decide(_proposed_restart())

    assert not outcome.permitted
    assert executor.calls == []
    # The "would have done" record: the operation itself, in the reason an
    # operator reads and in the audit event that outlives the process.
    assert "pct reboot 110" in outcome.reason
    assert "simulated" in outcome.reason
    assert recorder.events
    assert recorder.events[-1].detail.get("dry_run") is True


def _proposed_restart() -> RemediationAction:
    """Return the action the conclusion's first remediation step describes."""
    return RemediationAction(
        action_id="act-adguard-restart",
        capability="proxmox_restart_guest",
        target=RemediationTarget(identifier="ct-110", environment="hal9000", kind="container"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="system:webhook",
        team_node_id="platform",
        risk_class="low",
        rollback_planned=True,
        operation="pct reboot 110",
    )


# --- Reproducible from its own events ----------------------------------------------


async def test_the_whole_investigation_replays_from_its_recorded_events() -> None:
    """Acceptance 6, against this feature's own content rather than in the abstract."""
    sink = RecordingSink()

    run = await _investigate(sink=sink)

    view = replay(
        [type(event).from_record(record) for event, record in zip(sink.events, sink.records())]
    )

    assert [found.stage for found in view.stages] == list(STAGE_ORDER)
    assert all(found.completed for found in view.stages)
    assert [call.capability for call in view.tool_calls] == [
        "proxmox_guest_state",
        "prometheus_guest_memory",
        "loki_guest_lines",
    ]
    assert view.evidence_ids == tuple(entry.id for entry in run.state.evidence.entries)
    assert view.result == run.outcome.headline  # type: ignore[union-attr]


def test_the_scenario_window_is_pinned_rather_than_read_off_the_clock() -> None:
    """A suite whose two runs disagree is a suite that proves nothing."""
    first = pressure_alert()
    second = pressure_alert()

    assert first == second
    assert isinstance(AT, datetime)
    assert AT.tzinfo is UTC
    assert first["alerts"][0]["startsAt"] == (AT - timedelta(minutes=12)).isoformat()  # type: ignore[index]


def test_the_estate_the_scenario_resolves_against_is_declared_not_discovered() -> None:
    """The fixture states the numbers the assertions above depend on."""
    attributes: dict[str, Any] = dict(PRESSURE_ESTATE[0].attributes)
    assert attributes["vmid"] == 110
    assert attributes["zone"] == "apps"
