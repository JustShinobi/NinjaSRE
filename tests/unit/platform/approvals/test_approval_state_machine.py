"""The transition table, asserted as the property it is meant to be.

Reading the table and believing it is not the same as asserting it. Three
properties matter enough to be stated here rather than trusted:

- ``approved`` is reachable from ``pending`` and from nowhere else;
- the three decided states have no way out at all;
- ``conflicted`` does have a way out, back into review.

The first is the structural half of "nothing applies without a decision". The
second is "a decision is made once". The third is what stops a conflict quietly
becoming a rejection nobody made.
"""

from __future__ import annotations

import pytest

from platform.approvals.errors import IllegalTransition
from platform.approvals.models import ChangeState, ChangeTarget, ChangeType, PendingChange
from platform.approvals.state_machine import (
    OPEN_STATES,
    TRANSITIONS,
    advance,
    is_permitted,
    reachable_from,
    require_transition,
)

pytestmark = pytest.mark.unit

DECIDED = (ChangeState.APPROVED, ChangeState.REJECTED, ChangeState.EXPIRED)


def a_change(state: ChangeState = ChangeState.PENDING) -> PendingChange:
    """Return one queued change in ``state``."""
    from datetime import UTC, datetime, timedelta

    at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return PendingChange(
        change_id="c-1",
        change_type=ChangeType.PROMPT,
        target=ChangeTarget(identifier="team-payments", node_id="team-payments"),
        proposed={"level": "strict"},
        current={"level": "standard"},
        requester="ada",
        rationale="because",
        created_at=at,
        expires_at=at + timedelta(hours=72),
        fingerprint="whatever",
        state=state,
    )


def test_every_state_appears_in_the_table() -> None:
    """A state with no entry would be one no transition could be checked against."""
    assert set(TRANSITIONS) == set(ChangeState)


def test_approved_is_reachable_only_from_pending() -> None:
    sources = {state for state in ChangeState if ChangeState.APPROVED in reachable_from(state)}

    assert sources == {ChangeState.PENDING}


@pytest.mark.parametrize("state", DECIDED, ids=[state.value for state in DECIDED])
def test_a_decided_state_has_no_way_out(state: ChangeState) -> None:
    assert reachable_from(state) == frozenset()
    assert state.is_decided
    assert not state.is_open


def test_conflicted_is_open_and_returns_to_review() -> None:
    assert ChangeState.CONFLICTED.is_open
    assert ChangeState.PENDING in reachable_from(ChangeState.CONFLICTED)


def test_conflicted_cannot_become_approved_without_returning_to_review() -> None:
    """The one transition whose absence is the whole point of re-review."""
    assert not is_permitted(ChangeState.CONFLICTED, ChangeState.APPROVED)


def test_the_open_states_are_derived_from_the_table() -> None:
    """Two lists would be two places for the definition to drift apart."""
    assert {ChangeState.PENDING, ChangeState.CONFLICTED} == OPEN_STATES


def test_advance_moves_a_change_it_is_allowed_to_move() -> None:
    moved = advance(a_change(), ChangeState.CONFLICTED)

    assert moved.state is ChangeState.CONFLICTED


def test_advance_refuses_a_transition_the_table_does_not_have() -> None:
    with pytest.raises(IllegalTransition) as raised:
        advance(a_change(ChangeState.EXPIRED), ChangeState.APPROVED)

    assert raised.value.current == "expired"
    assert raised.value.target == "approved"


def test_a_refusal_names_both_states_so_it_can_be_acted_on() -> None:
    with pytest.raises(IllegalTransition) as raised:
        require_transition(a_change(ChangeState.CONFLICTED), ChangeState.APPROVED)

    assert "conflicted" in str(raised.value)
    assert "approved" in str(raised.value)


def test_a_change_cannot_be_created_already_expired() -> None:
    """An expiry at or before creation is a change nobody can answer."""
    from datetime import UTC, datetime

    at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="expires at or before"):
        PendingChange(
            change_id="c-2",
            change_type=ChangeType.PROMPT,
            target=ChangeTarget(identifier="team-payments"),
            proposed={},
            current={},
            requester="ada",
            rationale="because",
            created_at=at,
            expires_at=at,
            fingerprint="whatever",
        )


def test_a_change_needs_a_requester() -> None:
    """A proposal nobody made is not one anybody can follow up on."""
    from datetime import UTC, datetime, timedelta

    at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="requested it"):
        PendingChange(
            change_id="c-3",
            change_type=ChangeType.PROMPT,
            target=ChangeTarget(identifier="team-payments"),
            proposed={},
            current={},
            requester="",
            rationale="because",
            created_at=at,
            expires_at=at + timedelta(hours=1),
            fingerprint="whatever",
        )
