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
    LOCAL_ADMIN_SETUP_COMMAND,
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
from config.constants.security import (
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from core.llm.onboarding import ProviderOnboarding, all_onboardings
from core.llm.registry import default_registry
from gateway.http.routes.integrations import _direction as route_direction
from gateway.webhooks.router import PROFILES
from gateway.webhooks.sources import alertmanager
from integrations._catalogue.discovery import catalogue as integration_catalogue
from integrations._catalogue.entry import CatalogueEntry
from integrations._catalogue.gaps import gaps
from integrations._catalogue.health import HealthLedger
from integrations._verification.permissions import RequiredPermission
from platform.config_service.schema.policies import GuardianSettings
from platform.credentials.schemas import CredentialField
from platform.guardian.resolution import resolve as resolve_guardian
from platform.guardian.topology import ClusterShape
from platform.identity.permissions import Permission, Role, permissions_for
from platform.persistence.ports.run_trace_store import ToolCallRecord
from platform.runs.headline import synthesize_headline
from platform.runs.replay import REPLAY_RESULT_BOUNDS, touched_resources_of
from platform.runs.truncation import truncate
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
#: Somebody who used to hold a grant here and does not any more. Every other
#: entry in ``USERS`` below is active — a directory where nobody ever left is
#: a directory that never exercises the suspended state the console renders.
FORMER: Final = "user-departed"

#: What a sign-in against this dataset returns. Obviously not a credential: the
#: mock resolves no token, and a fixture holding something that looked like a
#: real one is a fixture somebody eventually tries in a deployment.
SIGN_IN_TOKEN: Final = "fixture-session-token"

#: The permissions the signed-in principal holds here, read off the platform's
#: own catalogue rather than hand-curated. This used to be a literal, chosen
#: list — plausible on its own, and silently narrower than what ``/identity/roles``
#: already publishes for the same role (``role_records()`` below, which *does*
#: read ``permissions_for``). The gap was invisible until something asked the
#: console to exercise a permission this list had never included: nothing here
#: ever granted ``identity.write``, ``sso.manage``, ``estate.manage`` or the
#: three destructive scopes, so no scenario this fixture ever served could
#: prove the console's own handling of any of them. Computed now, so the
#: ceiling this dataset serves is the one the role actually carries, not a
#: guess at what an operator "should" plausibly hold.
OPERATOR_PERMISSIONS: Final[tuple[str, ...]] = tuple(
    sorted(permission.value for permission in permissions_for(Role.OWNER))
)

VIEWER_PERMISSIONS: Final[tuple[str, ...]] = tuple(
    sorted(permission.value for permission in permissions_for(Role.VIEWER))
)


def at(*, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> str:
    """Return an instant that far before the survey, as the API spells one.

    ``seconds`` exists for the handful of events that land inside the same
    minute as one another — a stage boundary and the turn it precedes, say —
    where ``minutes`` alone cannot tell them apart. A negative value of any
    argument is an instant *after* the survey, which is what a stage the
    pipeline reaches only once gathering is already under way needs.
    """
    return (
        _CAPTURED - timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    ).isoformat()


#: How long before the survey each superseded first-run credential was issued.
#:
#: Fifteen of them, because a deployment brought up repeatedly accumulates one
#: per bring-up: each lived an hour and none was ever revoked, so the list grows
#: and the screen that groups them by purpose is what has to make fifteen rows
#: readable. Offsets rather than instants, like every other time in this module,
#: so they move with the survey instead of drifting away from it — the previous
#: hand-written set had already drifted far enough that its last entry was
#: issued *after* the moment the dataset was captured. Irregularly spaced on
#: purpose: a bring-up happens when somebody runs one, not on a schedule.
_BOOTSTRAP_ISSUED: Final = (
    (15, 6, 31),
    (14, 23, 56),
    (13, 19, 21),
    (12, 15, 36),
    (11, 2, 11),
    (10, 22, 26),
    (9, 16, 51),
    (8, 7, 1),
    (7, 0, 36),
    (6, 20, 6),
    (5, 13, 16),
    (4, 3, 26),
    (3, 20, 51),
    (2, 16, 36),
    (1, 9, 46),
)

#: How long a first-run credential lives before it expires on its own.
_BOOTSTRAP_LIFETIME: Final = timedelta(hours=1)


def _bootstrap_tokens() -> list[dict[str, Any]]:
    """Return the superseded first-run credentials, one per bring-up.

    Generated rather than written out fifteen times: the rows differ only in
    their identifier and their instant, and a hand-kept list of near-identical
    records is a list that drifts from the screen it exists to exercise.
    """
    return [
        {
            "token_id": f"tok-{1001 + index}",
            "name": "bootstrap",
            "user_id": "bootstrap-administrator",
            "team_node_id": None,
            "scopes": ["investigation.read", "token.manage"],
            "created_at": at(days=days, hours=hours, minutes=minutes),
            "expires_at": (
                datetime.fromisoformat(at(days=days, hours=hours, minutes=minutes))
                + _BOOTSTRAP_LIFETIME
            ).isoformat(),
            "last_used_at": None,
            "revoked": False,
            "description": "First-run credential. Establishes a durable one, then expires.",
        }
        for index, (days, hours, minutes) in enumerate(_BOOTSTRAP_ISSUED)
    ]


def _record(
    slug: str,
    arguments: Mapping[str, str],
    body: Any,
    *,
    method: str = "GET",
    status: int = 200,
) -> CapturedRecord:
    return CapturedRecord(
        slug=slug,
        arguments=dict(arguments),
        status=status,
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

#: One active temporary override, granted on the organisation's own node — the
#: node `resolveNode` (console `url-state.ts`) lands on when nothing in the
#: address names one, since the owner's own `team_node_id` is `ORG_NODE`. Every
#: other node in `CONFIG_NODES` keeps `overrides: []`: an override is granted
#: to somebody working a specific node, and the same grant repeated
#: identically across five nodes would read as a fixture posing rather than a
#: deployment mid-operation. `expires_at` is a plain future instant rather
#: than `at()` (which only ever subtracts from the survey moment): a grant
#: that is still active has to read as being ahead of "now", not as a fixed
#: offset from a capture that is already in the past.
_ACTIVE_OVERRIDE: Final[Mapping[str, Any]] = {
    "name": "storage-capacity-response",
    "level": "act_and_report",
    "reason": (
        "store-cove is near its capacity threshold; approved to let automation "
        "expand it unattended until the maintenance window closes."
    ),
    "expires_at": "2026-09-01T12:00:00+00:00",
    "granted_by": "Morgan Thorne",
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
        "status": "completed",
        "trigger": "alert",
        "started_at": at(days=2, minutes=41),
        "finished_at": at(days=2, minutes=27),
        "summary": "A guest reached the ceiling of its own volume while the datastore "
        "under it still read comfortable.",
    },
    {
        "run_id": "run-0002",
        "status": "completed",
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
        # Declared rather than synthesised. A run triggered by hand has whatever
        # objective the operator typed, and this dataset has no such field — so
        # the synthesiser would fall back to the trigger word and put "manual
        # investigation" where a sentence belongs, which is the exact shape this
        # wave spent itself removing from every screen. What a real run of this
        # kind carries is a sentence a model wrote, so that is what is declared.
        "headline": "The metrics agent on the primary never answered, so nothing was read",
        "started_at": at(days=3, hours=6),
        "finished_at": at(days=3, hours=5, minutes=51),
        "summary": "The investigation could not reach the metrics agent; it is one of the "
        "failed units on the primary.",
    },
    {
        "run_id": "run-0005",
        # Paused on a human decision, not finished — the store's own word for
        # exactly that (`core/agent/session.py::SessionStatus.SUSPENDED`'s own
        # docstring: "the state a run sits in while a human..."). `finished_at`
        # stays `None` for the same reason: nothing about this run has ended.
        "status": "suspended",
        "trigger": "alert",
        "started_at": at(minutes=22),
        "finished_at": None,
        "summary": "A remediation is proposed and is waiting for a decision.",
    },
    {
        "run_id": "run-0006",
        "status": "cancelled",
        "trigger": "manual",
        "headline": "An operator found the cause by hand and stopped the investigation",
        "started_at": at(days=5, hours=1),
        "finished_at": at(days=5, minutes=58),
        "summary": "Cancelled by the operator after the cause was identified by hand.",
    },
    # --- The three cases below reproduce, from fixture, what the running
    # deployment looked like before and after the console learned to read a
    # headline. Appended rather than folded into the six above: rewriting an
    # existing run would move baselines and unit assertions that are not
    # about this.
    {
        "run_id": "run-0101",
        # The word the persistence store actually serves for an ordinary
        # finish — the same word every run above now carries too, since the
        # store never wrote the runtime's own spelling in the first place.
        "status": "completed",
        "trigger": "alert",
        "started_at": at(days=1, hours=6, minutes=10),
        "finished_at": at(days=1, hours=5, minutes=41),
        # Explicitly empty, not merely absent: this run is one recorded
        # before the headline field existed, and an absent key would instead
        # take `_run_detail` down its *other* branch — synthesising a
        # generic one from the trigger, which is not what this fixture is
        # for. The empty string is what a real pre-headline row actually
        # holds, and it is what makes the console's own fallback the thing
        # under test here.
        "headline": "",
        "summary": (
            "### Incident Findings & Root Cause Analysis\n"
            "\n"
            "The **standby** replica fell behind after a maintenance window "
            "extended past its usual length, and alerting caught up only once "
            "the replication lag crossed the paging threshold.\n"
            "\n"
            "#### Evidence gathered\n"
            "\n"
            "- Replication lag crossed 900s at 05:12, alerting fired at 05:41\n"
            "- The maintenance window's own log shows it closed 38 minutes late\n"
            "- No write was lost: the standby caught up on its own within the hour\n"
            "\n"
            "| Metric | Before | After |\n"
            "| --- | --- | --- |\n"
            "| Replication lag | 940s | 4s |\n"
            "| Standby state | catching up | in sync |\n"
            "\n"
            "```\n"
            "2026-08-06T05:12:03Z lag_seconds=940 threshold=900 "
            "replica=pve02-pg-standby-01 window=maintenance-extended-past-schedule\n"
            "```\n"
            "\n"
            "No action is required: the standby is caught up and the "
            "maintenance window that caused the delay already closed."
        ),
    },
    {
        "run_id": "run-0102",
        # Degraded on the runtime's own account — the evidence gathered is
        # intact and the answer is whatever could be said from it — but the
        # persistence store has no third word for that nuance at the run's
        # own status field: `gateway/http/orchestration.py::_drive` writes
        # `COMPLETED` whether the investigator's own report is confident or
        # not, so this fixture serves the same word the deployment does. The
        # degradation is still legible in the summary below, which is where
        # the store actually carries it.
        "status": "completed",
        "trigger": "schedule",
        "started_at": at(days=6, hours=2),
        "finished_at": at(days=6, hours=1, minutes=44),
        # Deliberately over the console's own display limit once flattened,
        # and carrying emphasis a model's answer would — this is the case
        # that proves the name is flattened and clipped, not merely shown.
        "headline": (
            "The **platform** node's shared connection pool exhausted under "
            "sustained memory pressure, degrading query latency for every "
            "service that depends on it, until the leak was found and cleared"
        ),
        "summary": (
            "Memory pressure on the platform node exhausted the shared "
            "connection pool. The evidence gathered so far points at a slow "
            "leak in one long-running worker; the investigation could not "
            "confirm which one before its own budget ran out."
        ),
    },
    {
        "run_id": "run-0103",
        "status": "completed",
        "trigger": "manual",
        "started_at": at(days=7, hours=3),
        "finished_at": at(days=7, hours=2, minutes=55),
        "headline": "A stray log line was mistaken for a live credential",
        # Hostile on purpose: a raw HTML tag, an image pointing off this
        # deployment, a link whose scheme is executable, and one unbroken
        # line wider than the viewport. The report panel has to survive all
        # four without turning any of them into something the browser acts
        # on.
        "summary": (
            "The alert text embedded a fragment the log line itself had "
            "printed. Rendered here exactly as recorded, for review:\n"
            "\n"
            "<script>alert('not really')</script>\n"
            "\n"
            "![a screenshot the investigation was never given]"
            "(https://attacker.example/track.png)\n"
            "\n"
            "[open the dashboard](javascript:alert(document.cookie))\n"
            "\n"
            "```\n"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
            "```\n"
            "\n"
            "None of the above was a live credential; the alert source had "
            "copied a fixture line verbatim into its own payload."
        ),
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
    # Four calls across two turns — the run the transcript and cost panels
    # count against. One turn priced, one not: `unpriced_turns` on the
    # replay this produces is 1, never 0 and never every turn, so both the
    # "has cost" and the "this one did not price" paths stay exercised.
    "run-0005": (
        {
            "turn_id": "turn-0005-1",
            "index": 0,
            "model": "operator-configured",
            "selection_rationale": "the disabled job's own state names the subject to check first",
            "prompt_tokens": 612,
            "completion_tokens": 148,
            "cost": 0.0091,
            "calls": [
                {
                    "call_id": "call-0005-1",
                    "name": "estate.backup_job_status",
                    "status": "succeeded",
                    "duration_ms": 205,
                    "error": None,
                    "arguments": {"resource": "proxmox:container/hal9000/110"},
                },
                {
                    "call_id": "call-0005-2",
                    "name": "estate.backup_job_status",
                    "status": "succeeded",
                    "duration_ms": 179,
                    "error": None,
                    "arguments": {"resource_id": "ct-101"},
                },
            ],
        },
        {
            "turn_id": "turn-0005-2",
            "index": 1,
            "model": "operator-configured",
            "selection_rationale": "both subjects share one disabled job; read the schedule that disabled it",
            # No "cost" key: the call this turn made is one this dataset has
            # no real spend figure for, so the turn is left unpriced rather
            # than given an invented one.
            "calls": [
                {
                    "call_id": "call-0005-3",
                    "name": "knowledge.search",
                    "status": "succeeded",
                    "duration_ms": 91,
                    "error": None,
                },
                {
                    "call_id": "call-0005-4",
                    "name": "estate.backup_schedule",
                    "status": "succeeded",
                    "duration_ms": 133,
                    "error": None,
                    "arguments": {"resource": "proxmox:container/hal9000/110"},
                },
            ],
        },
    ),
}


#: What each run's stages established, in the order the pipeline runs them.
#:
#: Declared rather than derived, for the same reason the turns above are. A
#: stage's finding is what that stage's own slice said, and a fixture that
#: computed one from the turn list would be inventing the answer for the four
#: stages that produce no turn at all — which is the whole reason a stage is
#: recorded separately.
#:
#: ``llm_calls`` is structural and so is stated: intake classifies on one model
#: call and diagnosis structures on one, whatever the run. The token counts are
#: not structural, and this dataset has no real spend figures for them, so they
#: are absent rather than filled with plausible numbers — the same rule the
#: unpriced turn below already follows.
#:
#: ``run-0003`` is still gathering, so its trace holds the three stages that
#: finished and no fourth. A stage record is written when a stage *ends*; a
#: fixture that listed a fourth would be claiming a stage completed because it
#: was seen to start, which is exactly what the recorder refuses to do.
#:
#: ``run-0004`` failed partway through instead: its third entry carries
#: ``failed: True`` and a finding that names what went wrong, and the pipeline
#: never reached the three stages after it — the same "a stage record is
#: written when a stage ends" rule, ended in failure rather than in success.
_STAGES: Final[Mapping[str, Sequence[Mapping[str, Any]]]] = {
    "run-0001": (
        {
            "stage": "resolve_integrations",
            "finding": "6 capabilities available on this team",
            "duration_ms": 180,
        },
        {
            "stage": "intake",
            "finding": "A new incident, not a repeat of one already open",
            "duration_ms": 1_410,
            "llm_calls": 1,
        },
        {
            "stage": "plan_evidence",
            "finding": "4 capabilities shortlisted, best first",
            "duration_ms": 60,
        },
        {
            "stage": "gather_evidence",
            "finding": "3 observations gathered",
            "duration_ms": 27_900,
        },
        {
            "stage": "diagnose",
            "finding": "3 of 3 claims tied to an observation the run holds",
            "duration_ms": 4_120,
            "llm_calls": 1,
        },
        {
            "stage": "deliver",
            "finding": (
                "No destination is configured for this team, so the report was produced "
                "and not shipped. It is in the investigation record."
            ),
            "duration_ms": 300,
        },
    ),
    "run-0003": (
        {
            "stage": "resolve_integrations",
            "finding": "6 capabilities available on this team",
            "duration_ms": 175,
        },
        {
            "stage": "intake",
            "finding": "A new incident, not a repeat of one already open",
            "duration_ms": 1_260,
            "llm_calls": 1,
        },
        {
            "stage": "plan_evidence",
            "finding": "3 capabilities shortlisted, best first",
            "duration_ms": 55,
        },
    ),
    "run-0004": (
        {
            "stage": "resolve_integrations",
            "finding": "5 capabilities available on this team",
            "duration_ms": 190,
        },
        {
            "stage": "intake",
            "finding": "A new incident, not a repeat of one already open",
            "duration_ms": 1_180,
            "llm_calls": 1,
        },
        {
            "stage": "plan_evidence",
            "finding": "The model could not be reached to score the shortlist",
            "duration_ms": 340,
            "failed": True,
        },
    ),
    "run-0005": (
        {
            "stage": "resolve_integrations",
            "finding": "6 capabilities available on this team",
            "duration_ms": 168,
        },
        {
            "stage": "intake",
            "finding": "A new incident, not a repeat of one already open",
            "duration_ms": 1_330,
            "llm_calls": 1,
        },
        {
            "stage": "plan_evidence",
            "finding": "2 capabilities shortlisted, best first",
            "duration_ms": 48,
        },
        {
            "stage": "gather_evidence",
            "finding": "2 observations gathered",
            "duration_ms": 11_400,
            "prompt_tokens": 612,
            "completion_tokens": 148,
            "llm_calls": 2,
        },
    ),
}

#: Which of the six stages a turn ran inside. Every turn this dataset holds was
#: written by the loop, and the loop is what the gathering stage drives — so all
#: of them belong to that one stage, which is the fact that makes the other five
#: sections worth serving at all.
_TURN_STAGE: Final[str] = "gather_evidence"


def _run_calls(run_id: str) -> tuple[ToolCallRecord, ...]:
    """Return every call ``run_id`` made, in the shape ``touched_resources_of`` reads.

    ``ToolCallRecord.arguments`` is the whole recorded call body — the same
    ``arguments``/``result`` envelope a call in ``_TURNS`` is already written
    in — so this wraps what is already there rather than reshaping it.
    """
    return tuple(
        ToolCallRecord(
            call_id=str(call["call_id"]),
            run_id=run_id,
            turn_id=str(turn["turn_id"]),
            tool_name=str(call["name"]),
            arguments=call,
        )
        for turn in _TURNS.get(run_id, ())
        for call in turn.get("calls", ())
    )


def _run_detail(run: Mapping[str, Any], incident_by_run: Mapping[str, str]) -> dict[str, Any]:
    """Return ``run`` in the shape the console's investigation summary answers in.

    Field for field what ``gateway.http.routes.investigations.summary_of`` and
    ``linked_summary`` compute from a stored run — imported rather than
    reimplemented, so a headline synthesised here and one a live deployment
    synthesises are never two different sentences for the same run:

    - ``headline`` is synthesised the same way a stored run with none gets
      one — never read from ``summary``, which is the document it has to
      stay distinct from — **unless** ``run`` already names an explicit
      ``headline`` (including ``""``). A raw run entry that sets the key
      itself is standing in for a real model-produced sentence, or for a run
      recorded before this field existed at all; either way, the fixture is
      declaring the fact rather than asking this function to invent one.
    - ``report`` is that document, unaltered.
    - ``touched_resources`` comes from what this run's own calls were
      actually made with, never from a declared subject.
    - ``incident_id`` is read back from the same incident this run is
      attached to in the estate half of this dataset — the one place that
      link is recorded — never invented here.
    """
    identifier = str(run["run_id"])
    trigger = str(run.get("trigger") or "")
    objective = f"{trigger} investigation" if trigger else ""
    headline = (
        str(run["headline"]) if "headline" in run else synthesize_headline(objective=objective)
    )
    return {
        **run,
        "headline": headline,
        "report": str(run.get("summary") or ""),
        "incident_id": incident_by_run.get(identifier, ""),
        "touched_resources": list(touched_resources_of(_run_calls(identifier))),
    }


def _replay_call(call: Mapping[str, Any]) -> dict[str, Any]:
    """Return one call in the shape the replay route serves it.

    The result goes through the reading bound the route applies, rather than
    being copied out of ``_TURNS`` whole: a fixture that promised a console a
    payload a deployment would have cut is a fixture the screen built against
    it fails on in production. ``result`` and ``result_truncated`` are present
    on every call for the same reason the route sets them on every call — a
    capability that returned nothing and one whose answer was dropped are
    different facts, and both have to be sayable.
    """
    served, removal = truncate(dict(call.get("result") or {}), bounds=REPLAY_RESULT_BOUNDS)
    return {**call, "result": served, "result_truncated": removal.happened}


def _replay_turn(turn: Mapping[str, Any]) -> dict[str, Any]:
    """Return one turn with its calls in the shape the replay route serves them."""
    return {**turn, "calls": [_replay_call(call) for call in turn.get("calls", ())]}


def _replay_stage(stage: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return one stage in the shape the replay route serves it.

    Every key the route's own model declares is present, defaulted the way the
    route defaults it. A fixture that omitted ``llm_calls`` on the four stages
    that never turn would leave a console unable to tell a stage that made a
    model call and produced no turn from one that did nothing at all — which is
    the distinction the whole grouping rests on.
    """
    gathered = stage["stage"] == _TURN_STAGE
    return {
        "stage": str(stage["stage"]),
        "finding": str(stage.get("finding", "")),
        "duration_ms": int(stage.get("duration_ms", 0)),
        "prompt_tokens": int(stage.get("prompt_tokens", 0)),
        "completion_tokens": int(stage.get("completion_tokens", 0)),
        "llm_calls": int(stage.get("llm_calls", 0)),
        "failed": bool(stage.get("failed", False)),
        "turns": [_replay_turn(turn) for turn in turns] if gathered else [],
    }


def _recorded_events(
    turns: Sequence[Mapping[str, Any]],
    stages: Sequence[Mapping[str, Any]],
    *,
    finished: bool,
) -> int:
    """Return how many entries this run's own event log holds.

    Enumerated from the records the fixture declares, never a formula over the
    turn count. The recorder writes exactly one event per turn, one per call,
    one per stage that ended, one when the run starts and one when it ends — so
    counting the declared records *is* reading the log, while multiplying turns
    by a constant is guessing at a shape and is what the console was doing
    before the count was served.
    """
    calls = sum(len(turn.get("calls", ())) for turn in turns)
    return 1 + len(stages) + len(turns) + calls + (1 if finished else 0)


def _turn_usage(turn: Mapping[str, Any]) -> tuple[float, int, bool]:
    """Return ``(cost, tokens, priced)`` for one turn, from what it recorded.

    ``priced`` is ``False`` exactly when the turn carries no ``cost`` at
    all — the same distinction ``platform.runs.recorder.record_turn`` marks
    by omitting the key, and the one ``ReplayedRun.unpriced_turn_count``
    counts on the real replay path. A turn with no cost contributes zero to
    the running total rather than a guess, which is what keeps the sum
    honest for a run whose calls this dataset does not have real spend
    figures for.
    """
    if "cost" not in turn:
        return 0.0, 0, False
    tokens = int(turn.get("prompt_tokens", 0)) + int(turn.get("completion_tokens", 0))
    return float(turn["cost"]), tokens, True


def runs_records(*, incident_by_run: Mapping[str, str] | None = None) -> tuple[CapturedRecord, ...]:
    """Return the run list, each run's detail, its transcript and its replay."""
    linked = incident_by_run or {}
    details = tuple(_run_detail(run, linked) for run in RUNS)
    records: list[CapturedRecord] = [_record("runs", {}, {"runs": list(details)})]
    for run, detail in zip(RUNS, details):
        identifier = str(run["run_id"])
        records.append(_record("run-detail", {"run_id": identifier}, detail))
        turns = list(_TURNS.get(identifier, ()))
        records.append(
            _record("run-threads", {"run_id": identifier}, {"run_id": identifier, "turns": turns})
        )
        # Summed from what each turn actually carries — never a formula over
        # the turn count — so a run with no real spend recorded reports zero
        # rather than a plausible-looking number nothing backs. A turn that
        # never priced itself (still running, or a call this dataset has no
        # real figure for) is counted in ``unpriced_turns`` instead of
        # silently contributing to the total.
        usages = [_turn_usage(turn) for turn in turns]
        stages = list(_STAGES.get(identifier, ()))
        turn_tokens = sum(tokens for _, tokens, _ in usages)
        records.append(
            _record(
                "run-replay",
                {"run_id": identifier},
                {
                    "run_id": identifier,
                    "turns": [_replay_turn(turn) for turn in turns],
                    "stages": [_replay_stage(stage, turns) for stage in stages],
                    "total_cost": round(sum(cost for cost, _, _ in usages), 4),
                    # Summed over the stages when the run recorded any, which is
                    # what the route does and for the same reason: only the
                    # gathering stage produces turns, so a turn-only total omits
                    # every model call the other five made.
                    "total_tokens": (
                        sum(
                            int(stage.get("prompt_tokens", 0))
                            + int(stage.get("completion_tokens", 0))
                            for stage in stages
                        )
                        if stages
                        else turn_tokens
                    ),
                    "turn_tokens": turn_tokens,
                    "total_events": _recorded_events(
                        turns, stages, finished=run.get("finished_at") is not None
                    ),
                    "is_interrupted": run["status"] == "cancelled",
                    "unpriced_turns": sum(1 for _, _, priced in usages if not priced),
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


def _decision(
    *,
    approval_id: str,
    run_id: str,
    action: str,
    side_effect_level: str,
    summary: str,
    title: str,
    requester: str,
    state: str,
    requested_at: str,
    expires_at: str,
    category: str = "remediation",
    intent: str = "",
    origin: Mapping[str, Any] | None = None,
    risk: Mapping[str, Any] | None = None,
    steps: tuple[Mapping[str, Any], ...] = (),
    rollback: tuple[Mapping[str, Any], ...] = (),
    reversible: bool = True,
    evidence: tuple[Mapping[str, Any], ...] = (),
    blast_radius: Mapping[str, Any] | None = None,
    arguments: Mapping[str, Any] | None = None,
    rollback_plan: Mapping[str, Any] | None = None,
    decided_at: str | None = None,
    decided_by: str | None = None,
    reason: str | None = None,
    verdict: str | None = None,
    applied_and_verified: bool = False,
    prior_effectiveness_summary: str = "",
) -> dict[str, Any]:
    """Return one decision in the field-by-field shape `ApprovalView` serves.

    One function rather than one literal per record, so the fixture cannot
    drift into a shape the real gateway would never actually send — every
    field `gateway/http/routes/approvals.py`'s `ApprovalView` declares is
    named here once, with the same defaults (`known: False`, `""`, `[]`)
    for whatever a given decision does not carry.
    """
    resolved_risk = risk or {"class": "medium", "score": 3, "scale": 5}
    resolved_radius = blast_radius or {"count": None, "depth": None, "known": False}
    raw = {
        "capability": action,
        "requester": requester,
        "intent": intent,
        "target": {"identifier": run_id},
        "side_effect_level": side_effect_level,
        "steps": [dict(step) for step in steps],
        "rollback": [dict(step) for step in rollback],
        "evidence": [dict(item) for item in evidence],
        "blast_radius": dict(resolved_radius),
    }
    return {
        "approval_id": approval_id,
        "run_id": run_id,
        "action": action,
        "side_effect_level": side_effect_level,
        "summary": summary,
        "requested_at": requested_at,
        "expires_at": expires_at,
        "state": state,
        "arguments": dict(arguments) if arguments is not None else {},
        "decided_at": decided_at,
        "decided_by": decided_by,
        "reason": reason,
        "rollback_plan": rollback_plan,
        "blast_radius_count": resolved_radius.get("count"),
        "title": title,
        "requester": requester,
        "origin": dict(origin)
        if origin is not None
        else {"run_id": run_id, "headline": "", "incident_id": ""},
        "category": category,
        "intent": intent,
        "risk": dict(resolved_risk),
        "steps": [dict(step) for step in steps],
        "rollback": [dict(step) for step in rollback],
        "evidence": [dict(item) for item in evidence],
        "blast_radius": dict(resolved_radius),
        "autonomy": {
            "side_effect_level": side_effect_level,
            "reversible": reversible,
            "queued": True,
        },
        "prior_effectiveness": {"summary": prior_effectiveness_summary},
        "created_at": requested_at,
        "verdict": verdict,
        "applied_and_verified": applied_and_verified,
        "raw": raw,
    }


#: The real staging payload (spec fact 2) — a pending remediation, in-window,
#: with an open interaction on its run (`INTERACTIONS['run-0005']`), so this
#: one exercises the `DecisionControls` decide-in-place path.
_PENDING = _decision(
    approval_id="apr-0001",
    run_id="run-0005",
    action="proxmox_start_guest",
    side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
    summary="Restart the guest lxc/122 on pve01.",
    title="Start the guest lxc/122 on pve01",
    requester="alert-router",
    state="pending",
    requested_at=at(minutes=21),
    expires_at=at(minutes=-39),
    intent="The Redis probes fail because the container was shut down.",
    origin={"run_id": "run-0005", "headline": "RedisExporterDown", "incident_id": "inc-0001"},
    risk={"class": "low", "score": 3, "scale": 5},
    steps=(
        {
            "ordinal": 1,
            "summary": "Start the guest via Proxmox",
            "capability": "proxmox_start_guest",
        },
    ),
    rollback=(
        {
            "ordinal": 1,
            "summary": "Ask the guest to shut down and wait",
            "capability": "proxmox_shutdown_guest",
        },
    ),
    reversible=True,
    evidence=(
        {
            "summary": "11 entries in the Alertmanager timeline",
            "reference": "alertmanager:incident_timeline:inc-0001",
        },
        {
            "summary": "HAL9000 quorate — restarting does not risk the cluster",
            "reference": "proxmox:quorum:HAL9000",
        },
    ),
    blast_radius={"count": 1, "depth": 1, "known": True},
    arguments={"node": "pve01", "vmid": 122},
    rollback_plan={
        "plan_id": "plan-0001",
        "approval_id": "apr-0001",
        "notes": "Shutting the guest down again restores the state exactly.",
        "steps": [
            {
                "ordinal": 1,
                "description": "Ask the guest to shut down and wait",
                "capability": "proxmox_shutdown_guest",
                "arguments": {"node": "pve01", "vmid": 122},
            }
        ],
    },
)

#: Genuinely past its own window — a live origin (the capability still
#: resolves), so reproposing it succeeds.
_EXPIRED = _decision(
    approval_id="apr-0002",
    run_id="run-0001",
    action="estate.expand_volume",
    side_effect_level=SIDE_EFFECT_WRITE_IRREVERSIBLE,
    summary="Grow the volume that is at the ceiling of its own allocation.",
    title="Grow the volume that is at the ceiling of its own allocation.",
    requester="alert-router",
    state="expired",
    requested_at=at(days=2, minutes=33),
    expires_at=at(days=1, minutes=33),
    origin={"run_id": "run-0001", "headline": "", "incident_id": ""},
    risk={"class": "high", "score": 4, "scale": 5},
    steps=(
        {
            "ordinal": 1,
            "summary": "Grow the volume that is at the ceiling of its own allocation.",
            "capability": "estate.expand_volume",
        },
    ),
    rollback=(),
    reversible=False,
    evidence=(
        {
            "summary": "Volume at 99.6% of its own allocation",
            "reference": "estate:storage:vm-100-disk-0",
        },
    ),
    blast_radius={"count": 1, "depth": 1, "known": True},
    arguments={"volume_id": "vm-100-disk-0", "add_bytes": 16_000_000_000},
    rollback_plan=None,
    decided_at=at(days=1, minutes=33),
)

#: Also past its own window, but its origin cannot be rebuilt — the connector
#: it named has since been removed from the catalogue. Reproposing it is
#: refused by name rather than crashing or fabricating a plan (FR-016);
#: `tools/mockplane/server.py`'s write simulation for `approval-repropose`
#: keys its refusal to this one approval by id, so every *other* expired
#: decision still reproposes as the live-origin case does.
_EXPIRED_DEAD_ORIGIN = _decision(
    approval_id="apr-0005",
    run_id="run-0006",
    action="legacy.rotate_removed_connector_credential",
    side_effect_level=SIDE_EFFECT_WRITE_IRREVERSIBLE,
    summary="Rotate the credential for a connector that has since been removed.",
    title="Rotate the credential for a connector that has since been removed.",
    requester="alert-router",
    state="expired",
    requested_at=at(days=5, minutes=10),
    expires_at=at(days=4, minutes=10),
    origin={"run_id": "run-0006", "headline": "", "incident_id": ""},
    risk={"class": "medium", "score": 3, "scale": 5},
    steps=(
        {
            "ordinal": 1,
            "summary": "Rotate the credential for the retired connector",
            "capability": "legacy.rotate_removed_connector_credential",
        },
    ),
    rollback=(),
    reversible=False,
    evidence=(
        {
            "summary": "Credential due for rotation before the connector was removed",
            "reference": "integrations:connector:legacy-example",
        },
    ),
    blast_radius={"count": 0, "depth": 0, "known": False},
    arguments={"connector_id": "legacy-example"},
    rollback_plan=None,
    decided_at=at(days=4, minutes=10),
)

#: Approved, applied and verified.
_APPROVED = _decision(
    approval_id="apr-0003",
    run_id="run-0004",
    action="knowledge.clear_cache",
    side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
    summary="Clear cache of flaresolverr.",
    title="Clear cache of flaresolverr",
    requester="alert-router",
    state="approved",
    requested_at=at(days=2, hours=3),
    expires_at=at(days=1, hours=27),
    origin={"run_id": "run-0004", "headline": "", "incident_id": ""},
    risk={"class": "low", "score": 1, "scale": 5},
    reversible=True,
    arguments={"service": "flaresolverr"},
    decided_at=at(days=2),
    decided_by="user-operator",
    verdict="approved",
    applied_and_verified=True,
)

#: Rejected, with a named reason.
_REJECTED = _decision(
    approval_id="apr-0004",
    run_id="run-0002",
    action="estate.migrate_guest",
    side_effect_level=SIDE_EFFECT_WRITE_IRREVERSIBLE,
    summary="Migrate vibe-kanban to pve02.",
    title="Migrate vibe-kanban to pve02",
    requester="alert-router",
    state="rejected",
    requested_at=at(days=8),
    expires_at=at(days=7),
    origin={"run_id": "run-0002", "headline": "", "incident_id": ""},
    risk={"class": "medium", "score": 3, "scale": 5},
    reversible=False,
    arguments={"guest": "vibe-kanban", "target_node": "pve02"},
    decided_at=at(days=7, hours=23),
    decided_by="user-operator",
    reason="wrong maintenance window",
    verdict="rejected",
)

APPROVALS: Final[tuple[Mapping[str, Any], ...]] = (
    _PENDING,
    _EXPIRED,
    _EXPIRED_DEAD_ORIGIN,
    _APPROVED,
    _REJECTED,
)

#: The approval id `approval-repropose` refuses by name — `server.py`'s write
#: simulation matches this one exactly and every other expired id falls
#: through to the generic success record below.
DEAD_ORIGIN_APPROVAL_ID: Final = str(_EXPIRED_DEAD_ORIGIN["approval_id"])

#: The id `approval-repropose`'s generic (fixture-default) success hands out.
#: A literal rather than a counter: the mock's write simulation
#: (`_apply_write` in `server.py`) overwrites every timestamp on it with a
#: fresh one at call time, so the only thing this literal has to be is
#: distinct from every approval id the dataset serves elsewhere.
REPROPOSED_APPROVAL_ID: Final = "apr-1002"


def interaction_records() -> tuple[CapturedRecord, ...]:
    """Return each run's open questions and approvals, and the approval queue.

    The queue is recorded once per `state=` bucket (FR-006) — three separate
    responses under the one `approvals` slug, distinguished by their own
    recorded `arguments`, which `bodyFor`/`MockPlane.answer` match against
    the request's actual query string. A single undifferentiated response
    (the shape this fixture used to be) answers every bucket identically,
    which is exactly the defect a acceptance run against this dataset found:
    the same two rows counted as pending, expired and decided at once.
    """
    records = [
        _record("interactions", {"run_id": run_id}, {"interactions": list(found)})
        for run_id, found in INTERACTIONS.items()
    ]
    # A bare read with no `state=` at all matches the real gateway's own
    # default (`Query(default="pending", ...)`, gateway/http/routes/approvals.py)
    # — the same body as `state=pending`, so `shell/load.ts`'s `readAttention`,
    # which still reads the endpoint unfiltered, sees the same list a
    # `state=pending` read would.
    records.append(_record("approvals", {}, {"approvals": [_PENDING]}))
    records.append(_record("approvals", {"state": "pending"}, {"approvals": [_PENDING]}))
    records.append(
        _record(
            "approvals",
            {"state": "expired"},
            # The live-origin one first: it is the one every `cardInState`
            # lookup in the acceptance spec expands, since the screen only
            # expands `queue[0]` (`approvals.tsx`) and a reproposed origin is
            # never removed from this bucket — only `discard` does that, by
            # changing its own state. The dead-origin one rides along after
            # it, collapsed, so the dataset carries both cases FR-016 and
            # T031 ask for without disturbing which card the spec exercises.
            {"approvals": [_EXPIRED, _EXPIRED_DEAD_ORIGIN]},
        )
    )
    records.append(
        _record(
            "approvals",
            {"state": "decided", "limit": "10"},
            {"approvals": [_REJECTED, _APPROVED]},
        )
    )
    for approval in APPROVALS:
        records.append(
            _record(
                "approval-detail", {"approval_id": str(approval["approval_id"])}, dict(approval)
            )
        )
    # A fresh pending decision, on the same mechanism `RequestBuilder.queue()`
    # composes for the real gateway (FR-015) — the generic (fixture-default)
    # response every expired id gets, and `server.py`'s `_apply_write`
    # overwrites every timestamp on it at call time so "a current reading of
    # the environment" is not a fixed literal three days old.
    records.append(
        _record(
            "approval-repropose",
            {},
            {
                "approval_id": REPROPOSED_APPROVAL_ID,
                "state": "pending",
                "created_at": at(),
            },
            method="POST",
            status=201,
        )
    )
    # The one approval id whose origin cannot be rebuilt (FR-016) — refused
    # by name rather than by the generic success above.
    records.append(
        _record(
            "approval-repropose",
            {"approval_id": DEAD_ORIGIN_APPROVAL_ID},
            {
                "detail": f"{DEAD_ORIGIN_APPROVAL_ID!r}'s stored document no longer "
                "describes a remediation action that can be rebuilt"
            },
            method="POST",
            status=422,
        )
    )
    records.append(
        _record(
            "approval-discard",
            {},
            {
                "approval_id": "",
                "state": "discarded",
                "decided_at": at(),
                "decided_by": "user-operator",
            },
            method="POST",
        )
    )
    # Deciding an approval directly — the path staging exercises for every
    # real approve and reject today, since staging has no live run for a
    # decision to answer through an interaction instead
    # (`gateway/http/routes/approvals.py::decide_approval`). One generic
    # (fixture-default) success record, the same simplification
    # `proposal-decision` above already makes for the same reason: the served
    # answer is the same shape either way, and which verdict actually landed
    # is what the `approvals` buckets `server.py`'s write simulation rewrites
    # answer on the next read, not this response's own body.
    records.append(
        _record(
            "approval-decision",
            {},
            {
                "approval_id": "",
                "state": "approved",
                "decided_at": at(),
                "decided_by": "user-operator",
            },
            method="POST",
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

# ``outcome`` reads from the values ``EpisodeOutcome`` actually declares
# (``platform/persistence/ports/episode_store.py``) — ``"resolved"``,
# ``"mitigated"``, ``"inconclusive"`` or ``"false_positive"`` — not
# ``"acknowledged"``/``"unresolved"``, which the real backend has never
# emitted and the console has no presentation declared for.
#
# The two below that used to read ``"acknowledged"`` now read ``"mitigated"``,
# not ``"inconclusive"``: the demonstration seeder's own translation table
# (``platform/startup/demo/seeder.py``, ``_EPISODE_OUTCOME``) is the one place
# this exact legacy vocabulary is already mapped onto the real enum, and it
# maps ``"acknowledged"`` to ``MITIGATED`` and ``"unresolved"`` to
# ``INCONCLUSIVE`` — two different words, kept two different outcomes, not
# flattened to one.
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
        "outcome": "mitigated",
        "components": ["cluster"],
        "occurred_at": at(days=1, hours=2, minutes=47),
    },
    {
        "episode_id": "ep-0003",
        "run_id": "run-0004",
        "title": "The investigation could not reach the metrics agent",
        "summary": "The agent is one of the failed units on the primary; nothing was "
        "watching the watcher.",
        "outcome": "inconclusive",
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
        "outcome": "mitigated",
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

#: Fields the two advanced-configuration sections on Autonomy & guardrails and
#: on Notifications draw an effective-value row for, and that this dataset
#: leaves on the schema's own default everywhere — no node in the chain sets
#: any of them. Unlike ``_CONFIG_FIELDS`` above, which pairs every entry with
#: an owner in ``_config_fields``'s ``source``/``values``, a field named here
#: and nowhere else in that mapping is exactly the state those two screens'
#: own suite needs: a value with no override, resolved from the schema's
#: default alone, with an empty ``provenance`` rather than a level that never
#: set it. The value each carries below *is* its schema default
#: (``platform/config_service/schema/policies.py``,
#: ``platform/config_service/schema/surfaces.py``) — kept in one place, not
#: retyped, so a schema default that moves is a failing contract test here
#: rather than a fixture silently describing a default nothing enforces.
_CONFIG_FIELDS_DEFAULTED: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "path": "policies.masking.enabled",
        "label": "Masking enabled",
        "type": "boolean",
        "help": "Hide identifying values before they are sent to a model.",
        "section": "policies.masking",
        "section_summary": "How much of the estate may reach a model you do not host.",
        "section_help": "How much of the estate may reach a model you do not host.",
        "default": True,
    },
    {
        "path": "policies.masking.level",
        "label": "Masking level",
        "type": "string",
        "help": "How much is hidden. A stricter level covers more kinds of value.",
        "section": "policies.masking",
        "section_summary": "How much of the estate may reach a model you do not host.",
        "section_help": "How much of the estate may reach a model you do not host.",
        "default": "standard",
    },
    # An array the schema names an entry shape for (`name`, `pattern`), so the
    # generic editor draws it as an `ObjectList` — but only where this
    # catalogue actually hands the field to that editor, which no entry named
    # it to before. Left on the schema's own default (`[]`), same as every
    # other field in this tuple, its own docstring's promise.
    {
        "path": "policies.masking.custom_patterns",
        "label": "Custom patterns",
        "type": "array",
        "help": "Extra value shapes of your own to hide, beyond the ones shipped.",
        "section": "policies.masking",
        "section_summary": "How much of the estate may reach a model you do not host.",
        "section_help": "How much of the estate may reach a model you do not host.",
        "default": [],
        "item_fields": [
            {
                "path": "name",
                "label": "Name",
                "type": "string",
                "help": "A short name for this shape. It appears in the placeholder "
                "that replaces the value, so make it recognisable.",
                "max_length": 20000,
            },
            {
                "path": "pattern",
                "label": "Pattern",
                "type": "string",
                "help": "A regular expression matching the values to hide.",
                "max_length": 20000,
            },
        ],
    },
    {
        "path": "policies.guardrails.mode",
        "label": "Guardrail mode",
        "type": "string",
        "help": "Enforcing blocks or redacts a match. Observing only records it.",
        "section": "policies.guardrails",
        "section_summary": "What happens when something that looks like a secret is spotted.",
        "section_help": "What happens when something that looks like a secret is spotted.",
        "default": "enforcing",
        "allowed_values": ["enforcing", "observing"],
    },
    {
        "path": "policies.guardrails.ruleset",
        "label": "Ruleset",
        "type": "string",
        "help": "Which named set of rules to use. Empty means the shipped set.",
        "section": "policies.guardrails",
        "section_summary": "What happens when something that looks like a secret is spotted.",
        "section_help": "What happens when something that looks like a secret is spotted.",
        "default": None,
    },
    {
        "path": "policies.approvals.threshold",
        "label": "Approval threshold",
        "type": "string",
        "help": "The lowest kind of action that needs a person to say yes.",
        "section": "policies.approvals",
        "section_summary": "Where the line sits between acting alone and asking first.",
        "section_help": "Where the line sits between acting alone and asking first.",
        "default": "write_reversible",
    },
    {
        "path": "policies.approvals.expiry_hours",
        "label": "Approval expiry",
        "type": "number",
        "help": "How long a request waits for an answer before it lapses.",
        "section": "policies.approvals",
        "section_summary": "Where the line sits between acting alone and asking first.",
        "section_help": "Where the line sits between acting alone and asking first.",
        "default": 4.0,
        "minimum": 0.25,
        "maximum": 168.0,
    },
    {
        "path": "surfaces.notification_policy.quiet_hours_enabled",
        "label": "Quiet hours enabled",
        "type": "boolean",
        "help": "Hold non-urgent notifications during the hours set below.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": False,
    },
    {
        "path": "surfaces.notification_policy.quiet_hours_start",
        "label": "Quiet hours start",
        "type": "integer",
        "help": "The hour of the day quiet hours begin, 0 to 23.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": 22,
        "minimum": 0,
        "maximum": 23,
    },
    {
        "path": "surfaces.notification_policy.quiet_hours_end",
        "label": "Quiet hours end",
        "type": "integer",
        "help": "The hour of the day quiet hours end, 0 to 23.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": 7,
        "minimum": 0,
        "maximum": 23,
    },
    {
        "path": "surfaces.notification_policy.timezone",
        "label": "Timezone",
        "type": "string",
        "help": "The team's own timezone, so quiet hours mean this team's night.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": "UTC",
    },
    {
        "path": "surfaces.notification_policy.cooldown_seconds",
        "label": "Cooldown",
        "type": "number",
        "help": "How long to wait before notifying about the same thing again.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": 900.0,
        "minimum": 0,
    },
    {
        "path": "surfaces.notification_policy.notifications_per_hour",
        "label": "Notifications per hour",
        "type": "integer",
        "help": "The most notifications this team receives in an hour.",
        "section": "surfaces.notification_policy",
        "section_summary": "How much of a team's attention a notification may take.",
        "section_help": "How much of a team's attention a notification may take.",
        "default": 20,
        "minimum": 0,
    },
    {
        "path": "policies.autonomy.allow_unverifiable_actions",
        "label": "Allow unverifiable actions",
        "type": "boolean",
        "help": "Let an action run unattended even when nothing can confirm it worked.",
        "section": "policies.autonomy",
        "section_summary": "How much this team may do without asking, and the bounds on the answer.",
        "section_help": "How much this team may do without asking, and the bounds on the answer.",
        "default": False,
    },
    {
        "path": "policies.autonomy.dry_run",
        "label": "Dry run",
        "type": "boolean",
        "help": "Simulate every action for this team, whatever any rule says.",
        "section": "policies.autonomy",
        "section_summary": "How much this team may do without asking, and the bounds on the answer.",
        "section_help": "How much this team may do without asking, and the bounds on the answer.",
        "default": False,
    },
    {
        "path": "policies.autonomy.recurrence_threshold",
        "label": "Recurrence threshold",
        "type": "integer",
        "help": "How many times the same fix may repeat before it is a recurring problem.",
        "section": "policies.autonomy",
        "section_summary": "How much this team may do without asking, and the bounds on the answer.",
        "section_help": "How much this team may do without asking, and the bounds on the answer.",
        "default": 0,
        "minimum": 0,
    },
    {
        "path": "policies.autonomy.recurrence_window_seconds",
        "label": "Recurrence window",
        "type": "integer",
        "help": "How long that window is, in seconds. Zero uses the deployment default.",
        "section": "policies.autonomy",
        "section_summary": "How much this team may do without asking, and the bounds on the answer.",
        "section_help": "How much this team may do without asking, and the bounds on the answer.",
        "default": 0,
        "minimum": 0,
    },
)


def _config_fields(node_id: str, *, inherited: bool) -> list[dict[str, Any]]:
    """Return the field catalogue as one node stands on it.

    The provenance mirrors the effective record beside it, so the editor and the
    values table above it cannot disagree about which level set what — which is
    the one thing a configuration screen must never do.

    Every field in ``_CONFIG_FIELDS_DEFAULTED`` is deliberately absent from
    ``source``/``values`` below: a path with no entry in either resolves to its
    own ``default`` with an empty provenance, exactly the "nothing has ever
    overridden this" state those two mappings have no other way to say.
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
            "value": values.get(str(declared["path"]), declared["default"]),
            "provenance": source.get(str(declared["path"]), ""),
            "set_here": source.get(str(declared["path"])) == node_id,
            "locked_by": "",
            "approval_gated": str(declared["path"]) == "approval.required_above",
            "required": False,
        }
        for declared in (*_CONFIG_FIELDS, *_CONFIG_FIELDS_DEFAULTED)
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
                        # The investigator's own choice, nested rather than a
                        # flat dotted key: `ModelsSettingsScreen` reads every
                        # role through `valueAt`, which walks a path segment at
                        # a time, the same shape `models.test.tsx`'s own
                        # fixture already assumes. The other seven roles are
                        # left absent on purpose — `_config_fields` below
                        # already photographs "one role bound, seven left on
                        # the deployment default", and this is the same fact.
                        "models": {
                            "investigator": {
                                "provider": "anthropic",
                                "model": "claude-sonnet-5",
                            },
                        },
                    },
                    "provenance": {
                        "investigation.max_loops": ORG_NODE if inherited else identifier,
                        "investigation.reasoning_effort": identifier,
                        "approval.required_above": ORG_NODE if inherited else identifier,
                        "retention.audit_days": ORG_NODE if inherited else identifier,
                        "agents.subagents": identifier,
                        "agents.prompts.investigator": identifier,
                        "capabilities.protocol_servers": identifier,
                        "models.investigator.provider": ORG_NODE if inherited else identifier,
                        "models.investigator.model": ORG_NODE if inherited else identifier,
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
                    "overrides": [dict(_ACTIVE_OVERRIDE)] if identifier == ORG_NODE else [],
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
                            "side_effect_level": SIDE_EFFECT_WRITE_REVERSIBLE,
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
        # Read through the route's own helper rather than restated: the
        # direction is derived from the webhook router's source list, and a
        # second derivation here is a second thing to forget when a source is
        # added.
        **dict(
            zip(
                ("direction", "intake_path"),
                route_direction(entry.name),
                strict=True,
            )
        ),
        "where_to_get_it": entry.profile.where_to_get_it,
    }


#: The one real, installed vendor that is connected and verified — the second
#: half of "two connected and verified" the docstring below already promises,
#: alongside the fictional ``chat``. Produced through the real health ledger
#: rather than hand-typed, so a browser test against a *non-fictional*
#: catalogue entry is exercising the exact function
#: ``gateway/http/routes/integrations.py`` calls, not a second opinion about
#: what that function would say. Alertmanager, because it is the one this
#: deployment's own intake, rules and receiver already point at (see
#: ``_LIVE_SOURCE`` below) — the deployment that is connected to it for real.
_VERIFIED_INTEGRATION: Final = "alertmanager"

#: Configured — a credential is stored — and never checked. ``catalogue()``
#: reports ``HealthStatus.UNKNOWN`` for a name that is ``configured`` but
#: carries no ledger record, which is exactly "stored, never verified": the
#: state a screen showing only ``unconfigured`` real vendors could never
#: render. Loki rather than Prometheus, so the one other real vendor a deep
#: link is measured against elsewhere stays exactly as unconfigured as every
#: other uninstalled entry.
_STORED_UNVERIFIED_INTEGRATION: Final = "loki"


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

    Two of the real, layered-in entries carry the rest of the credential-state
    story the three fictional ones cannot finish alone: ``_VERIFIED_INTEGRATION``
    is the second "connected and verified", and ``_STORED_UNVERIFIED_INTEGRATION``
    is the one "stored, never checked" — both produced by the real health ledger
    rather than typed as a literal here.
    """
    ledger = HealthLedger(clock=lambda: _CAPTURED)
    ledger.record_success(_VERIFIED_INTEGRATION)
    real_entries = [
        _catalogue_integration_record(entry)
        for entry in integration_catalogue(
            health=ledger,
            configured=frozenset({_VERIFIED_INTEGRATION, _STORED_UNVERIFIED_INTEGRATION}),
        )
    ]
    for entry in real_entries:
        if entry["name"] == "redis":
            # The other half of the suggestion story ``metrics-store`` tells
            # above. That one resolves to a legible name — "a guest labelled
            # prometheus" — which is the ordinary case
            # ``suggest_integrations`` (``platform/estate/suggestions.py``)
            # produces. This one is the edge that function's own fallback
            # exists for: a resource with no display name and no matching
            # label, so the evidence sentence names the estate's raw
            # identifier instead, in the same shape that fallback produces
            # (``resource.display_name or resource.resource_id!r``). Attached
            # to a real, uninstalled catalogue entry rather than a fourth
            # fictional one, so the "one only suggested" story above stays
            # true of the hand-authored three and this is additional height,
            # the same way the eighty-plus real entries beneath them are.
            entry["suggested"] = {
                "address": "http://10.20.0.187:6379",
                "from_resource": "ct-9042",
                "because": (
                    "this estate holds a container called 'ct-9042' at "
                    "10.20.0.187, which is where redis was found rather than "
                    "where anyone guessed it would be"
                ),
                # Unresolvable on purpose — the edge ``resource_label``'s own
                # fallback exists for, matched with ``resource_kind`` to the
                # ``because`` sentence above (a container, never named).
                "resource_label": "",
                "resource_kind": "container",
            }
            break
    return (
        _record(
            "integrations",
            {},
            {
                "known_gaps": [gap.to_record() for gap in gaps()],
                "integrations": [
                    {
                        "name": "metrics-store",
                        "direction": "outbound",
                        "intake_path": "",
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
                            # Resolvable — matches the sentence above, which
                            # already names the guest by a legible label.
                            "resource_label": "prometheus",
                            "resource_kind": "guest",
                        },
                    },
                    {
                        "name": "chat",
                        "direction": "outbound",
                        "intake_path": "",
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
                        "direction": "outbound",
                        "intake_path": "",
                        "display_name": "Ticketing",
                        "category": "workflow",
                        "summary": "Opens and updates tickets from findings.",
                        # Not ``degraded`` — a stored credential the vendor
                        # itself rejects is ``failing``, the credential
                        # vocabulary's own word for it
                        # (``console/src/design/status.ts``), carrying its
                        # own critical chip rather than a warning one. It is
                        # what keeps this entry in Connected instead of
                        # falling back to the catalogue grid.
                        "health": "failing",
                        "health_detail": "the stored credential was rejected by the vendor",
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
                    *real_entries,
                ],
            },
        ),
        *_integration_docs_records(),
    )


def _integration_docs_records() -> tuple[CapturedRecord, ...]:
    """Return one record per real, installed vendor's own package documentation.

    Read the same way the gateway route reads it — the parity report's own
    resolved path, never a path composed from the vendor name — so the mock
    plane and a real deployment answer the documentation route identically.
    A vendor whose parity report resolved no docs.md path answers unreadable,
    the same distinction the real route holds between "no such vendor" (a 404
    this endpoint's declaration itself already produces for an unknown name)
    and "this deployment's own build did not carry the file".
    """
    records: list[CapturedRecord] = []
    for entry in integration_catalogue():
        docs_path = entry.parity.docs_path
        if docs_path is None:
            body: dict[str, Any] = {
                "name": entry.name,
                "display_name": entry.display_name,
                "markdown": "",
                "readable": False,
            }
        else:
            body = {
                "name": entry.name,
                "display_name": entry.display_name,
                "markdown": docs_path.read_text(encoding="utf-8"),
                "readable": True,
            }
        records.append(_record("integration-docs", {"name": entry.name}, body))
    return tuple(records)


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
        verified = onboarding.provider_id in answered
        return {
            "provider_id": onboarding.provider_id,
            "display_name": onboarding.display_name,
            "local": onboarding.local,
            "configured": present,
            "verified": verified,
            # No scenario here represents a check that failed rather than
            # never having run — a real gap in coverage, not a value
            # fabricated to fill it.
            "readiness": (
                SETUP_READINESS_VERIFIED
                if verified
                else SETUP_READINESS_CONFIGURED
                if present
                else SETUP_READINESS_ABSENT
            ),
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

    registry = default_registry()

    def capabilities(onboarding: ProviderOnboarding) -> list[dict[str, Any]]:
        """Return what the registry knows about tool calling, per model.

        Read from the same registry the route itself joins against
        (`gateway/http/routes/providers.py`'s own `_model_capabilities`), so
        the fixture cannot say something the real endpoint would not: a model
        the registry has no row for reports `None` here too, never `False`.
        """
        found = []
        for model_id in onboarding.models:
            descriptor = registry.find(onboarding.provider_id, model_id)
            found.append(
                {
                    "model_id": model_id,
                    "supports_tools": descriptor.supports_tools if descriptor is not None else None,
                }
            )
        return found

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
                    "model_capabilities": capabilities(onboarding),
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


def ingress_records(*, delivery_token_name: str = "") -> tuple[CapturedRecord, ...]:
    """Return what an operator pastes into each alert router, per source.

    Derived from the shipped profiles rather than written out, for the reason
    the signal block is: a fixture that carried its own copy of the seven
    receivers would go on describing a receiver after it was removed.

    ``delivery_token_name`` mirrors the real route's own rule
    (``gateway/http/routes/ingress.py``): the receiver block is generated —
    never assembled here by concatenation — and only for Alertmanager, and
    only once a delivery token actually exists to name in it. A scenario with
    no delivery-scoped token (``empty_records``' own call to this function)
    passes nothing, so its receiver stays exactly as silent as its token list
    is — the same contradiction the real route refuses to produce.
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
                        "receiver_yaml": (
                            alertmanager.receiver_yaml(
                                url=f"{INGRESS_BASE_URL}/webhooks/{name}",
                                token_name=delivery_token_name,
                            )
                            if name == _LIVE_SOURCE and delivery_token_name
                            else None
                        ),
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

#: How much of the week's ingress ``counts`` actually landed, for the two
#: sources that have any: the accepted total for the live one, the rejected
#: total for the refusing one. A wider window than ``counts`` in principle,
#: but this dataset invents no activity older than what ``counts`` already
#: states, so the two agree here rather than one silently exceeding the other.
_WEEK_COUNT: Final[dict[str, int]] = {_LIVE_SOURCE: 14, _REFUSING_SOURCE: 6}

#: Must match the delivery-scoped token's own name in the ``tokens`` record
#: below (``tok-0003``) — the receiver block names the credential an operator
#: actually has to find in Machine tokens, not a name invented here. Scenarios
#: built without that token (``empty_records``' own call to ``ingress_records``)
#: pass nothing instead of borrowing this name.
_DELIVERY_TOKEN_NAME: Final = "Alert delivery"


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
            "week_count": _WEEK_COUNT.get(name, 0),
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
                    },
                    # A destination declared for a channel this deployment has
                    # not wired — the one other way `unconfigurable_reason`
                    # comes back non-empty (`platform/delivery/destinations.py`),
                    # distinct from the "nothing at all can deliver" case
                    # `empty_transit_records` below covers. The wording mirrors
                    # what that module actually produces, so a screen reading
                    # this fixture is reading the same sentence the gateway
                    # would compose.
                    {
                        "destination_id": "oncall-teams",
                        "channel": "microsoft_teams",
                        "events": ["approval_pending", "source_degraded"],
                        "detail": "summary_with_link",
                        "enabled": True,
                        "masking_policy": "standard",
                        "unconfigurable_reason": (
                            "No configured channel carries 'microsoft_teams'. "
                            "This deployment delivers over slack."
                        ),
                    },
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


def overview_record(*, populated: bool) -> CapturedRecord:
    """Return the Painel's five KPI tiles: bare on an empty deployment, real numbers otherwise.

    Not derived from the other populated records' own counts -- a follow-up
    that ties this to the same simulated cluster `estate()` projects from
    would remove that gap; until then this is a self-consistent but
    independently-declared set of numbers, valid against the response
    schema and enough for kpi-tiles.tsx to render against.
    """
    if not populated:
        empty_kpi = {"value": None, "breakdown": {}, "series": [], "note": ""}
        return _record(
            "overview",
            {},
            {
                "captured_at": at(),
                "watched": {**empty_kpi, "value": 0},
                "degraded": {**empty_kpi, "value": 0, "note": "no_detector_enabled"},
                "self_resolved": dict(empty_kpi),
                "success_rate": dict(empty_kpi),
                "time_to_cause": dict(empty_kpi),
            },
        )

    def series(values: list[float]) -> list[dict[str, object]]:
        return [
            {"date": at(days=-(len(values) - 1 - index)).split("T")[0], "value": value}
            for index, value in enumerate(values)
        ]

    return _record(
        "overview",
        {},
        {
            "captured_at": at(),
            "watched": {
                "value": 99,
                "breakdown": {"container": 68, "datastore": 21, "node": 2},
                "series": series([84.0, 88.0, 91.0, 95.0, 99.0]),
                "note": "",
            },
            "degraded": {
                "value": 14,
                "breakdown": {},
                "series": series([10.0, 11.0, 9.0, 13.0, 14.0]),
                "note": "",
            },
            "self_resolved": {
                "value": 100.0,
                "breakdown": {"self_resolved": 45.0, "total": 45.0},
                "series": series([100.0, 100.0, 96.0, 100.0, 100.0]),
                "note": "",
            },
            "success_rate": {
                "value": 100.0,
                "breakdown": {"succeeded": 48.0, "total": 48.0},
                "series": series([97.0, 98.0, 100.0, 100.0, 100.0]),
                "note": "",
            },
            "time_to_cause": {
                "value": 75.0,
                "breakdown": {"median_seconds": 75.0, "worst_seconds": 190.0},
                "series": series([80.0, 78.0, 70.0, 72.0, 75.0]),
                "note": "",
            },
        },
    )


def local_administrator_record(*, unclaimed: bool = False) -> CapturedRecord:
    """Return the ternary fact the sign-in and first-run screens read.

    Mirrors the gateway's own ``LocalAdministratorAvailabilityView``:
    ``unclaimed`` for a deployment nobody has opened local sign-in on yet
    (with the CLI invitation attached, the same constant the boot
    announcement prints), ``administered`` for one that already has an
    owner — from the environment or a deliberate enrolment, this dataset
    does not distinguish which. No scenario this module builds configures
    an identity provider, so the gateway's third state is never returned
    here.
    """
    if unclaimed:
        return _record(
            "local-administrator",
            {},
            {"state": "unclaimed", "command": LOCAL_ADMIN_SETUP_COMMAND},
        )
    return _record("local-administrator", {}, {"state": "administered", "command": ""})


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
        # This deployment already has an owner — the whole rest of this
        # dataset is one operating mid-flight, and only `first_run_records`
        # patches this back to `unclaimed`.
        local_administrator_record(),
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
    {
        "user_id": FORMER,
        "display_name": "Jordan Vance",
        "email": "jordan.vance@example.invalid",
        "kind": "user",
        "is_active": False,
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
        # Mirrors what apr-0001 itself declares above, not a second opinion.
        "detail": {"side_effect_level": SIDE_EFFECT_WRITE_REVERSIBLE},
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
        # Not configured at all — every field genuinely empty, nothing tested,
        # nothing active. `restricted_records` never returns this record (it
        # takes only "principal" from a viewer's own `identity_records`), so
        # this is the one place this state lives, and it is the state the
        # single-sign-on screen's own suite needs: a virgin form must draw with
        # no error and no accusation, which only holds if the deployment it is
        # reading really has nothing set yet. The eight required fields below
        # mirror `SSO_FIELDS` (`console/src/surfaces/sso-fields.ts`) — the same
        # eight the deployment's own validation names as missing.
        _record(
            "sso",
            {},
            {
                "provider": "",
                "issuer": "",
                "client_id": "",
                "authorisation_endpoint": "",
                "token_endpoint": "",
                "jwks_uri": "",
                "redirect_uri": "",
                "scopes": [],
                "claims": {"subject": "", "email": "", "display_name": "", "groups": ""},
                "group_to_node": {},
                "default_node_id": "",
                "is_active": False,
                "verified": False,
                "problems": [
                    "provider is required",
                    "issuer is required",
                    "client_id is required",
                    "authorisation_endpoint is required",
                    "token_endpoint is required",
                    "jwks_uri is required",
                    "redirect_uri is required",
                    "default_node_id is required",
                ],
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
                        # The console's own predicate for "this is a browser
                        # sign-in, not a machine token" is an exact match on
                        # this name (`CONSOLE_SESSION_NAME`,
                        # `console/src/surfaces/token-identity.ts`) — not on
                        # `description`, which is prose nobody parses. A name
                        # that does not match it is read as an ordinary
                        # machine token: it lists on the Machine tokens
                        # screen instead of the Active sessions panel it
                        # actually belongs to.
                        "name": "Console sign-in",
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
                    {
                        # The one token this deployment's webhook route
                        # actually accepts: every token above holds an
                        # investigation or token-management scope, and none
                        # of them authenticates a POST to
                        # ``/webhooks/alertmanager``. Named the way the
                        # console's own alert-delivery issuance template
                        # names the purpose
                        # (``settings.machineTokens.template.alertDelivery.name``),
                        # scoped to nothing beyond delivery, and last used at
                        # the instant the one accepted delivery
                        # (``_TRANSIT_ACCEPTED_AT`` below) actually arrived —
                        # the same token, not a coincidence of timing.
                        "token_id": "tok-0003",
                        "name": "Alert delivery",
                        "user_id": AUTOMATION,
                        "team_node_id": PLATFORM_TEAM_NODE,
                        "scopes": [Permission.WEBHOOK_DELIVER.value],
                        "created_at": at(days=6, hours=4),
                        "expires_at": None,
                        "last_used_at": at(minutes=12),
                        "revoked": False,
                        "description": "Authenticates inbound Alertmanager webhook deliveries.",
                    },
                    *_bootstrap_tokens(),
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
                        "side_effect_level": SIDE_EFFECT_WRITE_REVERSIBLE,
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


def served_records(
    *, role: str = "owner", incident_by_run: Mapping[str, str] | None = None
) -> tuple[CapturedRecord, ...]:
    """Return every record the gateway half of the dataset holds."""
    return (
        *agent_records(),
        *runs_records(incident_by_run=incident_by_run),
        *interaction_records(),
        *proposal_records(),
        *memory_records(),
        *topology_records(),
        *config_records(),
        *integration_records(),
        *identity_records(role=role),
        *role_records(),
        *platform_records(),
        *ingress_records(delivery_token_name=_DELIVERY_TOKEN_NAME),
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
    "local_administrator_record",
    "proposal_records",
    "memory_records",
    "platform_records",
    "provider_records",
    "runs_records",
    "served_records",
    "setup_records",
    "topology_records",
]
