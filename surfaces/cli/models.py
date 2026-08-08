"""What a command reports, independent of how it is rendered.

One shape per command output, each with a ``to_record`` that produces the
document ``--json`` prints and the tables render from. Two renderers over one
value rather than two code paths, because a table and a JSON document that can
disagree will, and the one nobody looks at is the one that drifts.

These are also the shapes the published schemas describe. A field added here
without a schema entry fails the contract suite, which is what stops
``--json`` from being documented once and then quietly extended.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


def _moment(value: datetime | None) -> str:
    """Return an instant as ISO 8601, or the empty string for none.

    Empty rather than ``null``: every field in a payload is a string, a number,
    a bool, a list, or an object, and a reader that has to handle ``null`` on
    half the timestamps handles it wrongly on one of them.
    """
    return value.isoformat() if value is not None else ""


class CheckState(StrEnum):
    """How one diagnostic check came out."""

    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CostReport:
    """What a set of runs consumed.

    ``unpriced_runs`` is carried rather than folded into the total, because a
    model whose pricing the deployment does not hold contributes tokens and no
    cost — and a total that quietly omitted them understates a bill in a way
    nothing in the number reveals.
    """

    runs: int = 0
    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    unpriced_runs: int = 0

    @property
    def total_tokens(self) -> int:
        """Return prompt and completion tokens together."""
        return self.prompt_tokens + self.completion_tokens

    def to_record(self) -> dict[str, Any]:
        """Return this report as a JSON-serialisable document."""
        return {
            "runs": self.runs,
            "turns": self.turns,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": round(self.cost, 6),
            "unpriced_runs": self.unpriced_runs,
        }


@dataclass(frozen=True, slots=True)
class SpendLine:
    """One row of a spend report: a team, a run, or the total across both."""

    label: str = ""
    runs: int = 0
    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    unpriced_runs: int = 0

    @property
    def total_tokens(self) -> int:
        """Return prompt and completion tokens together."""
        return self.prompt_tokens + self.completion_tokens

    @property
    def is_complete(self) -> bool:
        """Return whether every run in this row could be priced.

        Read the money with this. A row containing an unpriced run reports a
        floor, and presenting a floor as a total is how a locally hosted model
        comes to look free.
        """
        return self.unpriced_runs == 0

    def plus(self, other: CostReport) -> SpendLine:
        """Return this row with ``other`` added to it."""
        return SpendLine(
            label=self.label,
            runs=self.runs + max(other.runs, 1),
            turns=self.turns + other.turns,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost=self.cost + other.cost,
            unpriced_runs=self.unpriced_runs + other.unpriced_runs,
        )

    def to_record(self) -> dict[str, Any]:
        """Return this row as a JSON-serialisable document."""
        return {
            "label": self.label,
            "runs": self.runs,
            "turns": self.turns,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": round(self.cost, 6),
            "unpriced_runs": self.unpriced_runs,
            "complete": self.is_complete,
        }


@dataclass(frozen=True, slots=True)
class SpendReport:
    """What a period cost, per team and per run.

    The window is carried in the report rather than left to whoever asked for
    it. A spend figure whose period is somewhere else is a number two people
    will read as covering two different things.
    """

    since: datetime | None = None
    until: datetime | None = None
    total: SpendLine = field(default_factory=SpendLine)
    by_team: tuple[SpendLine, ...] = ()
    by_run: tuple[SpendLine, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return this report as a JSON-serialisable document."""
        return {
            "since": _moment(self.since),
            "until": _moment(self.until),
            "total": self.total.to_record(),
            "by_team": [line.to_record() for line in self.by_team],
            "by_run": [line.to_record() for line in self.by_run],
        }


