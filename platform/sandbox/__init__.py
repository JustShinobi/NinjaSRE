"""Where capability execution runs, what it may reach, and what it may consume.

One port, three profiles. ``process`` for a contributor with neither a container
runtime nor a cluster, ``container`` for a team, ``kubernetes`` for a deployment
that has to defend its isolation in a security review. All three pass the same
contract suite, which is what lets everything above this package hold a
``Sandbox`` without asking which one it got.

Because the credential proxy already took credentials out of the agent's reach, this
package is about resource bounds and egress rather than secret containment —
and that is precisely what makes the lighter profiles safe enough to be worth
having. A profile that nobody runs locally is a profile that gets bypassed.

Start with ``port.py`` for the shape and ``spec.py`` for what a sandbox is asked
for. ``selection.py`` is how a deployment says which profile it runs, and it has
no path that returns an unsandboxed executor.
"""

from __future__ import annotations

from platform.sandbox.content import ContentBundle, ContentEntry
from platform.sandbox.egress import record_blocked_egress
from platform.sandbox.errors import (
    ContentTampered,
    SandboxEgressDenied,
    SandboxError,
    SandboxExpired,
    SandboxInterrupted,
    SandboxLimitExceeded,
    SandboxNotFound,
    SandboxProvisioningFailed,
    SandboxRuntimeUnavailable,
    UnknownSandboxProfile,
)
from platform.sandbox.health import SandboxHealth, SandboxHealthReport
from platform.sandbox.port import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    OutputChunk,
    OutputStream,
    Sandbox,
    SandboxInstance,
    SandboxState,
    collect,
)
from platform.sandbox.reaper import ReapableInstance, ReapableSandboxes, Reaper, ReapReport
from platform.sandbox.selection import (
    ProfileGuarantees,
    resolve_profile,
    startup_report,
)
from platform.sandbox.spec import (
    EgressPolicy,
    LimitKind,
    ResourceLimits,
    SandboxProfile,
    SandboxSpec,
)
from platform.sandbox.trace import (
    CollectingSandboxEvents,
    SandboxEvent,
    SandboxEventKind,
    SandboxEventSink,
)

__all__ = [
    "CollectingSandboxEvents",
    "ContentBundle",
    "ContentEntry",
    "ContentTampered",
    "EgressPolicy",
    "ExecutionCompleted",
    "ExecutionEvent",
    "ExecutionRequest",
    "ExecutionResult",
    "LimitKind",
    "OutputChunk",
    "OutputStream",
    "ProfileGuarantees",
    "ReapReport",
    "ReapableInstance",
    "ReapableSandboxes",
    "Reaper",
    "ResourceLimits",
    "Sandbox",
    "SandboxEgressDenied",
    "SandboxError",
    "SandboxEvent",
    "SandboxEventKind",
    "SandboxEventSink",
    "SandboxExpired",
    "SandboxHealth",
    "SandboxHealthReport",
    "SandboxInstance",
    "SandboxInterrupted",
    "SandboxLimitExceeded",
    "SandboxNotFound",
    "SandboxProfile",
    "SandboxProvisioningFailed",
    "SandboxRuntimeUnavailable",
    "SandboxSpec",
    "SandboxState",
    "UnknownSandboxProfile",
    "collect",
    "record_blocked_egress",
    "resolve_profile",
    "startup_report",
]
