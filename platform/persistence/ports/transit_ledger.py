"""Where data crossed the boundary, in which direction, and what happened to it.

The seventeenth port, and the first that exists to make a *negative* answerable.
Every other store here records something the deployment has; this one records
that something arrived and was refused, or that a source has been silent since
the day it was configured. A configured source that never delivered is
indistinguishable from one nobody configured unless the absence is a row you can
query, and that is the failure this port exists to end.

**A delivery row is written on every path, including the ones that end in a
4xx.** Accepted, rejected, shed, duplicate, recorded-only, discarded-by-rule,
and — in the other direction — delivered and failed. A rejection that leaves no
trace is the silent failure the whole feature is about, so "record it if it
worked" is exactly the wrong shape.

**A sample is a masked payload, and there is one per source.** The raw body is
never stored: what is written has already been through the deployment's masking
policy, and the policy that was applied is named on the sample so a reader knows
what they are looking at. One per source, replaced on the next delivery, because
the sample answers "did the format change" — a question about the last payload.

**Ledger rows are transit, not audit.** They are swept by the one retention
sweeper under their own ``DataClass``, like every other bounded history here.
The record that a *person* acted — re-sending a failed delivery by hand — is an
audit event, written beside the ledger row and never deleted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from config.constants.transit import (
    DEFAULT_TRANSIT_PAGE_SIZE,
    MAX_TRANSIT_PAGE_SIZE,
    MAX_TRANSIT_SAMPLE_BYTES,
    TRANSIT_SAMPLE_TRUNCATION_MARKER,
)
from platform.persistence.errors import BoundExceeded


class TransitDirection(StrEnum):
    """Which way across the boundary a delivery went. There is no third member."""

    INGRESS = "ingress"
    OUTBOUND = "outbound"


class TransitOutcome(StrEnum):
    """What became of one delivery.

    Seven members, and the split between them is the one an operator makes when
    something did not arrive: was it refused at the door (``REJECTED``,
    ``SHED``), recognised as something already handled (``DUPLICATE``), or
    accepted and then deliberately not acted on (``RECORDED``, ``DISCARDED``)?
    The last two are the routing rules' doing and carry the rule that did it.
    """

    #: Verified, matched, and acted on — a run was started or an incident raised.
    ACCEPTED = "accepted"
    #: Refused before it was acted on: unverified, unparseable, or oversize.
    REJECTED = "rejected"
    #: Refused by the rate limiter. Distinct from ``REJECTED`` because the
    #: sender did nothing wrong and the fix is a limit rather than their config.
    SHED = "shed"
    #: A delivery this deployment had already processed.
    DUPLICATE = "duplicate"
    #: Matched a rule whose action was to record without investigating.
    RECORDED = "recorded"
    #: Matched a rule whose action was to discard. Always with a reason.
    DISCARDED = "discarded"
    #: Outbound only: the destination accepted the message.
    DELIVERED = "delivered"
    #: Outbound only: the destination did not, and the reason says why.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TransitDelivery:
    """One crossing of the boundary, and everything the screen asks about it.

    Flat rather than nested, and deliberately so: this record is read as a table
    row in both directions, and a shape that needed a different accessor for an
    ingress row and an outbound row would be two records wearing one name.
    ``source`` is the ingress path name one way and the destination id the
    other — the thing at the far end, whichever way the data was going.
    """

    delivery_id: str
    direction: TransitDirection
    source: str
    occurred_at: datetime
    outcome: TransitOutcome
    #: Why, when the outcome is not a success. Empty for an accepted delivery,
    #: and refused at construction when the outcome is ``DISCARDED``.
    reason: str = ""
    #: The routing rule that decided this delivery's fate, when one did.
    matched_rule: str = ""
    team_node_id: str = ""
    #: The estate resource the payload resolved to, when it resolved to one.
    resource_id: str = ""
    run_id: str = ""
    incident_id: str = ""
    #: Outbound only: which subscribed event produced this message.
    event_type: str = ""
    #: 1 for a first try. Retries of one outbound message share a delivery id
    #: prefix and differ here, so "it failed four times" is countable.
    attempt: int = 1
    detail: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A discard with no reason is the silent drop this whole feature exists
        # to end, and refusing it here means no backend, route or rule editor
        # has to remember to check. The spec's word is "descartar com motivo";
        # without this the "com motivo" half is a convention.
        if self.outcome is TransitOutcome.DISCARDED and not self.reason:
            raise ValueError(
                f"delivery {self.delivery_id!r} from {self.source!r} was discarded with no "
                f"reason. A silent discard is how an alert disappears without anybody knowing."
            )

    @property
    def succeeded(self) -> bool:
        """Return whether this delivery ended in the outcome its sender wanted."""
        return self.outcome in (TransitOutcome.ACCEPTED, TransitOutcome.DELIVERED)


@dataclass(frozen=True, slots=True)
class PayloadSample:
    """The last thing one source sent, after masking, and which policy did it.

    ``body`` has already been through the deployment's masking policy before it
    reaches any implementation of this port — there is no unmasked field to
    forget to clear. ``masking_policy`` is on the record rather than looked up
    at read time because the policy can change, and a sample captured under
    ``standard`` shown beside a label saying ``strict`` would be a lie about
    what was withheld.
    """

    source: str
    captured_at: datetime
    body: str
    masking_policy: str
    #: What the sender called this delivery, when it named one. Lets a reader
    #: match the sample against the row in the delivery list above it.
    delivery_id: str = ""
    #: Whether ``body`` was cut at ``MAX_TRANSIT_SAMPLE_BYTES``.
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class TransitQuery:
    """A window over the ledger, in the dimensions the screen reads it by.

    Empty tuples mean "no filter on this dimension" rather than "match nothing",
    for the reason ``EstateQuery`` gives: it is the only reading that composes
    when a caller builds a query out of optional inputs.
    """

    directions: tuple[TransitDirection, ...] = ()
    sources: tuple[str, ...] = ()
    outcomes: tuple[TransitOutcome, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    limit: int = DEFAULT_TRANSIT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class SourceActivity:
    """What one source has done inside a window, and when it was last heard from.

    ``last_delivery`` reaches outside the window on purpose, for the same reason
    ``SignalStore.latest`` does: a count over the last day is zero both for a
    source that stopped in March and for one that was configured this morning,
    and those are different facts. A source with no row at all does not appear
    here — the caller enumerates what it configured and treats an absence as
    never-delivered, because this port cannot know what was configured.
    """

    source: str
    direction: TransitDirection
    last_delivery: TransitDelivery | None = None
    #: Counts within the window, keyed by outcome. Outcomes with no rows are
    #: absent rather than zero: a caller reading `.get(outcome, 0)` gets the
    #: same answer, and the absent key is one row this store did not write.
    counts: Mapping[TransitOutcome, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Return how many deliveries of any outcome landed inside the window."""
        return sum(self.counts.values())


