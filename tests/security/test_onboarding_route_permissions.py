"""The onboarding surface's rows in the table every request is checked against.

The credential write is the row that matters most here. It demands
``credential.write`` rather than ``config.write`` on purpose: whoever may adjust
a masking threshold is not automatically whoever may replace the API token a
cluster is reached with, and collapsing the two would make that a decision
nobody took.

The rest of the file is the property the table exists for — a mounted route
with no declaration cannot obtain a guard, so it cannot be served at all.
"""

from __future__ import annotations

import pytest

from gateway.http.security.onboarding_routes import ONBOARDING_ROUTES
from gateway.http.state import APPLICATION_ROUTE_TABLE
from platform.identity.permissions import Permission

pytestmark = pytest.mark.security


def test_every_onboarding_route_declares_a_permission_or_says_why_not() -> None:
    for route in ONBOARDING_ROUTES:
        assert (route.permission is None) != (route.public_because is None), (
            f"{route.method} {route.path} must declare a permission or say why it is public"
        )


def test_none_of_these_routes_is_public() -> None:
    """Nothing in an onboarding surface is reachable without a principal.

    First run is not anonymous: a caller holds the bootstrap credential or their
    own, and the checklist route is the one that tells them which.
    """
    assert all(route.permission is not None for route in ONBOARDING_ROUTES)


def test_every_onboarding_permission_is_in_the_catalogue() -> None:
    for route in ONBOARDING_ROUTES:
        assert route.permission in set(Permission)


def test_the_credential_write_demands_credential_write() -> None:
    guard = APPLICATION_ROUTE_TABLE.guard_for("PUT", "/v1/integrations/{name}/credential")

    assert guard is not None
    assert guard.permission is Permission.CREDENTIAL_WRITE


def test_the_composed_table_still_declares_each_route_once() -> None:
    """Composition raises on a collision, so building the table is the assertion."""
    keys = [route.key for route in APPLICATION_ROUTE_TABLE.routes]
    assert len(keys) == len(set(keys))


def test_no_credential_route_is_a_read() -> None:
    """There is no route that reads a credential back, masked or otherwise.

    Asserted over the whole composed table rather than over this feature's rows,
    because the property is about the surface as a whole: a later feature adding
    ``GET /v1/integrations/{name}/credential`` fails here.
    """
    for route in APPLICATION_ROUTE_TABLE.routes:
        if route.path.endswith("/credential"):
            assert route.method != "GET", (
                f"{route.method} {route.path} would be a credential-reading route"
            )
