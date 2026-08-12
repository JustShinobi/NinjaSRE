"""Everything one running gateway process needs, held on ``app.state``.

One object rather than a scatter of globals, so a test stands up the whole
surface by constructing one value and wiring it in — the same reason
``ProxyStack`` exists for the credential proxy's tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from capabilities.protocols.port import ProtocolAdapter
from core.llm.verification import ModelVerdict
from gateway.http.protocol_catalogue import ProtocolCatalogueCache
from gateway.http.rate_limit import ApiRateLimiter
from gateway.http.security.agent_routes import AGENT_ROUTES
from gateway.http.security.autonomy_routes import AUTONOMY_ROUTES
from gateway.http.security.console_routes import CONSOLE_ROUTES
from gateway.http.security.estate_routes import ESTATE_ROUTES
from gateway.http.security.first_run_routes import FIRST_RUN_ROUTES
from gateway.http.security.gateway_routes import (
    GATEWAY_ROUTES,
    INGRESS_ROUTES,
    PROTOCOL_ROUTES,
    TRANSIT_ROUTES,
    WEBHOOK_ROUTES,
)
from gateway.http.security.incident_routes import INCIDENT_ROUTES
from gateway.http.security.onboarding_routes import ONBOARDING_ROUTES
from gateway.http.security.remediation_routes import REMEDIATION_ROUTES
from gateway.http.security.route_permissions import ROUTE_TABLE, RouteTable
from gateway.http.services import InvestigationRunner
from gateway.webhooks.dedup import DeduplicationIndex
from gateway.webhooks.idempotency import IdempotencyIndex
from gateway.webhooks.shedding import LoadShedder, LoadShedRecord
from platform.estate.discovery.port import ResourceReader
from platform.estate.kinds import KindRegistry, core_registry
from platform.guardrails.engine import GuardrailEngine
from platform.identity.local_accounts import LocalSignIn
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
    .extended_with(INGRESS_ROUTES)
    .extended_with(TRANSIT_ROUTES)
    .extended_with(PROTOCOL_ROUTES)
    .extended_with(CONSOLE_ROUTES)
    .extended_with(ESTATE_ROUTES)
    .extended_with(INCIDENT_ROUTES)
    .extended_with(AUTONOMY_ROUTES)
    .extended_with(REMEDIATION_ROUTES)
    .extended_with(FIRST_RUN_ROUTES)
    .extended_with(ONBOARDING_ROUTES)
    .extended_with(AGENT_ROUTES)
)


#: How this deployment checks that a provider can actually run an investigation.
#: Takes a provider identifier and returns the verdict — tool calling and
#: structured output exercised against the operator's own endpoint, not a check
#: that a key is present.
ProviderVerifier = Callable[[str], Awaitable[ModelVerdict]]

#: How this deployment runs an integration's *own* verifier — the one that makes
#: live vendor calls and answers with a document rather than a boolean. Takes an
#: integration name and returns its report, or ``None`` for an integration that
#: has no deep verifier to run.
#:
#: Supplied at composition for the same reason ``ProviderVerifier`` is: reaching
#: a vendor means a credential proxy and a transport, and a gateway that built
#: one from whatever ambient configuration was present would be reaching a
#: cluster nobody chose.
DeepVerifier = Callable[[str], Awaitable[Mapping[str, Any] | None]]


@dataclass(slots=True)
class GatewayState:
    """The composition root's answer to "what does this deployment run on"."""

    gateway: PersistenceGateway
    tokens: TokenService
    investigator: InvestigationRunner
    #: Supplied at composition, because *how* this deployment reaches its models
    #: is a deployment concern: a process wired with the credential proxy verifies
    #: through it, and one running against environment credentials does not.
    #: ``None`` falls back to the same end-to-end preflight ``make preflight``
    #: runs, which is the honest default rather than a report nobody made.
    model_verifier: ProviderVerifier | None = None
    #: How a deep verify reaches a vendor. ``None`` in a deployment that composed
    #: none, and then the deep-verify route refuses with a sentence naming what
    #: is missing rather than reporting an empty document as a clean bill.
    deep_verifier: DeepVerifier | None = None
    #: The discovery sources this deployment has been pointed at, by integration
    #: name. Empty until composition wires one, because a source needs a vendor
    #: client and a client needs the credential proxy — neither of which the
    #: gateway builds for itself.
    discovery_sources: Mapping[str, ResourceReader] = field(default_factory=dict)
    #: The metrics systems this deployment has been pointed at. Empty until
    #: composition wires one, for the reason the discovery sources give: a
    #: client needs the credential proxy, which the gateway does not build for
    #: itself. An observation tick over none of them stores nothing and says so.
    signal_sources: tuple[Any, ...] = ()
    #: The document sources a nightly ``knowledge.sync`` job can name, by source
    #: name. Empty until composition wires one, for the same reason as above: a
    #: wiki adapter needs a client and the client needs the credential proxy. A
    #: job naming a source that is not here fails with the name in the message
    #: rather than syncing nothing and reporting success.
    knowledge_sources: Mapping[str, Any] = field(default_factory=dict)
    #: The repositories a ``knowledge.corpus_sync`` job can name. Separate from
    #: the document sources because a corpus pass does more than ingest — it
    #: links to the estate and proposes detectors — and a deployment that wanted
    #: the documents without the proposals registers the plain sync.
    corpus_sources: Mapping[str, Any] = field(default_factory=dict)
    #: The change sources this deployment has been pointed at — a repository's
    #: apply record, a git host, or neither. Empty until composition wires one,
    #: and the routes that read it report "nothing was consulted" rather than
    #: "nothing changed": an absence from a source nobody configured is not
    #: evidence of anything.
    change_sources: Sequence[Any] = field(default_factory=tuple)
    #: How this deployment reaches the MCP and ACP servers its teams registered.
    #: ``None`` in a deployment that composed none — reaching one needs a
    #: transport and the credential proxy — and then the bridged catalogue says
    #: that in a sentence rather than answering "no tools", which is what an
    #: empty catalogue and an unwired bridge would otherwise both look like.
    protocol_adapter: ProtocolAdapter | None = None
    #: Composed catalogues, held per team for a few seconds. Building one costs
    #: a call per registered server to somebody else's infrastructure, and an
    #: operator working a classification queue refreshes the screen.
    protocol_catalogue_cache: ProtocolCatalogueCache = field(default_factory=ProtocolCatalogueCache)
    route_table: RouteTable = APPLICATION_ROUTE_TABLE
    broker: RunEventBroker = field(default_factory=RunEventBroker)
    guardrails: GuardrailEngine = field(default_factory=GuardrailEngine)
    #: The resource kinds this deployment models. Held on the state rather than
    #: built per request because an integration registers its own kinds at
    #: composition and the registry is sealed afterwards — a fresh one per
    #: request would know only the core kinds.
    estate_kinds: KindRegistry = field(default_factory=core_registry)
    rate_limiter: ApiRateLimiter = field(default_factory=ApiRateLimiter)
    #: How a person signs in when there is no identity provider. ``None`` for a
    #: deployment that configured no local account, and then ``POST
    #: /auth/sign-in`` refuses everything — which is the correct behaviour for a
    #: deployment whose operators come from a directory.
    local_sign_in: LocalSignIn | None = None
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


__all__ = ["DeepVerifier", "GatewayState", "ProviderVerifier"]
