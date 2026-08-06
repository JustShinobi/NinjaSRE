"""Who may decide this change, derived from the grants that already exist.

There is no reviewer list. A reviewer is whoever holds ``approval.review`` at
the node the change takes effect at — the same node-scoped grant that decides
everything else — and deriving the set rather than storing it is what keeps it
correct when somebody is offboarded. A stored list is a list somebody has to
remember to prune, and the one nobody pruned is how a departed employee stays
able to approve production changes.

Two exclusions, and both are reported rather than silently applied:

**The requester**, when policy forbids self-approval. A queue with exactly one
eligible reviewer who happens to be the person who asked is a change nobody can
answer, and "nobody is eligible" is not an answer an operator can act on where
"only the requester is eligible" is.

**Anyone scoped elsewhere.** A grant at ``platform`` does not reach
``payments``: inheritance is downward only, which is the same asymmetry every
other permission check follows. Making routing the exception would give an
operator two hierarchies to keep straight and the security one would be the one
they got wrong.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from platform.approvals.models import PendingChange, ReviewerSet
from platform.approvals.policy import SecurityPolicy
from platform.config_service.hierarchy import Hierarchy
from platform.identity.authorisation import PermissionSet
from platform.identity.models import Grant
from platform.identity.permissions import Permission

#: What holding a review permission is called when a caller has to name it. One
#: spelling, so routing and the decision-time re-check cannot disagree about
#: which permission this feature runs on.
REVIEW_PERMISSION = Permission.APPROVAL_REVIEW

#: Why somebody eligible by permission is nonetheless excluded.
EXCLUDED_REQUESTER = "requested this change and policy forbids self-approval"
EXCLUDED_INACTIVE = "is no longer an active principal"


def reviewers_for(
    change: PendingChange,
    grants: Iterable[Grant],
    *,
    policy: SecurityPolicy,
    hierarchy: Hierarchy | None = None,
    inactive: Iterable[str] = (),
) -> ReviewerSet:
    """Return who may decide ``change``, and who was excluded and why.

    ``hierarchy`` is optional and its absence narrows the answer rather than
    widening it: without the tree, only grants at the exact node and grants over
    the whole organisation apply, and inherited ones do not. Denying more than
    it should is the safe direction for a missing input to fail in.
    """
    withheld = frozenset(inactive)
    eligible: list[str] = []
    excluded: dict[str, str] = {}

    for principal_id, held in _by_principal(grants, hierarchy).items():
        if not held.allows(REVIEW_PERMISSION, node_id=change.node_id):
            continue
        if principal_id in withheld:
            excluded[principal_id] = EXCLUDED_INACTIVE
            continue
        if principal_id == change.requester and not policy.permits_self_approval():
            excluded[principal_id] = EXCLUDED_REQUESTER
            continue
        eligible.append(principal_id)

    return ReviewerSet(
        change_id=change.change_id,
        reviewers=tuple(sorted(eligible)),
        excluded=dict(sorted(excluded.items())),
    )


def may_decide(change: PendingChange, permissions: PermissionSet, *, principal_id: str) -> bool:
    """Return whether ``principal_id`` holds review permission for ``change`` now.

    The decision-time half of the same question ``reviewers_for`` answers when
    the change is queued, and it is asked again rather than cached because the
    interval between the two is where offboarding happens.
    """
    if not permissions.allows(REVIEW_PERMISSION, node_id=change.node_id):
        return False
    return not permissions.grants or any(
        grant.principal_id == principal_id for grant in permissions.grants
    )


def _by_principal(
    grants: Iterable[Grant], hierarchy: Hierarchy | None
) -> Mapping[str, PermissionSet]:
    """Return one resolvable permission set per principal named in ``grants``."""
    collected: dict[str, list[Grant]] = {}
    for grant in grants:
        collected.setdefault(grant.principal_id, []).append(grant)
    return {
        principal_id: PermissionSet(grants=tuple(held), hierarchy=hierarchy)
        for principal_id, held in collected.items()
    }


def notify_order(reviewers: Sequence[str], *, limit: int) -> tuple[str, ...]:
    """Return the reviewers to notify, in a stable order, bounded by ``limit``.

    Sorted rather than arbitrary, so a retry notifies the same people. A bound
    rather than everybody, because a change that pages two hundred people is how
    an organisation learns to filter the notification.
    """
    return tuple(sorted(reviewers))[:limit]


__all__ = [
    "EXCLUDED_INACTIVE",
    "EXCLUDED_REQUESTER",
    "REVIEW_PERMISSION",
    "may_decide",
    "notify_order",
    "reviewers_for",
]
