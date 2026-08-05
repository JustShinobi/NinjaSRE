"""What survives when the evidence outgrows the window, and why that one.

An investigation that gathers well runs out of context before it runs out of
iterations. Something has to go, and the interesting question is not *that* the
loop drops evidence — it is whether an operator reading the trace afterwards can
tell why the observation their conclusion needed was the one that went.

So the policy is four named terms and no judgement at the call site.

``recency``
    ``1 / (1 + age)`` in iterations. Steep rather than linear: the difference
    between "this turn" and "five turns ago" matters far more than the
    difference between fifteen and twenty.

``cited``
    A flat bonus, and the largest term. An entry a previous turn reasoned from
    is one the model will reach for again; evicting it is how a run forgets its
    own argument halfway through making it.

``size``
    A penalty proportional to the entry's share of the largest entry held. Two
    equally old observations are not equally expensive to keep.

``source reliability``
    A penalty on the agent's own reasoning output. It is worth keeping while it
    is fresh and it is the first thing to go against anything measured, because
    the model can restate a hypothesis and cannot re-observe a log line from
    four hours ago. The penalty is deliberately larger than the maximum size
    penalty, which makes provenance dominate volume.

Two passes, lowest value first: truncate to the floor, then — if that was not
enough — drop bodies entirely. An evicted entry keeps its summary and its
reference, because a reference is what makes a claim checkable and dropping the
pointer is data loss rather than a budget decision.

Both passes rewrite the transcript the model actually reads. Trimming the
evidence record while the transcript still carried the full payload would leave
the budget enforcing nothing at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from config.constants.investigation import (
    CONTEXT_EVIDENCE_BUDGET_RATIO,
    EVIDENCE_TRUNCATION_FLOOR_CHARS,
    EVIDENCE_VALUE_CITED_BONUS,
    EVIDENCE_VALUE_RECENCY_WEIGHT,
    EVIDENCE_VALUE_SIZE_PENALTY,
    EVIDENCE_VALUE_UNRELIABLE_PENALTY,
    UNRELIABLE_EVIDENCE_SOURCES,
)
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import BudgetAction, BudgetActionKind
from core.capability.tokens import estimate_tokens
from core.llm.types import Message, ToolResult

#: Appended to a truncated body, and counted inside the floor rather than added
#: on top of it — a marker that pushed the entry back over the limit would make
#: the truncation pass increase the total it exists to reduce.
TRUNCATION_MARKER = "\n[truncated to fit the context budget]"

#: Replaces the body of an evicted entry in the transcript. Short by design: it
#: is what the budget spends to keep the pointer, and it carries the identifier
#: so the trace's eviction record and the prompt refer to the same thing.
EVICTION_NOTICE = "[evidence {id} dropped to fit the context budget: {summary}]"


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """The bounds one run's evidence is held to.

    ``total_tokens`` of zero means "no budget of our own": the caller is relying
    on the model's context window and the provider client's context guard, which
    is the right default for a small run. Reading zero as a literal ceiling would
    evict everything on every run that did not ask for a budget.
    """

    total_tokens: int = 0
    evidence_ratio: float = CONTEXT_EVIDENCE_BUDGET_RATIO
    truncation_floor_chars: int = EVIDENCE_TRUNCATION_FLOOR_CHARS

    def __post_init__(self) -> None:
        if self.total_tokens < 0:
            raise ValueError("total_tokens must not be negative")
        if not 0.0 < self.evidence_ratio <= 1.0:
            raise ValueError("evidence_ratio must be above 0.0 and at most 1.0")

    @property
    def evidence_tokens(self) -> int:
        """Return the share of the budget evidence may occupy."""
        return int(self.total_tokens * self.evidence_ratio)

    @property
    def enforced(self) -> bool:
        """Return whether this policy bounds anything."""
        return self.total_tokens > 0


def evidence_value(entry: EvidenceEntry, *, current_iteration: int, largest_tokens: int) -> float:
    """Return how much this entry is worth keeping, higher meaning keep.

    Deterministic and total-ordered on the four terms the module docstring
    names. The golden test pins the ordering it produces over a fixed set, so a
    retune is a diff in the constants and a diff in that test rather than a
    scenario score that moved for reasons nobody can reconstruct.
    """
    age = max(current_iteration - entry.iteration, 0)
    value = EVIDENCE_VALUE_RECENCY_WEIGHT / (1.0 + age)

    if entry.cited:
        value += EVIDENCE_VALUE_CITED_BONUS

    if largest_tokens > 0:
        value -= EVIDENCE_VALUE_SIZE_PENALTY * (entry.tokens / largest_tokens)

    if entry.source in UNRELIABLE_EVIDENCE_SOURCES:
        value -= EVIDENCE_VALUE_UNRELIABLE_PENALTY

    return value


def _prompt_text(entry: EvidenceEntry) -> str:
    """Return what the transcript carries for ``entry``.

    The budget is accounted against this rather than against the raw content,
    so the notice an evicted entry leaves behind is itself inside the budget.
    """
    if entry.content:
        return entry.content
    return EVICTION_NOTICE.format(id=entry.id, summary=entry.summary)


def _cost(entry: EvidenceEntry) -> int:
    """Return what ``entry`` costs in the prompt right now."""
    return estimate_tokens(_prompt_text(entry))


def _ranked(entries: Sequence[EvidenceEntry], *, current_iteration: int) -> list[int]:
    """Return entry indices ordered least valuable first."""
    largest = max((entry.tokens for entry in entries), default=0)
    return sorted(
        range(len(entries)),
        key=lambda index: evidence_value(
            entries[index], current_iteration=current_iteration, largest_tokens=largest
        ),
    )


def _rewrite_transcript(session: Session, replacements: dict[str, str]) -> None:
    """Rewrite the tool results whose evidence the budget just changed.

    A message is rebuilt only when one of its results is affected; ``Message``
    is frozen, so leaving the rest alone keeps the identity of everything the
    budget did not touch.
    """
    if not replacements:
        return

    for index, message in enumerate(session.transcript):
        if not message.tool_results:
            continue
        if not any(result.call_id in replacements for result in message.tool_results):
            continue
        session.transcript[index] = Message(
            role=message.role,
            text=message.text,
            tool_calls=message.tool_calls,
            tool_results=tuple(
                (
                    ToolResult(
                        call_id=result.call_id,
                        name=result.name,
                        content=replacements[result.call_id],
                        is_error=result.is_error,
                    )
                    if result.call_id in replacements
                    else result
                )
                for result in message.tool_results
            ),
        )


def apply_budget(session: Session, policy: BudgetPolicy) -> tuple[BudgetAction, ...]:
    """Bring ``session``'s evidence inside ``policy``, recording every change.

    Returns the actions taken, in the order they were taken. The session is
    mutated in place: both the evidence entries and the transcript results that
    quote them, because those two disagreeing is the failure mode this whole
    module exists to prevent.
    """
    if not policy.enforced or not session.evidence:
        return ()

    entries = list(session.evidence)
    budget = policy.evidence_tokens
    total = sum(_cost(entry) for entry in entries)
    if total <= budget:
        return ()

    order = _ranked(entries, current_iteration=session.iteration)
    actions: list[BudgetAction] = []
    replacements: dict[str, str] = {}
    floor = max(policy.truncation_floor_chars - len(TRUNCATION_MARKER), 0)

    for index in order:
        if total <= budget:
            break
        entry = entries[index]
        if len(entry.content) <= policy.truncation_floor_chars:
            continue
        before = _cost(entry)
        trimmed = entry.content[:floor] + TRUNCATION_MARKER
        entries[index] = replace(entry, content=trimmed, truncated=True)
        after = _cost(entries[index])
        total += after - before
        replacements[entry.call_id] = trimmed
        actions.append(
            BudgetAction(
                kind=BudgetActionKind.TRUNCATED,
                evidence_id=entry.id,
                tokens_before=before,
                tokens_after=after,
                reason=(
                    f"lowest-value entry still held: recorded at iteration {entry.iteration}, "
                    f"{'cited' if entry.cited else 'never cited'}, source {entry.source!r}"
                ),
            )
        )

    for index in order:
        if total <= budget:
            break
        entry = entries[index]
        if not entry.content:
            continue
        before = _cost(entry)
        entries[index] = replace(entry, content="", truncated=True)
        after = _cost(entries[index])
        total += after - before
        replacements[entry.call_id] = _prompt_text(entries[index])
        actions.append(
            BudgetAction(
                kind=BudgetActionKind.EVICTED,
                evidence_id=entry.id,
                tokens_before=before,
                tokens_after=after,
                reason=(
                    f"truncation left the run over budget; body dropped, summary and "
                    f"reference kept (iteration {entry.iteration}, "
                    f"{'cited' if entry.cited else 'never cited'})"
                ),
            )
        )

    session.replace_evidence(entries)
    replacements.pop("", None)
    _rewrite_transcript(session, replacements)
    return tuple(actions)


__all__ = [
    "EVICTION_NOTICE",
    "TRUNCATION_MARKER",
    "BudgetPolicy",
    "apply_budget",
    "evidence_value",
]
