"""OpenClaw: a capability source, governed like everything else."""

from __future__ import annotations

from capabilities.protocols.openclaw.adapter import OpenClawAdapter, capability_from_declaration

__all__ = ["OpenClawAdapter", "capability_from_declaration"]
