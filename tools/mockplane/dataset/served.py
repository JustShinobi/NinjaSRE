"""The half of the dataset a live deployment already answers.

Runs, transcripts, interactions, approvals, memory, knowledge, configuration,
identity and audit — recorded rather than projected, because the gateway serves
every one of them today.

Two properties are load-bearing and neither is visible in any single record.
The history is coherent: a run starts before it finishes, an episode is created
after the run that produced it, an approval is requested before it expires. And
the two halves agree: the investigations here are about the guests and the
findings the estate half actually contains, so a screen that joins a run to its
subject has something to join to.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from config.constants.config_service import MODEL_ROLES
from config.constants.first_run import (
    SETUP_READINESS_ABSENT,
    SETUP_READINESS_CONFIGURED,
    SETUP_READINESS_VERIFIED,
    SETUP_STATE_BLOCKED,
    SETUP_STATE_DONE,
    SETUP_STATE_READY,
    SETUP_STEP_DURABLE_CREDENTIAL,
    SETUP_STEP_FIRST_INVESTIGATION,
    SETUP_STEP_INFRASTRUCTURE_SOURCE,
    SETUP_STEP_INVESTIGATION_RUNTIME,
    SETUP_STEP_MODEL_PROVIDER,
)
from core.llm.onboarding import ProviderOnboarding, all_onboardings
from gateway.webhooks.router import PROFILES
from integrations._catalogue.discovery import catalogue as integration_catalogue
from integrations._catalogue.entry import CatalogueEntry
from integrations._catalogue.gaps import gaps
from integrations._verification.permissions import RequiredPermission
from platform.config_service.schema.policies import GuardianSettings
from platform.credentials.schemas import CredentialField
from platform.guardian.resolution import resolve as resolve_guardian
from platform.guardian.topology import ClusterShape
from platform.identity.permissions import Permission
from tools.mockplane.dataset import profile
from tools.mockplane.records import CapturedRecord, Provenance, Request

_CAPTURED: Final = datetime.fromisoformat(profile.CAPTURED_AT)

ORG_NODE: Final = "org-northwind"
PLATFORM_TEAM_NODE: Final = "team-platform"
STORAGE_TEAM_NODE: Final = "team-storage"

OPERATOR: Final = "user-operator"
REVIEWER: Final = "user-reviewer"
VIEWER: Final = "user-viewer"
AUTOMATION: Final = "user-automation"

#: What a sign-in against this dataset returns. Obviously not a credential: the
#: mock resolves no token, and a fixture holding something that looked like a
#: real one is a fixture somebody eventually tries in a deployment.
SIGN_IN_TOKEN: Final = "fixture-session-token"

#: The permissions a full operator holds here. Spelled rather than imported so
#: the fixture states what it claims rather than tracking a runtime enum — a
#: fixture that changed when a permission was renamed would hide the change the
#: console has to cope with.
OPERATOR_PERMISSIONS: Final[tuple[str, ...]] = (
    "approval.read",
    # Reading the proposal queue takes ``approval.read``; answering one takes
    # this. The console renders no approve or reject control without it, so a
    # dataset whose operator lacked it served a queue nobody could empty.
    "approval.review",
    "audit.read",
    "config.read",
    "config.write",
    "identity.read",
    "integration.manage",
    "investigation.read",
    "investigation.run",
    "knowledge.read",
    "memory.read",
    "remediation.approve",
    "remediation.execute",
    "schedule.manage",
    "token.manage",
)

VIEWER_PERMISSIONS: Final[tuple[str, ...]] = (
    "approval.read",
    "config.read",
    "investigation.read",
    "knowledge.read",
    "memory.read",
)


def at(*, days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    """Return an instant that far before the survey, as the API spells one."""
    return (_CAPTURED - timedelta(days=days, hours=hours, minutes=minutes)).isoformat()


def _record(
    slug: str, arguments: Mapping[str, str], body: Any, *, method: str = "GET"
) -> CapturedRecord:
    return CapturedRecord(
        slug=slug,
        arguments=dict(arguments),
        status=200,
        body=body,
        provenance=Provenance.GATEWAY,
        request=Request(method=method, path=slug),
    )


#: The specialists this team declares, the prompt it overrides, and the budgets
#: it lowered. Three specialists so the topology has a shape, and one of them
#: switched off — a disabled specialist has to be drawn faint rather than
#: omitted, and a dataset where every one was on would never photograph that.
AGENTS_SECTION: Final[Mapping[str, Any]] = {
    "prompts": {
        "investigator": "Prefer the storage evidence before the network evidence on this estate.",
    },
    "subagents": [
        {
            "name": "storage",
            "description": "Datastore fill, volume fill, and what a backup job is protecting.",
            "capabilities": ["estate.storage_pressure", "estate.enable_backup_job"],
            "max_iterations": 6,
            "model_role": "subagent",
            "enabled": True,
        },
        {
            "name": "cluster-health",
            "description": "What is failed on a node, and what quorum costs if it goes.",
            "capabilities": ["estate.failed_units"],
            "max_iterations": 6,
            "model_role": "subagent",
            "enabled": True,
        },
        {
            "name": "change-historian",
            "description": "Reads the change history around the incident window.",
            "capabilities": [],
            "max_iterations": 4,
            "model_role": "subagent",
            "enabled": False,
        },
    ],
    "max_iterations": 12,
    "max_parallel_subagents": 3,
    "max_subagent_depth": 1,
    "tool_budget": 40,
}

#: One server outside this deployment, so the tools tab has an outside origin to
#: name. Its tools are not listed: nothing enumerates them without reaching it.
CAPABILITIES_SECTION: Final[Mapping[str, Any]] = {
    "protocol_servers": [
        {
            "name": "runbooks",
            "protocol": "mcp",
            "transport": "http",
            "url": "https://runbooks.rushes.example.invalid/mcp",
            "enabled": True,
        },
    ],
}


def _policy_document(node_id: str) -> dict[str, Any]:
    """Return the posture this node resolves to, as the export format spells it.

    One function rather than a literal per caller, because two surfaces read it:
    the policy screen shows the document, and the agent screen shows what it
    would decide. A second copy would let the two disagree, which is the exact
    failure the outlook exists to make impossible.

    One rule per posture the primary story names, so the screen shows the three
    that matter rather than one of each shape: the safe default everywhere, one
    relaxation, and one resource that is never touched unattended.
    """
    return {
        "node_id": node_id,
        "dry_run": False,
        "rules": [
            {
                "scope": {"kind": "deployment"},
                "level": "propose_only",
                "risk_bound": "low",
            },
            {
                "scope": {"kind": "capability", "capability": "unlock_guest"},
                "level": "act_and_report",
                "risk_bound": "low",
            },
            {
                "scope": {"kind": "labels", "labels": {"env": "lab"}},
                "level": "act_on_low_risk",
                "risk_bound": "moderate",
            },
        ],
        "freezes": [
            {
                "name": "nightly-backups",
                "scope": {"kind": "resource", "resource_id": "store-cove"},
                "start": "01:00",
                "end": "04:00",
                "timezone": "Europe/Lisbon",
                "reason": "backups run",
            }
        ],
        "budgets": [
            {
                "name": "hourly",
                "counted_by": "resource",
                "limit": 5,
                "interval_seconds": 3600.0,
            }
        ],
        "overrides": [],
    }


# --- Recurring investigations, and the record a posture is replayed against -------

#: Two schedules, one running and one not, so both states are on the screen and
#: both are photographed.
SCHEDULES: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "job_id": "weekly-storage-review",
        "name": "Weekly storage review",
        "team_node_id": "team-storage",
        "cron": "0 7 * * 1",
        "objective": "Check datastore fill and backup coverage across the estate.",
        "timezone": "Europe/Lisbon",
        "enabled": True,
        "next_run_at": "2026-08-17T07:00:00+00:00",
    },
    {
        "job_id": "nightly-quorum-check",
        "name": "Nightly quorum check",
        "team_node_id": "team-platform",
        "cron": "0 3 * * *",
        "objective": "Establish whether the cluster would survive losing a node.",
        "timezone": "Europe/Lisbon",
        "enabled": False,
        "next_run_at": None,
    },
)

#: What the policy engine decided about two actions that actually happened.
#: ``before`` and ``after`` are the same because the document being replayed is
#: the one that is stored — which is the question the agent screen asks.
REPLAYED_ACTIONS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "action_id": "act-2026-0814-01",
        "capability": "restart_workload",
        "subjects": ["ct-101"],
        "at": "2026-08-14T09:12:00+00:00",
        "before": "propose_only",
        "after": "propose_only",
        "before_reason": "restart_workload on ct-101 is proposed rather than run.",
        "after_reason": "restart_workload on ct-101 is proposed rather than run.",
        "changed": False,
        "more_autonomous": False,
    },
    {
        "action_id": "act-2026-0814-02",
        "capability": "unlock_guest",
        "subjects": ["vm-204"],
        "at": "2026-08-14T09:40:00+00:00",
        "before": "act_and_report",
        "after": "act_and_report",
        "before_reason": "unlock_guest on vm-204 resolves to act_and_report.",
        "after_reason": "unlock_guest on vm-204 resolves to act_and_report.",
        "changed": False,
        "more_autonomous": False,
    },
)


# --- Runs -------------------------------------------------------------------------

RUNS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "run_id": "run-0001",
        "status": "succeeded",
        "trigger": "alert",
        "started_at": at(days=2, minutes=41),
        "finished_at": at(days=2, minutes=27),
        "summary": "A guest reached the ceiling of its own volume while the datastore "
        "under it still read comfortable.",
    },
    {
        "run_id": "run-0002",
        "status": "succeeded",
        "trigger": "schedule",
        "started_at": at(days=1, hours=3),
        "finished_at": at(days=1, hours=2, minutes=48),
        "summary": "Quorum has no margin: two of two required votes, and the device in "
        "the membership view carries none.",
    },
    {
        "run_id": "run-0003",
        "status": "running",
        "trigger": "alert",
        "started_at": at(minutes=4),
        "finished_at": None,
        "summary": None,
    },
    {
        "run_id": "run-0004",
        "status": "failed",
        "trigger": "manual",
        "started_at": at(days=3, hours=6),
        "finished_at": at(days=3, hours=5, minutes=51),
        "summary": "The investigation could not reach the metrics agent; it is one of the "
        "failed units on the primary.",
    },
    {
        "run_id": "run-0005",
        "status": "awaiting_approval",
        "trigger": "alert",
        "started_at": at(minutes=22),
        "finished_at": None,
        "summary": "A remediation is proposed and is waiting for a decision.",
    },
    {
        "run_id": "run-0006",
        "status": "cancelled",
        "trigger": "manual",
        "started_at": at(days=5, hours=1),
        "finished_at": at(days=5, minutes=58),
        "summary": "Cancelled by the operator after the cause was identified by hand.",
    },
)

#: The window the storage investigation asked what changed in: the six hours
#: ending when the run started. Fixed off the capture like every other instant
#: here, so the ruler's geometry is the same picture on every capture rather
#: than whatever the clock said.
CHANGE_WINDOW_HOURS: Final = 6

#: What ``changes_in_window`` answered for run-0001. Written in the shape
#: ``platform.changes.service.ChangeAnswer.to_record`` produces — the same
#: record the trace stores and the console's ruler reads back — because a
#: fixture in any other shape is a fixture that teaches the console to read a
#: field the deployment never sends. That is not hypothetical: the ruler read
#: ``instant`` until this record was written, and no test outside the console
#: had ever seen the real one.
_CHANGES_IN_WINDOW: Final[Mapping[str, Any]] = {
    "tool": "changes_in_window",
    "resource_id": "proxmox:container/hal9000/110",
    "resource": "adguard",
    "window": {
        "start": at(days=2, hours=CHANGE_WINDOW_HOURS, minutes=41),
        "end": at(days=2, minutes=41),
        "hours": CHANGE_WINDOW_HOURS,
    },
    "sources": ["infra_apply"],
    "answered": True,
    "statement": (
        "Two changes landed in the six hours before this run, and one of them manages "
        "the container that filled."
    ),
    "total": 2,
    "truncated": False,
    "degraded": [],
    "changes": [
        {
            "change_id": "9f2c1ab",
            "source": "infra_apply",
            "component": "adguard",
            "author": "erik",
            "message": "feat(adguard): keep query logs for a fortnight",
            "message_truncated": False,
            "occurred_at": at(days=2, hours=3, minutes=41),
            "applied": True,
            "applied_at": at(days=2, hours=3, minutes=12),
            "paths": ["services/adguard/stack/values.yaml"],
            "paths_seen": 1,
            "paths_truncated": False,
            "redactions": [],
            "detail": {},
            "strength": "manages_resource",
            "temporal_only": False,
            "why": (
                "services/adguard/stack/values.yaml belongs to the adguard component, "
                "which manages this container."
            ),
            "correlated_component": "adguard",
            "matched_path": "services/adguard/stack/values.yaml",
            "matched_name": "adguard",
            "chain": ["path", "component", "resource"],
        },
        {
            "change_id": "b0c99fe",
            "source": "infra_apply",
            "component": "storage",
            "author": "erik",
            "message": "chore(storage): widen the backup datastore",
            "message_truncated": False,
            "occurred_at": at(days=2, hours=1, minutes=11),
            "applied": True,
            "applied_at": at(days=2, hours=1, minutes=4),
            "paths": ["services/storage/datastore/main.tf"],
            "paths_seen": 1,
            "paths_truncated": False,
            "redactions": [],
            "detail": {},
            "strength": "window_only",
            "temporal_only": True,
            "why": "This change happened in the same window and nothing connects it.",
            "correlated_component": "",
            "matched_path": "",
            "matched_name": "",
            "chain": [],
        },
    ],
    "text": (
        "Two changes landed in the six hours before this run. One manages the container "
        "that filled; the other shares the window and nothing else."
    ),
}


_TURNS: Final[Mapping[str, Sequence[Mapping[str, Any]]]] = {
    "run-0001": (
        {
            "turn_id": "turn-0001-1",
            "index": 0,
            "model": "operator-configured",
            "selection_rationale": "storage pressure is a first-party domain",
            "calls": [
                {
                    "call_id": "call-0001-1",
                    "name": "estate.storage_pressure",
                    "status": "succeeded",
                    "duration_ms": 412,
                    "error": None,
                }
            ],
        },
        {
            "turn_id": "turn-0001-2",
            "index": 1,
            "model": "operator-configured",
            "selection_rationale": "the datastore reading disagrees with the volume reading",
            "calls": [
                {
                    "call_id": "call-0001-2",
                    "name": "estate.volume_fill",
                    "status": "succeeded",
                    "duration_ms": 188,
                    "error": None,
                },
                {
                    "call_id": "call-0001-3",
                    "name": "knowledge.search",
                    "status": "succeeded",
                    "duration_ms": 96,
                    "error": None,
                },
                # The call the run screen's change ruler is drawn from. The
                # console holds no query of its own for it: what the picture
                # shows is what the investigation asked and was told, so the
                # fixture has to carry the answer rather than the question.
                {
                    "call_id": "call-0001-4",
                    "name": "changes_in_window",
                    "status": "succeeded",
                    "duration_ms": 341,
                    "error": None,
                    "arguments": {
                        "resource": "proxmox:container/hal9000/110",
                        "hours": CHANGE_WINDOW_HOURS,
                    },
                    "result": dict(_CHANGES_IN_WINDOW),
                },
            ],
        },
        {
            "turn_id": "turn-0001-3",
            "index": 2,
            "model": "operator-configured",
            "selection_rationale": "enough evidence to conclude",
            "calls": [],
        },
    ),
    "run-0003": (
        {
            "turn_id": "turn-0003-1",
            "index": 0,
            "model": "operator-configured",
            "selection_rationale": "the alert names a unit, so start at the node",
            "calls": [
                {
                    "call_id": "call-0003-1",
                    "name": "estate.failed_units",
                    "status": "succeeded",
                    "duration_ms": 233,
                    "error": None,
                }
            ],
        },
        {
            "turn_id": "turn-0003-2",
            "index": 1,
            "model": "operator-configured",
            "selection_rationale": "one of the failed units is the hardening script",
            "calls": [
                {
                    "call_id": "call-0003-2",
                    "name": "knowledge.search",
                    "status": "running",
                    "duration_ms": 0,
                    "error": None,
                }
            ],
        },
    ),
}


def runs_records() -> tuple[CapturedRecord, ...]:
    """Return the run list, each run's detail, its transcript and its replay."""
    records: list[CapturedRecord] = [_record("runs", {}, {"runs": list(RUNS)})]
    for run in RUNS:
        identifier = str(run["run_id"])
        records.append(_record("run-detail", {"run_id": identifier}, dict(run)))
        turns = list(_TURNS.get(identifier, ()))
        records.append(
            _record("run-threads", {"run_id": identifier}, {"run_id": identifier, "turns": turns})
        )
        records.append(
            _record(
                "run-replay",
                {"run_id": identifier},
                {
                    "run_id": identifier,
                    "turns": turns,
                    "total_cost": round(0.031 * (len(turns) + 1), 4),
                    "total_tokens": 1840 * (len(turns) + 1),
                    "is_interrupted": run["status"] == "cancelled",
                },
            )
        )
    return tuple(records)


