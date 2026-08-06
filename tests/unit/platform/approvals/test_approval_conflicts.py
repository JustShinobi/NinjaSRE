"""A change queued against state that has since moved is not applied blind.

The failure this prevents is specific and common. Somebody proposes a change on
Monday, somebody else edits the same field on Tuesday, and on Wednesday a
reviewer approves a diff describing Monday's world. The change applies against
state nobody reviewed, and the incident that follows is attributed to the
reviewer who did exactly what they were asked to.

Four shapes of divergence, and each has to be caught:

- the target changed underneath the queued change;
- a *sibling* change to the same target was approved first;
- the target was deleted, which is unrecoverable rather than re-reviewable;
- two reviewers decided at once, where one wins and the other is told.

Conflicted is not rejected. The change goes back into review against what the
target says now, because an operator's edit vanishing because a colleague
touched a neighbouring field is its own way of losing changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from platform.approvals.errors import ChangeAlreadyDecided, ChangeConflicted
from platform.approvals.models import ChangeState, ConflictReason, PendingChange
from platform.approvals.service import ApprovalService

pytestmark = pytest.mark.unit

REVIEWER = "grace"

#: The applier double lives in ``conftest``. ``tests/`` is not a package, so it
#: arrives by fixture rather than by import, and is annotated here for what this
#: file uses it as: something with ``state``, ``applied``, and ``was_applied``.
Applier = Any


async def test_a_change_queued_against_a_stale_value_is_conflicted(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}  # somebody else edited it in the meantime

    with pytest.raises(ChangeConflicted) as raised:
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert raised.value.reason == ConflictReason.TARGET_CHANGED.value
    assert not applier.was_applied
    assert (await service.get(change.change_id)).state is ChangeState.CONFLICTED


async def test_a_conflicted_change_stays_open_for_re_review(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Conflicted is a state a reviewer answers, not one the change dies in."""
    change = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert (await service.get(change.change_id)).is_open
    assert change.change_id in {open_.change_id for open_ in await service.list_open()}


async def test_re_review_re_fingerprints_against_what_is_there_now(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    rereviewed = await service.rereview(change.change_id)

    assert rereviewed.state is ChangeState.PENDING
    assert rereviewed.current == {"level": "off"}
    assert rereviewed.conflict is None

    decided = await service.decide(change.change_id, **as_reviewer(), approve=True)
    assert decided.state is ChangeState.APPROVED
    assert applier.state == {"level": "strict"}


async def test_a_conflicted_change_cannot_be_approved_before_re_review(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Retrying the same click must not be the way around the check."""
    change = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert not applier.was_applied


async def test_a_conflicted_change_can_still_be_rejected(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Rejecting a conflicted change is the reviewer saying the proposal is dead."""
    change = await queue_change({"level": "strict"})
    applier.state = {"level": "off"}
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    decided = await service.decide(
        change.change_id, **as_reviewer(), approve=False, reason="superseded"
    )

    assert decided.state is ChangeState.REJECTED
    assert decided.rejection_reason == "superseded"


async def test_approving_one_sibling_conflicts_the_others(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """The rest are re-reviewed rather than applied on top of each other."""
    first: PendingChange = await queue_change({"level": "strict"})
    second: PendingChange = await queue_change({"level": "off"})
    third: PendingChange = await queue_change({"level": "standard"})

    await service.decide(first.change_id, **as_reviewer(), approve=True)

    assert (await service.get(first.change_id)).state is ChangeState.APPROVED
    for sibling in (second, third):
        marked = await service.get(sibling.change_id)
        assert marked.state is ChangeState.CONFLICTED
        assert marked.conflict is not None
        assert marked.conflict.reason is ConflictReason.SIBLING_APPROVED

    assert [applied.change_id for applied in applier.applied] == [first.change_id]


async def test_a_sibling_conflict_names_the_change_that_won(
    service: ApprovalService,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """A reviewer re-reviewing needs to know what displaced their change."""
    first: PendingChange = await queue_change({"level": "strict"})
    second: PendingChange = await queue_change({"level": "off"})

    await service.decide(first.change_id, **as_reviewer(), approve=True)

    conflict = (await service.get(second.change_id)).conflict
    assert conflict is not None
    assert first.change_id in conflict.detail


async def test_a_deleted_target_conflicts_and_cannot_be_approved(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    change = await queue_change({"level": "strict"})
    applier.state = None  # the node was deleted while the change waited

    with pytest.raises(ChangeConflicted) as raised:
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    assert raised.value.reason == ConflictReason.TARGET_DELETED.value
    assert not applier.was_applied

    marked = await service.get(change.change_id)
    assert marked.conflict is not None
    assert not marked.conflict.is_recoverable


async def test_a_deleted_target_cannot_be_recovered_by_re_review(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """There is nothing to apply it to, so re-review would produce a dead approval."""
    change = await queue_change({"level": "strict"})
    applier.state = None
    with pytest.raises(ChangeConflicted):
        await service.decide(change.change_id, **as_reviewer(), approve=True)

    with pytest.raises(ChangeConflicted):
        await service.rereview(change.change_id)


async def test_two_reviewers_deciding_at_once_produce_one_decision(
    service: ApprovalService,
    applier: Applier,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """One wins; the other is told what was decided rather than losing silently."""
    change = await queue_change({"level": "strict"})

    await service.decide(change.change_id, **as_reviewer(REVIEWER), approve=True)

    with pytest.raises(ChangeAlreadyDecided) as raised:
        await service.decide(change.change_id, **as_reviewer("erin"), approve=True)

    assert raised.value.decided_by == REVIEWER
    assert len(applier.applied) == 1


async def test_an_unrelated_target_is_not_conflicted_by_a_sibling(
    service: ApprovalService,
    queue_change: Callable[..., Any],
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """Sibling conflict is per target, not per queue."""
    first: PendingChange = await queue_change({"level": "strict"})
    other: PendingChange = await queue_change(
        {"level": "off"}, identifier="team-search", node_id="team-search"
    )

    await service.decide(first.change_id, **as_reviewer(), approve=True)

    assert (await service.get(other.change_id)).state is ChangeState.PENDING
