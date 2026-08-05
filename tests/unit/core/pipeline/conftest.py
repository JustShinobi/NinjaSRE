"""Doubles the pipeline tests share.

The LLM double is scripted rather than clever: a test states what the provider
returns and asserts what the stage did with it. A double that tried to behave
like a model would make every stage test a test of the double.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.agent.runtime_port import RunRequest, RunResult, RunStatus
from core.agent.session import EvidenceEntry as RuntimeEvidenceEntry
from core.agent.session import Session
from core.agent.turn import ToolExecution, Turn
from core.capability.metadata import (
    AppliesWhen,
    EvidenceType,
    Requirements,
    SideEffectLevel,
    SkillMetadata,
    ToolMetadata,
)
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityResult, Evidence
from core.domain.alerts.normalisation import RawAlert
from core.llm.failures import FailureClass
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    StructuredMechanism,
    TokenEstimate,
)
from core.llm.usage import TokenCounts, UsageRecord
from core.pipeline.state_factory import initial_state
from core.state.agent_state import AgentState
from core.state.types import TeamContext

AT = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)


def fixed_clock(at: datetime = AT) -> Any:
    """Return a clock that always answers ``at``."""
    return lambda: at


@dataclass(slots=True)
class ScriptedLLM:
    """An ``LLMClient`` that returns what a test told it to.

    ``structured`` is a queue: the first call takes the first entry. A stage
    that made one call more than the test scripted gets the last entry again,
    which keeps a mis-scripted test failing on its assertion rather than on an
    ``IndexError`` three frames away.
    """

    structured: list[Mapping[str, Any] | None] = field(default_factory=list)
    text: str = ""
    failure: FailureClass | None = None
    failure_message: str = ""
    tokens: TokenCounts = field(
        default_factory=lambda: TokenCounts(input_tokens=120, output_tokens=40)
    )
    requests: list[InvokeRequest] = field(default_factory=list)
    schemas: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    def _usage(self) -> UsageRecord:
        return UsageRecord(provider_id=self.provider_id, model_id=self.model_id, tokens=self.tokens)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=self.text,
            usage=self._usage(),
            failure=self.failure,
            failure_message=self.failure_message,
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=self.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        self.requests.append(request)
        self.schemas.append(schema)
        structured = self.structured.pop(0) if len(self.structured) > 1 else _peek(self.structured)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=self.text,
            structured=structured,
            structured_mechanism=StructuredMechanism.NATIVE if structured else None,
            usage=self._usage(),
            failure=self.failure,
            failure_message=self.failure_message,
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)

    @property
    def calls(self) -> int:
        """Return how many requests this client was given."""
        return len(self.requests)


def _peek(queue: Sequence[Mapping[str, Any] | None]) -> Mapping[str, Any] | None:
    return queue[0] if queue else None


@dataclass(slots=True)
class ScriptedRuntime:
    """A ``Runtime`` that returns the session and answer a test built.

    Canonical by default, because that is what the pipeline is normally handed
    and because a test that needed the experimental answer should say so.
    """

    answer: str = "The checkout container exceeded its memory limit and was OOM-killed."
    evidence: tuple[RuntimeEvidenceEntry, ...] = ()
    turns: tuple[Turn, ...] = ()
    status: RunStatus = RunStatus.COMPLETED
    failure: str = ""
    is_canonical: bool = True
    requests: list[RunRequest] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "ninjasre.react"

    async def run(self, request: RunRequest) -> RunResult:
        self.requests.append(request)
        session = Session(id=request.session_id or "session-1", objective=request.objective)
        for entry in self.evidence:
            session.record_evidence(entry)
        for turn in self.turns:
            session.record_turn(turn)
        return RunResult(
            session=session, status=self.status, answer=self.answer, failure=self.failure
        )

    async def resume(self, session: Session) -> RunResult:
        return RunResult(session=session, status=self.status, answer=self.answer)

    async def cancel(self, session_id: str) -> None:
        return None


def runtime_evidence(identifier: str = "e1", **overrides: Any) -> RuntimeEvidenceEntry:
    """Return one observation as the runtime records it."""
    fields: dict[str, Any] = {
        "id": identifier,
        "capability": "datadog_log_statistics",
        "summary": "412 errors in checkout between 12:04 and 12:20",
        "evidence_type": EvidenceType.LOG,
        "source": "datadog",
        "content": "status=500 count=412",
        "reference": "query:abc123",
        "call_id": "c1",
        "iteration": 1,
    }
    fields.update(overrides)
    return RuntimeEvidenceEntry(**fields)


def turn(index: int = 1, **overrides: Any) -> Turn:
    """Return one completed turn with a successful call on it."""
    executions = overrides.pop(
        "executions",
        (
            ToolExecution(
                call_id="c1",
                capability="datadog_log_statistics",
                arguments={"query": "service:checkout status:error"},
                evidence_ids=("e1",),
            ),
        ),
    )
    return Turn(
        index=index,
        rationale=overrides.pop("rationale", "check the error volume first"),
        executions=executions,
        usage=overrides.pop(
            "usage",
            UsageRecord(
                provider_id="scripted",
                model_id="scripted-1",
                tokens=TokenCounts(input_tokens=300, output_tokens=90),
            ),
        ),
        **overrides,
    )


def incident_classification(**overrides: Any) -> dict[str, Any]:
    """Return a structured intake answer saying this is an incident."""
    answer: dict[str, Any] = {
        "is_incident": True,
        "confidence": 0.95,
        "reason": "an alert is firing on the checkout service",
        "alert_name": "HighErrorRate",
        "severity": "critical",
        "summary": "checkout error rate above 5%",
        "components": ["checkout"],
        "error_text": "5xx responses are 12% of traffic",
    }
    answer.update(overrides)
    return answer


def noise_classification(**overrides: Any) -> dict[str, Any]:
    """Return a structured intake answer saying this is not an incident."""
    answer: dict[str, Any] = {
        "is_incident": False,
        "confidence": 0.96,
        "reason": "a greeting, not a report of a production problem",
        "alert_name": "",
        "severity": "unknown",
        "summary": "",
        "components": [],
        "error_text": "",
    }
    answer.update(overrides)
    return answer


async def _log_statistics(**arguments: Any) -> CapabilityResult:
    """Stand in for a vendor log tool."""
    return CapabilityResult.ok(
        "datadog_log_statistics",
        value={"errors": 412},
        evidence=(
            Evidence(
                source="datadog",
                evidence_type=EvidenceType.LOG,
                summary="412 errors in checkout",
                reference="query:abc",
            ),
        ),
    )


def tool(name: str = "datadog_log_statistics", **overrides: Any) -> RegisteredTool:
    """Return a registered tool a catalogue can hold."""
    metadata = ToolMetadata(
        name=name,
        display_name=overrides.pop("display_name", name.replace("_", " ").title()),
        description=overrides.pop("description", "Aggregate log counts over a window."),
        domain=overrides.pop("domain", "observability"),
        tags=overrides.pop("tags", ("logs", "errors")),
        use_cases=overrides.pop("use_cases", ("investigate an elevated error rate",)),
        evidence_source=overrides.pop("evidence_source", "datadog"),
        evidence_type=overrides.pop("evidence_type", EvidenceType.LOG),
        side_effect_level=overrides.pop("side_effect_level", SideEffectLevel.READ),
        parallel_safe=overrides.pop("parallel_safe", True),
        requires=overrides.pop("requires", Requirements(integrations=("datadog",))),
    )
    return RegisteredTool(
        metadata=metadata,
        input_schema=overrides.pop(
            "input_schema",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        output_schema=overrides.pop("output_schema", {"type": "object"}),
        call=overrides.pop("call", _log_statistics),
        source_module="tests.unit.core.pipeline.conftest",
        source_qualname=f"tool.{name}",
    )


def skill(name: str = "error-rate-triage", **overrides: Any) -> SkillMetadata:
    """Return skill metadata a catalogue can hold."""
    return SkillMetadata(
        name=name,
        display_name=overrides.pop("display_name", "Error rate triage"),
        description=overrides.pop("description", "How to triage an elevated error rate."),
        domain=overrides.pop("domain", "observability"),
        applies_when=overrides.pop(
            "applies_when", AppliesWhen(alert_sources=("alertmanager",), tags=("errors",))
        ),
        directs_tools=overrides.pop("directs_tools", ("datadog_log_statistics",)),
    )


def team(**overrides: Any) -> TeamContext:
    """Return a team context with one integration configured."""
    fields: dict[str, Any] = {
        "team_id": "payments",
        "integrations": ("datadog",),
        "destinations": ("slack",),
    }
    fields.update(overrides)
    return TeamContext(**fields)


def alertmanager_state(*, run_id: str = "run-1", at: datetime = AT, **overrides: Any) -> AgentState:
    """Return the state one Alertmanager alert starts from."""
    payload: dict[str, Any] = {
        "receiver": "payments-team",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "service": "checkout",
                },
                "annotations": {"summary": "checkout error rate above 5%"},
                "startsAt": (at - timedelta(minutes=10)).isoformat(),
                "endsAt": "0001-01-01T00:00:00Z",
            }
        ],
    }
    payload.update(overrides.pop("payload", {}))
    return initial_state(
        RawAlert(payload=payload, received_at=at),
        overrides.pop("team", team()),
        run_id=run_id,
        started_at=at,
    )
