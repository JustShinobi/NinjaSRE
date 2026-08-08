"""A whole deployment the surfaces can be driven against, in memory.

The CLI and the REPL are the two surfaces where "does it work" is a question
about the seam rather than about the platform behind it. So the platform behind
it is this: a set of services satisfying ``LocalServices``, holding dictionaries,
returning the payload shapes the commands render.

It counts LLM calls. Not because it makes any — it makes none — but because
the contract suite asserts that a slash command produces zero, and an assertion
about a number nothing counts is not an assertion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.llm import DEFAULT_MODEL_ID, LOCAL_PROVIDERS, SUPPORTED_PROVIDERS
from surfaces.cli.client import (
    EstateFilter,
    IncidentFilter,
    InvestigationRequest,
    ScheduleRequest,
)
from surfaces.cli.models import (
    CheckState,
    ConfigChange,
    ConfigEntry,
    ConfigView,
    CostReport,
    CredentialFieldSpec,
    DetectionState,
    DetectorRecord,
    DiagnosticCheck,
    DiagnosticReport,
    DryRunRecord,
    EstateResource,
    EstateResourceDetail,
    EstateSummaryReport,
    EstateTransition,
    IncidentDetailRecord,
    IncidentRecord,
    IncidentSubjectRecord,
    IncidentTimelineRecord,
    IntegrationStatus,
    InvestigationOutcome,
    MemoryHit,
    MemoryStats,
    ObservationRecord,
    ProviderStatus,
    RunDetail,
    RunSummary,
    ScheduleSummary,
    StageReport,
)

EPOCH = datetime(2026, 3, 14, 9, 0, tzinfo=UTC)

#: What each fixture integration declares it needs. Two fields for one of them
#: so the wizard's optional-field path is exercised by something real.
CREDENTIAL_FIELDS: Mapping[str, tuple[CredentialFieldSpec, ...]] = {
    "datadog": (
        CredentialFieldSpec(name="api_key", label="API key", secret=True),
        CredentialFieldSpec(name="app_key", label="Application key", secret=True),
        CredentialFieldSpec(
            name="site", label="Site", secret=False, required=False, help="datadoghq.eu"
        ),
    ),
    "kubernetes": (CredentialFieldSpec(name="kubeconfig", label="Kubeconfig", secret=True),),
    "anthropic": (CredentialFieldSpec(name="ANTHROPIC_API_KEY", label="API key", secret=True),),
    "ollama": (
        CredentialFieldSpec(name="OLLAMA_BASE_URL", label="Base URL", secret=False, required=True),
    ),
}


@dataclass(slots=True)
class FakeServices:
    """An in-memory platform, satisfying what the CLI asks of a local deployment."""

    run_details: dict[str, RunDetail] = field(default_factory=dict)
    events: dict[str, tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    scheduled: dict[str, ScheduleSummary] = field(default_factory=dict)
    config: dict[str, ConfigView] = field(default_factory=dict)
    resources: dict[str, EstateResource] = field(default_factory=dict)
    incident_records: dict[str, IncidentRecord] = field(default_factory=dict)
    detector_records: dict[str, DetectorRecord] = field(default_factory=dict)
    observation_records: tuple[ObservationRecord, ...] = ()
    detection: DetectionState = field(default_factory=DetectionState)
    episodes: tuple[MemoryHit, ...] = ()
    provider_states: dict[str, ProviderStatus] = field(default_factory=dict)
    integration_states: dict[str, IntegrationStatus] = field(default_factory=dict)
    checks: tuple[DiagnosticCheck, ...] = ()
    #: Every credential this deployment was given, by integration. Field names
    #: and values both, so a test can assert the values reached the vault path
    #: and nothing else.
    vault: dict[str, dict[str, str]] = field(default_factory=dict)
    #: How many times anything asked a model for anything. Stays at zero for
    #: every slash command, which is what the contract suite asserts.
    llm_calls: int = 0
    started: list[InvestigationRequest] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    # -- investigation --------------------------------------------------------

    async def investigate(self, request: InvestigationRequest) -> InvestigationOutcome:
        self.started.append(request)
        self.llm_calls += 1
        run_id = f"run-{len(self.started):04d}"
        detail = RunDetail(
            run=RunSummary(
                run_id=run_id,
                status="completed",
                trigger="cli",
                objective=request.objective or "alert",
                team_node_id=request.team_node_id,
                started_at=EPOCH,
                ended_at=EPOCH + timedelta(minutes=3),
            ),
            stages=(StageReport(stage="intake", started_at=EPOCH, ended_at=EPOCH),),
            evidence_ids=("ev-1", "ev-2"),
            result="the deploy at 14:02 halved the connection pool",
            cost=CostReport(runs=1, turns=4, prompt_tokens=900, completion_tokens=300, cost=0.02),
        )
        self.run_details[run_id] = detail
        return InvestigationOutcome(
            run_id=run_id,
            status="completed",
            summary=detail.result,
            evidence_count=len(detail.evidence_ids),
            cost=detail.cost,
        )

    async def runs(self, *, team_node_id: str, limit: int) -> tuple[RunSummary, ...]:
        listed = [
            detail.run
            for detail in self.run_details.values()
            if not team_node_id or detail.run.team_node_id == team_node_id
        ]
        listed.sort(key=lambda run: run.started_at or EPOCH, reverse=True)
        return tuple(listed[:limit])

    async def run_detail(self, run_id: str) -> RunDetail | None:
        return self.run_details.get(run_id)

    async def run_events(self, run_id: str) -> tuple[Mapping[str, Any], ...]:
        return self.events.get(run_id, ())

    async def run_cost(self, *, team_node_id: str, limit: int) -> CostReport:
        listed = await self.runs(team_node_id=team_node_id, limit=limit)
        total = CostReport()
        for summary in listed:
            found = self.run_details[summary.run_id].cost
            total = CostReport(
                runs=total.runs + found.runs,
                turns=total.turns + found.turns,
                prompt_tokens=total.prompt_tokens + found.prompt_tokens,
                completion_tokens=total.completion_tokens + found.completion_tokens,
                cost=total.cost + found.cost,
                unpriced_runs=total.unpriced_runs + found.unpriced_runs,
            )
        return total

    # -- configuration --------------------------------------------------------

    async def effective_config(self, node_id: str) -> ConfigView:
        return self.config.get(node_id, ConfigView(node_id=node_id))

    async def write_config(self, node_id: str, path: str, value: str) -> ConfigChange:
        view = await self.effective_config(node_id)
        before = next((entry.value for entry in view.entries if entry.path == path), "")
        entries = tuple(entry for entry in view.entries if entry.path != path) + (
            ConfigEntry(path=path, value=value, source_node_id=node_id),
        )
        self.config[node_id] = ConfigView(node_id=node_id, entries=entries)
        return ConfigChange(node_id=node_id, path=path, before=before, after=value, applied=True)

    # -- schedules ------------------------------------------------------------

    async def schedules(self, *, team_node_id: str) -> tuple[ScheduleSummary, ...]:
        return tuple(
            schedule
            for schedule in self.scheduled.values()
            if not team_node_id or schedule.team_node_id == team_node_id
        )

    async def create_schedule(self, request: ScheduleRequest) -> ScheduleSummary:
        job_id = request.job_id or f"job-{len(self.scheduled) + 1:03d}"
        created = ScheduleSummary(
            job_id=job_id,
            objective=request.objective,
            cron=request.cron,
            timezone=request.timezone,
            team_node_id=request.team_node_id,
            next_fire_at=EPOCH + timedelta(hours=1),
        )
        self.scheduled[job_id] = created
        return created

    async def delete_schedule(self, job_id: str) -> bool:
        return self.scheduled.pop(job_id, None) is not None

    # -- memory ---------------------------------------------------------------

    async def recall(self, query: str, *, limit: int) -> tuple[MemoryHit, ...]:
        matched = tuple(
            hit for hit in self.episodes if query.lower() in f"{hit.title} {hit.root_cause}".lower()
        )
        return matched[:limit]

    async def corpus(self) -> MemoryStats:
        return MemoryStats(
            episodes=len(self.episodes),
            components=len({found for hit in self.episodes for found in hit.components}),
            mean_effectiveness=0.72,
            oldest_at=EPOCH if self.episodes else None,
            newest_at=EPOCH if self.episodes else None,
        )

    # -- providers and integrations -------------------------------------------

    async def providers(self) -> tuple[ProviderStatus, ...]:
        return tuple(
            self.provider_states.get(
                name,
                ProviderStatus(provider_id=name, local=name in LOCAL_PROVIDERS),
            )
            for name in SUPPORTED_PROVIDERS
        )

    async def check_provider(self, provider_id: str) -> ProviderStatus:
        known = self.provider_states.get(provider_id)
        if known is None:
            return ProviderStatus(
                provider_id=provider_id, detail="no credential is stored for this provider"
            )
        self.provider_states[provider_id] = ProviderStatus(
            provider_id=provider_id,
            configured=known.configured,
            local=known.local,
            verified=known.configured,
            model_id=known.model_id or DEFAULT_MODEL_ID,
            detail="a request went out and came back" if known.configured else "not configured",
        )
        return self.provider_states[provider_id]

    async def integrations(self) -> tuple[IntegrationStatus, ...]:
        return tuple(
            self.integration_states.get(name, IntegrationStatus(integration=name))
            for name in sorted(CREDENTIAL_FIELDS)
        )

    async def credential_schema(self, integration: str) -> tuple[CredentialFieldSpec, ...]:
        return CREDENTIAL_FIELDS.get(integration, ())

    async def store_credential(
        self, integration: str, values: Mapping[str, str]
    ) -> IntegrationStatus:
        self.vault[integration] = dict(values)
        stored = IntegrationStatus(
            integration=integration,
            configured=True,
            credential_state="stored",
            detail="written to the vault",
        )
        self.integration_states[integration] = stored
        if integration in SUPPORTED_PROVIDERS:
            self.provider_states[integration] = ProviderStatus(
                provider_id=integration,
                configured=True,
                local=integration in LOCAL_PROVIDERS,
                model_id=DEFAULT_MODEL_ID,
            )
        return stored

    async def check_integration(self, integration: str) -> IntegrationStatus:
        known = self.integration_states.get(integration)
        if known is None or not known.configured:
            return IntegrationStatus(
                integration=integration, detail="no credential is stored", credential_state="absent"
            )
        verified = IntegrationStatus(
            integration=integration,
            configured=True,
            healthy=True,
            credential_state="active",
            detail="the vendor answered",
        )
        self.integration_states[integration] = verified
        return verified

    async def incidents(self, query: IncidentFilter) -> tuple[IncidentRecord, ...]:
        matched = [
            incident
            for incident in self.incident_records.values()
            if (not query.live_only or incident.closed_at is None)
            and (not query.states or incident.state in query.states)
            and (not query.severities or incident.severity in query.severities)
            and (not query.detectors or incident.detector in query.detectors)
            and (not query.subject or query.subject in incident.subjects)
        ]
        matched.sort(key=lambda incident: incident.incident_id, reverse=True)
        return tuple(matched[: query.limit])

    async def incident(self, incident_id: str) -> IncidentDetailRecord | None:
        found = self.incident_records.get(incident_id)
        if found is None:
            return None
        return IncidentDetailRecord(
            incident=found,
            subjects=tuple(
                IncidentSubjectRecord(
                    resource_id=resource_id,
                    detail=found.summary,
                    evidence={"used_percent": "95.65"},
                    observed_at=found.opened_at,
                )
                for resource_id in found.subjects
            ),
            timeline=(
                IncidentTimelineRecord(
                    at=found.opened_at,
                    kind="opened",
                    actor="system:observation",
                    cause=found.summary,
                ),
            ),
            actions=(),
        )

    async def close_incident(
        self, incident_id: str, *, reason: str, resolved: bool
    ) -> IncidentRecord:
        found = self.incident_records[incident_id]
        closed = replace(
            found,
            state="resolved" if resolved else "closed_without_action",
            closed_at=EPOCH,
            close_reason=reason,
        )
        self.incident_records[incident_id] = closed
        return closed

    async def suppress_incident(
        self, incident_id: str, *, rule: str, reason: str
    ) -> IncidentRecord:
        found = self.incident_records[incident_id]
        suppressed = replace(
            found,
            state="suppressed",
            closed_at=EPOCH,
            close_reason=reason,
            suppressed_by=rule,
        )
        self.incident_records[incident_id] = suppressed
        return suppressed

    async def detection_state(self) -> DetectionState:
        return self.detection

    async def detectors(self) -> tuple[DetectorRecord, ...]:
        return tuple(self.detector_records[key] for key in sorted(self.detector_records))

    async def observations(self, *, limit: int) -> tuple[ObservationRecord, ...]:
        return self.observation_records[:limit]

    async def set_detector_enabled(self, detector_id: str, *, enabled: bool) -> DetectorRecord:
        found = self.detector_records[detector_id]
        updated = replace(found, enabled=enabled)
        self.detector_records[detector_id] = updated
        return updated

    async def detector_dry_run(self, detector_id: str) -> DryRunRecord:
        seen = tuple(entry for entry in self.observation_records if entry.detector == detector_id)
        return DryRunRecord(
            detector_id=detector_id,
            would_fire=any(entry.verdict == "firing" for entry in seen),
            observations=seen,
            fired=False,
        )

    async def estate(self, query: EstateFilter) -> tuple[EstateResource, ...]:
        matched = [
            resource
            for resource in self.resources.values()
            if (query.include_absent or not resource.absent_since)
            and (not query.kinds or resource.kind in query.kinds)
            and (not query.health or resource.health in query.health)
            and (not query.sources or resource.source in query.sources)
            and (not query.labels or set(query.labels) <= set(resource.labels))
            and (not query.parent_id or resource.parent_id == query.parent_id)
        ]
        matched.sort(key=lambda resource: resource.resource_id)
        return tuple(matched[: query.limit])

    async def estate_totals(self) -> EstateSummaryReport:
        present = [
            resource for resource in self.resources.values() if resource.absent_since is None
        ]
        by_kind: dict[str, int] = {}
        by_health: dict[str, int] = {}
        for resource in present:
            by_kind[resource.kind] = by_kind.get(resource.kind, 0) + 1
            by_health[resource.health] = by_health.get(resource.health, 0) + 1
        return EstateSummaryReport(
            total=len(present),
            problems=sum(1 for resource in present if resource.health in {"degraded", "unhealthy"}),
            maintenance=sum(1 for resource in present if resource.health == "maintenance"),
            absent=len(self.resources) - len(present),
            captured_at=EPOCH,
            by_kind=by_kind,
            by_health=by_health,
            by_source={},
        )

    async def resource(self, resource_id: str) -> EstateResourceDetail | None:
        found = self.resources.get(resource_id)
        if found is None:
            return None
        return EstateResourceDetail(
            resource=found,
            rule="provider_status",
            raw_status=found.stored_health,
            explanation=found.explanation,
            freshness_seconds=3600,
            rollup_rule="own_only",
            transitions=(
                EstateTransition(occurred_at=EPOCH, state=found.health, rule="provider_status"),
            ),
            children=tuple(
                child for child in self.resources.values() if child.parent_id == resource_id
            ),
        )

    async def open_maintenance(
        self, resource_id: str, *, until: datetime, reason: str
    ) -> EstateResource:
        found = self.resources[resource_id]
        updated = replace(
            found, health="maintenance", maintenance_until=until, maintenance_reason=reason
        )
        self.resources[resource_id] = updated
        return updated

    async def close_maintenance(self, resource_id: str) -> EstateResource:
        found = self.resources[resource_id]
        updated = replace(
            found,
            health=found.stored_health or "unknown",
            maintenance_until=None,
            maintenance_reason="",
        )
        self.resources[resource_id] = updated
        return updated

    async def diagnostics(self) -> DiagnosticReport:
        if self.checks:
            return DiagnosticReport(checks=self.checks, version="0.1.0")

        provider_ok = any(status.configured for status in await self.providers())
        return DiagnosticReport(
            checks=(
                DiagnosticCheck(
                    name="provider",
                    state=CheckState.OK if provider_ok else CheckState.FAILED,
                    detail="a provider is configured" if provider_ok else "no provider configured",
                    remedy="" if provider_ok else "run 'ninjasre onboard'",
                ),
            ),
            version="0.1.0",
        )


def seeded() -> FakeServices:
    """Return a deployment with something in it, for the reading commands."""
    services = FakeServices()
    services.run_details = {
        "run-0001": RunDetail(
            run=RunSummary(
                run_id="run-0001",
                status="completed",
                trigger="cli",
                objective="checkout latency doubled after the 14:02 deploy",
                team_node_id="payments",
                started_at=EPOCH,
                ended_at=EPOCH + timedelta(minutes=4),
            ),
            stages=(
                StageReport(stage="intake", started_at=EPOCH, ended_at=EPOCH),
                StageReport(stage="diagnose", started_at=EPOCH, ended_at=EPOCH, failed=False),
            ),
            evidence_ids=("ev-1", "ev-2", "ev-3"),
            result="the deploy halved the connection pool",
            cost=CostReport(runs=1, turns=6, prompt_tokens=4200, completion_tokens=900, cost=0.11),
        )
    }
    services.events = {
        "run-0001": (
            {"sequence": 1, "kind": "stage_start", "stage": "intake", "text": ""},
            {"sequence": 2, "kind": "thought", "text": "the timing lines up with a deploy"},
            {"sequence": 3, "kind": "evidence", "evidence_id": "ev-1", "text": ""},
            {"sequence": 4, "kind": "result", "text": "the deploy halved the connection pool"},
        )
    }
    services.config = {
        "payments": ConfigView(
            node_id="payments",
            entries=(
                ConfigEntry(path="settings.model", value="claude-sonnet-5", source_node_id="root"),
                ConfigEntry(path="settings.masking", value="standard", source_node_id="payments"),
            ),
        ),
        "root": ConfigView(
            node_id="root",
            entries=(
                ConfigEntry(path="settings.model", value="claude-sonnet-5", source_node_id="root"),
                ConfigEntry(path="settings.masking", value="strict", source_node_id="root"),
            ),
        ),
    }
    services.incident_records = {
        "inc-0001": IncidentRecord(
            incident_id="inc-0001",
            title="Datastore near full",
            summary="store-cove is 95.65% full",
            state="open",
            severity="critical",
            origin="detector",
            detector="datastore-near-full",
            subjects=("store-cove", "store-ridge"),
            opened_at=EPOCH,
        )
    }
    services.detector_records = {
        "datastore-near-full": DetectorRecord(
            detector_id="datastore-near-full",
            name="Datastore near full",
            description="A datastore that fills stops every guest on it at once.",
            severity="critical",
            signal="storage.used_percent",
            enabled=True,
            subjects_covered=2,
            subjects_total=3,
            last_verdict="firing",
            last_evaluated_at=EPOCH,
        )
    }
    services.observation_records = (
        ObservationRecord(
            detector="datastore-near-full",
            subject="store-cove",
            verdict="firing",
            detail="store-cove is 95.65% full",
            evidence={"storage.used_percent": "95.65"},
            observed_at=EPOCH,
        ),
    )
    services.resources = {
        "res-node": EstateResource(
            resource_id="res-node",
            kind="node",
            display_name="pve1",
            health="healthy",
            stored_health="healthy",
            source="proxmox",
            sources=("proxmox",),
            native_id="node/pve1",
            labels=("site:home",),
            last_seen_at=EPOCH,
            explanation="the provider reported 'online', which maps to healthy.",
        ),
        "res-guest": EstateResource(
            resource_id="res-guest",
            kind="virtual_machine",
            display_name="checkout",
            health="unhealthy",
            stored_health="unhealthy",
            source="proxmox",
            sources=("proxmox",),
            native_id="qemu/101",
            parent_id="res-node",
            labels=("env:prod",),
            last_seen_at=EPOCH,
            explanation="the provider reported 'stopped', which maps to unhealthy.",
        ),
    }
    services.episodes = (
        MemoryHit(
            episode_id="ep-1",
            title="connection pool exhaustion in checkout",
            score=0.91,
            components=("checkout", "postgres"),
            occurred_at=EPOCH,
            root_cause="a deploy halved the pool size",
        ),
    )
    return services


__all__ = [
    "CREDENTIAL_FIELDS",
    "EPOCH",
    "FakeServices",
    "seeded",
]
