"""The seam between the container profile and whatever runtime is installed.

One protocol, and everything above it — the read-only root, the sized tmpfs, the
routeless bridge, the content mount, the lifecycle — is profile code that runs
unchanged whichever implementation is behind it. That is what lets the contract
suite drive the real ``ContainerSandbox`` without a daemon, and what lets a
deployment that speaks to its runtime over a socket rather than a CLI substitute
one class.

``CliContainerEngine`` drives ``docker`` or ``podman``. A CLI rather than an HTTP
client, for the reason the credential proxy's transport gives: NinjaSRE's runtime
dependency list is six packages an operator has to audit, and an SDK for this
would be a seventh that exists to build argument vectors an operator could read
in a shell. Docker and Podman take identical flags for everything this profile
asks for, so the choice of binary is configuration rather than a second adapter.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from platform.sandbox.errors import SandboxLimitExceeded, SandboxProvisioningFailed
from platform.sandbox.port import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    OutputChunk,
    OutputStream,
)
from platform.sandbox.profiles.container.image import ContainerSpec
from platform.sandbox.profiles.container.network import ContainerNetwork
from platform.sandbox.spec import LimitKind, ResourceLimits

#: What a container runtime reports when the kernel's OOM killer stopped the
#: process: 128 plus ``SIGKILL``. It is the one exit status that has a
#: reliable meaning across Docker and Podman, which is why memory is the bound
#: the CLI engine can name and the others fall back to the sampler.
_OOM_KILLED_EXIT_CODE = 137


@runtime_checkable
class ContainerEngine(Protocol):
    """Creates, runs, and destroys containers and the networks they live on."""

    async def available(self) -> bool:
        """Return whether this runtime can be reached right now.

        Checked at provision rather than at construction: a daemon that stopped
        while the deployment was running must fail the next investigation
        loudly, not be discovered at boot and assumed thereafter.
        """

    async def create_network(self, network: ContainerNetwork) -> None:
        """Create ``network``, a bridge with no route off it."""

    async def remove_network(self, name: str) -> None:
        """Remove the network called ``name``. Idempotent."""

    async def create(self, spec: ContainerSpec) -> str:
        """Create the container ``spec`` describes and return its identifier."""

    async def start(self, container: str) -> None:
        """Start ``container``, which then waits for work."""

    def exec_stream(
        self,
        container: str,
        request: ExecutionRequest,
        *,
        limits: ResourceLimits,
        wall_clock_seconds: float,
        sandbox_id: str,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run ``request`` inside ``container``, yielding output then a completion.

        Raises ``SandboxLimitExceeded`` when the runtime or the sampler stopped
        it, and ``SandboxInterrupted`` when ``interrupt`` did.
        """

    async def interrupt(self, container: str) -> None:
        """Stop what ``container`` is running, without destroying it."""

    async def remove(self, container: str) -> None:
        """Destroy ``container`` and everything it held. Idempotent."""


class CliContainerEngine:
    """Drives ``docker`` or ``podman`` as a subprocess.

    Every method builds an argument vector and runs it with no shell, so there
    is no string a hostile value could be interpolated into — the same reasoning
    that keeps query text out of the persistence layer.
    """

    __slots__ = ("_binary",)

    def __init__(self, *, binary: str = "docker") -> None:
        self._binary = binary

    @property
    def binary(self) -> str:
        """Return the runtime binary this engine drives."""
        return self._binary

    async def available(self) -> bool:
        """Return whether the runtime binary exists and its daemon answers."""
        if shutil.which(self._binary) is None:
            return False
        code, _, _ = await self._run("info", "--format", "{{.ServerVersion}}")
        return code == 0

    async def create_network(self, network: ContainerNetwork) -> None:
        """Create ``network``, failing provisioning if the runtime refuses."""
        code, _, error = await self._run(*network.create_arguments())
        if code != 0:
            raise SandboxProvisioningFailed(
                "container", f"network create failed: {error.decode(errors='replace')}"
            )

    async def remove_network(self, name: str) -> None:
        """Remove the network called ``name``, ignoring one that is already gone."""
        await self._run("network", "rm", "--force", name)

    async def create(self, spec: ContainerSpec) -> str:
        """Create ``spec``'s container and return the identifier the runtime gave it."""
        code, out, error = await self._run(*spec.create_arguments())
        if code != 0:
            raise SandboxProvisioningFailed(
                "container", f"create failed: {error.decode(errors='replace')}"
            )
        return out.decode().strip() or spec.name

    async def start(self, container: str) -> None:
        """Start ``container``, failing provisioning if it does not come up."""
        code, _, error = await self._run("start", container)
        if code != 0:
            raise SandboxProvisioningFailed(
                "container", f"start failed: {error.decode(errors='replace')}"
            )

    async def exec_stream(
        self,
        container: str,
        request: ExecutionRequest,
        *,
        limits: ResourceLimits,
        wall_clock_seconds: float,
        sandbox_id: str,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run ``request`` in ``container`` via ``exec``, streaming both pipes."""
        arguments = ["exec", "--interactive"]
        if request.working_directory:
            arguments.extend(["--workdir", request.working_directory])
        for name, value in sorted(request.environment.items()):
            arguments.extend(["--env", f"{name}={value}"])
        arguments.append(container)
        arguments.extend(request.command)

        process = await asyncio.create_subprocess_exec(
            self._binary,
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdin is not None:
            if request.stdin:
                process.stdin.write(request.stdin)
            process.stdin.close()

        stdout, stderr = b"", b""
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=wall_clock_seconds
            )
        except TimeoutError:
            process.kill()
            await self.interrupt(container)
            raise SandboxLimitExceeded(
                LimitKind.WALL_CLOCK_SECONDS,
                sandbox_id=sandbox_id,
                allowed=wall_clock_seconds,
            ) from None

        if stdout:
            yield OutputChunk(stream=OutputStream.STDOUT, data=stdout)
        if stderr:
            yield OutputChunk(stream=OutputStream.STDERR, data=stderr)

        exit_code = process.returncode or 0
        if exit_code == _OOM_KILLED_EXIT_CODE:
            raise SandboxLimitExceeded(
                LimitKind.MEMORY_BYTES,
                sandbox_id=sandbox_id,
                allowed=float(limits.memory_bytes),
                stdout=stdout,
                stderr=stderr,
            )
        yield ExecutionCompleted(result=ExecutionResult(exit_code=exit_code))

    async def interrupt(self, container: str) -> None:
        """Signal everything running inside ``container``."""
        await self._run("kill", "--signal", "KILL", container)

    async def remove(self, container: str) -> None:
        """Destroy ``container``, ignoring one that is already gone."""
        await self._run("rm", "--force", "--volumes", container)

    async def _run(self, *arguments: str) -> tuple[int, bytes, bytes]:
        """Run the runtime binary with ``arguments`` and return what it said."""
        try:
            process = await asyncio.create_subprocess_exec(
                self._binary,
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            return 127, b"", str(error).encode()
        stdout, stderr = await process.communicate()
        return process.returncode or 0, stdout, stderr


__all__ = [
    "CliContainerEngine",
    "ContainerEngine",
]