# --- Interactions and approvals ----------------------------------------------------

INTERACTIONS: Final[Mapping[str, Sequence[Mapping[str, Any]]]] = {
    "run-0003": (
        {
            "interaction_id": "int-0001",
            "run_id": "run-0003",
            "kind": "question",
            "text": "The hardening unit failed at boot. Should the investigation read the "
            "boot journal as well?",
            "options": ["yes", "no"],
            "is_open": True,
            "reason": "",
        },
    ),
    "run-0005": (
        {
            "interaction_id": "int-0002",
            "run_id": "run-0005",
            "kind": "approval",
            "text": "Enable the disabled backup job covering the primary's guests.",
            "options": [],
            "is_open": True,
            "reason": "",
        },
    ),
    "run-0001": (
        {
            "interaction_id": "int-0003",
            "run_id": "run-0001",
            "kind": "question",
            "text": "Which datastore should the freed space be measured against?",
            "options": ["the guest volume", "the datastore"],
            "is_open": False,
            "reason": "answered",
        },
    ),
}

APPROVALS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "approval_id": "apr-0001",
        "run_id": "run-0005",
        "action": "estate.enable_backup_job",
        "side_effect_level": "write",
        "summary": "Enable the disabled job so the primary's guests are covered at all.",
        "requested_at": at(minutes=21),
        "expires_at": at(minutes=-99),
        "state": "pending",
        "arguments": {"job_id": "backup-7d831311"},
        "decided_at": None,
        "decided_by": None,
        "reason": None,
        "rollback_plan": {
            "plan_id": "plan-0001",
            "approval_id": "apr-0001",
            "notes": "Disabling it again restores the state exactly, and takes one call.",
            "steps": [
                {
                    "ordinal": 1,
                    "description": "Disable the job again",
                    "capability": "estate.disable_backup_job",
                    "arguments": {"job_id": "backup-7d831311"},
                }
            ],
        },
    },
    {
        "approval_id": "apr-0002",
        "run_id": "run-0001",
        "action": "estate.expand_volume",
        "side_effect_level": "write",
        "summary": "Grow the volume that is at the ceiling of its own allocation.",
        "requested_at": at(days=2, minutes=33),
        "expires_at": at(days=1, minutes=33),
        "state": "pending",
        "arguments": {"volume_id": "vm-100-disk-0", "add_bytes": 16_000_000_000},
        "decided_at": None,
        "decided_by": None,
        "reason": None,
        "rollback_plan": None,
    },
)


def interaction_records() -> tuple[CapturedRecord, ...]:
    """Return each run's open questions and approvals, and the approval queue."""
    records = [
        _record("interactions", {"run_id": run_id}, {"interactions": list(found)})
        for run_id, found in INTERACTIONS.items()
    ]
    records.append(_record("approvals", {}, {"approvals": list(APPROVALS)}))
    for approval in APPROVALS:
        records.append(
            _record(
                "approval-detail", {"approval_id": str(approval["approval_id"])}, dict(approval)
            )
        )
    return tuple(records)


