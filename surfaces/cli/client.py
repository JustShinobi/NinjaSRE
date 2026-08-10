"""What a command talks to: this process, or a deployment somewhere else.

Local or remote, in one protocol. A command never knows which it got — it holds a
``PlatformClient``, calls a method, and renders what comes back. That is what
makes "point the CLI at the cluster" a flag rather than a second implementation
of every command, and it is why the protocol is stated in terms of the payload
shapes in ``models`` rather than in terms of the platform's own types: a
transport that had to reconstruct a ``MemoryEpisode`` over HTTP would be
carrying the whole domain across the wire to render six fields of it.

Two implementations ship.

``LocalClient``
    Reads the platform in process, through the ports it already exposes. What a
    single-host deployment runs, and what starts what it needs.

``RemoteClient``
    A thin client over the REST API. Uses the standard library's HTTP client
    rather than adding a dependency, because the CLI is the piece an operator
    installs on a laptop and every megabyte there is one they did not ask for.

``select_client`` decides between them from configuration and a flag, once, at
the application root — so nothing below has a branch on it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.surfaces import (
    JSON_SCHEMA_VERSION,
    TRANSPORT_LOCAL,
    TRANSPORT_REMOTE,
)
from platform.credentials.fields import CredentialFieldSpec
from platform.observability.logging import get_logger
from surfaces.cli.errors import (
    ApprovalRequiredError,
    CliError,
    ConfigurationError,
    DeniedError,
    NotFoundError,
    UnavailableError,
)
from surfaces.cli.models import (
    AutonomyBoundsRecord,
    AutonomyExplanation,
    AutonomyPolicyRecord,
    AutonomyRuleRecord,
    ConfigChange,
    ConfigDelta,
    ConfigDiff,
    ConfigEntry,
    ConfigView,
    ConsideredRuleRecord,
    CostReport,
    DetectionState,
    DetectorRecord,
    DiagnosticReport,
    DryRunRecord,
    EffectivenessRecord,
    EstateHealthSignal,
    EstateReference,
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
    KillSwitchRecord,
    MemoryHit,
    MemoryStats,
    ObservationRecord,
    OverrideRecord,
    PolicyPreviewRecord,
    PreviewedActionRecord,
    ProviderStatus,
    RecurringProblemRecord,
    RemediationOutcomeRecord,
    RunDetail,
    RunReplay,
    RunSummary,
    ScheduleSummary,
    SpendReport,
    SuspensionRecord,
    aggregate_spend,
)

logger = get_logger(__name__)

#: How long a remote call waits before reporting the deployment unreachable.
#: An investigation is not made through this client — it is started through it
#: and watched over the event stream — so a request here is a control-plane
#: call and thirty seconds is generous.
REMOTE_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class InvestigationRequest:
    """One investigation, as the operator stated it.

    Either an alert document or a description in words. Both reach the same
    pipeline: an alert is a description somebody's monitoring wrote.
    """

    objective: str = ""
    alert: Mapping[str, Any] | None = None
    alert_source: str = ""
    team_node_id: str = ""
    report_path: str = ""

    def __post_init__(self) -> None:
        if not self.objective.strip() and self.alert is None:
            raise ValueError(
                "an investigation needs an alert or a description. Starting one with "
                "neither would produce a run with nothing to investigate."
            )


@dataclass(frozen=True, slots=True)
class IncidentFilter:
    """What an incident listing is narrowed by.

    One record rather than six keyword arguments, for the reason
    ``EstateFilter`` is one: the CLI, the console and the gateway all build the
    same filter, and three signatures spelling it out is three that drift.
    """

    states: tuple[str, ...] = ()
    severities: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ()
    subject: str = ""
    live_only: bool = False
    limit: int = 50


@dataclass(frozen=True, slots=True)
class EstateFilter:
    """What an estate listing is narrowed by.

    One record rather than eight keyword arguments, for the reason
    ``EstateQuery`` is one in the storage layer: the CLI, the console and the
    gateway all build the same filter, and three signatures spelling it out is
    three signatures that drift.
    """

    kinds: tuple[str, ...] = ()
    health: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    team_node_id: str = ""
    parent_id: str = ""
    include_absent: bool = False
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ScheduleRequest:
    """A recurring investigation, as the operator stated it."""

    objective: str
    cron: str
    timezone: str = "UTC"
    team_node_id: str = ""
    job_id: str = ""


@runtime_checkable
class PlatformClient(Protocol):
    """Everything the CLI asks of a deployment, local or remote."""

    @property
    def transport(self) -> str:
        """Return which kind of deployment this talks to."""

    async def investigate(self, request: InvestigationRequest) -> InvestigationOutcome:
        """Run one investigation and return what it produced."""

    async def list_runs(self, *, team_node_id: str = "", limit: int = 20) -> tuple[RunSummary, ...]:
        """Return the most recent runs, newest first."""

    async def show_run(self, run_id: str) -> RunDetail:
        """Return one run in full.

        Raises:
            NotFoundError: no run carries that identifier.
        """

    async def replay_run(self, run_id: str) -> RunReplay:
        """Return ``run_id`` rebuilt from its recorded events alone."""

    async def cost_of_runs(self, *, team_node_id: str = "", limit: int = 20) -> CostReport:
        """Return what the runs a listing would show consumed."""

    async def spend(
        self,
        *,
        team_node_id: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> SpendReport:
        """Return what a period cost, per team and per run."""

    async def show_config(self, node_id: str) -> ConfigView:
        """Return ``node_id``'s effective configuration, every value attributed."""

    async def set_config(self, node_id: str, path: str, value: str) -> ConfigChange:
        """Set one configuration value and report what happened to it."""

    async def diff_config(self, left_node_id: str, right_node_id: str) -> ConfigDiff:
        """Return how two nodes' effective configuration differ."""

    async def list_schedules(self, *, team_node_id: str = "") -> tuple[ScheduleSummary, ...]:
        """Return the scheduled investigations."""

    async def add_schedule(self, request: ScheduleRequest) -> ScheduleSummary:
        """Create a scheduled investigation and return it."""

    async def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled investigation, reporting whether one went."""

    async def list_estate(self, query: EstateFilter) -> tuple[EstateResource, ...]:
        """Return the resources matching ``query``, by identifier."""

    async def list_incidents(self, query: IncidentFilter) -> tuple[IncidentRecord, ...]:
        """Return the incidents matching ``query``, most recently opened first."""

    async def show_incident(self, incident_id: str) -> IncidentDetailRecord:
        """Return one incident with its timeline, or raise if there is none."""

    async def close_incident(
        self, incident_id: str, *, reason: str, resolved: bool = False
    ) -> IncidentRecord:
        """Close an incident with a reason and return it as it now reads."""

    async def suppress_incident(
        self, incident_id: str, *, rule: str, reason: str
    ) -> IncidentRecord:
        """Close an incident as suppressed, naming what covered it."""

    async def list_remediations(
        self,
        *,
        resource: str = "",
        capability: str = "",
        condition: str = "",
        limit: int = 25,
    ) -> tuple[RemediationOutcomeRecord, ...]:
        """Return what the deployment changed, most recent first."""

    async def remediation_effectiveness(
        self, *, capability: str = "", resource: str = "", condition: str = ""
    ) -> EffectivenessRecord:
        """Return how often this has worked, sliced by whatever was named."""

    async def list_recurring_problems(
        self, *, live_only: bool = True
    ) -> tuple[RecurringProblemRecord, ...]:
        """Return the patterns the deployment has raised, most recent first."""

    async def close_recurring_problem(
        self, problem_id: str, *, change: str
    ) -> RecurringProblemRecord:
        """Close a pattern, naming the change that closed it."""

    async def list_suspensions(self, *, live_only: bool = True) -> tuple[SuspensionRecord, ...]:
        """Return the resources autonomy is suspended on."""

    async def clear_suspension(self, resource_id: str, *, reason: str) -> SuspensionRecord:
        """Let autonomy resume on a resource, recording who looked and what they found."""

    async def detection_state(self) -> DetectionState:
        """Return whether detection is paused for this team, and why."""

    async def autonomy_policy(self, node_id: str) -> AutonomyPolicyRecord:
        """Return what ``node_id`` may do without asking, inheritance applied."""

    async def apply_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any]
    ) -> AutonomyPolicyRecord:
        """Replace ``node_id``'s posture and return what it now resolves to."""

    async def preview_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any], *, days: float
    ) -> PolicyPreviewRecord:
        """Return what a change would have decided differently, storing nothing."""

    async def explain_autonomy(
        self, node_id: str, action: Mapping[str, Any]
    ) -> AutonomyExplanation:
        """Return what would happen to one action, and every reason it would."""

    async def autonomy_bounds(self, node_id: str) -> AutonomyBoundsRecord:
        """Return the freezes, budgets, overrides and stop bounding ``node_id``."""

    async def set_autonomy_dry_run(self, node_id: str, *, enabled: bool) -> AutonomyPolicyRecord:
        """Turn simulation on or off for everything ``node_id`` resolves."""

    async def grant_autonomy_override(
        self, node_id: str, request: Mapping[str, Any]
    ) -> OverrideRecord:
        """Raise autonomy in a scope until it expires, and record who asked."""

    async def engage_kill_switch(self, *, reason: str, scope: str = "") -> KillSwitchRecord:
        """Stop every automated write, immediately."""

    async def release_kill_switch(self, *, scope: str = "") -> KillSwitchRecord:
        """Let automated writes happen again, for one scope."""

    async def list_detectors(self) -> tuple[DetectorRecord, ...]:
        """Return every declared detector and what it concludes now."""

    async def list_observations(self, *, limit: int = 50) -> tuple[ObservationRecord, ...]:
        """Return what every enabled detector concludes right now."""

    async def set_detector_enabled(self, detector_id: str, *, enabled: bool) -> DetectorRecord:
        """Turn a detector on or off and return it as it now reads."""

    async def dry_run_detector(self, detector_id: str) -> DryRunRecord:
        """Return what a detector would conclude, firing nothing."""

    async def estate_summary(self) -> EstateSummaryReport:
        """Return the estate in the numbers a first screen shows."""

    async def show_resource(self, resource_id: str) -> EstateResourceDetail:
        """Return one resource's state, why it is in it, and its history."""

    async def set_maintenance(
        self, resource_id: str, *, until: datetime, reason: str
    ) -> EstateResource:
        """Suppress a resource from the problem count until ``until``."""

    async def clear_maintenance(self, resource_id: str) -> EstateResource:
        """End a resource's maintenance window now."""

    async def search_memory(self, query: str, *, limit: int = 10) -> tuple[MemoryHit, ...]:
        """Return the episodes matching ``query``, best first."""

    async def memory_stats(self) -> MemoryStats:
        """Return what the episodic corpus holds."""

    async def list_providers(self) -> tuple[ProviderStatus, ...]:
        """Return every supported provider and this deployment's state for it."""

    async def verify_provider(self, provider_id: str) -> ProviderStatus:
        """Check one provider end to end and return what was found."""

    async def list_integrations(self) -> tuple[IntegrationStatus, ...]:
        """Return every known integration and its current state."""

    async def credential_fields(self, integration: str) -> tuple[CredentialFieldSpec, ...]:
        """Return what ``integration`` needs, as a prompt can ask for it.

        Read from the integration's own credential schema rather than held
        here, which is what makes adding a vendor a package rather than an edit
        to the wizard.
        """

    async def store_integration_credential(
        self, integration: str, values: Mapping[str, str]
    ) -> IntegrationStatus:
        """Write ``values`` to the vault for ``integration``.

        The values never touch a config file, a command argument, or the
        process environment. This is the only path credentials take into the
        platform from the CLI.
        """

    async def verify_integration(self, integration: str) -> IntegrationStatus:
        """Check one integration's credential and connectivity."""

    async def diagnose(self) -> DiagnosticReport:
        """Return what is configured, reachable, and healthy."""


