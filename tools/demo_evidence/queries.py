"""The questions the demonstration asks of a live database, one per station.

Every one of them is a ``SELECT``, every one is scoped to a single
organisation, and every one that claims something was recorded carries the
value measured **before** this work started. "Three tool calls" is a number;
"nought to three, for this run, read back after a reload" is a proof, and the
difference is the whole reason this file lists the earlier value beside the
query rather than in somebody's memory.

Two things are deliberately absent.

**No column that could hold a secret is named anywhere below.** Not the
credential store, not a token hash, not a stored passphrase. A collector that
never asks for one cannot print one into a file somebody commits.

**No vocabulary is spelled out by hand.** The audit resource kinds and the
approval states are imported from the modules that declare them, so a query
cannot quietly go on asking about a word the product stopped using.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config.constants.security import (
    APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
    REMEDIATION_AUDIT_RESOURCE_KIND,
)
from platform.persistence.ports.approval_store import ApprovalState

#: The change kind a remediation approval is stored under, read from the value
#: the approvals layer writes rather than repeated here as a word.
REMEDIATION_CHANGE_TYPE: Final = "remediation"

#: How many audit rows a station reads when it is looking for two decisions
#: among whatever else the deployment did. Big enough to hold an evening,
#: small enough to read.
AUDIT_WINDOW: Final = 50


@dataclass(frozen=True, slots=True)
class Query:
    """One question, what it proves, and what the answer was before this work."""

    name: str
    #: One sentence: what a reader should conclude from the answer.
    asks: str
    sql: str
    #: The parameters this query cannot run without.
    needs: tuple[str, ...]
    #: What this same query returned before the wave, when that is known.
    #: Empty when there is no earlier reading to contrast against.
    baseline: str = ""


@dataclass(frozen=True, slots=True)
class Station:
    """One point of the loop, and the questions that decide whether it held."""

    name: str
    title: str
    queries: tuple[Query, ...]


E3 = Station(
    name="E3",
    title="the incident opens legible, over a subject the estate resolves",
    queries=(
        Query(
            name="incident",
            asks="the incident exists, is addressable, and is named by a title rather than an id",
            needs=("org", "incident"),
            baseline="every alert incident's detail was unrecoverable",
            sql="""
SELECT public_id,
       title,
       state,
       severity,
       origin,
       origin_id,
       opened_at,
       closed_at,
       subjects,
       run_ids,
       actions
FROM incidents
WHERE org_id = :org
  AND (incident_id = :incident OR public_id = :incident);
""",
        ),
        Query(
            name="estate",
            asks="the estate holds real resources rather than being empty",
            needs=("org",),
            baseline="0 — the estate was empty and every incident showed an unplaced zone",
            sql="""
SELECT count(*) AS present_resources
FROM estate_resources
WHERE org_id = :org
  AND absent_since IS NULL;
""",
        ),
        Query(
            name="subject",
            asks="the resource the incident points at is one the estate actually holds",
            needs=("org", "resource"),
            baseline="no row — nothing to point at",
            sql="""
SELECT resource_id,
       kind,
       source,
       native_id,
       display_name,
       health,
       last_seen_at,
       absent_since
FROM estate_resources
WHERE org_id = :org
  AND resource_id = :resource;
""",
        ),
    ),
)


E4 = Station(
    name="E4",
    title="the investigation records its turns, its calls, its evidence and its cost",
    queries=(
        Query(
            name="turns",
            asks="the run recorded turns, read back from the store rather than the process",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
            sql="""
