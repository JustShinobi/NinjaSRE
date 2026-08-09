"""The push outward that makes the guardian's own death detectable.

A guardian that has stopped looks exactly like a cluster with no problems. That
sentence is the whole module. Every other failure in this system produces a
signal; this one produces silence, and silence is indistinguishable from the
outcome everybody is hoping for.

The case is not hypothetical. On the cluster this wave was built for, both nodes
lost networking after a kernel upgrade renamed their interfaces. Prometheus,
Alertmanager, Grafana, the blackbox exporter and Loki were all containers on one
of those nodes. **Not one alert fired.** The outage was discovered by a person
noticing that nothing responded, and diagnosed by carrying a keyboard and a
monitor to the machines. That cluster's own remediation plan still lists an
external dead-man's switch as its top open action.

So: an outbound push, on an interval, to a destination the operator picks. It
carries nothing sensitive — a timestamp, a sequence number, whether the last
tick was healthy, and how many incidents are open — because its value is
entirely in arriving. What watches for it is outside this system by definition;
what this module guarantees is that it goes.

**There is no setting that turns it off while the guardian is enabled.** FR-028
says so and it is right: a switch to disable the dead-man's switch is a switch
that gets used during the noisy first week and never put back.

**A deployment on the estate it manages with no destination configured is
warned, continuously.** That combination — FR-029 — is the exact one in which
the system cannot report its own death, and it is also the default arrangement
of every homelab, which is why it warns rather than assuming somebody read the
documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from config.constants.guardian import (
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_MISSED_INTERVALS,
)


@dataclass(frozen=True, slots=True)
class Heartbeat:
    """One outbound push, and everything it is allowed to carry.

    Deliberately small and deliberately dull. A heartbeat that carried the
    estate's shape would be an inventory leaving the operator's network on a
    fifteen-minute schedule, and the destination is usually a third party. The
    counts are the most it says.
    """

    sequence: int
    at: datetime
    healthy: bool = True
    open_incidents: int = 0
    #: Set when the deployment knows something is wrong with itself, so the
    #: watcher can tell "still alive and unhappy" from "still alive".
    degraded_because: str = ""
    deployment_name: str = "ninjasre"

    def to_payload(self) -> dict[str, Any]:
        """Return what is actually sent, which is this and nothing else."""
        return {
            "deployment": self.deployment_name,
            "sequence": self.sequence,
            "at": self.at.isoformat(),
            "healthy": self.healthy,
            "open_incidents": self.open_incidents,
            "degraded_because": self.degraded_because,
        }


@dataclass(frozen=True, slots=True)
class HeartbeatSchedule:
    """When the next push is due, and when silence should be believed.

    Two intervals rather than one. Concluding the guardian has stopped after a
    single missed push would raise an alarm every time the host restarts, and an
    external watcher that cried wolf on every reboot is one the operator mutes —
    at which point the dead-man's switch is off and looks on.
    """

    interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS
    missed_intervals: int = HEARTBEAT_MISSED_INTERVALS

    def next_due(self, after: datetime) -> datetime:
        """Return when the next heartbeat should be pushed."""
        return after + timedelta(seconds=self.interval_seconds)

    def is_overdue(self, *, last_seen: datetime, now: datetime) -> bool:
        """Return whether an external watcher should conclude the guardian stopped."""
        return now - last_seen > timedelta(seconds=self.interval_seconds * self.missed_intervals)

    def describe_for_watcher(self) -> str:
        """Return the sentence an operator gives whatever is watching for this."""
        minutes = int(self.interval_seconds // 60)
        return (
            f"This deployment pushes a heartbeat every {minutes} minutes. Alert if more "
            f"than {int(self.interval_seconds * self.missed_intervals // 60)} minutes pass "
            f"with no push: that is {self.missed_intervals} missed intervals, which "
            f"survives a restart and does not survive the guardian stopping."
        )


@dataclass(frozen=True, slots=True)
class HeartbeatReadiness:
    """Whether this deployment can report its own death, and what to do if not.

    The check FR-029 asks for, in one value. It is asked at setup and again on
    every health report, because the answer changes: an operator who moves the
    deployment onto the cluster it watches has changed it without touching any
    configuration.
    """

    destination_configured: bool
    #: Whether the deployment is running on the infrastructure it manages.
    on_managed_estate: bool

    @property
    def can_report_its_own_death(self) -> bool:
        """Return whether anything outside this deployment would notice it stopping."""
        return self.destination_configured

    @property
    def is_the_dangerous_combination(self) -> bool:
        """Return whether this is the arrangement FR-029 names.

        Running on the estate it manages *and* with nowhere to push. Either
        alone is survivable; together, the failure that takes the estate down
        takes the only thing that would report it, and nothing is left.
        """
        return self.on_managed_estate and not self.destination_configured

    def warning(self) -> str:
        """Return the warning shown at setup and continuously, or an empty string."""
        if not self.is_the_dangerous_combination:
            if self.destination_configured:
                return ""
            return (
                "No external heartbeat destination is configured, so nothing outside this "
                "deployment would notice if it stopped. A dead-man's-switch URL is enough."
            )
        return (
            "This deployment is running on the infrastructure it manages, and no external "
            "heartbeat destination is configured. That is the one combination in which it "
            "cannot report its own death: the failure that takes the cluster down takes "
            "this with it, and the message that would have told you is the one that never "
            "arrives. It is not a hypothetical — it is how the worst outage on a cluster "
            "of this shape went undetected until somebody noticed nothing was responding. "
            "Set a heartbeat destination: any URL that something outside the cluster "
            "watches will do."
        )

    def to_record(self) -> dict[str, Any]:
        """Return what a health report and the setup flow both render."""
        return {
            "destination_configured": self.destination_configured,
            "on_managed_estate": self.on_managed_estate,
            "can_report_its_own_death": self.can_report_its_own_death,
            "warning": self.warning(),
        }


class HeartbeatUndeliverable(Exception):
    """The heartbeat did not land.

    Raised rather than swallowed. A dead-man's switch whose own failures were
    silent would be a second copy of the problem it exists to catch, and the
    caller — whatever drives the deployment's clock — is the thing that can
    decide whether to retry, log, or surface it.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@runtime_checkable