async def _spend_of(
    client: PlatformClient,
    *,
    team_node_id: str,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> SpendReport:
    """Return the spend report for ``client``, built from the runs it can see.

    Written once and used by both implementations, over the two calls each
    already answers. A remote deployment therefore pays one request per run,
    which is the honest cost of a report the API does not aggregate — and it is
    a report an operator asks for occasionally, not a page they refresh.

    A run whose detail has gone is skipped rather than fatal. A trace that was
    purged is a run whose cost is no longer knowable, and refusing to report the
    period because of it would make retention deletions look like outages.
    """
    summaries = await client.list_runs(team_node_id=team_node_id, limit=limit)
    entries: list[tuple[RunSummary, CostReport]] = []
    for summary in summaries:
        try:
            detail = await client.show_run(summary.run_id)
        except NotFoundError:
            continue
        entries.append((summary, detail.cost))
    return aggregate_spend(entries, since=since, until=until)


# --- The local client --------------------------------------------------------


@runtime_checkable
class LocalServices(Protocol):
    """What a local deployment hands the CLI.

    A protocol rather than a concrete composition root: the CLI is tier 1 and
    the composition of a running platform is a deployment concern (feature
    030). This is the seam, and it is also what lets the whole CLI be driven in
    a test by a set of in-memory services rather than a database.
    """

    async def investigate(self, request: InvestigationRequest) -> InvestigationOutcome:
        """Run one investigation through the canonical runtime."""

    async def runs(self, *, team_node_id: str, limit: int) -> tuple[RunSummary, ...]:
        """Return the recent runs."""

    async def run_detail(self, run_id: str) -> RunDetail | None:
        """Return one run in full, or ``None`` if there is no such run."""

    async def run_events(self, run_id: str) -> tuple[Mapping[str, Any], ...]:
        """Return every recorded event of ``run_id``, in sequence order."""

    async def run_cost(self, *, team_node_id: str, limit: int) -> CostReport:
        """Return what the recent runs consumed."""

    async def effective_config(self, node_id: str) -> ConfigView:
        """Return one node's effective configuration."""

    async def write_config(self, node_id: str, path: str, value: str) -> ConfigChange:
        """Attempt one configuration write."""

    async def schedules(self, *, team_node_id: str) -> tuple[ScheduleSummary, ...]:
        """Return the scheduled investigations."""

    async def create_schedule(self, request: ScheduleRequest) -> ScheduleSummary:
        """Create one scheduled investigation."""

    async def delete_schedule(self, job_id: str) -> bool:
        """Remove one scheduled investigation."""

    async def estate(self, query: EstateFilter) -> tuple[EstateResource, ...]:
        """Return the resources matching ``query``."""

    async def estate_totals(self) -> EstateSummaryReport:
        """Return the estate's counts."""

    async def resource(self, resource_id: str) -> EstateResourceDetail | None:
        """Return one resource's detail, or ``None``."""

    async def open_maintenance(
        self, resource_id: str, *, until: datetime, reason: str
    ) -> EstateResource:
        """Open a maintenance window and return the resource as it now reads."""

    async def close_maintenance(self, resource_id: str) -> EstateResource:
        """Close a maintenance window and return the resource as it now reads."""

    async def incidents(self, query: IncidentFilter) -> tuple[IncidentRecord, ...]:
        """Return the incidents matching ``query``, most recently opened first."""

    async def incident(self, incident_id: str) -> IncidentDetailRecord | None:
        """Return one incident with its timeline, or ``None``."""

    async def close_incident(
        self, incident_id: str, *, reason: str, resolved: bool
    ) -> IncidentRecord:
        """Close an incident with a reason and return it as it now reads."""

    async def suppress_incident(
        self, incident_id: str, *, rule: str, reason: str
    ) -> IncidentRecord:
        """Close an incident as suppressed, naming what covered it."""

    async def remediations(
        self, *, resource: str, capability: str, condition: str, limit: int
    ) -> tuple[RemediationOutcomeRecord, ...]:
        """Return what the deployment changed, most recent first."""

    async def effectiveness(
        self, *, capability: str, resource: str, condition: str
    ) -> EffectivenessRecord:
        """Return how often this has worked."""

    async def recurring_problems(self, *, live_only: bool) -> tuple[RecurringProblemRecord, ...]:
        """Return the patterns the deployment has raised."""

    async def close_recurring_problem(
        self, problem_id: str, *, change: str
    ) -> RecurringProblemRecord | None:
        """Close a pattern, or return ``None`` when nobody raised it."""

    async def suspensions(self, *, live_only: bool) -> tuple[SuspensionRecord, ...]:
        """Return the resources autonomy is suspended on."""

    async def clear_suspension(self, resource_id: str, *, reason: str) -> SuspensionRecord | None:
        """Clear a suspension, or return ``None`` when there was none."""

    async def detection_state(self) -> DetectionState:
        """Return whether detection is paused for this team, and why."""

    async def autonomy_policy(self, node_id: str) -> AutonomyPolicyRecord:
        """Return what ``node_id`` may do without asking, inheritance applied."""

    async def apply_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any]
    ) -> AutonomyPolicyRecord:
        """Replace ``node_id``'s posture and return what it now resolves to."""

    async def preview_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any], *, days: float
    ) -> PolicyPreviewRecord:
        """Return what a change would have decided differently."""

    async def explain_autonomy(
        self, node_id: str, action: Mapping[str, Any]
    ) -> AutonomyExplanation:
        """Return what would happen to one action, and every reason it would."""

    async def autonomy_bounds(self, node_id: str) -> AutonomyBoundsRecord:
        """Return what is bounding ``node_id`` right now."""

    async def set_autonomy_dry_run(self, node_id: str, *, enabled: bool) -> AutonomyPolicyRecord:
        """Turn simulation on or off for everything ``node_id`` resolves."""

    async def grant_autonomy_override(
        self, node_id: str, request: Mapping[str, Any]
    ) -> OverrideRecord:
        """Raise autonomy in a scope until it expires."""

    async def engage_kill_switch(self, *, reason: str, scope: str = "") -> KillSwitchRecord:
        """Stop every automated write, immediately."""

    async def release_kill_switch(self, *, scope: str = "") -> KillSwitchRecord:
        """Let automated writes happen again, for one scope."""

    async def detectors(self) -> tuple[DetectorRecord, ...]:
        """Return every declared detector, its coverage, and what it concludes now."""

    async def observations(self, *, limit: int) -> tuple[ObservationRecord, ...]:
        """Return what every enabled detector concludes right now."""

    async def set_detector_enabled(self, detector_id: str, *, enabled: bool) -> DetectorRecord:
        """Turn a detector on or off and return it as it now reads."""

    async def detector_dry_run(self, detector_id: str) -> DryRunRecord:
        """Return what a detector would conclude against stored signals."""

    async def recall(self, query: str, *, limit: int) -> tuple[MemoryHit, ...]:
        """Return the episodes matching ``query``."""

    async def corpus(self) -> MemoryStats:
        """Return what the episodic corpus holds."""

    async def providers(self) -> tuple[ProviderStatus, ...]:
        """Return every supported provider and its state."""

    async def check_provider(self, provider_id: str) -> ProviderStatus:
        """Check one provider end to end."""

    async def integrations(self) -> tuple[IntegrationStatus, ...]:
        """Return every known integration and its state."""

    async def credential_schema(self, integration: str) -> tuple[CredentialFieldSpec, ...]:
        """Return the fields ``integration``'s credential schema declares."""

    async def store_credential(
        self, integration: str, values: Mapping[str, str]
    ) -> IntegrationStatus:
        """Write one integration's credential to the vault."""

    async def check_integration(self, integration: str) -> IntegrationStatus:
        """Check one integration's credential and connectivity."""

    async def diagnostics(self) -> DiagnosticReport:
        """Return what is configured, reachable, and healthy."""


