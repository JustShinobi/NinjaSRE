"""ACP: agent-to-agent interoperation, governed like everything else."""

from __future__ import annotations

from capabilities.protocols.acp.adapter import AcpAdapter, agent_from_declaration

__all__ = ["AcpAdapter", "agent_from_declaration"]
