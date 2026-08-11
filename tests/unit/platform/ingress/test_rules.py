"""Ordered rules: first match wins, the last one catches everything, discard says why.

The three properties that make a rule set readable. Each of them is a bug this
shape prevents rather than a preference: two rules that could both apply is a
set nobody can predict from reading, a set with no catch-all leaves "everything
else" implicit, and an implicit default for discard is how an alert disappears
with nobody knowing it disappeared.
"""

from __future__ import annotations

import pytest

from config.constants.transit import (
    MAX_ROUTING_RULES,
    RULE_ACTION_DISCARD,
    RULE_ACTION_INVESTIGATE,
    RULE_ACTION_RECORD_ONLY,
)
from platform.ingress.rules import (
    RoutingRule,
    RuleSet,
    RuleSetInvalid,
    Signals,
    default_rule_set,
    evaluate,
)

pytestmark = pytest.mark.unit

CATCH_ALL = RoutingRule(rule_id="everything-else", action=RULE_ACTION_INVESTIGATE)


# --- Evaluation -------------------------------------------------------------------


def test_the_first_matching_rule_decides() -> None:
    """Order is the operator's, and it is preserved."""
    rules = RuleSet.of(
        (
            RoutingRule(rule_id="first", sources=("alertmanager",), team_node_id="platform"),
            RoutingRule(rule_id="second", sources=("alertmanager",), team_node_id="payments"),
            CATCH_ALL,
        )
    )

    match = evaluate(rules, Signals(source="alertmanager"))

    assert match.rule.rule_id == "first"
    assert match.team_node_id == "platform"


def test_a_delivery_matching_nothing_reaches_the_catch_all() -> None:
    rules = RuleSet.of((RoutingRule(rule_id="only-grafana", sources=("grafana",)), CATCH_ALL))

    match = evaluate(rules, Signals(source="sentry"))

    assert match.rule.rule_id == "everything-else"


def test_every_matcher_a_rule_declares_has_to_agree() -> None:
    """Matchers are conjunctive: a rule naming two dimensions means both."""
    rules = RuleSet.of(
        (
            RoutingRule(
                rule_id="critical-in-apps",
                zones=("apps",),
                criticalities=("critical",),
                team_node_id="platform",
            ),
            CATCH_ALL,
        )
    )

    assert (
        evaluate(rules, Signals(zone="apps", criticality="critical")).rule.rule_id
        == "critical-in-apps"
    )
    assert evaluate(rules, Signals(zone="apps", criticality="low")).rule.rule_id == (
        "everything-else"
    )


def test_a_rule_that_names_no_team_keeps_the_one_the_verifier_established() -> None:
    """Which is what makes the default set reproduce today's behaviour exactly."""
    match = evaluate(default_rule_set(), Signals(source="alertmanager", team_node_id="payments"))

    assert match.team_node_id == "payments"
    assert match.action == RULE_ACTION_INVESTIGATE


def test_a_resource_matcher_picks_out_one_thing() -> None:
    rules = RuleSet.of(
        (
            RoutingRule(
                rule_id="the-noisy-box",
                resource_ids=("proxmox:container/hal9000/110",),
                action=RULE_ACTION_RECORD_ONLY,
            ),
            CATCH_ALL,
        )
    )

    match = evaluate(rules, Signals(resource_id="proxmox:container/hal9000/110"))

    assert match.action == RULE_ACTION_RECORD_ONLY


# --- Validation -------------------------------------------------------------------


def test_a_set_without_a_catch_all_last_is_refused() -> None:
    """Acceptance 4: the fate of an unmatched delivery is an explicit choice."""
    with pytest.raises(RuleSetInvalid, match="no declared fate"):
        RuleSet.of((RoutingRule(rule_id="only-grafana", sources=("grafana",)),))


def test_a_catch_all_that_is_not_last_is_refused() -> None:
    with pytest.raises(RuleSetInvalid, match="can ever fire"):
        RuleSet.of((CATCH_ALL, RoutingRule(rule_id="unreachable", sources=("grafana",))))


def test_an_empty_set_is_refused() -> None:
    with pytest.raises(RuleSetInvalid, match="decides nothing"):
        RuleSet.of(())


def test_two_rules_with_one_name_are_refused() -> None:
    with pytest.raises(RuleSetInvalid, match="appears twice"):
        RuleSet.of(
            (
                RoutingRule(rule_id="same", sources=("grafana",)),
                RoutingRule(rule_id="same", sources=("sentry",)),
                CATCH_ALL,
            )
        )


def test_more_rules_than_the_bound_are_refused() -> None:
    many = [
        RoutingRule(rule_id=f"r{index}", sources=("grafana",)) for index in range(MAX_ROUTING_RULES)
    ]
    with pytest.raises(RuleSetInvalid, match="exceeds"):
        RuleSet.of([*many, CATCH_ALL])


def test_a_discard_without_a_reason_cannot_be_constructed() -> None:
    """Checked on the rule, so no editor, importer or evaluator can miss it."""
    with pytest.raises(RuleSetInvalid, match="without a reason"):
        RoutingRule(rule_id="quiet", sources=("sentry",), action=RULE_ACTION_DISCARD)


def test_an_action_nothing_implements_is_refused() -> None:
    with pytest.raises(RuleSetInvalid, match="expected one of"):
        RoutingRule(rule_id="odd", action="escalate")


def test_the_catch_all_is_always_reachable_for_the_editor_to_render() -> None:
    """Acceptance 4 again, from the console's side: there is always a row to show."""
    rules = RuleSet.of((RoutingRule(rule_id="only-grafana", sources=("grafana",)), CATCH_ALL))

    assert rules.catch_all.rule_id == "everything-else"
    assert rules.catch_all.is_catch_all


# --- Vocabulary -------------------------------------------------------------------


def test_a_zone_the_estate_has_never_heard_of_is_refused() -> None:
    """Zones come from the estate, not from text somebody typed."""
    rules = RuleSet.of((RoutingRule(rule_id="typo", zones=("aps",)), CATCH_ALL))

    with pytest.raises(RuleSetInvalid, match="can never fire"):
        rules.check_vocabulary(
            sources=("alertmanager",), zones=("apps", "storage"), criticalities=("critical",)
        )


def test_a_known_zone_passes_the_same_check() -> None:
    rules = RuleSet.of((RoutingRule(rule_id="apps", zones=("apps",)), CATCH_ALL))

    rules.check_vocabulary(
        sources=("alertmanager",), zones=("apps", "storage"), criticalities=("critical",)
    )


def test_an_estate_that_has_not_been_swept_yet_checks_nothing() -> None:
    """Refusing every zone matcher before the first sweep would refuse to configure
    the deployment before it has been configured."""
    rules = RuleSet.of((RoutingRule(rule_id="apps", zones=("apps",)), CATCH_ALL))

    rules.check_vocabulary(sources=(), zones=(), criticalities=())
