"""The operations a sandbox has, and the shapes they pass.

Everything above this package holds a ``Sandbox`` and never asks which profile
it got. That is the whole claim of this feature, and the contract suite is what
makes it true rather than intended: one suite, run three times, once per
profile. A capability that passes on ``process`` and fails on ``kubernetes`` is
a gap in the suite, not a difference the caller is expected to handle.

Two shapes here are worth the paragraph they cost.

**Streaming is the primitive and ``execute`` is derived.** ``stream`` yields
output as it arrives and ends with exactly one ``ExecutionCompleted``; ``execute``
is ``collect(stream(...))``, in this module, shared by all three profiles. The
alternative — each profile implementing both — is three chances for buffered and
streamed execution to disagree about exit codes, about which limit fired, and
about whether the last line of stderr made it out.

**A limit is an exception, not a field on the result.** A capability that was
killed did not produce a result; it produced a partial one plus the reason it
stopped, and ``SandboxLimitExceeded`` carries both. Returning it as a normal
result with a flag is how a caller writes ``if result.exit_code == 0`` and
silently treats a memory kill as a clean empty answer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from platform.sandbox.spec import SandboxProfile, SandboxSpec


class SandboxState(StrEnum):
    """Where one instance is in its life.

    ``IDLE`` exists for the warm pool: an instance that is running and healthy
    but bound to no investigation yet. It is a state rather than a separate
    collection so that the reaper, health reporting, and the claim mechanism all
    read one source of truth.
    """

    PROVISIONING = "provisioning"
    IDLE = "idle"
    CLAIMED = "claimed"
    RELEASED = "released"
    FAILED = "failed"

    @property
    def usable(self) -> bool:
        """Return whether work can be submitted to an instance in this state."""
        return self in (SandboxState.IDLE, SandboxState.CLAIMED)


class OutputStream(StrEnum):
    """Which of the two streams a chunk came from."""

    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True)
class SandboxInstance:
    """A provisioned sandbox: what it is, who owns it, and when it expires.

    Immutable, and every lifecycle operation returns a new one. A mutable
    instance shared between the pool, the claim, and the reaper is how two
    replicas end up with different opinions about whether a pod is still
    claimed.
    """

    sandbox_id: str
    profile: SandboxProfile
    org_id: str
    team_id: str
    investigation_id: str
    state: SandboxState
    created_at: datetime
    expires_at: datetime
    scratch_path: str
    content_path: str
    content_digest: str = ""
    #: Whatever the profile needs to address this instance again — a pod name, a
    #: container id, a working directory. Opaque above this package on purpose.
    handle: str = ""

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return whether this instance's TTL has elapsed."""
        at = now if now is not None else datetime.now(UTC)
        return at >= self.expires_at

    def belongs_to(self, spec: SandboxSpec) -> bool:
        """Return whether this instance is already scoped to ``spec``'s tenant.

        The single-tenant guarantee in one predicate: an instance may
        be handed to an investigation only when the organisation and team match,
        and an idle pooled instance matches nobody until it is claimed.
        """
        return self.org_id == spec.org_id and self.team_id == spec.team_id


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """One command to run inside a sandbox.

    ``environment`` is additive over the profile's own minimal environment and
    is never a place for a credential — the sandbox reaches authenticated
    services through the proxy, whose address is the only thing this needs to
    know about them. There is no parameter here that could carry a secret,
    which is the same design the proxy's client uses one tier up.
    """

    command: tuple[str, ...]
    stdin: bytes = b""
    environment: Mapping[str, str] = field(default_factory=dict)
    #: Relative to the scratch mount. Absolute paths are rejected: a working
    #: directory outside the mount is one the read-only root is meant to forbid.
    working_directory: str = ""
    #: Narrows the spec's wall-clock bound for this one call; it never widens it.
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("an execution request needs a command to run")
        if self.working_directory.startswith("/"):
            raise ValueError(
                f"{self.working_directory!r} is absolute. A working directory is "
                f"relative to the sandbox's scratch mount, because a path outside it "
                f"is one the read-only root exists to forbid."
            )
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "environment", dict(self.environment))


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """What one command produced, once it finished on its own terms."""

    exit_code: int
    stdout: bytes = b""
    stderr: bytes = b""
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Return whether the command exited zero."""
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class OutputChunk:
    """Bytes as they arrived, tagged with the stream they came from."""

    stream: OutputStream
    data: bytes


@dataclass(frozen=True, slots=True)
class ExecutionCompleted:
    """The terminal event of a stream, carrying the assembled result."""

    result: ExecutionResult


#: Exactly one ``ExecutionCompleted``, and it is last. A stream that ended
#: without one ended because something else went wrong, and ``collect`` says so
#: rather than inventing an exit code.
ExecutionEvent = OutputChunk | ExecutionCompleted


async def collect(events: AsyncIterator[ExecutionEvent]) -> ExecutionResult:
    """Drain ``events`` and return the completed result with output assembled.

    Shared by every profile's ``execute`` so buffered and streamed execution
    cannot disagree. Raises ``RuntimeError`` when the stream ended without a
    completion, because a missing terminal event is a broken profile rather
    than a command that exited strangely.
    """
    stdout: list[bytes] = []
    stderr: list[bytes] = []
    completion: ExecutionCompleted | None = None

    async for event in events:
        if isinstance(event, OutputChunk):
            if event.stream is OutputStream.STDOUT:
                stdout.append(event.data)
            else:
                stderr.append(event.data)
        else:
            completion = event

    if completion is None:
        raise RuntimeError(
            "a sandbox stream ended without a completion event, so there is no exit "
            "status to report — the profile that produced it is broken"
        )
    return ExecutionResult(
        exit_code=completion.result.exit_code,
        stdout=b"".join(stdout) or completion.result.stdout,
        stderr=b"".join(stderr) or completion.result.stderr,
        duration_seconds=completion.result.duration_seconds,
    )


@runtime_checkable
class Sandbox(Protocol):
    """Provision, execute, stream, interrupt, release, refresh — and nothing else.

    Six operations, and the list is closed. Five are provisioning and execution;
    ``refresh`` is the sixth because a refreshable TTL is part of every sandbox's
    lifecycle rather than an extra some profiles have. Anything a profile needs beyond
    these is configuration it was constructed with — a seventh method is how a
    profile-specific escape hatch gets added and then depended on, at which
    point the contract stops meaning that behaviour is identical.
    """

    @property
    def profile(self) -> SandboxProfile:
        """Return which profile this implementation is."""

    async def provision(self, spec: SandboxSpec) -> SandboxInstance:
        """Return a sandbox satisfying ``spec``, ready to execute.

        Raises ``SandboxProvisioningFailed`` when it cannot. There is no
        degraded return value: a caller that received something less isolated
        than it asked for would have no way to notice.
        """

    async def execute(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> ExecutionResult:
        """Run ``request`` to completion and return what it produced.

        Raises ``SandboxLimitExceeded`` naming the bound that terminated it,
        ``SandboxExpired`` when the instance's TTL has elapsed, and
        ``SandboxNotFound`` when it has already been released.
        """

    def stream(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> AsyncIterator[ExecutionEvent]:
        """Yield output as it arrives, ending with one ``ExecutionCompleted``."""

    async def interrupt(self, instance: SandboxInstance) -> None:
        """Stop whatever ``instance`` is running, promptly and without releasing it.

        Idempotent: interrupting an idle sandbox is a no-op rather than an
        error. Cancellation arrives from outside and races with completion by
        construction, so a caller cannot know which it won.
        """

    async def release(self, instance: SandboxInstance) -> None:
        """Destroy ``instance`` and everything it held.

        Idempotent, because the reaper and the investigation both call it and
        neither knows whether the other got there first.
        """

    async def refresh(self, instance: SandboxInstance) -> SandboxInstance:
        """Push ``instance``'s expiry out by its spec's TTL and return the new handle.

        Explicit rather than implied by activity. "Active" is the wrong
        test in both directions: a capability tailing logs for an hour is active
        and still needs a bound, and an investigation waiting on a human
        approval is idle and must not be collected.
        """


__all__ = [
    "ExecutionCompleted",
    "ExecutionEvent",
    "ExecutionRequest",
    "ExecutionResult",
    "OutputChunk",
    "OutputStream",
    "Sandbox",
    "SandboxInstance",
    "SandboxState",
    "collect",
]
