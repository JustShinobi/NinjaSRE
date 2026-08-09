"""What the operator is told, in the shape a person outside a company can act on.

Four questions, always in the same order, and the third one is the one most
systems leave out.

    What happened.
    What was done about it.
    What was *not* done, and why.
    What is needed from you.

The third exists because this deployment is usually in propose-only, which means
the honest answer to "what was done" is "nothing" — and a notification that said
only that would read as a failure rather than as the posture the operator chose.
"Nothing, because you have it in propose-only, and here is what it would have
done" is a completely different message from the same facts.

**A storm becomes one message.** Not a rate limit — a rate limit says the same
thing by throwing away the later items, and the later items are usually the ones
that explain the earlier ones. A node going down takes twenty guests with it, and
the useful message is "pve01 went down and took these twenty with it", which is
one notification and is also the true shape of the event.

**A resolution is sent even when the original was never read.** The operator was
at work. Arriving home to an alert about a problem that fixed itself four hours
ago is how somebody learns to stop reading them, and the resolution costs one
message.

**Escalation ends.** There is no rota. An escalation that repeats indefinitely
assumes somebody else eventually picks it up, and in a homelab nobody does — so
after a bounded number of rounds it stops, and says that it has stopped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from config.constants.guardian import (
    DIGEST_THRESHOLD,
    DIGEST_WINDOW_SECONDS,
    GUARDIAN_ESCALATION_ROUNDS,
    MAX_DIGEST_ITEMS,
)
from platform.notifications.models import Notification, Outcome, Severity

#: What a digest's subject is keyed on, so every message about one storm lands
#: in one cooldown rather than one per finding.
DIGEST_SUBJECT: str = "guardian-digest"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the guardian concluded, as a notification is built from it."""

    detector_id: str
    title: str
    #: What actually happened, with the reading in it.
    happened: str
    resource: str = ""
    severity: Severity = Severity.HIGH
    at: datetime | None = None
    #: What the deployment did about it, if anything. Empty is the ordinary case
    #: under propose-only and produces a different sentence, not a missing one.
    done: str = ""
    #: Why the rest was not done. Under propose-only this is the posture; under
    #: a permissive one it is a gate, a freeze window, or a spent budget.
    not_done_because: str = ""
    #: What the operator has to do. The remedy from the detector that raised it.
    needed: str = ""

    def message(self) -> str:
        """Return the four-part body, with the third part present even when empty."""
        parts = [self.happened.rstrip(".") + "."]
        if self.done:
            parts.append(f"Done: {self.done.rstrip('.')}.")
        else:
            parts.append("Done: nothing — nothing has been executed.")
        if self.not_done_because:
            parts.append(f"Not done: {self.not_done_because.rstrip('.')}.")
        parts.append(
            f"Needed from you: {self.needed.rstrip('.')}."
            if self.needed
            else "Needed from you: nothing yet; this is for information."
        )
        return " ".join(parts)

    def notification(self, *, team_node_id: str = "", link: str = "") -> Notification:
        """Return this finding as one notification, through the ordinary type."""
        return Notification(
            subject=f"{self.detector_id}:{self.resource}" if self.resource else self.detector_id,
            title=self.title,
            message=self.message(),
            severity=self.severity,
            outcome=Outcome.UNRESOLVED,
            team_node_id=team_node_id,
            link=link,
        )

    def resolution(self, *, team_node_id: str = "", link: str = "") -> Notification:
        """Return the message sent when this resolves, acknowledged or not.

        Deliberately a notification rather than a state change on the first one.
        The operator may never have seen the first one, and "this is over" has
        to stand on its own.
        """
        return Notification(
            subject=f"{self.detector_id}:{self.resource}" if self.resource else self.detector_id,
            title=f"Resolved: {self.title}",
            message=(
                f"{self.happened.rstrip('.')}. This has now cleared on its own, and there "
                f"is nothing for you to do. It is being sent because you may not have seen "
                f"the first message, and finding out about a finished problem hours later "
                f"is worse than being told twice."
            ),
            severity=Severity.LOW,
            outcome=Outcome.RESOLVED,
            team_node_id=team_node_id,
            link=link,
        )


