"""The switch that stops everything, and the conditions that let anything through.

Two properties are asserted here that no amount of reading the code establishes.

**The kill switch is immediate**, including against an action that has already
been approved and is about to run. The test engages it after the approval and
before the execution, which is the window it exists for.

**Conditions are answered against the moment of execution.** The test makes them
hold when the action is proposed and stop holding before it runs, which is the
case that makes re-evaluation mean something — an approval sitting pending while
a dependency is discovered is not hypothetical.
"""

from __future__ import annotations

import pytest

from platform.remediation.autonomy.allow_list import (
    AllowList,
    AllowListEntry,
    EnvironmentIs,
    MaximumBlastRadius,
    RateLimit,
    TargetPattern,
    TimeWindow,
)
from platform.remediation.autonomy.evaluation import ConditionEvaluator, ExecutionLedger
from platform.remediation.autonomy.kill_switch import ORGANISATION_SCOPE, KillSwitch
from platform.remediation.errors import ConditionsNotMet, KillSwitchEngaged

PRODUCTION = "production"
STAGING = "staging"
TEAM = "team-payments"
WORKLOAD = "checkout-api"


# --- The kill switch ---------------------------------------------------------


async def test_the_kill_switch_refuses_an_action_that_was_already_approved(
    executor, plane, an_action, clock, registry, plans
) -> None:
    """Engaged between the approval and the execution, it still stops the write.

    The whole reason the switch is checked inside the executor rather than only
    at the gate. The human who approved this did so before whatever made an
    operator reach for the switch, and an approval is not a licence that
    outlives the reason it was granted.
    """
    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    executor.kill_switch.engage(engaged_by="grace", reason="cluster is unstable", at=clock())

    with pytest.raises(KillSwitchEngaged):
        await executor.execute(action, plan=plan, before=before, approval_id="change-1")

    assert not plane.was_applied


PRODUCTION = "production"
STAGING = "staging"
TEAM = "team-payments"
WORKLOAD = "checkout-api"


def test_an_organisation_switch_stops_a_team_that_has_none_of_its_own() -> None:
    """Scopes nest and the wider one wins.

    An org-wide stop a team could be outside of is not an org-wide stop, and the
    team asking "am I stopped" gets the widest reason rather than discovering
    the narrow one and concluding the rest of the estate is running.
    """
    switch = KillSwitch()
    switch.engage(engaged_by="grace", scope=ORGANISATION_SCOPE, reason="incident 4102")

    assert switch.is_engaged(team_node_id=TEAM)
    assert switch.state_for(team_node_id=TEAM) is not None
    assert switch.state_for(team_node_id=TEAM).scope == ORGANISATION_SCOPE


def test_releasing_an_organisation_switch_leaves_a_team_switch_engaged() -> None:
    """Each scope was engaged by somebody for a reason, and is released the same way.

    A release that quietly cleared scopes it was not asked about would be this
    control's failure mode rather than a convenience: the team that stopped its
    own writes would find them running again because somebody else resolved a
    different incident.
    """
    switch = KillSwitch()
    switch.engage(engaged_by="grace", scope=ORGANISATION_SCOPE)
    switch.engage(engaged_by="ada", scope=TEAM, reason="the deploy is still rolling")

    assert switch.release(released_by="grace", scope=ORGANISATION_SCOPE)
    assert switch.is_engaged(team_node_id=TEAM)
    assert not switch.is_engaged(team_node_id="team-search")


# --- The allow-list ----------------------------------------------------------


def test_an_entry_that_names_no_environment_never_covers_production(an_action) -> None:
    """Production is excluded unless an entry says otherwise, by construction.

    Added when the entry is built rather than left to the operator, because the
    alternative is a default nobody chose taking effect in the environment where
    a mistake is most expensive.
    """
    entry = AllowListEntry(capability="scale_workload", team_node_id=TEAM)
    conditions = [
        condition for condition in entry.conditions if isinstance(condition, EnvironmentIs)
    ]

    assert conditions, "an entry with no environment condition must be given one"
    assert PRODUCTION not in conditions[0].environments


def test_conditions_are_conjunctive_and_every_failure_is_reported(an_action, clock) -> None:
    """All of them have to hold, and an operator sees all of the ones that did not.

    Fixing one and re-running to discover the next is how an allow-list gets
    widened further than anybody intended.
    """
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(
            TargetPattern(pattern="staging-*"),
            MaximumBlastRadius(limit=2),
        ),
    )
    evaluator = ConditionEvaluator(allow_list=AllowList(entries=[entry]))

    evaluation = evaluator.evaluate(an_action(), at=clock(), blast_radius=19)

    assert not evaluation.permitted
    assert len(evaluation.unmet) == 2, evaluation.unmet
    assert any("staging-*" in reason for reason in evaluation.unmet)
    assert any("19 service(s)" in reason for reason in evaluation.unmet)


