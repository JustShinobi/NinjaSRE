"""What a sandbox is asked for: bounds, egress, lifetime, and content.

One request object for all three profiles. That is the point of the feature —
a capability's behaviour must not depend on where the deployment runs it — so
everything a profile needs is declared here and nothing is passed as a
profile-specific extra. Three enforcement mechanisms, one description.

**``EgressPolicy`` is derived, not written.** Its hosts are the union of the
``InjectionRule.hosts`` of the integrations a team has configured, which is the
same tuple the credential proxy checks a request against. There is no second
allow-list to keep in step with the first, so adding an integration widens both
by construction and removing one narrows both. The proxy itself is always
reachable, because a sandbox that cannot reach the proxy is a sandbox that
cannot make an authenticated call at all.

**Limits are values, not policy.** ``ResourceLimits.defaults()`` reads the
constants tier; a spec may narrow them for a capability that declares a smaller
appetite, and ``narrowed_to`` is the only way to do it — a spec cannot widen a
limit past the deployment's ceiling, because the ceiling is what the operator
agreed to and a capability is not the thing that gets to raise it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from config.constants.security import (
    SANDBOX_CONTENT_MOUNT_PATH,
    SANDBOX_CPU_SECONDS_LIMIT,
    SANDBOX_MAX_PROCESSES,
    SANDBOX_MEMORY_BYTES_LIMIT,
    SANDBOX_PROFILE_CONTAINER,
    SANDBOX_PROFILE_KUBERNETES,
    SANDBOX_PROFILE_PROCESS,
    SANDBOX_SCRATCH_BYTES_LIMIT,
    SANDBOX_SCRATCH_MOUNT_PATH,
    SANDBOX_TTL_SECONDS,
    SANDBOX_WALL_CLOCK_SECONDS_LIMIT,
)
from platform.credentials.proxy.injection import InjectionRule
from platform.sandbox.content import ContentBundle


class SandboxProfile(StrEnum):
    """Where capability execution runs in this deployment.

    Deployment-wide. A per-capability profile would mean a capability's
    isolation depended on which tool the model happened to pick, which is not a
    property anybody could reason about while an incident is running.
    """

    PROCESS = SANDBOX_PROFILE_PROCESS
    CONTAINER = SANDBOX_PROFILE_CONTAINER
    KUBERNETES = SANDBOX_PROFILE_KUBERNETES


class LimitKind(StrEnum):
    """Which bound terminated an execution.

    A closed set, because the structured error names one of these and
    an operator's next action depends on which: raise the ceiling, or fix the
    capability that is looping.
    """

    CPU_SECONDS = "cpu_seconds"
    MEMORY_BYTES = "memory_bytes"
    WALL_CLOCK_SECONDS = "wall_clock_seconds"
    SCRATCH_BYTES = "scratch_bytes"
    PROCESS_COUNT = "process_count"

    @property
    def description(self) -> str:
        """Return the human phrase an error message uses for this bound."""
        return _LIMIT_DESCRIPTIONS[self]

    def render(self, value: float) -> str:
        """Return ``value`` in the unit this bound is measured in."""
        if self in (LimitKind.MEMORY_BYTES, LimitKind.SCRATCH_BYTES):
            return f"{value / (1024 * 1024):.0f}MiB"
        if self is LimitKind.PROCESS_COUNT:
            return f"{int(value)} processes"
        return f"{value:g}s"


_LIMIT_DESCRIPTIONS: dict[LimitKind, str] = {
    LimitKind.CPU_SECONDS: "CPU budget",
    LimitKind.MEMORY_BYTES: "memory ceiling",
    LimitKind.WALL_CLOCK_SECONDS: "wall-clock budget",
    LimitKind.SCRATCH_BYTES: "scratch quota",
    LimitKind.PROCESS_COUNT: "process ceiling",
}


#: Which field of ``ResourceLimits`` holds each bound. A mapping rather than a
#: name match, because the field reads better as ``max_processes`` and the bound
#: reads better as ``process_count`` — and an implicit ``getattr`` on the enum's
#: value would tie the two spellings together silently.
_LIMIT_FIELDS: dict[LimitKind, str] = {
    LimitKind.CPU_SECONDS: "cpu_seconds",
    LimitKind.MEMORY_BYTES: "memory_bytes",
    LimitKind.WALL_CLOCK_SECONDS: "wall_clock_seconds",
    LimitKind.SCRATCH_BYTES: "scratch_bytes",
    LimitKind.PROCESS_COUNT: "max_processes",
}


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """The five bounds every profile enforces.

    CPU and wall clock are separate on purpose. A capability that spends a
    minute on the CPU is looping; one that spends a minute waiting on a slow
    vendor is doing its job, and a single timeout would either kill the second
    or fail to notice the first.
    """

    cpu_seconds: int = SANDBOX_CPU_SECONDS_LIMIT
    memory_bytes: int = SANDBOX_MEMORY_BYTES_LIMIT
    wall_clock_seconds: float = SANDBOX_WALL_CLOCK_SECONDS_LIMIT
    scratch_bytes: int = SANDBOX_SCRATCH_BYTES_LIMIT
    max_processes: int = SANDBOX_MAX_PROCESSES

    def __post_init__(self) -> None:
        for name in ("cpu_seconds", "memory_bytes", "wall_clock_seconds", "max_processes"):
            if getattr(self, name) <= 0:
                raise ValueError(
                    f"{name} must be positive: a non-positive limit is not 'unbounded', "
                    f"it is a sandbox nothing can run in"
                )
        if self.scratch_bytes < 0:
            raise ValueError("scratch_bytes must not be negative")

    @classmethod
    def defaults(cls) -> ResourceLimits:
        """Return the deployment ceiling, as the constants tier declares it."""
        return cls()

    def value_of(self, limit: LimitKind) -> float:
        """Return this spec's bound for ``limit``, in that bound's own unit."""
        return float(getattr(self, _LIMIT_FIELDS[limit]))

    def narrowed_to(self, other: ResourceLimits) -> ResourceLimits:
        """Return the tighter of each bound, pairwise.

        Only ever tightens. A capability declaring it needs four gigabytes does
        not get four gigabytes; it gets the deployment's ceiling and a
        capability that fails against it, which is the conversation the operator
        should be having rather than the one where a tool silently raised its
        own limit.
        """
        return ResourceLimits(
            cpu_seconds=min(self.cpu_seconds, other.cpu_seconds),
            memory_bytes=min(self.memory_bytes, other.memory_bytes),
            wall_clock_seconds=min(self.wall_clock_seconds, other.wall_clock_seconds),
            scratch_bytes=min(self.scratch_bytes, other.scratch_bytes),
            max_processes=min(self.max_processes, other.max_processes),
        )


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    """Where a sandbox may send a packet: the proxy, and the declared hosts.

    ``proxy_url`` is not optional and has no default. Every authenticated call
    goes through the credential proxy, so a policy without one describes a
    sandbox that can reach vendors but not the thing that authenticates them —
    which is either a mistake or a deployment that has just reinvented putting
    credentials in the agent.
    """

    proxy_url: str
    hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        split = urlsplit(self.proxy_url)
        if not split.scheme or not split.hostname:
            raise ValueError(
                f"{self.proxy_url!r} is not an absolute URL, so a sandbox built from "
                f"this policy would have no proxy to route through"
            )
        object.__setattr__(self, "hosts", tuple(dict.fromkeys(h.lower() for h in self.hosts)))

    @classmethod
    def from_injection_rules(
        cls, rules: Iterable[InjectionRule], *, proxy_url: str
    ) -> EgressPolicy:
        """Return the policy implied by the integrations a team has configured.

        The union of every rule's declared hosts, which is the same tuple the
        proxy enforces its own allow-list from. One source
        of truth, three enforcement mechanisms — so an integration added to a
        team widens the sandbox's egress and the proxy's in the same edit.
        """
        hosts: list[str] = []
        for rule in rules:
            hosts.extend(rule.hosts)
        return cls(proxy_url=proxy_url, hosts=tuple(hosts))

    @property
    def proxy_host(self) -> str:
        """Return the host the credential proxy is reachable at."""
        return urlsplit(self.proxy_url).hostname or ""

    @property
    def proxy_port(self) -> int:
        """Return the proxy's port, defaulted from its scheme."""
        split = urlsplit(self.proxy_url)
        if split.port is not None:
            return split.port
        return 443 if split.scheme == "https" else 80

    @property
    def proxy_is_loopback(self) -> bool:
        """Return whether the proxy lives on this host's loopback interface.

        Load-bearing for the ``process`` profile: a loopback proxy is the case
        where a network namespace with only ``lo`` in it is both the strongest
        available isolation *and* still lets the sandbox authenticate. A remote
        proxy makes those two goals pull against each other.
        """
        return self.proxy_host in _LOOPBACK_HOSTS

    def permits(self, host: str) -> bool:
        """Return whether ``host`` is the proxy or an allow-listed vendor.

        Exact match, case-insensitively, and no wildcards — for the same reason
        the proxy has none. ``*.vendor.com`` is one acquisition away from
        permitting a host the operator never approved.
        """
        candidate = host.lower()
        return candidate == self.proxy_host.lower() or candidate in self.hosts

    def reachable(self) -> tuple[str, ...]:
        """Return every host this sandbox may address, proxy first."""
        return (self.proxy_host, *(h for h in self.hosts if h != self.proxy_host.lower()))


