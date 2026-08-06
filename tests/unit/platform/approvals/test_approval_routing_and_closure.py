"""Who is told, and the property that a decision on one surface closes it on all.

The failure this covers is the one every deployment with a chat integration
eventually has. A change is announced in Slack, in Discord, and in the console;
somebody approves it in the console; the two chat messages sit there for the
rest of the week with live buttons. The next person clicks one and either gets
an error they cannot interpret or — worse — applies the change a second time.

So there is one decision event and every surface subscribes to it, rather than
per-surface state each surface keeps in step by hand. And publishing is
idempotent, because a retried decision path must not produce a second "approved"
announcement in a channel that already has one.

Routing is derived rather than stored, for the same reason: a stored reviewer
list is one somebody has to remember to prune, and the one nobody pruned is how
a departed employee keeps the ability to approve production changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from platform.approvals.closure import ClosurePublisher, DecisionEvent
from platform.approvals.models import (
    ChangeState,
    ChangeTarget,
    ChangeType,
    PendingChange,
)
from platform.approvals.notification import ReviewerNotifier, ReviewRequest
from platform.approvals.policy import SecurityPolicy
from platform.approvals.routing import (
    EXCLUDED_REQUESTER,
    notify_order,
    reviewers_for,
)
from platform.approvals.service import ApprovalService
from platform.config_service.hierarchy import Hierarchy
from platform.identity.models import Grant
from platform.identity.permissions import Role
from platform.persistence.ports import ConfigNode, ConfigNodeKind

pytestmark = pytest.mark.unit

ORG = "acme"
DIVISION = "division-platform"
TEAM = "team-payments"
OTHER_TEAM = "team-search"
REQUESTER = "ada"
REVIEWER = "grace"

Applier = Any


# --- Doubles -----------------------------------------------------------------


@dataclass(slots=True)
class RecordingSink:
    """A surface that keeps what it was told, and can be made to fail."""

    name: str = "console"
    delivered: list[ReviewRequest] = field(default_factory=list)
    fails: bool = False

    async def deliver(self, request: ReviewRequest) -> None:
        """Record ``request``, or raise if this sink is scripted to fail."""
        if self.fails:
            raise RuntimeError(f"{self.name} is unreachable")
        self.delivered.append(request)


@dataclass(slots=True)
class RecordingSurface:
    """A surface that showed the request and records being told to close it."""

    name: str = "slack"
    closed_events: list[DecisionEvent] = field(default_factory=list)
    fails: bool = False

    async def closed(self, event: DecisionEvent) -> None:
        """Record ``event``, or raise if this surface is scripted to fail."""
        if self.fails:
            raise RuntimeError(f"{self.name} is unreachable")
        self.closed_events.append(event)


def a_change(requester: str = REQUESTER, *, node_id: str | None = TEAM) -> PendingChange:
    """Return one queued change at ``node_id``."""
    from datetime import UTC, datetime, timedelta

    at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return PendingChange(
        change_id="c-1",
        change_type=ChangeType.PROMPT,
        target=ChangeTarget(identifier=node_id or ORG, node_id=node_id),
        proposed={"level": "strict"},
        current={"level": "standard"},
        requester=requester,
        rationale="because",
        created_at=at,
        expires_at=at + timedelta(hours=72),
        fingerprint="whatever",
    )


def grant(principal_id: str, role: Role, node_id: str | None) -> Grant:
    """Return one role binding as a grant."""
    return Grant(
        grant_id=f"{principal_id}-{role.value}-{node_id or 'org'}",
        principal_id=principal_id,
        role=role,
        node_id=node_id,
    )


@pytest.fixture
def tree() -> Hierarchy:
    """Return the tree routing resolves grants against."""
    return Hierarchy.of(
        [
            ConfigNode(node_id=ORG, kind=ConfigNodeKind.ORGANISATION, name=ORG, parent_id=None),
            ConfigNode(node_id=DIVISION, kind=ConfigNodeKind.TEAM, name=DIVISION, parent_id=ORG),
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=DIVISION),
            ConfigNode(
                node_id=OTHER_TEAM, kind=ConfigNodeKind.TEAM, name=OTHER_TEAM, parent_id=DIVISION
            ),
        ]
    )


# --- Routing (T040) ----------------------------------------------------------


def test_a_reviewer_at_the_node_is_eligible(tree: Hierarchy) -> None:
    reviewers = reviewers_for(
        a_change(),
        [grant(REVIEWER, Role.RESPONDER, TEAM)],
        policy=SecurityPolicy(),
        hierarchy=tree,
    )

    assert reviewers.reviewers == (REVIEWER,)
    assert reviewers.allows(REVIEWER)


def test_a_reviewer_above_the_node_is_eligible_through_inheritance(tree: Hierarchy) -> None:
    reviewers = reviewers_for(
        a_change(),
        [grant(REVIEWER, Role.RESPONDER, DIVISION)],
        policy=SecurityPolicy(),
        hierarchy=tree,
    )

    assert reviewers.reviewers == (REVIEWER,)


def test_a_reviewer_beside_the_node_is_not(tree: Hierarchy) -> None:
    """Inheritance is downward only — the same asymmetry as every other check."""
    reviewers = reviewers_for(
        a_change(),
        [grant(REVIEWER, Role.OWNER, OTHER_TEAM)],
        policy=SecurityPolicy(),
        hierarchy=tree,
    )

    assert reviewers.is_empty


def test_somebody_who_can_only_read_approvals_is_not_a_reviewer(tree: Hierarchy) -> None:
    reviewers = reviewers_for(
        a_change(),
        [grant("bob", Role.VIEWER, TEAM)],
        policy=SecurityPolicy(),
        hierarchy=tree,
    )

    assert reviewers.is_empty


def test_the_requester_is_excluded_and_the_exclusion_says_why(tree: Hierarchy) -> None:
    """ "Nobody is eligible" is not actionable; "only the requester is" is."""
    reviewers = reviewers_for(
        a_change(),
        [grant(REQUESTER, Role.OWNER, TEAM)],
        policy=SecurityPolicy(),
        hierarchy=tree,
    )

    assert reviewers.is_empty
    assert reviewers.excluded[REQUESTER] == EXCLUDED_REQUESTER


def test_the_requester_is_eligible_when_the_policy_allows_it(tree: Hierarchy) -> None:
    reviewers = reviewers_for(
        a_change(),
        [grant(REQUESTER, Role.OWNER, TEAM)],
        policy=SecurityPolicy(allow_self_approval=True),
        hierarchy=tree,
    )

    assert reviewers.reviewers == (REQUESTER,)


def test_an_inactive_principal_is_excluded_and_named(tree: Hierarchy) -> None:
    reviewers = reviewers_for(
        a_change(),
        [grant(REVIEWER, Role.RESPONDER, TEAM)],
        policy=SecurityPolicy(),
        hierarchy=tree,
        inactive=[REVIEWER],
    )

    assert reviewers.is_empty
    assert REVIEWER in reviewers.excluded


def test_without_the_tree_only_exact_and_organisation_grants_apply() -> None:
    """A missing input narrows the answer rather than widening it."""
    inherited = reviewers_for(
        a_change(), [grant(REVIEWER, Role.RESPONDER, DIVISION)], policy=SecurityPolicy()
    )
    exact = reviewers_for(
        a_change(), [grant(REVIEWER, Role.RESPONDER, TEAM)], policy=SecurityPolicy()
    )
    organisation = reviewers_for(
        a_change(), [grant(REVIEWER, Role.RESPONDER, None)], policy=SecurityPolicy()
    )

    assert inherited.is_empty
    assert exact.reviewers == (REVIEWER,)
    assert organisation.reviewers == (REVIEWER,)


def test_the_notify_order_is_stable_and_bounded() -> None:
    """A retry has to reach the same people, not a different sample of them."""
    everybody = [f"user-{index:03d}" for index in range(50)]

    first = notify_order(everybody, limit=5)
    second = notify_order(list(reversed(everybody)), limit=5)

    assert first == second
    assert len(first) == 5


# --- Notification (T041) -----------------------------------------------------


async def test_every_sink_is_told_about_a_queued_change(
    gateway: Any, scope: Any, applier: Applier, clock: Any, queue_change: Callable[..., Any]
) -> None:
    console, chat = RecordingSink("console"), RecordingSink("slack")
    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        notifier=ReviewerNotifier(sinks=(console, chat)),
        clock=clock,
    )

    await service.queue(
        change_type=ChangeType.PROMPT,
        target=ChangeTarget(identifier=TEAM, node_id=TEAM),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="because",
    )

    assert len(console.delivered) == 1
    assert len(chat.delivered) == 1
    assert console.delivered[0].requester == REQUESTER


async def test_a_failing_sink_does_not_stop_the_others() -> None:
    """A queued change whose Slack message failed must still reach the console."""
    broken, working = RecordingSink("slack", fails=True), RecordingSink("console")
    notifier = ReviewerNotifier(sinks=(broken, working))

    result = await notifier.notify(
        a_change(), reviewers_for(a_change(), [], policy=SecurityPolicy())
    )

    assert result.failed == ("slack",)
    assert result.delivered == ("console",)
    assert len(working.delivered) == 1


async def test_a_change_nobody_can_review_is_reported_as_reaching_nobody() -> None:
    sink = RecordingSink()
    notifier = ReviewerNotifier(sinks=(sink,))

    result = await notifier.notify(
        a_change(), reviewers_for(a_change(), [], policy=SecurityPolicy())
    )

    assert result.reached_nobody


async def test_a_notification_carries_a_summary_rather_than_the_diff() -> None:
    """A chat message that is two hundred lines is a chat message nobody reads."""
    sink = RecordingSink()
    reviewers = reviewers_for(
        a_change(), [grant(REVIEWER, Role.RESPONDER, None)], policy=SecurityPolicy()
    )

    await ReviewerNotifier(sinks=(sink,)).notify(a_change(), reviewers)

    delivered = sink.delivered[0]
    assert delivered.recipients == (REVIEWER,)
    assert delivered.change_id == "c-1"


# --- Cross-surface closure ---------------------------------------------------


async def test_a_decision_closes_the_request_on_every_surface() -> None:
    console = RecordingSurface("console")
    slack = RecordingSurface("slack")
    discord = RecordingSurface("discord")
    publisher = ClosurePublisher().subscribe(console).subscribe(slack).subscribe(discord)

    from datetime import UTC, datetime

    at = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    told = await publisher.publish(
        DecisionEvent.of(a_change().with_state(ChangeState.APPROVED), at=at)
    )

    assert told == ("console", "slack", "discord")
    for surface in (console, slack, discord):
        assert surface.closed_events[0].closes_the_request


async def test_a_decision_is_published_once_however_many_times_it_is_retried() -> None:
    """A retried decision path must not produce a second announcement."""
    surface = RecordingSurface("console")
    publisher = ClosurePublisher().subscribe(surface)

    from datetime import UTC, datetime

    at = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    event = DecisionEvent.of(a_change().with_state(ChangeState.APPROVED), at=at)

    assert await publisher.publish(event) == ("console",)
    assert await publisher.publish(event) == ()
    assert len(surface.closed_events) == 1
    assert publisher.has_published("c-1")


async def test_a_failing_surface_does_not_leave_the_others_showing_a_button() -> None:
    broken, working = RecordingSurface("slack", fails=True), RecordingSurface("console")
    publisher = ClosurePublisher().subscribe(broken).subscribe(working)

    from datetime import UTC, datetime

    told = await publisher.publish(
        DecisionEvent.of(
            a_change().with_state(ChangeState.REJECTED),
            at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        )
    )

    assert told == ("console",)
    assert len(working.closed_events) == 1


async def test_an_expiry_closes_the_request_too() -> None:
    """A lapsed change is one a surface has to stop showing a button for."""
    surface = RecordingSurface()
    publisher = ClosurePublisher().subscribe(surface)

    from datetime import UTC, datetime

    await publisher.publish(
        DecisionEvent.of(
            a_change().with_state(ChangeState.EXPIRED),
            at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        )
    )

    assert surface.closed_events[0].state is ChangeState.EXPIRED
    assert surface.closed_events[0].closes_the_request


async def test_a_conflicted_change_does_not_close_the_request() -> None:
    """It is still waiting on somebody — the button has to stay live."""
    surface = RecordingSurface()
    publisher = ClosurePublisher().subscribe(surface)

    from datetime import UTC, datetime

    await publisher.publish(
        DecisionEvent.of(
            a_change().with_state(ChangeState.CONFLICTED),
            at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        )
    )

    assert not surface.closed_events[0].closes_the_request


async def test_the_service_publishes_a_decision_to_every_surface(
    gateway: Any,
    scope: Any,
    applier: Applier,
    clock: Any,
    as_reviewer: Callable[..., dict[str, Any]],
) -> None:
    """End to end: deciding through the service closes it on every surface."""
    slack, console = RecordingSurface("slack"), RecordingSurface("console")
    service = ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=dict.fromkeys(ChangeType, applier),
        closure=ClosurePublisher().subscribe(slack).subscribe(console),
        clock=clock,
    )
    change = await service.queue(
        change_type=ChangeType.PROMPT,
        target=ChangeTarget(identifier=TEAM, node_id=TEAM),
        proposed={"level": "strict"},
        requester=REQUESTER,
        rationale="because",
    )

    await service.decide(change.change_id, **as_reviewer(), approve=True)

    for surface in (slack, console):
        assert [event.change_id for event in surface.closed_events] == [change.change_id]
        assert surface.closed_events[0].state is ChangeState.APPROVED
        assert surface.closed_events[0].decided_by == REVIEWER
