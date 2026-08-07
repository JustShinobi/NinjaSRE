"""Readiness that names the dependency, because "not ready" is not an answer.

FR-008 asks that health and readiness gate traffic and that readiness report
*which* dependency is not ready. The second half is the one that costs an
on-call engineer an hour when it is missing: a load balancer removing a pod
because ``/ready`` returned 503 tells nobody whether the database is down, the
schema is mid-migration, the credential proxy has not started, or the model
provider is unreachable — and those have four different responses.

So a readiness report is a list of dependencies, each with a state and a reason,
and the overall answer is derived from them rather than reported alongside them.
Two states are worth distinguishing:

- **A required dependency that is not ready blocks traffic.** The database is
  the obvious one: an investigation with nowhere to write its trace has not
  happened, whatever it printed.
- **An optional dependency that is not ready is reported and survived.** The
  graph extension is the example the persistence layer already draws: an
  investigation without a blast radius is a worse investigation, not an
  impossible one, and taking the deployment out of rotation over it would turn
  a degraded service into no service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class DependencyState(StrEnum):
    """Whether one dependency can carry the work that needs it."""

    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

    @property
    def serves(self) -> bool:
        """Return whether work depending on this can proceed."""
        return self in (DependencyState.READY, DependencyState.DEGRADED)


@dataclass(frozen=True, slots=True)
class DependencyReadiness:
    """One dependency, its state, and why it is in it.

    ``required`` is a property of the dependency rather than of the moment.
    Whether the deployment can serve without this is a design decision that was
    made when the dependency was added, and deciding it per probe is how a
    deployment ends up serving without its database once.
    """

    name: str
    state: DependencyState
    required: bool = True
    detail: str = ""

    @property
    def blocks_traffic(self) -> bool:
        """Return whether this dependency's state should stop the deployment serving."""
        return self.required and not self.state.serves

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a readiness endpoint serves."""
        return {
            "name": self.name,
            "state": str(self.state),
            "required": self.required,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.name} is {self.state}{suffix}"


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Every dependency this deployment needs, and whether it should take work."""

    dependencies: tuple[DependencyReadiness, ...] = ()
    observed_at: datetime | None = None
    draining: bool = False

    @property
    def ready(self) -> bool:
        """Return whether this deployment should be sent traffic."""
        return not self.draining and not self.blocking

    @property
    def blocking(self) -> tuple[DependencyReadiness, ...]:
        """Return the dependencies whose state is keeping traffic away."""
        return tuple(entry for entry in self.dependencies if entry.blocks_traffic)

    @property
    def degraded(self) -> tuple[DependencyReadiness, ...]:
        """Return the dependencies that are serving with something missing."""
        return tuple(
            entry
            for entry in self.dependencies
            if entry.state is DependencyState.DEGRADED
            or (not entry.required and not entry.state.serves)
        )

    def named(self, name: str) -> DependencyReadiness | None:
        """Return the dependency called ``name``, or ``None``."""
        for entry in self.dependencies:
            if entry.name == name:
                return entry
        return None

    def reasons(self) -> tuple[str, ...]:
        """Return one sentence per dependency an operator has to act on."""
        return tuple(str(entry) for entry in (*self.blocking, *self.degraded))

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a readiness endpoint serves."""
        return {
            "ready": self.ready,
            "draining": self.draining,
            "dependencies": [entry.to_record() for entry in self.dependencies],
            "blocking": [entry.name for entry in self.blocking],
            "reasons": list(self.reasons()),
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
        }

    def summary(self) -> str:
        """Return the line a probe's failure should have printed in the first place."""
        if self.draining:
            return "not ready: this replica is draining"
        if not self.blocking:
            degraded = self.degraded
            if not degraded:
                return "ready: every dependency is available"
            return f"ready, degraded: {'; '.join(str(entry) for entry in degraded)}"
        return f"not ready: {'; '.join(str(entry) for entry in self.blocking)}"


def report(
    dependencies: tuple[DependencyReadiness, ...],
    *,
    draining: bool = False,
    now: datetime | None = None,
) -> ReadinessReport:
    """Return a readiness report over ``dependencies``, timestamped."""
    return ReadinessReport(
        dependencies=dependencies,
        draining=draining,
        observed_at=now if now is not None else datetime.now(UTC),
    )


__all__ = [
    "DependencyReadiness",
    "DependencyState",
    "ReadinessReport",
    "report",
]
