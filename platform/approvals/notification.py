"""Telling the people who can decide that there is something to decide.

A port and a fan-out, and nothing that knows what a chat message looks like.
The surfaces that render one live in tiers above this package, and a sink here
that knew about Slack would be this tier importing that one.

Two properties this module is responsible for, both of which are about failure:

**A sink that fails does not stop the others.** A queued change whose Slack
notification failed must still reach the console and the mailbox. The failure is
reported back to the caller as part of the result rather than raised, because
"nobody was told" is a fact about the change worth recording and not a reason to
refuse the change that was already queued.

**Notification is never the approval.** Nothing here can decide anything. The
sink receives a summary and an identifier; the decision comes back through the
service, which re-checks permission at that point. A design where the
notification carried the authority would be a design where forwarding a message
forwards the ability to approve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.security import MAX_REVIEWER_NOTIFICATIONS
from platform.approvals.blast_radius import BlastRadius
from platform.approvals.diff.summarise import DiffSummary
from platform.approvals.models import PendingChange, ReviewerSet
from platform.approvals.routing import notify_order
from platform.observability.logging import get_logger

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """What a reviewer is told, on whichever surface tells them.

    Carries the summary rather than the diff. A surface that wants the whole
    thing asks the service for it, which keeps a chat message from becoming two
    hundred lines nobody reads and keeps the diff out of a transport whose
    retention nobody here controls.
    """

    change_id: str
    change_type: str
    target: str
    requester: str
    rationale: str
    summary: str
    blast_radius: str
    recipients: tuple[str, ...] = field(default_factory=tuple)
    expires_at: str = ""

    @classmethod
    def of(
        cls,
        change: PendingChange,
        *,
        recipients: Sequence[str],
        diff: DiffSummary | None = None,
        radius: BlastRadius | None = None,
    ) -> ReviewRequest:
        """Return the request describing ``change`` for ``recipients``."""
        return cls(
            change_id=change.change_id,
            change_type=change.change_type.value,
            target=str(change.target),
            requester=change.requester,
            rationale=change.rationale,
            summary=(
                f"{diff.shown_lines} of {diff.total_lines} change(s) shown"
                if diff is not None and diff.is_summarised
                else (f"{diff.total_lines} change(s)" if diff is not None else change.summary())
            ),
            blast_radius=radius.describe() if radius is not None else "",
            recipients=tuple(recipients),
            expires_at=change.expires_at.isoformat(),
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, for a notification audit or a test."""
        return {
            "change_id": self.change_id,
            "change_type": self.change_type,
            "target": self.target,
            "requester": self.requester,
            "rationale": self.rationale,
            "summary": self.summary,
            "blast_radius": self.blast_radius,
            "recipients": list(self.recipients),
            "expires_at": self.expires_at,
        }


@runtime_checkable
class ReviewSink(Protocol):
    """One place reviewers are told about a change: a console, a chat, a mailbox."""

    @property
    def name(self) -> str:
        """Return what this sink is called, for the log line when it fails."""

    async def deliver(self, request: ReviewRequest) -> None:
        """Tell this sink's audience that ``request`` is waiting on them."""


@dataclass(frozen=True, slots=True)
class NotificationResult:
    """Which sinks were told, and which could not be."""

    delivered: tuple[str, ...] = field(default_factory=tuple)
    failed: tuple[str, ...] = field(default_factory=tuple)
    recipients: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reached_nobody(self) -> bool:
        """Return whether the change is now waiting on people who were not told."""
        return not self.delivered or not self.recipients


@dataclass(slots=True)
class ReviewerNotifier:
    """Fans one queued change out to every configured surface."""

    sinks: tuple[ReviewSink, ...] = ()
    limit: int = MAX_REVIEWER_NOTIFICATIONS

    async def notify(
        self,
        change: PendingChange,
        reviewers: ReviewerSet,
        *,
        diff: DiffSummary | None = None,
        radius: BlastRadius | None = None,
    ) -> NotificationResult:
        """Tell every sink, and return which of them heard it.

        The recipient list is bounded and stably ordered, so a retry reaches the
        same people rather than a different sample of them.
        """
        recipients = notify_order(reviewers.reviewers, limit=self.limit)
        request = ReviewRequest.of(change, recipients=recipients, diff=diff, radius=radius)

        delivered: list[str] = []
        failed: list[str] = []
        for sink in self.sinks:
            try:
                await sink.deliver(request)
            except Exception as failure:  # noqa: BLE001 — one sink must not stop the rest
                failed.append(sink.name)
                _LOG.error(
                    "approvals.notification_failed",
                    change_id=change.change_id,
                    sink=sink.name,
                    error=str(failure),
                )
            else:
                delivered.append(sink.name)

        if reviewers.is_empty:
            _LOG.warning(
                "approvals.no_eligible_reviewer",
                change_id=change.change_id,
                node_id=change.node_id,
                excluded=sorted(reviewers.excluded),
            )

        return NotificationResult(
            delivered=tuple(delivered), failed=tuple(failed), recipients=recipients
        )


__all__ = [
    "NotificationResult",
    "ReviewRequest",
    "ReviewSink",
    "ReviewerNotifier",
]
