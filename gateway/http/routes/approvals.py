"""Approvals as a reviewer has to see them, the decision, and the rollback.

An approval card that shows only "restart checkout?" is a card nobody can
answer. Article III's requirement is that a change above read carries a stored
rollback plan *before* it can be approved, so the plan already exists by the
time anybody is looking — and returning it with the request is what turns the
decision from a guess into a review.

Deciding is the one write here that is not the rollback. It calls
``ApprovalStore.decide`` directly rather than routing through the governance
``ApprovalService`` or the agent ``ProposalQueue``: both exist for a different
shape of change (a configuration edit, a detector, a knowledge write, a
prompt), and neither claims a remediation approval as one of its own.

**An approved remediation is then carried out, through the gate.** Not from
here: this hands the action the request stored to
``RemediationGate.execute_approved``, which re-reads the emergency stop and the
closed loop's guards and descends the same execution path a proposal raised
inside a run would. Calling the executor from a route would be a second
entrance to a production write, and the whole design rests on there being one.

The order matters and it is the one that survives a crash between the halves.
The decision is recorded first: a stored approval that did not run is something
an operator finds and re-runs, while a change applied with nothing saying who
authorised it is indistinguishable from a compromise.

A deployment that composed no remediation desk records the decision and carries
nothing, which is the honest behaviour for a deployment that cannot act rather
than one that decided not to.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from config.constants.closed_loop import REMEDIATION_PAYLOAD_EFFECTIVENESS
from config.constants.security import (
    APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
    REMEDIATION_PAYLOAD_BLAST_RADIUS,
    REMEDIATION_PAYLOAD_EVIDENCE,
    REMEDIATION_PAYLOAD_ROLLBACK,
    REMEDIATION_PAYLOAD_STEPS,
    REMEDIATION_PAYLOAD_WAIVER,
)
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, conflict, not_found, unprocessable
from gateway.http.state import GatewayState
from platform.approvals.models import PROPOSED_KEY, ChangeType
from platform.identity.audit.recorder import (
    APPROVAL_AUDIT_ACTION_DECIDE,
    AuditContext,
    AuditRecorder,
)
from platform.incidents.errors import UnknownIncident
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observability.logging import get_logger
from platform.persistence.errors import AppendOnlyViolation, PersistenceError, RecordNotFound
from platform.persistence.ports import ActorKind, AuditOutcome
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
)
from platform.persistence.ports.transaction import TenantScope, UnitOfWork
from platform.remediation.errors import RemediationError
from platform.remediation.gating import RunContext
from platform.remediation.models import RemediationAction

logger = get_logger(__name__)

#: The risk score's own scale — five segments, always. Named rather than
#: spelled `5` at both call sites (the derivation and the response model),
#: because a scale that only one of the two remembered to update is a card
#: whose gauge draws more segments than the number it labels them with.
_RISK_SCALE = 5

#: Base score by side-effect level, before the blast-radius adjustment
#: (plan, Decisions §3). A level this deployment does not recognise floors at
#: the reversible-write score rather than raising — a document from a future
#: capability is a reason to still show a number, never a reason to fail the
#: whole card.
_RISK_BASE_BY_LEVEL: Mapping[str, int] = {
    "read": 1,
    "read_sensitive": 1,
    "write_reversible": 2,
    "write_irreversible": 4,
    "destructive": 5,
}

#: Capabilities this deployment knows a human verb for. A capability outside
#: this table is not guessed at — the title falls back to the stored
#: `summary`, per FR-003: "nunca capability cru, nunca id".
_CAPABILITY_VERBS: Mapping[str, str] = {
    "proxmox_start_guest": "Start the guest",
    "proxmox_shutdown_guest": "Shut down the guest",
    "proxmox_restart_guest": "Restart the guest",
    "estate.enable_backup_job": "Enable the backup job",
    "estate.disable_backup_job": "Disable the backup job",
    "estate.expand_volume": "Expand the volume",
    "scale_workload": "Scale the workload",
}

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])

#: A verdict this route recognises. Anything else is refused before a store is
#: ever asked.
_VERDICTS = frozenset({"approve", "reject"})

#: Where a reproposed pending request's link to the expired one it came from
#: lives — a key inside the existing `arguments` JSON, never a new column
#: (the store's `state` is an unconstrained `String(32)` and `arguments` is
#: already JSONB, so this needs no migration). Read by `repropose_approval`'s
#: own idempotency check; nothing else reads it.
_ORIGIN_APPROVAL_ID_KEY = "origin_approval_id"


class RollbackStepView(BaseModel):
    ordinal: int
    description: str
    capability: str
    arguments: dict[str, Any]


class RollbackPlanView(BaseModel):
    plan_id: str
    approval_id: str
    steps: list[RollbackStepView]
    notes: str | None = None


class ActionStepView(BaseModel):
    """One numbered sentence — either what the action does or how it undoes it."""

    ordinal: int
    summary: str
    #: Detail typography, per the card (FR-009) — never the section's title.
    capability: str


class EvidenceItemView(BaseModel):
    summary: str
    #: The raw `source:kind:id`-shaped reference the document carries.
    #: Never empty when the item exists — an evidence entry with nothing to
    #: point at is not evidence.
    reference: str


class RiskView(BaseModel):
    #: Constructed and read as ``risk_class`` in Python (``class`` is a
    #: keyword); served as ``class``, per the plan's own field name —
    #: ``populate_by_name`` is what lets both spellings work.
    risk_class: str = Field(alias="class")
    score: int
    scale: int

    model_config = {"populate_by_name": True}


class BlastRadiusFieldView(BaseModel):
    count: int | None = None
    depth: int | None = None
    known: bool = False


class AutonomyView(BaseModel):
    side_effect_level: str
    reversible: bool
    #: Always ``True`` for a remediation approval today — propose-only means
    #: every approval this route serves sits in the queue. Served rather than
    #: hard-coded on the console so a future write path that skips the queue
    #: does not silently start lying about this line.
    queued: bool = True


class PriorEffectivenessView(BaseModel):
    #: One sentence, or `""` when nothing here has a history yet. Never a
    #: structure the console would have to phrase itself — two surfaces
    #: phrasing "worked 2 of 3 times" independently is how they drift.
    summary: str = ""


class OriginView(BaseModel):
    run_id: str = ""
    #: The incident's own title when one is attached, else the run's
    #: headline, else `""`. Never an identifier standing in for a name.
    headline: str = ""
    incident_id: str = ""


class ApprovalView(BaseModel):
    approval_id: str
    run_id: str
    action: str
    side_effect_level: str
    summary: str
    requested_at: str
    expires_at: str
    state: str
    arguments: dict[str, Any]
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None
    #: ``None`` rather than an omitted field: "there is no plan" is information a
    #: reviewer needs, and a missing key reads as "not loaded".
    rollback_plan: RollbackPlanView | None = None
    #: How many resources the *action* itself would reach, from the topology
    #: graph — not how many subjects the incident carries, which is a different
    #: number answering a different question. ``None`` when nothing computed
    #: one for this request, which today is every request: never a fabricated
    #: count standing in for a real one.
    blast_radius_count: int | None = None

    # --- The decision-by-field shape ------------------------------------------
    #
    # Everything below is additive: `incident-detail.tsx` (060-telas-de-area)
    # already reads `approval_id`/`state`/`summary`/`blast_radius_count` above
    # and nothing here changes what those mean or how they are shaped.

    #: A human sentence naming the action and its target, derived once on the
    #: server (`_title_of`) and identical between the listing and the detail.
    #: Never the raw capability, never a bare identifier (FR-003).
    title: str = ""
    requester: str = ""
    origin: OriginView = Field(default_factory=OriginView)
    #: `"remediation"` for everything this route serves today — carried as a
    #: field rather than assumed, because the card's meta-line names it and a
    #: literal in the console would be the console deciding a taxonomy fact.
    category: str = "remediation"
    intent: str = ""
    risk: RiskView
    steps: list[ActionStepView] = Field(default_factory=list)
    rollback: list[ActionStepView] = Field(default_factory=list)
    evidence: list[EvidenceItemView] = Field(default_factory=list)
    blast_radius: BlastRadiusFieldView = Field(default_factory=BlastRadiusFieldView)
    autonomy: AutonomyView
    prior_effectiveness: PriorEffectivenessView = Field(default_factory=PriorEffectivenessView)
    created_at: str = ""
    verdict: str | None = None
    #: The full stored document, verbatim — the one field the raw-payload
    #: `<details>` renders (FR-004). Present on both the listing and the
    #: detail: a reviewer expanding a collapsed row in a crowded queue should
    #: not have to open the detail first.
    raw: dict[str, Any] = Field(default_factory=dict)


class ApprovalList(BaseModel):
    approvals: list[ApprovalView]


class ReproposeResult(BaseModel):
    approval_id: str
    state: str
    created_at: str


class RollbackResult(BaseModel):
    plan_id: str
    approval_id: str
    executed_at: str
    completed_steps: list[int]


class ApprovalDecisionRequest(BaseModel):
    verdict: str
    #: Required to reject, ignored on an approval — the same rule the
    #: proposal queue's own decision route enforces, restated here because
    #: this route calls a different store method and cannot inherit the check.
    reason: str = Field(default="")


class ApprovalDecisionResult(BaseModel):
    approval_id: str
    state: str
    decided_at: str
    decided_by: str


def _blast_radius_count(arguments: Mapping[str, Any]) -> int | None:
    """Return the action's own blast-radius count, when the request carries one.

    A remediation queued through the approval service nests its payload under
    ``proposed`` (``platform.approvals.models.PendingChange.to_arguments``); a
    request written directly carries it flat. Both are read so a caller does
    not have to know which one produced this row. ``None`` — never a
    fabricated zero — when neither shape names a count.
    """
    proposed = arguments.get(PROPOSED_KEY)
    nested = (
        proposed.get(REMEDIATION_PAYLOAD_BLAST_RADIUS) if isinstance(proposed, Mapping) else None
    )
    flat = arguments.get(REMEDIATION_PAYLOAD_BLAST_RADIUS)
    radius = (
        nested if isinstance(nested, Mapping) else (flat if isinstance(flat, Mapping) else None)
    )
    if radius is None:
        return None
    count = radius.get("count")
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def _plan_view(plan: RollbackPlan | None) -> RollbackPlanView | None:
    if plan is None:
        return None
    return RollbackPlanView(
        plan_id=plan.plan_id,
        approval_id=plan.approval_id,
        steps=[
            RollbackStepView(
                ordinal=step.ordinal,
                description=step.description,
                capability=step.capability,
                arguments=dict(step.arguments),
            )
            for step in plan.steps
        ],
        notes=plan.notes,
    )


# --- The decision-by-field derivations ----------------------------------------
#
# Every one reads `request.arguments` alone (never a second lookup, per the
# plan's performance goal) and degrades to a declared absence rather than
# raising — a document from before this feature, or one a capability wrote
# by hand, must still render a card.


def _proposed_of(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the action's own document, nested or flat (`_blast_radius_count`'s rule).

    A remediation queued through `RequestBuilder.queue()` nests it under
    `proposed`; a request written directly carries the same keys flat. Both
    are read the same way so nothing here has to know which produced a row.
    """
    proposed = arguments.get(PROPOSED_KEY)
    if isinstance(proposed, Mapping):
        return proposed
    return arguments


