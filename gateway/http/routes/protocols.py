"""What this team's bridged servers offer, and whether they answered.

Everything needed to answer the question existed already — ``discover`` on each
adapter, the classification table, the health probe, and ``bridged_catalogue``
composing the three. None of it was reachable from outside the process, so an
operator classifying ``deploys.roll_out`` had to already know that the tool
existed, which server it came from, and what it claimed to do.

One read, and it answers three things at once because they are one question:

**Where did this tool come from?** The server, the protocol it speaks, and the
qualified name — the one with the dot, which is what an operator classifies
against. The flattened catalogue name is carried too, because that is what
appears in a run's trace and the two are deliberately different strings.

**What is this deployment allowed to do with it?** The effective classification,
and whether it can execute at all. An unclassified tool is *shown* and is not
offered: the queue has to be visible for the refusal to make sense.

**Is the server even there?** Per server, with the reason when it is not. A
server that is down and a server that offers nothing produce the same empty tool
list, and only one of them is something an operator can act on.

Served from a short-lived per-team cache. Composing this contacts every
registered server, and a screen that did that per refresh would aim a request
storm at somebody else's infrastructure from a read-only page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from capabilities.protocols.catalogue import BridgedCatalogue, bridged_catalogue
from capabilities.protocols.registration import ProtocolRegistry
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.config_service.schema import RootConfig
from platform.config_service.service import ConfigService

router = APIRouter(prefix="/v1/protocols", tags=["protocols"])

#: What the catalogue says when this build has no way to reach a server. Named
#: once, because the route says it and a screen renders it and neither should
#: be the place the sentence lives.
NO_PROTOCOL_ADAPTER_REASON = (
    "This deployment has no protocol bridge wired, so the servers below were "
    "never contacted. Reaching one needs a transport and the credential proxy."
)


class BridgedToolView(BaseModel):
    """One tool a server offers, with where it came from and what it may do."""

    #: What the operator reads and classifies against — ``<server>.<tool>``.
    qualified_name: str
    #: What the model would call, and what a run's trace records. Different from
    #: the qualified name on purpose; both are shown so the two are traceable to
    #: each other rather than left to be guessed at.
    catalogue_name: str
    server: str
    tool: str
    description: str = ""
    #: The effective decision. Never the server's own claim about itself.
    classification: str = ""
    #: What the server said it was, carried so an operator can see a server
    #: describing a write as a read, and never acted on.
    declared_side_effect: str = ""
    executable: bool = False
    awaiting_classification: bool = False


class BridgedServerView(BaseModel):
    """One registered server: whether it answered, and what it gave."""

    server: str
    protocol: str = ""
    enabled: bool = True
    reachable: bool = True
    #: Why it is not reachable. Empty when it is.
    detail: str = ""
    tools: list[BridgedToolView] = Field(default_factory=list)


class ExcludedToolView(BaseModel):
    """A tool that was offered and is not available, and why."""

    qualified_name: str
    server: str
    tool: str
    reason: str
    detail: str = ""


class BridgedCatalogueView(BaseModel):
    """Everything one team bridges, as a screen renders it."""

    servers: list[BridgedServerView] = Field(default_factory=list)
    excluded: list[ExcludedToolView] = Field(default_factory=list)
    #: The qualified names waiting on somebody's decision, in one list, so the
    #: queue is a thing an operator can work through rather than something they
    #: assemble by reading every server.
    awaiting_classification: list[str] = Field(default_factory=list)
    #: What this team registered, whether or not anything was contacted. Answers
    #: "I registered a server and see nothing" without a second request.
    declared: list[str] = Field(default_factory=list)
    #: Empty when the bridge is wired. Filled with the reason when it is not.
    unavailable_reason: str = ""


async def _settings(state: GatewayState, auth: AuthenticatedRequest) -> RootConfig:
    """Return the caller's effective configuration, or the shipped defaults."""
    service = ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)
    for node_id in (auth.team_node_id, auth.scope.org_id):
        if not node_id:
            continue
        try:
            return (await service.resolve(node_id)).config
        except Exception:  # noqa: BLE001 — an unresolvable tree is a defaulted read
            continue
    return RootConfig()


def _tools_of(catalogue: BridgedCatalogue, server: str) -> list[BridgedToolView]:
    """Return one server's tools as the screen renders them."""
    return [
        BridgedToolView(
            qualified_name=found.qualified_name,
            catalogue_name=found.catalogue_name,
            server=found.server,
            tool=found.tool,
            description=found.registered.metadata.description,
            classification=found.classification.effective_level,
            declared_side_effect=found.classification.declared,
            executable=found.executable,
            awaiting_classification=not found.executable,
        )
        for found in catalogue.capabilities
        if found.server == server
    ]


@router.get("/catalogue", response_model=BridgedCatalogueView)
async def bridged_catalogue_view(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> BridgedCatalogueView:
    """Return this team's bridged tools, their origin, and each server's health.

    Built from the team's own registrations rather than from whatever the
    adapter happens to hold, so a server registered and never reached still
    appears — with the reason where its tools would be.
    """
    registry = ProtocolRegistry.from_config((await _settings(state, auth)).capabilities)
    declared = [item.name for item in registry.registrations]

    if state.protocol_adapter is None:
        return BridgedCatalogueView(
            declared=declared,
            unavailable_reason=NO_PROTOCOL_ADAPTER_REASON if declared else "",
        )

    enabled = [item.name for item in registry.registrations if item.enabled]
    catalogue = state.protocol_catalogue_cache.get(auth.scope)
    if catalogue is None:
        catalogue = await bridged_catalogue(
            state.protocol_adapter,
            servers=enabled,
            classifications=registry.classifications,
        )
        state.protocol_catalogue_cache.put(auth.scope, catalogue)

    down = {report.server: report for report in catalogue.unavailable}
    servers = [
        BridgedServerView(
            server=item.name,
            protocol=item.protocol.value,
            enabled=item.enabled,
            reachable=item.name not in down,
            detail=down[item.name].detail if item.name in down else "",
            tools=_tools_of(catalogue, item.name),
        )
        for item in registry.registrations
        if item.enabled
    ]

    return BridgedCatalogueView(
        servers=servers,
        excluded=[
            ExcludedToolView(
                qualified_name=dropped.qualified_name,
                server=dropped.server,
                tool=dropped.tool,
                reason=dropped.reason.value,
                detail=dropped.detail,
            )
            for dropped in catalogue.excluded
        ],
        awaiting_classification=list(catalogue.awaiting_classification()),
        declared=declared,
    )


__all__ = ["NO_PROTOCOL_ADAPTER_REASON", "router"]
