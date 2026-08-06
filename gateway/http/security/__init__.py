"""Permission enforcement at the API boundary.

Two modules. ``dependencies`` decides — one guard, one permission, no I/O.
``route_permissions`` is the table every route is declared in and the only place
a guard can be obtained from, which is what makes an undeclared route a wiring
failure instead of an open door.
"""

from __future__ import annotations

from gateway.http.security.dependencies import PermissionGuard, RequestContext, requires
from gateway.http.security.route_permissions import (
    ROUTE_TABLE,
    Route,
    RouteTable,
    UndeclaredRoute,
)

__all__ = [
    "ROUTE_TABLE",
    "PermissionGuard",
    "RequestContext",
    "Route",
    "RouteTable",
    "UndeclaredRoute",
    "requires",
]
