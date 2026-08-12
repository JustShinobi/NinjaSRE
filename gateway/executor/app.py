"""The executor's surface: the one process in this system that holds an SSH key.

Everything deciding whether a command may run lives behind this — the allowlist,
the write flag, the argument patterns. What this adds is the surface, and a
surface is where an authority leaks if it leaks anywhere.

**A refusal is an answer, not an error.** A caller that named a command nobody
declared asked a well-formed question, and the honest reply is two hundred with
``refused`` set. A four hundred would say the request was malformed, which sends
whoever wrote the caller looking in the wrong place.

**The catalogue needs no node.** An operator has to know what this executor can
be asked for before pointing anything at it, and discovery that required a
target would make reading the list a privileged act.

**Nothing here mentions the identity.** Not in health, not in the catalogue, not
in an error. The process with the most authority is the one with the most reason
never to describe how it got it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from gateway.executor.service import CommandRunner, ExecutionRequest, Executor
from integrations.proxmox.commands import catalogue
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class ExecuteBody(BaseModel):
    """One command a caller is asking for, by name.

    ``node`` and ``command_id`` are required rather than defaulted: a missing
    node is not an empty node, and a missing command is not a default one.
    """

    node: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    arguments: dict[str, str] = Field(default_factory=dict)
    intends_write: bool = False


def build_executor_app(*, runner: CommandRunner) -> FastAPI:
    """Return the executor's application, wired to ``runner``."""
    app = FastAPI(title="NinjaSRE node executor", docs_url=None, redoc_url=None)
    executor = Executor(runner=runner)

    @app.post("/execute")
    async def execute(body: ExecuteBody) -> dict[str, Any]:
        """Run one declared command and return what happened."""
        result = await executor.perform(
            ExecutionRequest(
                node=body.node,
                command_id=body.command_id,
                arguments=dict(body.arguments),
                intends_write=body.intends_write,
            )
        )
        return {
            "node": result.node,
            "command_id": result.command_id,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "refused": result.refused,
            "unreachable": result.unreachable,
            "reason": result.reason,
        }

    @app.get("/commands")
    async def commands() -> dict[str, Any]:
        """Return everything this executor may be asked for, and why."""
        return {"commands": list(catalogue())}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Return that this is serving, and nothing about how it authenticates."""
        return {"ready": True, "commands": len(catalogue())}

    return app


__all__ = ["ExecuteBody", "build_executor_app"]
