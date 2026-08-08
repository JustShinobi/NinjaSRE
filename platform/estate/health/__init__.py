"""What "how is it doing" means here, and why every answer can be questioned.

Three modules. ``mapping`` declares how a provider's own vocabulary lands in the
closed set, keeping the raw word. ``derive`` turns a status and a set of named
signals into a state that carries its own evidence. ``rollup`` decides how much
of a child's trouble is its parent's, under a rule the parent names.

The property they exist to hold, jointly, is that no resource is ever in a state
nobody can explain — and that an observation nobody made reads as ``unknown``
rather than as ``healthy``.
"""

from __future__ import annotations

from platform.estate.health.derive import RULE_NO_SIGNALS, RULE_PROVIDER_STATUS, derive_from
from platform.estate.health.mapping import COMMON_STATUSES, DEFAULT_MAPPING, StatusMapping
from platform.estate.health.rollup import RollupRule, roll_up, rule_for

__all__ = [
    "COMMON_STATUSES",
    "DEFAULT_MAPPING",
    "RULE_NO_SIGNALS",
    "RULE_PROVIDER_STATUS",
    "RollupRule",
    "StatusMapping",
    "derive_from",
    "roll_up",
    "rule_for",
]