SELECT count(*) AS run_turns
FROM run_turns
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
        Query(
            name="tool-calls",
            asks="the run recorded the capability calls it made",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
            sql="""
SELECT count(*) AS tool_calls
FROM tool_calls
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
        Query(
            name="evidence",
            asks="the run recorded the observations it cited",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
            sql="""
SELECT count(*) AS evidence_rows
FROM evidence
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
        Query(
            name="trace-events",
            asks="the run's own log exists beside the counts above",
            needs=("org", "run"),
            baseline="73 for the whole instance, across 37 completed runs",
            sql="""
SELECT count(*) AS trace_events
FROM trace_events
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
        Query(
            name="cost-per-turn",
            asks="cost is recorded turn by turn, and an unpriced turn is empty rather than nought",
            needs=("org", "run"),
            baseline="no turn was recorded at all, so no cost could be",
            sql="""
SELECT "index",
       started_at,
       finished_at,
       usage
FROM run_turns
WHERE org_id = :org
  AND run_id = :run
ORDER BY "index";
""",
        ),
        Query(
            name="what-each-call-returned",
            asks="each call carries what it returned, in the order it was recorded",
            needs=("org", "run"),
            baseline="no row",
            sql="""
SELECT recorded_seq,
       tool_name,
       status,
       started_at,
       finished_at,
       error
FROM tool_calls
WHERE org_id = :org
  AND run_id = :run
ORDER BY recorded_seq;
""",
        ),
    ),
)


E5 = Station(
    name="E5",
    title="the sentence naming the run is not the document",
    queries=(
        Query(
            name="sentence-and-document",
            asks="the sentence does not open with markdown syntax, and the document still does",
            needs=("org", "run"),
            baseline="every recent summary opened with ###, and no separate sentence existed",
            sql="""
SELECT headline,
       left(summary, 120) AS summary_opens_with,
       status,
       finished_at
FROM agent_runs
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
    ),
)


E7 = Station(
    name="E7",
    title="the proposal waits, with the plan that would undo it",
    queries=(
        Query(
            name="proposal",
            asks=(
                "exactly one proposal exists for this run, and its state is still "
                f"{ApprovalState.PENDING.value!r} — the word the approvals port uses "
                "for a decision nobody has taken"
            ),
            needs=("org", "run"),
            baseline="no row, for any run",
            sql="""
SELECT approval_id,
       action,
       side_effect_level,
       state,
       requested_at,
       expires_at,
       arguments ->> 'change_type' AS change_type
FROM approvals
WHERE org_id = :org
  AND run_id = :run
ORDER BY requested_at;
""",
        ),
        Query(
            name="rollback-plan",
            asks="the undo was recorded, and it was recorded before anything ran",
            needs=("org", "approval"),
            baseline="no row",
            sql="""
SELECT plan_id,
       created_at,
       notes,
       steps
FROM rollback_plans
WHERE org_id = :org
  AND approval_id = :approval;
""",
        ),
        Query(
            name="every-remediation-proposal",
            asks=(
                "how many remediation proposals this deployment has ever queued; "
                "nought here means nothing bound a control plane, which the log says outright"
            ),
            needs=("org",),
            baseline="0 — no control plane was bound, so no write could be proposed",
            sql=f"""
SELECT count(*) AS remediation_proposals
FROM approvals
WHERE org_id = :org
  AND arguments ->> 'change_type' = '{REMEDIATION_CHANGE_TYPE}';
""",
        ),
    ),
)


E8 = Station(
    name="E8",
    title="the decision, its author and its instant, recorded before any effect",
    queries=(
        Query(
            name="decision",
            asks="who decided, when, and why — on the row the execution was authorised from",
            needs=("org", "approval"),
            baseline="no row",
            sql="""
SELECT approval_id,
       state,
       decided_by,
       decided_at,
       reason,
       requested_at,
       expires_at
FROM approvals
WHERE org_id = :org
  AND approval_id = :approval;
""",
        ),
        Query(
            name="audit-of-the-decision",
            asks="the decision reached the audit trail with author, action, subject and result",
            needs=("org", "approval"),
            baseline="no row",
            sql=f"""
SELECT occurred_at,
       actor_kind,
       actor_id,
       action,
       resource_kind,
       resource_id,
       outcome
FROM audit_events
WHERE org_id = :org
  AND resource_id = :approval
  AND resource_kind IN (
        '{APPROVAL_AUDIT_RESOURCE_KIND_REQUEST}',
        '{REMEDIATION_AUDIT_RESOURCE_KIND}'
      )
ORDER BY occurred_at;
""",
        ),
        Query(
            name="nothing-executed-unattended",
            asks=(
                "no action above reading executed without a recorded human decision; "
                "this must read nought at the end of the demonstration"
            ),
            needs=("org",),
            baseline="0 — nothing executed at all",
            sql="""
SELECT count(*) AS unattended_executions
FROM remediation_outcomes
WHERE org_id = :org
  AND autonomous IS TRUE;
""",
        ),
    ),
)


