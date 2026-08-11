"""The declared route → permission map, and the only place a guard comes from.

Every privileged route must have an explicit permission check, and a new route
without one has to fail CI. There are two ways to build that, and one
of them does not work.

The one that does not work is a checklist compared against a mounted router. It
is a second list, kept in step with the first by hand, and the day it falls
behind is the day it starts reporting that an unguarded route is guarded.

So the table is not a checklist — it is the *source*. A handler obtains its
guard by asking this table for it, and a route nobody declared has nothing to
ask for: ``guard_for`` raises, at wiring time, and the application does not
start. The test suite then only has to assert that every row is coherent, which
is a thing a test can actually prove.

"Public" is a row too, with prose saying why. A route with no permission and no
reason cannot be constructed at all — ``Route`` refuses — so the absent
declaration fails where somebody wrote it rather than where somebody serves it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from gateway.http.security.dependencies import PermissionGuard, requires
from platform.identity.permissions import Permission


class UndeclaredRoute(LookupError):
    """A handler asked for a guard for a route the table does not declare.

    Raised at wiring time, which is the whole point: the failure has to happen
    before the first request rather than on the first request that mattered.
    """

    def __init__(self, method: str, path: str) -> None:
        super().__init__(
            f"{method} {path} is not declared in the route table. Add it with the permission "
            f"it needs, or with the reason it is public. A route the table does not know "
            f"about is a route nothing is checking."
        )
        self.method = method
        self.path = path


def _normalise(method: str, path: str) -> tuple[str, str]:
    """Return the canonical spelling of a route key.

    Case in the method and a trailing slash in the path are the two ways one
    route becomes two, and a guard that a trailing slash evades is not a guard.
    """
    trimmed = path.rstrip("/") or "/"
    return method.upper(), trimmed


@dataclass(frozen=True, slots=True)
class Route:
    """One route, and what it takes to reach it.

    Exactly one of ``permission`` and ``public_because`` is set. Neither means
    somebody forgot; both means somebody could not decide, and resolving that
    silently in favour of either would be the wrong answer half the time.
    """

    method: str
    path: str
    permission: Permission | None = None
    public_because: str | None = None

    def __post_init__(self) -> None:
        declared = (self.permission is not None) + (self.public_because is not None)
        if declared == 0:
            raise ValueError(
                f"{self.method} {self.path} declares neither a permission nor a reason for "
                f"being public. Every route needs one of the two."
            )
        if declared == 2:
            raise ValueError(
                f"{self.method} {self.path} declares both a permission and a reason for "
                f"being public. It cannot be both."
            )

    @property
    def key(self) -> tuple[str, str]:
        """Return the normalised ``(method, path)`` this route answers to."""
        return _normalise(self.method, self.path)

    @property
    def is_public(self) -> bool:
        """Return whether this route is reachable without a permission."""
        return self.permission is None


@dataclass(frozen=True, slots=True)
class RouteTable:
    """Every route this deployment serves, and what each one requires."""

    routes: tuple[Route, ...]

    @classmethod
    def of(cls, routes: Iterable[Route]) -> RouteTable:
        """Return the table ``routes`` describes, or raise on a duplicate.

        Two rows for one route is two answers to "may I", and the one that
        happens to be found first is not a decision anybody made.
        """
        collected = tuple(routes)
        seen: set[tuple[str, str]] = set()
        for route in collected:
            if route.key in seen:
                raise ValueError(
                    f"{route.method} {route.path} is declared twice. One route, one answer."
                )
            seen.add(route.key)
        return cls(routes=collected)

    def extended_with(self, routes: Iterable[Route]) -> RouteTable:
        """Return this table plus ``routes``, refusing a collision.

        How a later feature adds its own surface: the rows live beside the
        handlers that serve them, and the collision check still happens once,
        here.
        """
        return RouteTable.of((*self.routes, *routes))

    def declaration_for(self, method: str, path: str) -> Route:
        """Return the row for this route, or raise ``UndeclaredRoute``."""
        wanted = _normalise(method, path)
        for route in self.routes:
            if route.key == wanted:
                return route
        raise UndeclaredRoute(*wanted)

    def guard_for(self, method: str, path: str) -> PermissionGuard | None:
        """Return the guard this route depends on, or ``None`` if it is public.

        Raises ``UndeclaredRoute`` for anything the table does not know about.
        That refusal is the enforcement: a handler cannot be wired without
        passing through here, so a route with no declaration cannot be served.
        """
        route = self.declaration_for(method, path)
        if route.permission is None:
            return None
        return requires(route.permission)

    def public_routes(self) -> tuple[Route, ...]:
        """Return the routes reachable without a permission."""
        return tuple(route for route in self.routes if route.is_public)

    def guarded_routes(self) -> tuple[Route, ...]:
        """Return the routes that require one."""
        return tuple(route for route in self.routes if not route.is_public)


#: The routes this feature introduces. Later features extend the table with
#: their own rows; this is the set that exists on the day identity ships.
#:
#: The public ones are the sign-in flow and nothing else. Every one of them
#: names why: an unauthenticated user has no permission to check, which is the
#: only honest reason a route can be open, and writing it out each time is what
#: makes a fourth one stand out.
_IDENTITY_ROUTES: Final[tuple[Route, ...]] = (
    # --- Sign-in, before there is a principal ---------------------------------
    Route(
        method="GET",
        path="/auth/login",
        public_because="sign-in starts here, so there is no principal to check yet",
    ),
    Route(
        method="GET",
        path="/auth/callback",
        public_because="the provider redirects here before a session exists",
    ),
    Route(
        method="POST",
        path="/auth/break-glass",
        public_because=(
            "this is the path for when the identity provider is unreachable, so it cannot "
            "depend on the identity provider; it is rate limited and prominently audited"
        ),
    ),
    # --- The signed-in principal's own view -----------------------------------
    Route(method="POST", path="/auth/logout", permission=Permission.INVESTIGATION_READ),
    Route(method="GET", path="/auth/me", permission=Permission.INVESTIGATION_READ),
    # --- Machine tokens -------------------------------------------------------
    Route(method="GET", path="/identity/tokens", permission=Permission.TOKEN_MANAGE),
    Route(method="POST", path="/identity/tokens", permission=Permission.TOKEN_MANAGE),
    Route(
        method="DELETE",
        path="/identity/tokens/{token_id}",
        permission=Permission.TOKEN_MANAGE,
    ),
    Route(
        method="POST",
        path="/identity/tokens/revoke",
        permission=Permission.TOKEN_MANAGE,
    ),
    # --- People and their roles -----------------------------------------------
    Route(method="GET", path="/identity/principals", permission=Permission.IDENTITY_READ),
    # The catalogue a grant form offers. Read with the same permission as the
    # grants themselves: what roles exist is not a secret, and a client that
    # cannot see the grants has nothing to do with the list.
    Route(method="GET", path="/identity/roles", permission=Permission.IDENTITY_READ),
    Route(method="GET", path="/identity/grants", permission=Permission.IDENTITY_READ),
    Route(method="POST", path="/identity/grants", permission=Permission.IDENTITY_WRITE),
    Route(
        method="DELETE",
        path="/identity/grants/{grant_id}",
        permission=Permission.IDENTITY_WRITE,
    ),
    Route(
        method="POST",
        path="/identity/owners/{principal_id}",
        permission=Permission.OWNER_ASSIGN,
    ),
    # --- Single sign-on -------------------------------------------------------
    Route(method="GET", path="/identity/sso", permission=Permission.SSO_MANAGE),
    Route(method="PUT", path="/identity/sso", permission=Permission.SSO_MANAGE),
    Route(method="POST", path="/identity/sso/test", permission=Permission.SSO_MANAGE),
    Route(method="POST", path="/identity/sso/activate", permission=Permission.SSO_MANAGE),
    # --- Impersonation --------------------------------------------------------
    Route(
        method="POST",
        path="/identity/impersonation",
        permission=Permission.IMPERSONATION_USE,
    ),
    Route(
        method="DELETE",
        path="/identity/impersonation",
        permission=Permission.IMPERSONATION_USE,
    ),
    # --- The record -----------------------------------------------------------
    Route(method="GET", path="/audit/events", permission=Permission.AUDIT_READ),
    Route(method="GET", path="/audit/export", permission=Permission.AUDIT_EXPORT),
)

#: The table the application wires itself from.
ROUTE_TABLE: Final[RouteTable] = RouteTable.of(_IDENTITY_ROUTES)


__all__ = [
    "ROUTE_TABLE",
    "Route",
    "RouteTable",
    "UndeclaredRoute",
]
