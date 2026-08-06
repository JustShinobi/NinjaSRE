"""Removing what nobody is using, safely when several replicas try at once.

Two failure modes cost real money, and they need different detection.

An **expired** sandbox is one whose TTL elapsed. Its owning investigation either
finished or stopped refreshing, and either way nothing is waiting on it. That is
a clock comparison.

An **orphan** is one whose TTL has not elapsed and whose owning run no longer
exists — the agent was killed, the pod was evicted, the process was restarted
mid-investigation. TTL alone would eventually collect these, but "eventually" is
fifteen minutes of a pod per killed agent, and one sweep should be enough. So the
reaper is told which runs are live and treats anything else as an orphan.

**The lease is what makes concurrency safe.** Two replicas sweeping the same
cluster will both see the same expired instance, and both calling delete would
be merely wasteful — but both calling delete on an instance a *third* replica
just claimed would not be. So a reaper takes a lease before it destroys
anything, and the lease is held in the same place the instance is: the cluster
for ``kubernetes``, the runner's own registry for the lighter profiles. A reaper
that dies mid-sweep releases its leases by expiry rather than by cleanup, which
is the only release mechanism a dead process has.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from config.constants.security import SANDBOX_REAPER_LEASE_SECONDS
from platform.observability.logging import get_logger
from platform.sandbox.spec import SandboxProfile
from platform.sandbox.trace import (
    NullSandboxEvents,
    SandboxEvent,
    SandboxEventKind,
    SandboxEventSink,
)

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReapableInstance:
    """The minimum a reaper needs to decide whether something should go.

    Deliberately not a ``SandboxInstance``. The reaper reads what the *source*
    knows — for ``kubernetes`` that is a pod's labels and annotations, which is
    the cluster's own record and outlives any process's memory of it.
    """

    sandbox_id: str
    org_id: str
    investigation_id: str
    expires_at: datetime
    profile: SandboxProfile
    team_id: str = ""
    #: An instance in the warm pool belongs to no investigation and is not an
    #: orphan for as long as its TTL holds.
    pooled: bool = False

    def is_expired(self, *, now: datetime) -> bool:
        """Return whether this instance's TTL has elapsed."""
        return now >= self.expires_at

    def is_orphaned(self, *, live_runs: Collection[str]) -> bool:
        """Return whether the run that owns this instance is gone."""
        if self.pooled:
            return False
        return self.investigation_id not in live_runs


@runtime_checkable
class ReapableSandboxes(Protocol):
    """A source of instances a reaper can enumerate, lease, and destroy.

    Every profile implements this over whatever it already uses to track
    instances, which is why there is no repository port behind it. The cluster
    is the source of truth for ``kubernetes``; inventing a second one in
    Postgres would create two records that can disagree, and the one the reaper
    trusted would be the one that was wrong.
    """

    async def list_reapable(self) -> tuple[ReapableInstance, ...]:
        """Return every instance this source currently knows about."""

    async def acquire_lease(
        self, sandbox_id: str, *, holder: str, lease_seconds: float, now: datetime
    ) -> bool:
        """Return whether ``holder`` now owns the right to destroy ``sandbox_id``.

        False when another holder's lease is still live. Must be atomic against
        a concurrent call from another replica — a compare-and-set on the
        cluster's own record, not a read followed by a write.
        """

    async def destroy(self, sandbox_id: str) -> None:
        """Remove ``sandbox_id`` and everything it held. Idempotent."""


@dataclass(frozen=True, slots=True)
class ReapReport:
    """What one sweep did, in the terms an operator asks about."""

    swept_at: datetime
    examined: int = 0
    expired: tuple[str, ...] = ()
    orphaned: tuple[str, ...] = ()
    skipped_leased: tuple[str, ...] = ()
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def destroyed(self) -> tuple[str, ...]:
        """Return every sandbox this sweep removed."""
        return self.expired + self.orphaned

    @property
    def clean(self) -> bool:
        """Return whether the sweep finished with nothing left to collect."""
        return not self.failures

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "swept_at": self.swept_at.isoformat(),
            "examined": self.examined,
            "expired": list(self.expired),
            "orphaned": list(self.orphaned),
            "skipped_leased": list(self.skipped_leased),
            "failures": list(self.failures),
        }


class Reaper:
    """Sweeps a source of sandboxes, safely alongside other reapers.

    ``holder`` identifies this replica in a lease. It defaults to a fresh UUID
    rather than a hostname because two replicas on one host would otherwise
    share an identity and each would happily take the other's lease — which is
    exactly the case the lease exists to prevent.
    """

    __slots__ = ("_events", "_holder", "_lease_seconds", "_source")

    def __init__(
        self,
        source: ReapableSandboxes,
        *,
        holder: str = "",
        lease_seconds: float = SANDBOX_REAPER_LEASE_SECONDS,
        events: SandboxEventSink | None = None,
    ) -> None:
        self._source = source
        self._holder = holder or f"reaper-{uuid.uuid4()}"
        self._lease_seconds = lease_seconds
        self._events = events if events is not None else NullSandboxEvents()

    @property
    def holder(self) -> str:
        """Return the identity this reaper takes leases under."""
        return self._holder

    async def sweep(
        self, *, live_runs: Collection[str] = (), now: datetime | None = None
    ) -> ReapReport:
        """Destroy every expired and orphaned instance this reaper can lease.

        ``live_runs`` is what makes orphan detection possible: a caller that
        passes nothing gets expiry-based reaping alone, which is correct but
        slow. Passing the set of running investigations is what turns a killed
        agent into a single sweep's worth of cleanup rather than a TTL's.
        """
        at = now if now is not None else datetime.now(UTC)
        instances = await self._source.list_reapable()

        expired: list[str] = []
        orphaned: list[str] = []
        skipped: list[str] = []
        failures: list[str] = []

        for instance in instances:
            is_expired = instance.is_expired(now=at)
            is_orphan = not is_expired and instance.is_orphaned(live_runs=live_runs)
            if not is_expired and not is_orphan:
                continue

            leased = await self._source.acquire_lease(
                instance.sandbox_id,
                holder=self._holder,
                lease_seconds=self._lease_seconds,
                now=at,
            )
            if not leased:
                skipped.append(instance.sandbox_id)
                continue

            try:
                await self._source.destroy(instance.sandbox_id)
            except Exception as error:  # noqa: BLE001 — one bad instance must not
                # end the sweep; the rest of the cluster still needs collecting,
                # and the failure is reported rather than swallowed.
                failures.append(f"{instance.sandbox_id}: {error}")
                _logger.warning(
                    "sandbox.reaper.destroy_failed",
                    sandbox_id=instance.sandbox_id,
                    error=str(error),
                )
                continue

            (expired if is_expired else orphaned).append(instance.sandbox_id)
            await self._events.record(
                SandboxEvent(
                    kind=(SandboxEventKind.EXPIRED if is_expired else SandboxEventKind.REAPED),
                    sandbox_id=instance.sandbox_id,
                    profile=instance.profile,
                    org_id=instance.org_id,
                    team_id=instance.team_id,
                    investigation_id=instance.investigation_id,
                    occurred_at=at,
                    reason="ttl elapsed" if is_expired else "owning run no longer exists",
                )
            )

        return ReapReport(
            swept_at=at,
            examined=len(instances),
            expired=tuple(expired),
            orphaned=tuple(orphaned),
            skipped_leased=tuple(skipped),
            failures=tuple(failures),
        )


__all__ = [
    "ReapReport",
    "ReapableInstance",
    "ReapableSandboxes",
    "Reaper",
]