def _title_of(arguments: Mapping[str, Any], *, fallback: str) -> str:
    """Return the human sentence naming this decision, or `fallback`.

    One function, called from both the listing and the detail projection, so
    the two can never disagree about the same approval's title.
    """
    payload = _proposed_of(arguments)
    capability = payload.get("capability")
    if not isinstance(capability, str) or capability == "":
        return fallback
    verb = _CAPABILITY_VERBS.get(capability)
    if verb is None:
        return fallback
    target = payload.get("target")
    identifier = target.get("identifier") if isinstance(target, Mapping) else None
    node = target.get("node_id") if isinstance(target, Mapping) else None
    if not isinstance(identifier, str) or identifier == "":
        return verb
    where = f"{identifier} on {node}" if isinstance(node, str) and node != "" else identifier
    return f"{verb} {where}"


def _risk_of(arguments: Mapping[str, Any], *, fallback_class: str) -> RiskView:
    """Return the risk gauge: a deterministic score out of `_RISK_SCALE`.

    Base by side-effect level, `+1` when the blast radius is wide (more than
    one resource, or deeper than two hops), capped at the scale — the table
    the plan fixes, reproduced here as the one place it is computed.
    """
    payload = _proposed_of(arguments)
    level = payload.get("side_effect_level")
    base = (
        _RISK_BASE_BY_LEVEL.get(level, _RISK_BASE_BY_LEVEL["write_reversible"])
        if isinstance(level, str)
        else _RISK_BASE_BY_LEVEL["write_reversible"]
    )

    radius = payload.get(REMEDIATION_PAYLOAD_BLAST_RADIUS)
    wide = False
    if isinstance(radius, Mapping):
        count = radius.get("count")
        depth = radius.get("depth")
        wide = (isinstance(count, int) and count > 1) or (isinstance(depth, int) and depth > 2)

    score = min(_RISK_SCALE, base + (1 if wide else 0))
    risk_class = payload.get("risk_class")
    return RiskView(
        risk_class=risk_class
        if isinstance(risk_class, str) and risk_class != ""
        else fallback_class,
        score=score,
        scale=_RISK_SCALE,
    )