#: Spelled out rather than pattern-matched, so widening it is an edit somebody
#: has to justify — the same reasoning as the proxy's own loopback exception.
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """One sandbox as it is asked for, before any profile has made it real.

    ``investigation_id`` is what makes a sandbox single-tenant: it is
    stamped on the instance, checked on claim, and is how the reaper recognises
    an orphan whose owning run is gone.
    """

    org_id: str
    team_id: str
    investigation_id: str
    egress: EgressPolicy
    limits: ResourceLimits = field(default_factory=ResourceLimits.defaults)
    content: ContentBundle = field(default_factory=ContentBundle.empty)
    ttl_seconds: int = SANDBOX_TTL_SECONDS
    scratch_path: str = SANDBOX_SCRATCH_MOUNT_PATH
    content_path: str = SANDBOX_CONTENT_MOUNT_PATH
    image: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("org_id", "team_id", "investigation_id"):
            if not getattr(self, name):
                raise ValueError(
                    f"a sandbox spec needs an {name}: an instance that belongs to "
                    f"nobody cannot be scoped, claimed, or reaped"
                )
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive; every sandbox has a lifetime")
        object.__setattr__(self, "labels", dict(self.labels))

    def expires_at(self, *, now: datetime | None = None) -> datetime:
        """Return when a sandbox provisioned at ``now`` would expire."""
        at = now if now is not None else datetime.now(UTC)
        return at + timedelta(seconds=self.ttl_seconds)

    def with_limits(self, limits: ResourceLimits) -> SandboxSpec:
        """Return a copy bounded by the tighter of this spec's limits and ``limits``."""
        return replace(self, limits=self.limits.narrowed_to(limits))

    def with_content(self, content: ContentBundle) -> SandboxSpec:
        """Return a copy delivering ``content`` read-only into the sandbox."""
        return replace(self, content=content)


__all__ = [
    "EgressPolicy",
    "LimitKind",
    "ResourceLimits",
    "SandboxProfile",
    "SandboxSpec",
]
