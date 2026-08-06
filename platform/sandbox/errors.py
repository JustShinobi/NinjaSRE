"""What a sandbox refuses, and why — as types a caller can branch on.

Two of these carry the weight of the feature.

``SandboxProvisioningFailed`` is raised and never recovered from inside this
package. There is no unsandboxed path to fall back to, so the only correct
handling is to fail the investigation, and that is easier to get right when the
alternative does not exist. A profile whose runtime is absent raises
``SandboxRuntimeUnavailable``, which is the same failure with the cause named.

``SandboxLimitExceeded`` names *which* limit terminated the execution. "The
capability was killed" and "the capability allocated half a gigabyte" lead to
different operator actions — raise the ceiling, or fix the capability — and a
message that did not distinguish them would send everyone to the first.
Whatever output the capability produced before it was killed rides along: a
truncated traceback is usually the whole diagnosis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `spec` imports `content`, which raises from here — one of the
    # three edges has to be a type-only import, and this is the one that costs
    # nothing at runtime: the error formats a ``LimitKind`` it is handed.
    from platform.sandbox.spec import LimitKind


class SandboxError(Exception):
    """Base for everything this package raises."""


class SandboxProvisioningFailed(SandboxError):
    """A sandbox could not be created, so the work it would have held cannot run."""

    def __init__(self, profile: str, reason: str) -> None:
        self.profile = profile
        self.reason = reason
        super().__init__(
            f"the {profile!r} sandbox profile could not provision a sandbox: {reason}. "
            f"The investigation fails here; there is no unsandboxed path to fall back to."
        )


class SandboxRuntimeUnavailable(SandboxProvisioningFailed):
    """The configured profile needs a runtime this host does not have."""

    def __init__(self, profile: str, runtime: str) -> None:
        self.runtime = runtime
        super().__init__(
            profile,
            f"{runtime} is not available on this host. Install it, or configure a "
            f"profile whose runtime is present — the deployment does not choose one "
            f"for you, because silently choosing the weaker profile is how a "
            f"production deployment ends up with development isolation.",
        )


class SandboxLimitExceeded(SandboxError):
    """Execution was terminated because it crossed one of its bounds."""

    def __init__(
        self,
        limit: LimitKind,
        *,
        sandbox_id: str,
        allowed: float,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> None:
        self.limit = limit
        self.sandbox_id = sandbox_id
        self.allowed = allowed
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"sandbox {sandbox_id} was terminated after exceeding its "
            f"{limit.description} of {limit.render(allowed)}"
        )


class SandboxEgressDenied(SandboxError):
    """A capability addressed a host outside the deployment's allow-list."""

    def __init__(self, host: str, *, sandbox_id: str, allowed: tuple[str, ...]) -> None:
        self.host = host
        self.sandbox_id = sandbox_id
        self.allowed = allowed
        super().__init__(
            f"sandbox {sandbox_id} tried to reach {host!r}, which is not on its egress "
            f"allow-list ({', '.join(allowed) if allowed else 'empty'})"
        )


class SandboxExpired(SandboxError):
    """The sandbox's TTL elapsed before the work using it finished."""

    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id
        super().__init__(
            f"sandbox {sandbox_id} expired. An investigation that is still running "
            f"refreshes its TTL; one that stopped refreshing is one nothing is "
            f"waiting on."
        )


class SandboxNotFound(SandboxError):
    """The sandbox was released, reaped, or never belonged to this profile."""

    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id
        super().__init__(f"sandbox {sandbox_id} does not exist in this profile")


class SandboxInterrupted(SandboxError):
    """Execution was cancelled from outside, and stopped."""

    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id
        super().__init__(f"execution in sandbox {sandbox_id} was interrupted")


class UnknownSandboxProfile(SandboxError):
    """The deployment named a profile that does not exist."""

    def __init__(self, name: str, known: tuple[str, ...]) -> None:
        self.name = name
        self.known = known
        super().__init__(f"{name!r} is not a sandbox profile. Known: {', '.join(known)}.")


class ContentTampered(SandboxError):
    """Delivered capability content no longer matches what was delivered.

    Raised on the way *in* to an execution, not on the way out, because the
    point is that a sandbox cannot modify what it will execute next.
    Detecting it afterwards would report the compromise after it ran.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"{path} does not match the digest it was delivered with, so the content "
            f"this sandbox is about to execute is not the content that was approved"
        )


__all__ = [
    "ContentTampered",
    "SandboxEgressDenied",
    "SandboxError",
    "SandboxExpired",
    "SandboxInterrupted",
    "SandboxLimitExceeded",
    "SandboxNotFound",
    "SandboxProvisioningFailed",
    "SandboxRuntimeUnavailable",
    "UnknownSandboxProfile",
]
