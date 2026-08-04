"""Tier 3 — agent runtime and pure domain rules.

Owns the ReAct loop and its guardrails, the investigation pipeline, the state
and evidence model, the LLM provider abstraction, the capability framework
primitives, and the pure domain rules. May import ``config`` and its sibling
``platform``; never a tier 1 or tier 2 package.
"""

from __future__ import annotations
