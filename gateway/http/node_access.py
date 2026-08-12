"""Binding the node capability to the executor this deployment runs.

The executor is a separate process holding an SSH identity, which is the whole
reason it is separate: Article IV keeps that identity out of the agent. This is
the seam between the two — the agent names a command, this carries the name, and
the executor decides whether it is one anybody declared.

**Reached through the credential proxy, like every vendor.** From the agent's
side an executor is exactly as privileged as a cloud API — more so — and gets
exactly the same treatment. Nothing here learns a key.

**No address means no binding.** The tool then reports that no executor is
configured, which an operator can act on, rather than reporting a node as quiet,
which nobody can.

**A transport failure is not a refusal.** One says the command is not allowed and
the other says nobody could ask; an investigation acts differently on each, so
the two arrive as different fields rather than one error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from capabilities.tools.node import binding
from gateway.executor.service import ExecutionResult
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class ExecutorTransport(Protocol):
    """Whatever can carry one execution request to the executor."""

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the executor's answer to ``payload``."""


@dataclass(frozen=True, slots=True)
class ComposedNodeAccess:
    """What the node capability asks, wired to this deployment's executor."""

    transport: ExecutorTransport

    async def run(self, *, node: str, command_id: str) -> ExecutionResult:
        """Return what the executor said about running ``command_id`` on ``node``."""
        try:
            answer = await self.transport.request({"node": node, "command_id": command_id})
        except Exception as unreachable:  # noqa: BLE001 — a transport failure is a finding
            logger.warning("node_access.unreachable", node=node, error=str(unreachable))
            return ExecutionResult(
                node=node,
                command_id=command_id,
                unreachable=True,
                reason=f"{type(unreachable).__name__}: {unreachable}",
            )

        return ExecutionResult(
            node=str(answer.get("node", node)),
            command_id=str(answer.get("command_id", command_id)),
            exit_code=int(answer.get("exit_code", 0) or 0),
            stdout=str(answer.get("stdout", "") or ""),
            stderr=str(answer.get("stderr", "") or ""),
            refused=bool(answer.get("refused", False)),
            unreachable=bool(answer.get("unreachable", False)),
            reason=str(answer.get("reason", "") or ""),
        )


async def compose_node_access(state: Any, *, executor_url: str) -> ComposedNodeAccess | None:
    """Bind the node capability to the configured executor, or to nothing.

    Returns what was bound, so a caller can log it. Binds nothing when no
    executor is configured: an unbound tool says so, and that is an answer.
    """
    address = executor_url.strip()
    if not address:
        logger.info("node_access.skipped", reason="no node executor is configured")
        binding.bind(None)
        return None

    from gateway.http.executor_transport import HttpExecutorTransport

    access = ComposedNodeAccess(transport=HttpExecutorTransport(base_url=address))
    state.node_executor = access
    binding.bind(access)
    logger.info("node_access.composed")
    return access


__all__ = ["ComposedNodeAccess", "ExecutorTransport", "compose_node_access"]
