"""Tier 1 — human-facing clients.

The CLI, the interactive REPL, and the web console's backend-for-frontend. May
import everything below it, and must never import its tier 1 peer ``gateway``.
"""

from __future__ import annotations
