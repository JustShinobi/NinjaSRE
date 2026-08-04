"""Tier 2 — one package per vendor.

Each vendor package owns its configuration normalisation, credential schema,
verifier, and API client. Integrations stay reusable below the agent layer:
they may import ``core``, ``platform``, and ``config``, and must never import
``capabilities``, ``surfaces``, or ``gateway``.
"""

from __future__ import annotations
