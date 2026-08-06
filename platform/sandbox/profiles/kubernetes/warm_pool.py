"""Pods waiting to be claimed, so provisioning is not on the critical path.

Scheduling a pod, pulling an image, and starting Envoy takes seconds. Seconds
per investigation is not a latency problem in the abstract — it is seconds added
to every incident response, at the moment somebody is watching a dashboard go
red. The pool moves that cost off the critical path by paying it in advance.

**The pool is not a cache and an idle instance is not a warm one in the usual
sense.** A pooled pod has never held any investigation's work. It carries no
organisation and no team, its scratch is empty, and claiming it is what gives it
a tenant for the first time. That is what makes single tenancy hold without a "reset"
step to get wrong: there is nothing to reset, because a claimed instance is
never returned to the pool. It is destroyed.

That is the trade this design makes deliberately. Reusing a released pod would
make the pool cheaper and would mean an instance's second tenant inherits
whatever its first one left in a page cache, a temp file, or a process the
runtime did not reap. Destroy-and-replenish costs one pod create per
investigation, off the critical path, and buys a guarantee that does not depend
on the completeness of a cleanup routine.

**Exhaustion is a latency event, not a failure.** A burst larger than the pool
provisions on demand and says so in the health report, because a pool that
refused work under load would convert a slow incident response into no incident
response.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.security import (
    SANDBOX_ORG_LABEL,
    SANDBOX_REAPER_LEASE_SECONDS,
    SANDBOX_STATE_LABEL,
    SANDBOX_TEAM_LABEL,
    SANDBOX_WARM_POOL_SIZE,
)
from platform.observability.logging import get_logger
from platform.sandbox.port import SandboxState
from platform.sandbox.profiles.kubernetes import claims, ttl
from platform.sandbox.profiles.kubernetes.engine import KubernetesApi
from platform.sandbox.spec import SandboxSpec

_logger = get_logger(__name__)

#: What an unclaimed instance is labelled with. Selecting on it is how the pool
#: enumerates its own members without also finding every claimed sandbox.
POOL_LABEL_SELECTOR: Mapping[str, str] = {SANDBOX_STATE_LABEL: str(SandboxState.IDLE)}


@dataclass(frozen=True, slots=True)
class PoolStatus:
    """How much slack the pool currently has, for the health report."""

    size: int
    idle: int

    @property
    def exhausted(self) -> bool:
        """Return whether the next claim would have to provision on demand."""
        return self.size > 0 and self.idle == 0

    @property
    def deficit(self) -> int:
        """Return how many instances replenishment should create."""
        return max(0, self.size - self.idle)


class WarmPool:
    """Keeps a configured number of unclaimed instances ready to be taken.

    Takes a ``provision`` callable rather than building pods itself. The pool's
    concern is *how many*; what one looks like belongs to the runner, and
    splitting them is what lets the pool be reasoned about — and tested —
    without a pod spec in sight.
    """

    __slots__ = ("_api", "_holder", "_provision", "_size")

    def __init__(
        self,
        *,
        api: KubernetesApi,
        provision: object,
        size: int = SANDBOX_WARM_POOL_SIZE,
        holder: str = "",
    ) -> None:
        self._api = api
        self._provision = provision
        self._size = max(0, size)
        self._holder = holder or f"pool-{uuid.uuid4()}"

    @property
    def size(self) -> int:
        """Return how many idle instances this pool aims to hold."""
        return self._size

    @property
    def holder(self) -> str:
        """Return the identity this pool takes claims under."""
        return self._holder

    async def status(self, *, now: datetime | None = None) -> PoolStatus:
        """Return how many instances are idle and claimable right now."""
        at = now if now is not None else datetime.now(UTC)
        idle = await self._idle_pods(now=at)
        return PoolStatus(size=self._size, idle=len(idle))

    async def claim(
        self,
        spec: SandboxSpec,
        *,
        lease_seconds: float = SANDBOX_REAPER_LEASE_SECONDS,
        now: datetime | None = None,
    ) -> claims.Claim | None:
        """Bind an idle instance to ``spec``, or return ``None`` if none was free.

        Tries each candidate in turn rather than the first: a losing
        compare-and-set means another replica took that one, not that the pool
        is empty, and giving up after one attempt would send a request to
        on-demand provisioning while three idle pods sat there.
        """
        at = now if now is not None else datetime.now(UTC)
        for pod in await self._idle_pods(now=at):
            metadata = pod.get("metadata")
            name = str(metadata.get("name", "")) if isinstance(metadata, dict) else ""
            if not name:
                continue
            claim = await claims.bind(
                self._api,
                name,
                spec,
                holder=self._holder,
                lease_seconds=lease_seconds,
                now=at,
            )
            if claim is not None:
                return claim
        return None

    async def replenish(self, *, now: datetime | None = None) -> int:
        """Create instances until the pool is back at size, and return how many.

        Failures are counted rather than raised. Replenishment runs in the
        background and a cluster that is briefly out of capacity should leave
        the pool short, not take down the caller — the next investigation
        provisions on demand and the health report shows the deficit.
        """
        status = await self.status(now=now)
        created = 0
        for _ in range(status.deficit):
            try:
                await self._create_idle()
            except Exception as error:  # noqa: BLE001 — one failure must not stop the rest
                _logger.warning("sandbox.pool.replenish_failed", error=str(error))
                break
            created += 1
        return created

    async def _create_idle(self) -> None:
        """Create one unclaimed instance belonging to nobody."""
        provision = self._provision
        if not callable(provision):
            raise TypeError("a warm pool needs a callable that provisions one idle instance")
        await provision()

    async def _idle_pods(self, *, now: datetime) -> tuple[Mapping[str, Any], ...]:
        """Return the pods that are idle, unexpired, and belong to no tenant."""
        pods = await self._api.list_pods(label_selector=dict(POOL_LABEL_SELECTOR))
        return tuple(pod for pod in pods if _is_idle(pod, now=now) and claims.claim_of(pod) is None)


def _is_idle(pod: Mapping[str, Any], *, now: datetime) -> bool:
    """Return whether ``pod`` is a live pool member that has never been claimed."""
    metadata = pod.get("metadata")
    if not isinstance(metadata, dict):
        return False
    if ttl.is_expired(metadata, now=now):
        return False
    labels = metadata.get("labels") or {}
    if not isinstance(labels, dict):
        return False
    if labels.get(SANDBOX_STATE_LABEL) != str(SandboxState.IDLE):
        return False
    # A pooled instance carries no tenant. One that does has been claimed, and a
    # claimed instance never returns to the pool — it is destroyed on release.
    return not labels.get(SANDBOX_ORG_LABEL) and not labels.get(SANDBOX_TEAM_LABEL)


__all__ = [
    "POOL_LABEL_SELECTOR",
    "PoolStatus",
    "WarmPool",
]
