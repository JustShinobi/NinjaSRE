"""Logging, tracing, metrics, and cost accounting.

Nothing here transmits off-host by itself. OpenTelemetry, when it arrives, is
opt-in and points at a collector the operator configures.
"""

from __future__ import annotations
