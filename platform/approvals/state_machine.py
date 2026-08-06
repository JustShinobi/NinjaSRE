"""The five states a queued change can be in, and the seven ways between them.

Written as data rather than as branches. A transition table can be read in one
sitting, asserted against, and rendered for an operator; the same rules spread
across ``if`` statements in a service method cannot, and the transition somebody
adds without meaning to is invisible in the second form.

```
                    ┌──────────────────────────────┐
    queue ──▶ pending ──▶ approved                  │
                 │  ╲                               │
                 │   ╲──▶ rejected                  │
                 │    ╲                             │
                 │     ╲─▶ expired                  │
                 │                                  │
                 ├──▶ conflicted ──▶ pending ───────┘  (re-review)
                                 ╲─▶ rejected
                                 ╲─▶ expired
```

Three properties the table has and a set of branches would not:

**``approved`` is reachable from ``pending`` and from nowhere else.** Not from
``conflicted`` — a conflicted change has to be re-reviewed against current state
first, which is a transition through ``pending`` that a reviewer has to make on
purpose. Not from ``expired``, which is final. This is the structural half of
"nothing applies without a decision".

**``conflicted`` is not terminal.** It is a change still waiting on somebody,
which is why it is reachable back to ``pending``. Making it final would mean an
operator's edit disappeared because a colleague touched a neighbouring field.

**Nothing leaves a decided state.** ``approved``, ``rejected``, and ``expired``
have no outgoing edges at all. A decision is made once.

Nothing here reaches storage, and nothing here decides *whether* a transition is
allowed for a given principal — that is the service's job, and it is the only
caller. This module answers a narrower question: whether the transition exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from platform.approvals.errors import IllegalTransition
from platform.approvals.models import ChangeState, PendingChange

#: Every permitted transition, as state to the states reachable from it. The
#: three decided states map to an empty set rather than being absent, so
#: "nothing leaves here" is stated rather than inferred from a missing key.
TRANSITIONS: Final[Mapping[ChangeState, frozenset[ChangeState]]] = {
    ChangeState.PENDING: frozenset(
        {
            ChangeState.APPROVED,
            ChangeState.REJECTED,
            ChangeState.EXPIRED,
            ChangeState.CONFLICTED,
        }
    ),
    ChangeState.CONFLICTED: frozenset(
        {
            ChangeState.PENDING,
            ChangeState.REJECTED,
            ChangeState.EXPIRED,
        }
    ),
    ChangeState.APPROVED: frozenset(),
    ChangeState.REJECTED: frozenset(),
    ChangeState.EXPIRED: frozenset(),
}

#: The states a change may sit in while it still needs an answer. Derived from
#: the table rather than listed again: a state with no way out is decided, and
#: a second list would be the place the two definitions drifted apart.
OPEN_STATES: Final[frozenset[ChangeState]] = frozenset(
    state for state, onward in TRANSITIONS.items() if onward
)


def reachable_from(state: ChangeState) -> frozenset[ChangeState]:
    """Return every state ``state`` may move to."""
    return TRANSITIONS[state]


def is_permitted(current: ChangeState, target: ChangeState) -> bool:
    """Return whether a change in ``current`` may move to ``target``."""
    return target in TRANSITIONS[current]


def require_transition(change: PendingChange, target: ChangeState) -> None:
    """Raise ``IllegalTransition`` unless ``change`` may move to ``target``.

    Named for what a caller does with it rather than for what it returns. Every
    call site is a guard, and a guard that returns a boolean somebody forgot to
    check is not one.
    """
    if not is_permitted(change.state, target):
        raise IllegalTransition(change.change_id, change.state.value, target.value)


def advance(change: PendingChange, target: ChangeState) -> PendingChange:
    """Return ``change`` in ``target``, or raise naming the transition it lacks.

    The only function in this package that puts a state onto a change without
    the caller having chosen it themselves, and the service is its only caller.
    The decision-carrying moves — approve, reject — go through
    ``PendingChange.decided`` instead, because they carry a value the state
    alone cannot express, and the service guards those with
    ``require_transition`` first.
    """
    require_transition(change, target)
    return change.with_state(target)


__all__ = [
    "OPEN_STATES",
    "TRANSITIONS",
    "advance",
    "is_permitted",
    "reachable_from",
    "require_transition",
]