PROPOSALS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "proposal_id": "prop-0001",
        "proposal_type": "operating_context",
        "node_id": ORG_NODE,
        "summary": "Record that LXC guest memory is read from the host",
        "rationale": "Three investigations of container memory each had to rediscover it.",
        "evidence": ["run-0001/turn-4", "run-0003/turn-2"],
        "run_id": "run-0003",
        "correlation_id": "agents.operating_context.Metrics",
        "payload": {
            "agents": {
                "operating_context": {
                    "sections": {
                        "Metrics": "Container memory for LXC guests is read from the host, "
                        "not from inside the guest."
                    }
                }
            }
        },
        "effect": {"mechanism": "context-preview", "target": ORG_NODE},
        "state": "pending",
        "proposed_at": at(minutes=48),
        "decided_at": None,
        "decided_by": "",
        "reason": "",
        "prior_rejections": [],
    },
    {
        "proposal_id": "prop-0002",
        "proposal_type": "detector",
        "node_id": ORG_NODE,
        "summary": "Watch the datastore fill the runbook already says to check",
        "rationale": "The verification document states this check and nothing performs it.",
        "evidence": [
            "No datastore is above its safe fill — a datastore past this cannot "
            "complete a snapshot of its largest guest.",
            "corpus:docs/verification.md",
        ],
        "run_id": "run-0005",
        "correlation_id": "detector:corpus-no-datastore-is-above-its-safe-fill",
        "payload": {
            "detector_id": "corpus-no-datastore-is-above-its-safe-fill",
            "name": "No datastore is above its safe fill",
            "description": "A datastore past this cannot complete a snapshot.",
            "signal": "datastore.used_percent",
            "kind": "threshold",
            "comparison": "above",
            "fire_value": 85.0,
            "enabled": False,
            "origin": "corpus:docs/verification.md",
        },
        "effect": {
            "mechanism": "detector-dry-run",
            "target": "corpus-no-datastore-is-above-its-safe-fill",
        },
        "state": "pending",
        "proposed_at": at(days=1, minutes=12),
        "decided_at": None,
        "decided_by": "",
        "reason": "",
        "prior_rejections": [
            {
                "proposal_id": "prop-0000",
                "reason": "The snapshot window runs nightly; 85 is normal on this store.",
                "decided_by": OPERATOR,
                "decided_at": at(days=9),
            }
        ],
    },
)

#: How this deployment has answered so far. Both numbers, never the ratio alone.
PROPOSAL_ACCEPTANCE: Final[Mapping[str, Any]] = {
    "decided": 5,
    "approved": 3,
    "rate": 0.6,
}


def proposal_records() -> tuple[CapturedRecord, ...]:
    """Return the proposal queue, its count, each proposal, and the answer to one."""
    records = [
        _record(
            "proposals",
            {},
            {"proposals": list(PROPOSALS), "acceptance": dict(PROPOSAL_ACCEPTANCE)},
        ),
        _record("proposal-count", {}, {"pending": len(PROPOSALS)}),
    ]
    records.extend(
        _record("proposal-detail", {"proposal_id": str(proposal["proposal_id"])}, dict(proposal))
        for proposal in PROPOSALS
    )
    # The decision, which the console reaches for every approve and every reject.
    # Recorded as an approval: the served answer is the same shape either way,
    # and ``applied`` is the sentence the owning path returns when it has
    # written the change — empty on a rejection, because nothing was written.
    records.extend(
        _record(
            "proposal-decision",
            {"proposal_id": str(proposal["proposal_id"])},
            {
                "proposal_id": proposal["proposal_id"],
                "state": "approved",
                "applied": f"{proposal['node_id']}: applied {proposal['summary']}",
            },
            method="POST",
        )
        for proposal in PROPOSALS
    )
    return tuple(records)


# --- Memory and knowledge ----------------------------------------------------------

EPISODES: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "episode_id": "ep-0001",
        "run_id": "run-0001",
        "title": "A guest volume filled while its datastore looked fine",
        "summary": "The datastore read 84% and the guest read 99.6%. The threshold that "
        "matters is the one on the volume.",
        "outcome": "resolved",
        "components": ["plateau", "store-linen"],
        "occurred_at": at(days=2, minutes=26),
    },
    {
        "episode_id": "ep-0002",
        "run_id": "run-0002",
        "title": "Quorum has no margin",
        "summary": "Two of two required votes, and the device in the membership view carries none.",
        "outcome": "acknowledged",
        "components": ["cluster"],
        "occurred_at": at(days=1, hours=2, minutes=47),
    },
    {
        "episode_id": "ep-0003",
        "run_id": "run-0004",
        "title": "The investigation could not reach the metrics agent",
        "summary": "The agent is one of the failed units on the primary; nothing was "
        "watching the watcher.",
        "outcome": "unresolved",
        "components": ["node01", "metrics-agent.service"],
        "occurred_at": at(days=3, hours=5, minutes=50),
    },
    {
        "episode_id": "ep-0004",
        "run_id": "run-0006",
        "title": "Name resolution stalled twice in one week",
        "summary": "Both guests responsible were near the ceiling of their own volumes.",
        "outcome": "resolved",
        "components": ["quartz", "sorrel"],
        "occurred_at": at(days=5, minutes=57),
    },
    {
        "episode_id": "ep-0005",
        "run_id": "run-0002",
        "title": "A kernel was installed and never booted",
        "summary": "The usual signal did not fire, so the first real boot of it will be "
        "an unplanned one.",
        "outcome": "acknowledged",
        "components": ["node01", "node02"],
        "occurred_at": at(days=1, hours=2, minutes=40),
    },
)

DOCUMENTS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "document_id": "doc-0001",
        "title": "Runbook: a guest volume near its ceiling",
        "content_type": "text/markdown",
        "checksum": "b6f1c0d2e4a58937",
        "source_uri": "knowledge://runbooks/volume-near-ceiling",
        "updated_at": at(days=12),
        "metadata": {"kind": "runbook", "reviewed": True},
    },
    {
        "document_id": "doc-0002",
        "title": "Postmortem: both nodes lost networking at boot",
        "content_type": "text/markdown",
        "checksum": "1d9a73be05c4f218",
        "source_uri": "knowledge://postmortems/network-at-boot",
        "updated_at": at(days=1, hours=9),
        "metadata": {"kind": "postmortem", "severity": "critical"},
    },
    {
        "document_id": "doc-0003",
        "title": "Runbook: quorum with no margin",
        "content_type": "text/markdown",
        "checksum": "77c0aa41e2b6d905",
        "source_uri": "knowledge://runbooks/quorum-margin",
        "updated_at": at(days=30),
        "metadata": {"kind": "runbook", "reviewed": False},
    },
)

_PASSAGES: Final[Mapping[str, Sequence[str]]] = {
    "doc-0001": (
        "A datastore threshold cannot see a guest at the ceiling of its own volume. "
        "Read both, and alert on whichever is worse.",
        "Growing the volume is reversible; growing the datastore usually is not.",
    ),
    "doc-0002": (
        "An upgrade renamed the interfaces. The bridge could not be built, and every "
        "service that depended on it failed at once, including the monitoring.",
        "The recovery needed physical access to both machines, because the path in "
        "depended on the thing that was down.",
    ),
    "doc-0003": (
        "With two nodes and no quorum device, losing either one makes the cluster "
        "filesystem read-only. The guests already running keep running.",
    ),
}


def memory_records() -> tuple[CapturedRecord, ...]:
    """Return the episodic corpus, its statistics, and the knowledge documents."""
    records: list[CapturedRecord] = [
        _record("episodes", {}, {"episodes": list(EPISODES)}),
        _record("memory-stats", {}, {"episode_count": len(EPISODES)}),
        _record("documents", {}, {"documents": list(DOCUMENTS)}),
    ]
    for document in DOCUMENTS:
        identifier = str(document["document_id"])
        records.append(
            _record(
                "document-detail",
                {"document_id": identifier},
                {
                    "document": dict(document),
                    "chunks": [
                        {"chunk_id": f"{identifier}-{index}", "ordinal": index, "text": text}
                        for index, text in enumerate(_PASSAGES.get(identifier, ()))
                    ],
                },
            )
        )
    return tuple(records)


def topology_records() -> tuple[CapturedRecord, ...]:
    """Return one service's dependencies, dependents and blast radius."""

    def node(identifier: str, name: str, kind: str) -> dict[str, Any]:
        return {
            "node_id": identifier,
            "name": name,
            "kind": kind,
            "owner_node_id": PLATFORM_TEAM_NODE,
            "properties": {"tier": kind},
        }

    view = {
        "node_id": "svc-ledger",
        "available": True,
        "reason": None,
        "truncated": False,
        "dependencies": [
            node("svc-store", "store-linen", "datastore"),
            node("svc-resolver", "quartz", "service"),
        ],
        "dependents": [
            node("svc-gateway", "harbour", "service"),
            node("svc-reporting", "lumen", "service"),
        ],
        "blast_radius": [
            {"depth": 1, "node": node("svc-gateway", "harbour", "service")},
            {"depth": 2, "node": node("svc-reporting", "lumen", "service")},
        ],
    }
    return (_record("topology", {"node_id": "svc-ledger"}, view),)


# --- Configuration -----------------------------------------------------------------

CONFIG_NODES: Final[tuple[Mapping[str, Any], ...]] = (
    {"node_id": ORG_NODE, "name": "Northwind", "kind": "organisation", "parent_id": None},
    {"node_id": PLATFORM_TEAM_NODE, "name": "Platform", "kind": "team", "parent_id": ORG_NODE},
    {"node_id": STORAGE_TEAM_NODE, "name": "Storage", "kind": "team", "parent_id": ORG_NODE},
    {
        "node_id": "env-production",
        "name": "Production",
        "kind": "environment",
        "parent_id": PLATFORM_TEAM_NODE,
    },
    {
        "node_id": "env-staging",
        "name": "Staging",
        "kind": "environment",
        "parent_id": PLATFORM_TEAM_NODE,
    },
)


