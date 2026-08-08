"""The four gates no level overrides, and the one that refuses first."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time

import pytest

from platform.autonomy.bounds import (
    Bound,
    BudgetRule,
    BudgetState,
    FreezeWindow,
    NoStop,
    evaluate_bounds,
)
from platform.autonomy.scopes import PolicyScope, ScopeKind
from tests.unit.platform.autonomy.conftest import NOON, action, subject


@dataclass(frozen=True, slots=True)
class EngagedStop:
    """A stop that is simply on. What a deployment looks like mid-incident."""

    reason: str = "the estate is on fire"

    def is_engaged(self, *, team_node_id: str | None = None) -> bool:
        del team_node_id
        return True

    def describe_for(self, *, team_node_id: str | None = None) -> str:
        del team_node_id
        return self.reason


def test_nothing_configured_refuses_nothing_when_the_action_can_be_undone() -> None:
    outcome = evaluate_bounds(action(), at=NOON, stop=NoStop())
    assert not outcome.refused
    assert outcome.bound is None


def test_the_stop_refuses_before_anything_else_is_even_looked_at() -> None:
    """A spent budget is true and irrelevant while writes are stopped."""
    window = FreezeWindow(
        name="backups",
        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
        start=time(0, 0),
        end=time(23, 59),
    )
    spent = BudgetState(
        rule=BudgetRule(name="hourly", limit=1), key="hourly:resource:ct-101", spent=9
    )

    outcome = evaluate_bounds(
        action(rollback=False), at=NOON, stop=EngagedStop(), freezes=(window,), budgets=(spent,)
    )
    assert outcome.bound is Bound.KILL_SWITCH
    assert outcome.reason == "the estate is on fire"


def test_a_freeze_window_refuses_inside_it_and_permits_outside_it() -> None:
    window = FreezeWindow(
        name="nightly-backups",
        scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id="ct-101"),
        start=time(1, 0),
        end=time(4, 0),
        reason="backups run",
    )
    inside = datetime(2026, 3, 12, 2, 30, tzinfo=UTC)

    refused = evaluate_bounds(action(), at=inside, stop=NoStop(), freezes=(window,))
    permitted = evaluate_bounds(action(), at=NOON, stop=NoStop(), freezes=(window,))

    assert refused.bound is Bound.FREEZE
    assert "nightly-backups" in refused.reason
    assert "backups run" in refused.reason
    assert not permitted.refused


def test_a_freeze_window_covering_another_resource_does_not_refuse_this_one() -> None:
    window = FreezeWindow(
        name="datastore",
        scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id="ct-999"),
        start=time(1, 0),
        end=time(4, 0),
    )
    inside = datetime(2026, 3, 12, 2, 30, tzinfo=UTC)
    assert not evaluate_bounds(action(), at=inside, stop=NoStop(), freezes=(window,)).refused


def test_a_freeze_window_is_read_in_its_own_timezone_not_the_deployments() -> None:
    """01:00–04:00 in Tokyo is 16:00–19:00 the previous day in UTC."""
    window = FreezeWindow(
        name="tokyo-backups",
        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
        start=time(1, 0),
        end=time(4, 0),
        timezone="Asia/Tokyo",
    )
    inside = datetime(2026, 3, 11, 17, 0, tzinfo=UTC)
    outside = datetime(2026, 3, 12, 2, 0, tzinfo=UTC)

    assert evaluate_bounds(action(), at=inside, stop=NoStop(), freezes=(window,)).refused
    assert not evaluate_bounds(action(), at=outside, stop=NoStop(), freezes=(window,)).refused


def test_a_freeze_window_holds_across_a_daylight_saving_change() -> None:
    """London's clocks go forward on 29 March 2026; 02:30 local still freezes."""
    window = FreezeWindow(
        name="london-backups",
        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
        start=time(1, 0),
        end=time(4, 0),
        timezone="Europe/London",
    )
    # Before the change: 02:30 London is 02:30 UTC.
    winter = datetime(2026, 3, 22, 2, 30, tzinfo=UTC)
    # After it: 02:30 London is 01:30 UTC, and 02:30 UTC is 03:30 London.
    summer_inside = datetime(2026, 4, 5, 1, 30, tzinfo=UTC)
    # 00:30 London on the same day is 23:30 UTC the night before, outside.
    summer_outside = datetime(2026, 4, 4, 23, 30, tzinfo=UTC)

    assert evaluate_bounds(action(), at=winter, stop=NoStop(), freezes=(window,)).refused
    assert evaluate_bounds(action(), at=summer_inside, stop=NoStop(), freezes=(window,)).refused
    assert not evaluate_bounds(
        action(), at=summer_outside, stop=NoStop(), freezes=(window,)
    ).refused