class HeartbeatTransport(Protocol):
    """Carries one heartbeat outward and reports whether it landed."""

    async def push(self, destination: str, payload: dict[str, Any]) -> None:
        """Send ``payload`` to ``destination``, raising if it did not land."""


@dataclass(slots=True)
class HeartbeatPusher:
    """The thing that actually pushes, and the state that makes a gap visible.

    **It owns no timer.** ``is_due`` answers "should one go now" and ``push``
    sends one; whatever drives the deployment's clock — the scheduler, a loop, a
    test moving time by hand — asks. That is the same shape the escalation
    registry takes, for the same reason: a component with its own timer is a
    component the suite has to sit through.

    **An empty destination is refused at construction.** FR-028 says the
    heartbeat has no configuration that disables it while the guardian is
    enabled, and the only setting there is is *where* to send it. Treating an
    empty one as "off" would be a disable switch wearing a different name.

    **A failed push does not advance the sequence.** Otherwise the watcher sees
    a gap and the deployment believes it pushed, which is the one disagreement
    that matters here.
    """

    transport: HeartbeatTransport
    destination: str
    schedule: HeartbeatSchedule = field(default_factory=HeartbeatSchedule)
    deployment_name: str = "ninjasre"
    sequence: int = 0
    last_pushed_at: datetime | None = None
    consecutive_failures: int = 0
    last_push_landed: bool = False

    def __post_init__(self) -> None:
        if not self.destination.strip():
            raise ValueError(
                "a heartbeat pusher needs a destination. There is no setting that turns "
                "the heartbeat off while the guardian is enabled — the only setting is "
                "where it goes, and an empty one would be a disable switch under another "
                "name. A deployment with nowhere to push should not construct one; "
                "HeartbeatReadiness is what reports that state."
            )
        self.destination = self.destination.strip()

    def is_due(self, at: datetime) -> bool:
        """Return whether a heartbeat should be pushed now.

        The first one is always due. A deployment that had just started and
        waited a full interval before saying anything would be a deployment
        indistinguishable from one that failed to start.
        """
        if self.last_pushed_at is None:
            return True
        return at >= self.schedule.next_due(self.last_pushed_at)

    async def push(
        self,
        *,
        at: datetime,
        open_incidents: int = 0,
        degraded_because: str = "",
    ) -> Heartbeat:
        """Push one heartbeat and return it, or raise ``HeartbeatUndeliverable``."""
        beat = Heartbeat(
            sequence=self.sequence + 1,
            at=at,
            healthy=not degraded_because,
            open_incidents=open_incidents,
            degraded_because=degraded_because,
            deployment_name=self.deployment_name,
        )
        try:
            await self.transport.push(self.destination, beat.to_payload())
        except HeartbeatUndeliverable:
            self.consecutive_failures += 1
            self.last_push_landed = False
            raise

        self.sequence = beat.sequence
        self.last_pushed_at = at
        self.consecutive_failures = 0
        self.last_push_landed = True
        return beat

    def to_record(self) -> dict[str, Any]:
        """Return what a health endpoint says about the heartbeat.

        The destination is deliberately absent. A dead-man's-switch URL is a
        capability token in everything but name — anything holding it can
        convince the watcher this deployment is alive — so the report says
        whether one is configured and never what it is.
        """
        return {
            "pushes": self.sequence,
            "last_pushed_at": self.last_pushed_at.isoformat() if self.last_pushed_at else "",
            "consecutive_failures": self.consecutive_failures,
            "last_push_landed": self.last_push_landed,
            "destination_configured": True,
            "interval_seconds": self.schedule.interval_seconds,
        }


__all__ = [
    "Heartbeat",
    "HeartbeatPusher",
    "HeartbeatReadiness",
    "HeartbeatSchedule",
    "HeartbeatTransport",
    "HeartbeatUndeliverable",
]
