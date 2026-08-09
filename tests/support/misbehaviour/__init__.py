"""Recorded misbehaving-model transcripts, and the harness that replays them.

Every behaviour this feature adds has to be provable against a recording, with
no live model anywhere in the gate. That is not a convenience: the misbehaviours
are intermittent by nature — a quantised build produces valid JSON nine times in
ten — so a test that asked a real model to misbehave would be a test that passed
most of the time for the wrong reason.

So each misbehaviour is a data file under ``transcripts/``, written in
provider-neutral terms because that is the level the resilience layer works at.
A transcript carries the tools that were on the turn, the sequence of outputs the
model produced, and what the layer is expected to make of them. Replaying one is
a scripted client and nothing else.

Nothing here was recorded from a live call, so there is no secret to scrub —
which is a stronger guarantee than scrubbing. Each file's ``description`` says
which observed failure it stands for.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.llm import PROVIDER_OLLAMA
from core.llm.resilience import ResilientClient
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    Message,
    Role,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
    ToolSchema,
)

TRANSCRIPTS = Path(__file__).parent / "transcripts"

#: The model every transcript is attributed to. A plausible local build rather
#: than a made-up name, because the failure messages quote it and an operator
#: reading one should recognise the shape of what they are running.
MODEL_ID = "qwen2.5:7b-instruct-q4_K_M"


@dataclass(frozen=True, slots=True)
class Transcript:
    """One recorded misbehaviour, as it came off the wire."""

    id: str
    description: str
    tools: tuple[ToolSchema, ...]
    outputs: tuple[InvokeResult, ...] = ()
    stream: tuple[StreamEvent, ...] = ()
    capability_result: str = ""
    error_body: Mapping[str, Any] = field(default_factory=dict)
    expected: Mapping[str, Any] = field(default_factory=dict)

    @property
    def expected_repairs(self) -> tuple[str, ...]:
        """Return the repair kinds this transcript is recorded to produce."""
        return tuple(str(kind) for kind in self.expected.get("repairs", ()))


def _tool(document: Mapping[str, Any]) -> ToolSchema:
    return ToolSchema(
        name=str(document["name"]),
        description=str(document.get("description", "")),
        parameters=dict(document.get("parameters") or {}),
    )


def _call(document: Mapping[str, Any]) -> ToolCall:
    return ToolCall(
        id=str(document.get("id", "")),
        name=str(document["name"]),
        arguments=dict(document.get("arguments") or {}),
    )


def _output(document: Mapping[str, Any]) -> InvokeResult:
    return InvokeResult(
        provider_id=PROVIDER_OLLAMA,
        model_id=MODEL_ID,
        text=str(document.get("text", "")),
        tool_calls=tuple(_call(item) for item in document.get("tool_calls") or ()),
        finish_reason=FinishReason(document.get("finish_reason", FinishReason.STOP.value)),
    )


def _event(document: Mapping[str, Any]) -> StreamEvent:
    call = document.get("tool_call")
    finish = document.get("finish_reason")
    return StreamEvent(
        kind=StreamEventKind(document["kind"]),
        text=str(document.get("text", "")),
        tool_call=_call(call) if isinstance(call, Mapping) else None,
        tool_call_fragment=str(document.get("fragment", "")),
        finish_reason=FinishReason(finish) if finish else None,
    )


def _capability_result(document: Mapping[str, Any]) -> str:
    """Return the oversized result a transcript describes, expanded.

    Stored as a line and a count rather than as nine hundred copies of the line:
    a fixture nobody can read in a diff is a fixture nobody reviews.
    """
    line = str(document["line"])
    return "".join(
        line.format(second=index % 60) for index in range(int(document.get("repeat", 1)))
    )


def load(transcript_id: str) -> Transcript:
    """Return the recorded transcript called ``transcript_id``."""
    path = TRANSCRIPTS / f"{transcript_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no recorded transcript {transcript_id!r} in {TRANSCRIPTS}")
    return _from_document(json.loads(path.read_text(encoding="utf-8")))


def load_all() -> tuple[Transcript, ...]:
    """Return every recorded transcript, in identifier order."""
    return tuple(
        _from_document(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(TRANSCRIPTS.glob("*.json"))
    )


def transcript_ids() -> tuple[str, ...]:
    """Return every recorded transcript's identifier, for parameterisation."""
    return tuple(path.stem for path in sorted(TRANSCRIPTS.glob("*.json")))


