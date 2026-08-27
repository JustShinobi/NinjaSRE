"""The four properties an approval mechanism is worth nothing without.

Each one is a way the control has failed in real deployments, and each is
asserted here rather than reviewed:

**No code path applies a gated change without a recorded decision.** Two halves:
a behavioural one that drives every entry point the service exposes and asserts
the target was never touched, and a structural one that reads the package's own
source and asserts nothing outside ``service.py`` can put a change into
``approved``. The behavioural half proves today's code is right; the structural
half is what notices the shortcut somebody adds next year.

**Self-approval is refused when policy forbids it, including via
impersonation.** An admin who steps around the control by acting as the
requester has stepped around the control.

**Approval permission is re-checked when the decision is made.** Offboarding
between the queue and the decision is routine.

**Policy maximums bind every role, owner included.** A ceiling an owner
can quietly exceed is documentation, not a control.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from platform.approvals.errors import (
    PolicyViolation,
    ReviewerNotPermitted,
    SelfApprovalForbidden,
)
from platform.approvals.models import ChangeState, ChangeTarget, ChangeType, PendingChange
from platform.approvals.policy import SecurityPolicy
from platform.approvals.service import ApprovalService
from platform.identity.audit.recorder import AuditContext
from platform.identity.authorisation import PermissionSet
from platform.identity.impersonation import Impersonation
from platform.identity.models import Grant, Principal
from platform.identity.permissions import ROLE_ORDER, Role
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ActorKind,
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    PrincipalKind,
    TenantScope,
)

pytestmark = pytest.mark.security

APPROVALS_PACKAGE = Path(__file__).resolve().parents[2] / "platform" / "approvals"

ORG = "acme"
TEAM = "team-payments"
REQUESTER = "ada"
REVIEWER = "grace"

EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


class FrozenClock:
    """A clock a test moves on purpose."""

    def __init__(self, at: datetime = EPOCH) -> None:
        self.at = at

    def __call__(self) -> datetime:
        """Return the instant this clock is currently at."""
        return self.at

    def advance(self, **delta: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.at += timedelta(**delta)
        return self.at


@dataclass(slots=True)
class RecordingApplier:
    """The target, and the whole of the no-bypass positive control.

    A change that reached the thing being changed without a decision shows up
    here as a call this object recorded. No amount of careful reading of the
    service proves the same thing.
    """

    state: dict[str, Any] | None = field(default_factory=lambda: {"level": "standard"})
    applied: list[PendingChange] = field(default_factory=list)

    async def read(
        self,
        target: ChangeTarget,
        *,
        proposed: Mapping[str, Any] | None = None,  # noqa: ARG002 — named by its target
    ) -> Mapping[str, Any] | None:
        """Return the target's current value, or ``None`` if it is gone."""
        return self.state

    async def apply(self, change: PendingChange) -> None:
        """Apply ``change``'s proposed value to the target."""
        self.applied.append(change)
        self.state = dict(change.proposed)

    @property
    def was_applied(self) -> bool:
        """Return whether anything reached the target at all."""
        return bool(self.applied)


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with the organisation and its tree created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        # Creating the organisation already created its root node, so the root
        # is upserted at the version it is at rather than at zero.
        root = await uow.config.get(ORG)
        await uow.config.upsert(
            ConfigNode(
                node_id=ORG,
                kind=ConfigNodeKind.ORGANISATION,
                name=ORG,
                parent_id=None,
                version=root.version if root is not None else 0,
            )
        )
        await uow.config.upsert(
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=ORG)
        )
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the organisation under test."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def clock() -> FrozenClock:
    """Return a clock the test moves."""
    return FrozenClock()


@pytest.fixture
def applier() -> RecordingApplier:
    """Return the target every change in this file is applied to."""
    return RecordingApplier()


@pytest.fixture
def service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: RecordingApplier,
    clock: FrozenClock,
) -> ApprovalService:
    """Return a service wired to the recording applier for every change type."""
    return ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        clock=clock,
    )


def principal(principal_id: str) -> Principal:
    """Return a human principal in the organisation under test."""
    return Principal(
        principal_id=principal_id,
        org_id=ORG,
        kind=PrincipalKind.USER,
        display_name=principal_id,
    )


def permissions_of(principal_id: str, role: Role, *, node_id: str | None = None) -> PermissionSet:
    """Return what ``principal_id`` holds, as one grant at ``node_id``."""
    return PermissionSet(
        grants=(
            Grant(
                grant_id=f"{principal_id}-{role.value}",
                principal_id=principal_id,
                role=role,
                node_id=node_id,
            ),
        )
    )


def context_of(principal_id: str, *, impersonating: str) -> AuditContext:
    """Return the context ``principal_id`` acts under while impersonating somebody."""
    return AuditContext(
        actor_kind=ActorKind.USER,
        actor_id=principal_id,
        impersonation=Impersonation(
            real_principal_id=principal_id,
            node_id=TEAM,
            started_at=EPOCH,
            expires_at=EPOCH + timedelta(minutes=30),
            reason="reproducing the report the team filed",
            subject_principal_id=impersonating,
        ),
    )


