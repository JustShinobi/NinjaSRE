"""What a policy change would have done to a week that already happened."""

from __future__ import annotations

from datetime import timedelta

from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.preview import RecordedAction, preview_change
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import ScopeKind
from tests.unit.platform.autonomy.conftest import NOON, action, rule, subject


def a_recorded_week() -> tuple[RecordedAction, ...]:
    """Return seven days of actions, one a day, over two containers."""
    return tuple(
        RecordedAction(
            action=action(
                action_id=f"act-{day}",
                subjects=(subject(f"ct-10{day % 2}", labels={"env": "lab"}),),
                risk=RiskClass.LOW,
            ),
            at=NOON - timedelta(days=day),
        )
        for day in range(7)
    )


def test_a_change_reports_which_recorded_actions_it_would_decide_differently() -> None:
    before = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.PROPOSE_ONLY),))
    after = before.with_rules(
        (
            *before.rules,
            rule(ScopeKind.LABELS, AutonomyLevel.ACT_AND_REPORT, labels={"env": "lab"}),
        )
    )

    change = preview_change(before, after, a_recorded_week())

    assert len(change.previewed) == 7
    assert len(change.changed) == 7
    assert len(change.newly_autonomous) == 7
    assert "7 of the last 7 action(s) would be decided differently" in change.summarise()
    assert change.previewed[0].before is AutonomyLevel.PROPOSE_ONLY
    assert change.previewed[0].after is AutonomyLevel.ACT_AND_REPORT


def test_a_change_that_only_tightens_reports_nothing_as_newly_autonomous() -> None:
    before = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),))
    after = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.PROPOSE_ONLY),))

    change = preview_change(before, after, a_recorded_week())

    assert len(change.changed) == 7
    assert change.newly_autonomous == ()
    assert "would no longer" in change.changed[0].describe()


def test_a_change_that_touches_nothing_recorded_reports_no_differences() -> None:
    before = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.PROPOSE_ONLY),))
    after = before.with_rules(
        (
            *before.rules,
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-999"),
        )
    )

    change = preview_change(before, after, a_recorded_week())

    assert change.changed == ()
    assert "would have been decided differently" in change.summarise()


def test_a_change_is_previewed_against_only_the_resources_it_reaches() -> None:
    before = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.PROPOSE_ONLY),))
    after = before.with_rules(
        (
            *before.rules,
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-101"),
        )
    )

    change = preview_change(before, after, a_recorded_week())

    assert {entry.subjects[0] for entry in change.changed} == {"ct-101"}
    assert len(change.changed) == 3


def test_each_recorded_action_is_replayed_at_its_own_instant() -> None:
    """A freeze last Tuesday says nothing about a freeze today."""
    from datetime import time

    from platform.autonomy.bounds import FreezeWindow
    from platform.autonomy.scopes import PolicyScope

    window = FreezeWindow(
        name="backups",
        scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
        start=time(11, 0),
        end=time(13, 0),
    )
    before = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),))
    after = PolicySet(rules=before.rules, freezes=(window,))

    change = preview_change(before, after, a_recorded_week())

    # A freeze is a bound rather than a level, so the resolution is unchanged.
    # The preview is honest about that instead of inventing a level for it.
    assert change.changed == ()
    assert all(entry.after is AutonomyLevel.ACT_AND_REPORT for entry in change.previewed)


def test_a_preview_over_no_history_says_so_rather_than_reporting_no_change() -> None:
    empty = PolicySet()
    change = preview_change(empty, empty, ())
    assert "no recorded history" in change.summarise()


def test_a_preview_is_bounded_by_how_much_it_will_replay() -> None:
    change = preview_change(PolicySet(), PolicySet(), a_recorded_week(), limit=3)
    assert len(change.previewed) == 3


def test_the_preview_uses_the_same_resolver_the_gate_does() -> None:
    """A second implementation of precedence would be reassuring and wrong."""
    import inspect

    from platform.autonomy import preview, resolution

    source = inspect.getsource(preview)
    assert "resolve(" in source
    assert source.count("def resolve") == 0
    assert resolution.resolve.__module__ == "platform.autonomy.resolution"
