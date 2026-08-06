"""The ``process`` profile: a subprocess, confined by what the host will confine.

The profile that exists so isolation is not something contributors turn off. A
sandbox that required Kubernetes locally would be a sandbox nobody ran locally,
and code written against no sandbox is code that only meets one in production.

What it provides is real and bounded. A private scratch directory per instance,
a fresh session so the whole process group can be signalled as a unit, an
environment built from nothing rather than inherited, POSIX rlimits or Windows
Job Objects on every bound, a sampler that names which bound was crossed, and —
where the kernel allows it and the proxy is on loopback — a network namespace
containing only ``lo``.

What it does not provide is a mount namespace. Two concurrent sandboxes have
different scratch directories with unguessable names and neither is told where
the other's is, but on a shared filesystem a process that went looking could
find one. That is the honest boundary of this profile, it is why
``guarantees_for`` marks it development-only, and it is why the deployment
profiles that carry multiple tenants are the other two.

Credentials do not come into it. The mandatory credential proxy means there is
nothing in this process for a capability to find, which is precisely what makes a profile with
this much isolation — and not more — safe enough to be worth having.
"""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

from platform.sandbox.errors import (
    SandboxExpired,
    SandboxNotFound,
    SandboxProvisioningFailed,
)
from platform.sandbox.port import (
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    SandboxInstance,
    SandboxState,
    collect,
)
from platform.sandbox.profiles.process.execution import (
    LaunchPlan,
    RunningExecution,
    stream_execution,
    terminate,
)
from platform.sandbox.profiles.process.monitor import ResourceMonitor, default_monitor
from platform.sandbox.profiles.process.network import EgressPlan, plan_egress
from platform.sandbox.reaper import ReapableInstance
from platform.sandbox.spec import SandboxProfile, SandboxSpec
from platform.sandbox.trace import (
    NullSandboxEvents,
    SandboxEventKind,
    SandboxEventSink,
    event_from,
)

#: The environment every sandbox starts from: nothing. The proxy variables and
#: whatever the request declares are added on top. Inheriting the agent's
#: environment would be the one way a credential could reach a capability in a
#: deployment that had got everything else right.
_BASE_ENVIRONMENT: dict[str, str] = {}


