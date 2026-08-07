"""Alert ingestion: verification, normalisation, deduplication, and load shedding.

A webhook is untrusted until its signature verifies, and deduplicated before it
starts an investigation. Load shedding is reported, never silent — see
``shedding.py``.
"""

from __future__ import annotations
