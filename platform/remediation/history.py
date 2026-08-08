"""What has worked here before, and getting it in front of the decision.

Recording effectiveness is worth nothing on its own. The value is entirely in
two places: an agent proposing a remediation reads what happened the last four
times it was tried on this resource, and a human reviewing the proposal sees the
same thing. This module is the read side of the ledger and the route into the
memory the rest of the platform already learns from.

**One sentence, not a table.** ``PriorEffectiveness.describe`` is what goes into
the proposal's evidence and onto the approval request. A model handed a table of
counts will summarise it, differently each time; a model handed "this has been
tried here 4 times and worked once; the last attempt made things worse" has
nothing to summarise.

**Never verified is not never worked.** A capability with three actions all
still settling has no history, and reporting a zero success ratio for it would
argue against a remediation for the sole reason that it is recent. ``known`` is
the flag that keeps those apart.

**The learning goes into episodic memory, not into a second store.** FR-016, and
it is a constitutional point rather than a tidiness one: every learning
mechanism here ships with an ablation that isolates its contribution, and a
parallel effectiveness store would be a second learning system whose
contribution nobody measures. So a verdict is written onto the episode of the
run that took the action, and the playbooks synthesised for that component are
marked stale — which is exactly what an episode write already does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.observability.logging import get_logger
from platform.persistence.ports.episode_store import EpisodeStore
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    EffectivenessSummary,
    RemediationLedger,
    RemediationOutcome,
    VerificationVerdict,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.remediation.models import RemediationEvidence, utc_now
from platform.remediation.obligations import Verification

_LOG = get_logger(__name__)

#: Where a verdict lands inside an episode's metadata. One key, because two
#: spellings would mean strategy synthesis reads half the history and nothing
#: would ever say so.
EPISODE_REMEDIATION_KEY = "remediation"

#: The tag an episode gains when the remediation it records was verified. Read
#: by recall, so "show me investigations where the fix worked" is a filter
#: rather than a scan.
EPISODE_TAG_PREFIX = "remediation:"


@dataclass(frozen=True, slots=True)
class PriorEffectiveness:
    """What has happened the last time this was tried here, in one value.

    Carries the summary as well as the sentence, because the API response and
    the console render the counts and the proposal renders the sentence, and
    computing the sentence twice from two shapes is how they come to disagree.
    """

    capability: str
    resource_id: str
    condition_key: str = ""
    summary: EffectivenessSummary = field(default_factory=EffectivenessSummary)

    @property
    def known(self) -> bool:
        """Return whether anything here has ever been verified.

        Distinct from a zero success ratio. A capability whose three attempts
        are all still settling has no history, and arguing against it for that
        reason would argue against every recent remediation.
        """
        return self.summary.verified > 0

    @property
    def success_ratio(self) -> float:
        """Return the share of verdicts that were ``EFFECTIVE``, in ``[0, 1]``."""
        return self.summary.success_ratio

    @property
    def discouraged(self) -> bool:
        """Return whether the history argues against trying this again here.

        Never worked, having been tried at least twice. Once is not a pattern
        and this is read by a model that will treat a strong word as an
        instruction — so the bar is deliberately the same one recurrence uses
        for the smallest thing it will call a pattern.
        """
        return self.known and self.summary.verified >= 2 and self.success_ratio == 0.0

    def describe(self) -> str:
        """Return the sentence a proposal and an approval request both carry."""
        where = f"{self.capability} on {self.resource_id}"
        if self.summary.total == 0:
            return f"{where} has not been tried here before."
        if not self.known:
            return (
                f"{where} has been tried {self.summary.total} time(s) here and none of "
                f"them has finished settling, so nothing is known about whether it works."
            )
        effective = self.summary.counts.get(VerificationVerdict.EFFECTIVE, 0)
        parts = [
            f"{where} has been verified {self.summary.verified} time(s) here and worked "
            f"{effective} of them."
        ]
        if self.summary.last_verdict is not None:
            parts.append(f"The last attempt was {self.summary.last_verdict.value}.")
        if self.summary.counts.get(VerificationVerdict.WORSENED, 0):
            parts.append(
                f"{self.summary.counts[VerificationVerdict.WORSENED]} of them made things "
                f"worse and had to be rolled back."
            )
        if self.discouraged:
            parts.append("It has never worked here; propose something else and say why.")
        return " ".join(parts)

    def as_evidence(self) -> RemediationEvidence:
        """Return this history as the observation an approval request carries."""
        return RemediationEvidence(
            summary=self.describe(),
            reference=f"effectiveness:{self.capability}@{self.resource_id}",
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the API response and the console render."""
        return {
            "capability": self.capability,
            "resource_id": self.resource_id,
            "condition_key": self.condition_key,
            "total": self.summary.total,
            "verified": self.summary.verified,
            "awaiting": self.summary.awaiting,
            "success_ratio": round(self.success_ratio, 4),
            "counts": {
                verdict.value: count for verdict, count in sorted(self.summary.counts.items())
            },
            "last_at": self.summary.last_at.isoformat() if self.summary.last_at else None,
            "last_verdict": (
                self.summary.last_verdict.value if self.summary.last_verdict else None
            ),
            "known": self.known,
            "discouraged": self.discouraged,
            "summary": self.describe(),
        }