@dataclass(frozen=True, slots=True)
class LocalClient:
    """Talks to the platform running in this process."""

    services: LocalServices

    @property
    def transport(self) -> str:
        """Return that this is an in-process deployment."""
        return TRANSPORT_LOCAL

    async def investigate(self, request: InvestigationRequest) -> InvestigationOutcome:
        """Run one investigation and return what it produced."""
        return await self.services.investigate(request)

    async def list_runs(self, *, team_node_id: str = "", limit: int = 20) -> tuple[RunSummary, ...]:
        """Return the most recent runs, newest first."""
        return await self.services.runs(team_node_id=team_node_id, limit=limit)

    async def show_run(self, run_id: str) -> RunDetail:
        """Return one run in full.

        Raises:
            NotFoundError: no run carries that identifier.
        """
        found = await self.services.run_detail(run_id)
        if found is None:
            raise NotFoundError(
                f"no run named {run_id!r}",
                remedy="list what there is with 'ninjasre runs list'",
            )
        return found

    async def replay_run(self, run_id: str) -> RunReplay:
        """Return ``run_id`` rebuilt from its recorded events alone."""
        events = await self.services.run_events(run_id)
        if not events:
            raise NotFoundError(
                f"no recorded events for run {run_id!r}",
                remedy="a run whose trace was purged cannot be replayed",
            )
        return RunReplay(run_id=run_id, events=events, view=await self.services.run_detail(run_id))

    async def cost_of_runs(self, *, team_node_id: str = "", limit: int = 20) -> CostReport:
        """Return what the runs a listing would show consumed."""
        return await self.services.run_cost(team_node_id=team_node_id, limit=limit)

    async def spend(
        self,
        *,
        team_node_id: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> SpendReport:
        """Return what a period cost, per team and per run."""
        return await _spend_of(
            self, team_node_id=team_node_id, since=since, until=until, limit=limit
        )

    async def show_config(self, node_id: str) -> ConfigView:
        """Return ``node_id``'s effective configuration, every value attributed."""
        return await self.services.effective_config(node_id)

    async def set_config(self, node_id: str, path: str, value: str) -> ConfigChange:
        """Set one configuration value and report what happened to it."""
        return await self.services.write_config(node_id, path, value)

    async def diff_config(self, left_node_id: str, right_node_id: str) -> ConfigDiff:
        """Return how two nodes' effective configuration differ."""
        left = await self.services.effective_config(left_node_id)
        right = await self.services.effective_config(right_node_id)
        return _diff_of(left, right)

    async def list_schedules(self, *, team_node_id: str = "") -> tuple[ScheduleSummary, ...]:
        """Return the scheduled investigations."""
        return await self.services.schedules(team_node_id=team_node_id)

    async def add_schedule(self, request: ScheduleRequest) -> ScheduleSummary:
        """Create a scheduled investigation and return it."""
        return await self.services.create_schedule(request)

    async def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled investigation, reporting whether one went."""
        return await self.services.delete_schedule(job_id)

    async def list_estate(self, query: EstateFilter) -> tuple[EstateResource, ...]:
        """Return the resources matching ``query``, by identifier."""
        return await self.services.estate(query)

    async def list_incidents(self, query: IncidentFilter) -> tuple[IncidentRecord, ...]:
        """Return the incidents matching ``query``, most recently opened first."""
        return await self.services.incidents(query)

    async def show_incident(self, incident_id: str) -> IncidentDetailRecord:
        """Return one incident with its timeline, or raise if there is none."""
        detail = await self.services.incident(incident_id)
        if detail is None:
            raise NotFoundError(
                f"no incident {incident_id!r} in this organisation",
                remedy="list what there is with 'ninjasre incidents list'",
            )
        return detail

    async def close_incident(
        self, incident_id: str, *, reason: str, resolved: bool = False
    ) -> IncidentRecord:
        """Close an incident with a reason and return it as it now reads."""
        return await self.services.close_incident(incident_id, reason=reason, resolved=resolved)

    async def suppress_incident(
        self, incident_id: str, *, rule: str, reason: str
    ) -> IncidentRecord:
        """Close an incident as suppressed, naming what covered it."""
        return await self.services.suppress_incident(incident_id, rule=rule, reason=reason)

    async def list_remediations(
        self,
        *,
        resource: str = "",
        capability: str = "",
        condition: str = "",
        limit: int = 25,
    ) -> tuple[RemediationOutcomeRecord, ...]:
        """Return what the deployment changed, most recent first."""
        return await self.services.remediations(
            resource=resource, capability=capability, condition=condition, limit=limit
        )

    async def remediation_effectiveness(
        self, *, capability: str = "", resource: str = "", condition: str = ""
    ) -> EffectivenessRecord:
        """Return how often this has worked, sliced by whatever was named."""
        return await self.services.effectiveness(
            capability=capability, resource=resource, condition=condition
        )

    async def list_recurring_problems(
        self, *, live_only: bool = True
    ) -> tuple[RecurringProblemRecord, ...]:
        """Return the patterns the deployment has raised, most recent first."""
        return await self.services.recurring_problems(live_only=live_only)

    async def close_recurring_problem(
        self, problem_id: str, *, change: str
    ) -> RecurringProblemRecord:
        """Close a pattern, naming the change that closed it.

        Raises:
            NotFoundError: no pattern carries that identifier.
        """
        closed = await self.services.close_recurring_problem(problem_id, change=change)
        if closed is None:
            raise NotFoundError(
                f"no recurring problem named {problem_id!r}",
                remedy="list what there is with 'ninjasre remediation problems'",
            )
        return closed

    async def list_suspensions(self, *, live_only: bool = True) -> tuple[SuspensionRecord, ...]:
        """Return the resources autonomy is suspended on."""
        return await self.services.suspensions(live_only=live_only)

    async def clear_suspension(self, resource_id: str, *, reason: str) -> SuspensionRecord:
        """Let autonomy resume on a resource.

        Raises:
            NotFoundError: autonomy on that resource is not suspended.
        """
        cleared = await self.services.clear_suspension(resource_id, reason=reason)
        if cleared is None:
            raise NotFoundError(
                f"autonomous action on {resource_id!r} is not suspended",
                remedy="list what is with 'ninjasre remediation suspensions'",
            )
        return cleared

    async def detection_state(self) -> DetectionState:
        """Return whether detection is paused for this team, and why."""
        return await self.services.detection_state()

    async def autonomy_policy(self, node_id: str) -> AutonomyPolicyRecord:
        """Return what ``node_id`` may do without asking, inheritance applied."""
        return await self.services.autonomy_policy(node_id)

    async def apply_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any]
    ) -> AutonomyPolicyRecord:
        """Replace ``node_id``'s posture and return what it now resolves to."""
        return await self.services.apply_autonomy_policy(node_id, document)

    async def preview_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any], *, days: float
    ) -> PolicyPreviewRecord:
        """Return what a change would have decided differently, storing nothing."""
        return await self.services.preview_autonomy_policy(node_id, document, days=days)

    async def explain_autonomy(
        self, node_id: str, action: Mapping[str, Any]
    ) -> AutonomyExplanation:
        """Return what would happen to one action, and every reason it would."""
        return await self.services.explain_autonomy(node_id, action)

    async def autonomy_bounds(self, node_id: str) -> AutonomyBoundsRecord:
        """Return the freezes, budgets, overrides and stop bounding ``node_id``."""
        return await self.services.autonomy_bounds(node_id)

    async def set_autonomy_dry_run(self, node_id: str, *, enabled: bool) -> AutonomyPolicyRecord:
        """Turn simulation on or off for everything ``node_id`` resolves."""
        return await self.services.set_autonomy_dry_run(node_id, enabled=enabled)

    async def grant_autonomy_override(
        self, node_id: str, request: Mapping[str, Any]
    ) -> OverrideRecord:
        """Raise autonomy in a scope until it expires, and record who asked."""
        return await self.services.grant_autonomy_override(node_id, request)

    async def engage_kill_switch(self, *, reason: str, scope: str = "") -> KillSwitchRecord:
        """Stop every automated write, immediately."""
        return await self.services.engage_kill_switch(reason=reason, scope=scope)

    async def release_kill_switch(self, *, scope: str = "") -> KillSwitchRecord:
        """Let automated writes happen again, for one scope."""
        return await self.services.release_kill_switch(scope=scope)

    async def list_detectors(self) -> tuple[DetectorRecord, ...]:
        """Return every declared detector and what it concludes now."""
        return await self.services.detectors()

    async def list_observations(self, *, limit: int = 50) -> tuple[ObservationRecord, ...]:
        """Return what every enabled detector concludes right now."""
        return await self.services.observations(limit=limit)

    async def set_detector_enabled(self, detector_id: str, *, enabled: bool) -> DetectorRecord:
        """Turn a detector on or off and return it as it now reads."""
        return await self.services.set_detector_enabled(detector_id, enabled=enabled)

    async def dry_run_detector(self, detector_id: str) -> DryRunRecord:
        """Return what a detector would conclude, firing nothing."""
        return await self.services.detector_dry_run(detector_id)

    async def estate_summary(self) -> EstateSummaryReport:
        """Return the estate in the numbers a first screen shows."""
        return await self.services.estate_totals()

    async def show_resource(self, resource_id: str) -> EstateResourceDetail:
        """Return one resource's state, why it is in it, and its history."""
        detail = await self.services.resource(resource_id)
        if detail is None:
            raise NotFoundError(
                f"no resource {resource_id!r} in this estate",
                remedy="list what there is with 'ninjasre estate list'",
            )
        return detail

    async def set_maintenance(
        self, resource_id: str, *, until: datetime, reason: str
    ) -> EstateResource:
        """Suppress a resource from the problem count until ``until``."""
        return await self.services.open_maintenance(resource_id, until=until, reason=reason)

    async def clear_maintenance(self, resource_id: str) -> EstateResource:
        """End a resource's maintenance window now."""
        return await self.services.close_maintenance(resource_id)

    async def search_memory(self, query: str, *, limit: int = 10) -> tuple[MemoryHit, ...]:
        """Return the episodes matching ``query``, best first."""
        return await self.services.recall(query, limit=limit)

    async def memory_stats(self) -> MemoryStats:
        """Return what the episodic corpus holds."""
        return await self.services.corpus()

    async def list_providers(self) -> tuple[ProviderStatus, ...]:
        """Return every supported provider and this deployment's state for it."""
        return await self.services.providers()

    async def verify_provider(self, provider_id: str) -> ProviderStatus:
        """Check one provider end to end and return what was found."""
        return await self.services.check_provider(provider_id)

    async def list_integrations(self) -> tuple[IntegrationStatus, ...]:
        """Return every known integration and its current state."""
        return await self.services.integrations()

    async def credential_fields(self, integration: str) -> tuple[CredentialFieldSpec, ...]:
        """Return what ``integration`` needs, as a prompt can ask for it."""
        return await self.services.credential_schema(integration)

    async def store_integration_credential(
        self, integration: str, values: Mapping[str, str]
    ) -> IntegrationStatus:
        """Write ``values`` to the vault for ``integration``."""
        return await self.services.store_credential(integration, values)

    async def verify_integration(self, integration: str) -> IntegrationStatus:
        """Check one integration's credential and connectivity."""
        return await self.services.check_integration(integration)

    async def diagnose(self) -> DiagnosticReport:
        """Return what is configured, reachable, and healthy."""
        return await self.services.diagnostics()


