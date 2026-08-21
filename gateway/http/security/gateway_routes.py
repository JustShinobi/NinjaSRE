"""The routes feature 020 adds to the table feature 014 built.

Extended rather than edited: ``route_permissions.py`` stays feature 014's own
file, and this table sits beside the handlers that serve it, per
``gateway/AGENTS.md``. ``gateway/http/app.py`` composes the two with
``ROUTE_TABLE.extended_with(GATEWAY_ROUTES)`` when it wires the application, and
that composed table — not either half alone — is what a request is actually
checked against.

Every row here carries a permission except the SSE stream, which reuses
``INVESTIGATION_READ``: watching a run is a read of it, not a distinct
capability, and giving it its own permission would let an operator grant "see
the trace live" without "see the trace", which is a distinction nobody asked
for.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

GATEWAY_ROUTES: Final[tuple[Route, ...]] = (
    # --- Investigations ---------------------------------------------------
    Route(method="POST", path="/v1/investigations", permission=Permission.INVESTIGATION_RUN),
    Route(method="GET", path="/v1/investigations", permission=Permission.INVESTIGATION_READ),
    Route(
        method="GET",
        path="/v1/investigations/{run_id}",
        permission=Permission.INVESTIGATION_READ,
    ),
    Route(
        method="POST",
        path="/v1/investigations/{run_id}/cancel",
        permission=Permission.INVESTIGATION_RUN,
    ),
    # Taking over is steering the run, which is the same authority as starting
    # one — and strictly more than reading it.
    Route(
        method="POST",
        path="/v1/investigations/{run_id}/take-over",
        permission=Permission.INVESTIGATION_RUN,
    ),
    Route(
        method="POST",
        path="/v1/investigations/{run_id}/resume",
        permission=Permission.INVESTIGATION_RUN,
    ),
    Route(
        method="GET",
        path="/v1/investigations/{run_id}/stream",
        permission=Permission.INVESTIGATION_READ,
    ),
    Route(
        method="POST",
        path="/v1/investigations/{run_id}/messages",
        permission=Permission.INVESTIGATION_RUN,
    ),
    Route(
        method="GET",
        path="/v1/investigations/{run_id}/threads",
        permission=Permission.INVESTIGATION_READ,
    ),
    Route(
        method="GET",
        path="/v1/investigations/{run_id}/turns",
        permission=Permission.INVESTIGATION_READ,
    ),
    Route(
        method="GET",
        path="/v1/investigations/{run_id}/interactions",
        permission=Permission.INVESTIGATION_READ,
    ),
    # --- Interactions: answered, approved, or rejected from anywhere ------
    Route(
        method="POST",
        path="/v1/interactions/{interaction_id}/answer",
        permission=Permission.INVESTIGATION_RUN,
    ),
    Route(
        method="POST",
        path="/v1/interactions/{interaction_id}/approve",
        permission=Permission.REMEDIATION_APPROVE,
    ),
    Route(
        method="POST",
        path="/v1/interactions/{interaction_id}/reject",
        permission=Permission.REMEDIATION_APPROVE,
    ),
    # --- Runs and traces ----------------------------------------------------
    Route(method="GET", path="/v1/runs", permission=Permission.INVESTIGATION_READ),
    Route(method="GET", path="/v1/runs/{run_id}", permission=Permission.INVESTIGATION_READ),
    Route(
        method="GET",
        path="/v1/runs/{run_id}/replay",
        permission=Permission.INVESTIGATION_READ,
    ),
    # --- Configuration -------------------------------------------------------
    Route(method="GET", path="/v1/config/{node_id}", permission=Permission.CONFIG_READ),
    Route(method="PUT", path="/v1/config/{node_id}", permission=Permission.CONFIG_WRITE),
    # --- Integrations --------------------------------------------------------
    Route(method="GET", path="/v1/integrations", permission=Permission.INTEGRATION_MANAGE),
    Route(
        method="POST",
        path="/v1/integrations/{name}/verify",
        permission=Permission.INTEGRATION_MANAGE,
    ),
    # --- Memory ----------------------------------------------------------------
    Route(method="GET", path="/v1/memory/search", permission=Permission.MEMORY_READ),
    Route(method="GET", path="/v1/memory/stats", permission=Permission.MEMORY_READ),
    # --- Schedules -------------------------------------------------------------
    Route(method="GET", path="/v1/schedules", permission=Permission.SCHEDULE_MANAGE),
    Route(method="POST", path="/v1/schedules", permission=Permission.SCHEDULE_MANAGE),
    Route(method="GET", path="/v1/schedules/{job_id}", permission=Permission.SCHEDULE_MANAGE),
    Route(method="PUT", path="/v1/schedules/{job_id}", permission=Permission.SCHEDULE_MANAGE),
    Route(method="DELETE", path="/v1/schedules/{job_id}", permission=Permission.SCHEDULE_MANAGE),
    Route(
        method="POST",
        path="/v1/schedules/{job_id}/enable",
        permission=Permission.SCHEDULE_MANAGE,
    ),
    Route(
        method="POST",
        path="/v1/schedules/{job_id}/disable",
        permission=Permission.SCHEDULE_MANAGE,
    ),
    # --- Capabilities catalogue ------------------------------------------------
    Route(method="GET", path="/v1/capabilities", permission=Permission.INVESTIGATION_READ),
    # --- Signing in — public, because it is where a credential comes from ------
    Route(
        method="POST",
        path="/auth/sign-in",
        public_because=(
            "this is the route that issues the credential every other route requires, so "
            "requiring one to reach it would leave a deployment with no first way in; the "
            "name and passphrase are checked in the handler against the local account"
        ),
    ),
    # --- Health and readiness — public: a probe precedes authentication ------
    Route(
        method="GET",
        path="/health/live",
        public_because="a liveness probe runs before any credential could be presented",
    ),
    Route(
        method="GET",
        path="/health/ready",
        public_because=(
            "a load balancer checks readiness before routing traffic, which is before it "
            "could hold a credential; the response carries no secret, only connectivity"
        ),
    ),
)

#: Alert ingestion is public in the permission sense: there is no NinjaSRE
#: principal behind an Alertmanager receiver. Trust is established per source by
#: signature, shared secret, or mTLS in ``gateway/webhooks/verification/``, and
#: an unverified request is rejected and audited (FR-016) — a different boundary
#: than ``Permission``, enforced in the handler rather than by this table.
WEBHOOK_ROUTES: Final[tuple[Route, ...]] = tuple(
    Route(
        method="POST",
        path=f"/webhooks/{source}",
        public_because=(
            "alert sources authenticate by per-source signature verification, not by a "
            "NinjaSRE principal; an unverified request is rejected and audited"
        ),
    )
    for source in (
        "alertmanager",
        "pagerduty",
        "datadog",
        "grafana",
        "sentry",
        "opsgenie",
        "generic",
    )
)

__all__ = ["GATEWAY_ROUTES", "WEBHOOK_ROUTES"]
