"""NinjaSRE exposed as an MCP server: read and investigate, and nothing else.

``surface``
    The six operations, their permissions, and the named refusals.
``auth``
    Token, permission, team — in that order, and every refusal one sentence.
``app``
    The frames, the dispatch, and the audit line every invocation leaves.
"""

from __future__ import annotations

from capabilities.protocols.server.app import (
    DISABLED_MESSAGE,
    McpServerApp,
    SurfaceOutcome,
    enabled_for,
)
from capabilities.protocols.server.auth import (
    AccessRefused,
    SurfaceCaller,
    TokenAuthenticator,
    authenticate,
    authorise,
)
from capabilities.protocols.server.surface import (
    EXPOSED_TOOLS,
    OPERATION_PERMISSIONS,
    REFUSED_OPERATIONS,
    CatalogueSurface,
    ExposedTool,
    InvestigationSurface,
    MemorySurface,
    SurfaceOperation,
    TopologySurface,
    refusal_for,
)

__all__ = [
    "DISABLED_MESSAGE",
    "EXPOSED_TOOLS",
    "OPERATION_PERMISSIONS",
    "REFUSED_OPERATIONS",
    "AccessRefused",
    "CatalogueSurface",
    "ExposedTool",
    "InvestigationSurface",
    "McpServerApp",
    "MemorySurface",
    "SurfaceCaller",
    "SurfaceOperation",
    "SurfaceOutcome",
    "TokenAuthenticator",
    "TopologySurface",
    "authenticate",
    "authorise",
    "enabled_for",
    "refusal_for",
]