# --- The remote client -------------------------------------------------------

#: The two integration-health words this client has to tell apart, spelled as
#: the catalogue spells them. Read rather than imported: reaching into the
#: integration tree to compare two strings would give a surface a dependency on
#: eighty vendor packages for the sake of a rendering decision.
_HEALTH_HEALTHY = "healthy"
_HEALTH_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Where a remote deployment is, and what to present to it."""

    url: str
    token: str = ""
    timeout_seconds: float = REMOTE_TIMEOUT_SECONDS

    def resolve(self, path: str) -> str:
        """Return the absolute URL of ``path`` on this deployment."""
        return f"{self.url.rstrip('/')}/{path.lstrip('/')}"


@dataclass(frozen=True, slots=True)
class RemoteClient:
    """A thin client over a deployment's REST API.

    Every method is the same three steps — request, document, value — so the
    only thing that differs between two commands is which path and which shape,
    and a transport failure is reported the same way whichever one it happened
    under.

    **What the API answers with is the shape this reads.** A route returns its
    own document: an object for a single thing, an array for a listing, an
    empty body for a deletion. A failure is ``{"error": {...}}`` with the
    status carrying the meaning. There is no wrapper around any of it, so
    nothing here goes looking for one — a client that unwrapped a payload the
    deployment never wrapped would report an empty answer for every populated
    one, and "no runs" reads exactly like a quiet deployment.

    **Not every command has a route.** Cost reporting, provider inventory,
    credential schemas, credential writes, and diagnostics are answered in a
    local composition from ports a deployment wires in process, and this
    surface exposes none of them. Those methods refuse by name rather than
    answering from defaults: a spend figure of zero and an empty provider list
    are answers somebody acts on.
    """

    endpoint: Endpoint
    opener: Any = None

    @property
    def transport(self) -> str:
        """Return that this talks to a deployment elsewhere."""
        return TRANSPORT_REMOTE

    def _call(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        """Return the document one API call answered with, whatever shape it has.

        ``None`` for an empty body, which is what a successful deletion is.

        Raises:
            UnavailableError: the deployment did not answer, or answered with
                something that is not a NinjaSRE API document.
            CliError: it answered with a failure.
        """
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.endpoint.resolve(path),
            data=payload,
            method=method,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "x-ninjasre-schema": JSON_SCHEMA_VERSION,
                **(
                    {"authorization": f"Bearer {self.endpoint.token}"}
                    if self.endpoint.token
                    else {}
                ),
            },
        )

        opener = self.opener or urllib.request.urlopen
        try:
            with opener(request, timeout=self.endpoint.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as failure:
            raise _from_status(failure.code, path, _failure_detail(failure)) from failure
        except (urllib.error.URLError, TimeoutError, OSError) as failure:
            raise UnavailableError(
                f"could not reach {self.endpoint.url}: {failure}",
                remedy="check the endpoint and that the deployment is running",
            ) from failure

        if not raw.strip():
            return None
        try:
            document = json.loads(raw.decode())
        except json.JSONDecodeError as failure:
            raise UnavailableError(
                f"{self.endpoint.url} answered with something that is not JSON",
                remedy="check that the endpoint points at a NinjaSRE deployment",
            ) from failure

        # A gated write answers 202 with the same failure document a refusal
        # uses, because "not yet" is the outcome rather than the transport
        # having gone wrong. It is the one success status that carries one.
        if isinstance(document, dict) and isinstance(document.get("error"), dict):
            raise ApprovalRequiredError(_text(document["error"], "message") or f"{path} is gated")
        return document

    def _document(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """Return one API call's answer, which has to be an object."""
        document = self._call(method, path, body)
        if document is None:
            return {}
        if not isinstance(document, dict):
            raise UnavailableError(f"{path} answered with a document that is not an object")
        return document

    def _listing(self, method: str, path: str) -> list[Mapping[str, Any]]:
        """Return one API call's answer, which has to be an array of objects."""
        document = self._call(method, path)
        if not isinstance(document, list):
            raise UnavailableError(f"{path} answered with a document that is not a list")
        return [record for record in document if isinstance(record, dict)]

    def _no_route(self, what: str, **asked: Any) -> UnavailableError:
        """Return the refusal for something this surface has no route for.

        What was asked for is logged rather than dropped: an operator who ran
        the command against the wrong deployment wants the trace to say which
        provider or which integration they meant, and the refusal itself stays
        short enough to read at the top of a terminal.
        """
        logger.debug("cli.route_not_served", endpoint=self.endpoint.url, wanted=what, **asked)
        return UnavailableError(
            f"this deployment's API does not expose {what}",
            remedy="run this command where the platform is composed, without --endpoint",
        )

    async def investigate(self, request: InvestigationRequest) -> InvestigationOutcome:
        """Run one investigation and return its identity and status.

        The team is the token's, not the request's: a remote caller acts within
        the scope the deployment issued them, and a body field naming another
        team would be a permission decision taken by the client.

        Evidence count and cost are not on this route, so they stay at their
        defaults — the run's identity is what the API returns immediately.
        """
        payload = self._document(
            "POST",
            "/v1/investigations",
            {
                "objective": request.objective or request.alert_source or "investigate this alert",
                "alert_source": request.alert_source,
                "context": {key: str(value) for key, value in dict(request.alert or {}).items()},
            },
        )
        return InvestigationOutcome(
            run_id=_text(payload, "run_id"),
            status=_text(payload, "status"),
            summary=_text(payload, "summary"),
        )

    async def list_runs(self, *, team_node_id: str = "", limit: int = 20) -> tuple[RunSummary, ...]:
        """Return the most recent runs, newest first.

        ``team_node_id`` is deliberately not sent, and is recorded rather than
        silently dropped: the deployment scopes a listing by the token that
        asked for it, and a client-supplied team would be asking a remote
        deployment to widen its own answer.
        """
        if team_node_id:
            logger.debug("cli.team_filter_is_the_tokens", asked=team_node_id)
        payload = self._document("GET", f"/v1/runs?limit={limit}")
        return tuple(_run_summary(record) for record in _records(payload, "runs"))

    async def show_run(self, run_id: str) -> RunDetail:
        """Return one run in full."""
        return _run_detail(self._document("GET", f"/v1/runs/{run_id}"))

    async def replay_run(self, run_id: str) -> RunReplay:
        """Return ``run_id`` rebuilt from its recorded events alone.

        The API returns the reconstruction rather than the raw event log, which
        is the same thing a local replay renders and is derived from the trace
        exactly as it is here.
        """
        payload = self._document("GET", f"/v1/runs/{run_id}/replay")
        return RunReplay(
            run_id=_text(payload, "run_id") or run_id,
            events=tuple(_records(payload, "turns")),
        )

    async def cost_of_runs(self, *, team_node_id: str = "", limit: int = 20) -> CostReport:
        """Refuse: this surface has no cost route."""
        raise self._no_route("what its runs cost", team=team_node_id, limit=limit)

    async def spend(
        self,
        *,
        team_node_id: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> SpendReport:
        """Refuse: spend is derived from per-run cost, which has no route."""
        raise self._no_route(
            "what a period cost", team=team_node_id, since=since, until=until, limit=limit
        )

    async def show_config(self, node_id: str) -> ConfigView:
        """Return ``node_id``'s effective configuration, every value attributed."""
        return _config_view_of(self._document("GET", f"/v1/config/{node_id}"), node_id)

    async def set_config(self, node_id: str, path: str, value: str) -> ConfigChange:
        """Set one configuration value and report what happened to it.

        Read first, then write, because the API answers a write with the new
        effective view and not with what the value used to be — and "it was
        already that" is the difference between a change and a no-op.
        """
        before = _value_at(self._document("GET", f"/v1/config/{node_id}"), path)
        try:
            after = self._document("PUT", f"/v1/config/{node_id}", {"patch": _nested(path, value)})
        except ApprovalRequiredError as gated:
            return ConfigChange(
                node_id=node_id,
                path=path,
                before=before,
                after=value,
                requires_approval=True,
                detail=gated.message,
            )
        return ConfigChange(
            node_id=node_id,
            path=path,
            before=before,
            after=_value_at(after, path),
            applied=True,
        )

    async def diff_config(self, left_node_id: str, right_node_id: str) -> ConfigDiff:
        """Return how two nodes' effective configuration differ."""
        left = await self.show_config(left_node_id)
        right = await self.show_config(right_node_id)
        return _diff_of(left, right)

    async def list_schedules(self, *, team_node_id: str = "") -> tuple[ScheduleSummary, ...]:
        """Return the scheduled investigations, scoped by the token as runs are."""
        if team_node_id:
            logger.debug("cli.team_filter_is_the_tokens", asked=team_node_id)
        return tuple(_schedule(record) for record in self._listing("GET", "/v1/schedules"))

    async def add_schedule(self, request: ScheduleRequest) -> ScheduleSummary:
        """Create a scheduled investigation and return it."""
        job_id = request.job_id or request.objective
        payload = self._document(
            "POST",
            "/v1/schedules",
            {
                "job_id": job_id,
                "name": job_id,
                "objective": request.objective,
                "cron": request.cron,
                "timezone": request.timezone,
            },
        )
        return _schedule(payload)

    async def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled investigation, reporting whether one went.

        A deletion answers with no body at all, so the absence of one is the
        success. Removing what is not there is reported as ``False`` rather
        than raised, matching what a local deployment answers.
        """
        try:
            self._call("DELETE", f"/v1/schedules/{job_id}")
        except NotFoundError:
            return False
        return True

    async def list_estate(self, query: EstateFilter) -> tuple[EstateResource, ...]:
        """Return the resources matching ``query``, by identifier."""
        payload = self._document("GET", f"/v1/estate/resources?{_estate_params(query)}")
        return tuple(_estate_resource(record) for record in _records(payload, "resources"))

    async def list_incidents(self, query: IncidentFilter) -> tuple[IncidentRecord, ...]:
        """Return the incidents matching ``query``, most recently opened first."""
        payload = self._document("GET", f"/v1/incidents?{_incident_params(query)}")
        return tuple(_incident(record) for record in _records(payload, "incidents"))

    async def show_incident(self, incident_id: str) -> IncidentDetailRecord:
        """Return one incident with its timeline, or raise if there is none."""
        return _incident_detail(self._document("GET", f"/v1/incidents/{incident_id}"))

    async def close_incident(
        self, incident_id: str, *, reason: str, resolved: bool = False
    ) -> IncidentRecord:
        """Close an incident with a reason and return it as it now reads."""
        return _incident(
            self._document(
                "POST",
                f"/v1/incidents/{incident_id}/close",
                {"reason": reason, "resolved": resolved},
            )
        )

    async def suppress_incident(
        self, incident_id: str, *, rule: str, reason: str
    ) -> IncidentRecord:
        """Close an incident as suppressed, naming what covered it."""
        return _incident(
            self._document(
                "POST",
                f"/v1/incidents/{incident_id}/suppress",
                {"rule": rule, "reason": reason},
            )
        )

    async def list_remediations(
        self,
        *,
        resource: str = "",
        capability: str = "",
        condition: str = "",
        limit: int = 25,
    ) -> tuple[RemediationOutcomeRecord, ...]:
        """Return what the deployment changed, most recent first."""
        query = _closed_loop_query(
            {"resource": resource, "capability": capability, "condition": condition},
            limit=limit,
        )
        payload = self._document("GET", f"/v1/remediations?{query}")
        return tuple(_remediation(record) for record in _records(payload, "outcomes"))

    async def remediation_effectiveness(
        self, *, capability: str = "", resource: str = "", condition: str = ""
    ) -> EffectivenessRecord:
        """Return how often this has worked, sliced by whatever was named."""
        query = _closed_loop_query(
            {"capability": capability, "resource": resource, "condition": condition}
        )
        return _effectiveness(
            self._document("GET", f"/v1/remediations/effectiveness/summary?{query}")
        )

    async def list_recurring_problems(
        self, *, live_only: bool = True
    ) -> tuple[RecurringProblemRecord, ...]:
        """Return the patterns the deployment has raised, most recent first."""
        payload = self._document(
            "GET", f"/v1/remediations/problems/recurring?live={str(live_only).lower()}"
        )
        return tuple(_recurring_problem(record) for record in _records(payload, "problems"))

    async def close_recurring_problem(
        self, problem_id: str, *, change: str
    ) -> RecurringProblemRecord:
        """Close a pattern, naming the change that closed it."""
        return _recurring_problem(
            self._document(
                "POST",
                f"/v1/remediations/problems/{problem_id}/close",
                {"change": change},
            )
        )

    async def list_suspensions(self, *, live_only: bool = True) -> tuple[SuspensionRecord, ...]:
        """Return the resources autonomy is suspended on."""
        payload = self._document(
            "GET", f"/v1/remediations/suspensions?live={str(live_only).lower()}"
        )
        return tuple(_suspension(record) for record in _records(payload, "suspensions"))

    async def clear_suspension(self, resource_id: str, *, reason: str) -> SuspensionRecord:
        """Let autonomy resume on a resource, recording who looked and what they found."""
        return _suspension(
            self._document(
                "POST",
                f"/v1/remediations/suspensions/{resource_id}/clear",
                {"reason": reason},
            )
        )

    async def detection_state(self) -> DetectionState:
        """Return whether detection is paused for this team, and why.

        Read off the detector listing rather than from a route of its own: the
        deployment already says it there, and a second endpoint would be a
        second thing to keep in step.
        """
        payload = self._document("GET", "/v1/detectors")
        return DetectionState(
            paused=bool(payload.get("paused")), reason=_text(payload, "pause_reason")
        )

    async def autonomy_policy(self, node_id: str) -> AutonomyPolicyRecord:
        """Return what ``node_id`` may do without asking, inheritance applied."""
        return _policy(self._document("GET", f"/v1/autonomy/policy/{node_id}"))

    async def apply_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any]
    ) -> AutonomyPolicyRecord:
        """Replace ``node_id``'s posture and return what it now resolves to."""
        return _policy(self._document("PUT", f"/v1/autonomy/policy/{node_id}", dict(document)))

    async def preview_autonomy_policy(
        self, node_id: str, document: Mapping[str, Any], *, days: float
    ) -> PolicyPreviewRecord:
        """Return what a change would have decided differently, storing nothing."""
        payload = self._document(
            "POST", f"/v1/autonomy/policy/{node_id}/preview?days={days}", dict(document)
        )
        return PolicyPreviewRecord(
            summary=_text(payload, "summary"),
            considered=_number(payload, "considered"),
            changed=_number(payload, "changed"),
            newly_autonomous=_number(payload, "newly_autonomous"),
            actions=tuple(_previewed(record) for record in _records(payload, "actions")),
        )

    async def explain_autonomy(
        self, node_id: str, action: Mapping[str, Any]
    ) -> AutonomyExplanation:
        """Return what would happen to one action, and every reason it would."""
        payload = self._document("POST", f"/v1/autonomy/policy/{node_id}/explain", dict(action))
        return AutonomyExplanation(
            decision=_text(payload, "decision"),
            level=_text(payload, "level"),
            risk_bound=_text(payload, "risk_bound"),
            risk_class=_text(payload, "risk_class"),
            dry_run=bool(payload.get("dry_run")),
            refused_by=_text(payload, "refused_by"),
            reason=_text(payload, "reason"),
            winning_rule=_text(payload, "winning_rule"),
            operation=_text(payload, "operation"),
            considered=tuple(_considered(record) for record in _records(payload, "considered")),
        )

    async def autonomy_bounds(self, node_id: str) -> AutonomyBoundsRecord:
        """Return the freezes, budgets, overrides and stop bounding ``node_id``."""
        payload = self._document("GET", f"/v1/autonomy/policy/{node_id}/bounds")
        return AutonomyBoundsRecord(
            node_id=_text(payload, "node_id") or node_id,
            stopped=bool(payload.get("stopped")),
            stop_reason=_text(payload, "stop_reason"),
            freezes=tuple(_records(payload, "freezes")),
            budgets=tuple(_records(payload, "budgets")),
            overrides=tuple(_records(payload, "overrides")),
            expired_overrides=_strings(payload, "expired_overrides"),
        )

    async def set_autonomy_dry_run(self, node_id: str, *, enabled: bool) -> AutonomyPolicyRecord:
        """Turn simulation on or off for everything ``node_id`` resolves."""
        return _policy(
            self._document("POST", f"/v1/autonomy/policy/{node_id}/dry-run", {"enabled": enabled})
        )

    async def grant_autonomy_override(
        self, node_id: str, request: Mapping[str, Any]
    ) -> OverrideRecord:
        """Raise autonomy in a scope until it expires, and record who asked."""
        payload = self._document("POST", f"/v1/autonomy/policy/{node_id}/overrides", dict(request))
        return OverrideRecord(
            name=_text(payload, "name"),
            level=_text(payload, "level"),
            expires_at=_instant(payload, "expires_at"),
            granted_by=_text(payload, "granted_by"),
            reason=_text(payload, "reason"),
            scope=dict(payload.get("scope") or {}),
        )

    async def engage_kill_switch(self, *, reason: str, scope: str = "") -> KillSwitchRecord:
        """Stop every automated write, immediately."""
        body: dict[str, Any] = {"reason": reason}
        if scope:
            body["scope"] = scope
        return _switch(self._document("POST", "/v1/autonomy/kill-switch", body))

    async def release_kill_switch(self, *, scope: str = "") -> KillSwitchRecord:
        """Let automated writes happen again, for one scope."""
        query = f"?scope={scope}" if scope else ""
        return _switch(self._document("DELETE", f"/v1/autonomy/kill-switch{query}"))

    async def list_detectors(self) -> tuple[DetectorRecord, ...]:
        """Return every declared detector and what it concludes now."""
        payload = self._document("GET", "/v1/detectors")
        return tuple(_detector(record) for record in _records(payload, "detectors"))

    async def list_observations(self, *, limit: int = 50) -> tuple[ObservationRecord, ...]:
        """Return what every enabled detector concludes right now."""
        payload = self._document("GET", f"/v1/observations?limit={limit}")
        return tuple(_observation(record) for record in _records(payload, "observations"))

    async def set_detector_enabled(self, detector_id: str, *, enabled: bool) -> DetectorRecord:
        """Turn a detector on or off and return it as it now reads."""
        verb = "enable" if enabled else "disable"
        return _detector(self._document("POST", f"/v1/detectors/{detector_id}/{verb}", {}))

    async def dry_run_detector(self, detector_id: str) -> DryRunRecord:
        """Return what a detector would conclude, firing nothing."""
        payload = self._document("POST", f"/v1/detectors/{detector_id}/dry-run", {})
        return DryRunRecord(
            detector_id=_text(payload, "detector_id") or detector_id,
            would_fire=bool(payload.get("would_fire")),
            observations=tuple(
                _observation(record) for record in _records(payload, "observations")
            ),
            fired=bool(payload.get("fired")),
        )

    async def estate_summary(self) -> EstateSummaryReport:
        """Return the estate in the numbers a first screen shows."""
        return _estate_summary(self._document("GET", "/v1/estate/summary"))

    async def show_resource(self, resource_id: str) -> EstateResourceDetail:
        """Return one resource's state, why it is in it, and its history."""
        return _estate_detail(self._document("GET", f"/v1/estate/resources/{resource_id}"))

    async def set_maintenance(
        self, resource_id: str, *, until: datetime, reason: str
    ) -> EstateResource:
        """Suppress a resource from the problem count until ``until``."""
        return _estate_resource(
            self._document(
                "POST",
                f"/v1/estate/resources/{resource_id}/maintenance",
                {"until": until.isoformat(), "reason": reason},
            )
        )

    async def clear_maintenance(self, resource_id: str) -> EstateResource:
        """End a resource's maintenance window now."""
        return _estate_resource(
            self._document("DELETE", f"/v1/estate/resources/{resource_id}/maintenance")
        )

    async def search_memory(self, query: str, *, limit: int = 10) -> tuple[MemoryHit, ...]:
        """Return the episodes involving ``query``, most recent first.

        Exact-match recall over components, which is what this surface offers:
        similarity search needs an embedding model the API does not compose. No
        score comes back, so none is invented.
        """
        payload = self._document("GET", f"/v1/memory/search?component={query}&limit={limit}")
        return tuple(_memory_hit(record) for record in _records(payload, "episodes"))

    async def memory_stats(self) -> MemoryStats:
        """Return what the episodic corpus holds.

        The route counts episodes and nothing else; the rest of the report
        stays at its defaults rather than being filled with zeros that read as
        measurements.
        """
        payload = self._document("GET", "/v1/memory/stats")
        return MemoryStats(episodes=_number(payload, "episode_count"))

    async def list_providers(self) -> tuple[ProviderStatus, ...]:
        """Refuse: this surface has no provider route."""
        raise self._no_route("which model providers it can use")

    async def verify_provider(self, provider_id: str) -> ProviderStatus:
        """Refuse: this surface has no provider route."""
        raise self._no_route("which model providers it can use", provider=provider_id)

    async def list_integrations(self) -> tuple[IntegrationStatus, ...]:
        """Return every known integration and its current state."""
        payload = self._document("GET", "/v1/integrations")
        return tuple(_catalogued(record) for record in _records(payload, "integrations"))

    async def credential_fields(self, integration: str) -> tuple[CredentialFieldSpec, ...]:
        """Refuse: credential schemas are reachable per node, not per client."""
        raise self._no_route("what an integration's credential needs", integration=integration)

    async def store_integration_credential(
        self, integration: str, values: Mapping[str, str]
    ) -> IntegrationStatus:
        """Write ``values`` to the deployment's vault and return what it now holds.

        The values go in the request body and nowhere else — not in the path,
        not in a query parameter, not in a header — because those are the parts
        every proxy between here and the deployment writes down. The log line
        carries the field *names*, which is what a support thread needs and is
        the same line the local path emits.

        The response is a status. There is no route that reads a credential
        back, so nothing here has anywhere to put one.
        """
        names = sorted(values)
        logger.info("cli.integration_credential_stored", integration=integration, fields=names)
        payload = self._document(
            "PUT", f"/v1/integrations/{integration}/credential", {"values": dict(values)}
        )
        return IntegrationStatus(
            integration=_text(payload, "integration") or integration,
            configured=True,
            healthy=bool(payload.get("usable", False)),
            credential_state=_text(payload, "state"),
        )

    async def verify_integration(self, integration: str) -> IntegrationStatus:
        """Check one integration's credential: present, current, decryptable."""
        payload = self._document("POST", f"/v1/integrations/{integration}/verify")
        usable = bool(payload.get("usable", False))
        return IntegrationStatus(
            integration=_text(payload, "integration") or integration,
            configured=usable,
            healthy=usable,
            credential_state=_text(payload, "state"),
        )

    async def diagnose(self) -> DiagnosticReport:
        """Refuse: this surface has no diagnostics route."""
        raise self._no_route("its own diagnostics")


# --- Selection ---------------------------------------------------------------


def select_client(
    *,
    services: LocalServices | None = None,
    endpoint: Endpoint | None = None,
) -> PlatformClient:
    """Return the client this invocation should use.

    An explicit endpoint wins. A flag or an environment variable naming one is
    the operator saying "not this machine", and silently preferring a local
    deployment because one happened to be composed would run an investigation
    somewhere they did not mean.

    Raises:
        CliError: neither a local composition nor an endpoint was supplied.
    """
    if endpoint is not None:
        logger.debug("cli.client_selected", transport=TRANSPORT_REMOTE, url=endpoint.url)
        return RemoteClient(endpoint=endpoint)
    if services is not None:
        logger.debug("cli.client_selected", transport=TRANSPORT_LOCAL)
        return LocalClient(services=services)
    raise CliError(
        "no deployment to talk to",
        remedy="point at one with --endpoint, or run where the platform is composed",
    )


# --- Reading documents -------------------------------------------------------


def _policy(payload: Mapping[str, Any]) -> AutonomyPolicyRecord:
    """Return the posture ``payload`` describes, document and rendering both.

    The document is kept whole beside the rendered rows. ``--json`` has to
    round-trip: what an operator exports is what they edit and apply back, and
    a rendering with the scopes flattened to prose could not be applied.
    """
    rules = _records(payload, "rules")
    return AutonomyPolicyRecord(
        node_id=_text(payload, "node_id"),
        dry_run=bool(payload.get("dry_run")),
        document={
            "dry_run": bool(payload.get("dry_run")),
            "rules": rules,
            "freezes": _records(payload, "freezes"),
            "budgets": _records(payload, "budgets"),
            "overrides": _records(payload, "overrides"),
        },
        rules=tuple(_rule_row(record) for record in rules),
    )


def _rule_row(record: Mapping[str, Any]) -> AutonomyRuleRecord:
    """Return one rule as a table row shows it."""
    scope = record.get("scope") or {}
    return AutonomyRuleRecord(
        rule_id=_scope_identity(scope if isinstance(scope, Mapping) else {}),
        scope=_scope_phrase(scope if isinstance(scope, Mapping) else {}),
        level=_text(record, "level"),
        risk_bound=_text(record, "risk_bound"),
        dry_run=bool(record.get("dry_run")),
    )


def _scope_identity(scope: Mapping[str, Any]) -> str:
    """Return the identifier the deployment names this scope by."""
    labels = scope.get("labels") or {}
    written = (
        ",".join(f"{name}={value}" for name, value in sorted(labels.items()))
        if isinstance(labels, Mapping)
        else ""
    )
    return ":".join(
        (
            _text(scope, "kind"),
            _text(scope, "team_node_id"),
            _text(scope, "resource_kind"),
            _text(scope, "resource_id"),
            _text(scope, "capability"),
            written,
        )
    )


def _scope_phrase(scope: Mapping[str, Any]) -> str:
    """Return the scope in the words a table shows.

    Assembled here rather than sent by the API, because it is a rendering
    decision and the API sends the fields it is made of. A client that could
    only show what the server phrased could not show it in another language.
    """
    kind = _text(scope, "kind")
    labels = scope.get("labels") or {}
    if kind == "deployment":
        return "everywhere"
    if kind == "team":
        return f"team {_text(scope, 'team_node_id')}"
    if kind == "resource_kind":
        return f"every {_text(scope, 'resource_kind')}"
    if kind == "labels" and isinstance(labels, Mapping):
        return ", ".join(f"{name}={value}" for name, value in sorted(labels.items()))
    if kind == "capability":
        return f"{_text(scope, 'capability')} anywhere"
    if kind == "resource":
        return _text(scope, "resource_id")
    return f"{_text(scope, 'capability')} on {_text(scope, 'resource_id')}"


def _considered(record: Mapping[str, Any]) -> ConsideredRuleRecord:
    """Return one rule a resolution looked at."""
    return ConsideredRuleRecord(
        rule_id=_text(record, "rule_id"),
        scope=_text(record, "scope"),
        level=_text(record, "level"),
        applied=bool(record.get("applied")),
        won=bool(record.get("won")),
        subject=_text(record, "subject"),
        reason=_text(record, "reason"),
    )


def _previewed(record: Mapping[str, Any]) -> PreviewedActionRecord:
    """Return one recorded action as the preview lists it."""
    return PreviewedActionRecord(
        action_id=_text(record, "action_id"),
        capability=_text(record, "capability"),
        subjects=_strings(record, "subjects"),
        before=_text(record, "before"),
        after=_text(record, "after"),
        changed=bool(record.get("changed")),
        more_autonomous=bool(record.get("more_autonomous")),
    )


def _switch(payload: Mapping[str, Any]) -> KillSwitchRecord:
    """Return the switch's state as the API reports it."""
    scopes = payload.get("scopes") or {}
    return KillSwitchRecord(
        engaged=bool(payload.get("engaged")),
        scopes=dict(scopes) if isinstance(scopes, Mapping) else {},
    )


def _text(payload: Mapping[str, Any], key: str) -> str:
    """Return a string field, defaulting to empty."""
    value = payload.get(key)
    return str(value) if value is not None else ""


def _number(payload: Mapping[str, Any], key: str) -> int:
    """Return an integer field, defaulting to zero."""
    value = payload.get(key)
    return int(value) if isinstance(value, int | float) else 0


def _decimal(payload: Mapping[str, Any], key: str) -> float:
    """Return a float field, defaulting to zero."""
    value = payload.get(key)
    return float(value) if isinstance(value, int | float) else 0.0


def _instant(payload: Mapping[str, Any], key: str) -> datetime | None:
    """Return a timestamp field, or ``None`` when it is absent or unreadable."""
    raw = _text(payload, key)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        # A timestamp the deployment wrote in a shape this client does not read
        # is a field to omit, not a reason to fail the whole listing.
        logger.debug("cli.unreadable_timestamp", key=key, value=raw)
        return None


def _records(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    """Return a list-of-objects field, defaulting to empty."""
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [record for record in value if isinstance(record, dict)]


def _strings(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """Return a list-of-strings field, defaulting to empty."""
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(str(element) for element in value)


def _incident_params(query: IncidentFilter) -> str:
    """Return ``query`` as the API's query string.

    Repeated keys for the multi-valued dimensions, matching what the route
    reads and matching the estate's own listing.
    """
    pairs: list[tuple[str, str]] = []
    for name, values in (
        ("state", query.states),
        ("severity", query.severities),
        ("detector", query.detectors),
    ):
        pairs.extend((name, value) for value in values)
    if query.subject:
        pairs.append(("subject", query.subject))
    if query.live_only:
        pairs.append(("live", "true"))
    pairs.append(("limit", str(query.limit)))
    return urllib.parse.urlencode(pairs)


def _evidence(record: Mapping[str, Any]) -> dict[str, str]:
    """Return one payload's evidence map, as strings."""
    found = record.get("evidence")
    if not isinstance(found, dict):
        return {}
    return {str(name): str(value) for name, value in found.items()}


def _closed_loop_query(fields: Mapping[str, str], *, limit: int | None = None) -> str:
    """Return the query string the named filters describe, omitting the empty ones.

    Empty means "no filter on this dimension" all the way down — the command,
    the route and the store all read it that way — so sending the key with an
    empty value would be a third spelling of the same idea.
    """
    parts = [f"{name}={value}" for name, value in fields.items() if value]
    if limit is not None:
        parts.append(f"limit={limit}")
    return "&".join(parts)


def _floats(record: Mapping[str, Any], key: str) -> dict[str, float]:
    """Return the numeric mapping under ``key``, dropping anything unreadable."""
    found = record.get(key)
    if not isinstance(found, Mapping):
        return {}
    values: dict[str, float] = {}
    for name, value in found.items():
        try:
            values[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    return values


def _counts(record: Mapping[str, Any], key: str) -> dict[str, int]:
    """Return the integer mapping under ``key``, dropping anything unreadable."""
    found = record.get(key)
    if not isinstance(found, Mapping):
        return {}
    counts: dict[str, int] = {}
    for name, value in found.items():
        try:
            counts[str(name)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def _remediation(record: Mapping[str, Any]) -> RemediationOutcomeRecord:
    """Return the remediation one API row describes."""
    return RemediationOutcomeRecord(
        action_id=_text(record, "action_id"),
        capability=_text(record, "capability"),
        resource_id=_text(record, "resource_id"),
        condition_key=_text(record, "condition_key"),
        incident_id=_text(record, "incident_id"),
        executed_at=_instant(record, "executed_at"),
        due_at=_instant(record, "due_at"),
        settle_seconds=int(record.get("settle_seconds") or 0),
        awaiting_verification=bool(record.get("awaiting_verification", True)),
        verdict=_text(record, "verdict"),
        verified_at=_instant(record, "verified_at"),
        before=_floats(record, "before"),
        after=_floats(record, "after"),
        rollback=_text(record, "rollback") or "not_required",
        rollback_detail=_text(record, "rollback_detail"),
        autonomous=bool(record.get("autonomous")),
        detail=_text(record, "detail"),
    )


def _effectiveness(record: Mapping[str, Any]) -> EffectivenessRecord:
    """Return the effectiveness one API document describes."""
    return EffectivenessRecord(
        capability=_text(record, "capability"),
        resource_id=_text(record, "resource_id"),
        condition_key=_text(record, "condition_key"),
        total=int(record.get("total") or 0),
        verified=int(record.get("verified") or 0),
        awaiting=int(record.get("awaiting") or 0),
        success_ratio=float(record.get("success_ratio") or 0.0),
        counts=_counts(record, "counts"),
        last_verdict=_text(record, "last_verdict"),
        known=bool(record.get("known")),
        discouraged=bool(record.get("discouraged")),
        summary=_text(record, "summary"),
    )


def _recurring_problem(record: Mapping[str, Any]) -> RecurringProblemRecord:
    """Return the recurring problem one API row describes."""
    return RecurringProblemRecord(
        problem_id=_text(record, "problem_id"),
        pattern_key=_text(record, "pattern_key"),
        capability=_text(record, "capability"),
        resource_id=_text(record, "resource_id"),
        title=_text(record, "title"),
        summary=_text(record, "summary"),
        raised_at=_instant(record, "raised_at"),
        occurrences=int(record.get("occurrences") or 0),
        window_seconds=int(record.get("window_seconds") or 0),
        suppresses_autonomy=bool(record.get("suppresses_autonomy", True)),
        live=bool(record.get("live", True)),
        close_reason=_text(record, "close_reason"),
        closed_by=_text(record, "closed_by"),
    )


def _suspension(record: Mapping[str, Any]) -> SuspensionRecord:
    """Return the suspension one API row describes."""
    return SuspensionRecord(
        resource_id=_text(record, "resource_id"),
        since=_instant(record, "since"),
        reason=_text(record, "reason"),
        action_id=_text(record, "action_id"),
        live=bool(record.get("live", True)),
        cleared_by=_text(record, "cleared_by"),
        clear_reason=_text(record, "clear_reason"),
    )


def _incident(record: Mapping[str, Any]) -> IncidentRecord:
    """Return the incident one API row describes."""
    return IncidentRecord(
        incident_id=_text(record, "incident_id"),
        title=_text(record, "title"),
        summary=_text(record, "summary"),
        state=_text(record, "state"),
        severity=_text(record, "severity"),
        origin=_text(record, "origin"),
        detector=_text(record, "detector"),
        subjects=_strings(record, "subjects"),
        opened_at=_instant(record, "opened_at"),
        closed_at=_instant(record, "closed_at"),
        run_id=_text(record, "run_id"),
        self_resolved=bool(record.get("self_resolved")),
        suppressed_by=_text(record, "suppressed_by"),
        close_reason=_text(record, "close_reason"),
    )


def _incident_detail(payload: Mapping[str, Any]) -> IncidentDetailRecord:
    """Return the incident detail one API document describes."""
    incident = payload.get("incident")
    return IncidentDetailRecord(
        incident=_incident(incident if isinstance(incident, dict) else {}),
        subjects=tuple(
            IncidentSubjectRecord(
                resource_id=_text(record, "resource_id"),
                detail=_text(record, "detail"),
                evidence=_evidence(record),
                observed_at=_instant(record, "observed_at"),
                absent_since=_instant(record, "absent_since"),
            )
            for record in _records(payload, "subjects")
        ),
        timeline=tuple(
            IncidentTimelineRecord(
                at=_instant(record, "at"),
                kind=_text(record, "kind"),
                actor=_text(record, "actor"),
                cause=_text(record, "cause"),
                detail=_text(record, "detail"),
            )
            for record in _records(payload, "timeline")
        ),
        actions=_strings(payload, "actions"),
    )


def _detector(record: Mapping[str, Any]) -> DetectorRecord:
    """Return the detector one API row describes."""
    return DetectorRecord(
        detector_id=_text(record, "detector_id"),
        name=_text(record, "name"),
        description=_text(record, "description"),
        severity=_text(record, "severity"),
        signal=_text(record, "signal"),
        enabled=bool(record.get("enabled")),
        subjects_covered=int(record.get("subjects_covered") or 0),
        subjects_total=int(record.get("subjects_total") or 0),
        last_verdict=_text(record, "last_verdict"),
        last_evaluated_at=_instant(record, "last_evaluated_at"),
    )


def _observation(record: Mapping[str, Any]) -> ObservationRecord:
    """Return the observation one API row describes."""
    return ObservationRecord(
        detector=_text(record, "detector"),
        subject=_text(record, "subject"),
        verdict=_text(record, "verdict"),
        detail=_text(record, "detail"),
        evidence=_evidence(record),
        observed_at=_instant(record, "observed_at"),
    )


def _estate_params(query: EstateFilter) -> str:
    """Return ``query`` as the API's query string.

    Repeated keys for the multi-valued dimensions, which is what the route
    reads. Comma-joining would mean a label containing a comma silently became
    two labels, and an operator's label is theirs to choose.
    """
    pairs: list[tuple[str, str]] = []
    for name, values in (
        ("kind", query.kinds),
        ("health", query.health),
        ("source", query.sources),
        ("label", query.labels),
    ):
        pairs.extend((name, value) for value in values)
    if query.team_node_id:
        pairs.append(("team", query.team_node_id))
    if query.parent_id:
        pairs.append(("parent", query.parent_id))
    if query.include_absent:
        pairs.append(("include_absent", "true"))
    pairs.append(("limit", str(query.limit)))
    return urllib.parse.urlencode(pairs)


def _estate_resource(record: Mapping[str, Any]) -> EstateResource:
    """Return the resource one API row describes."""
    return EstateResource(
        resource_id=_text(record, "resource_id"),
        kind=_text(record, "kind"),
        display_name=_text(record, "display_name"),
        health=_text(record, "health"),
        stored_health=_text(record, "stored_health"),
        source=_text(record, "source"),
        sources=_strings(record, "sources"),
        native_id=_text(record, "native_id"),
        parent_id=_text(record, "parent_id"),
        is_stale=bool(record.get("is_stale")),
        labels=_strings(record, "labels"),
        last_seen_at=_instant(record, "last_seen_at"),
        absent_since=_instant(record, "absent_since"),
        maintenance_until=_instant(record, "maintenance_until"),
        maintenance_reason=_text(record, "maintenance_reason"),
        explanation=_text(record, "explanation"),
    )


def _estate_summary(payload: Mapping[str, Any]) -> EstateSummaryReport:
    """Return the summary one API document describes."""

    def counts(key: str) -> dict[str, int]:
        value = payload.get(key)
        if not isinstance(value, dict):
            return {}
        return {str(name): int(count) for name, count in value.items()}

    return EstateSummaryReport(
        total=_number(payload, "total"),
        problems=_number(payload, "problems"),
        maintenance=_number(payload, "maintenance"),
        absent=_number(payload, "absent"),
        captured_at=_instant(payload, "captured_at"),
        by_kind=counts("by_kind"),
        by_health=counts("by_health"),
        by_source=counts("by_source"),
    )


def _estate_detail(payload: Mapping[str, Any]) -> EstateResourceDetail:
    """Return the resource detail one API document describes."""
    resource = payload.get("resource")
    derivation = payload.get("derivation")
    derived = derivation if isinstance(derivation, dict) else {}
    return EstateResourceDetail(
        resource=_estate_resource(resource if isinstance(resource, dict) else {}),
        rule=_text(derived, "rule"),
        raw_status=_text(derived, "raw_status"),
        explanation=_text(derived, "explanation"),
        freshness_seconds=_number(payload, "freshness_seconds"),
        rollup_rule=_text(payload, "rollup_rule"),
        signals=tuple(
            EstateHealthSignal(
                name=_text(signal, "name"),
                value=_text(signal, "value"),
                observed_at=_instant(signal, "observed_at"),
                source=_text(signal, "source"),
            )
            for signal in _records(derived, "signals")
        ),
        transitions=tuple(
            EstateTransition(
                occurred_at=_instant(entry, "occurred_at"),
                state=_text(entry, "state"),
                previous_state=_text(entry, "previous_state"),
                rule=_text(entry, "rule"),
            )
            for entry in _records(payload, "transitions")
        ),
        references=tuple(
            EstateReference(
                reference_kind=_text(entry, "reference_kind"),
                reference_id=_text(entry, "reference_id"),
                recorded_at=_instant(entry, "recorded_at"),
                summary=_text(entry, "summary"),
            )
            for entry in _records(payload, "references")
        ),
        children=tuple(_estate_resource(child) for child in _records(payload, "children")),
    )


def _run_summary(record: Mapping[str, Any]) -> RunSummary:
    """Return the run summary an investigation document describes.

    The API's summary is what the run *concluded*, not what it was asked; there
    is no objective on the route, so the field stays empty rather than being
    filled with the conclusion, which is a different sentence.
    """
    return RunSummary(
        run_id=_text(record, "run_id"),
        status=_text(record, "status"),
        trigger=_text(record, "trigger"),
        started_at=_instant(record, "started_at"),
        ended_at=_instant(record, "finished_at"),
    )


def _run_detail(payload: Mapping[str, Any]) -> RunDetail:
    """Return the run detail an investigation document describes.

    Stages, evidence, and cost are not on this route. They stay empty rather
    than being reconstructed from what is here — an empty stage list reads as
    "nothing recorded", which is at least the truth about what was asked for.
    """
    return RunDetail(run=_run_summary(payload), result=_text(payload, "summary"))


def _config_view_of(payload: Mapping[str, Any], node_id: str) -> ConfigView:
    """Return the configuration view an effective-configuration document describes.

    Provenance is what enumerates the entries, not the value tree: it is keyed
    by the dotted path of every value the merge decided, so iterating it lists
    exactly the settings that resolved and attributes each one. Walking the
    nested values instead would report a path for every intermediate mapping.
    """
    provenance = payload.get("provenance")
    attributions: Mapping[str, Any] = provenance if isinstance(provenance, dict) else {}
    return ConfigView(
        node_id=_text(payload, "node_id") or node_id,
        entries=tuple(
            ConfigEntry(
                path=path,
                value=_value_at(payload, path),
                source_node_id=str(attributions[path]),
            )
            for path in sorted(attributions)
        ),
    )


def _value_at(payload: Mapping[str, Any], path: str) -> str:
    """Return the value a dotted path names inside a document's ``values`` tree."""
    found: Any = payload.get("values")
    for segment in path.split("."):
        if not isinstance(found, Mapping):
            return ""
        found = found.get(segment)
    return "" if found is None else str(found)


def _nested(path: str, value: str) -> dict[str, Any]:
    """Return ``value`` wrapped in the mappings a dotted path names.

    The API takes a partial document merged onto the node's own settings, and
    the CLI takes one dotted path. A flat key would write a setting literally
    called ``settings.masking`` beside the one the operator meant.
    """
    document: Any = value
    for segment in reversed(path.split(".")):
        document = {segment: document}
    return dict(document) if isinstance(document, dict) else {path: value}


def _catalogued(record: Mapping[str, Any]) -> IntegrationStatus:
    """Return the integration status a catalogue entry describes.

    An integration nothing has ever run against reports its health as unknown,
    and unknown is deliberately not healthy: the catalogue draws that
    distinction so that "never tried" cannot be read as "working". This carries
    it across rather than collapsing the two into one boolean.
    """
    health = _text(record, "health")
    return IntegrationStatus(
        integration=_text(record, "name"),
        configured=bool(health) and health != _HEALTH_UNKNOWN,
        healthy=health == _HEALTH_HEALTHY,
        credential_state=health,
        detail=_text(record, "health_detail"),
    )


def _schedule(record: Mapping[str, Any]) -> ScheduleSummary:
    """Return the schedule a document describes."""
    return ScheduleSummary(
        job_id=_text(record, "job_id"),
        objective=_text(record, "objective"),
        cron=_text(record, "cron"),
        timezone=_text(record, "timezone"),
        enabled=bool(record.get("enabled", True)),
        team_node_id=_text(record, "team_node_id"),
        next_fire_at=_instant(record, "next_run_at"),
    )


def _memory_hit(record: Mapping[str, Any]) -> MemoryHit:
    """Return the memory hit an episode document describes.

    No score: this route recalls by exact component match rather than by
    similarity, so there is no ranking to report and a zero is what the model's
    own default says — nothing was measured.
    """
    return MemoryHit(
        episode_id=_text(record, "episode_id"),
        title=_text(record, "title"),
        components=_strings(record, "components"),
        occurred_at=_instant(record, "occurred_at"),
    )


def _diff_of(left: ConfigView, right: ConfigView) -> ConfigDiff:
    """Return where two effective configurations differ.

    Computed here rather than asked of the deployment, so a diff between a
    local node and a remote one is the same function — and because "what does
    the platform think differs" is a question with one answer only when one
    thing answers it.
    """
    left_values = {entry.path: entry.value for entry in left.entries}
    right_values = {entry.path: entry.value for entry in right.entries}
    deltas = tuple(
        ConfigDelta(path=path, left=left_values.get(path, ""), right=right_values.get(path, ""))
        for path in sorted(set(left_values) | set(right_values))
        if left_values.get(path) != right_values.get(path)
    )
    return ConfigDiff(left_node_id=left.node_id, right_node_id=right.node_id, deltas=deltas)


def _failure_detail(failure: urllib.error.HTTPError) -> str:
    """Return the sentence the API wrote about a failure, if it wrote one.

    The API sanitises its own failure messages before they cross the boundary,
    so what is there is safe to repeat. What is *not* repeated is a body that
    is not one of its documents — an intermediary's error page has nothing to
    do with the deployment and reads as though it did.
    """
    try:
        body = failure.read()
    except (OSError, ValueError, AttributeError):
        return ""
    try:
        document = json.loads(body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(document, dict):
        return ""
    error = document.get("error")
    return _text(error, "message") if isinstance(error, dict) else ""


def _from_status(status: int, path: str, detail: str = "") -> CliError:
    """Return the error a failing HTTP status describes.

    Mapped rather than reported verbatim so the exit code an operator's script
    branches on is the same whether the deployment is local or remote. The
    deployment's own sentence is appended where it wrote one, because "the
    deployment rejected this" without saying what it objected to is a message
    that sends somebody to the server logs.
    """
    said = f": {detail}" if detail else ""
    match status:
        case 401 | 403:
            return DeniedError(
                f"the deployment refused {path}{said}",
                remedy="check the token this CLI is using",
            )
        case 404:
            return NotFoundError(f"{path} does not exist on this deployment{said}")
        case 409:
            return ApprovalRequiredError(f"{path} is gated on an approval{said}")
        case 422:
            return ConfigurationError(f"the deployment rejected the request to {path}{said}")
        case _ if status >= 500:
            return UnavailableError(f"the deployment failed on {path} with status {status}{said}")
        case _:
            return CliError(f"{path} answered with status {status}{said}")


@dataclass(frozen=True, slots=True)
class ClientSelection:
    """What the application root resolved, for a command to be handed.

    Carried as a value rather than assembled per command, so "which deployment
    is this talking to" is decided once and is visible in ``--json`` output and
    in ``doctor``.
    """

    client: PlatformClient
    endpoint: Endpoint | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def transport(self) -> str:
        """Return which kind of deployment this invocation reached."""
        return self.client.transport


def endpoint_from(url: str, *, token: str = "") -> Endpoint | None:
    """Return the endpoint ``url`` names, or ``None`` when it names nothing.

    Raises:
        CliError: the URL is not one this client can reach.
    """
    trimmed = url.strip()
    if not trimmed:
        return None
    if not trimmed.startswith(("http://", "https://")):
        raise CliError(
            f"{trimmed!r} is not an endpoint this CLI can reach",
            remedy="give a full URL, for example https://ninjasre.internal:8420",
        )
    return Endpoint(url=trimmed, token=token)


__all__ = [
    "REMOTE_TIMEOUT_SECONDS",
    "ClientSelection",
    "Endpoint",
    "EstateFilter",
    "InvestigationRequest",
    "LocalClient",
    "LocalServices",
    "PlatformClient",
    "RemoteClient",
    "ScheduleRequest",
    "endpoint_from",
    "select_client",
]
