"""How much of a deployment scheduled work may occupy, globally and per team.

Two semaphores, and the second one is the interesting one. A global limit alone
protects the platform and not its tenants: one team with forty nightly sweeps
fills every slot at midnight and every other team's schedules queue behind it,
which is a fair-sharing failure that looks exactly like an outage to everybody
but the team causing it.

So a permit needs both, and it takes them **global first, then team**, always in
that order. Two acquirers taking them in opposite orders is the textbook
deadlock, and the way to not have one is for there to be one order rather than a
convention that there is.

Work **queues** rather than being refused. A scheduler that dropped a firing
because the platform was busy would turn a capacity problem into a missed
disaster-recovery validation, and the operator would find out about the second
one much later than the first.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from config.constants.runs import SCHEDULER_GLOBAL_CONCURRENCY, SCHEDULER_TEAM_CONCURRENCY
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ConcurrencyLimits:
    """The permits scheduled runs contend for.

    One object per worker process. The limits are per process rather than per
    deployment, which is the honest thing to say about a semaphore held in
    memory: a deployment's effective ceiling is this times its replica count,
    and a cluster-wide limit would need the same lease machinery the claiming
    uses. The bound that matters — one team cannot swamp the others *here* — is
    the one this delivers.
    """

    global_limit: int = SCHEDULER_GLOBAL_CONCURRENCY
    team_limit: int = SCHEDULER_TEAM_CONCURRENCY
    _global: asyncio.Semaphore | None = field(default=None, repr=False)
    _teams: dict[str, asyncio.Semaphore] = field(default_factory=dict, repr=False)
    _running: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.global_limit < 1 or self.team_limit < 1:
            raise ValueError(
                "A concurrency limit below one would stop every scheduled run. "
                "Disable the schedule instead — that is a decision with a record."
            )
        if self.team_limit > self.global_limit:
            raise ValueError(
                f"A team limit of {self.team_limit} above the global limit of "
                f"{self.global_limit} is not a limit; the global one binds first."
            )

    @property
    def running(self) -> int:
        """Return how many scheduled runs currently hold a permit."""
        return sum(self._running.values())

    def running_for(self, team_node_id: str) -> int:
        """Return how many of ``team_node_id``'s runs currently hold a permit."""
        return self._running.get(team_node_id, 0)

    @contextlib.asynccontextmanager
    async def permit(self, team_node_id: str) -> AsyncIterator[None]:
        """Hold a global and a team permit for the duration of the block.

        Waits rather than refusing. Both are released however the block ends,
        including on the exception a failing investigation raises — a permit
        leaked by a failure is a slot the deployment never gets back.
        """
        team = self._team_semaphore(team_node_id)
        await self._global_semaphore().acquire()
        try:
            await team.acquire()
        except BaseException:
            self._global_semaphore().release()
            raise

        self._running[team_node_id] = self._running.get(team_node_id, 0) + 1
        try:
            yield
        finally:
            remaining = self._running.get(team_node_id, 1) - 1
            if remaining:
                self._running[team_node_id] = remaining
            else:
                self._running.pop(team_node_id, None)
            team.release()
            self._global_semaphore().release()

    def _global_semaphore(self) -> asyncio.Semaphore:
        """Return the deployment-wide semaphore, created on first use.

        Lazily, because ``asyncio.Semaphore`` binds to the running loop and a
        limits object built at import time would bind to whichever loop happened
        to be running then — which in a test suite is a different one per test.
        """
        if self._global is None:
            self._global = asyncio.Semaphore(self.global_limit)
        return self._global

    def _team_semaphore(self, team_node_id: str) -> asyncio.Semaphore:
        """Return ``team_node_id``'s semaphore, created on first use."""
        held = self._teams.get(team_node_id)
        if held is None:
            held = asyncio.Semaphore(self.team_limit)
            self._teams[team_node_id] = held
        return held


__all__ = ["ConcurrencyLimits"]
