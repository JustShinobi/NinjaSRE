"""How a parent's health accounts for its children, and how it shows that it did.

A node whose every guest is down is not a healthy node, whatever the hypervisor
says about the node itself. But "worst child wins" is wrong just as often: a
cluster of forty machines with one degraded guest is a cluster with one degraded
guest, not a degraded cluster, and an estate that says otherwise trains an
operator to ignore the top-level number.

So the rule is *declared per kind* and *visible on the parent*. Three rules
cover everything seen so far, each of them a different answer to "when does a
child's problem become the parent's":

``OWN_ONLY``
    Children do not affect the parent. Right when the parent is a container for
    unrelated things — a datacentre holding two customers' racks.

``WORST_CHILD``
    Any child's problem is the parent's problem. Right when the parent cannot do
    its job while a child is failing — a backup job covering four datastores is
    not succeeding if one of them is unreachable.

``MAJORITY_HEALTHY``
    The parent is healthy while most children are, degraded while some are not,
    and unhealthy when most are not. Right for the aggregate cases — a node full
    of guests, a cluster full of nodes.

Whichever applies, the parent's derivation names it and lists the children that
decided, so an operator asking "why is this node degraded" gets the answer rather
than a number.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Final

from config.constants.estate import MAX_HEALTH_SIGNALS
from platform.persistence.ports.estate_repository import (
    HealthDerivation,
    HealthSignal,
    Resource,
    ResourceHealth,
)

#: The rule name a rolled-up derivation carries, so the transition log and the
#: query surface both say "this came from the children" in one spelling.
RULE_PREFIX: Final = "rollup:"

#: States that count against a parent. Maintenance is excluded on purpose: a
#: guest deliberately paused must not make its node look degraded, or an
#: operator doing planned work would light up the whole estate.
_COUNTS_AGAINST: Final = frozenset({ResourceHealth.DEGRADED, ResourceHealth.UNHEALTHY})


class RollupRule(StrEnum):
    """How a parent's state accounts for its children."""

    OWN_ONLY = "own_only"
    WORST_CHILD = "worst_child"
    MAJORITY_HEALTHY = "majority_healthy"


#: What each kind uses when nothing else is declared. A node and a cluster
#: aggregate; a backup job is only doing its job if every datastore it covers is
#: reachable; everything else answers for itself.
DEFAULT_RULES: dict[str, RollupRule] = {
    "cluster": RollupRule.MAJORITY_HEALTHY,
    "node": RollupRule.MAJORITY_HEALTHY,
    "backup_job": RollupRule.WORST_CHILD,
}


def rule_for(kind: str) -> RollupRule:
    """Return the rollup rule ``kind`` uses.

    ``OWN_ONLY`` for a kind nobody declared, which is the conservative default:
    a kind whose aggregation nobody thought about does not silently start
    inheriting its children's problems.
    """
    return DEFAULT_RULES.get(kind, RollupRule.OWN_ONLY)


def roll_up(
    parent: Resource,
    children: Sequence[Resource],
    *,
    now: datetime,
    rule: RollupRule | None = None,
) -> HealthDerivation:
    """Return ``parent``'s state with ``children`` accounted for, and the working.

    The parent's own derivation is the floor: a node the hypervisor says is
    offline stays unhealthy however healthy its guests look, because a guest
    that appears healthy on an unreachable node is a stale observation wearing
    a green badge.
    """
    applied = rule if rule is not None else rule_for(parent.kind)
    own = parent.derivation
    own_state = own.state if own is not None else ResourceHealth.UNKNOWN

    if applied is RollupRule.OWN_ONLY or not children:
        return _derived(
            state=own_state,
            rule=applied,
            now=now,
            signals=own.signals if own is not None else (),
            raw_status=own.raw_status if own is not None else "",
            explanation=(
                own.explanation
                if own is not None and applied is RollupRule.OWN_ONLY
                else f"{parent.display_name or parent.resource_id} has no children to account for."
            ),
        )

    states = [child.reported_health(now) for child in children]
    counted = [state for state in states if state is not ResourceHealth.MAINTENANCE]
    against = [state for state in counted if state in _COUNTS_AGAINST]

    from_children = (
        _worst(against) if applied is RollupRule.WORST_CHILD else _majority(counted, against)
    )
    state = _worse_of(own_state, from_children)

    return _derived(
        state=state,
        rule=applied,
        now=now,
        signals=_child_signals(children, states, now=now),
        raw_status=own.raw_status if own is not None else "",
        explanation=_explain(parent, applied, counted, against, state),
    )


