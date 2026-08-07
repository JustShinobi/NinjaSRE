"""SC-003: a decision made elsewhere closes the console's pending item.

"Elsewhere" is the point. The console has no idea which surface decided — chat,
the CLI, another browser — and it must not need one: what reaches it is the
run's own event, and the same event closes the card whoever produced it.
"""

from __future__ import annotations

from platform.identity.permissions import Role
from surfaces.console.html import text_of
from surfaces.console.live import (
    apply_event,
    apply_events,
    closed_by,
    open_count,
    opened_by,
)
from surfaces.console.pages.interactions import interaction_card
from surfaces.console.stream import StreamEvent
from tests.unit.surfaces.console.conftest import INTERACTIONS, context_for

RUN = "run-1"


def _event(kind: str, **payload: object) -> StreamEvent:
    return StreamEvent(run_id=RUN, kind=kind, sequence=1, payload=dict(payload))


def test_a_decision_made_elsewhere_closes_the_matching_item() -> None:
    closed = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=False, interaction_id="q-1")
    )

    answered = next(item for item in closed if item["interaction_id"] == "q-1")
    assert answered["is_open"] is False


def test_the_other_items_are_left_exactly_as_they_were() -> None:
    closed = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=False, interaction_id="q-1")
    )

    untouched = next(item for item in closed if item["interaction_id"] == "ap-1")
    assert untouched["is_open"] is True


def test_an_approval_decided_elsewhere_closes_by_its_approval_id() -> None:
    closed = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=False, approval_id="ap-1")
    )

    assert open_count(closed) == 1


def test_a_run_that_starts_waiting_closes_nothing() -> None:
    """The other direction of the same event, which would otherwise hide a card."""
    unchanged = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=True, interaction_id="q-1")
    )

    assert open_count(unchanged) == len(INTERACTIONS)


def test_an_event_about_something_else_entirely_changes_nothing() -> None:
    unchanged = apply_event(INTERACTIONS, _event("capability_called", capability="k8s.logs"))

    assert unchanged == tuple(INTERACTIONS)


def test_an_approval_raised_while_the_page_is_open_appears_on_it() -> None:
    opened = apply_event(
        (), _event("approval_requested", approval_id="ap-9", summary="restart checkout")
    )

    assert len(opened) == 1
    assert opened[0]["interaction_id"] == "ap-9"
    assert opened[0]["is_open"] is True


def test_the_same_approval_arriving_twice_appears_once() -> None:
    once = apply_event((), _event("approval_requested", approval_id="ap-9", summary="x"))
    twice = apply_event(once, _event("approval_requested", approval_id="ap-9", summary="x"))

    assert len(twice) == 1


def test_a_batch_of_events_is_applied_in_order() -> None:
    events = [
        _event("approval_requested", approval_id="ap-9", summary="restart"),
        _event("attention_changed", waiting=False, approval_id="ap-9"),
    ]

    settled = apply_events((), events)

    assert open_count(settled) == 0


def test_an_event_naming_nothing_is_not_treated_as_closing_everything() -> None:
    assert closed_by(_event("attention_changed", waiting=False)) == ""
    assert opened_by(_event("approval_requested")) is None


def test_a_closed_card_says_it_was_decided_elsewhere_rather_than_vanishing() -> None:
    closed = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=False, interaction_id="q-1")
    )
    answered = next(item for item in closed if item["interaction_id"] == "q-1")

    rendered = interaction_card(context_for(Role.RESPONDER), answered)

    assert [node for node in rendered.walk() if node.has("data-closed")]
    assert "decided elsewhere" in text_of(rendered)


def test_a_closed_card_no_longer_offers_a_decision_to_anybody() -> None:
    closed = apply_event(
        INTERACTIONS, _event("attention_changed", waiting=False, approval_id="ap-1")
    )
    decided = next(item for item in closed if item["interaction_id"] == "ap-1")

    rendered = interaction_card(context_for(Role.OWNER), decided)

    from surfaces.console.permissions import actions_in

    assert actions_in(rendered) == ()


def test_an_open_card_does_offer_one_so_the_test_above_means_something() -> None:
    from surfaces.console.permissions import actions_in

    rendered = interaction_card(context_for(Role.OWNER), INTERACTIONS[0])

    assert "approval.approve" in actions_in(rendered)
