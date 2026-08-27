"""The run's memory: transcript, evidence, accounting, and where it got to.

Two requirements pull on this type from opposite directions and meet in the
same place.

**Resumption.** A run cancelled mid-sub-agent has to come back coherent, which
means everything the loop consults has to be here rather than in a local
variable — the iteration count, the stagnation counter, whether tool access has
already been stripped.

**Offline replay.** A trace that cannot be reconstructed from the store is a
summary of an investigation rather than evidence of one. So every field
round-trips through JSON, and the test that proves it does so through
``json.dumps`` rather than through a dictionary comparison.

Evidence is held apart from the transcript on purpose. The transcript is what
the model said; evidence is what the system observed, and only the second is
citable in a conclusion. Compaction summarises the first and never touches the
second.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from config.constants.investigation import MAX_INVESTIGATION_LOOPS, RUN_WALL_CLOCK_SECONDS
from config.prompts import SUBJECT_BRIEF_HEADING
from core.agent.turn import Turn
from core.capability.metadata import EvidenceType
from core.capability.result import Evidence
from core.capability.tokens import estimate_tokens
from core.llm.routing import ModelAttribution, TaskClass
from core.llm.types import Message, Role, ToolCall, ToolResult
from core.llm.usage import UsageLedger, UsageRecord


class SessionStatus(StrEnum):
    """Where a run got to.

    ``SUSPENDED`` is not a failure. It is the state a run sits in while a human
    decides on an approval or answers a handoff question, and it is resumable
    in a way ``CANCELLED`` deliberately is not.
    """

    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Return whether no further iteration will happen under this status."""
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES: frozenset[SessionStatus] = frozenset(
    {SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.FAILED}
)


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """One observation the session holds, with everything eviction needs.

    ``origin`` is empty for the loop's own calls and carries the sub-agent's
    name for a finding that came back from one. The parent has to be able to
    say where a claim came from, and "a specialist told me" is a materially
    different provenance from "I read it".

    ``cited`` is the single most important input to the value function. An
    entry a prior turn reasoned from is one the model is likely to reach for
    again, and evicting it is how a run forgets its own argument.
    """

    id: str
    capability: str
    summary: str
    evidence_type: EvidenceType
    source: str
    content: str = ""
    reference: str = ""
    call_id: str = ""
    iteration: int = 0
    origin: str = ""
    cited: bool = False
    truncated: bool = False

    @property
    def tokens(self) -> int:
        """Return what this entry costs in the prompt, summary and body together."""
        return estimate_tokens(f"{self.summary}\n{self.content}")

    def as_evidence(self) -> Evidence:
        """Return the capability-layer shape, for a conclusion that cites this."""
        return Evidence(
            source=self.source,
            evidence_type=self.evidence_type,
            summary=self.summary,
            reference=self.reference,
        )

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this entry."""
        return {
            "id": self.id,
            "capability": self.capability,
            "summary": self.summary,
            "evidence_type": self.evidence_type.value,
            "source": self.source,
            "content": self.content,
            "reference": self.reference,
            "call_id": self.call_id,
            "iteration": self.iteration,
            "origin": self.origin,
            "cited": self.cited,
            "truncated": self.truncated,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EvidenceEntry:
        """Return the entry a stored record describes."""
        return cls(
            id=str(record["id"]),
            capability=str(record["capability"]),
            summary=str(record.get("summary", "")),
            evidence_type=EvidenceType(record["evidence_type"]),
            source=str(record.get("source", "")),
            content=str(record.get("content", "")),
            reference=str(record.get("reference", "")),
            call_id=str(record.get("call_id", "")),
            iteration=int(record.get("iteration", 0)),
            origin=str(record.get("origin", "")),
            cited=bool(record.get("cited", False)),
            truncated=bool(record.get("truncated", False)),
        )


def message_to_record(message: Message) -> dict[str, Any]:
    """Return one transcript message as JSON."""
    return {
        "role": message.role.value,
        "text": message.text,
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}
            for call in message.tool_calls
        ],
        "tool_results": [
            {
                "call_id": result.call_id,
                "name": result.name,
                "content": result.content,
                "is_error": result.is_error,
            }
            for result in message.tool_results
        ],
    }


def message_from_record(record: Mapping[str, Any]) -> Message:
    """Return the message a stored record describes."""
    return Message(
        role=Role(record["role"]),
        text=str(record.get("text", "")),
        tool_calls=tuple(
            ToolCall(
                id=str(call["id"]),
                name=str(call["name"]),
                arguments=dict(call.get("arguments") or {}),
            )
            for call in record.get("tool_calls") or ()
        ),
        tool_results=tuple(
            ToolResult(
                call_id=str(result["call_id"]),
                name=str(result["name"]),
                content=str(result.get("content", "")),
                is_error=bool(result.get("is_error", False)),
            )
            for result in record.get("tool_results") or ()
        ),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def context_brief(context: Mapping[str, str]) -> str:
    """Return what a run already knows about its subject, as one stated turn.

    Empty for a run that knows nothing, so a caller appends nothing rather than
    a heading over an empty list — a brief that says only "here is what we
    know" and then nothing is worse than silence, because it reads as "we
    checked and there is nothing".

    Keys are printed as written. They are the deployment's own vocabulary and
    the agent is about to pass some of them straight to a vendor's tool; a
    prettified rendering here would be a second spelling of a name that has to
    match.
    """
    stated = [(key, value) for key, value in sorted(context.items()) if str(value).strip()]
    if not stated:
        return ""
    lines = "\n".join(f"- {key}: {value}" for key, value in stated)
    return f"{SUBJECT_BRIEF_HEADING}\n\n{lines}"


@dataclass(slots=True)
class Session:
    """One investigation's state, persistable and resumable.

    Mutable and deliberately not thread-safe. A session belongs to one loop;
    a sub-agent gets its own, which is what makes context isolation a property
    of the type rather than a rule the dispatcher has to remember.
    """

    id: str
    objective: str = ""
    system_prompt: str = ""
    alert_source: str = ""
    depth: int = 0
    parent_id: str = ""
    subagent: str = ""
    status: SessionStatus = SessionStatus.RUNNING
    iteration: int = 0
    stagnant_iterations: int = 0
    tools_stripped: bool = False
    # The bounds this run is held to, carried on the session rather than in the
    # runtime's memory: a session resumed in another process has to be held to
    # the same ceiling as the one that started it.
    max_iterations: int = MAX_INVESTIGATION_LOOPS
    wall_clock_seconds: float = RUN_WALL_CLOCK_SECONDS
    context_budget_tokens: int = 0
    transcript: list[Message] = field(default_factory=list)
    evidence: list[EvidenceEntry] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    # Which model produced which part of the answer. Held on the session rather
    # than derived from the turns because not every model call is a turn — a
    # summary, an embedding and a classification each produce an output the run
    # is accountable for and none of them appears in the transcript.
    attributions: list[ModelAttribution] = field(default_factory=list)
    usage: UsageLedger = field(default_factory=lambda: UsageLedger(scope="run"))
    context: dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    # -- mutation -------------------------------------------------------------

    def touch(self) -> None:
        """Mark the session as changed now."""
        self.updated_at = _now()

    def append(self, message: Message) -> None:
        """Add one message to the transcript."""
        self.transcript.append(message)
        self.touch()

    def extend(self, messages: Sequence[Message]) -> None:
        """Add several messages to the transcript."""
        for message in messages:
            self.transcript.append(message)
        self.touch()

    def record_evidence(self, entry: EvidenceEntry) -> EvidenceEntry:
        """Store ``entry``, assigning an identifier when it carries none.

        A supplied identifier is kept. A sub-agent's finding arrives already
        identified, and renumbering it would break the provenance the parent
        recorded the claim against.
        """
        stored = entry if entry.id else replace(entry, id=f"e{len(self.evidence) + 1}")
        self.evidence.append(stored)
        self.touch()
        return stored

    def record_turn(self, turn: Turn) -> None:
        """Store one completed turn and its usage."""
        self.turns.append(turn)
        self.usage.add(turn.usage)
        self.touch()

    def record_usage(self, usage: UsageRecord | None) -> None:
        """Store usage for a call that produced no turn of its own."""
        self.usage.add(usage)
        self.touch()

    def attribute(
        self,
        task: TaskClass | str,
        *,
        provider_id: str,
        model_id: str,
        output: str = "",
    ) -> ModelAttribution:
        """Note that ``model_id`` produced ``output`` for ``task``."""
        entry = ModelAttribution(
            task=task.value if isinstance(task, TaskClass) else str(task),
            provider_id=provider_id,
            model_id=model_id,
            output=output,
        )
        self.attributions.append(entry)
        self.touch()
        return entry

    @property
    def model_set(self) -> tuple[str, ...]:
        """Return the distinct models this run used, sorted.

        What a published number records beside it: a score whose model set is
        unknown is a score nobody can reproduce or compare.
        """
        return tuple(sorted({entry.label for entry in self.attributions}))

    def cite(self, evidence_id: str) -> None:
        """Mark one entry as reasoned from, raising if it is not held.

        Raising rather than ignoring is deliberate. A citation of something the
        session does not hold means the model invented a reference, and that is
        precisely the thing Article I exists to make impossible to miss.
        """
        for index, entry in enumerate(self.evidence):
            if entry.id == evidence_id:
                self.evidence[index] = replace(entry, cited=True)
                self.touch()
                return
        raise KeyError(f"{self.id}: no evidence entry {evidence_id!r} to cite")

    def replace_evidence(self, entries: Sequence[EvidenceEntry]) -> None:
        """Replace the held evidence, as the context budget does after eviction."""
        self.evidence = list(entries)
        self.touch()

    # -- reading --------------------------------------------------------------

    def find_evidence(self, evidence_id: str) -> EvidenceEntry | None:
        """Return the entry with ``evidence_id``, or ``None``."""
        return next((entry for entry in self.evidence if entry.id == evidence_id), None)

    @property
    def evidence_tokens(self) -> int:
        """Return what the held evidence costs in the prompt."""
        return sum(entry.tokens for entry in self.evidence)

    # -- persistence ----------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of the whole session."""
        return {
            "id": self.id,
            "objective": self.objective,
            "system_prompt": self.system_prompt,
            "alert_source": self.alert_source,
            "depth": self.depth,
            "parent_id": self.parent_id,
            "subagent": self.subagent,
            "status": self.status.value,
            "iteration": self.iteration,
            "stagnant_iterations": self.stagnant_iterations,
            "tools_stripped": self.tools_stripped,
            "max_iterations": self.max_iterations,
            "wall_clock_seconds": self.wall_clock_seconds,
            "context_budget_tokens": self.context_budget_tokens,
            "transcript": [message_to_record(message) for message in self.transcript],
            "evidence": [entry.to_record() for entry in self.evidence],
            "turns": [turn.to_record() for turn in self.turns],
            "attributions": [entry.to_record() for entry in self.attributions],
            "context": dict(self.context),
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Session:
        """Return the session a stored record describes.

        Usage is rebuilt from the stored turns rather than serialised
        separately: two copies of the same total are two chances for a resumed
        run to report a cost that does not match its own trace.
        """
        turns = [Turn.from_record(item) for item in record.get("turns") or ()]
        ledger = UsageLedger(scope="run")
        for turn in turns:
            ledger.add(turn.usage)

        return cls(
            id=str(record["id"]),
            objective=str(record.get("objective", "")),
            system_prompt=str(record.get("system_prompt", "")),
            alert_source=str(record.get("alert_source", "")),
            depth=int(record.get("depth", 0)),
            parent_id=str(record.get("parent_id", "")),
            subagent=str(record.get("subagent", "")),
            status=SessionStatus(record.get("status", SessionStatus.RUNNING.value)),
            iteration=int(record.get("iteration", 0)),
            stagnant_iterations=int(record.get("stagnant_iterations", 0)),
            tools_stripped=bool(record.get("tools_stripped", False)),
            max_iterations=int(record.get("max_iterations", MAX_INVESTIGATION_LOOPS)),
            wall_clock_seconds=float(record.get("wall_clock_seconds", RUN_WALL_CLOCK_SECONDS)),
            context_budget_tokens=int(record.get("context_budget_tokens", 0)),
            transcript=[message_from_record(item) for item in record.get("transcript") or ()],
            evidence=[EvidenceEntry.from_record(item) for item in record.get("evidence") or ()],
            turns=turns,
            attributions=[
                ModelAttribution.from_record(item) for item in record.get("attributions") or ()
            ],
            usage=ledger,
            context=dict(record.get("context") or {}),
            started_at=datetime.fromisoformat(str(record["started_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
        )


__all__ = [
    "EvidenceEntry",
    "Session",
    "SessionStatus",
    "context_brief",
    "message_from_record",
    "message_to_record",
]
