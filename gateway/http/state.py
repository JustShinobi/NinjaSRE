"""Everything one running gateway process needs, held on ``app.state``.

One object rather than a scatter of globals, so a test stands up the whole
surface by constructing one value and wiring it in — the same reason
``ProxyStack`` exists for the credential proxy's tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from gateway.http.rate_limit import ApiRateLimiter
from gateway.http.security.autonomy_routes import AUTONOMY_ROUTES
from gateway.http.security.console_routes import CONSOLE_ROUTES
from gateway.http.security.estate_routes import ESTATE_ROUTES
from gateway.http.security.gateway_routes import GATEWAY_ROUTES, WEBHOOK_ROUTES
from gateway.http.security.incident_routes import INCIDENT_ROUTES
from gateway.http.security.remediation_routes import REMEDIATION_ROUTES
from gateway.http.security.route_permissions import ROUTE_TABLE, RouteTable
from gateway.http.services import InvestigationRunner
from gateway.webhooks.dedup import DeduplicationIndex
from gateway.webhooks.idempotency import IdempotencyIndex
from gateway.webhooks.shedding import LoadShedder, LoadShedRecord
from platform.estate.kinds import KindRegistry, core_registry
from platform.guardrails.engine import GuardrailEngine
from platform.identity.tokens import TokenService
from platform.persistence.ports.transaction import PersistenceGateway
from platform.remediation.autonomy.kill_switch import KillSwitch
from platform.runs.stream import RunEventBroker

#: The table this deployment actually serves: feature 014's identity routes,
#: extended with the API's own and with the console's — each beside the handlers
#: that serve them, per ``gateway/AGENTS.md``. Every request is checked against
#: this, never against ``ROUTE_TABLE`` alone.
APPLICATION_ROUTE_TABLE: RouteTable = (
    ROUTE_TABLE.extended_with(GATEWAY_ROUTES)
    .extended_with(WEBHOOK_ROUTES)
    .extended_with(CONSOLE_ROUTES)
    .extended_with(ESTATE_ROUTES)
    .extended_with(INCIDENT_ROUTES)
    .extended_with(AUTONOMY_ROUTES)
    .extended_with(REMEDIATION_ROUTES)
)


@dataclass(slots=True)
class GatewayState:
    """The composition root's answer to "what does this deployment run on"."""

    gateway: PersistenceGateway
    tokens: TokenService
    investigator: InvestigationRunner
    route_table: RouteTable = APPLICATION_ROUTE_TABLE
    broker: RunEventBroker = field(default_factory=RunEventBroker)
    guardrails: GuardrailEngine = field(default_factory=GuardrailEngine)
    #: The resource kinds this deployment models. Held on the state rather than
    #: built per request because an integration registers its own kinds at
    #: composition and the registry is sealed afterwards — a fresh one per
    #: request would know only the core kinds.
    estate_kinds: KindRegistry = field(default_factory=core_registry)
    rate_limiter: ApiRateLimiter = field(default_factory=ApiRateLimiter)
    #: The emergency stop, one per process. Held here rather than built per
    #: request because a switch constructed per request is a switch that is
    #: never engaged by the time anything reads it, and the window this control
    #: exists to close is measured in the seconds that matter.
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    webhook_dedup: DeduplicationIndex = field(default_factory=DeduplicationIndex)
    webhook_idempotency: IdempotencyIndex = field(default_factory=IdempotencyIndex)
    webhook_shedder: LoadShedder = field(default_factory=LoadShedder)
    #: Investigations started from a request and still running in the
    #: background. Graceful shutdown drains this rather than the ASGI
    #: server's own request queue, because the response for these has
    #: already gone out (FR-025, SC-008).
    background_runs: set[asyncio.Task[None]] = field(default_factory=set)
    #: Set once shutdown begins. A request arriving after this is refused with
    #: a clear reason rather than accepted and then abandoned mid-run.
    draining: bool = False

    def track(self, task: asyncio.Task[None]) -> None:
        """Track ``task`` so a graceful shutdown can wait for it."""
        self.background_runs.add(task)
        task.add_done_callback(self.background_runs.discard)

    def recorded_shed(self, source: str, team_node_id: str) -> LoadShedRecord | None:
        """Return the most recent shed decision for ``source``/``team_node_id``, if any.

        A thin read used by ``routes/health.py`` to surface what ingestion has
        dropped (FR-020, T054) without the health route depending on webhook
        internals directly.
        """
        return self.webhook_shedder.log.most_recent(source=source, team_node_id=team_node_id)


__all__ = ["GatewayState"]
