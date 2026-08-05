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
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.investigation import (
    TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
)
from core.agent.session import Session
from core.llm.types import Message, Role

#: Opens the summary that replaces the compacted messages. Addressed to the
#: model: it has to read this as its own history rather than as new instruction.
COMPACTION_PREAMBLE = (
    "[Earlier turns in this investigation have been summarised to make room. "
    "Everything below happened; the evidence identifiers still resolve.]"
)


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """What one compaction pass changed."""

    messages: tuple[Message, ...]
    removed: int
    summary: str

    @property
    def compacted(self) -> bool:
        """Return whether anything was actually replaced."""
        return self.removed > 0


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


def compact(
    session: Session,
    *,
    keep_recent: int = TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    trigger_at: int = TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
) -> CompactionResult:
    """Return the compacted transcript for ``session``, without applying it.

    Returns the transcript unchanged when it is under ``trigger_at``: below that
    a conversation is cheaper to keep than to summarise, and a summary the model
    reads alongside the messages it summarises costs more than either.
    """
    transcript = tuple(session.transcript)
    if len(transcript) < trigger_at or keep_recent <= 0:
        return CompactionResult(messages=transcript, removed=0, summary="")

    opening = transcript[:1]
    recent = transcript[-keep_recent:] if keep_recent < len(transcript) - 1 else transcript[1:]
    middle = transcript[len(opening) : len(transcript) - len(recent)]
    if not middle:
        return CompactionResult(messages=transcript, removed=0, summary="")

    summary = _summarise(middle, session)
    return CompactionResult(
        messages=(*opening, Message(role=Role.USER, text=summary), *recent),
        removed=len(middle),
        summary=summary,
    )


def apply_compaction(
    session: Session,
    *,
    keep_recent: int = TRANSCRIPT_COMPACTION_KEEP_MESSAGES,
    trigger_at: int = TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES,
) -> CompactionResult:
    """Compact ``session``'s transcript in place and return what changed."""
    result = compact(session, keep_recent=keep_recent, trigger_at=trigger_at)
    if result.compacted:
        session.transcript = list(result.messages)
        session.touch()
    return result


__all__ = [
    "COMPACTION_PREAMBLE",
    "CompactionResult",
    "apply_compaction",
    "compact",
]