@dataclass(frozen=True, slots=True)
class Digest:
    """Many findings inside a window, as the one message they should be."""

    findings: tuple[Finding, ...]
    opened_at: datetime
    closed_at: datetime

    @property
    def severity(self) -> Severity:
        """Return the worst severity in the digest.

        The worst rather than an average: a digest containing one critical
        finding is a critical notification whatever the other nineteen are, and
        averaging would be a way of demoting the one that mattered.
        """
        return min((finding.severity for finding in self.findings), key=lambda s: s.rank)

    def title(self) -> str:
        """Return the one-line subject a phone shows."""
        return f"{len(self.findings)} findings in {self._minutes()} minutes"

    def message(self) -> str:
        """Return the body: the shape of the storm, then as much of it as fits."""
        listed = self.findings[:MAX_DIGEST_ITEMS]
        lines = [
            f"{len(self.findings)} findings were raised in {self._minutes()} minutes. "
            f"They are sent together because {len(self.findings)} separate messages is "
            f"not {len(self.findings)} times more useful than one."
        ]
        lines.extend(
            f"- [{finding.severity.value}] {finding.title}"
            + (f" ({finding.resource})" if finding.resource else "")
            for finding in listed
        )
        remaining = len(self.findings) - len(listed)
        if remaining:
            lines.append(f"- and {remaining} more, in the console.")
        return "\n".join(lines)

    def notification(self, *, team_node_id: str = "", link: str = "") -> Notification:
        """Return the single notification this whole storm becomes."""
        return Notification(
            subject=DIGEST_SUBJECT,
            title=self.title(),
            message=self.message(),
            severity=self.severity,
            outcome=Outcome.UNRESOLVED,
            team_node_id=team_node_id,
            link=link,
        )

    def _minutes(self) -> int:
        """Return how many minutes the digest window spans, rounded up to one."""
        return max(1, int((self.closed_at - self.opened_at).total_seconds() // 60))


def digest_or_individually(
    findings: Sequence[Finding],
    *,
    now: datetime,
    window_seconds: float = DIGEST_WINDOW_SECONDS,
    threshold: int = DIGEST_THRESHOLD,
    team_node_id: str = "",
) -> tuple[Notification, ...]:
    """Return one notification per finding, or one digest, depending on the volume.

    The rule is a count inside a window and nothing cleverer. Two findings a few
    minutes apart are two things and the operator wants both; three is a storm
    starting, and what they want then is its shape.

    Findings older than the window are not included in the count *or* dropped —
    they are simply not part of this decision, because the question is whether
    what is happening now is a storm.
    """
    recent = [
        finding
        for finding in findings
        if finding.at is None or now - finding.at <= timedelta(seconds=window_seconds)
    ]
    if not recent:
        return ()
    if len(recent) < threshold:
        return tuple(finding.notification(team_node_id=team_node_id) for finding in recent)

    moments = [finding.at for finding in recent if finding.at is not None]
    opened_at = min(moments) if moments else now
    return (
        Digest(findings=tuple(recent), opened_at=opened_at, closed_at=now).notification(
            team_node_id=team_node_id
        ),
    )


@dataclass(frozen=True, slots=True)
class EscalationBound:
    """How far an escalation goes before it stops, and what it says when it does.

    Separate from the escalation registry that schedules them, because the
    registry answers "what is due" and this answers "is there any point". In a
    homelab the second question has an end, and saying so is the difference
    between a system that gave up and one that was designed to.
    """

    rounds: int = GUARDIAN_ESCALATION_ROUNDS

    def exhausted(self, round_number: int) -> bool:
        """Return whether ``round_number`` is past the last escalation."""
        return round_number >= self.rounds

    def final_message(self, subject: str) -> str:
        """Return what the last escalation says, which is that it is the last."""
        return (
            f"{subject} has now been escalated {self.rounds} times and nothing has "
            f"changed. This is the last message about it: there is no rota to escalate "
            f"to here, and an alert that repeats for ever is one you would learn to "
            f"filter — which would cost you the next one too. It stays open in the "
            f"console, and it will be in the next digest if it gets worse."
        )

    def to_record(self) -> dict[str, Any]:
        """Return what a report says about this deployment's escalation bound."""
        return {
            "rounds": self.rounds,
            "ends": True,
            "why": (
                "escalation is bounded because there is nobody to escalate to; an "
                "unbounded one trains the only recipient to ignore it"
            ),
        }


__all__ = [
    "DIGEST_SUBJECT",
    "Digest",
    "EscalationBound",
    "Finding",
    "digest_or_individually",
]