def test_conditions_holding_at_request_time_do_not_hold_at_execution_time(an_action, clock) -> None:
    """The re-evaluation the whole design turns on.

    The blast radius is two when the action is proposed and twenty when it runs,
    because a dependency was discovered while the approval waited. The first
    evaluation permits it; the second must not.
    """
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(MaximumBlastRadius(limit=5),),
    )
    evaluator = ConditionEvaluator(allow_list=AllowList(entries=[entry]))
    action = an_action()

    at_request = evaluator.evaluate(action, at=clock(), blast_radius=2)
    clock.advance(minutes=9)
    at_execution = evaluator.evaluate(action, at=clock(), blast_radius=20)

    assert at_request.permitted
    assert not at_execution.permitted
    with pytest.raises(ConditionsNotMet):
        at_execution.raise_if_refused()


def test_a_time_window_may_wrap_past_midnight(an_action, clock) -> None:
    """ "Outside business hours" is 18:00 to 08:00, and has to be expressible.

    A window type that could not wrap would be one operators worked around by
    declaring two entries, and two entries for one intent is one entry somebody
    forgets to narrow.
    """
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(TimeWindow(start_hour=18, end_hour=8),),
    )
    evaluator = ConditionEvaluator(allow_list=AllowList(entries=[entry]))

    clock.at = clock.at.replace(hour=23)
    assert evaluator.evaluate(an_action(), at=clock()).permitted

    clock.at = clock.at.replace(hour=11)
    assert not evaluator.evaluate(an_action(), at=clock()).permitted


def test_the_rate_limit_counts_completed_runs_and_not_attempts(an_action, clock) -> None:
    """A refused action must not spend the budget it was refused from.

    Recording at the point of permission would let a later refusal consume the
    limit, and the limit would bound attempts rather than changes — which is the
    opposite of what it is for.
    """
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(RateLimit(limit=2, window_seconds=3600),),
    )
    evaluator = ConditionEvaluator(
        allow_list=AllowList(entries=[entry]), ledger=ExecutionLedger(window_seconds=3600)
    )
    action = an_action()

    assert evaluator.evaluate(action, at=clock()).permitted
    evaluator.record_execution(action, at=clock())
    assert evaluator.evaluate(action, at=clock()).permitted
    evaluator.record_execution(action, at=clock())

    spent = evaluator.evaluate(action, at=clock())
    assert not spent.permitted
    assert any("at the permitted limit" in reason for reason in spent.unmet)


def test_the_rate_limit_window_moves(an_action, clock) -> None:
    """Runs outside the window stop counting, or the limit would be a lifetime cap."""
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(RateLimit(limit=1, window_seconds=600),),
    )
    evaluator = ConditionEvaluator(
        allow_list=AllowList(entries=[entry]), ledger=ExecutionLedger(window_seconds=600)
    )
    action = an_action()

    evaluator.record_execution(action, at=clock())
    assert not evaluator.evaluate(action, at=clock()).permitted

    clock.advance(minutes=11)
    assert evaluator.evaluate(action, at=clock()).permitted


def test_an_action_nobody_allow_listed_is_not_a_refusal_to_explain(an_action, clock) -> None:
    """The default is not an exception path.

    Most actions are not allow-listed and go to a human. Raising for that would
    turn the ordinary case into an error, and would make the log full of
    refusals that are just the system working.
    """
    evaluator = ConditionEvaluator(allow_list=AllowList())

    evaluation = evaluator.evaluate(an_action(), at=clock())

    assert not evaluation.permitted
    assert not evaluation.allow_listed
    evaluation.raise_if_refused()  # deliberately does not raise
    assert "not on this team's autonomous allow-list" in evaluation.describe()


def test_one_team_s_entry_does_not_cover_another_team(an_action, clock) -> None:
    """Entries are scoped per team, and the scope is part of the match."""
    entry = AllowListEntry(
        capability="scale_workload", team_node_id="team-search", environments=(STAGING,)
    )
    evaluator = ConditionEvaluator(allow_list=AllowList(entries=[entry]))

    assert not evaluator.evaluate(an_action(team_node_id=TEAM), at=clock()).allow_listed
    assert evaluator.evaluate(an_action(team_node_id="team-search"), at=clock()).allow_listed


def test_a_target_pattern_is_matched_case_sensitively(an_action, clock) -> None:
    """``staging-*`` does not match ``Staging-checkout``.

    Case-insensitive matching would make an allow-list wider than it reads, and
    the person who wrote ``staging-*`` did not agree to anything else.
    """
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(TargetPattern(pattern="staging-*"),),
    )
    evaluator = ConditionEvaluator(allow_list=AllowList(entries=[entry]))

    assert not evaluator.evaluate(an_action(identifier=f"Staging-{WORKLOAD}"), at=clock()).permitted
    assert evaluator.evaluate(an_action(identifier=f"staging-{WORKLOAD}"), at=clock()).permitted
