"""Running a declared command on a node, for an agent that holds no key.

Article IV keeps credentials out of the agent's process. An SSH key is a
credential, and SSH is not an HTTP request the credential proxy can inject into
— so the key lives in this process, which the agent reaches by name and never by
command. That is the same shape as the credential proxy: the thing that can
authenticate is not the thing that decides what to ask for.

Relocating the key is worth nothing on its own. An executor that ran whatever it
was handed would be the same authority wearing a different process. Three things
make it a boundary:

**Every request is resolved against the declared list first.** A command nobody
declared never reaches the transport, so the boundary is the list rather than
the transport's own judgement.

**A write needs the caller to have said it is making one.** The flag is
permission rather than instruction: it does not widen a read, and its absence
refuses a write outright. An autonomy layer that has not approved a change
simply never sets it.

**A failure is a result.** A unit that would not restart, a node that could not
be reached, and a command that was refused are three different findings, and an
investigation acts differently on each. Collapsing any of them into an exception
loses which one happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from integrations.proxmox.commands import CommandRefused, argv_for, declaration_for
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: How long one command may take. A node that has stopped answering must not
#: hold a request open: the timeout is what turns a hung node into a finding.
DEFAULT_TIMEOUT_SECONDS = 20.0


@runtime_checkable
class CommandRunner(Protocol):
    """Whatever can run one vector on one node and say how it went."""

    async def run(
        self, *, node: str, argv: list[str], timeout_seconds: float
    ) -> tuple[int, str, str]:
        """Return the exit code, standard output and standard error."""


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """One thing an agent asked a node for, by name."""

    node: str
    command_id: str
    arguments: dict[str, str] = field(default_factory=dict)
    #: Whether the caller is knowingly making a change. A write with this unset
    #: is refused: the alternative is a caller changing the cluster because a
    #: command it named happened to be a write.
    intends_write: bool = False
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """What happened, in a shape that keeps the three outcomes apart."""

    node: str
    command_id: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    #: The command, or one of its arguments, was not something the list allows.
    refused: bool = False
    #: Nobody could ask the node at all, which is a different finding from the
    #: node having answered unhappily.
    unreachable: bool = False
    reason: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether the node ran it and was content."""
        return not self.refused and not self.unreachable and self.exit_code == 0


@dataclass(frozen=True, slots=True)
class Executor:
    """Resolves a request against the declared list, then runs it."""

    runner: CommandRunner

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Return what running ``request`` produced, refusals included."""
        try:
            declared = declaration_for(request.command_id)
            if declared.writes and not request.intends_write:
                raise CommandRefused(
                    f"{request.command_id!r} changes the cluster and the caller did not "
                    f"say it was making a change"
                )
            argv = argv_for(request.command_id, node=request.node, arguments=request.arguments)
        except CommandRefused as refusal:
            logger.info("executor.refused", node=request.node, command=request.command_id)
            return ExecutionResult(
                node=request.node,
                command_id=request.command_id,
                refused=True,
                reason=str(refusal),
            )

        try:
            code, out, err = await self.runner.run(
                node=request.node, argv=argv, timeout_seconds=request.timeout_seconds
            )
        except Exception as unreachable:  # noqa: BLE001 — a transport failure is a finding
            logger.warning("executor.unreachable", node=request.node, error=str(unreachable))
            return ExecutionResult(
                node=request.node,
                command_id=request.command_id,
                unreachable=True,
                reason=f"{type(unreachable).__name__}: {unreachable}",
            )

        logger.info(
            "executor.ran",
            node=request.node,
            command=request.command_id,
            exit_code=code,
            writes=declared.writes,
        )
        return ExecutionResult(
            node=request.node,
            command_id=request.command_id,
            exit_code=code,
            stdout=out,
            stderr=err,
        )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "CommandRunner",
    "ExecutionRequest",
    "ExecutionResult",
    "Executor",
]