def _steps_of(arguments: Mapping[str, Any], *, summary_fallback: str) -> list[ActionStepView]:
    """Return the numbered sentences describing what the action itself does.

    Falls back to the stored `summary` as a single step when the document
    names none — the edge case where `steps` is empty and `summary` is
    present must not read as an empty section beside a full payload.
    """
    payload = _proposed_of(arguments)
    raw = payload.get(REMEDIATION_PAYLOAD_STEPS)
    entries = (
        [entry for entry in raw if isinstance(entry, Mapping)] if isinstance(raw, list) else []
    )
    if not entries:
        if summary_fallback == "":
            return []
        return [ActionStepView(ordinal=1, summary=summary_fallback, capability="")]
    return [
        ActionStepView(
            ordinal=index + 1,
            summary=str(entry.get("description", "")),
            capability=str(entry.get("capability", "")),
        )
        for index, entry in enumerate(entries)
    ]


def _rollback_of(arguments: Mapping[str, Any]) -> list[ActionStepView]:
    """Return the numbered sentences describing how the action is undone.

    Read from the stored rollback plan's own record (`rollback_waiver`,
    `RollbackPlan.to_record`), which carries real ordinals — the flatter
    `rollback` list `remediation_payload` also writes does not.
    """
    payload = _proposed_of(arguments)
    waiver = payload.get(REMEDIATION_PAYLOAD_WAIVER)
    steps = waiver.get(REMEDIATION_PAYLOAD_STEPS) if isinstance(waiver, Mapping) else None
    if isinstance(steps, list) and steps:
        return [
            ActionStepView(
                ordinal=int(step.get("ordinal", index + 1)),
                summary=str(step.get("description", "")),
                capability=str(step.get("capability", "")),
            )
            for index, step in enumerate(steps)
            if isinstance(step, Mapping)
        ]
    # No plan record at all (a document from before this feature, or written
    # directly) — the flatter list is the fallback, ordinals assigned here.
    flat = payload.get(REMEDIATION_PAYLOAD_ROLLBACK)
    if not isinstance(flat, list):
        return []
    return [
        ActionStepView(
            ordinal=index + 1,
            summary=str(entry.get("description", "")),
            capability=str(entry.get("capability", "")),
        )
        for index, entry in enumerate(flat)
        if isinstance(entry, Mapping)
    ]


