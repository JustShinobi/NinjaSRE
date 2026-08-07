"""Running the suite with no model at all, by replaying what one said before.

FR-017's reason is economic and it is the reason regression gating is
affordable: a suite that spent tokens on every pull request is a suite somebody
eventually turns off, and a gate nobody runs gates nothing. So a scenario can
carry a recorded transcript, and the whole investigation — pipeline, loop,
capabilities, clients, proxy, vendors — runs against it with the provider
removed.

Recording and replay are one wrapper and one client, both satisfying
``LLMClient``. That is what keeps the two paths honest: the recorder is the live
path with a tap on it rather than a second implementation, and the player is
substituted where the provider goes rather than short-circuiting a stage.

**A replay that runs past its transcript raises.** It is tempting to invent a
closing turn instead, and it would be wrong: the run has diverged from the one
that was recorded, and reporting a diverged run as a scenario failure would blame
the agent for a stale fixture. A raised ``TranscriptExhausted`` says which of the
two happened.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    StructuredMechanism,
    TokenEstimate,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord

#: The two kinds of call an investigation makes: the loop's turns, and the
#: pipeline's structured stages. Recorded in one stream because they happen in
#: one order, and a replay has to give them back in that order.
INVOKE = "invoke"
STRUCTURED = "structured"


class TranscriptExhausted(Exception):
    """A replay asked for a turn the transcript does not have.

    Distinct from every scenario failure, because it is not one: it means the
    run diverged from the one that was recorded, and the fix is to re-record
    rather than to look at the agent.
    """


@dataclass(frozen=True, slots=True)
class TranscriptEntry:
    """One recorded provider answer."""

    kind: str
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    structured: Mapping[str, Any] | None = None
    finish_reason: str = FinishReason.STOP.value

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this entry."""
        return {
            "kind": self.kind,
            "text": self.text,
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}
                for call in self.tool_calls
            ],
            "structured": dict(self.structured) if self.structured is not None else None,
            "finish_reason": self.finish_reason,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> TranscriptEntry:
        """Return the entry a stored record describes."""
        return cls(
            kind=str(record.get("kind", INVOKE)),
            text=str(record.get("text", "")),
            tool_calls=tuple(
                ToolCall(
                    id=str(call.get("id", "")),
                    name=str(call.get("name", "")),
                    arguments=dict(call.get("arguments") or {}),
                )
                for call in record.get("tool_calls") or ()
            ),
            structured=record.get("structured"),
            finish_reason=str(record.get("finish_reason", FinishReason.STOP.value)),
        )


@dataclass(frozen=True, slots=True)
class Transcript:
    """Everything one provider said during one recorded run."""

    entries: tuple[TranscriptEntry, ...] = ()
    provider_id: str = ""
    model_id: str = ""
    scenario: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this transcript."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "scenario": self.scenario,
            "entries": [entry.to_record() for entry in self.entries],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Transcript:
        """Return the transcript a stored record describes."""
        return cls(
            entries=tuple(
                TranscriptEntry.from_record(entry) for entry in record.get("entries") or ()
            ),
            provider_id=str(record.get("provider_id", "")),
            model_id=str(record.get("model_id", "")),
            scenario=str(record.get("scenario", "")),
        )