@dataclass(slots=True)
class EffectivenessHistory:
    """The read side of the ledger: what worked, sliced the three ways it is asked.

    Every method here is a count rather than a listing except ``recent``, which
    is what a human reads. That asymmetry is deliberate: the question on the
    decision path is "how often", and the question on a screen is "which ones".
    """

    ledger: RemediationLedger

    async def prior(
        self,
        capability: str,
        resource_id: str,
        *,
        condition_key: str = "",
        since: datetime | None = None,
    ) -> PriorEffectiveness:
        """Return what has happened when this was tried here before.

        The condition narrows when one is given, because "this restart works on
        this pod" and "this restart works when the pod is out of memory" are
        different claims and only the second is useful to a proposal about an
        out-of-memory pod.
        """
        summary = await self.ledger.effectiveness(
            EffectivenessQuery(
                capabilities=(capability,),
                resource_ids=(resource_id,),
                condition_keys=(condition_key,) if condition_key else (),
                since=since,
            )
        )
        return PriorEffectiveness(
            capability=capability,
            resource_id=resource_id,
            condition_key=condition_key,
            summary=summary,
        )

    async def by_resource(self, resource_id: str, **narrow: Any) -> EffectivenessSummary:
        """Return how remediation has gone on one resource."""
        return await self.ledger.effectiveness(
            EffectivenessQuery(resource_ids=(resource_id,), **narrow)
        )

    async def by_capability(self, capability: str, **narrow: Any) -> EffectivenessSummary:
        """Return how one capability has gone, wherever it has been applied."""
        return await self.ledger.effectiveness(
            EffectivenessQuery(capabilities=(capability,), **narrow)
        )

    async def by_condition(self, condition_key: str, **narrow: Any) -> EffectivenessSummary:
        """Return how remediation has gone against one kind of problem."""
        return await self.ledger.effectiveness(
            EffectivenessQuery(condition_keys=(condition_key,), **narrow)
        )

    async def recent(
        self,
        *,
        resource_id: str = "",
        capability: str = "",
        condition_key: str = "",
        limit: int = 20,
    ) -> tuple[RemediationOutcome, ...]:
        """Return the individual actions a human is reading, most recent first.

        Raises ``BoundExceeded`` above ``MAX_EFFECTIVENESS_PAGE_SIZE`` rather
        than clamping, for the reason the storage layer gives: a caller that
        asked for five hundred and received a hundred has no way to tell that
        from there being a hundred.
        """
        return await self.ledger.history(
            EffectivenessQuery(
                resource_ids=(resource_id,) if resource_id else (),
                capabilities=(capability,) if capability else (),
                condition_keys=(condition_key,) if condition_key else (),
                limit=limit,
            )
        )