def _reversible_of(arguments: Mapping[str, Any], *, fallback: bool) -> bool:
    """Return whether the stored plan says this action can be undone."""
    payload = _proposed_of(arguments)
    waiver = payload.get(REMEDIATION_PAYLOAD_WAIVER)
    if isinstance(waiver, Mapping) and isinstance(waiver.get("reversible"), bool):
        return bool(waiver["reversible"])
    return fallback


def _evidence_of(arguments: Mapping[str, Any]) -> list[EvidenceItemView]:
    """Return the evidence items the document names, each with its reference."""
    payload = _proposed_of(arguments)
    raw = payload.get(REMEDIATION_PAYLOAD_EVIDENCE)
    if not isinstance(raw, list):
        return []
    return [
        EvidenceItemView(
            summary=str(item.get("summary", "")), reference=str(item.get("reference", ""))
        )
        for item in raw
        if isinstance(item, Mapping) and str(item.get("reference", "")) != ""
    ]


def _blast_radius_field_of(arguments: Mapping[str, Any]) -> BlastRadiusFieldView:
    """Return the structured blast radius `{count, depth, known}`."""
    payload = _proposed_of(arguments)
    radius = payload.get(REMEDIATION_PAYLOAD_BLAST_RADIUS)
    if not isinstance(radius, Mapping):
        return BlastRadiusFieldView(known=False)
    count = radius.get("count")
    depth = radius.get("depth")
    return BlastRadiusFieldView(
        count=count if isinstance(count, int) and not isinstance(count, bool) else None,
        depth=depth if isinstance(depth, int) and not isinstance(depth, bool) else None,
        known=radius.get("known") is True,
    )


def _prior_effectiveness_of(arguments: Mapping[str, Any]) -> PriorEffectivenessView:
    """Return one sentence summarising what has happened here before, or none."""
    payload = _proposed_of(arguments)
    record = payload.get(REMEDIATION_PAYLOAD_EFFECTIVENESS)
    if not isinstance(record, Mapping):
        return PriorEffectivenessView(summary="")
    total = record.get("total")
    if not isinstance(total, int) or total == 0:
        return PriorEffectivenessView(summary="")
    verified = record.get("verified")
    if not isinstance(verified, int) or verified == 0:
        return PriorEffectivenessView(
            summary=f"Tried {total} time(s) here; none has finished settling yet."
        )
    counts = record.get("counts")
    effective = counts.get("effective", 0) if isinstance(counts, Mapping) else 0
    return PriorEffectivenessView(
        summary=f"Verified {verified} time(s) here; worked {effective} of them."
    )


