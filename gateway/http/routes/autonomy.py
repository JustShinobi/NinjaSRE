"""What this deployment may do without asking, over the API.

Nine routes over one service. Three shapes are decisions rather than
conveniences.

**A policy is read and written as one document.** Not field by field: an
operator reviewing a posture reads it whole, and a surface that let somebody
change one rule without seeing the rest is a surface where the rule they did not
look at is the one that acts at four in the morning. The document is also the
export format, so what a review reads is what a deployment runs.

**Explaining takes an action, not an identifier.** "Why would this be refused"
is asked about something that has not happened yet, and the answer has to come
from the same resolver the gate uses rather than from a rendering of a past
decision. The route resolves a hypothetical and performs nothing.

**The kill switch is not part of the policy document.** Engaging it is a POST of
its own, it takes a reason, and it does not go through validation or an approval
— because the ten seconds in which it matters are the ten seconds in which
nobody has a reviewer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from config.constants.autonomy import (
    AUTONOMY_LEVELS,
    DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
    MAX_AUTONOMY_PREVIEW_ACTIONS,
)
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.routes.tenancy import within_scope
from gateway.http.state import GatewayState
from platform.autonomy.errors import MalformedPolicy
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.risk import risk_class_of
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.autonomy.service import AutonomyService
from platform.autonomy.subjects import ProposedAction, Subject
from platform.config_service.service import ConfigService
from platform.identity.audit.recorder import AuditRecorder
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.audit_repository import ActorKind
from platform.remediation.audit import RemediationAuditor
from platform.remediation.autonomy.kill_switch import ORGANISATION_SCOPE

router = APIRouter(prefix="/v1/autonomy", tags=["autonomy"])

#: How far back a preview reads when the caller does not say. A week, because
#: that is the window an operator has an intuition about.
DEFAULT_PREVIEW_DAYS = 7.0


class PolicyDocumentView(BaseModel):
    """One node's posture, whole, in the shape it is exported and imported as."""

    node_id: str
    dry_run: bool = False
    rules: list[dict[str, Any]] = Field(default_factory=list)
    freezes: list[dict[str, Any]] = Field(default_factory=list)
    budgets: list[dict[str, Any]] = Field(default_factory=list)
    overrides: list[dict[str, Any]] = Field(default_factory=list)


class PolicyWriteRequest(BaseModel):
    """The whole document, because that is what a review reads."""

    dry_run: bool = False
    rules: list[dict[str, Any]] = Field(default_factory=list)
    freezes: list[dict[str, Any]] = Field(default_factory=list)
    budgets: list[dict[str, Any]] = Field(default_factory=list)
    overrides: list[dict[str, Any]] = Field(default_factory=list)

    def document(self) -> dict[str, Any]:
        """Return this request as the document the engine parses."""
        return {
            "dry_run": self.dry_run,
            "rules": self.rules,
            "freezes": self.freezes,
            "budgets": self.budgets,
            "overrides": self.overrides,
        }


class PreviewedActionView(BaseModel):
    """One recorded action, decided twice."""

    action_id: str
    capability: str
    subjects: list[str] = Field(default_factory=list)
    at: datetime
    before: str
    after: str
    before_reason: str = ""
    after_reason: str = ""
    changed: bool = False
    more_autonomous: bool = False


class PolicyPreviewView(BaseModel):
    """What a change would have decided differently over recorded history."""

    summary: str
    considered: int = 0
    changed: int = 0
    newly_autonomous: int = 0
    actions: list[PreviewedActionView] = Field(default_factory=list)


class SubjectRequest(BaseModel):
    """One resource an explained action would touch."""

    resource_id: str = Field(min_length=1)
    kind: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    team_node_id: str = ""


class ExplainRequest(BaseModel):
    """A hypothetical action, asked about before anybody proposes it."""

    capability: str = Field(min_length=1)
    subjects: list[SubjectRequest] = Field(min_length=1)
    risk_class: str = ""
    has_rollback_plan: bool = True
    operation: str = ""


class ConsideredRuleView(BaseModel):
    rule_id: str
    scope: str
    level: str
    specificity: int
    applied: bool
    won: bool = False
    subject: str = ""
    reason: str = ""


class ExplanationView(BaseModel):
    """The resolved level and every reason it is that level."""

    decision: str
    level: str
    risk_bound: str
    risk_class: str
    dry_run: bool = False
    refused_by: str = ""
    reason: str
    winning_rule: str = ""
    considered: list[ConsideredRuleView] = Field(default_factory=list)
    per_subject: list[dict[str, str]] = Field(default_factory=list)
    operation: str = ""


