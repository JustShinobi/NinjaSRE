"""Authentication, the boundary check, and tenant scoping — one dependency, wired once.

FastAPI resolves ``authorized`` after routing, which is what lets it read
``request.scope["route"].path`` — the declared template
(``/v1/config/{node_id}``), not the concrete path a client sent. That template
is the key ``RouteTable`` was built from, so this is the one place the table
and a live request actually meet.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, Request

from gateway.http.errors import bad_request
from gateway.http.security.dependencies import RequestContext
from gateway.http.state import GatewayState
from platform.identity.errors import TokenRejected
from platform.identity.tokens import AuthenticatedToken
from platform.persistence.ports.transaction import TenantScope

BEARER_PREFIX = "bearer "


def get_state(request: Request) -> GatewayState:
    """Return the process's ``GatewayState``, wired at application startup."""
    return request.app.state.gateway_state  # type: ignore[no-any-return]


async def authenticate(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthenticatedToken:
    """Return who this bearer token is, or raise (401 via ``TokenRejected``, 400 for none supplied)."""
    if not authorization or not authorization.lower().startswith(BEARER_PREFIX):
        raise bad_request("this route needs a bearer token: 'Authorization: Bearer <token>'")
    secret = authorization[len(BEARER_PREFIX) :].strip()
    if not secret:
        raise bad_request("the bearer token is empty")
    state = get_state(request)
    try:
        return await state.tokens.authenticate(secret)
    except TokenRejected:
        raise


@dataclass(frozen=True, slots=True)
class AuthenticatedRequest:
    """What a route handler needs about who is calling and what they may reach.

    ``scope`` is the tenant a storage read or write is opened against — always
    the authenticated token's own, never a value taken from the request body
    or a query parameter. That is the whole of what makes cross-team access
    structurally unreachable (FR-003, SC-006): there is no code path where a
    caller's own team is not what gets used.
    """

    context: RequestContext
    token: AuthenticatedToken

    @property
    def scope(self) -> TenantScope:
        """Return the tenant this request is scoped to."""
        return self.token.scope

    @property
    def principal_id(self) -> str:
        """Return the calling principal's identifier."""
        return self.context.principal.principal_id

    @property
    def team_node_id(self) -> str:
        """Return the team this request is scoped to, or the empty string."""
        return self.token.scope.team_node_id or ""


async def authorized(
    request: Request,
    authenticated: AuthenticatedToken = Depends(authenticate),
) -> AuthenticatedRequest:
    """Return the authenticated, permission-checked view of this request.

    Raises ``UndeclaredRoute`` — surfaced as a sanitised 500 — for a route
    mounted without a row in the table. That is a defect at wiring time, not a
    response a client's input can trigger, which is the property
    ``tests/security/test_gateway_route_permissions.py`` exists to prove never
    ships.
    """
    state = get_state(request)
    state.rate_limiter.check(
        principal_id=authenticated.principal.principal_id,
        team_node_id=authenticated.scope.team_node_id,
    )
    route = request.scope.get("route")
    path_template = getattr(route, "path", request.url.path)
    context = RequestContext(
        principal=authenticated.principal,
        permissions=authenticated.permissions,
        node_id=request.path_params.get("node_id"),
    )
    guard = state.route_table.guard_for(request.method, path_template)
    if guard is not None:
        guard(context)
    return AuthenticatedRequest(context=context, token=authenticated)


__all__ = ["AuthenticatedRequest", "authenticate", "authorized", "get_state"]