def _from_document(document: Mapping[str, Any]) -> Transcript:
    capability = document.get("capability_result")
    return Transcript(
        id=str(document["id"]),
        description=str(document["description"]),
        tools=tuple(_tool(item) for item in document.get("tools") or ()),
        outputs=tuple(_output(item) for item in document.get("outputs") or ()),
        stream=tuple(_event(item) for item in document.get("stream") or ()),
        capability_result=(
            _capability_result(capability) if isinstance(capability, Mapping) else ""
        ),
        error_body=dict(document.get("error_body") or {}),
        expected=dict(document.get("expected") or {}),
    )


@dataclass
class RecordedModel:
    """Replays a transcript's outputs, and records what it was sent.

    Recording the requests is half the point: most of what these fixtures prove
    is about the *correction* the layer sent back, and that is only visible from
    in here.
    """

    outputs: list[InvokeResult]
    events: tuple[StreamEvent, ...] = ()
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return PROVIDER_OLLAMA

    @property
    def model_id(self) -> str:
        return MODEL_ID

    @property
    def corrections(self) -> tuple[str, ...]:
        """Return the text of the last message on every request after the first."""
        return tuple(request.messages[-1].text for request in self.requests[1:])

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=0, estimated=True)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        if not self.outputs:
            # The last recorded output stands for "and it kept doing that",
            # which is what a bounded repair loop has to be driven past.
            return InvokeResult(provider_id=self.provider_id, model_id=self.model_id, text="")
        return self.outputs.pop(0)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        return await self.invoke(request)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event


@dataclass(frozen=True, slots=True)
class Replay:
    """What replaying one transcript through the layer produced."""

    results: tuple[InvokeResult, ...]
    model: RecordedModel

    @property
    def repairs(self) -> tuple[str, ...]:
        """Return every repair kind recorded across the replay, in order."""
        return tuple(repair.kind.value for result in self.results for repair in result.repairs)

    @property
    def final(self) -> InvokeResult:
        """Return the last result the layer produced."""
        return self.results[-1]


def build(transcript: Transcript, **options: Any) -> tuple[ResilientClient, RecordedModel]:
    """Return the layer wrapped around ``transcript``'s recorded model."""
    model = RecordedModel(outputs=list(transcript.outputs), events=transcript.stream)
    return ResilientClient(model, **options), model


def request_for(transcript: Transcript, *, session_id: str = "replay") -> InvokeRequest:
    """Return the request a turn against ``transcript`` is made with."""
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="Why is checkout returning 503?"),),
        tools=transcript.tools,
        metadata={"session_id": session_id},
    )


async def replay(
    transcript: Transcript,
    *,
    turns: int = 1,
    session_id: str = "replay",
    **options: Any,
) -> Replay:
    """Drive ``turns`` turns of ``transcript`` through the layer and return what happened.

    No live model, no network, no credential. The layer's own code runs
    unchanged — a recorded output and a real one are the same value by the time
    it sees either, which is the property that makes this a test of the layer
    rather than of the harness.
    """
    layer, model = build(transcript, **options)
    results = [
        await layer.invoke(request_for(transcript, session_id=session_id)) for _ in range(turns)
    ]
    return Replay(results=tuple(results), model=model)


def streamed_events(transcript: Transcript, **options: Any) -> AsyncIterator[StreamEvent]:
    """Return the layer's view of ``transcript``'s recorded stream."""
    layer, _ = build(transcript, **options)
    return layer.stream(request_for(transcript))


def expected_sequence(transcript: Transcript) -> Sequence[Mapping[str, Any]]:
    """Return the calls ``transcript`` records the layer should end up with."""
    return list(transcript.expected.get("tool_calls", ()))


__all__ = [
    "MODEL_ID",
    "TRANSCRIPTS",
    "RecordedModel",
    "Replay",
    "Transcript",
    "build",
    "expected_sequence",
    "load",
    "load_all",
    "replay",
    "request_for",
    "streamed_events",
    "transcript_ids",
]
