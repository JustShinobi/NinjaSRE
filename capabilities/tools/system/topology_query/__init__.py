"""The topology capability, its result shaping, and the binding that connects it.

Three modules rather than one because they are read by different people. The
declaration is what a reviewer checks against the catalogue's rules; the shaping
is what decides what the model actually sees and is the part worth arguing about;
the binding is composition-root machinery nobody should have to read to
understand either.
"""

from __future__ import annotations

from capabilities.tools.system.topology_query.tool import TOOL_NAME, query_service_topology

__all__ = ["TOOL_NAME", "query_service_topology"]