#: The fields the editor draws, one per setting the effective view above holds.
#:
#: Hand-written to match that record rather than derived from the real schema,
#: and deliberately: this dataset is a *plausible deployment*, and a form
#: listing ninety fields nothing beside it shows a value for would be a screen
#: nobody could read a screenshot of. The derivation itself is proven where it
#: lives, against the schema, in the configuration service's own suite.
_CONFIG_FIELDS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "path": "investigation.max_loops",
        "label": "Max loops",
        "type": "integer",
        "description": "How many times one investigation may go round before it stops.",
        "help": "How many times one investigation may go round before it stops.",
        "section": "investigation",
        "section_summary": "What an investigation may spend before it reports.",
        "section_help": "What an investigation may spend before it reports.",
        "default": 12,
        "minimum": 1,
        "maximum": 20,
    },
    {
        "path": "investigation.reasoning_effort",
        "label": "Reasoning effort",
        "type": "string",
        "help": "How hard the model thinks before it answers. Higher costs more.",
        "section": "investigation",
        "section_summary": "What an investigation may spend before it reports.",
        "section_help": "What an investigation may spend before it reports.",
        "default": "medium",
        "allowed_values": ["low", "medium", "high"],
    },
    {
        "path": "approval.required_above",
        "label": "Required above",
        "type": "string",
        "description": "The side-effect level past which a person decides.",
        "help": "The side-effect level past which a person decides.",
        "section": "approval",
        "section_summary": "Which actions a person answers for.",
        "section_help": "Which actions a person answers for.",
        "default": "read",
        "allowed_values": ["read", "write_reversible", "write_irreversible"],
    },
    {
        "path": "retention.audit_days",
        "label": "Audit days",
        "type": "integer",
        "help": "How long an audit record is kept before it is removed.",
        "section": "retention",
        "section_summary": "How long each class of record is kept.",
        "section_help": "How long each class of record is kept.",
        "default": 365,
        "minimum": 1,
    },
    # Two budgets, so the agent screen can show a ceiling beside a value. Both
    # carry the schema's own bound: a team may lower either and may not raise
    # one, which is the property the screen is there to make visible.
    {
        "path": "agents.max_iterations",
        "label": "Max iterations",
        "type": "integer",
        "description": "How many times the loop may go round in one investigation.",
        "help": "How many times the loop may go round in one investigation.",
        "section": "agents",
        "section_summary": "Prompts, topology, and what one run may spend.",
        "section_help": "Prompts, topology, and what one run may spend.",
        "default": 20,
        "minimum": 1,
        "maximum": 20,
    },
    {
        "path": "agents.tool_budget",
        "label": "Tool budget",
        "type": "integer",
        "description": "How many capability calls one investigation may make.",
        "help": "How many capability calls one investigation may make.",
        "section": "agents",
        "section_summary": "Prompts, topology, and what one run may spend.",
        "section_help": "Prompts, topology, and what one run may spend.",
        "default": 40,
        "minimum": 1,
    },
    # One role bound explicitly, and seven left on the deployment default. That
    # asymmetry is the point: the agent screen has to render both, and a dataset
    # where every role was chosen would photograph only half of it.
    {
        "path": "models.investigator.provider",
        "label": "Provider",
        "type": "string",
        "description": "Which provider this role resolves to.",
        "help": "Which provider this role resolves to.",
        "section": "models.investigator",
        "section_summary": "What the investigator role runs on.",
        "section_help": "What the investigator role runs on.",
        "default": "anthropic",
    },
    {
        "path": "models.investigator.model",
        "label": "Model",
        "type": "string",
        "description": "Which model this role resolves to.",
        "help": "Which model this role resolves to.",
        "section": "models.investigator",
        "section_summary": "What the investigator role runs on.",
        "section_help": "What the investigator role runs on.",
        "default": "claude-sonnet-5",
    },
)


def _config_fields(node_id: str, *, inherited: bool) -> list[dict[str, Any]]:
    """Return the field catalogue as one node stands on it.

    The provenance mirrors the effective record beside it, so the editor and the
    values table above it cannot disagree about which level set what — which is
    the one thing a configuration screen must never do.
    """
    source = {
        "investigation.max_loops": ORG_NODE if inherited else node_id,
        "investigation.reasoning_effort": node_id,
        "approval.required_above": ORG_NODE if inherited else node_id,
        "retention.audit_days": ORG_NODE if inherited else node_id,
        "agents.max_iterations": ORG_NODE if inherited else node_id,
        "agents.tool_budget": ORG_NODE if inherited else node_id,
        "models.investigator.provider": ORG_NODE if inherited else node_id,
        "models.investigator.model": ORG_NODE if inherited else node_id,
    }
    values: Mapping[str, Any] = {
        "investigation.max_loops": 12,
        "investigation.reasoning_effort": "medium",
        "approval.required_above": "read",
        "retention.audit_days": 365,
        "agents.max_iterations": 12,
        "agents.tool_budget": 40,
        "models.investigator.provider": "anthropic",
        "models.investigator.model": "claude-sonnet-5",
    }
    return [
        {
            **dict(declared),
            "value": values[str(declared["path"])],
            "provenance": source[str(declared["path"])],
            "set_here": source[str(declared["path"])] == node_id,
            "locked_by": "",
            "approval_gated": str(declared["path"]) == "approval.required_above",
            "required": False,
        }
        for declared in _CONFIG_FIELDS
    ]


#: The three facts this deployment's own postmortems are about, as an operator
#: would have written them. Two at the organisation and one at the team, so the
#: screen shows what it exists to show: a section is the unit of inheritance,
#: and provenance says which level supplied each one.
_CONTEXT_SECTIONS: Final[tuple[tuple[str, str, bool], ...]] = (
    (
        "Where the signals really are",
        "A container shares its host's kernel, so memory and CPU for a guest are "
        "read from the host's own series for it, keyed by the guest's numeric id "
        "(vmid). A figure read from inside the container is the host's, and is "
        "plausible, consistent, and wrong.",
        False,
    ),
    (
        "What criticality means here",
        "Criticality comes from the declared inventory, never from the "
        "hypervisor. A stopped guest marked critical is an incident; a stopped "
        "guest marked best-effort is a Tuesday.",
        False,
    ),
    (
        "How the network is divided",
        # No CIDR in this text on purpose. The dataset is anonymised on the way
        # out, and an address rewritten inside a sentence comes back as a host
        # with a prefix on it — which is not a network, and is the one thing this
        # section is supposed to state correctly.
        "The vk8s zone runs MTU 1450 over a 1450 underlay, which fragments long "
        "TLS handshakes and shows up as timeouts that look like an unhealthy "
        "backend.",
        True,
    ),
)

#: What the sections above cost, by the deployment's own estimator, and the
#: ceiling it enforces. Written rather than computed: this dataset is a
#: plausible deployment rather than a second implementation of the budget.
_CONTEXT_TOKENS: Final = 168
_CONTEXT_BUDGET: Final = 1200


def _operating_context(node_id: str, *, inherited: bool) -> dict[str, Any]:
    """Return the operating context as one node stands on it.

    The team's own section is attributed to the team and the rest to the
    organisation, which is the whole thing the screen has to be able to show. A
    node with an ancestor has written none of its own, so nothing here claims
    the organisation's text was typed twice.
    """
    sections = [
        {
            "name": name,
            "body": body,
            "provenance": node_id if (local and inherited) else ORG_NODE,
        }
        for name, body, local in _CONTEXT_SECTIONS
    ]
    return {
        "node_id": node_id,
        "enabled": True,
        "sections": sections,
        "context": "\n\n".join(f"### {entry['name']}\n\n{entry['body']}" for entry in sections),
        "prompt": (
            "You are an SRE investigator. Establish the root cause from evidence.\n\n"
            "## Operating context for this deployment\n\n"
            + "\n\n".join(f"### {entry['name']}\n\n{entry['body']}" for entry in sections)
        ),
        "tokens_used": _CONTEXT_TOKENS,
        "token_budget": _CONTEXT_BUDGET,
        "roles": ["investigator", "subagent"],
        # Written, so the template is not offered. A screenshot showing both a
        # filled context and its own starting document would be a screenshot of
        # two states at once.
        "template": [],
    }