async def _origin_of(uow: UnitOfWork, request: ApprovalRequest) -> OriginView:
    """Return the run and, when one is attached, the incident this came from.

    One extra read per row, bounded by the small, capped queue this route
    ever lists — the "no new call per card rendered" performance goal is
    about the console never making a request per row, which this does not
    change: the console still makes exactly one call to this route.
    """
    run_id = request.run_id
    if run_id == "":
        return OriginView()
    incident = await uow.incidents.find_by_run(run_id)
    if incident is not None:
        return OriginView(run_id=run_id, headline=incident.title, incident_id=incident.incident_id)
    run = await uow.run_traces.get_run(run_id)
    headline = (run.headline or "") if run is not None else ""
    return OriginView(run_id=run_id, headline=headline)


async def _view(
    uow: UnitOfWork, request: ApprovalRequest, plan: RollbackPlan | None
) -> ApprovalView:
    return ApprovalView(
        approval_id=request.approval_id,
        run_id=request.run_id,
        action=request.action,
        side_effect_level=request.side_effect_level,
        summary=request.summary,
        requested_at=request.requested_at.isoformat(),
        expires_at=request.expires_at.isoformat(),
        state=request.state.value,
        arguments=dict(request.arguments),
        decided_at=request.decided_at.isoformat() if request.decided_at else None,
        decided_by=request.decided_by,
        reason=request.reason,
        rollback_plan=_plan_view(plan),
        blast_radius_count=_blast_radius_count(request.arguments),
        title=_title_of(request.arguments, fallback=request.summary),
        requester=str(_proposed_of(request.arguments).get("requester", "")),
        origin=await _origin_of(uow, request),
        intent=str(_proposed_of(request.arguments).get("intent", "")),
        risk=_risk_of(request.arguments, fallback_class=""),
        steps=_steps_of(request.arguments, summary_fallback=request.summary),
        rollback=_rollback_of(request.arguments),
        evidence=_evidence_of(request.arguments),
        blast_radius=_blast_radius_field_of(request.arguments),
        autonomy=AutonomyView(
            side_effect_level=request.side_effect_level,
            reversible=_reversible_of(request.arguments, fallback=True),
            queued=True,
        ),
        prior_effectiveness=_prior_effectiveness_of(request.arguments),
        created_at=request.requested_at.isoformat(),
        verdict=request.state.value if request.state.is_decided else None,
        raw=dict(request.arguments),
    )


#: States `state=` accepts, and which store states each bucket is built from.
#: `pending` is the store's own `PENDING` — genuinely within its window,
#: never a row that merely has not been swept yet, because every call here
#: sweeps first. `decided` deliberately excludes `EXPIRED`: an expiry is not
#: a person's verdict, and FR-006 asks for the two to be separate buckets.
_DECIDED_STATES = (ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.DISCARDED)


@router.get("", response_model=ApprovalList)
async def list_approvals(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    run_id: str = "",
    limit: int = 50,
    approval_state: str = Query(default="pending", alias="state"),
) -> ApprovalList:
    """Return approvals in one state bucket, per FR-006.

    ``state=pending`` (the default) is only requests genuinely within their
    own window; ``state=expired`` is only the ones that have lapsed;
    ``state=decided`` is ``approved``/``rejected``/``discarded``, most
    recently decided first. Every call sweeps lapsed requests to ``expired``
    first (`ApprovalStore.expire_due`), in the same transaction — the
    mechanism already existed with its own test coverage and nothing in
    production called it, so a request answered an hour after its own window
    closed still read as `pending` and the sidebar counted it. This is the
    one place that composes it into a path something actually serves.

    Each carries its rollback plan, because the queue is where a reviewer
    decides which one to open — and "this one has no undo" is exactly the fact
    that decides it.
    """
    async with state.gateway.begin(auth.scope) as uow:
        await uow.approvals.expire_due(datetime.now(UTC))
        if approval_state == "expired":
            found = await uow.approvals.list_decided(states=(ApprovalState.EXPIRED,), limit=limit)
        elif approval_state == "decided":
            found = await uow.approvals.list_decided(states=_DECIDED_STATES, limit=limit)
        else:
            found = await uow.approvals.list_pending(run_id=run_id or None, limit=limit)
        plans = {
            request.approval_id: await uow.approvals.rollback_plan_for(request.approval_id)
            for request in found
        }
        views = [await _view(uow, request, plans[request.approval_id]) for request in found]
    return ApprovalList(approvals=views)


