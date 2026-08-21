"""The composed table this deployment actually serves: identity plus the gateway.

``ROUTE_TABLE`` is feature 014's own declaration. Feature 020 extends it with
``GATEWAY_ROUTES`` and ``WEBHOOK_ROUTES`` beside the handlers that serve them,
and ``gateway/http/app.py`` wires the application from the composed result —
so the composed result, not either half alone, is what has to be coherent.
"""

from __future__ import annotations

import pytest

from gateway.http.security.gateway_routes import GATEWAY_ROUTES, WEBHOOK_ROUTES
from gateway.http.state import APPLICATION_ROUTE_TABLE
from platform.identity.permissions import Permission

pytestmark = pytest.mark.security


def application_table():
    """Return the table the application is actually wired from.

    Imported from ``gateway.http.state`` rather than recomposed here — a
    second composition would be a second place the two could disagree.
    """
    return APPLICATION_ROUTE_TABLE


def test_the_gateway_routes_declare_a_permission_or_say_why_not() -> None:
    for route in GATEWAY_ROUTES:
        assert (route.permission is None) != (route.public_because is None)


def test_every_gateway_permission_is_in_the_catalogue() -> None:
    for route in GATEWAY_ROUTES:
        if route.permission is not None:
            assert route.permission in set(Permission)


def test_webhook_routes_are_public_with_a_reason_naming_verification() -> None:
    for route in WEBHOOK_ROUTES:
        assert route.public_because is not None
        assert "signature" in route.public_because or "verif" in route.public_because.lower()


def test_the_composed_table_has_no_collision_between_identity_and_gateway() -> None:
    application_table()


def test_every_planned_surface_is_represented() -> None:
    """FR-001: investigations, threads, streaming, queue, interactions, runs,
    config, integrations, memory, schedules, and health are all declared."""
    paths = {route.path for route in application_table().routes}
    for fragment in (
        "/v1/investigations",
        "/v1/investigations/{run_id}/threads",
        "/v1/investigations/{run_id}/stream",
        "/v1/investigations/{run_id}/messages",
        "/v1/interactions/{interaction_id}/answer",
        "/v1/runs/{run_id}/replay",
        "/v1/config/{node_id}",
        "/v1/integrations",
        "/v1/memory/search",
        "/v1/schedules",
        "/health/ready",
    ):
        assert fragment in paths, f"{fragment} is not declared"


def test_every_webhook_source_is_declared() -> None:
    paths = {route.path for route in application_table().routes}
    for source in (
        "alertmanager",
        "grafana",
        "generic",
    ):
        assert f"/webhooks/{source}" in paths


def test_a_guarded_gateway_route_yields_the_declared_guard() -> None:
    table = application_table()
    guard = table.guard_for("POST", "/v1/investigations")
    assert guard is not None
    assert guard.permission is Permission.INVESTIGATION_RUN


def test_a_webhook_route_yields_no_guard() -> None:
    table = application_table()
    assert table.guard_for("POST", "/webhooks/alertmanager") is None
