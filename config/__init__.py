"""Tier 4 — configuration.

Environment-variable names, shared constants, and prompt text. This package is
the architectural leaf: it imports no other first-party package, which is what
lets every other tier read from it without creating a cycle.

See the tier table in the root ``AGENTS.md`` for what each tier may import.
"""

from __future__ import annotations