@router.get("/{approval_id}", response_model=ApprovalView)
async def get_approval(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ApprovalView:
    """Return one approval with everything a decision rests on (FR-009)."""
    async with state.gateway.begin(auth.scope) as uow:
        request = await uow.approvals.get_request(approval_id)
        if request is None:
            raise not_found(f"no approval {approval_id!r}")
        plan = await uow.approvals.rollback_plan_for(approval_id)
        return await _view(uow, request, plan)


@router.post("/{approval_id}/repropose", response_model=ReproposeResult, status_code=201)
async def repropose_approval(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ReproposeResult:
    """Propose a fresh reading against an expired decision's origin (FR-015).

    Queues through ``RequestBuilder.queue()`` — the exact mechanism that
    produced the original, reached the same way `RemediationGate` reaches it
    — never `RemediationGate.decide()`/`.execute_approved()`, which can
    suspend waiting on a decision or, under an autonomy policy, execute the
    action outright. Neither is acceptable for a handler whose only contract
    is "always exactly one new pending proposal, never a write": calling
    `queue()` directly is what makes propose-only structural here rather than
    a convention a policy could override.

    Only an expired decision may be reproposed (FR-015: "Só aceita
    state=expired"). Idempotent by origin while the new pending exists
    (FR-017): a second call returns `409` naming the same pending rather than
    a second one. An origin that no longer resolves — the capability retired,
    the plan undeliverable — is refused by name with `422` (FR-016), never a
    server error.
    """
    # Three transactions, never nested — `RequestBuilder.queue()` opens its
    # own `state.gateway.begin(...)` inside `ApprovalService.queue()`
    # (`platform/approvals/service.py`), and `FakePersistence.begin` (like
    # the real gateway's own transaction scope) is not reentrant: holding one
    # open across the call that opens a second deadlocks the request rather
    # than refusing it, which is a far worse failure to ship than the two
    # extra round trips cost here.
    async with state.gateway.begin(auth.scope) as uow:
        expired = await uow.approvals.get_request(approval_id)
        if expired is None:
            raise not_found(f"no approval {approval_id!r}")
        if expired.state is not ApprovalState.EXPIRED:
            raise conflict(
                f"{approval_id!r} is {expired.state.value}, not expired — only an expired "
                f"decision may be reproposed"
            )

        existing = await uow.approvals.list_pending(limit=200)
        already = next(
            (row for row in existing if row.arguments.get(_ORIGIN_APPROVAL_ID_KEY) == approval_id),
            None,
        )
        if already is not None:
            raise conflict(f"{approval_id!r} was already reproposed as {already.approval_id!r}")

        action = _action_of(expired)
        if action is None:
            raise unprocessable(
                f"{approval_id!r}'s stored document no longer describes a remediation "
                f"action that can be rebuilt"
            )

    desk = getattr(state, "remediation", None)
    if desk is None:
        raise unprocessable(
            "this deployment composed no remediation desk, so nothing can be reproposed"
        )

    try:
        queued = await desk.requests.queue(action)
    except RemediationError as unresolved:
        raise unprocessable(str(unresolved)) from unresolved

    if not queued.change_id:
        raise unprocessable(
            f"{approval_id!r} could not be reproposed — this deployment has no "
            f"approval store composed for it"
        )

    async with state.gateway.begin(auth.scope) as uow:
        just_queued = await uow.approvals.get_request(queued.change_id)
        assert just_queued is not None  # created moments ago, by the call above
        fresh = await uow.approvals.amend_request(
            queued.change_id,
            arguments={**just_queued.arguments, _ORIGIN_APPROVAL_ID_KEY: approval_id},
        )

    logger.info(
        "remediation.approval_reproposed",
        origin_approval_id=approval_id,
        new_approval_id=fresh.approval_id,
    )
    return ReproposeResult(
        approval_id=fresh.approval_id,
        state=fresh.state.value,
        created_at=fresh.requested_at.isoformat(),
    )


@router.post("/{approval_id}/discard", response_model=ApprovalDecisionResult)
async def discard_approval(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ApprovalDecisionResult:
    """Withdraw a decision from the queue, marked, never deleted (FR-018).

    Reachable from `pending` or `expired`; refused once a person has already
    decided it (`approved`/`rejected`) or discarded it once already — the same
    append-only guarantee `decide` already enforces.
    """
    discarded_at = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        existing = await uow.approvals.get_request(approval_id)
        if existing is None:
            raise not_found(f"no approval {approval_id!r}")
        try:
            discarded = await uow.approvals.discard(
                approval_id, discarded_by=auth.principal_id, discarded_at=discarded_at
            )
        except AppendOnlyViolation as already_decided:
            raise conflict(str(already_decided)) from already_decided

    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=APPROVAL_AUDIT_ACTION_DECIDE,
        resource_kind=APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
        resource_id=approval_id,
        outcome=AuditOutcome.DENIED,
        detail={"action": discarded.action, "summary": discarded.summary, "verdict": "discarded"},
    )
    return ApprovalDecisionResult(
        approval_id=discarded.approval_id,
        state=discarded.state.value,
        decided_at=discarded.decided_at.isoformat() if discarded.decided_at else "",
        decided_by=discarded.decided_by or "",
    )


@router.post("/{approval_id}/rollback", response_model=RollbackResult)
async def record_rollback(
    approval_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RollbackResult:
    """Record that the stored rollback plan for ``approval_id`` was executed (FR-011).

    Refused for an approval that was never granted. Undoing something nobody
    authorised is not a rollback, and recording one would put a step in the
    audit trail that never had a decision behind it.
    """
    executed_at = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        request = await uow.approvals.get_request(approval_id)
        if request is None:
            raise not_found(f"no approval {approval_id!r}")
        if request.state.value != "approved":
            raise bad_request(
                f"{approval_id!r} is {request.state.value}, so there is nothing to roll back"
            )
        plan = await uow.approvals.rollback_plan_for(approval_id)
        if plan is None:
            raise not_found(f"no rollback plan is stored for {approval_id!r}")
        completed = [step.ordinal for step in plan.steps]
        recorded = await uow.approvals.record_rollback_executed(
            plan.plan_id, executed_at=executed_at, completed_steps=completed
        )
    return RollbackResult(
        plan_id=recorded.plan_id,
        approval_id=approval_id,
        executed_at=executed_at.isoformat(),
        completed_steps=completed,
    )


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResult)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ApprovalDecisionResult:
    """Approve or reject an approval request, in the caller's name.

    Approving records the decision, the decider and the instant, and then —
    when the change is a remediation and this deployment composed a desk —
    carries the action out through the gate. The store refuses to record an
    approval with no rollback plan stored against it, so the undo is already
    there before anything runs; the recording happens first for the reason the
    module docstring gives.

    Rejecting without a reason is refused before either store is touched. The
    console's own control disables the reject button until a reason is typed;
    this is the rule behind that courtesy.
    """
    if body.verdict not in _VERDICTS:
        raise bad_request(f"{body.verdict!r} is not a verdict; use 'approve' or 'reject'")
    if body.verdict == "reject" and not body.reason.strip():
        raise bad_request(
            "a rejection carries a reason. The same proposal arrives again after the "
            "next investigation of the same failure, and the reason is what stops it."
        )

    decided_at = datetime.now(UTC)
    async with state.gateway.begin(auth.scope) as uow:
        existing = await uow.approvals.get_request(approval_id)
        if existing is None:
            raise not_found(f"no approval {approval_id!r}")
        try:
            decided = await uow.approvals.decide(
                approval_id,
                state=ApprovalState.APPROVED
                if body.verdict == "approve"
                else ApprovalState.REJECTED,
                decided_by=auth.principal_id,
                decided_at=decided_at,
                reason=body.reason or None,
            )
        except RecordNotFound as missing:
            # Reached only when approving and no rollback plan is stored — the
            # approval itself was already confirmed to exist, above. A missing
            # precondition, not a missing resource: 400, not 404, and
            # distinguishable from "no such route" for exactly that reason.
            raise bad_request(str(missing)) from missing
        except AppendOnlyViolation as already_decided:
            raise conflict(str(already_decided)) from already_decided

    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id),
        action=APPROVAL_AUDIT_ACTION_DECIDE,
        resource_kind=APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
        resource_id=approval_id,
        outcome=AuditOutcome.ALLOWED if body.verdict == "approve" else AuditOutcome.DENIED,
        detail={
            "action": decided.action,
            "summary": decided.summary,
            "reason": decided.reason,
        },
    )

    if decided.state is ApprovalState.APPROVED:
        await _carry_out(state, decided, principal=auth.principal_id)
    else:
        await _record_refusal(state, decided, scope=auth.scope, principal=auth.principal_id)

    return ApprovalDecisionResult(
        approval_id=decided.approval_id,
        state=decided.state.value,
        decided_at=decided.decided_at.isoformat() if decided.decided_at else "",
        decided_by=decided.decided_by or "",
    )