@runtime_checkable
class EffectivenessLookup(Protocol):
    """The one question a proposal asks the history: has this worked here?

    Narrower than ``EffectivenessHistory`` because that is genuinely all a
    request builder needs, and because the builder holds a gateway rather than a
    transaction — so the implementation it holds opens its own unit of work and
    the one a worker holds does not.
    """

    async def prior(
        self,
        capability: str,
        resource_id: str,
        *,
        condition_key: str = "",
    ) -> PriorEffectiveness:
        """Return what has happened when this was tried here before."""


@dataclass(slots=True)
class LedgerEffectiveness:
    """An effectiveness lookup that opens its own unit of work per question.

    What a long-lived request builder holds, for the reason ``LedgerVerification``
    exists: the history service takes a ledger bound to one transaction, and the
    builder outlives every transaction in the process.
    """

    gateway: PersistenceGateway
    scope: TenantScope

    async def prior(
        self,
        capability: str,
        resource_id: str,
        *,
        condition_key: str = "",
    ) -> PriorEffectiveness:
        """Return what has happened when this was tried here before."""
        async with self.gateway.begin(self.scope) as uow:
            return await EffectivenessHistory(ledger=uow.remediation).prior(
                capability, resource_id, condition_key=condition_key
            )


@dataclass(slots=True)
class EffectivenessMemory:
    """Routes a verdict into the episodic memory the platform already learns from.

    Not a second learning store. The verdict is written onto the episode of the
    run that took the action — the same record recall reads and strategy
    synthesis is built from — and the playbooks for that component are marked
    stale, because a remediation that turned out not to work is exactly the kind
    of contradiction a cached playbook should not survive.

    A verdict about a run with no episode is dropped with a log line rather than
    raised. Runs that wrote no episode are ordinary — memory writing is a policy
    switch, and an ablation turns it off deliberately — and a closed loop that
    failed because learning was disabled would make the ablation unrunnable.
    """

    episodes: EpisodeStore
    clock: Callable[[], datetime] = field(default=utc_now)

    async def record(self, verification: Verification) -> bool:
        """Write ``verification`` onto its run's episode and return whether it landed."""
        outcome = verification.outcome
        if not outcome.run_id:
            return False

        episode = await self.episodes.get_by_run(outcome.run_id)
        if episode is None:
            _LOG.debug(
                "remediation.effectiveness_not_routed",
                action_id=outcome.action_id,
                run_id=outcome.run_id,
                reason="the run wrote no episode",
            )
            return False

        recorded = list(episode.metadata.get(EPISODE_REMEDIATION_KEY, []))
        recorded.append(_episode_record(verification))
        tag = f"{EPISODE_TAG_PREFIX}{verification.verdict.value}"
        await self.episodes.save(
            replace(
                episode,
                metadata={**dict(episode.metadata), EPISODE_REMEDIATION_KEY: recorded},
                tags=tuple(dict.fromkeys((*episode.tags, tag))),
            )
        )

        if episode.components:
            # The playbook for this component said something that has now been
            # contradicted by what actually happened. Stale rather than deleted,
            # for the reason the store's own docstring gives.
            for component in episode.components:
                await self.episodes.mark_strategies_stale(
                    team_node_id=outcome.team_node_id,
                    issue_type=outcome.condition_key,
                    component_key=component,
                )

        _LOG.info(
            "remediation.effectiveness_routed_to_memory",
            action_id=outcome.action_id,
            run_id=outcome.run_id,
            episode_id=episode.episode_id,
            verdict=verification.verdict.value,
        )
        return True


def _episode_record(verification: Verification) -> dict[str, Any]:
    """Return what one verdict looks like inside an episode's metadata."""
    outcome = verification.outcome
    return {
        "action_id": outcome.action_id,
        "capability": outcome.capability,
        "resource_id": outcome.resource_id,
        "condition_key": outcome.condition_key,
        "verdict": verification.verdict.value,
        "before": dict(verification.before),
        "after": dict(verification.after),
        "settle_seconds": outcome.settle_seconds,
        "autonomous": outcome.autonomous,
    }


__all__ = [
    "EPISODE_REMEDIATION_KEY",
    "EPISODE_TAG_PREFIX",
    "EffectivenessHistory",
    "EffectivenessLookup",
    "EffectivenessMemory",
    "LedgerEffectiveness",
    "PriorEffectiveness",
]
