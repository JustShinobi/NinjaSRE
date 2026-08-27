"""The resolver: a level, and every reason it is that level.

A pure function of an action, a policy set and a clock. Purity is not a style
preference here — it is what makes the decision matrix a unit test rather than a
sampling, and what makes "these eleven actions from last week would now be
autonomous" answerable without a deployment to run them in.

**The explanation is part of the return value.** Returning a bare level would
make every "why did it do that" an archaeology exercise six weeks later, against
a policy set that has since been edited. So a resolution carries every rule that
was considered, whether it applied, which one won, and why — and that is what is
audited and what the console shows before the action, not a reconstruction of it.

**Most specific wins, and a tie is broken deterministically.** Two rules at the
same specificity are resolved to the *less permissive* of the two, and a tie
there is broken by rule identifier. Least-permissive-wins rather than
last-declared-wins because the order two rules appear in a merged document is an
artefact of the merge, and an operator should never discover that reordering
their configuration granted autonomy.

**A multi-subject action takes the least permissive level among its subjects.**
Draining a node touches every guest on it. Resolving to the node's own level
would be permitting changes to resources whose rules were never read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.constants.autonomy import DEFAULT_RISK_BOUND
from platform.autonomy.levels import DEFAULT_LEVEL, AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.risk import RiskClass
from platform.autonomy.subjects import ProposedAction, Subject


@dataclass(frozen=True, slots=True)
class ConsideredRule:
    """One rule the resolution looked at, and what became of it.

    Non-applying rules are kept. "There is no rule for this container" and "there
    is one and it did not win" send an operator to different screens, and a list
    of only the winners would collapse them.
    """

    rule_id: str
    scope: str
    level: AutonomyLevel
    specificity: int
    applied: bool
    won: bool = False
    subject: str = ""
    reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the audit detail carries."""
        return {
            "rule_id": self.rule_id,
            "scope": self.scope,
            "level": self.level.value,
            "specificity": self.specificity,
            "applied": self.applied,
            "won": self.won,
            "subject": self.subject,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Resolution:
    """What the policy set says about one action, and how it got there."""

    level: AutonomyLevel
    risk_bound: RiskClass
    dry_run: bool = False
    winner: str = ""
    considered: tuple[ConsideredRule, ...] = ()
    #: The level each subject resolved to on its own, so an explanation can say
    #: which resource supplied the least permissive answer.
    per_subject: tuple[tuple[str, AutonomyLevel], ...] = ()
    reason: str = ""

    @property
    def from_default(self) -> bool:
        """Return whether nothing applied and the safe default was used."""
        return not self.winner

    def describe(self) -> str:
        """Return the sentence an operator or a proposal shows."""
        return self.reason

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the audit trail and the API carry."""
        return {
            "level": self.level.value,
            "risk_bound": self.risk_bound.value,
            "dry_run": self.dry_run,
            "winner": self.winner,
            "considered": [entry.to_record() for entry in self.considered],
            "per_subject": [
                {"subject": subject, "level": level.value} for subject, level in self.per_subject
            ],
            "reason": self.reason,
        }


def resolve(action: ProposedAction, policies: PolicySet, *, at: datetime) -> Resolution:
    """Return the level ``action`` resolves to under ``policies`` at ``at``.

    Pure: the same three arguments always produce the same resolution, and
    nothing here reads a clock, a database or an environment of its own.
    """
    rules = policies.active_rules(at)
    considered: list[ConsideredRule] = []
    per_subject: list[tuple[str, AutonomyLevel]] = []
    winners: list[tuple[Subject, PolicyRule | None]] = []

    for subject in action.subjects:
        applicable = [rule for rule in rules if rule.applies_to(action, subject)]
        winner = _winner(applicable)
        winners.append((subject, winner))
        per_subject.append(
            (subject.resource_id, winner.level if winner is not None else DEFAULT_LEVEL)
        )
        considered.extend(_considered(rules, applicable, winner, subject))

    least = min(
        winners,
        key=lambda pair: (
            pair[1].level.rank if pair[1] is not None else DEFAULT_LEVEL.rank,
            pair[0].resource_id,
        ),
    )
    subject, rule = least
    level = rule.level if rule is not None else DEFAULT_LEVEL
    bound = rule.risk_bound if rule is not None else RiskClass(DEFAULT_RISK_BOUND)
    dry_run = policies.dry_run or any(held.dry_run for _, held in winners if held is not None)

    return Resolution(
        level=level,
        risk_bound=bound,
        dry_run=dry_run,
        winner=rule.rule_id if rule is not None else "",
        considered=tuple(_marked(considered, rule, subject)),
        per_subject=tuple(per_subject),
        reason=_reason(action, subject, rule, level, dry_run, len(action.subjects)),
    )


def _winner(applicable: Sequence[PolicyRule]) -> PolicyRule | None:
    """Return the rule that wins among ``applicable``, or ``None`` when empty.

    Most specific first; on a tie, the less permissive; on a tie there, the
    lower rule identifier. Every step is total, so two policy sets that are
    equal produce the same winner whatever order they were assembled in.
    """
    if not applicable:
        return None
    return min(
        applicable,
        key=lambda rule: (-rule.specificity, rule.level.rank, rule.rule_id),
    )


def _considered(
    rules: Sequence[PolicyRule],
    applicable: Sequence[PolicyRule],
    winner: PolicyRule | None,
    subject: Subject,
) -> list[ConsideredRule]:
    """Return the record of every rule looked at for one subject."""
    applied = {rule.rule_id for rule in applicable}
    entries: list[ConsideredRule] = []
    for rule in rules:
        did_apply = rule.rule_id in applied
        entries.append(
            ConsideredRule(
                rule_id=rule.rule_id,
                scope=rule.scope.describe(),
                level=rule.level,
                specificity=rule.specificity,
                applied=did_apply,
                won=did_apply and winner is not None and rule.rule_id == winner.rule_id,
                subject=subject.resource_id,
                reason=("" if did_apply else f"does not cover {subject.resource_id}"),
            )
        )
    return entries


def _marked(
    considered: Sequence[ConsideredRule], winner: PolicyRule | None, subject: Subject
) -> list[ConsideredRule]:
    """Return ``considered`` with only the action's overall winner marked as won.

    A rule can win for one subject and lose the action, when a second subject
    resolved lower. Leaving both marked would make the explanation say two rules
    decided one action.
    """
    if winner is None:
        return list(considered)
    return [
        entry
        if entry.won and entry.rule_id == winner.rule_id and entry.subject == subject.resource_id
        else _unwon(entry)
        for entry in considered
    ]


def _unwon(entry: ConsideredRule) -> ConsideredRule:
    """Return ``entry`` with its win cleared."""
    if not entry.won:
        return entry
    return ConsideredRule(
        rule_id=entry.rule_id,
        scope=entry.scope,
        level=entry.level,
        specificity=entry.specificity,
        applied=entry.applied,
        won=False,
        subject=entry.subject,
        reason="won for this resource, but a less permissive resource decided the action",
    )


def _reason(
    action: ProposedAction,
    subject: Subject,
    rule: PolicyRule | None,
    level: AutonomyLevel,
    dry_run: bool,
    subjects: int,
) -> str:
    """Return the sentence that explains this resolution to a person."""
    simulated = " Actions in this scope are simulated rather than executed." if dry_run else ""
    if rule is None:
        return (
            f"No rule covers {action.capability} on {subject.resource_id}, so it resolves to "
            f"{level.label}: {level.describe()}{simulated}"
        )
    across = (
        f" It is the least permissive of the {subjects} resources this action targets."
        if subjects > 1
        else ""
    )
    return (
        f"{action.capability} on {subject.resource_id} resolves to {level.label} because "
        f"{rule.describe()} is the most specific rule that applies.{across}{simulated}"
    )


__all__ = [
    "ConsideredRule",
    "Resolution",
    "resolve",
]