def config_records() -> tuple[CapturedRecord, ...]:
    """Return the organisation tree, and each node's effective configuration."""
    records: list[CapturedRecord] = [
        _record("config-tree", {}, {"nodes": list(CONFIG_NODES)}),
        # Not engaged, which is the ordinary state and the one the rest of the
        # dataset is coherent with: a stopped deployment with running
        # investigations in it would be a screenshot of two contradictions.
        _record("kill-switch", {}, {"engaged": False, "scopes": {}}),
    ]
    for entry in CONFIG_NODES:
        identifier = str(entry["node_id"])
        inherited = entry["parent_id"] is not None
        records.append(
            _record(
                "config-effective",
                {"node_id": identifier},
                {
                    "node_id": identifier,
                    "values": {
                        "investigation.max_loops": 12,
                        "investigation.reasoning_effort": "medium",
                        "approval.required_above": "read",
                        "retention.audit_days": 365,
                        # Nested, because that is what the route returns: the
                        # merged settings, in the shape the schema declares.
                        # The four flat keys above are older invented settings
                        # this dataset has always carried.
                        "agents": dict(AGENTS_SECTION),
                        "capabilities": dict(CAPABILITIES_SECTION),
                    },
                    "provenance": {
                        "investigation.max_loops": ORG_NODE if inherited else identifier,
                        "investigation.reasoning_effort": identifier,
                        "approval.required_above": ORG_NODE if inherited else identifier,
                        "retention.audit_days": ORG_NODE if inherited else identifier,
                        "agents.subagents": identifier,
                        "agents.prompts.investigator": identifier,
                        "capabilities.protocol_servers": identifier,
                    },
                },
            )
        )
        records.append(
            _record(
                "config-fields",
                {"node_id": identifier},
                {"fields": _config_fields(identifier, inherited=inherited)},
            )
        )
        records.append(
            _record(
                "config-operating-context",
                {"node_id": identifier},
                _operating_context(identifier, inherited=inherited),
            )
        )
        records.append(
            _record("autonomy-policy", {"node_id": identifier}, _policy_document(identifier))
        )
        records.append(
            _record(
                "autonomy-bounds",
                {"node_id": identifier},
                {
                    "node_id": identifier,
                    "stopped": False,
                    "stop_reason": "",
                    "freezes": [
                        {
                            "name": "nightly-backups",
                            "scope": {"kind": "resource", "resource_id": "store-cove"},
                            "start": "01:00",
                            "end": "04:00",
                            "timezone": "Europe/Lisbon",
                            "reason": "backups run",
                        }
                    ],
                    "budgets": [
                        {
                            "name": "hourly",
                            "counted_by": "resource",
                            "limit": 5,
                            "interval_seconds": 3600.0,
                        }
                    ],
                    "overrides": [],
                    "expired_overrides": [],
                },
            )
        )
        # Resolved by the real thing rather than transcribed. The shipped
        # detector set is in the image and its rationale is prose an operator
        # reads, so a hand-written copy here would be the one place the console
        # is shown reasoning the deployment does not hold — which is exactly
        # what this dataset exists not to be.
        records.append(
            _record(
                "config-guardian",
                {"node_id": identifier},
                resolve_guardian(
                    GuardianSettings(enabled=True, cluster_shape=ClusterShape.TWO_NODE.value),
                    shape=ClusterShape.TWO_NODE,
                ).to_record(),
            )
        )
        records.append(
            _record(
                "config-catalogue",
                {"node_id": identifier},
                {
                    "entries": [
                        {
                            "name": "estate.storage_pressure",
                            "kind": "tool",
                            "summary": "Read datastore fill and per-guest volume fill together.",
                            "side_effect_level": "read",
                            "available": True,
                            "reason": None,
                            "required_integrations": [],
                            "tags": ["estate", "storage"],
                        },
                        {
                            "name": "estate.enable_backup_job",
                            "kind": "tool",
                            "summary": "Enable a backup job that exists and is disabled.",
                            "side_effect_level": "write",
                            "available": True,
                            "reason": None,
                            "required_integrations": [],
                            "tags": ["estate", "backup"],
                        },
                        {
                            "name": "estate.failed_units",
                            "kind": "tool",
                            "summary": "What is failed on a node, which no API level reports.",
                            "side_effect_level": "read",
                            "available": True,
                            "reason": None,
                            "required_integrations": [],
                            "tags": ["estate", "health"],
                        },
                        {
                            "name": "knowledge.search",
                            "kind": "skill",
                            "summary": "Search the documents an investigation may read.",
                            "side_effect_level": "read",
                            "available": True,
                            "reason": None,
                            "required_integrations": [],
                            "tags": ["knowledge"],
                        },
                        {
                            "name": "metrics.range_query",
                            "kind": "tool",
                            "summary": "Query the metrics store over a window.",
                            "side_effect_level": "read",
                            "available": False,
                            "reason": "the metrics integration holds no credential here",
                            "required_integrations": ["metrics-store"],
                            "tags": ["metrics"],
                        },
                    ],
                    "blocked_by_integration": {"metrics-store": ["metrics.range_query"]},
                },
            )
        )
        records.append(
            _record(
                "config-integration-schemas",
                {"node_id": identifier},
                {
                    "schemas": [
                        {
                            "name": "metrics-store",
                            "display_name": "Metrics store",
                            "hosts": ["metrics.example.invalid"],
                            "credential_fields": [
                                {
                                    "name": "api_token",
                                    "label": "API token",
                                    "help": "A read-only token. It is stored by the proxy, "
                                    "never by the console.",
                                    "required": True,
                                    "secret": True,
                                }
                            ],
                            "settings_fields": [
                                {
                                    "name": "base_url",
                                    "label": "Base URL",
                                    "help": "Where the metrics store answers.",
                                    "required": True,
                                    "secret": False,
                                }
                            ],
                        },
                        {
                            "name": "chat",
                            "display_name": "Chat",
                            "hosts": ["chat.example.invalid"],
                            "credential_fields": [
                                {
                                    "name": "bot_token",
                                    "label": "Bot token",
                                    "help": "Used to post investigation summaries.",
                                    "required": True,
                                    "secret": True,
                                }
                            ],
                            "settings_fields": [],
                        },
                    ]
                },
            )
        )
    return tuple(records)


def _credential_field_record(declared: CredentialField) -> dict[str, Any]:
    """Return one declared credential field as the catalogue route serves it."""
    return {
        "name": declared.name,
        "label": declared.display_label,
        "secret": declared.is_secret,
        "required": declared.required,
        "help": declared.description,
        "min_scope": declared.min_scope,
        "guide_url": declared.guide_url,
    }


def _required_permission_record(permission: RequiredPermission) -> dict[str, Any]:
    """Return one declared permission exactly as the gateway serves it."""
    return {
        "name": permission.name,
        "grants": permission.grants,
        "where": permission.where,
        "capabilities": list(permission.capabilities),
    }


def _catalogue_integration_record(entry: CatalogueEntry) -> dict[str, Any]:
    """Return one real, installed integration exactly as the gateway serves it.

    Mirrors ``gateway/http/routes/integrations.py``'s own construction rather
    than reading ``entry.to_record()``, which is a different, internal shape
    (docs generation and the CLI's own reader) that has never carried ``hosts``
    or the structured field list this route serves.
    """
    return {
        "name": entry.name,
        "display_name": entry.display_name,
        "category": entry.category.value,
        "summary": entry.summary,
        "hosts": list(entry.descriptor.rule.hosts),
        "regions": list(entry.regions),
        "capabilities": list(entry.capabilities),
        "fields": [_credential_field_record(each) for each in entry.descriptor.schema.fields],
        "permissions": [_required_permission_record(each) for each in entry.permissions],
        "health": entry.health.value,
        "health_detail": entry.health_detail,
        "parity": entry.parity.status.value,
        "missing_artefacts": [artefact.value for artefact in entry.parity.missing],
    }


def integration_records() -> tuple[CapturedRecord, ...]:
    """Return every installed integration, one of them unhealthy.

    ``known_gaps`` is the other half of the same answer and is served with it:
    the question this endpoint is read to answer is "what can this deployment
    look at", and an operator who has to know to ask a second time about the
    absences discovers them by not finding them. Read from the declaration
    rather than restated here, because a second copy of the reasoning is a copy
    that stops matching the first.

    The catalogue below has two halves for the same reason the deployment does:
    a handful of hand-authored, fictional vendors carry this scenario's story —
    two connected and verified, one connected and failing, one only suggested —
    and every *real* installed integration is layered in beneath them, read
    from the same declaration the gateway route itself walks
    (``integrations._catalogue.discovery.catalogue``), so the height this
    screen renders at is the height eighty-plus real integrations actually
    produce rather than a guess at what that would look like. The three
    fictional entries are never replaced by a same-named real one: none of the
    installed vendors is called ``metrics-store``, ``chat`` or ``ticketing``.
    """
    return (
        _record(
            "integrations",
            {},
            {
                "known_gaps": [gap.to_record() for gap in gaps()],
                "integrations": [
                    {
                        "name": "metrics-store",
                        "display_name": "Metrics store",
                        "category": "observability",
                        "summary": "Range queries against the metrics store.",
                        "health": "unconfigured",
                        "health_detail": "no credential is stored for this node",
                        "hosts": ["metrics.example.invalid"],
                        "regions": [],
                        "capabilities": ["metrics.range_query"],
                        "fields": [
                            {
                                "name": "api_token",
                                "label": "API token",
                                "secret": True,
                                "required": True,
                                "help": "Generated from the metrics store's own settings page.",
                                "min_scope": "read-only",
                                # Relative, never a third-party origin: nothing this
                                # deployment serves may point off it, even in a
                                # fictional demo. No page answers this path yet — it
                                # exists to prove the link renders when a field
                                # declares one, not to be followed.
                                "guide_url": "/integrations/metrics-store/guide",
                            }
                        ],
                        "permissions": [
                            {
                                "name": "metrics:read",
                                "grants": "run range queries against stored series",
                                "where": "Metrics store → Settings → API tokens → Scopes",
                                "capabilities": ["metrics.range_query"],
                            }
                        ],
                        "parity": "full",
                        "missing_artefacts": [],
                        # The estate found this vendor running on something it
                        # already holds, so the address is derived rather than
                        # typed. It is present here because a surface that
                        # offers it has to be photographed offering it.
                        "suggested": {
                            "address": "http://10.20.0.14:9090",
                            "from_resource": "vm-201-metrics",
                            "because": "a guest labelled prometheus is reachable on the metrics port",
                        },
                    },
                    {
                        "name": "chat",
                        "display_name": "Chat",
                        "category": "collaboration",
                        "summary": "Posts investigation summaries and takes approvals.",
                        "health": "healthy",
                        "health_detail": "verified 3 hours ago",
                        "hosts": ["chat.example.invalid"],
                        "regions": [],
                        "capabilities": ["chat.post_message"],
                        "fields": [
                            {
                                "name": "bot_token",
                                "label": "Bot token",
                                "secret": True,
                                "required": True,
                                "help": "Created from the chat workspace's app management console.",
                                "min_scope": "chat:write",
                                "guide_url": "",
                            }
                        ],
                        "permissions": [
                            {
                                "name": "chat:write",
                                "grants": "post a message as the bot",
                                "where": "Chat workspace → App management → OAuth scopes",
                                "capabilities": ["chat.post_message"],
                            }
                        ],
                        "parity": "full",
                        "missing_artefacts": [],
                    },
                    {
                        "name": "ticketing",
                        "display_name": "Ticketing",
                        "category": "workflow",
                        "summary": "Opens and updates tickets from findings.",
                        "health": "degraded",
                        "health_detail": "the last verification timed out",
                        "hosts": ["tickets.example.invalid"],
                        "regions": [],
                        "capabilities": ["ticketing.open_ticket"],
                        "fields": [
                            {
                                "name": "api_token",
                                "label": "API token",
                                "secret": True,
                                "required": True,
                                "help": "Generated from the ticketing system's integration settings.",
                                "min_scope": "",
                                "guide_url": "",
                            }
                        ],
                        "permissions": [
                            {
                                "name": "issues:write",
                                "grants": "create and update tickets from findings",
                                "where": "Ticketing system → Integration settings → API scopes",
                                "capabilities": ["ticketing.open_ticket"],
                            }
                        ],
                        "parity": "partial",
                        "missing_artefacts": ["synthetic scenario"],
                    },
                    *[
                        _catalogue_integration_record(entry)
                        for entry in integration_catalogue(configured=frozenset())
                    ],
                ],
            },
        ),
    )


