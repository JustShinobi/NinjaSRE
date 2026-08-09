"""Shortening a long conversation without losing what it established.

A run that has spent fifteen iterations gathering evidence is carrying fifteen
iterations of conversation, and most of it is no longer load-bearing: the model
does not need to re-read its own narration of a call whose result it still
holds.

What it does need is the *references*. So compaction summarises the
conversational turns and keeps every evidence identifier in the summary, which
means a claim made ten turns ago can still be traced to the observation behind
it. The context budget already governs how much of an observation's body
survives; this governs how much of the talking around it does.

Two things are never compacted. The opening message, because it states the
objective and a run that forgets what it was asked is worse than a long one. And
the most recent turns, because that is where the model's current line of
reasoning lives.

**When it happens has two triggers, and the second is the one a small model
needs.** A message count is a proxy for a size, and it is a bad proxy on a model
whose usable context was measured at a fraction of what its card advertised: the
transcript would be refused at the provider long before it was forty messages
long. So where a deployment has a measured window, compaction runs at a declared
share of it — while there is still room for the turn it is making room for.

Every pass records the strategy it used and what it dropped, and the loop puts
both in the trace. A degraded answer that can be traced to the compaction that
caused it is a bug report; one that cannot is a mystery.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.investigation import (
    TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    TRANSCRIPT_COMPACTION_TIGHT_KEEP_MESSAGES,
    TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
    TRANSCRIPT_COMPACTION_TRIGGER_RATIO,
)
from core.agent.session import Session
from core.capability.tokens import estimate_tokens
from core.llm.types import Message, Role

#: Opens the summary that replaces the compacted messages. Addressed to the
#: model: it has to read this as its own history rather than as new instruction.
COMPACTION_PREAMBLE = (
    "[Earlier turns in this investigation have been summarised to make room. "
    "Everything below happened; the evidence identifiers still resolve.]"
)

#: The strategy's name, recorded on every pass. One name because there is one
#: strategy: a trace that said "compacted" without saying how would not let
#: anybody reason about what a compacted run lost.
COMPACTION_STRATEGY = "objective-and-evidence-preserving"


def transcript_tokens(session: Session) -> int:
    """Return what ``session``'s transcript costs, by the offline estimate.

    The same estimate the provider client's context guard uses, deliberately: a
    trigger measured one way and a refusal measured another would leave a band
    of transcript sizes that compaction thinks are fine and the provider rejects.
    """
    total = 0
    for message in session.transcript:
        total += estimate_tokens(message.text)
        for call in message.tool_calls:
            total += estimate_tokens(f"{call.name}{dict(call.arguments)}")
        for result in message.tool_results:
            total += estimate_tokens(result.content)
    return total


def _describe(message: Message) -> str:
    """Return a one-line description of a message compaction removed."""
    if message.tool_calls:
        return f"{message.role.value}: called {', '.join(call.name for call in message.tool_calls)}"
    if message.tool_results:
        names = ", ".join(result.name for result in message.tool_results)
        return f"{message.role.value}: results from {names}"
    return f"{message.role.value}: {estimate_tokens(message.text)} tokens of prose"


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """What one compaction pass changed."""

    messages: tuple[Message, ...]
    removed: int
    summary: str
    strategy: str = COMPACTION_STRATEGY
    #: One line per removed message. FR-013's "record what it dropped" in the
    #: form somebody reading a trace can act on: a count says a run lost
    #: something, this says which somethings.
    dropped: tuple[str, ...] = ()

    @property
    def compacted(self) -> bool:
        """Return whether anything was actually replaced."""
        return self.removed > 0

    @property
    def reason(self) -> str:
        """Return the sentence the trace carries for this pass."""
        return f"{self.strategy}: {self.removed} message(s) summarised — " + "; ".join(self.dropped)


def _summarise(messages: tuple[Message, ...], session: Session) -> str:
    """Return the deterministic summary of ``messages``.

    Deterministic rather than model-generated, and that is a deliberate trade.
    A model-written summary reads better and costs a call, a share of the
    budget, and — the part that matters — reproducibility: two runs of the same
    scenario would compact differently and the trajectory comparison would be
    measuring the summariser.
    """
    called: list[str] = []
    for message in messages:
        called.extend(call.name for call in message.tool_calls)

    lines = [COMPACTION_PREAMBLE, ""]
    if called:
        counted: dict[str, int] = {}
        for name in called:
            counted[name] = counted.get(name, 0) + 1
        lines.append(
            "Capabilities called in the summarised turns: "
            + ", ".join(f"{name} ×{count}" for name, count in sorted(counted.items()))
            + "."
        )

    kept = [entry for entry in session.evidence if entry.id]
    if kept:
        lines.append("")
        lines.append("Evidence gathered, still available to cite:")
        lines.extend(
            f"- {entry.id} ({entry.capability}"
            + (f", via {entry.origin}" if entry.origin else "")
            + f"): {entry.summary}"
            for entry in kept
        )
    else:
        lines.append("No evidence was gathered in the summarised turns.")

    return "\n".join(lines)


def _over_measured_window(
    session: Session, *, usable_context_tokens: int, trigger_ratio: float
) -> bool:
    """Return whether the transcript has reached its share of the measured window."""
    if usable_context_tokens <= 0:
        return False
    return transcript_tokens(session) >= usable_context_tokens * trigger_ratio


def compact(
    session: Session,
    *,
    keep_recent: int = TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    trigger_at: int = TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
    usable_context_tokens: int = 0,
    trigger_ratio: float = TRANSCRIPT_COMPACTION_TRIGGER_RATIO,
) -> CompactionResult:
    """Return the compacted transcript for ``session``, without applying it.

    Returns the transcript unchanged when neither trigger has been reached:
    below them a conversation is cheaper to keep than to summarise, and a summary
    the model reads alongside the messages it summarises costs more than either.

    ``usable_context_tokens`` of zero means nobody measured this model, and the
    message count is the only trigger — which is what this function did before
    any of it was measurable.
    """
    transcript = tuple(session.transcript)
    over_window = _over_measured_window(
        session, usable_context_tokens=usable_context_tokens, trigger_ratio=trigger_ratio
    )
    # Either trigger, not both. The message count catches a long conversation of
    # short turns; the measured window catches a short conversation carrying one
    # enormous log dump, and on a small model that second case arrives first.
    if keep_recent <= 0 or not (len(transcript) >= trigger_at or over_window):
        return CompactionResult(messages=transcript, removed=0, summary="")

    # A transcript over a small model's window has to actually get smaller, and
    # the ordinary tail is longer than such a conversation usually is — keeping
    # it would summarise one message a turn while the conversation grew by three.
    keep = (
        min(keep_recent, TRANSCRIPT_COMPACTION_TIGHT_KEEP_MESSAGES) if over_window else keep_recent
    )
    keep = min(keep, max(len(transcript) - 2, 0))
    if keep <= 0:
        return CompactionResult(messages=transcript, removed=0, summary="")

    opening = transcript[:1]
    recent = transcript[-keep:] if keep < len(transcript) - 1 else transcript[1:]
    middle = transcript[len(opening) : len(transcript) - len(recent)]
    if not middle:
        return CompactionResult(messages=transcript, removed=0, summary="")

    summary = _summarise(middle, session)
    return CompactionResult(
        messages=(*opening, Message(role=Role.USER, text=summary), *recent),
        removed=len(middle),
        summary=summary,
        dropped=tuple(_describe(message) for message in middle),
    )


def apply_compaction(
    session: Session,
    *,
    keep_recent: int = TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    trigger_at: int = TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
    usable_context_tokens: int = 0,
    trigger_ratio: float = TRANSCRIPT_COMPACTION_TRIGGER_RATIO,
) -> CompactionResult:
    """Compact ``session``'s transcript in place and return what changed."""
    result = compact(
        session,
        keep_recent=keep_recent,
        trigger_at=trigger_at,
        usable_context_tokens=usable_context_tokens,
        trigger_ratio=trigger_ratio,
    )
    if result.compacted:
        session.transcript = list(result.messages)
        session.touch()
    return result


__all__ = [
    "COMPACTION_PREAMBLE",
    "COMPACTION_STRATEGY",
    "CompactionResult",
    "apply_compaction",
    "compact",
    "transcript_tokens",
]
