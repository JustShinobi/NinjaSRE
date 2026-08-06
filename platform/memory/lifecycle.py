"""Writing the episode at run end: once per conversation, whatever else happens.

The hook is ``on_run_end``, and three properties of it are load-bearing.

**Exactly once per conversation.** The key is the correlation id, the write is an
upsert, and this object refuses to finalise a session it has already finalised.
Both halves are needed and neither is redundant: the in-process guard closes the
window two concurrent turns would race through, and the upsert closes the one two
*processes* would — a resumed run finalising in a second worker cannot produce a
second episode, because there is one row and both writers name it.

**It never fails the run.** Extraction is already failure-isolated; this adds the
rest — a store that is down, an index that was never declared, a guardrail that
threw. All of it is logged and none of it propagates. The hook registry would
swallow an exception anyway and record it as a hook failure; catching here means
the *reason* is a memory reason rather than a stack trace attributed to a hook.

**Content is scanned before it is persisted.** An episode is written to the
database, and a secret in the database is a secret in every backup and every
replica from then on. The engine redacts rather than refuses, for the same reason
``post_tool_use`` does: the investigation already happened, and dropping the
episode would lose the learning while the secret has already been removed from
the text. Which rules fired is recorded on the episode, so a corpus can be
audited without reading it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from config.prompts.memory import EPISODE_SKIPPED_DISABLED
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.runtime_port import RunResult
from core.agent.session import Session
from platform.guardrails.engine import GuardrailEngine
from platform.memory.effectiveness import EffectivenessInputs, effectiveness, formula_version
from platform.memory.embeddings.port import Embedder, embed_one
from platform.memory.extraction import (
    EpisodeExtraction,
    EpisodeExtractor,
    capability_sequence,
    observed_findings,
)
from platform.memory.models import MemoryEpisode
from platform.memory.models import now as _utc_now
from platform.memory.policy import MemoryPolicy
from platform.memory.retrieval import RecallLedger
from platform.memory.strategy.invalidation import StrategyInvalidator
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import VectorRecord

logger = get_logger(__name__)

#: The name the hook registers under.
MEMORY_LIFECYCLE_HOOK = "memory.on_run_end"

#: Late, so a hook that adds evidence or rewrites the answer has already run —
#: the episode should record the run as it finished, not as it stood halfway
#: through the other run-end hooks.
HOOK_ORDER = 200


@dataclass(frozen=True, slots=True)
class FinalisationOutcome:
    """What finalising one run did, including when it deliberately did nothing."""

    episode: MemoryEpisode | None = None
    written: bool = False
    skipped: bool = False
    reason: str = ""

    @property
    def correlation_id(self) -> str:
        """Return the conversation this outcome is about, if an episode was built."""
        return self.episode.correlation_id if self.episode else ""


@dataclass(slots=True)
class MemoryLifecycle:
    """Turns a finished run into one episode, exactly once."""

    gateway: PersistenceGateway
    scope: TenantScope
    embedder: Embedder
    extractor: EpisodeExtractor
    policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    engine: GuardrailEngine | None = None
    ledger: RecallLedger = field(default_factory=RecallLedger)
    clock: Callable[[], datetime] = _utc_now
    invalidator: StrategyInvalidator | None = None
    _finalised: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: an episode must be written under a team — an "
                "unscoped episode is one every team can retrieve"
            )

    # -- the hook --------------------------------------------------------------

    async def on_run_end(self, session: Session, result: Any) -> None:
        """Finalise ``session`` into an episode, swallowing every failure.

        The broad catch is the contract. An investigation that produced an answer
        has succeeded, and nothing this module does to record it afterwards may
        change that.
        """
        try:
            await self.finalise(session, result)
        except Exception as error:  # noqa: BLE001 — memory must never fail a run
            logger.warning("memory.finalisation_failed", session=session.id, error=str(error))

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach the finalisation hook to ``hooks`` and return it."""
        hooks.register(
            HookPoint.ON_RUN_END,
            self.on_run_end,
            name=MEMORY_LIFECYCLE_HOOK,
            order=HOOK_ORDER,
        )
        return hooks

    # -- finalisation ----------------------------------------------------------

    async def finalise(self, session: Session, result: Any) -> FinalisationOutcome:
        """Return what writing the episode for ``session`` did.

        Claiming the session is the first thing that happens and it happens
        before any await. Two turns of the same conversation finishing at once
        both reach this method; the second one finds the id already claimed and
        stops, and there is no suspension point between the check and the claim
        for it to slip through.
        """
        if not self.policy.write_enabled:
            return FinalisationOutcome(skipped=True, reason=EPISODE_SKIPPED_DISABLED)

        correlation_id = self._correlation_id(session)
        if correlation_id in self._finalised:
            return FinalisationOutcome(
                skipped=True,
                reason=f"{correlation_id} was already finalised by this runtime",
            )
        self._finalised.add(correlation_id)

        answer = _answer(result)
        self.ledger.mark_acted_on(answer)

        outcome = await self.extractor.extract(
            objective=session.objective,
            answer=answer,
            capabilities=capability_sequence(session),
            findings=observed_findings(session),
        )
        extraction = outcome.extraction
        if extraction is None:
            # A skip is a decision and a failure is a breakage; both leave the
            # session claimed, because retrying either at the next hook would
            # spend another model call on the same unusable run.
            logger.info(
                "memory.episode_not_written",
                session=session.id,
                skipped=outcome.skipped,
                reason=outcome.reason,
            )
            return FinalisationOutcome(skipped=outcome.skipped, reason=outcome.reason)

        episode = self._episode(session, correlation_id, extraction)
        await self._persist(episode)
        logger.info(
            "memory.episode_written",
            session=session.id,
            episode=episode.correlation_id,
            resolved=episode.resolved,
            effectiveness=round(episode.effectiveness_score, 3),
        )
        return FinalisationOutcome(episode=episode, written=True)

    # -- building --------------------------------------------------------------

    def _episode(
        self,
        session: Session,
        correlation_id: str,
        extraction: EpisodeExtraction,
    ) -> MemoryEpisode:
        """Return the episode this run produced, scanned and scored."""
        scanned, rules = self._scan(extraction)
        moment = self.clock()

        return MemoryEpisode(
            correlation_id=correlation_id,
            org_id=self.scope.org_id,
            team_node_id=self.scope.team_node_id or "",
            issue_type=scanned.issue_type,
            issue_description=scanned.issue_description,
            severity=scanned.severity,
            components=scanned.components,
            capabilities_used=capability_sequence(session),
            key_findings=scanned.key_findings,
            resolved=scanned.resolved,
            root_cause=scanned.root_cause,
            summary=scanned.summary,
            effectiveness_score=effectiveness(self._effectiveness_inputs(session, scanned)),
            effectiveness_formula_version=formula_version(),
            duration_seconds=(moment - session.started_at).total_seconds(),
            iterations=session.iteration,
            run_id=session.id,
            occurred_at=session.started_at,
            updated_at=moment,
            embedding_model=self.embedder.model,
            embedding_dimension=self.embedder.dimension,
            guardrail_rules_fired=rules,
        )

    @staticmethod
    def _effectiveness_inputs(
        session: Session, extraction: EpisodeExtraction
    ) -> EffectivenessInputs:
        """Return what the documented formula reads for this run.

        Evidence backing is measured over the run's own evidence: a claim is
        "backed" when the entry it rests on was cited during the investigation.
        That is the same signal the context budget's value function uses, and
        reusing it means the two never disagree about what a run relied on.
        """
        total = len(session.evidence)
        return EffectivenessInputs(
            resolved=extraction.resolved,
            has_root_cause=bool(extraction.root_cause.strip()),
            validated_claims=sum(1 for entry in session.evidence if entry.cited),
            total_claims=total,
            iterations=session.iteration,
        )

    def _scan(self, extraction: EpisodeExtraction) -> tuple[EpisodeExtraction, tuple[str, ...]]:
        """Return ``extraction`` with every readable field redacted, and the rules fired."""
        if self.engine is None:
            return extraction, ()

        fired: dict[str, None] = {}

        def clean(text: str) -> str:
            if not text:
                return text
            result = self.engine.scan(text) if self.engine else None
            if result is None:
                return text
            for rule in result.rules_fired:
                fired.setdefault(rule, None)
            return result.text

        scanned = replace(
            extraction,
            issue_description=clean(extraction.issue_description),
            root_cause=clean(extraction.root_cause),
            summary=clean(extraction.summary),
            key_findings=tuple(
                replace(finding, query=clean(finding.query), finding=clean(finding.finding))
                for finding in extraction.key_findings
            ),
        )
        return scanned, tuple(fired)

    # -- writing ---------------------------------------------------------------

    async def _persist(self, episode: MemoryEpisode) -> None:
        """Write the episode and its vector in one unit of work.

        One transaction for both, so a crash between them cannot leave a vector
        pointing at nothing or an episode nothing can find. The embedding is
        computed outside the block: it may reach a hosted model, and holding a
        transaction open across a network call is how a pool is exhausted by a
        provider having a slow afternoon.
        """
        embedding = await embed_one(self.embedder, episode.embedding_text())

        async with self.gateway.begin(self.scope) as uow:
            existing = await uow.episodes.get(episode.correlation_id)
            merged = (
                episode.merged_with(MemoryEpisode.from_stored(existing, org_id=self.scope.org_id))
                if existing is not None
                else episode
            )

            await uow.episodes.save(merged.to_stored())
            await uow.vectors.ensure(
                EPISODE_VECTOR_NAMESPACE,
                model=self.embedder.model,
                dimension=self.embedder.dimension,
            )
            await uow.vectors.upsert(
                EPISODE_VECTOR_NAMESPACE,
                [
                    VectorRecord(
                        vector_id=merged.correlation_id,
                        embedding=embedding,
                        metadata=merged.vector_metadata(),
                    )
                ],
            )
            if self.invalidator is not None:
                # In the same unit of work as the episode, so there is no window
                # in which the new episode exists and a playbook it contradicts
                # is still being served as current.
                await self.invalidator.on_episode_written(uow, merged)

    @staticmethod
    def _correlation_id(session: Session) -> str:
        """Return the conversation this session belongs to.

        A sub-agent's session is part of its parent's conversation, so its
        episode is the parent's episode. Without this a five-specialist
        investigation would write six episodes, five of which describe a
        fragment of it.
        """
        return session.parent_id or session.id


def _answer(result: Any) -> str:
    """Return the run's answer, whatever shape the result arrived in.

    Typed against ``RunResult`` but not requiring it: the hook point passes
    ``Any``, an alternative runtime may pass its own record, and a memory layer
    that crashed on an unfamiliar result type would be failing the run it exists
    to record.
    """
    if isinstance(result, RunResult):
        return result.answer
    return str(getattr(result, "answer", "") or "")


__all__ = [
    "HOOK_ORDER",
    "MEMORY_LIFECYCLE_HOOK",
    "FinalisationOutcome",
    "MemoryLifecycle",
]