# --- Setting the deployment up -------------------------------------------------------

#: The three integrations the populated deployment declares, and how far along
#: each is. Held beside the catalogue above rather than derived from it: the
#: catalogue reports what a *live run* found, and the checklist reports what a
#: credential read found, and a scenario in which the two agreed by construction
#: could not exercise the screen that tells them apart.
_INTEGRATION_READINESS: Final[tuple[tuple[str, str], ...]] = (
    ("chat", SETUP_READINESS_VERIFIED),
    ("metrics-store", SETUP_READINESS_ABSENT),
    ("ticketing", SETUP_READINESS_CONFIGURED),
)


def provider_records(
    configured: Sequence[str] = (), verified: Sequence[str] = ()
) -> tuple[CapturedRecord, ...]:
    """Return the provider listing and one detail record per supported provider.

    Built from the shipped descriptors rather than written out here. Nine
    hand-copied provider blocks would be nine chances for the fixture to say
    something the platform stopped saying — and the one property the first-run
    screen has to hold, that all nine are offered with equal weight and the
    local one among them, is only worth asserting against a list that is the
    real list.
    """
    stored = frozenset(configured)
    answered = frozenset(verified)

    def listing(onboarding: ProviderOnboarding) -> dict[str, Any]:
        present = onboarding.provider_id in stored
        return {
            "provider_id": onboarding.provider_id,
            "display_name": onboarding.display_name,
            "local": onboarding.local,
            "configured": present,
            "verified": onboarding.provider_id in answered,
            "default_model": onboarding.default_model,
            "detail": (
                "a live request reached this endpoint"
                if onboarding.provider_id in answered
                else (
                    "no verification has been run against this deployment — a stored "
                    "credential is not the same fact as an endpoint that answers"
                )
                if present
                else "no credential is stored for this provider"
            ),
        }

    onboardings = all_onboardings()
    records = [_record("providers", {}, {"providers": [listing(one) for one in onboardings]})]
    for onboarding in onboardings:
        records.append(
            _record(
                "provider-detail",
                {"provider_id": onboarding.provider_id},
                {
                    **listing(onboarding),
                    "fields": [field.to_record() for field in onboarding.fields],
                    "guidance": onboarding.guidance,
                    "where_to_get_it": onboarding.where_to_get_it,
                    "models": list(onboarding.models),
                    "install_hint": onboarding.install_hint,
                },
            )
        )
    return tuple(records)


def checklist_record(
    *,
    provider: str = SETUP_READINESS_ABSENT,
    source: bool = False,
    runtime: bool = False,
    investigated: bool = False,
    integrations: Sequence[tuple[str, str]] = (),
) -> CapturedRecord:
    """Return what this deployment has left to set up.

    The five steps and their vocabulary are the platform's, not this module's —
    a fixture that invented a sixth step or a fifth state would be a console
    tested against a document nothing serves.

    ``runtime`` is whether this deployment says something can actually drive an
    investigation — the one dependency that leaves no trace on any other screen,
    composed by whoever operates the deployment rather than by a configuration
    field. It sits between ``source`` and ``investigated`` in both the step order
    and the blocking chain, the same as the platform's own checklist: the last
    step cannot go ready without it, whatever ``investigated`` says on its own.
    """
    provider_done = provider == SETUP_READINESS_VERIFIED
    steps = [
        {
            "name": SETUP_STEP_DURABLE_CREDENTIAL,
            "title": "Claim this deployment",
            "state": SETUP_STATE_DONE,
            "detail": "an administrator holds a credential of their own",
            "action": "issue further credentials from administration",
            "readiness": SETUP_READINESS_ABSENT,
        },
        {
            "name": SETUP_STEP_MODEL_PROVIDER,
            "title": "Give it something to think with",
            "state": SETUP_STATE_DONE if provider_done else SETUP_STATE_READY,
            "detail": (
                "a live request reached the endpoint and called a tool"
                if provider_done
                else "a credential is stored and nothing has checked it"
                if provider == SETUP_READINESS_CONFIGURED
                else "no provider holds a credential here"
            ),
            "action": "choose a provider and store its credential",
            "readiness": provider,
        },
        {
            "name": SETUP_STEP_INFRASTRUCTURE_SOURCE,
            "title": "Give it something to look at",
            "state": (
                SETUP_STATE_DONE
                if source
                else SETUP_STATE_READY
                if provider_done
                else SETUP_STATE_BLOCKED
            ),
            "detail": (
                "the last sweep found resources" if source else "no sweep has found anything yet"
            ),
            "action": "connect an infrastructure source",
            "readiness": SETUP_READINESS_ABSENT,
        },
        {
            "name": SETUP_STEP_INVESTIGATION_RUNTIME,
            "title": "Give it something to investigate with",
            "state": (
                SETUP_STATE_DONE
                if runtime
                else SETUP_STATE_READY
                if source
                else SETUP_STATE_BLOCKED
            ),
            "detail": (
                "this deployment holds a runtime, so an investigation has something to run in"
                if runtime
                else (
                    "nothing here can drive an investigation yet — a model provider and an "
                    "integration are both configured, and the part that puts them together "
                    "has not been supplied to this process"
                )
            ),
            "action": (
                "nothing further"
                if runtime
                else (
                    "whoever operates this deployment supplies the investigation runtime; "
                    "until they do, starting an investigation will fail immediately"
                )
            ),
            "readiness": SETUP_READINESS_ABSENT,
        },
        {
            "name": SETUP_STEP_FIRST_INVESTIGATION,
            "title": "Watch it look",
            "state": (
                SETUP_STATE_DONE
                if investigated
                else SETUP_STATE_READY
                if runtime
                else SETUP_STATE_BLOCKED
            ),
            "detail": (
                "an investigation has finished here"
                if investigated
                else "no investigation has finished here"
            ),
            "action": "start an investigation and watch it run",
            "readiness": SETUP_READINESS_ABSENT,
        },
    ]
    outstanding = next((step["name"] for step in steps if step["state"] == SETUP_STATE_READY), None)
    return _record(
        "setup-checklist",
        {},
        {
            "complete": all(step["state"] == SETUP_STATE_DONE for step in steps),
            "steps": steps,
            "next": outstanding,
            "provider": provider,
            "integrations": [
                {"name": name, "readiness": readiness} for name, readiness in integrations
            ],
        },
    )


#: The address the ingress panel's URLs are built from in the dataset. The real
#: route derives it from the request, which a fixture has none of; an obviously
#: fictional host is the honest stand-in, and it is the same shape an operator
#: sees.
INGRESS_BASE_URL: Final = "https://ninjasre.example.invalid"


def ingress_records() -> tuple[CapturedRecord, ...]:
    """Return what an operator pastes into each alert router, per source.

    Derived from the shipped profiles rather than written out, for the reason
    the signal block is: a fixture that carried its own copy of the seven
    receivers would go on describing a receiver after it was removed.
    """
    return (
        _record(
            "ingress-sources",
            {},
            {
                "sources": [
                    {
                        "source": name,
                        "path": f"/webhooks/{name}",
                        "url": f"{INGRESS_BASE_URL}/webhooks/{name}",
                        "expects": profile_of.expects,
                        "verification": profile_of.verification,
                    }
                    for name, profile_of in sorted(PROFILES.items())
                ],
                "delivery_permission": Permission.WEBHOOK_DELIVER.value,
            },
        ),
    )


#: The instants the transit rows are dated from. Fixed offsets off the capture,
#: so "an hour ago" is the same sentence on every run of the suite rather than
#: whatever the clock said.
_TRANSIT_ACCEPTED_AT: Final = _CAPTURED - timedelta(minutes=12)
_TRANSIT_REJECTED_AT: Final = _CAPTURED - timedelta(hours=3)
_TRANSIT_FAILED_AT: Final = _CAPTURED - timedelta(minutes=40)

#: The receiver this deployment actually uses. The other six are configured
#: routes that have never delivered — which is deliberate: the state the screen
#: exists to make loud has to be in the dataset the design was drawn from, or
#: the design was drawn against a case that never appears.
_LIVE_SOURCE: Final = "alertmanager"

#: The one that is refusing rather than silent. A source delivering nothing and
#: a source delivering rubbish are different problems with different fixes, and
#: a dataset carrying only the first would let a screen conflate them.
_REFUSING_SOURCE: Final = "grafana"


