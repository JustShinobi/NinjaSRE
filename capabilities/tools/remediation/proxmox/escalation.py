"""When a graceful shutdown has not worked, and what happens instead.

A restart is not one action. Asking a guest's operating system to close its files
is middle-risk and undone by starting it again; cutting the power on a running
database loses whatever it had not written. Treating them as one action means an
operator permitting the first has permitted the second, which is not what
anybody means by "you may restart guests".

So the escalation is modelled rather than performed. This module decides whether
one is *due* — the graceful attempt finished, the guest is still running, and the
declared timeout has passed — and returns it as a proposal for the hard stop,
carrying its own risk class and the reason it is being asked for. Nothing here
writes; what does is the hard-stop capability, through the gate, with its own
approval.

**Slow is not stuck.** A guest that shuts down cleanly and takes twenty minutes
is a guest that is working. While Proxmox reports the shutdown task still
running, no escalation is due however long it has been — the timeout is measured
against an attempt that has *finished*, not against the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation.proxmox.risk import class_of
from config.constants.hypervisor import HARD_STOP_ESCALATION_SECONDS
from integrations.proxmox.models import GuestStatus, TaskRecord
from platform.autonomy.risk import RiskClass

#: The two capabilities the escalation runs between. Named rather than passed,
#: because which action escalates to which is the decision this module records.
GRACEFUL = "proxmox_shutdown_guest"
FORCEFUL = "proxmox_stop_guest"


@dataclass(frozen=True, slots=True)
class Escalation:
    """The hard stop a graceful shutdown did not achieve, as a separate proposal.

    Carries the class of the *hard stop* rather than of the shutdown that led to
    it. That is the whole point of modelling it: the first may be autonomous
    under an operator's policy and the second may not, and an escalation that
    inherited the first's class would launder one into the other.
    """

    guest: str
    from_capability: str
    to_capability: str
    after_seconds: int
    reason: str
    attempt: str = ""

    @property
    def risk_class(self) -> RiskClass:
        """Return the class of the action being escalated *to*."""
        return class_of(self.to_capability)

    @property
    def escalates(self) -> bool:
        """Return whether this raises the risk class, which it always should."""
        return self.risk_class.rank > class_of(self.from_capability).rank

    def describe(self) -> str:
        """Return the sentence recorded against the incident and shown for approval."""
        return (
            f"{self.from_capability} on {self.guest} did not stop it within "
            f"{self.after_seconds}s, so {self.to_capability} is proposed instead. It is "
            f"{self.risk_class.value} rather than {class_of(self.from_capability).value}: "
            f"{self.reason}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the incident timeline carries."""
        return {
            "guest": self.guest,
            "from_capability": self.from_capability,
            "to_capability": self.to_capability,
            "after_seconds": self.after_seconds,
            "risk_class": self.risk_class.value,
            "attempt": self.attempt,
            "reason": self.reason,
        }


def escalation_for(
    guest: GuestStatus,
    *,
    attempt: TaskRecord,
    waited_seconds: int,
    timeout_seconds: int = HARD_STOP_ESCALATION_SECONDS,
) -> Escalation | None:
    """Return the hard stop that is now due, or ``None`` when none is.

    Three ways to get ``None``, and each of them is a case where escalating would
    be wrong:

    * the guest has stopped, so the graceful attempt worked;
    * the attempt is still running, so the guest is shutting down cleanly and
      slowly, and slow is not stuck;
    * the declared timeout has not passed, so nobody has waited long enough to
      say anything.
    """
    if guest.status == "stopped":
        return None
    if not attempt.finished:
        return None
    if waited_seconds < timeout_seconds:
        return None
    return Escalation(
        guest=guest.display_name,
        from_capability=GRACEFUL,
        to_capability=FORCEFUL,
        after_seconds=waited_seconds,
        attempt=attempt.upid,
        reason=(
            "the guest did not close its own files, so stopping it now discards whatever it "
            "has not written — which is a different act from the one that was approved"
        ),
    )


__all__ = [
    "FORCEFUL",
    "GRACEFUL",
    "Escalation",
    "escalation_for",
]
