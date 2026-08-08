"""Noticing that this is the fourth time, and calling it a different thing.

Four incidents about the same container filling up are not four problems. They
are one problem and four symptoms, and a system that keeps clearing the disk is
an efficient way of never fixing the leak. So on the fourth occurrence inside
the declared window the deployment stops treating it as an incident to fix and
raises a *recurring problem*: a pattern, closed by a change rather than by a
fifth restart.

**The count is per resource and per capability.** A global count would raise a
pattern the first busy week the deployment had; a count per resource alone would
merge a restart and a scale into one story that is not true of either.

**The count is a query, not a counter.** It is taken over the ledger's own rows
inside the window, so it survives a restart for free and cannot drift from the
history it is supposed to describe. A counter would be a second number that can
disagree with the rows, and the disagreement would surface as a pattern raised
about something that happened twice.

**Raising a pattern suppresses repetition rather than blocking everything.**
Autonomous repetition of *that capability on that resource* stops; a human may
still approve one, and every other capability is untouched. The suppression is
the live problem itself, which is why there is no second flag: an operator has
one thing to look at, and closing the problem is what lets the deployment act
again.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from config.constants.closed_loop import (
    DEFAULT_RECURRENCE_THRESHOLD,
    DEFAULT_RECURRENCE_WINDOW_SECONDS,
    MAX_EFFECTIVENESS_PAGE_SIZE,
    MAX_RECURRENCE_WINDOW_SECONDS,
    MAX_RECURRING_PROBLEM_PAGE_SIZE,
)
from platform.observability.logging import get_logger
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    RecurringProblem,
    RemediationLedger,
    RemediationOutcome,
)
from platform.remediation.errors import UnknownRecurringProblem
from platform.remediation.models import utc_now

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """How many times, over how long, before a pattern is worth naming.

    Per capability, because the thresholds genuinely differ: restarting a
    workload four times a month is a leak, and toggling a feature flag four
    times a month is a Tuesday. The defaults are the deployment's, and a
    capability that needs its own says so through the config service.
    """

    threshold: int = DEFAULT_RECURRENCE_THRESHOLD
    window_seconds: int = DEFAULT_RECURRENCE_WINDOW_SECONDS

    def __post_init__(self) -> None:
        if self.threshold < 2:
            raise ValueError(
                f"A recurrence threshold of {self.threshold} is not a recurrence. Two is "
                f"the smallest number of occurrences that can be a pattern."
            )
        if not 0 < self.window_seconds <= MAX_RECURRENCE_WINDOW_SECONDS:
            raise ValueError(
                f"A recurrence window of {self.window_seconds}s is outside "
                f"(0, {MAX_RECURRENCE_WINDOW_SECONDS}]. Beyond a year the count stops "
                f"describing the system that exists now."
            )

    def since(self, now: datetime) -> datetime:
        """Return the instant the window opens for a count taken at ``now``."""
        return now - timedelta(seconds=self.window_seconds)

    def describe(self) -> str:
        """Return the sentence the raised problem carries about its own bounds."""
        days = self.window_seconds / 86_400
        return f"{self.threshold} applications within {days:g} days"


def problem_key(capability: str, resource_id: str) -> str:
    """Return the pattern one capability applied to one resource is counted under."""
    return f"{capability}@{resource_id}"


@dataclass(slots=True)
class RecurrenceWatch:
    """Counts identical remediations in the window and names the pattern.

    ``rules`` is a mapping rather than one rule, so a deployment can tune the
    count per capability through the config service — which the plan asks for,
    and which matters because a badly tuned window is visible only in use.
    """

    ledger: RemediationLedger
    rules: dict[str, RecurrenceRule] = field(default_factory=dict)
    default_rule: RecurrenceRule = field(default_factory=RecurrenceRule)
    clock: Callable[[], datetime] = field(default=utc_now)
    identifiers: Callable[[str, datetime], str] = field(
        default=lambda pattern, at: f"{pattern}@{at.isoformat()}"
    )

    def rule_for(self, capability: str) -> RecurrenceRule:
        """Return ``capability``'s rule, or the deployment's default."""
        return self.rules.get(capability, self.default_rule)

    async def count(
        self,
        capability: str,
        resource_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        """Return how many times this capability has run here inside the window."""
        at = now if now is not None else self.clock()
        rule = self.rule_for(capability)
        history = await self.ledger.history(
            EffectivenessQuery(
                capabilities=(capability,),
                resource_ids=(resource_id,),
                since=rule.since(at),
                limit=MAX_EFFECTIVENESS_PAGE_SIZE,
            )
        )
        return len(history)

    async def observe(
        self,
        outcome: RemediationOutcome,
        *,
        now: datetime | None = None,
    ) -> RecurringProblem | None:
        """Return the problem this occurrence raised, or ``None`` if it did not.

        Called once per verified remediation. Returns ``None`` when a live
        problem already exists for the pattern — the pattern was already named,
        and naming it again would give an operator two things to close for one
        leak.
        """
        at = now if now is not None else self.clock()
        rule = self.rule_for(outcome.capability)
        pattern = problem_key(outcome.capability, outcome.resource_id)

        existing = await self.ledger.open_problem_for(pattern)
        if existing is not None:
            return None

        history = await self.ledger.history(
            EffectivenessQuery(
                capabilities=(outcome.capability,),
                resource_ids=(outcome.resource_id,),
                since=rule.since(at),
                limit=MAX_EFFECTIVENESS_PAGE_SIZE,
            )
        )
        if len(history) < rule.threshold:
            return None

        problem = RecurringProblem(
            problem_id=self.identifiers(pattern, at),
            pattern_key=pattern,
            capability=outcome.capability,
            resource_id=outcome.resource_id,
            title=f"{outcome.capability} keeps being applied to {outcome.resource_id}",
            summary=(
                f"{len(history)} applications of {outcome.capability} to "
                f"{outcome.resource_id} in the last {rule.window_seconds / 86_400:g} days. "
                f"This is a pattern rather than an occurrence: it is closed by a change, "
                f"not by another remediation, and autonomous repetition is suppressed "
                f"until it is."
            ),
            raised_at=at,
            occurrences=len(history),
            window_seconds=rule.window_seconds,
            action_ids=tuple(row.action_id for row in history),
            team_node_id=outcome.team_node_id,
            incident_ids=tuple(sorted({row.incident_id for row in history if row.incident_id})),
        )
        stored = await self.ledger.upsert_problem(problem)
        _LOG.warning(
            "remediation.recurrence_raised",
            problem_id=stored.problem_id,
            capability=stored.capability,
            resource_id=stored.resource_id,
            occurrences=stored.occurrences,
            window_seconds=stored.window_seconds,
        )
        return stored

    async def suppressing(self, capability: str, resource_id: str) -> RecurringProblem | None:
        """Return the live problem suppressing this repetition, or ``None``.

        Asked on the path of a decision, which is why it is a single indexed
        lookup on the pattern rather than a count. A count here would make every
        proposal pay for the history.
        """
        problem = await self.ledger.open_problem_for(problem_key(capability, resource_id))
        return problem if problem is not None and problem.suppressing else None

    async def problems(
        self,
        *,
        live_only: bool = True,
        limit: int = MAX_RECURRING_PROBLEM_PAGE_SIZE,
    ) -> tuple[RecurringProblem, ...]:
        """Return the recurring problems, most recently raised first."""
        return await self.ledger.problems(live_only=live_only, limit=limit)

    async def close(
        self,
        problem_id: str,
        *,
        principal_id: str,
        change: str,
        at: datetime | None = None,
    ) -> RecurringProblem:
        """Close ``problem_id``, naming the change that closed it, and return it.

        ``change`` is required and the type enforces it. A recurring problem is
        closed by a change — more disk, a rotation, a fixed leak — and a close
        that did not say which is a record that the problem stopped being
        displayed.
        """
        found = next(
            (
                problem
                for problem in await self.ledger.problems(live_only=False)
                if problem.problem_id == problem_id
            ),
            None,
        )
        if found is None:
            raise UnknownRecurringProblem(problem_id)

        closed = replace(
            found,
            closed_at=at if at is not None else self.clock(),
            close_reason=change,
            closed_by=principal_id,
        )
        stored = await self.ledger.upsert_problem(closed)
        _LOG.info(
            "remediation.recurrence_closed",
            problem_id=stored.problem_id,
            closed_by=principal_id,
            change=change,
        )
        return stored


__all__ = [
    "RecurrenceRule",
    "RecurrenceWatch",
    "problem_key",
]