def check_transit_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the transit page bound."""
    if limit > MAX_TRANSIT_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_TRANSIT_PAGE_SIZE,
            constant="MAX_TRANSIT_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def bounded_sample(body: str) -> tuple[str, bool]:
    """Return ``body`` cut to the sample cap, and whether cutting happened.

    The cap is on bytes, because that is what the column costs, but a cut that
    lands mid-character is dropped rather than kept: a sample exists to be read,
    and a trailing replacement character answers nothing. The marker is appended
    so a short payload and a cut one are distinguishable, which is the
    difference between "that is the whole format" and "there is more of this".
    """
    if len(body.encode("utf-8")) <= MAX_TRANSIT_SAMPLE_BYTES:
        return body, False
    cut = body.encode("utf-8")[:MAX_TRANSIT_SAMPLE_BYTES].decode("utf-8", errors="ignore")
    return cut + TRANSIT_SAMPLE_TRUNCATION_MARKER, True


def matches(delivery: TransitDelivery, query: TransitQuery) -> bool:
    """Return whether ``delivery`` satisfies every filter ``query`` declares.

    Shared by both backends because it is *contract*: a source filter that
    matched a prefix in one and an exact string in the other would make the
    ingress column show different rows depending on where it ran.
    """
    if query.directions and delivery.direction not in query.directions:
        return False
    if query.sources and delivery.source not in query.sources:
        return False
    if query.outcomes and delivery.outcome not in query.outcomes:
        return False
    if query.since is not None and delivery.occurred_at < query.since:
        return False
    return not (query.until is not None and delivery.occurred_at > query.until)


@runtime_checkable
class TransitLedger(Protocol):
    """One organisation's record of what crossed its boundary, inside one transaction."""

    async def record(self, delivery: TransitDelivery) -> TransitDelivery:
        """Store ``delivery`` and return it, replacing any row with the same id.

        Idempotent by the caller's own identifier rather than by a check the
        caller makes, for the reason the signal store gives: a handler that
        retried its own ledger write has recorded one delivery, not two.
        """

    async def deliveries(self, query: TransitQuery) -> tuple[TransitDelivery, ...]:
        """Return the rows matching ``query``, most recent first.

        Newest first because every reader of this list is asking "what happened
        recently". Raises ``BoundExceeded`` above ``MAX_TRANSIT_PAGE_SIZE``.
        """

    async def delivery(self, delivery_id: str) -> TransitDelivery | None:
        """Return one row by id, or ``None``.

        The simulate endpoint's other input: an operator picks a delivery they
        can see and asks what today's rules would do with it.
        """

    async def store_sample(self, sample: PayloadSample) -> PayloadSample:
        """Store ``sample`` as this source's only sample, replacing the last one.

        One per source is a storage guarantee rather than a caller convention,
        for the reason the signal store's derived key is: a property enforced
        only by every caller remembering it is not a property.
        """

    async def sample(self, source: str) -> PayloadSample | None:
        """Return the last masked payload this source sent, or ``None``."""

    async def activity(
        self,
        *,
        direction: TransitDirection,
        since: datetime,
    ) -> tuple[SourceActivity, ...]:
        """Return per-source counts inside the window and each source's last delivery.

        One read rather than one per source: the ingress column asks this about
        every configured source at once, and a query per source would make the
        screen's cost a function of how many sources an operator wired up.
        """

    async def prune(self, *, before: datetime) -> int:
        """Delete delivery rows recorded before ``before`` and return how many went.

        Samples are not swept by age. There is one per source and it is replaced
        rather than appended, so the table is bounded by the number of sources
        rather than by time — and sweeping it would delete the answer to "what
        does this source send" from a source that sends rarely.
        """


__all__ = [
    "PayloadSample",
    "SourceActivity",
    "TransitDelivery",
    "TransitDirection",
    "TransitLedger",
    "TransitOutcome",
    "TransitQuery",
    "bounded_sample",
    "check_transit_limit",
    "matches",
]