async def _record_refusal(
    state: GatewayState,
    decided: ApprovalRequest,
    *,
    scope: TenantScope,
    principal: str,
) -> None:
    """Say on the incident that a person refused this change, and why.

    The store and the audit trail already hold the decision, and neither is
    where anybody looks. An incident whose proposed remediation was refused an
    hour ago goes on presenting it as waiting for a decision, so the next person
    to open it picks up a question that has been answered — which is how one
    refusal becomes three.

    Attributed to the reviewer rather than to the deployment. A refusal is the
    one event on that timeline that a named person is responsible for, and
    writing it as ``system`` would lose the only part of it that matters.

    Never raises, for the reason ``_carry_out`` does not: the decision is
    recorded and the response describes it, and failing to annotate an incident
    must not tell the reviewer their refusal did not land.
    """
    action = _action_of(decided)
    if action is None or not action.run_id:
        return

    reason = (decided.reason or "").strip() or "no reason was recorded"
    try:
        async with state.gateway.begin(scope) as uow:
            incident = await uow.incidents.find_by_run(action.run_id)
            if incident is None:
                return
            await IncidentLifecycle(store=uow.incidents).record_action(
                incident.incident_id,
                f"{action.capability} on {action.target} was refused by {principal}: {reason}",
                actor=principal,
                now=datetime.now(UTC),
            )
    except (RemediationError, PersistenceError, UnknownIncident) as unrecorded:
        logger.warning(
            "remediation.refusal_not_recorded_on_incident",
            approval_id=decided.approval_id,
            run_id=action.run_id,
            error=str(unrecorded),
        )


