"""The ``container`` profile: a real filesystem and network boundary per sandbox.

The profile most deployments should run. It is the first one where the isolation
does not depend on the capability's cooperation: the root filesystem is read-only
because the kernel says so, the scratch mount is a sized tmpfs, and the network
is a bridge with no route off it. A capability that ignores ``HTTPS_PROXY``
finds there is nowhere else for a packet to go.

The runner owns the *sequence*, and the sequence is the design:

1. A private bridge, created first. A container attached to it later is a
   container that never had a moment of full network access.
2. Host-side scratch and content directories, with content written without a
   write bit before anything mounts it.
3. The container, read-only root, both mounts, all capabilities dropped.
4. Only then is work accepted.

Release is the same list backwards, and it removes the bridge as well as the
container. A bridge per sandbox left behind is a resource leak the reaper would
have to know about, so the release path is what makes the reaper's job only
about containers.
"""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

from platform.sandbox.errors import (
    SandboxExpired,
    SandboxNotFound,
    SandboxProvisioningFailed,
    SandboxRuntimeUnavailable,
)
from platform.sandbox.port import (
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    SandboxInstance,
    SandboxState,
    collect,
)
from platform.sandbox.profiles.container.engine import ContainerEngine
from platform.sandbox.profiles.container.image import container_spec
from platform.sandbox.profiles.container.network import ContainerNetwork, network_for
from platform.sandbox.profiles.process.network import plan_egress
from platform.sandbox.reaper import ReapableInstance
from platform.sandbox.spec import SandboxProfile, SandboxSpec
from platform.sandbox.trace import (
    NullSandboxEvents,
    SandboxEventKind,
    SandboxEventSink,
    event_from,
)


@dataclass(frozen=True, slots=True)
class _Provisioned:
    """What the runner remembers about one live container."""

    instance: SandboxInstance
    spec: SandboxSpec
    network: ContainerNetwork
    root: Path
    container: str