class BoundsResponse(BaseModel):
    """What is bounding this node right now, whatever its levels say."""

    node_id: str
    stopped: bool = False
    stop_reason: str = ""
    freezes: list[dict[str, Any]] = Field(default_factory=list)
    budgets: list[dict[str, Any]] = Field(default_factory=list)
    overrides: list[dict[str, Any]] = Field(default_factory=list)
    expired_overrides: list[str] = Field(default_factory=list)


class DryRunRequest(BaseModel):
    enabled: bool


class OverrideRequest(BaseModel):
    """A raise in autonomy that ends by itself.

    ``reason`` is required. An override nobody explained is one the next person
    cannot decide whether to renew, and the person who granted it will not be
    the person who finds it.
    """

    name: str = Field(min_length=1)
    level: str
    reason: str = Field(min_length=1)
    seconds: float = DEFAULT_AUTONOMY_OVERRIDE_SECONDS
    scope_kind: str = ScopeKind.DEPLOYMENT.value
    team_node_id: str = ""
    resource_kind: str = ""
    resource_id: str = ""
    capability: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class OverrideView(BaseModel):
    name: str
    level: str
    scope: dict[str, Any]
    expires_at: datetime
    granted_by: str = ""
    reason: str = ""


class KillSwitchRequest(BaseModel):
    """Why writes are being stopped, and how widely.

    ``reason`` is required for the same reason a maintenance window's is: the
    person who releases it is usually not the person who engaged it.
    """

    reason: str = Field(min_length=1)
    scope: str = ""


class KillSwitchView(BaseModel):
    engaged: bool
    scopes: dict[str, Any] = Field(default_factory=dict)


async def _check_scope(node_id: str, state: GatewayState, auth: AuthenticatedRequest) -> None:
    """Raise 404 unless ``node_id`` is the caller's own team or beneath it.

    The same second check the configuration routes make, for the same reason: a
    team-scoped token's own node always wins over whatever the path names, so a
    route addressing an arbitrary node has to check the requested node is
    actually reachable itself. Written here rather than imported from a private
    name in another route module.
    """
    if not auth.team_node_id:
        return
    async with state.gateway.begin(auth.scope) as uow:
        try:
            ancestors = await uow.config.ancestors(node_id)
        except RecordNotFound:
            ancestors = ()
    if not within_scope(node_id, auth, ancestors):
        raise not_found(f"no configuration node {node_id!r}")


def _service(state: GatewayState, auth: AuthenticatedRequest) -> AutonomyService:
    """Return the autonomy service for this request.

    The kill switch comes off the gateway state rather than being constructed
    here: it is one value per process and a fresh one per request would be a
    switch that is never engaged by the time anything reads it.
    """
    return AutonomyService(
        gateway=state.gateway,
        scope=auth.scope,
        config=ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails),
        stop=state.kill_switch,
    )


def _auditor(state: GatewayState, auth: AuthenticatedRequest) -> RemediationAuditor:
    """Return the trail the switch writes into.

    The same auditor the execution path already uses, so a stop and the actions
    it stopped are rows in one trail rather than two — and the reason a review
    can ask "what was running when somebody pulled this" and get an answer.
    """
    return RemediationAuditor(scope=auth.scope, recorder=AuditRecorder(gateway=state.gateway))


def _switch_view(state: GatewayState, auth: AuthenticatedRequest) -> KillSwitchView:
    """Return what the switch stops for *this* caller, not for the organisation.

    Asked from the caller's own team, because a team-scoped operator who
    engaged their team's switch and was told "not engaged" would engage it
    again, more widely, during the minute it matters least.
    """
    switch = state.kill_switch
    return KillSwitchView(
        engaged=switch.is_engaged(team_node_id=auth.team_node_id or None),
        scopes=dict(switch.report()),
    )


def _document_view(node_id: str, policies: PolicySet) -> PolicyDocumentView:
    document = policies.to_document()
    return PolicyDocumentView(
        node_id=node_id,
        dry_run=bool(document["dry_run"]),
        rules=list(document["rules"]),
        freezes=list(document["freezes"]),
        budgets=list(document["budgets"]),
        overrides=list(document["overrides"]),
    )


