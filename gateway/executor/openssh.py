"""Reaching a node over SSH, with the vector kept a vector for as long as possible.

The executor resolves a request into an argument vector precisely so that no
value can become syntax. That guarantee survives the transport only if the
transport does not undo it — and OpenSSH undoes it by default: it joins the
arguments it is given with spaces and hands the result to the remote login
shell, which parses it.

So each element is quoted here, once, before OpenSSH sees any of it. That is the
last place a value could still become syntax, which is why it is the part with
its own tests rather than the part assumed to be fine.

**Batch mode, and host key checking left on.** A password prompt would hang the
executor until its timeout on every node whose key is wrong, turning a
configuration mistake into what looks like an outage. And switching host key
checking off would make this reachable by anything that can answer on the node's
address, which is the attack the key exists to prevent.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

#: What the remote end is told, and nothing else. ``BatchMode`` refuses every
#: interactive prompt; the rest keeps one unreachable node from becoming a slow
#: request rather than a fast finding.
#: How a local process is started, so a test can watch one without one
#: branch of this module being reachable only from a test.
Spawn = Callable[..., Awaitable[Any]]

SSH_OPTIONS: Final[tuple[str, ...]] = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "ServerAliveInterval=5",
    "-o",
    "ServerAliveCountMax=2",
)


def remote_command(argv: list[str]) -> str:
    """Return ``argv`` as one string the remote shell will read back as ``argv``.

    ``shlex.quote`` per element rather than a join: the remote end is a shell
    whatever we do, so the only question is whether it parses our structure or
    something a value smuggled in.
    """
    return " ".join(shlex.quote(part) for part in argv)


@dataclass(frozen=True, slots=True)
class OpenSshRunner:
    """One node reached with the system's own ssh, given a vector to run."""

    user: str
    identity: str
    #: How a local process is started. A port rather than a branch: a transport
    #: that took a different path when it was being tested would be testing a
    #: path no deployment runs.
    spawn: Spawn = asyncio.create_subprocess_exec

    def ssh_argv(self, *, node: str, argv: list[str]) -> list[str]:
        """Return the local vector that runs ``argv`` on ``node``."""
        return [
            "ssh",
            *SSH_OPTIONS,
            "-i",
            self.identity,
            f"{self.user}@{node}",
            remote_command(argv),
        ]

    async def run(
        self, *, node: str, argv: list[str], timeout_seconds: float
    ) -> tuple[int, str, str]:
        """Run ``argv`` on ``node`` and return its code, output and error.

        Raises:
            TimeoutError: the node did not finish in time. Raised rather than
                returned so the executor reports it as unreachable, which is a
                different finding from the node having answered unhappily.
        """
        process = await self.spawn(
            *self.ssh_argv(node=node, argv=argv),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise

        return (
            process.returncode or 0,
            out.decode("utf-8", "replace").strip(),
            err.decode("utf-8", "replace").strip(),
        )


__all__ = ["SSH_OPTIONS", "OpenSshRunner", "Spawn", "remote_command"]