class ContainerSandbox:
    """Runs capability code in a routeless container with a read-only root."""

    __slots__ = ("_engine", "_events", "_state")

    def __init__(
        self,
        *,
        engine: ContainerEngine,
        events: SandboxEventSink | None = None,
    ) -> None:
        self._engine = engine
        self._events = events if events is not None else NullSandboxEvents()
        self._state: dict[str, _Provisioned] = {}

    @property
    def profile(self) -> SandboxProfile:
        """Return which profile this implementation is."""
        return SandboxProfile.CONTAINER

    def network_of(self, instance: SandboxInstance) -> ContainerNetwork:
        """Return the bridge ``instance`` is attached to.

        Exposed so a security test can assert what the sandbox can reach without
        having to infer it from a connection that happened to fail.
        """
        return self._lookup(instance).network

    async def provision(self, spec: SandboxSpec) -> SandboxInstance:
        """Return a container satisfying ``spec``, attached to its own bridge."""
        started = time.monotonic()
        sandbox_id = f"sbx-{uuid.uuid4().hex[:16]}"

        if not await self._engine.available():
            await self._record(SandboxEventKind.PROVISIONING_FAILED, sandbox_id, spec)
            raise SandboxRuntimeUnavailable(str(self.profile), "a container runtime")

        network = network_for(sandbox_id, spec.egress)
        root: Path | None = None
        try:
            await self._engine.create_network(network)
            root = Path(mkdtemp(prefix=f"{sandbox_id}-"))
            scratch = root / "scratch"
            content = root / "content"
            scratch.mkdir(mode=0o700)
            spec.content.materialise(content)

            container = await self._engine.create(
                container_spec(
                    sandbox_id,
                    spec,
                    network=network.name,
                    scratch_source=str(scratch),
                    content_source=str(content),
                    environment=plan_egress(spec.egress, namespace_available=False).environment,
                )
            )
            await self._engine.start(container)
        except SandboxProvisioningFailed:
            await self._unwind(network.name, root)
            await self._record(SandboxEventKind.PROVISIONING_FAILED, sandbox_id, spec)
            raise
        except OSError as error:
            await self._unwind(network.name, root)
            await self._record(SandboxEventKind.PROVISIONING_FAILED, sandbox_id, spec)
            raise SandboxProvisioningFailed(str(self.profile), str(error)) from error

        now = datetime.now(UTC)
        instance = SandboxInstance(
            sandbox_id=sandbox_id,
            profile=self.profile,
            org_id=spec.org_id,
            team_id=spec.team_id,
            investigation_id=spec.investigation_id,
            state=SandboxState.CLAIMED,
            created_at=now,
            expires_at=spec.expires_at(now=now),
            scratch_path=spec.scratch_path,
            content_path=spec.content_path,
            content_digest=spec.content.digest,
            handle=container,
        )
        self._state[sandbox_id] = _Provisioned(
            instance=instance, spec=spec, network=network, root=root, container=container
        )
        await self._record(
            SandboxEventKind.PROVISIONED,
            sandbox_id,
            spec,
            content_digest=spec.content.digest,
            duration_seconds=time.monotonic() - started,
        )
        return instance

    async def execute(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> ExecutionResult:
        """Run ``request`` to completion and return what it produced."""
        return await collect(self.stream(instance, request))

    async def stream(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> AsyncIterator[ExecutionEvent]:
        """Yield output as it arrives, ending with one ``ExecutionCompleted``."""
        provisioned = self._lookup(instance)
        if provisioned.instance.is_expired():
            raise SandboxExpired(instance.sandbox_id)
        provisioned.spec.content.verify(provisioned.root / "content")

        wall_clock = min(
            provisioned.spec.limits.wall_clock_seconds,
            request.timeout_seconds
            if request.timeout_seconds is not None
            else provisioned.spec.limits.wall_clock_seconds,
        )
        await self._record(
            SandboxEventKind.EXECUTION_STARTED,
            instance.sandbox_id,
            provisioned.spec,
            capability=request.command[0],
        )
        started = time.monotonic()
        try:
            async for event in self._engine.exec_stream(
                provisioned.container,
                request,
                limits=provisioned.spec.limits,
                wall_clock_seconds=wall_clock,
                sandbox_id=instance.sandbox_id,
            ):
                yield event
        finally:
            await self._record(
                SandboxEventKind.EXECUTION_FINISHED,
                instance.sandbox_id,
                provisioned.spec,
                capability=request.command[0],
                duration_seconds=time.monotonic() - started,
            )

    async def interrupt(self, instance: SandboxInstance) -> None:
        """Stop whatever this container is running, without destroying it."""
        provisioned = self._state.get(instance.sandbox_id)
        if provisioned is None:
            return
        await self._engine.interrupt(provisioned.container)
        await self._record(SandboxEventKind.INTERRUPTED, instance.sandbox_id, provisioned.spec)

    async def release(self, instance: SandboxInstance) -> None:
        """Destroy the container, its bridge, and its host-side directories."""
        provisioned = self._state.pop(instance.sandbox_id, None)
        if provisioned is None:
            return
        await self._engine.remove(provisioned.container)
        await self._engine.remove_network(provisioned.network.name)
        provisioned.spec.content.release(provisioned.root / "content")
        shutil.rmtree(provisioned.root, ignore_errors=True)
        await self._record(SandboxEventKind.RELEASED, instance.sandbox_id, provisioned.spec)

    async def refresh(self, instance: SandboxInstance) -> SandboxInstance:
        """Push ``instance``'s expiry out by its spec's TTL."""
        provisioned = self._lookup(instance)
        refreshed = replace(
            provisioned.instance, expires_at=provisioned.spec.expires_at(now=datetime.now(UTC))
        )
        self._state[instance.sandbox_id] = replace(provisioned, instance=refreshed)
        await self._record(SandboxEventKind.TTL_REFRESHED, instance.sandbox_id, provisioned.spec)
        return refreshed

    async def list_reapable(self) -> tuple[ReapableInstance, ...]:
        """Return every container this runner is holding, for the reaper."""
        return tuple(
            ReapableInstance(
                sandbox_id=held.instance.sandbox_id,
                org_id=held.instance.org_id,
                team_id=held.instance.team_id,
                investigation_id=held.instance.investigation_id,
                expires_at=held.instance.expires_at,
                profile=self.profile,
            )
            for held in self._state.values()
        )

    async def acquire_lease(
        self, sandbox_id: str, *, holder: str, lease_seconds: float, now: datetime
    ) -> bool:
        """Return whether ``holder`` may destroy ``sandbox_id``.

        Unconditional, and correct for this profile: containers are tracked in
        the process that created them, so a second reaper would be reaping a
        different set. The lease exists for the profile whose instances outlive
        the process.
        """
        return sandbox_id in self._state

    async def destroy(self, sandbox_id: str) -> None:
        """Remove ``sandbox_id`` on the reaper's behalf. Idempotent."""
        provisioned = self._state.get(sandbox_id)
        if provisioned is not None:
            await self.release(provisioned.instance)

    async def _unwind(self, network: str, root: Path | None) -> None:
        """Undo a partial provision, in the reverse order it was built."""
        await self._engine.remove_network(network)
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)

    async def _record(
        self, kind: SandboxEventKind, sandbox_id: str, spec: SandboxSpec, **extra: object
    ) -> None:
        """Record one lifecycle event, with tenancy taken from ``spec``."""
        await self._events.record(
            event_from(
                kind,
                sandbox_id=sandbox_id,
                profile=self.profile,
                scope={
                    "org_id": spec.org_id,
                    "team_id": spec.team_id,
                    "investigation_id": spec.investigation_id,
                },
                **extra,
            )
        )

    def _lookup(self, instance: SandboxInstance) -> _Provisioned:
        """Return this runner's record of ``instance``, or raise ``SandboxNotFound``."""
        provisioned = self._state.get(instance.sandbox_id)
        if provisioned is None:
            raise SandboxNotFound(instance.sandbox_id)
        return provisioned


__all__ = ["ContainerSandbox"]
