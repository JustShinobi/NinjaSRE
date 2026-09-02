"""Queue, decide, expire — the ordinary path, and what it records on the way.

The security suite covers the ways this must not be bypassed. This file covers
the ways it has to work: that queueing captures the state a reviewer will be
shown against, that a rejection carries its reason back to the person who asked,
that a change nobody answered closes rather than lingering, and that Article
III's rollback plan is written in the same breath as the request.

The rollback plan is the one that would be easy to leave for later. The store
refuses to record an approval for a request with no plan, so a change queued
without one is a change nobody could ever approve — and it would be discovered
by a reviewer clicking approve during whatever made somebody propose it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from config.constants.security import PENDING_CHANGE_EXPIRY_HOURS
from platform.approvals.errors import ChangeExpired, ChangeNotFound
from platform.approvals.models import ChangeState, ChangeType, fingerprint_of
from platform.approvals.policy import SecurityPolicy
from platform.approvals.service import RESTORE_CAPABILITY, ApprovalService
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.approval_store import ORIGIN_APPROVAL_ID_KEY

pytestmark = pytest.mark.unit

REQUESTER = "ada"
REVIEWER = "grace"

Applier = Any


# --- Queueing (T011) ---------------------------------------------------------


async def test_a_queued_change_records_everything_a_decision_needs(
    queue_change: Callable[..., Any], clock: Any
) -> None:
    """Type, target, proposed, current, requester, rationale, and both times."""
    change = await queue_change({"level": "strict"})

    assert change.change_type is ChangeType.PROMPT
    assert change.target.identifier == "team-payments"
    assert change.proposed == {"level": "strict"}
    assert change.current == {"level": "standard"}
    assert change.requester == REQUESTER
    assert change.rationale == "the regulator asked for it"
    assert change.created_at == clock.at
    assert change.state is ChangeState.PENDING


async def test_the_fingerprint_is_taken_of_the_target_at_queue_time(
    queue_change: Callable[..., Any], applier: Applier
) -> None:
    change = await queue_change({"level": "strict"})

    assert change.fingerprint == fingerprint_of({"level": "standard"})
    assert change.matches(applier.state)


async def test_the_expiry_follows_the_policy(
    gateway: PersistenceGateway, scope: TenantScope, applier: Applier, clock: Any
) -> None:
    from datetime import timedelta

    from platform.approvals.models import ChangeTarget

    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        policy=SecurityPolicy(change_expiry_hours=6.0),
        clock=clock,
    )

    change = await service.queue(
        change_type=ChangeType.PROMPT,
        target=ChangeTarget(identifier="team-payments", node_id="team-payments"),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="because",
    )

    assert change.expires_at == clock.at + timedelta(hours=6)


async def test_the_default_expiry_is_the_platform_default(
    queue_change: Callable[..., Any], clock: Any
) -> None:
    from datetime import timedelta

    change = await queue_change()

    assert change.expires_at == clock.at + timedelta(hours=PENDING_CHANGE_EXPIRY_HOURS)


async def test_a_rollback_plan_is_stored_with_the_request(
    queue_change: Callable[..., Any], gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Article III's "and", made structural: no plan means no possible approval."""
    change = await queue_change({"level": "strict"})

    async with gateway.begin(scope) as uow:
        plan = await uow.approvals.rollback_plan_for(change.change_id)

    assert plan is not None
    assert plan.steps[0].capability == RESTORE_CAPABILITY
    assert plan.steps[0].arguments["value"] == {"level": "standard"}


async def test_a_queued_change_reads_back_identical(
    queue_change: Callable[..., Any], service: ApprovalService
) -> None:
    """The store round trip must not lose a field the review depends on."""
    change = await queue_change({"level": "strict"})

    assert await service.get(change.change_id) == change


async def test_an_unknown_change_is_named_rather_than_returned_empty(
    service: ApprovalService,
) -> None:
    with pytest.raises(ChangeNotFound, match="nothing-like-this"):
        await service.get("nothing-like-this")


# --- Reviewing ---------------------------------------------------------------


async def test_a_review_assembles_the_diff_the_radius_and_the_reviewers(
    queue_change: Callable[..., Any], service: ApprovalService
) -> None:
    change = await queue_change({"level": "strict"})

    review = await service.review(change.change_id)

    assert review.change == change
    # A prompt is diffed by line, so replacing one line is a removal and an
    # addition rather than a single "changed" entry.
    assert [line.render() for line in review.diff.lines()] == [
        "- line 1: standard",
        "+ line 1: strict",
    ]
    assert review.blast_radius.node_id == "team-payments"
    assert not review.summary.is_summarised