def aggregate_spend(
    entries: Sequence[tuple[RunSummary, CostReport]],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> SpendReport:
    """Return what ``entries`` cost, filtered to a window and grouped two ways.

    A run with no start time is included rather than dropped. It is a run that
    happened; excluding it because its trace is incomplete would understate a
    bill for the reason least visible to whoever reads it.
    """
    selected = [
        (run, cost) for run, cost in entries if _within(run.started_at, since=since, until=until)
    ]

    total = SpendLine(label="total")
    teams: dict[str, SpendLine] = {}
    runs: list[SpendLine] = []
    for run, cost in selected:
        total = total.plus(cost)
        team = run.team_node_id or "unattributed"
        teams[team] = teams.get(team, SpendLine(label=team)).plus(cost)
        runs.append(SpendLine(label=run.run_id).plus(cost))

    return SpendReport(
        since=since,
        until=until,
        total=total,
        by_team=tuple(teams[name] for name in sorted(teams)),
        by_run=tuple(runs),
    )


def _within(
    moment: datetime | None,
    *,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    """Return whether ``moment`` falls inside the window, an unknown one counting."""
    if moment is None:
        return True
    if since is not None and moment < since:
        return False
    return not (until is not None and moment > until)


@dataclass(frozen=True, slots=True)
class RunSummary:
    """One run, as a listing shows it."""

    run_id: str
    status: str = ""
    trigger: str = ""
    objective: str = ""
    team_node_id: str = ""
    principal_id: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    awaiting: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this summary as a JSON-serialisable document."""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "trigger": self.trigger,
            "objective": self.objective,
            "team_node_id": self.team_node_id,
            "principal_id": self.principal_id,
            "started_at": _moment(self.started_at),
            "ended_at": _moment(self.ended_at),
            "awaiting": self.awaiting,
        }


@dataclass(frozen=True, slots=True)
class StageReport:
    """One pass of one pipeline stage."""

    stage: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failed: bool = False

    def to_record(self) -> dict[str, Any]:
        """Return this stage as a JSON-serialisable document."""
        return {
            "stage": self.stage,
            "started_at": _moment(self.started_at),
            "ended_at": _moment(self.ended_at),
            "failed": self.failed,
        }


@dataclass(frozen=True, slots=True)
class RunDetail:
    """One run in full: what it did, what it found, and what it cost."""

    run: RunSummary
    stages: tuple[StageReport, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    result: str = ""
    errors: tuple[str, ...] = ()
    cost: CostReport = field(default_factory=CostReport)

    def to_record(self) -> dict[str, Any]:
        """Return this detail as a JSON-serialisable document."""
        return {
            "run": self.run.to_record(),
            "stages": [stage.to_record() for stage in self.stages],
            "evidence_ids": list(self.evidence_ids),
            "result": self.result,
            "errors": list(self.errors),
            "cost": self.cost.to_record(),
        }


@dataclass(frozen=True, slots=True)
class RunReplay:
    """A past run rebuilt from its events and nothing else.

    Article I in a payload: what a replay shows is derived from the trace, so
    anything visible here is something the trace can reproduce.
    """

    run_id: str
    events: tuple[Mapping[str, Any], ...] = ()
    view: RunDetail | None = None

    def to_record(self) -> dict[str, Any]:
        """Return this replay as a JSON-serialisable document."""
        return {
            "run_id": self.run_id,
            "events": [dict(event) for event in self.events],
            "view": self.view.to_record() if self.view else {},
        }


@dataclass(frozen=True, slots=True)
class InvestigationOutcome:
    """What one ``investigate`` produced."""

    run_id: str
    status: str = ""
    summary: str = ""
    report_path: str = ""
    evidence_count: int = 0
    cost: CostReport = field(default_factory=CostReport)

    def to_record(self) -> dict[str, Any]:
        """Return this outcome as a JSON-serialisable document."""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "summary": self.summary,
            "report_path": self.report_path,
            "evidence_count": self.evidence_count,
            "cost": self.cost.to_record(),
        }


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """One LLM provider, and whether this deployment can use it.

    ``local`` is reported for every provider rather than only the ones that
    are: a listing that only marked the local one would make "which of these
    leaves my infrastructure" a question about absence.
    """

    provider_id: str
    configured: bool = False
    local: bool = False
    verified: bool = False
    model_id: str = ""
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this status as a JSON-serialisable document."""
        return {
            "provider_id": self.provider_id,
            "configured": self.configured,
            "local": self.local,
            "verified": self.verified,
            "model_id": self.model_id,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class IntegrationStatus:
    """One vendor integration, and whether it is usable right now."""

    integration: str
    configured: bool = False
    healthy: bool = False
    credential_state: str = ""
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this status as a JSON-serialisable document."""
        return {
            "integration": self.integration,
            "configured": self.configured,
            "healthy": self.healthy,
            "credential_state": self.credential_state,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class CredentialFieldSpec:
    """One field an integration needs, as a prompt can ask for it.

    Carried out of the credential schema rather than hard-coded per vendor,
    which is what makes adding an integration a package rather than a change to
    the wizard. ``secret`` is what decides whether the prompt echoes — get that
    wrong and a token is on somebody's screen during a screen share.
    """

    name: str
    label: str = ""
    secret: bool = True
    required: bool = True
    help: str = ""

    @property
    def prompt(self) -> str:
        """Return the text the wizard shows when asking for this."""
        return self.label or self.name.replace("_", " ")

    def to_record(self) -> dict[str, Any]:
        """Return this field as a JSON-serialisable document."""
        return {
            "name": self.name,
            "label": self.prompt,
            "secret": self.secret,
            "required": self.required,
            "help": self.help,
        }


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    """One effective configuration value, and where it came from.

    The source node is not decoration. "Why is this team using that model" is
    asked constantly on a deep tree, and answering it by walking the tree by
    hand is how nobody ends up asking.
    """

    path: str
    value: str
    source_node_id: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this entry as a JSON-serialisable document."""
        return {
            "path": self.path,
            "value": self.value,
            "source_node_id": self.source_node_id,
        }


@dataclass(frozen=True, slots=True)
class ConfigView:
    """A team's effective configuration, every value attributed."""

    node_id: str
    entries: tuple[ConfigEntry, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return this view as a JSON-serialisable document."""
        return {
            "node_id": self.node_id,
            "entries": [entry.to_record() for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class ConfigChange:
    """The outcome of one attempted configuration write."""

    node_id: str
    path: str
    before: str = ""
    after: str = ""
    applied: bool = False
    requires_approval: bool = False
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this change as a JSON-serialisable document."""
        return {
            "node_id": self.node_id,
            "path": self.path,
            "before": self.before,
            "after": self.after,
            "applied": self.applied,
            "requires_approval": self.requires_approval,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ConfigDelta:
    """One path where two nodes' effective configuration differs."""

    path: str
    left: str = ""
    right: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this delta as a JSON-serialisable document."""
        return {"path": self.path, "left": self.left, "right": self.right}


@dataclass(frozen=True, slots=True)
class ConfigDiff:
    """How two nodes' effective configuration differ."""

    left_node_id: str
    right_node_id: str
    deltas: tuple[ConfigDelta, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return this diff as a JSON-serialisable document."""
        return {
            "left_node_id": self.left_node_id,
            "right_node_id": self.right_node_id,
            "deltas": [delta.to_record() for delta in self.deltas],
        }


@dataclass(frozen=True, slots=True)
class ScheduleSummary:
    """One scheduled investigation."""

    job_id: str
    objective: str = ""
    cron: str = ""
    timezone: str = ""
    enabled: bool = True
    team_node_id: str = ""
    next_fire_at: datetime | None = None
    disabled_reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this schedule as a JSON-serialisable document."""
        return {
            "job_id": self.job_id,
            "objective": self.objective,
            "cron": self.cron,
            "timezone": self.timezone,
            "enabled": self.enabled,
            "team_node_id": self.team_node_id,
            "next_fire_at": _moment(self.next_fire_at),
            "disabled_reason": self.disabled_reason,
        }


@dataclass(frozen=True, slots=True)
class EstateResource:
    """One thing the deployment is responsible for, as a table row shows it.

    ``health`` is the reported state — absence, maintenance and freshness
    already applied by the deployment — and ``stored_health`` is what was last
    derived. Both travel, because an operator seeing ``stale`` immediately asks
    what it was stale *at* and a second command to find out is a second command.
    """

    resource_id: str
    kind: str = ""
    display_name: str = ""
    health: str = ""
    stored_health: str = ""
    source: str = ""
    sources: tuple[str, ...] = ()
    native_id: str = ""
    parent_id: str = ""
    is_stale: bool = False
    labels: tuple[str, ...] = ()
    last_seen_at: datetime | None = None
    absent_since: datetime | None = None
    maintenance_until: datetime | None = None
    maintenance_reason: str = ""
    explanation: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "display_name": self.display_name,
            "health": self.health,
            "stored_health": self.stored_health,
            "source": self.source,
            "sources": list(self.sources),
            "native_id": self.native_id,
            "parent_id": self.parent_id,
            "is_stale": self.is_stale,
            "labels": list(self.labels),
            "last_seen_at": _moment(self.last_seen_at),
            "absent_since": _moment(self.absent_since),
            "maintenance_until": _moment(self.maintenance_until),
            "maintenance_reason": self.maintenance_reason,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EstateHealthSignal:
    """One named observation behind a resource's state."""

    name: str
    value: str
    observed_at: datetime | None = None
    source: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "name": self.name,
            "value": self.value,
            "observed_at": _moment(self.observed_at),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class EstateTransition:
    """One recorded change of a resource's state."""

    occurred_at: datetime | None
    state: str
    previous_state: str = ""
    rule: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "occurred_at": _moment(self.occurred_at),
            "state": self.state,
            "previous_state": self.previous_state,
            "rule": self.rule,
        }


@dataclass(frozen=True, slots=True)
class EstateReference:
    """A run or an incident that touched a resource."""

    reference_kind: str
    reference_id: str
    recorded_at: datetime | None = None
    summary: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "reference_kind": self.reference_kind,
            "reference_id": self.reference_id,
            "recorded_at": _moment(self.recorded_at),
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class EstateResourceDetail:
    """One resource's page: its state, why, its history, and what touched it."""

    resource: EstateResource
    rule: str = ""
    raw_status: str = ""
    explanation: str = ""
    freshness_seconds: int = 0
    rollup_rule: str = ""
    signals: tuple[EstateHealthSignal, ...] = ()
    transitions: tuple[EstateTransition, ...] = ()
    references: tuple[EstateReference, ...] = ()
    children: tuple[EstateResource, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "resource": self.resource.to_record(),
            "rule": self.rule,
            "raw_status": self.raw_status,
            "explanation": self.explanation,
            "freshness_seconds": self.freshness_seconds,
            "rollup_rule": self.rollup_rule,
            "signals": [signal.to_record() for signal in self.signals],
            "transitions": [entry.to_record() for entry in self.transitions],
            "references": [entry.to_record() for entry in self.references],
            "children": [child.to_record() for child in self.children],
        }


@dataclass(frozen=True, slots=True)
class EstateSummaryReport:
    """The estate in the numbers a first screen shows.

    ``problems`` is carried rather than derived from ``by_health``, because
    resources in maintenance are in the estate and out of the problem count and
    a reader recomputing it would have to know that rule too.
    """

    total: int = 0
    problems: int = 0
    maintenance: int = 0
    absent: int = 0
    captured_at: datetime | None = None
    by_kind: Mapping[str, int] = field(default_factory=dict)
    by_health: Mapping[str, int] = field(default_factory=dict)
    by_source: Mapping[str, int] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return the document ``--json`` prints."""
        return {
            "total": self.total,
            "problems": self.problems,
            "maintenance": self.maintenance,
            "absent": self.absent,
            "captured_at": _moment(self.captured_at),
            "by_kind": dict(self.by_kind),
            "by_health": dict(self.by_health),
            "by_source": dict(self.by_source),
        }


@dataclass(frozen=True, slots=True)
class MemoryHit:
    """One episode a memory search matched."""

    episode_id: str
    title: str = ""
    score: float = 0.0
    components: tuple[str, ...] = ()
    occurred_at: datetime | None = None
    root_cause: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this hit as a JSON-serialisable document."""
        return {
            "episode_id": self.episode_id,
            "title": self.title,
            "score": round(self.score, 6),
            "components": list(self.components),
            "occurred_at": _moment(self.occurred_at),
            "root_cause": self.root_cause,
        }


@dataclass(frozen=True, slots=True)
class MemoryStats:
    """What the episodic corpus currently holds."""

    episodes: int = 0
    components: int = 0
    mean_effectiveness: float = 0.0
    oldest_at: datetime | None = None
    newest_at: datetime | None = None
    read_enabled: bool = True
    write_enabled: bool = True

    def to_record(self) -> dict[str, Any]:
        """Return these statistics as a JSON-serialisable document."""
        return {
            "episodes": self.episodes,
            "components": self.components,
            "mean_effectiveness": round(self.mean_effectiveness, 6),
            "oldest_at": _moment(self.oldest_at),
            "newest_at": _moment(self.newest_at),
            "read_enabled": self.read_enabled,
            "write_enabled": self.write_enabled,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """One thing ``doctor`` looked at.

    ``remedy`` is required in spirit and defaulted in code only so a check that
    passed does not have to invent one. A diagnostic that says what is wrong and
    not what to do about it is a diagnostic somebody has to research.
    """

    name: str
    state: CheckState = CheckState.OK
    detail: str = ""
    remedy: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this check as a JSON-serialisable document."""
        return {
            "name": self.name,
            "state": self.state.value,
            "detail": self.detail,
            "remedy": self.remedy,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """Everything ``doctor`` looked at, and whether the deployment is usable."""

    checks: tuple[DiagnosticCheck, ...] = ()
    version: str = ""

    @property
    def failures(self) -> tuple[DiagnosticCheck, ...]:
        """Return the checks that failed outright."""
        return tuple(check for check in self.checks if check.state is CheckState.FAILED)

    @property
    def warnings(self) -> tuple[DiagnosticCheck, ...]:
        """Return the checks that passed with a caveat."""
        return tuple(check for check in self.checks if check.state is CheckState.WARNING)

    @property
    def healthy(self) -> bool:
        """Return whether anything is broken enough to stop an investigation."""
        return not self.failures

    def to_record(self) -> dict[str, Any]:
        """Return this report as a JSON-serialisable document."""
        return {
            "healthy": self.healthy,
            "version": self.version,
            "checks": [check.to_record() for check in self.checks],
            "failures": len(self.failures),
            "warnings": len(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """One resumable REPL session."""

    session_id: str
    objective: str = ""
    started_at: datetime | None = None
    updated_at: datetime | None = None
    turns: int = 0
    evidence: int = 0
    awaiting: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this session as a JSON-serialisable document."""
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "started_at": _moment(self.started_at),
            "updated_at": _moment(self.updated_at),
            "turns": self.turns,
            "evidence": self.evidence,
            "awaiting": self.awaiting,
        }


@dataclass(frozen=True, slots=True)
class PendingInteraction:
    """A question or an approval a run has stopped for."""

    interaction_id: str
    run_id: str
    kind: str = ""
    summary: str = ""
    text: str = ""
    options: tuple[str, ...] = ()
    reason: str = ""
    action: str = ""
    diff: str = ""
    blast_radius: str = ""
    rollback_plan: str = ""
    raised_at: datetime | None = None
    expires_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        """Return this interaction as a JSON-serialisable document."""
        return {
            "interaction_id": self.interaction_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "summary": self.summary,
            "text": self.text,
            "options": list(self.options),
            "reason": self.reason,
            "action": self.action,
            "diff": self.diff,
            "blast_radius": self.blast_radius,
            "rollback_plan": self.rollback_plan,
            "raised_at": _moment(self.raised_at),
            "expires_at": _moment(self.expires_at),
        }


@dataclass(frozen=True, slots=True)
class OnboardingOutcome:
    """What the guided first run left behind."""

    provider_id: str = ""
    model_id: str = ""
    integrations: tuple[IntegrationStatus, ...] = ()
    verified: bool = False
    steps: tuple[str, ...] = ()
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this outcome as a JSON-serialisable document."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "integrations": [status.to_record() for status in self.integrations],
            "verified": self.verified,
            "steps": list(self.steps),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class LifecycleOutcome:
    """What ``update`` or ``uninstall`` did.

    ``removed`` lists paths rather than counting them. An operator running
    ``uninstall`` is entitled to see exactly what went, and a number is not an
    answer to "did it take my configuration".
    """

    action: str
    changed: bool = False
    from_version: str = ""
    to_version: str = ""
    removed: tuple[str, ...] = ()
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return this outcome as a JSON-serialisable document."""
        return {
            "action": self.action,
            "changed": self.changed,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "removed": list(self.removed),
            "detail": self.detail,
        }


def records_of(values: Sequence[Any]) -> list[dict[str, Any]]:
    """Return the documents of a sequence of payload values."""
    return [value.to_record() for value in values]


__all__ = [
    "CheckState",
    "ConfigChange",
    "ConfigDelta",
    "ConfigDiff",
    "ConfigEntry",
    "ConfigView",
    "CostReport",
    "CredentialFieldSpec",
    "DiagnosticCheck",
    "DiagnosticReport",
    "EstateHealthSignal",
    "EstateReference",
    "EstateResource",
    "EstateResourceDetail",
    "EstateSummaryReport",
    "EstateTransition",
    "IntegrationStatus",
    "InvestigationOutcome",
    "LifecycleOutcome",
    "MemoryHit",
    "MemoryStats",
    "OnboardingOutcome",
    "PendingInteraction",
    "ProviderStatus",
    "RunDetail",
    "RunReplay",
    "RunSummary",
    "ScheduleSummary",
    "SessionSummary",
    "SpendLine",
    "SpendReport",
    "StageReport",
    "aggregate_spend",
    "records_of",
]