async def _carry_out(state: GatewayState, decided: ApprovalRequest, *, principal: str) -> None:
    """Take an authorised remediation through the gate, or say why it went no further.

    Never raises. The decision is already recorded and the response describes
    that decision; a failure to act is a fact about this deployment, and turning
    it into an error would tell the reviewer their decision did not land when it
    did.
    """
    desk = getattr(state, "remediation", None)
    if desk is None:
        logger.info(
            "remediation.approval_not_carried_out",
            approval_id=decided.approval_id,
            reason="this deployment composed no remediation desk",
        )
        return

    action = _action_of(decided)
    if action is None:
        return
    if not desk.handles(action.capability):
        logger.warning(
            "remediation.approval_not_carried_out",
            approval_id=decided.approval_id,
            capability=action.capability,
            reason="no components are registered for this capability here",
        )
        return

    try:
        outcome = await desk.gate_for(
            RunContext(
                requester=principal,
                team_node_id=action.team_node_id,
                run_id=action.run_id,
                environment=action.target.environment,
            )
        ).execute_approved(action, approval_id=decided.approval_id)
    except Exception as unexecuted:  # noqa: BLE001 — the approval was already stored
        logger.warning(
            "remediation.approval_execution_failed",
            approval_id=decided.approval_id,
            error=str(unexecuted),
        )
        return

    logger.info(
        "remediation.approval_carried_out",
        approval_id=decided.approval_id,
        capability=outcome.capability,
        permitted=outcome.permitted,
        reason=outcome.reason,
    )


def _action_of(decided: ApprovalRequest) -> RemediationAction | None:
    """Return the action this request's stored document describes, or ``None``.

    Rebuilt from what was stored rather than from anything a process happened
    to still hold — which is what lets an approval survive the replica that
    raised it being restarted, and what lets a repropose rebuild an expired
    request's origin from the row alone. Two callers read this: `_carry_out`
    (an approved decision, about to be executed) and `repropose_approval` (an
    expired one, about to be queued fresh) — neither approximates a payload
    that cannot describe an action; both refuse by name instead.
    """
    proposed = decided.arguments.get(PROPOSED_KEY)
    if not isinstance(proposed, Mapping):
        logger.warning(
            "remediation.action_not_rebuildable",
            approval_id=decided.approval_id,
            reason="the request carries no proposed action to rebuild",
        )
        return None
    if str(proposed.get("change_type", ChangeType.REMEDIATION.value)) != (
        ChangeType.REMEDIATION.value
    ):
        return None
    try:
        return RemediationAction.of_payload(proposed)
    except (KeyError, TypeError, ValueError) as incomplete:
        logger.warning(
            "remediation.action_not_rebuildable",
            approval_id=decided.approval_id,
            reason=f"the stored action could not be rebuilt: {incomplete}",
        )
        return None


__all__ = ["router"]