def write_transcript(transcript: Transcript, path: Path) -> Path:
    """Write ``transcript`` to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(transcript.to_record(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_transcript(path: Path) -> Transcript:
    """Return the transcript stored at ``path``.

    Raises:
        TranscriptExhausted: the file holds no entries, so replaying it could
            never produce a run.
    """
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    transcript = Transcript.from_record(document)
    if not transcript.entries:
        raise TranscriptExhausted(f"{path}: holds no recorded turns, so nothing can be replayed")
    return transcript


@dataclass(slots=True)
class TranscriptRecorder:
    """The live provider, with a tap on it (T030).

    Wrapping rather than reimplementing is what makes a recording session prove
    something about the live path: whatever the provider actually returned is
    what lands in the file, including the shapes nobody predicted.
    """

    inner: Any
    scenario: str = ""
    entries: list[TranscriptEntry] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""
        return str(self.inner.provider_id)

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""
        return str(self.inner.model_id)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return one live turn, and keep it."""
        result: InvokeResult = await self.inner.invoke(request)
        self.entries.append(
            TranscriptEntry(
                kind=INVOKE,
                text=result.text,
                tool_calls=result.tool_calls,
                finish_reason=result.finish_reason.value,
            )
        )
        return result

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Return the events of one live turn, keeping the turn it amounts to."""
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return one live structured answer, and keep it."""
        result: InvokeResult = await self.inner.invoke_structured(request, schema)
        self.entries.append(TranscriptEntry(kind=STRUCTURED, structured=result.structured))
        return result

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the token cost of ``request``."""
        estimate: TokenEstimate = self.inner.count_tokens(request)
        return estimate

    def transcript(self) -> Transcript:
        """Return everything recorded so far."""
        return Transcript(
            entries=tuple(self.entries),
            provider_id=self.provider_id,
            model_id=self.model_id,
            scenario=self.scenario,
        )


#: What a replayed call costs. Zero, and stated as a value rather than left
#: absent: a run whose usage was ``None`` would be indistinguishable from one
#: whose provider forgot to report it, and SC-006 is a claim about the number.
NO_TOKENS = TokenCounts(input_tokens=0, output_tokens=0)


@dataclass(slots=True)
class TranscriptPlayer:
    """A provider that answers from a recording and spends nothing (FR-017)."""

    transcript: Transcript
    position: int = 0

    @property
    def provider_id(self) -> str:
        """Return the provider the recording came from."""
        return self.transcript.provider_id or "offline"

    @property
    def model_id(self) -> str:
        """Return the model the recording came from."""
        return self.transcript.model_id or "transcript"

    @property
    def deterministic(self) -> bool:
        """Return that a replay cannot vary. There is nothing left to sample."""
        return True

    @property
    def tokens_spent(self) -> int:
        """Return what this run cost. Always zero."""
        return 0

    def next_entry(self, kind: str) -> TranscriptEntry:
        """Return the next recorded answer of ``kind``.

        Raises:
            TranscriptExhausted: the recording has no further turn, or its next
                turn is of the other kind — either way the run has diverged
                from the one that was recorded.
        """
        if self.position >= len(self.transcript.entries):
            raise TranscriptExhausted(
                f"the replay asked for a {kind!r} turn after {self.position} recorded turns; "
                f"the run has diverged from the one this transcript was recorded from, so "
                f"re-record it rather than reading this as a scenario failure"
            )
        entry = self.transcript.entries[self.position]
        if entry.kind != kind:
            raise TranscriptExhausted(
                f"the replay asked for a {kind!r} turn at position {self.position} and the "
                f"transcript records a {entry.kind!r} one; the run has diverged"
            )
        self.position += 1
        return entry

    def _usage(self) -> UsageRecord:
        return UsageRecord(provider_id=self.provider_id, model_id=self.model_id, tokens=NO_TOKENS)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the next recorded turn."""
        entry = self.next_entry(INVOKE)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=entry.text,
            tool_calls=entry.tool_calls,
            finish_reason=FinishReason(entry.finish_reason),
            usage=self._usage(),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Return the next recorded turn as a stream of events."""
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the next recorded structured answer."""
        entry = self.next_entry(STRUCTURED)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=entry.structured,
            structured_mechanism=(
                StructuredMechanism.NATIVE if entry.structured is not None else None
            ),
            usage=self._usage(),
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return zero. A replayed request is never sent anywhere."""
        return TokenEstimate(tokens=0, estimated=False)


def player_for(path: Path, scenarios: Sequence[str] = ()) -> TranscriptPlayer:
    """Return a player over the transcript at ``path``."""
    return TranscriptPlayer(load_transcript(path))


__all__ = [
    "INVOKE",
    "NO_TOKENS",
    "STRUCTURED",
    "Transcript",
    "TranscriptEntry",
    "TranscriptExhausted",
    "TranscriptPlayer",
    "TranscriptRecorder",
    "load_transcript",
    "player_for",
    "write_transcript",
]
