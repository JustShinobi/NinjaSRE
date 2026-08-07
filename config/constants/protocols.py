"""Every bound a protocol bridge runs inside, and the grammar of a bridged name.

A bridged capability comes from somewhere nobody here controls. The server is
the operator's own or one they chose, but its tool list, its schemas, its
latency, and the size of its answers are all decided elsewhere — so each of
those needs a ceiling written down in one place rather than a hope written
nowhere.

``MAX_TOOLS_PER_PROTOCOL_SERVER`` is the one that protects the turn. Selection
is capped, but the *catalogue* is not: a server exposing four hundred tools
would put four hundred declarations through scoring on every turn and would
crowd the reserved secondary slots with one vendor's opinion of what is useful.
The excess is reported rather than dropped silently, because "your server
contributed sixty-four of its two hundred tools" is something an operator can
act on and an absence is not.

``PROTOCOL_NAMESPACE_SEPARATOR`` is the load-bearing literal. A bridged tool's
catalogue name is ``<server>__<tool>``, and a server name may not contain the
separator — which is what makes the mapping from a pair to a name injective, and
therefore what makes a collision between two bridged tools impossible rather
than unlikely. Native capability names contain no ``__`` at all, which closes
the other half.
"""

from __future__ import annotations

from typing import Final

# --- Naming -------------------------------------------------------------------

#: Joins a server to one of its tools in the name the model calls. Underscores
#: rather than a dot because ``TOOL_NAME_PATTERN`` admits no punctuation, and a
#: dot would be rewritten by every provider's schema normaliser — leaving a
#: trace whose tool name does not match any declaration.
PROTOCOL_NAMESPACE_SEPARATOR: Final = "__"

#: Joins a server to one of its tools in the name an *operator* reads and
#: classifies against. Human-facing only: the console shows ``deploys.rollout``
#: and the classification table is keyed by it, so an operator's decision
#: survives a change to how the callable name is spelled.
PROTOCOL_QUALIFIED_SEPARATOR: Final = "."

#: A registered server's name, as an operator writes it. The same grammar as a
#: native tool name, which is what lets the joined form stay a legal tool name.
PROTOCOL_SERVER_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*$"

# --- Catalogue bounds ---------------------------------------------------------

#: Tools one server may contribute to a team's catalogue. Sized so that a team
#: bridging two or three servers still leaves the large majority of the
#: selection budget to the native catalogue, which carries methodology the
#: bridged tools do not.
MAX_TOOLS_PER_PROTOCOL_SERVER: Final[int] = 64

#: Servers one team may register. A bound on discovery cost per catalogue build:
#: every server is contacted, and a team that genuinely needs more than this has
#: a platform problem rather than a configuration one.
MAX_PROTOCOL_SERVERS_PER_TEAM: Final[int] = 16

#: How long a tool's description may be before it is truncated on the way into
#: the catalogue. A third-party server has no reason to respect our budget, and
#: a tool carrying an essay costs the same as a native one carrying a sentence.
MAX_BRIDGED_DESCRIPTION_CHARS: Final[int] = 1_024

# --- Call bounds --------------------------------------------------------------

#: One bridged invocation's wall clock. A server nobody here operates must not
#: be able to hold an investigation's turn open, and the failure it produces is
#: a classified ``TIMEOUT`` result rather than a hung loop.
PROTOCOL_INVOCATION_TIMEOUT_SECONDS: Final[float] = 20.0

#: A discovery or health call's wall clock. Shorter than an invocation, because
#: it happens on the path to *every* investigation rather than inside one.
PROTOCOL_DISCOVERY_TIMEOUT_SECONDS: Final[float] = 5.0

#: How much of a bridged answer is read. Beyond this the result is truncated and
#: says so: a server returning a megabyte is a query that should have been
#: narrowed, and silently keeping it would put a megabyte in the trace.
MAX_PROTOCOL_RESULT_BYTES: Final[int] = 256 * 1024

# --- MCP wire -----------------------------------------------------------------

#: The MCP revision this client speaks. Sent on initialise; a server answering
#: with something else is recorded rather than assumed compatible.
MCP_PROTOCOL_VERSION: Final = "2025-06-18"

#: JSON-RPC method names. Written once here because a typo in one of them
#: produces "server returned no tools", which reads exactly like a server that
#: has none.
MCP_METHOD_INITIALIZE: Final = "initialize"
MCP_METHOD_LIST_TOOLS: Final = "tools/list"
MCP_METHOD_CALL_TOOL: Final = "tools/call"
MCP_METHOD_PING: Final = "ping"

#: The JSON-RPC version every frame carries.
JSON_RPC_VERSION: Final = "2.0"

# --- Our own server -----------------------------------------------------------

#: What an external MCP client's call is called in the audit trail.
PROTOCOL_SERVER_AUDIT_ACTION: Final = "protocol.server.invoke"

#: What the audit trail calls the thing being acted on: one exposed operation.
PROTOCOL_SERVER_AUDIT_RESOURCE_KIND: Final = "protocol_surface"

#: Results one exposed read may return. The surface is for another agent to
#: consume, and an unbounded list is how a composing agent's context is spent by
#: ours.
MAX_EXPOSED_SURFACE_RESULTS: Final[int] = 50


__all__ = [
    "JSON_RPC_VERSION",
    "MAX_BRIDGED_DESCRIPTION_CHARS",
    "MAX_EXPOSED_SURFACE_RESULTS",
    "MAX_PROTOCOL_RESULT_BYTES",
    "MAX_PROTOCOL_SERVERS_PER_TEAM",
    "MAX_TOOLS_PER_PROTOCOL_SERVER",
    "MCP_METHOD_CALL_TOOL",
    "MCP_METHOD_INITIALIZE",
    "MCP_METHOD_LIST_TOOLS",
    "MCP_METHOD_PING",
    "MCP_PROTOCOL_VERSION",
    "PROTOCOL_DISCOVERY_TIMEOUT_SECONDS",
    "PROTOCOL_INVOCATION_TIMEOUT_SECONDS",
    "PROTOCOL_NAMESPACE_SEPARATOR",
    "PROTOCOL_QUALIFIED_SEPARATOR",
    "PROTOCOL_SERVER_AUDIT_ACTION",
    "PROTOCOL_SERVER_AUDIT_RESOURCE_KIND",
    "PROTOCOL_SERVER_NAME_PATTERN",
]