# --- Rejection (T013) --------------------------------------------------------


async def test_a_rejection_carries_its_reason_back_to_the_requester(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """A rejection whose reason was dropped is one they re-submit unchanged."""
    change = await queue_change()

    decided = await service.decide(
        change.change_id,
        **as_reviewer(),
        approve=False,
        reason="the current level was chosen with the regulator in the room",
    )

    assert decided.state is ChangeState.REJECTED
    assert decided.rejection_reason == "the current level was chosen with the regulator in the room"
    assert (await service.get(change.change_id)).rejection_reason == decided.rejection_reason


async def test_an_approved_change_has_no_rejection_reason(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_change()

    decided = await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert decided.rejection_reason is None
    assert decided.decision is not None
    assert decided.decision.decided_by == REVIEWER


# --- Expiry (T014) -----------------------------------------------------------


async def test_a_change_inside_its_window_is_not_expired(
    queue_change: Callable[..., Any], service: ApprovalService, clock: Any
) -> None:
    change = await queue_change()
    clock.advance(hours=1)

    assert await service.expire_due() == ()
    assert (await service.get(change.change_id)).state is ChangeState.PENDING


async def test_a_change_past_its_window_is_closed_as_expired(
    queue_change: Callable[..., Any], service: ApprovalService, clock: Any
) -> None:
    change = await queue_change()
    clock.advance(hours=PENDING_CHANGE_EXPIRY_HOURS + 1)

    expired = await service.expire_due()

    assert [lapsed.change_id for lapsed in expired] == [change.change_id]
    assert (await service.get(change.change_id)).state is ChangeState.EXPIRED


async def test_an_expired_change_cannot_be_decided(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
    clock: Any,
) -> None:
    """A change nobody answered during the incident is not answerable a week later."""
    from platform.approvals.errors import ChangeAlreadyDecided

    change = await queue_change()
    clock.advance(days=30)
    await service.expire_due()

    with pytest.raises(ChangeAlreadyDecided):
        await service.decide(change.change_id, **as_reviewer(), approve=True)


async def test_a_lapsed_change_is_refused_even_when_no_sweep_has_relabelled_it(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
    clock: Any,
) -> None:
    """The label is a cache of the clock, and the sweep that writes it may not run.

    The test above advances the clock *and* calls ``expire_due``. This one only
    advances the clock, which is the deployment that has no sweep scheduled —
    and that is not a hypothetical. Staging on 2026-08-25 had exactly two
    scheduled jobs, neither of them an expiry sweep, so every lapsed change sat
    ``pending`` and answerable indefinitely.

    A remediation proposed at 23:48 with a fifteen-minute window was approved at
    00:53 and carried out: the guest was started fifty minutes after the reading
    that said it was safe to start stopped being current. The window exists to
    stop precisely that, and a window enforced only by a sweep is a window a
    deployment can be missing.
    """
    change = await queue_change()
    clock.advance(days=30)

    with pytest.raises(ChangeExpired):
        await service.decide(change.change_id, **as_reviewer(), approve=True)


async def test_a_conflicted_change_expires_too(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    applier: Applier,
    as_reviewer: Callable[..., dict[str, Any]],
    clock: Any,
) -> None:
    """Conflicted is open, and open work is what an expiry window bounds."""
    from platform.approvals.errors import ChangeConflicted

    change = await queue_change()
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    clock.advance(days=30)
    expired = await service.expire_due()

    assert [lapsed.change_id for lapsed in expired] == [change.change_id]


async def test_an_expiry_sweep_leaves_decided_changes_alone(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
    clock: Any,
) -> None:
    change = await queue_change()
    await service.decide(change.change_id, **as_reviewer(), approve=True)
    clock.advance(days=30)

    assert await service.expire_due() == ()
    assert (await service.get(change.change_id)).state is ChangeState.APPROVED


# --- Listing -----------------------------------------------------------------


async def test_the_open_list_holds_pending_and_conflicted_changes(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    applier: Applier,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """A queue that hid conflicted changes is one they wait in until they expire."""
    from platform.approvals.errors import ChangeConflicted

    conflicted = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(conflicted.change_id, **as_reviewer(), approve=True)

    pending = await queue_change({"level": "standard"}, identifier="team-search")

    open_changes = {change.change_id: change.state for change in await service.list_open()}

    assert open_changes[conflicted.change_id] is ChangeState.CONFLICTED
    assert open_changes[pending.change_id] is ChangeState.PENDING


async def test_a_decided_change_leaves_the_open_list(
    queue_change: Callable[..., Any],
    service: ApprovalService,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_change()

    await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert change.change_id not in {open_.change_id for open_ in await service.list_open()}


# --- Policy at the queue -----------------------------------------------------


async def test_a_change_that_could_never_be_approved_is_refused_at_the_queue(
    gateway: PersistenceGateway, scope: TenantScope, applier: Applier, clock: Any
) -> None:
    """Refused in front of the person who wrote it, not the reviewer two days on."""
    from platform.approvals.errors import PolicyViolation
    from platform.approvals.models import ChangeTarget

    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        policy=SecurityPolicy(max_values={"budgets.iterations": 10}),
        clock=clock,
    )

    with pytest.raises(PolicyViolation):
        await service.queue(
            change_type=ChangeType.CONFIGURATION,
            target=ChangeTarget(identifier="team-payments", node_id="team-payments"),
            proposed={"budgets": {"iterations": 25}},
            requester=REQUESTER,
            rationale="more headroom",
        )

    assert await service.list_open() == ()


async def test_a_policy_tightened_after_queueing_is_re_checked_at_the_decision(
    gateway: PersistenceGateway,
    scope: TenantScope,
    applier: Applier,
    clock: Any,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """A queued change is re-checked against the policy in force when
    somebody decides it, rather than reinterpreted the moment the policy moved."""
    from platform.approvals.errors import PolicyViolation
    from platform.approvals.models import ChangeTarget

    relaxed = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        clock=clock,
    )
    change = await relaxed.queue(
        change_type=ChangeType.CONFIGURATION,
        target=ChangeTarget(identifier="team-payments", node_id="team-payments"),
        proposed={"budgets": {"iterations": 25}},
        requester=REQUESTER,
        rationale="more headroom",
    )

    tightened = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        policy=SecurityPolicy(max_values={"budgets.iterations": 10}),
        clock=clock,
    )

    with pytest.raises(PolicyViolation):
        await tightened.decide(change.change_id, **as_reviewer(), approve=True)

    assert not applier.was_applied
    assert (await tightened.get(change.change_id)).state is ChangeState.PENDING


# --- Replacing a lapsed proposal ---------------------------------------------


async def test_a_change_raised_to_replace_an_expired_one_records_that_origin(
    service: ApprovalService,
    target: Callable[..., Any],
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """The marker reaches the store in the insert that creates the request.

    Not in an amendment afterwards. The difference is the whole guarantee: a
    partial unique index over ``(org_id, arguments->>'origin_approval_id')``
    can only refuse a concurrent second proposal if the value is already in the
    statement that writes the row, and a marker applied one transaction later
    leaves a committed request carrying nothing for any later check to find.
    """
    change = await service.queue(
        change_type=ChangeType.PROMPT,
        target=target(),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="the earlier proposal lapsed unanswered",
        origin_approval_id="a-expired",
    )

    assert change.origin_approval_id == "a-expired"

    async with gateway.begin(scope) as uow:
        stored = await uow.approvals.get_request(change.change_id)
        found = await uow.approvals.pending_for_origin("a-expired")

    assert stored is not None
    assert stored.arguments[ORIGIN_APPROVAL_ID_KEY] == "a-expired"
    assert found is not None and found.approval_id == change.change_id


async def test_a_change_nobody_reproposed_carries_no_origin_marker(
    queue_change: Callable[..., Any],
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """The key is absent rather than null, which is what keeps the index empty.

    An ordinary change writing ``origin_approval_id: null`` would put every
    queued change into a uniqueness rule meant for reproposals alone.
    """
    change = await queue_change({"level": "strict"})

    assert change.origin_approval_id is None

    async with gateway.begin(scope) as uow:
        stored = await uow.approvals.get_request(change.change_id)

    assert stored is not None
    assert ORIGIN_APPROVAL_ID_KEY not in stored.arguments