def _parsed(document: dict[str, Any]) -> PolicySet:
    """Return the policy set ``document`` describes, or refuse naming the field."""
    try:
        return PolicySet.of_document(document)
    except MalformedPolicy as rejected:
        raise bad_request(str(rejected)) from rejected


def _level(value: str) -> AutonomyLevel:
    try:
        return AutonomyLevel(value)
    except ValueError as unknown:
        raise bad_request(
            f"{value!r} is not an autonomy level; expected one of {', '.join(AUTONOMY_LEVELS)}"
        ) from unknown


def _action(body: ExplainRequest, team_node_id: str) -> ProposedAction:
    """Return the hypothetical action ``body`` describes."""
    try:
        return ProposedAction(
            action_id="explain",
            capability=body.capability,
            subjects=tuple(
                Subject(
                    resource_id=entry.resource_id,
                    kind=entry.kind,
                    labels=dict(entry.labels),
                    team_node_id=entry.team_node_id or team_node_id,
                )
                for entry in body.subjects
            ),
            risk_class=risk_class_of(body.risk_class),
            has_rollback_plan=body.has_rollback_plan,
            team_node_id=team_node_id,
            operation=body.operation,
        )
    except ValueError as rejected:
        raise bad_request(str(rejected)) from rejected


@router.get("/policy/{node_id}", response_model=PolicyDocumentView)
async def read_policy(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> PolicyDocumentView:
    """Return ``node_id``'s posture, inheritance applied, as one document."""
    await _check_scope(node_id, state, auth)
    return _document_view(node_id, await _service(state, auth).policy(node_id))


@router.put("/policy/{node_id}", response_model=PolicyDocumentView)
async def write_policy(
    node_id: str,
    body: PolicyWriteRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> PolicyDocumentView:
    """Replace ``node_id``'s own posture and return what it now resolves to.

    Validated before anything is stored, and stored through the configuration
    service, so a malformed policy fails here with the field named rather than
    during an incident.
    """
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
    saved = await service.save(
        node_id,
        _parsed(body.document()),
        actor_id=auth.principal_id,
        actor_kind=ActorKind.USER,
    )
    return _document_view(node_id, saved)


@router.post("/policy/{node_id}/preview", response_model=PolicyPreviewView)
async def preview_policy(
    node_id: str,
    body: PolicyWriteRequest,
    days: float = Query(default=DEFAULT_PREVIEW_DAYS, gt=0),
    limit: int = Query(default=MAX_AUTONOMY_PREVIEW_ACTIONS, gt=0, le=MAX_AUTONOMY_PREVIEW_ACTIONS),
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> PolicyPreviewView:
    """Return what this change would have decided differently, storing nothing."""
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
    change = await service.preview(
        node_id,
        _parsed(body.document()),
        since=service.since(days),
        limit=limit,
    )
    return PolicyPreviewView(
        summary=change.summarise(),
        considered=len(change.previewed),
        changed=len(change.changed),
        newly_autonomous=len(change.newly_autonomous),
        actions=[
            PreviewedActionView(
                action_id=entry.action_id,
                capability=entry.capability,
                subjects=list(entry.subjects),
                at=entry.at,
                before=entry.before.value,
                after=entry.after.value,
                before_reason=entry.before_reason,
                after_reason=entry.after_reason,
                changed=entry.changed,
                more_autonomous=entry.more_autonomous,
            )
            for entry in change.previewed
        ],
    )


@router.post("/policy/{node_id}/dry-run", response_model=PolicyDocumentView)
async def set_dry_run(
    node_id: str,
    body: DryRunRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> PolicyDocumentView:
    """Turn simulation on or off for everything ``node_id`` resolves."""
    await _check_scope(node_id, state, auth)
    saved = await _service(state, auth).set_dry_run(
        node_id, body.enabled, actor_id=auth.principal_id, actor_kind=ActorKind.USER
    )
    return _document_view(node_id, saved)


@router.post(
    "/policy/{node_id}/overrides",
    response_model=OverrideView,
    status_code=status.HTTP_201_CREATED,
)
async def grant_override(
    node_id: str,
    body: OverrideRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> OverrideView:
    """Raise autonomy in a scope until it expires, and record who did it."""
    await _check_scope(node_id, state, auth)
    try:
        scope = PolicyScope(
            kind=ScopeKind(body.scope_kind),
            team_node_id=body.team_node_id,
            resource_kind=body.resource_kind,
            resource_id=body.resource_id,
            capability=body.capability,
            labels=dict(body.labels),
        )
    except ValueError as rejected:
        raise bad_request(str(rejected)) from rejected

    try:
        granted = await _service(state, auth).grant_override(
            node_id,
            name=body.name,
            scope=scope,
            level=_level(body.level),
            seconds=body.seconds,
            reason=body.reason,
            actor_id=auth.principal_id,
            actor_kind=ActorKind.USER,
        )
    except MalformedPolicy as rejected:
        raise bad_request(str(rejected)) from rejected

    return OverrideView(
        name=granted.name,
        level=granted.level.value,
        scope=granted.scope.to_record(),
        expires_at=granted.expires_at,
        granted_by=granted.granted_by,
        reason=granted.reason,
    )


@router.post("/policy/{node_id}/explain", response_model=ExplanationView)
async def explain(
    node_id: str,
    body: ExplainRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ExplanationView:
    """Return what would happen to this action, and every reason it would."""
    await _check_scope(node_id, state, auth)
    action = _action(body, auth.team_node_id)
    decision = await _service(state, auth).explain(node_id, action)
    resolution = decision.resolution
    return ExplanationView(
        decision=decision.outcome.value,
        level=resolution.level.value,
        risk_bound=resolution.risk_bound.value,
        risk_class=action.risk_class.value,
        dry_run=resolution.dry_run,
        refused_by=decision.bound.value if decision.bound is not None else "",
        reason=decision.reason,
        winning_rule=resolution.winner,
        considered=[
            ConsideredRuleView(
                rule_id=entry.rule_id,
                scope=entry.scope,
                level=entry.level.value,
                specificity=entry.specificity,
                applied=entry.applied,
                won=entry.won,
                subject=entry.subject,
                reason=entry.reason,
            )
            for entry in resolution.considered
        ],
        per_subject=[
            {"subject": subject, "level": level.value} for subject, level in resolution.per_subject
        ],
        operation=action.runnable(),
    )


@router.get("/policy/{node_id}/bounds", response_model=BoundsResponse)
async def read_bounds(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> BoundsResponse:
    """Return the freeze windows, budgets, overrides and stop bounding this node."""
    await _check_scope(node_id, state, auth)
    bounds = await _service(state, auth).bounds(node_id, auth.team_node_id or None)
    return BoundsResponse(
        node_id=node_id,
        stopped=bounds.stopped,
        stop_reason=bounds.stop_reason,
        freezes=[dict(entry) for entry in bounds.freezes],
        budgets=[dict(entry) for entry in bounds.budgets],
        overrides=[dict(entry) for entry in bounds.overrides],
        expired_overrides=list(bounds.expired_overrides),
    )


@router.get("/kill-switch", response_model=KillSwitchView)
async def read_kill_switch(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> KillSwitchView:
    """Return whether automated writes are stopped for this caller.

    A read of its own, because the two write routes answer the question only for
    whoever just changed it — and the thing that has to be visible is the
    engaged state, on every screen, to everybody. A dashboard where nothing is
    happening looks the same whether nothing needed doing or everything is
    stopped, and only one of those is something a person has to be told.
    """
    return _switch_view(state, auth)


@router.post("/kill-switch", response_model=KillSwitchView)
async def engage_kill_switch(
    body: KillSwitchRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> KillSwitchView:
    """Stop every automated write, immediately, with no configuration in the way.

    Audited after the switch is thrown rather than before it. The stop is the
    urgent half and must not wait on a database; the record is written straight
    afterwards, and a store that could not take it still leaves the auditor's own
    log line — which is the arrangement ``RemediationAuditor`` exists for.
    """
    switch = state.kill_switch
    engaged = switch.engage(
        engaged_by=auth.principal_id,
        scope=body.scope or auth.team_node_id or ORGANISATION_SCOPE,
        reason=body.reason,
    )
    await _auditor(state, auth).kill_switch(engaged, engaged=True, actor_id=auth.principal_id)
    return _switch_view(state, auth)


@router.delete("/kill-switch", response_model=KillSwitchView)
async def release_kill_switch(
    scope: str = Query(default=""),
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> KillSwitchView:
    """Let automated writes happen again, for one scope, attributed to whoever asked."""
    switch = state.kill_switch
    released = scope or auth.team_node_id or ORGANISATION_SCOPE
    before = switch.state_for(team_node_id=released)
    switch.release(released_by=auth.principal_id, scope=released)
    await _auditor(state, auth).kill_switch(before, engaged=False, actor_id=auth.principal_id)
    return _switch_view(state, auth)


__all__ = ["router"]
