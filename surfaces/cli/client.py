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
    ConfigChange,
    ConfigDelta,
    ConfigDiff,
    ConfigEntry,
    ConfigView,
    CostReport,
    CredentialFieldSpec,
    DiagnosticReport,
    IntegrationStatus,
    InvestigationOutcome,
    MemoryHit,
    MemoryStats,
    ProviderStatus,
    RunDetail,
    RunReplay,
    RunSummary,
    ScheduleSummary,
    SpendReport,
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
        """Refuse: this surface has no credential-write route.

        Refused before a request is built, so the secret is never put on the
        wire — nor into the failure, nor into the log line, which are both
        places an operator pastes from. Only the field *names* are recorded.
        """
        raise self._no_route(
            "writing an integration credential",
            integration=integration,
            fields=sorted(values),
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
    "InvestigationRequest",
    "LocalClient",
    "LocalServices",
    "PlatformClient",
    "RemoteClient",
    "ScheduleRequest",
    "endpoint_from",
    "select_client",
]
