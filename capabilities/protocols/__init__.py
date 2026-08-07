"""Capabilities that come from outside this repository, under the same rules.

An operator points NinjaSRE at an MCP server, an ACP peer, or an OpenClaw
source, and its tools appear in the catalogue beside the native ones. The whole
of this package exists to make "beside" mean *identical*: a bridged invocation
passes through guardrails, approval gating, the sandbox, the credential proxy,
and the trace exactly as a native one does, because it is dispatched as an
ordinary ``RegisteredTool`` through the ordinary execution path rather than
through a side channel of its own.

The one place a bridged capability is treated differently is the one place it
has to be. **A server's declaration of its own side effects is a suggestion, not
a classification.** A third-party server saying its ``delete_everything`` tool is
read-only must not be able to make it so, and Article III's direction — absence
is never permission — means an unclassified tool is a write and a write nobody
authorised cannot run. So a bridged tool is visible, scored, and inert until an
operator says what it does.

Read in this order:

===================  =========================================================
``port.py``          the four operations every protocol adapter has
``namespacing.py``   ``<server>__<tool>``, and why collisions are impossible
``classification.py``  the operator's verdict, and the fail-safe without one
``catalogue.py``     discovery plus classifications to registered tools
``registration.py``  which servers a team has, refreshed and health-checked
``mcp/``             the primary protocol: transports, discovery, invocation
``acp/``             agent-to-agent peers, same governance
``openclaw/``        an OpenClaw capability source, same governance
``server/``          NinjaSRE as an MCP server, read-and-investigate only
===================  =========================================================
"""

from __future__ import annotations

from capabilities.protocols.catalogue import (
    BridgedCatalogue,
    bridged_catalogue,
    registered_tool_for,
)
from capabilities.protocols.classification import (
    UNCLASSIFIED_LEVEL,
    Classification,
    ClassificationTable,
    UnclassifiedTool,
)
from capabilities.protocols.namespacing import (
    BridgedName,
    InvalidServerName,
    catalogue_name,
    is_bridged_name,
    parse_catalogue_name,
    qualified_name,
    validate_server_name,
)
from capabilities.protocols.peer import PeerTransport, ProxyPeerTransport
from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ExcludedTool,
    ExclusionReason,
    MalformedServerResponse,
    MalformedToolSchema,
    ProtocolAdapter,
    ProtocolBridgeError,
    ProtocolKind,
)
from capabilities.protocols.registration import (
    AuthKind,
    ProtocolRegistry,
    RefreshOutcome,
    ServerRegistration,
    TransportKind,
    refresh_classifications,
    registrations_from_config,
)
from capabilities.protocols.schema import (
    normalisation_failure,
    normalised_input_schema,
    validate_tool_schema,
)

__all__ = [
    "UNCLASSIFIED_LEVEL",
    "AuthKind",
    "BridgeHealth",
    "BridgedCatalogue",
    "BridgedName",
    "BridgedResult",
    "BridgedTool",
    "Classification",
    "ClassificationTable",
    "Discovery",
    "ExcludedTool",
    "ExclusionReason",
    "InvalidServerName",
    "MalformedServerResponse",
    "MalformedToolSchema",
    "PeerTransport",
    "ProtocolAdapter",
    "ProtocolBridgeError",
    "ProtocolKind",
    "ProtocolRegistry",
    "ProxyPeerTransport",
    "RefreshOutcome",
    "ServerRegistration",
    "TransportKind",
    "UnclassifiedTool",
    "bridged_catalogue",
    "catalogue_name",
    "is_bridged_name",
    "normalisation_failure",
    "normalised_input_schema",
    "parse_catalogue_name",
    "qualified_name",
    "refresh_classifications",
    "registered_tool_for",
    "registrations_from_config",
    "validate_server_name",
    "validate_tool_schema",
]