def transit_records() -> tuple[CapturedRecord, ...]:
    """Return what the Data screen shows: arrivals, rules, destinations, the ledger.

    Derived from the shipped profiles for the same reason ``ingress_records``
    is: a fixture carrying its own copy of the seven receivers goes on
    describing one after it has been removed.
    """
    accepted = {
        "delivery_id": "alertmanager:accepted",
        "direction": "ingress",
        "source": _LIVE_SOURCE,
        "occurred_at": _TRANSIT_ACCEPTED_AT.isoformat(),
        "outcome": "accepted",
        "reason": "",
        "matched_rule": "critical-to-platform",
        "team_node_id": PLATFORM_TEAM_NODE,
        "resource_id": "proxmox:container/hal9000/110",
        "run_id": RUNS[0]["run_id"],
        "incident_id": "",
        "event_type": "",
        "attempt": 1,
        "detail": {},
    }
    rejected = {
        "delivery_id": "grafana:rejected",
        "direction": "ingress",
        "source": _REFUSING_SOURCE,
        "occurred_at": _TRANSIT_REJECTED_AT.isoformat(),
        "outcome": "rejected",
        "reason": "this grafana webhook did not verify against any configured route",
        "matched_rule": "",
        "team_node_id": "",
        "resource_id": "",
        "run_id": "",
        "incident_id": "",
        "event_type": "",
        "attempt": 1,
        "detail": {},
    }
    undelivered = {
        "delivery_id": "chat-incidents:concluded",
        "direction": "outbound",
        "source": "chat-incidents",
        "occurred_at": _TRANSIT_FAILED_AT.isoformat(),
        "outcome": "failed",
        "reason": "the channel refused the message: channel_not_found",
        "matched_rule": "",
        "team_node_id": PLATFORM_TEAM_NODE,
        "resource_id": "",
        "run_id": "",
        "incident_id": "",
        "event_type": "investigation_concluded",
        "attempt": 1,
        "detail": {"channel": "slack", "detail_level": "summary_with_link"},
    }

    def source_row(name: str, profile_of: Any) -> dict[str, Any]:
        delivered = name == _LIVE_SOURCE
        refused = name == _REFUSING_SOURCE
        row: dict[str, Any] = {
            "source": name,
            "path": f"/webhooks/{name}",
            "url": f"{INGRESS_BASE_URL}/webhooks/{name}",
            "expects": profile_of.expects,
            "verification": profile_of.verification,
            "never_delivered": not (delivered or refused),
            "last_delivery_at": "",
            "last_outcome": "",
            "counts": {},
            "recent_rejections": [],
            "sample": None,
        }
        if delivered:
            row["last_delivery_at"] = accepted["occurred_at"]
            row["last_outcome"] = "accepted"
            row["counts"] = {"accepted": 14, "duplicate": 2}
            row["sample"] = {
                "captured_at": accepted["occurred_at"],
                "body": (
                    '{"status": "firing", "groupKey": "{}:{alertname=\\"ContainerMemoryHigh\\"}", '
                    '"commonLabels": {"alertname": "ContainerMemoryHigh", '
                    '"instance": "<ipv4-1>", "severity": "critical"}}'
                ),
                "masking_policy": "standard",
                "truncated": False,
            }
        if refused:
            row["last_delivery_at"] = rejected["occurred_at"]
            row["last_outcome"] = "rejected"
            row["counts"] = {"rejected": 6}
            row["recent_rejections"] = [rejected]
        return row

    return (
        _record(
            "transit-ingress",
            {},
            {
                "sources": [
                    source_row(name, profile_of) for name, profile_of in sorted(PROFILES.items())
                ],
                "window_hours": 24,
            },
        ),
        _record(
            "transit-rules",
            {},
            {
                "rules": [
                    {
                        "rule_id": "critical-to-platform",
                        "sources": [_LIVE_SOURCE],
                        "zones": [],
                        "criticalities": ["critical"],
                        "resources": [],
                        "team": PLATFORM_TEAM_NODE,
                        "action": "investigate",
                        "reason": "",
                        "is_catch_all": False,
                    },
                    {
                        "rule_id": "everything-else",
                        "sources": [],
                        "zones": [],
                        "criticalities": [],
                        "resources": [],
                        "team": "",
                        "action": "record_only",
                        "reason": "",
                        "is_catch_all": True,
                    },
                ]
            },
        ),
        _record(
            "transit-destinations",
            {},
            {
                "destinations": [
                    {
                        "destination_id": "chat-incidents",
                        "channel": "slack",
                        "events": ["investigation_concluded", "approval_pending"],
                        "detail": "summary_with_link",
                        "enabled": True,
                        "masking_policy": "standard",
                        "unconfigurable_reason": "",
                    }
                ],
                "events": [
                    "investigation_concluded",
                    "remediation_proposed",
                    "approval_pending",
                    "source_degraded",
                ],
                "unconfigurable_reason": "",
            },
        ),
        _record("transit-deliveries", {}, [accepted, rejected, undelivered]),
    )


def empty_transit_records() -> tuple[CapturedRecord, ...]:
    """Return a deployment where nothing has ever arrived, and every receiver says so.

    The state the ingress column exists for, in the scenario an operator's first
    day actually looks like: seven configured routes, seven silences. It is a
    fixture of its own rather than the populated one with the rows removed,
    because "never delivered" is the *only* thing on this screen then, and a
    design that was never drawn against it is a design that hides it.
    """
    return (
        _record(
            "transit-ingress",
            {},
            {
                "sources": [
                    {
                        "source": name,
                        "path": f"/webhooks/{name}",
                        "url": f"{INGRESS_BASE_URL}/webhooks/{name}",
                        "expects": profile_of.expects,
                        "verification": profile_of.verification,
                        "never_delivered": True,
                        "last_delivery_at": "",
                        "last_outcome": "",
                        "counts": {},
                        "recent_rejections": [],
                        "sample": None,
                    }
                    for name, profile_of in sorted(PROFILES.items())
                ],
                "window_hours": 24,
            },
        ),
        _record(
            "transit-rules",
            {},
            {
                "rules": [
                    {
                        "rule_id": "catch-all",
                        "sources": [],
                        "zones": [],
                        "criticalities": [],
                        "resources": [],
                        "team": "",
                        "action": "investigate",
                        "reason": "",
                        "is_catch_all": True,
                    }
                ]
            },
        ),
        _record(
            "transit-destinations",
            {},
            {
                "destinations": [],
                "events": [
                    "investigation_concluded",
                    "remediation_proposed",
                    "approval_pending",
                    "source_degraded",
                ],
                "unconfigurable_reason": (
                    "No configured integration can deliver a message. Connect a chat or "
                    "notification integration in the catalogue, then declare a destination here."
                ),
            },
        ),
        _record("transit-deliveries", {}, []),
    )


def setup_records() -> tuple[CapturedRecord, ...]:
    """Return what the full deployment says about its own setup: finished."""
    return (
        *provider_records(configured=("anthropic",), verified=("anthropic",)),
        checklist_record(
            provider=SETUP_READINESS_VERIFIED,
            source=True,
            # An investigation cannot have finished on this deployment without
            # something that could run it — a checklist reporting both
            # `investigated=True` and no runtime would be internally
            # inconsistent, the same contradiction F6 fixed on the platform's
            # own checklist.
            runtime=True,
            investigated=True,
            integrations=_INTEGRATION_READINESS,
        ),
    )


# --- Identity and audit ------------------------------------------------------------

USERS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "user_id": OPERATOR,
        "display_name": "Avery Lockhart",
        "email": "avery.lockhart@example.invalid",
        # The two values ``PrincipalKind`` actually declares
        # (``platform/persistence/ports/identity_repository.py``) — not
        # ``"person"``/``"machine"``, which the real backend never emits.
        "kind": "user",
        "is_active": True,
    },
    {
        "user_id": REVIEWER,
        "display_name": "Morgan Thorne",
        "email": "morgan.thorne@example.invalid",
        "kind": "user",
        "is_active": True,
    },
    {
        "user_id": VIEWER,
        "display_name": "Reese Underhill",
        "email": "reese.underhill@example.invalid",
        "kind": "user",
        "is_active": True,
    },
    {
        "user_id": AUTOMATION,
        "display_name": "Scheduler",
        "email": "scheduler@example.invalid",
        "kind": "service_account",
        "is_active": True,
    },
)

GRANTS: Final[tuple[Mapping[str, Any], ...]] = (
    {"grant_id": "grant-0001", "principal_id": OPERATOR, "role": "owner", "node_id": ORG_NODE},
    {
        "grant_id": "grant-0002",
        "principal_id": REVIEWER,
        "role": "approver",
        "node_id": PLATFORM_TEAM_NODE,
    },
    {"grant_id": "grant-0003", "principal_id": VIEWER, "role": "viewer", "node_id": ORG_NODE},
    {
        "grant_id": "grant-0004",
        "principal_id": AUTOMATION,
        "role": "operator",
        "node_id": STORAGE_TEAM_NODE,
    },
)

# ``actor_kind`` reads from the values ``ActorKind`` actually declares
# (``platform/persistence/ports/audit_repository.py``) — ``"user"`` for a
# person acting through their own session, ``"agent"`` for the autonomous
# pipeline (the same value ``platform/credentials/proxy/audit.py`` writes for
# every ``credential.resolve`` line) — not ``"person"``/``"machine"``, which
# the real backend never emits. ``outcome`` reads from ``AuditOutcome`` the
# same way — ``"allowed"``, not ``"succeeded"``, which is a run's own status,
# not a value this enum has ever declared.
AUDIT_EVENTS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "event_id": "aud-0008",
        "occurred_at": at(minutes=6),
        "actor_id": AUTOMATION,
        "actor_kind": "agent",
        "action": "investigation.start",
        "resource_kind": "run",
        "resource_id": "run-0003",
        "outcome": "allowed",
        "detail": {"trigger": "alert"},
    },
    {
        "event_id": "aud-0007",
        "occurred_at": at(minutes=21),
        "actor_id": AUTOMATION,
        "actor_kind": "agent",
        "action": "approval.request",
        "resource_kind": "approval",
        "resource_id": "apr-0001",
        "outcome": "allowed",
        "detail": {"side_effect_level": "write"},
    },
    {
        "event_id": "aud-0006",
        "occurred_at": at(hours=5),
        "actor_id": OPERATOR,
        "actor_kind": "user",
        "action": "config.write",
        "resource_kind": "config-node",
        "resource_id": "env-production",
        "outcome": "allowed",
        "detail": {"key": "investigation.reasoning_effort"},
    },
    {
        "event_id": "aud-0005",
        "occurred_at": at(days=1, hours=2),
        "actor_id": REVIEWER,
        "actor_kind": "user",
        "action": "approval.reject",
        "resource_kind": "approval",
        "resource_id": "apr-0002",
        "outcome": "allowed",
        "detail": {"reason": "the datastore has room; grow the volume in the window"},
    },
    {
        "event_id": "aud-0004",
        "occurred_at": at(days=2, minutes=27),
        "actor_id": AUTOMATION,
        "actor_kind": "agent",
        "action": "investigation.finish",
        "resource_kind": "run",
        "resource_id": "run-0001",
        "outcome": "allowed",
        "detail": {"status": "succeeded"},
    },
    {
        "event_id": "aud-0003",
        "occurred_at": at(days=3, hours=5, minutes=51),
        "actor_id": AUTOMATION,
        "actor_kind": "agent",
        "action": "investigation.finish",
        "resource_kind": "run",
        "resource_id": "run-0004",
        "outcome": "failed",
        "detail": {"status": "failed"},
    },
    {
        "event_id": "aud-0002",
        "occurred_at": at(days=4),
        "actor_id": OPERATOR,
        "actor_kind": "user",
        "action": "token.create",
        "resource_kind": "token",
        "resource_id": "tok-0002",
        "outcome": "allowed",
        "detail": {"name": "scheduler"},
    },
    {
        "event_id": "aud-0001",
        "occurred_at": at(days=9),
        "actor_id": OPERATOR,
        "actor_kind": "user",
        "action": "identity.grant",
        "resource_kind": "grant",
        "resource_id": "grant-0003",
        "outcome": "allowed",
        "detail": {"role": "viewer"},
    },
)


