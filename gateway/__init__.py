"""Tier 1 — inbound transports.

Chat platforms, alert webhook ingestion, and the REST/SSE server. May import
everything below it, and must never import its tier 1 peer ``surfaces``.
"""

from __future__ import annotations