class ProcessSandbox:
    """Runs capability code as a confined subprocess of this host.

    Holds its instances in memory, which is the correct source of truth for this
    profile: a ``process`` sandbox does not outlive the process that created it,
    so a record of one that did would describe something that no longer exists.
    """

    __slots__ = ("_events", "_monitor", "_namespace_available", "_plans", "_running", "_state")

    def __init__(
        self,
        *,
        events: SandboxEventSink | None = None,
        monitor: ResourceMonitor | None = None,
        namespace_available: bool | None = None,
    ) -> None:
        self._state: dict[str, tuple[SandboxInstance, SandboxSpec, Path]] = {}
        self._plans: dict[str, EgressPlan] = {}
        self._running: dict[str, RunningExecution] = {}
        self._events = events if events is not None else NullSandboxEvents()
        self._monitor = monitor if monitor is not None else default_monitor()
        self._namespace_available = namespace_available

    @property
    def profile(self) -> SandboxProfile:
        """Return which profile this implementation is."""
        return SandboxProfile.PROCESS

    def egress_plan(self, instance: SandboxInstance) -> EgressPlan:
        """Return how ``instance``'s egress is being constrained.

        Exposed because the mechanism varies by host, so "what is this sandbox
        actually enforcing" is a question with a per-instance answer that a
        health report and a security test both need to be able to ask.
        """
        plan = self._plans.get(instance.sandbox_id)
        if plan is None:
            raise SandboxNotFound(instance.sandbox_id)
        return plan

    async def provision(self, spec: SandboxSpec) -> SandboxInstance:
        """Return a confined subprocess environment satisfying ``spec``."""
        started = time.monotonic()
        sandbox_id = f"sbx-{uuid.uuid4().hex[:16]}"
        try:
            root = Path(mkdtemp(prefix=f"{sandbox_id}-"))
            scratch = root / "scratch"
            content = root / "content"
            scratch.mkdir(mode=0o700)
            spec.content.materialise(content)
        except OSError as error:
            await self._events.record(
                event_from(
                    SandboxEventKind.PROVISIONING_FAILED,
                    sandbox_id=sandbox_id,
                    profile=self.profile,
                    scope=_scope(spec),
                    reason=str(error),
                )
            )
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
            scratch_path=str(scratch),
            content_path=str(content),
            content_digest=spec.content.digest,
            handle=str(root),
        )
        self._state[sandbox_id] = (instance, spec, root)
        self._plans[sandbox_id] = plan_egress(
            spec.egress, namespace_available=self._namespace_available
        )

        await self._events.record(
            event_from(
                SandboxEventKind.PROVISIONED,
                sandbox_id=sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
                content_digest=spec.content.digest,
                duration_seconds=time.monotonic() - started,
            )
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
        stored, spec, _ = self._lookup(instance)
        _require_live(stored)

        # On the way *in*, never on the way out: a sandbox must not be able to
        # modify what it will execute next, and a check after the fact would
        # report the compromise once it had already run.
        spec.content.verify(Path(stored.content_path))

        cwd = Path(stored.scratch_path)
        if request.working_directory:
            cwd = cwd / request.working_directory
            cwd.mkdir(parents=True, exist_ok=True)

        plan = LaunchPlan(
            command=request.command,
            cwd=cwd,
            scratch=Path(stored.scratch_path),
            environment={
                **_BASE_ENVIRONMENT,
                **self._plans[stored.sandbox_id].environment,
                **request.environment,
            },
            limits=spec.limits,
            stdin=request.stdin,
            isolate_network_namespace=self._plans[stored.sandbox_id].isolate_network_namespace,
        )
        wall_clock = min(
            spec.limits.wall_clock_seconds,
            request.timeout_seconds
            if request.timeout_seconds is not None
            else spec.limits.wall_clock_seconds,
        )

        await self._events.record(
            event_from(
                SandboxEventKind.EXECUTION_STARTED,
                sandbox_id=stored.sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
                capability=request.command[0],
            )
        )
        started = time.monotonic()
        try:
            async for event in stream_execution(
                plan,
                sandbox_id=stored.sandbox_id,
                monitor=self._monitor,
                wall_clock_seconds=wall_clock,
                register=lambda execution: self._running.__setitem__(stored.sandbox_id, execution),
            ):
                yield event
        finally:
            self._running.pop(stored.sandbox_id, None)
            await self._events.record(
                event_from(
                    SandboxEventKind.EXECUTION_FINISHED,
                    sandbox_id=stored.sandbox_id,
                    profile=self.profile,
                    scope=_scope(spec),
                    capability=request.command[0],
                    duration_seconds=time.monotonic() - started,
                )
            )

    async def interrupt(self, instance: SandboxInstance) -> None:
        """Stop whatever this sandbox is running, without releasing it."""
        execution = self._running.get(instance.sandbox_id)
        if execution is None:
            return
        await execution.cancel()
        stored = self._state.get(instance.sandbox_id)
        if stored is not None:
            await self._events.record(
                event_from(
                    SandboxEventKind.INTERRUPTED,
                    sandbox_id=instance.sandbox_id,
                    profile=self.profile,
                    scope=_scope(stored[1]),
                )
            )

    async def release(self, instance: SandboxInstance) -> None:
        """Kill anything still running and delete everything this sandbox held."""
        stored = self._state.pop(instance.sandbox_id, None)
        self._plans.pop(instance.sandbox_id, None)
        execution = self._running.pop(instance.sandbox_id, None)
        if execution is not None:
            await terminate(execution)
        if stored is None:
            return

        _, spec, root = stored
        spec.content.release(root / "content")
        shutil.rmtree(root, ignore_errors=True)
        await self._events.record(
            event_from(
                SandboxEventKind.RELEASED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
            )
        )

    async def refresh(self, instance: SandboxInstance) -> SandboxInstance:
        """Push ``instance``'s expiry out by its spec's TTL and return the new instance.

        An investigation that is still working says so by refreshing;
        one that stopped is one nothing is waiting on, and the reaper collects
        it. That is why the refresh is explicit rather than implied by activity:
        a capability tailing logs for an hour is active and still bounded.
        """
        stored, spec, root = self._lookup(instance)
        refreshed = SandboxInstance(
            sandbox_id=stored.sandbox_id,
            profile=stored.profile,
            org_id=stored.org_id,
            team_id=stored.team_id,
            investigation_id=stored.investigation_id,
            state=stored.state,
            created_at=stored.created_at,
            expires_at=spec.expires_at(now=datetime.now(UTC)),
            scratch_path=stored.scratch_path,
            content_path=stored.content_path,
            content_digest=stored.content_digest,
            handle=stored.handle,
        )
        self._state[stored.sandbox_id] = (refreshed, spec, root)
        await self._events.record(
            event_from(
                SandboxEventKind.TTL_REFRESHED,
                sandbox_id=stored.sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
            )
        )
        return refreshed

    async def list_reapable(self) -> tuple[ReapableInstance, ...]:
        """Return every instance this runner is holding, for the reaper."""
        return tuple(
            ReapableInstance(
                sandbox_id=instance.sandbox_id,
                org_id=instance.org_id,
                team_id=instance.team_id,
                investigation_id=instance.investigation_id,
                expires_at=instance.expires_at,
                profile=self.profile,
            )
            for instance, _, _ in self._state.values()
        )

    async def acquire_lease(
        self, sandbox_id: str, *, holder: str, lease_seconds: float, now: datetime
    ) -> bool:
        """Return whether ``holder`` may destroy ``sandbox_id``.

        Always true for this profile, and that is correct rather than a stub: a
        ``process`` sandbox lives inside one process, so there is no second
        reaper that could be racing for it. The lease exists for the profile
        where there is.
        """
        return sandbox_id in self._state

    async def destroy(self, sandbox_id: str) -> None:
        """Remove ``sandbox_id`` on the reaper's behalf. Idempotent."""
        stored = self._state.get(sandbox_id)
        if stored is None:
            return
        await self.release(stored[0])

    def _lookup(self, instance: SandboxInstance) -> tuple[SandboxInstance, SandboxSpec, Path]:
        """Return this runner's record of ``instance``, or raise ``SandboxNotFound``."""
        stored = self._state.get(instance.sandbox_id)
        if stored is None:
            raise SandboxNotFound(instance.sandbox_id)
        return stored


def _require_live(instance: SandboxInstance) -> None:
    """Raise ``SandboxExpired`` if ``instance``'s TTL has already elapsed."""
    if instance.is_expired():
        raise SandboxExpired(instance.sandbox_id)


def _scope(spec: SandboxSpec) -> dict[str, str]:
    """Return the tenancy an event carries, taken from one place."""
    return {
        "org_id": spec.org_id,
        "team_id": spec.team_id,
        "investigation_id": spec.investigation_id,
    }


__all__ = ["ProcessSandbox"]
