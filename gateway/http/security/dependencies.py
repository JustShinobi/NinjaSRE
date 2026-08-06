"""The boundary check: one guard, one permission, evaluated before the handler.

The permission check belongs at the API boundary rather than inside business
logic, and the reason is worth stating because the alternative looks reasonable.
A check inside a service method covers the callers that exist today. It does not
cover the caller somebody adds next quarter — a chat command, a scheduled job, a
second route reaching the same method — and the failure mode is a path that was
never checked and that nobody noticed was never checked.

At the boundary the set of paths is enumerable, so it can be *enumerated*, which
is what ``route_permissions`` does and what makes an unguarded route a build
failure rather than a review comment.

A guard is a plain callable over a request context. It does no I/O and touches
no framework: the transport resolves who is asking and hands it over, and this
decides. That keeps the decision testable without a server, and keeps this
module from being the place a web framework leaks into tier 1's business.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from platform.identity.audit.recorder import AuditContext
from platform.identity.authorisation import PermissionSet
from platform.identity.errors import PermissionDenied
from platform.identity.models import Principal
from platform.identity.permissions import Permission


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is asking, what they hold, and what they are asking about.

    Assembled by the transport once a request is authenticated, and passed down
    unchanged. ``node_id`` is the node the request addresses — a path parameter,
    usually — and is what the permission is resolved against, so the same guard
    means "config.write on payments" for one request and "config.write on
    platform" for the next without either being written differently.
    """

    principal: Principal
    permissions: PermissionSet = field(default_factory=PermissionSet)
    node_id: str | None = None
    audit: AuditContext | None = None

    @property
    def scope_node_id(self) -> str | None:
        """Return the node this request resolves permissions against.

        A token's own team wins over the node in the path when the token is
        narrower. A token scoped to ``payments`` asking about ``platform``
        resolves against ``payments``, holds nothing there for ``platform``, and
        is denied — which is the answer, arrived at without a special case.
        """
        if self.principal.node_id is not None:
            return self.principal.node_id
        return self.node_id


@dataclass(frozen=True, slots=True)
class PermissionGuard:
    """Refuses a request that does not hold one named permission.

    Built only through ``requires``. A frozen value rather than a closure so a
    caller — and a test — can read which permission a route is guarded by
    without calling it.
    """

    permission: Permission

    def __call__(self, context: RequestContext) -> Principal:
        """Return the principal, or raise ``PermissionDenied`` naming what is needed."""
        node_id = context.scope_node_id
        if not context.principal.is_active:
            raise PermissionDenied(
                self.permission,
                node_id=node_id,
                principal_id=context.principal.principal_id,
            )
        context.permissions.require(self.permission, node_id=node_id)
        return context.principal

    def allows(self, context: RequestContext) -> bool:
        """Return whether this guard would let ``context`` through."""
        try:
            self(context)
        except PermissionDenied:
            return False
        return True


def requires(permission: Permission) -> PermissionGuard:
    """Return the guard a route declaring ``permission`` depends on.

    The one constructor, so "which permission does this route need" has exactly
    one answer and it is written at the route.
    """
    return PermissionGuard(permission=permission)


__all__ = ["PermissionGuard", "RequestContext", "requires"]
