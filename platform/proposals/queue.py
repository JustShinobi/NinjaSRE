"""Putting a proposal in the queue: one unit of work, request and undo together.

Extracted from the knowledge review queue, which had this shape first and now
shares it with three other origins. What is shared is small and load-bearing:

**The request and its rollback plan are stored in the same transaction.** The
approval store refuses to record an approval for a request with no plan —
Article III's "and" made structural — so storing the plan is what makes a
proposal reviewable at all, and doing it in one unit of work is what stops a
crash leaving a proposal nobody can ever approve.

**Which stored rows are proposals is answered in one place.** The approval store
holds remediation approvals and gated configuration writes in the same table,
and teaching it a third vocabulary to tell them apart would put the definition of
"a proposal" in the store rather than in the layer that has one.
"""

from __future__ import annotations

from collections.abc import Sequence

from platform.persistence.ports.approval_store import ApprovalRequest, RollbackPlan
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


async def queue_request(
    gateway: PersistenceGateway,
    scope: TenantScope,
    request: ApprovalRequest,
    plan: RollbackPlan,
) -> None:
    """Store ``request`` and its ``plan`` together, or store neither.

    Callers differ in what they put in the request. None of them may differ in
    whether the undo landed with it.
    """
    async with gateway.begin(scope) as uow:
        await uow.approvals.create_request(request)
        await uow.approvals.store_rollback_plan(plan)


def proposals_among(
    requests: Sequence[ApprovalRequest],
    *,
    actions: frozenset[str],
) -> tuple[ApprovalRequest, ...]:
    """Return the requests among ``requests`` whose action is one of ``actions``."""
    return tuple(request for request in requests if request.action in actions)


__all__ = ["proposals_among", "queue_request"]
