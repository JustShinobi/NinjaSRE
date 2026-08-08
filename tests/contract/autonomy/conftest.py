"""The fixtures the autonomy contract suite drives the real services with.

Re-exported from the configuration service's own suite rather than rebuilt. A
second in-memory gateway fixture is a second thing to keep in step with the
port, and the whole point of a contract test is that it runs against the same
collaborators everything else does.
"""

from __future__ import annotations

from tests.unit.platform.config_service.conftest import (
    engine,
    four_levels,
    gateway,
    other_org_scope,
    scope,
)

__all__ = [
    "engine",
    "four_levels",
    "gateway",
    "other_org_scope",
    "scope",
]
