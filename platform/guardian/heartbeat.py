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

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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


__all__ = ["Heartbeat", "HeartbeatReadiness", "HeartbeatSchedule"]