def _worst(against: Sequence[ResourceHealth]) -> ResourceHealth:
    """Return the worst state among the children that count against the parent."""
    if not against:
        return ResourceHealth.HEALTHY
    return (
        ResourceHealth.UNHEALTHY if ResourceHealth.UNHEALTHY in against else ResourceHealth.DEGRADED
    )


def _majority(
    counted: Sequence[ResourceHealth],
    against: Sequence[ResourceHealth],
) -> ResourceHealth:
    """Return healthy, degraded, or unhealthy by how many children are in trouble."""
    if not counted:
        return ResourceHealth.UNKNOWN
    if not against:
        return ResourceHealth.HEALTHY
    # Strictly more than half, so an even split is degraded rather than
    # unhealthy: two of four guests down is a bad afternoon, not a dead node.
    return ResourceHealth.UNHEALTHY if len(against) * 2 > len(counted) else ResourceHealth.DEGRADED


#: Least to most severe, for comparing two verdicts. ``ABSENT`` and
#: ``MAINTENANCE`` are not on it: neither is a severity, and neither can be the
#: output of a rollup — a parent does not become absent because its children are.
_SEVERITY: Final[tuple[ResourceHealth, ...]] = (
    ResourceHealth.HEALTHY,
    ResourceHealth.UNKNOWN,
    ResourceHealth.STALE,
    ResourceHealth.DEGRADED,
    ResourceHealth.UNHEALTHY,
)


def _worse_of(own: ResourceHealth, from_children: ResourceHealth) -> ResourceHealth:
    """Return whichever of the two verdicts is more severe."""
    if own not in _SEVERITY:
        return own
    if from_children not in _SEVERITY:
        return own
    return max(own, from_children, key=_SEVERITY.index)


def _child_signals(
    children: Sequence[Resource],
    states: Sequence[ResourceHealth],
    *,
    now: datetime,
) -> tuple[HealthSignal, ...]:
    """Return one signal per child that counts against the parent, bounded.

    Only the children in trouble. Listing forty healthy guests on a healthy node
    is a derivation nobody reads, and the question a rollup answers is always
    "which of them is the problem".
    """
    collected: list[HealthSignal] = []
    for child, state in zip(children, states, strict=True):
        if state not in _COUNTS_AGAINST:
            continue
        if len(collected) >= MAX_HEALTH_SIGNALS:
            break
        collected.append(
            HealthSignal(
                name=f"child:{child.resource_id}",
                value=state.value,
                observed_at=now,
                source=child.source,
            )
        )
    return tuple(collected)


def _derived(
    *,
    state: ResourceHealth,
    rule: RollupRule,
    now: datetime,
    signals: tuple[HealthSignal, ...],
    raw_status: str,
    explanation: str,
) -> HealthDerivation:
    return HealthDerivation(
        state=state,
        rule=f"{RULE_PREFIX}{rule.value}",
        derived_at=now,
        signals=signals,
        raw_status=raw_status,
        explanation=explanation,
    )


def _explain(
    parent: Resource,
    rule: RollupRule,
    counted: Sequence[ResourceHealth],
    against: Sequence[ResourceHealth],
    state: ResourceHealth,
) -> str:
    """Return the sentence shown on the parent, naming the rule and the counts."""
    name = parent.display_name or parent.resource_id
    return (
        f"{name} is {state.value} under the {rule.value} rule: "
        f"{len(against)} of {len(counted)} children counted against it "
        f"(resources in maintenance are excluded)."
    )


__all__ = ["DEFAULT_RULES", "RULE_PREFIX", "RollupRule", "roll_up", "rule_for"]