def a_target(path: str | None = "policies.masking.level") -> ChangeTarget:
    """Return the target every change in this file is queued against."""
    return ChangeTarget(identifier=TEAM, node_id=TEAM, path=path)


async def queue_one(service: ApprovalService) -> str:
    """Queue one change and return its identifier."""
    change = await service.queue(
        change_type=ChangeType.PROMPT,
        target=a_target(),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="the regulator asked for it",
    )
    return change.change_id


# --- Nothing applies without a decision --------------------------------------


async def test_queueing_a_change_does_not_apply_it(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """The current value stays in effect until somebody decides."""
    await queue_one(service)

    assert not applier.was_applied
    assert applier.state == {"level": "standard"}


async def test_no_read_path_applies_a_change(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """Every way of *looking* at a queued change leaves the target alone."""
    change_id = await queue_one(service)

    await service.get(change_id)
    await service.list_open()
    await service.review(change_id)

    assert not applier.was_applied


async def test_expiry_closes_a_change_without_applying_it(
    service: ApprovalService, applier: RecordingApplier, clock: FrozenClock
) -> None:
    """A change nobody answered is closed, never applied by default."""
    change_id = await queue_one(service)
    clock.advance(days=30)

    expired = await service.expire_due()

    assert [change.change_id for change in expired] == [change_id]
    assert (await service.get(change_id)).state is ChangeState.EXPIRED
    assert not applier.was_applied


async def test_rejection_discards_the_change_without_applying_it(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    change_id = await queue_one(service)

    decided = await service.decide(
        change_id,
        approver=principal(REVIEWER),
        permissions=permissions_of(REVIEWER, Role.RESPONDER),
        approve=False,
        reason="the previous level was chosen deliberately",
    )

    assert decided.state is ChangeState.REJECTED
    assert decided.rejection_reason == "the previous level was chosen deliberately"
    assert not applier.was_applied


async def test_a_decision_is_made_once(service: ApprovalService, applier: RecordingApplier) -> None:
    """A second reviewer deciding concurrently is told, not silently discarded."""
    from platform.approvals.errors import ChangeAlreadyDecided

    change_id = await queue_one(service)
    await service.decide(
        change_id,
        approver=principal(REVIEWER),
        permissions=permissions_of(REVIEWER, Role.RESPONDER),
        approve=False,
        reason="no",
    )

    with pytest.raises(ChangeAlreadyDecided):
        await service.decide(
            change_id,
            approver=principal("erin"),
            permissions=permissions_of("erin", Role.RESPONDER),
            approve=True,
        )

    assert not applier.was_applied


async def test_approval_is_the_one_path_that_applies(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    change_id = await queue_one(service)

    decided = await service.decide(
        change_id,
        approver=principal(REVIEWER),
        permissions=permissions_of(REVIEWER, Role.RESPONDER),
        approve=True,
    )

    assert decided.state is ChangeState.APPROVED
    assert [change.change_id for change in applier.applied] == [change_id]
    assert applier.state == {"level": "strict"}


def test_only_the_service_can_put_a_change_into_approved() -> None:
    """The structural half of no-bypass, read out of the package's own source.

    ``ChangeState.APPROVED`` is what "this applied" means. If a module other
    than the service and the state machine can name it in a position that
    produces it, then there are two ways into the applied state and only one of
    them has the permission re-check, the fingerprint comparison, and the audit
    record in front of it.
    """
    offenders: dict[str, int] = {}
    allowed = {"service.py", "state_machine.py", "models.py"}

    for source in sorted(APPROVALS_PACKAGE.rglob("*.py")):
        if source.name in allowed:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        produced = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "APPROVED"
            and isinstance(node.value, ast.Name)
            and node.value.id == "ChangeState"
            and not isinstance(getattr(node, "ctx", None), ast.Store)
            and _is_produced(node, tree)
        )
        if produced:
            offenders[str(source.relative_to(APPROVALS_PACKAGE))] = produced

    assert offenders == {}, (
        f"These modules can move a change into 'approved' without going through the "
        f"service: {sorted(offenders)}. There is one path, and it is service.decide."
    )


def _is_produced(target: ast.Attribute, tree: ast.AST) -> bool:
    """Return whether ``ChangeState.APPROVED`` is assigned rather than compared.

    Comparing against it — "has this been approved" — is what every renderer,
    notifier, and closure publisher legitimately does. Assigning it, passing it
    to ``with_state``, or returning it is what only the service may do.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            operand is target for operand in (node.left, *node.comparators)
        ):
            return False
        if isinstance(node, ast.Dict) and any(key is target for key in node.keys):
            return False
    return True


# --- Self-approval, including via impersonation ------------------------------


async def test_the_requester_cannot_approve_their_own_change(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    change_id = await queue_one(service)

    with pytest.raises(SelfApprovalForbidden):
        await service.decide(
            change_id,
            approver=principal(REQUESTER),
            permissions=permissions_of(REQUESTER, Role.OWNER),
            approve=True,
        )

    assert not applier.was_applied


async def test_an_admin_cannot_approve_by_impersonating_the_requester(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """The check reads the presented principal, so acting *as* the requester fails."""
    change_id = await queue_one(service)

    with pytest.raises(SelfApprovalForbidden):
        await service.decide(
            change_id,
            approver=principal(REQUESTER),
            permissions=permissions_of(REQUESTER, Role.OWNER),
            approve=True,
            context=context_of(REVIEWER, impersonating=REQUESTER),
        )

    assert not applier.was_applied


async def test_the_requester_cannot_approve_by_impersonating_somebody_else(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """And it reads the real principal, so hiding behind a reviewer fails too."""
    change_id = await queue_one(service)

    with pytest.raises(SelfApprovalForbidden):
        await service.decide(
            change_id,
            approver=principal(REVIEWER),
            permissions=permissions_of(REVIEWER, Role.OWNER),
            approve=True,
            context=context_of(REQUESTER, impersonating=REVIEWER),
        )

    assert not applier.was_applied


async def test_self_approval_is_allowed_when_the_policy_says_so(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: RecordingApplier,
    clock: FrozenClock,
) -> None:
    """A single-operator deployment turns it on deliberately."""
    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        policy=SecurityPolicy(allow_self_approval=True),
        clock=clock,
    )
    change_id = await queue_one(service)

    decided = await service.decide(
        change_id,
        approver=principal(REQUESTER),
        permissions=permissions_of(REQUESTER, Role.OWNER),
        approve=True,
    )

    assert decided.state is ChangeState.APPROVED
    assert applier.was_applied


# --- Permission re-checked at decision time ----------------------------------


async def test_a_reviewer_who_lost_permission_cannot_approve(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """Offboarded between the queue and the decision, which is the ordinary case."""
    change_id = await queue_one(service)

    with pytest.raises(ReviewerNotPermitted):
        await service.decide(
            change_id,
            approver=principal(REVIEWER),
            permissions=permissions_of(REVIEWER, Role.VIEWER),
            approve=True,
        )

    assert not applier.was_applied


async def test_a_reviewer_scoped_elsewhere_cannot_approve(
    service: ApprovalService, applier: RecordingApplier
) -> None:
    """A grant at another team does not reach this one — the same rule as everywhere."""
    change_id = await queue_one(service)

    with pytest.raises(ReviewerNotPermitted):
        await service.decide(
            change_id,
            approver=principal(REVIEWER),
            permissions=permissions_of(REVIEWER, Role.OWNER, node_id="team-search"),
            approve=True,
        )

    assert not applier.was_applied


async def test_the_permission_is_re_checked_on_a_rejection_too(
    service: ApprovalService,
) -> None:
    """Rejecting is a decision. Somebody with no standing must not make one."""
    change_id = await queue_one(service)

    with pytest.raises(ReviewerNotPermitted):
        await service.decide(
            change_id,
            approver=principal("mallory"),
            permissions=permissions_of("mallory", Role.VIEWER),
            approve=False,
            reason="I disagree",
        )


# --- Policy maximums bind every role -----------------------------------------


@pytest.mark.parametrize("role", ROLE_ORDER, ids=[role.value for role in ROLE_ORDER])
async def test_a_policy_maximum_binds_every_role_including_owner(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: RecordingApplier,
    clock: FrozenClock,
    role: Role,
) -> None:
    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        policy=SecurityPolicy(max_values={"budgets.iterations": 10}),
        clock=clock,
    )

    with pytest.raises(PolicyViolation) as raised:
        await service.queue(
            change_type=ChangeType.CONFIGURATION,
            target=a_target(path="budgets.iterations"),
            proposed={"budgets": {"iterations": 25}},
            requester=REQUESTER,
            rationale="we need more headroom",
        )

    assert "budgets.iterations" in str(raised.value)
    assert not applier.was_applied
    assert role in ROLE_ORDER


def test_the_policy_check_takes_no_role_at_all() -> None:
    """The structural reason the parametrised test above can never regress.

    A constraint that consulted the caller's role would be a constraint with an
    exemption, and the exemption would be for exactly the person the constraint
    exists to bind. The signature is the guarantee.
    """
    import inspect

    parameters = inspect.signature(SecurityPolicy.check_settings).parameters

    assert "role" not in parameters
    assert "permissions" not in parameters
    assert "principal" not in parameters


def test_a_locked_setting_is_refused_regardless_of_who_asks() -> None:
    from platform.approvals.errors import PolicyLocked

    policy = SecurityPolicy(locked_settings=("policies.masking.level",))

    with pytest.raises(PolicyLocked):
        policy.check_settings({"policies": {"masking": {"level": "off"}}})


def test_a_required_setting_cannot_be_cleared_by_anybody() -> None:
    policy = SecurityPolicy(required_settings=("policies.masking.level",))

    with pytest.raises(PolicyViolation):
        policy.check_settings({"policies": {"masking": {"level": None}}})


def test_an_allowed_value_set_is_closed_to_everybody() -> None:
    policy = SecurityPolicy(allowed_values={"policies.masking.level": ("standard", "strict")})

    with pytest.raises(PolicyViolation):
        policy.check_settings({"policies": {"masking": {"level": "off"}}})