def role_records() -> tuple[CapturedRecord, ...]:
    """Return the role catalogue, read off the platform rather than transcribed."""
    from platform.identity.permissions import ROLE_ORDER, permissions_for

    return (
        _record(
            "roles",
            {},
            {
                "roles": [
                    {
                        "name": role.value,
                        "permissions": sorted(
                            permission.value for permission in permissions_for(role)
                        ),
                    }
                    for role in ROLE_ORDER
                ]
            },
        ),
    )


def identity_records(*, role: str = "owner") -> tuple[CapturedRecord, ...]:
    """Return the principal, the directory, the grants, the tokens and the audit trail.

    ``role`` decides who is looking, which is the whole of the restricted
    scenario: the same deployment, seen by somebody who may not act on it.
    """
    viewer = role == "viewer"
    principal = VIEWER if viewer else OPERATOR
    display = next(user for user in USERS if user["user_id"] == principal)
    return (
        # What the sign-in hands back. The mock decides *whether* to answer this
        # by checking the credential it was sent; this record is only the shape
        # of the answer when it does, which is why one record covers both
        # scenarios and every role.
        _record(
            "sign-in",
            {},
            {
                "token": SIGN_IN_TOKEN,
                "expires_at": at(hours=-12),
                "principal_id": principal,
            },
        ),
        _record(
            "principal",
            {},
            {
                "principal_id": principal,
                "display_name": display["display_name"],
                "email": display["email"],
                # Read off the same record rather than repeated as a literal,
                # so this can never drift from `USERS` the way it once did.
                "kind": display["kind"],
                "roles": [role],
                "permissions": list(VIEWER_PERMISSIONS if viewer else OPERATOR_PERMISSIONS),
                "team_node_id": ORG_NODE,
                "impersonating": False,
                "impersonated_by": None,
            },
        ),
        _record("principals", {}, {"users": list(USERS)}),
        # Configured, tested, and not yet the way in — the state an operator is
        # in for exactly as long as it takes them to read the consequence, and
        # the only one where every control on the panel is worth photographing.
        _record(
            "sso",
            {},
            {
                "provider": "keycloak",
                "issuer": "https://id.northwind.invalid/realms/main",
                "client_id": "ninjasre",
                "authorisation_endpoint": "https://id.northwind.invalid/auth",
                "token_endpoint": "https://id.northwind.invalid/token",
                "jwks_uri": "https://id.northwind.invalid/certs",
                "redirect_uri": "https://ninjasre.northwind.invalid/auth/callback",
                "scopes": ["openid", "email", "profile"],
                "claims": {
                    "subject": "sub",
                    "email": "email",
                    "display_name": "name",
                    "groups": "groups",
                },
                "group_to_node": {"sre": PLATFORM_TEAM_NODE},
                "default_node_id": ORG_NODE,
                "is_active": False,
                "verified": True,
                "problems": [],
            },
        ),
        _record("grants", {}, {"grants": list(GRANTS)}),
        _record(
            "tokens",
            {},
            {
                "tokens": [
                    {
                        "token_id": "tok-0001",
                        "name": "console",
                        "user_id": OPERATOR,
                        "team_node_id": ORG_NODE,
                        "scopes": ["investigation.read", "investigation.run"],
                        "created_at": at(days=40),
                        "expires_at": at(days=-325),
                        "last_used_at": at(minutes=2),
                        "revoked": False,
                        "description": "The browser session's token.",
                    },
                    {
                        "token_id": "tok-0002",
                        "name": "scheduler",
                        "user_id": AUTOMATION,
                        "team_node_id": STORAGE_TEAM_NODE,
                        "scopes": ["investigation.run"],
                        "created_at": at(days=4),
                        "expires_at": None,
                        "last_used_at": at(minutes=6),
                        "revoked": False,
                        "description": None,
                    },
                ]
            },
        ),
        _record(
            "audit-events",
            {},
            {"events": list(AUDIT_EVENTS), "total": len(AUDIT_EVENTS)},
        ),
    )


def platform_records() -> tuple[CapturedRecord, ...]:
    """Return the capability catalogue and what the deployment says about itself."""
    return (
        _record(
            "capabilities",
            {},
            {
                "tools": [
                    {
                        "name": "estate.storage_pressure",
                        "display_name": "Storage pressure",
                        "description": "Datastore fill and per-guest volume fill, together.",
                        "domain": "estate",
                        "side_effect_level": "read",
                    },
                    {
                        "name": "estate.failed_units",
                        "display_name": "Failed units",
                        "description": "What is failed on a node, which no API level reports.",
                        "domain": "estate",
                        "side_effect_level": "read",
                    },
                    {
                        "name": "estate.enable_backup_job",
                        "display_name": "Enable backup job",
                        "description": "Enable a job that exists and is switched off.",
                        "domain": "estate",
                        "side_effect_level": "write",
                    },
                    {
                        "name": "knowledge.search",
                        "display_name": "Search knowledge",
                        "description": "Find the runbook or postmortem that covers this.",
                        "domain": "knowledge",
                        "side_effect_level": "read",
                    },
                ],
                "skills": [
                    {
                        "name": "storage-pressure",
                        "description": "How to tell a full datastore from a full volume.",
                    },
                    {
                        "name": "quorum-margin",
                        "description": "What losing a node costs when there is no margin.",
                    },
                ],
            },
        ),
        _record(
            "health",
            {},
            {
                "ready": True,
                "connected": True,
                "store_state": "ready",
                "migrations_current": True,
                "providers_configured": ["operator-configured"],
                "reasons": [],
                "recent_shedding": [],
            },
        ),
    )


def agent_records() -> tuple[CapturedRecord, ...]:
    """Return what this build says an investigation is, and what it would decide.

    Resolved by the real thing rather than transcribed, for the reason the
    guardian record gives: the stage declaration and the policy engine are both
    in the image, so a hand-written copy here would be the one place the console
    is shown a pipeline or a posture the deployment does not hold.
    """
    from core.pipeline.declaration import stage_declarations
    from platform.autonomy.decision import AutonomyGate
    from platform.autonomy.outlook import outlook_of, representative_actions
    from platform.autonomy.policy import PolicySet

    records = [
        _record(
            "agent-pipeline",
            {},
            {
                "stages": [
                    {
                        "name": entry.name.value,
                        "order": entry.order,
                        "summary": entry.summary,
                        "consults": list(entry.consults),
                        "writes": list(entry.writes),
                        "model_role": entry.model_role,
                        "dispatches_subagents": entry.dispatches_subagents,
                    }
                    for entry in stage_declarations()
                ],
                "model_roles": list(MODEL_ROLES),
            },
        ),
        _record("schedules", {}, [dict(entry) for entry in SCHEDULES]),
    ]

    for entry in CONFIG_NODES:
        identifier = str(entry["node_id"])
        policies = PolicySet.of_document(_policy_document(identifier))
        gate = AutonomyGate(policies=policies)
        readings = outlook_of(
            tuple(
                asyncio.run(gate.decide(action))
                for action in representative_actions(team_node_id=identifier)
            )
        )
        records.append(
            _record(
                "autonomy-outlook",
                {"node_id": identifier},
                {
                    "node_id": identifier,
                    "dry_run": any(reading.dry_run for reading in readings),
                    "classes": [
                        {
                            "risk_class": reading.risk_class,
                            "capability": reading.capability,
                            "resource_kind": reading.resource_kind,
                            "summary": reading.summary,
                            "sentence": reading.describe(),
                            "decision": reading.outcome,
                            "level": reading.level,
                            "refused_by": reading.refused_by,
                            "dry_run": reading.dry_run,
                            "reason": reading.decision.reason,
                        }
                        for reading in readings
                    ],
                },
            )
        )
        records.append(
            _record(
                "autonomy-preview",
                {"node_id": identifier},
                {
                    "summary": (
                        f"{len(REPLAYED_ACTIONS)} recorded actions considered; "
                        f"none would be decided differently."
                    ),
                    "considered": len(REPLAYED_ACTIONS),
                    "changed": 0,
                    "newly_autonomous": 0,
                    "actions": [dict(action) for action in REPLAYED_ACTIONS],
                },
                method="POST",
            )
        )
    return tuple(records)


def served_records(*, role: str = "owner") -> tuple[CapturedRecord, ...]:
    """Return every record the gateway half of the dataset holds."""
    return (
        *agent_records(),
        *runs_records(),
        *interaction_records(),
        *proposal_records(),
        *memory_records(),
        *topology_records(),
        *config_records(),
        *integration_records(),
        *identity_records(role=role),
        *role_records(),
        *platform_records(),
        *ingress_records(),
        *transit_records(),
        *setup_records(),
    )


__all__ = [
    "APPROVALS",
    "SCHEDULES",
    "AUDIT_EVENTS",
    "AUTOMATION",
    "CONFIG_NODES",
    "DOCUMENTS",
    "EPISODES",
    "GRANTS",
    "INTERACTIONS",
    "OPERATOR",
    "OPERATOR_PERMISSIONS",
    "ORG_NODE",
    "PLATFORM_TEAM_NODE",
    "REVIEWER",
    "RUNS",
    "STORAGE_TEAM_NODE",
    "USERS",
    "VIEWER",
    "VIEWER_PERMISSIONS",
    "agent_records",
    "at",
    "checklist_record",
    "config_records",
    "identity_records",
    "role_records",
    "integration_records",
    "interaction_records",
    "proposal_records",
    "memory_records",
    "platform_records",
    "provider_records",
    "runs_records",
    "served_records",
    "setup_records",
    "topology_records",
]