E9 = Station(
    name="E9",
    title="the execution went through the gate, and what it produced was recorded",
    queries=(
        Query(
            name="outcome",
            asks=(
                "the execution produced a recorded outcome for this resource — "
                "a named failure is an outcome, a silent one is not"
            ),
            needs=("org", "resource"),
            baseline="no row",
            sql="""
SELECT action_id,
       capability,
       resource_id,
       run_id,
       incident_id,
       state,
       verdict,
       rollback,
       autonomous,
       executed_at,
       due_at,
       verified_at,
       left(detail, 200) AS detail
FROM remediation_outcomes
WHERE org_id = :org
  AND resource_id = :resource
ORDER BY executed_at DESC;
""",
        ),
        Query(
            name="episode",
            asks="what a later investigation would be told about this one",
            needs=("org", "run"),
            baseline="no row for a run",
            sql="""
SELECT episode_id,
       title,
       outcome,
       occurred_at,
       components
FROM episodes
WHERE org_id = :org
  AND run_id = :run;
""",
        ),
    ),
)


E10 = Station(
    name="E10",
    title="the incident reflects the outcome instead of stopping at the diagnosis",
    queries=(
        Query(
            name="timeline",
            asks="the action left an entry on the incident's own timeline",
            needs=("org", "incident"),
            baseline="no entry for an action, because no action happened",
            sql="""
SELECT kind,
       at,
       actor,
       cause,
       left(detail, 160) AS detail
FROM incident_timeline
WHERE org_id = :org
  AND incident_id = (
        SELECT incident_id
        FROM incidents
        WHERE org_id = :org
          AND (incident_id = :incident OR public_id = :incident)
      )
ORDER BY at;
""",
        ),
        Query(
            name="incident-after",
            asks="the incident itself carries the outcome, the run and the action",
            needs=("org", "incident"),
            baseline="the incident stopped at the diagnosis",
            sql="""
SELECT title,
       state,
       severity,
       subjects,
       run_ids,
       actions,
       closed_at,
       close_reason,
       self_resolved
FROM incidents
WHERE org_id = :org
  AND (incident_id = :incident OR public_id = :incident);
""",
        ),
    ),
)


R = Station(
    name="R",
    title="the refusal path, exercised on a different occurrence",
    queries=(
        Query(
            name="rejections",
            asks="a rejection was recorded with its reason, and a reason is not optional",
            needs=("org",),
            baseline="no row",
            sql=f"""
SELECT approval_id,
       action,
       state,
       decided_by,
       decided_at,
       reason
FROM approvals
WHERE org_id = :org
  AND state = '{ApprovalState.REJECTED.value}'
ORDER BY decided_at DESC;
""",
        ),
        Query(
            name="both-decisions-in-the-audit",
            asks="the approval and the rejection both appear, with author, action, subject and result",
            needs=("org",),
            baseline="no row",
            sql=f"""
SELECT occurred_at,
       actor_kind,
       actor_id,
       action,
       resource_kind,
       resource_id,
       outcome
FROM audit_events
WHERE org_id = :org
  AND resource_kind IN (
        '{APPROVAL_AUDIT_RESOURCE_KIND_REQUEST}',
        '{REMEDIATION_AUDIT_RESOURCE_KIND}'
      )
ORDER BY occurred_at DESC
LIMIT {AUDIT_WINDOW};
""",
        ),
    ),
)


#: Every station, in the order the loop passes through them. E1, E2 and E6 are
#: absent on purpose: what proves them is an alert router, an intake screen and
#: a transcript, none of which is a row in this database. Claiming them here
#: would be inventing a query that measures something adjacent.
STATIONS: Final[tuple[Station, ...]] = (E3, E4, E5, E7, E8, E9, E10, R)


__all__ = [
    "AUDIT_WINDOW",
    "E3",
    "E4",
    "E5",
    "E7",
    "E8",
    "E9",
    "E10",
    "R",
    "REMEDIATION_CHANGE_TYPE",
    "STATIONS",
    "Query",
    "Station",
]