def test_a_window_wrapping_past_midnight_is_one_window_rather_than_two() -> None:
    window = FreezeWindow(
        name="out-of-hours",
        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
        start=time(22, 0),
        end=time(6, 0),
    )
    for hour in (22, 23, 0, 5):
        at = datetime(2026, 3, 12, hour, 30, tzinfo=UTC)
        assert window.contains(at), hour
    for hour in (6, 12, 21):
        at = datetime(2026, 3, 12, hour, 30, tzinfo=UTC)
        assert not window.contains(at), hour


def test_a_window_that_starts_and_ends_at_the_same_time_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="Say which you meant"):
        FreezeWindow(
            name="ambiguous",
            scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
            start=time(1, 0),
            end=time(1, 0),
        )


def test_a_timezone_this_host_does_not_know_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="not a timezone"):
        FreezeWindow(
            name="nowhere",
            scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
            start=time(1, 0),
            end=time(4, 0),
            timezone="Mars/Olympus",
        )


def test_a_spent_budget_refuses_and_names_every_budget_that_is_spent() -> None:
    hourly = BudgetRule(name="hourly", limit=2)
    daily = BudgetRule(name="daily", limit=5, interval_seconds=86400)
    outcome = evaluate_bounds(
        action(),
        at=NOON,
        stop=NoStop(),
        budgets=(
            BudgetState(rule=hourly, key="hourly:resource:ct-101", spent=2),
            BudgetState(rule=daily, key="daily:resource:ct-101", spent=5),
        ),
    )
    assert outcome.bound is Bound.BUDGET
    assert outcome.exhausted == ("hourly:resource:ct-101", "daily:resource:ct-101")
    assert "2 action(s) per 60 minutes per resource" in outcome.reason


def test_a_budget_with_room_left_refuses_nothing() -> None:
    rule = BudgetRule(name="hourly", limit=2)
    outcome = evaluate_bounds(
        action(),
        at=NOON,
        stop=NoStop(),
        budgets=(BudgetState(rule=rule, key="hourly:resource:ct-101", spent=1),),
    )
    assert not outcome.refused


def test_an_action_with_no_rollback_plan_is_refused_by_the_rollback_bound() -> None:
    outcome = evaluate_bounds(action(rollback=False), at=NOON, stop=NoStop())
    assert outcome.bound is Bound.ROLLBACK
    assert "no rollback plan" in outcome.reason


def test_a_budget_counts_one_action_once_however_many_resources_it_touches() -> None:
    from platform.autonomy.bounds import budget_states_needed

    team_budget = BudgetRule(name="team", counted_by="team", limit=3)
    spread = action(subjects=(subject("ct-101"), subject("ct-102"), subject("ct-103")))
    assert budget_states_needed(spread, (team_budget,)) == ((team_budget, "team:team:platform"),)


def test_a_per_resource_budget_counts_each_resource_separately() -> None:
    from platform.autonomy.bounds import budget_states_needed

    per_resource = BudgetRule(name="each", counted_by="resource", limit=1)
    spread = action(subjects=(subject("ct-101"), subject("ct-102")))
    assert [key for _, key in budget_states_needed(spread, (per_resource,))] == [
        "each:resource:ct-101",
        "each:resource:ct-102",
    ]


def test_a_budget_scoped_to_something_the_action_is_not_does_not_apply() -> None:
    from platform.autonomy.bounds import budget_states_needed

    elsewhere = BudgetRule(
        name="other-team",
        scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="payments"),
    )
    assert budget_states_needed(action(), (elsewhere,)) == ()
