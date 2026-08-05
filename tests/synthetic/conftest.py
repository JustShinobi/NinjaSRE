"""A small corpus of scenarios, each with the answer its investigation should reach.

These drive the whole pipeline over the *real* canonical runtime — the loop,
its execution path, its evidence recording — with only the provider and the
vendor backends replaced. A harness that stubbed the runtime as well would
prove the stages call each other and nothing about whether an investigation
works.

Every scenario carries an answer key. That is what makes the suite a
measurement rather than a smoke test: a run that produces a diagnosis is not
the same as a run that produces the right one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel, ToolMetadata
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityResult, Evidence
from core.domain.alerts.normalisation import RawAlert
from core.domain.diagnosis.taxonomy import RootCauseCategory
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
from core.pipeline.ports import DeliveryPayload, StaticCatalogue
from core.state.types import TeamContext

AT = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class LoopTurn:
    """What the provider returns on one turn of the loop."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    @property
    def finish_reason(self) -> FinishReason:
        """Return why generation stopped, derived from what it produced."""
        return FinishReason.TOOL_CALLS if self.tool_calls else FinishReason.STOP


@dataclass(slots=True)
class ScenarioLLM:
    """One provider double serving both the pipeline's calls and the loop's.

    The pipeline calls ``invoke_structured`` (intake, then diagnosis) and the
    loop calls ``invoke``. Two queues, one client, because that is the shape a
    real deployment has: one configured provider doing both jobs.
    """

    structured: list[Mapping[str, Any]] = field(default_factory=list)
    turns: list[LoopTurn] = field(default_factory=list)
    structured_calls: int = 0
    invocations: int = 0

    @property
    def provider_id(self) -> str:
        return "scenario"

    @property
    def model_id(self) -> str:
        return "scenario-1"

    def _usage(self) -> UsageRecord:
        return UsageRecord(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tokens=TokenCounts(input_tokens=400, output_tokens=120),
        )

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.invocations += 1
        turn = self.turns.pop(0) if self.turns else LoopTurn(text="No further evidence available.")
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=turn.text,
            tool_calls=turn.tool_calls,
            finish_reason=turn.finish_reason,
            usage=self._usage(),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        self.structured_calls += 1
        answer = self.structured.pop(0) if self.structured else None
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=answer,
            structured_mechanism=StructuredMechanism.NATIVE if answer else None,
            usage=self._usage(),
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


@dataclass(slots=True)
class RecordingDestination:
    """A destination that keeps what it was sent."""

    name: str = "slack"
    fails: bool = False
    received: list[DeliveryPayload] = field(default_factory=list)

    async def deliver(self, payload: DeliveryPayload) -> str:
        if self.fails:
            raise ConnectionError(f"{self.name} is unreachable")
        self.received.append(payload)
        return f"https://{self.name}.example/thread/1"


def backend_tool(
    name: str,
    *,
    evidence_source: str,
    summary: str,
    content: str,
    evidence_type: EvidenceType = EvidenceType.EVENT,
) -> RegisteredTool:
    """Return a capability standing in for one vendor call.

    The body is a constant because the scenario's answer key is about what the
    *investigation* concluded, not about what a vendor client would have done.
    """

    async def call(**arguments: Any) -> CapabilityResult:
        return CapabilityResult.ok(
            name,
            value={"arguments": arguments, "content": content},
            evidence=(
                Evidence(
                    source=evidence_source,
                    evidence_type=evidence_type,
                    summary=summary,
                    reference=f"{evidence_source}:{name}",
                ),
            ),
        )

    metadata = ToolMetadata(
        name=name,
        display_name=name.replace("_", " ").title(),
        description=f"Read {evidence_source} for the incident window.",
        domain="observability",
        tags=("errors", "logs", "events"),
        use_cases=("investigate an elevated error rate", "find why a pod restarted"),
        evidence_source=evidence_source,
        evidence_type=evidence_type,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
        requires=Requirements(integrations=(evidence_source,)),
    )
    return RegisteredTool(
        metadata=metadata,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["query"],
        },
        output_schema={"type": "object"},
        call=call,
        source_module="tests.synthetic.conftest",
        source_qualname=f"backend_tool.{name}",
    )


@dataclass(frozen=True, slots=True)
class Scenario:
    """One incident, the backends that can answer it, and the answer key."""

    key: str
    raw: RawAlert
    team: TeamContext
    tools: tuple[RegisteredTool, ...]
    turns: tuple[LoopTurn, ...]
    structured: tuple[Mapping[str, Any], ...]
    expected_category: RootCauseCategory
    expects_investigation: bool = True

    def llm(self) -> ScenarioLLM:
        """Return a provider double scripted for this scenario."""
        return ScenarioLLM(structured=list(self.structured), turns=list(self.turns))

    def catalogue(self) -> StaticCatalogue:
        """Return the catalogue this team resolves to."""
        return StaticCatalogue(
            tools=self.tools, declarations=tuple(found.metadata for found in self.tools)
        )


def _intake(**overrides: Any) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "is_incident": True,
        "confidence": 0.95,
        "reason": "an alert is firing on a production service",
        "alert_name": "",
        "severity": "critical",
        "summary": "",
        "components": [],
        "error_text": "",
    }
    answer.update(overrides)
    return answer


def _alertmanager(name: str, service: str, summary: str) -> RawAlert:
    return RawAlert(
        payload={
            "receiver": "payments-team",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": name, "severity": "critical", "service": service},
                    "annotations": {"summary": summary},
                    "startsAt": (AT - timedelta(minutes=12)).isoformat(),
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        },
        received_at=AT,
    )


OOM_KILL = Scenario(
    key="oom-kill",
    raw=_alertmanager("HighErrorRate", "checkout", "checkout error rate above 5%"),
    team=TeamContext(team_id="payments", integrations=("kubernetes",), destinations=("slack",)),
    tools=(
        backend_tool(
            "kubernetes_pod_events",
            evidence_source="kubernetes",
            summary="3 OOMKilled events on checkout-7f4c between 12:18 and 12:29",
            content="reason=OOMKilled count=3 container=checkout limit=512Mi",
        ),
    ),
    turns=(
        LoopTurn(
            tool_calls=(
                ToolCall(
                    id="c1",
                    name="kubernetes_pod_events",
                    arguments={
                        "query": "pod=checkout-7f4c",
                        "start_time": (AT - timedelta(days=1)).isoformat(),
                    },
                ),
            )
        ),
        LoopTurn(
            text=(
                "The checkout container was OOM-killed three times inside the incident "
                "window [e1]. Its memory limit is 512Mi and the process exceeded it."
            )
        ),
    ),
    structured=(
        _intake(),
        {
            "root_cause": "the checkout container exceeded its 512Mi memory limit",
            "root_cause_category": "resource_exhaustion",
            "summary": "The container was OOM-killed repeatedly and requests failed during "
            "each restart.",
            "causal_chain": [
                "memory use grew past the 512Mi limit",
                "the kernel killed the container",
                "requests failed while it restarted",
            ],
            "claims": [
                {
                    "statement": "the checkout container was OOM-killed three times",
                    "evidence_ids": ["e1"],
                },
                {
                    "statement": "the growth is probably a leak in the cart serialiser",
                    "evidence_ids": [],
                },
            ],
            "remediation_steps": [
                "raise the checkout memory limit to 1Gi",
                "profile the allocation growth under load",
            ],
            "confidence": 0.85,
        },
    ),
    expected_category=RootCauseCategory.RESOURCE_EXHAUSTION,
)

DEPLOY_REGRESSION = Scenario(
    key="deploy-regression",
    raw=_alertmanager("LatencyP99", "search", "p99 latency above 2s"),
    team=TeamContext(team_id="search", integrations=("kubernetes",), destinations=("slack",)),
    tools=(
        backend_tool(
            "kubernetes_deployment_history",
            evidence_source="kubernetes",
            summary="search rolled out revision 412 at 12:19, four minutes before the alert",
            content="revision=412 rolled_out_at=12:19 previous=411",
            evidence_type=EvidenceType.CHANGE,
        ),
    ),
    turns=(
        LoopTurn(
            tool_calls=(
                ToolCall(
                    id="c1",
                    name="kubernetes_deployment_history",
                    arguments={"query": "deployment=search"},
                ),
            )
        ),
        LoopTurn(
            text=(
                "Revision 412 rolled out four minutes before the latency alert fired [e1]. "
                "The previous revision did not have the problem."
            )
        ),
    ),
    structured=(
        _intake(reason="a latency alert is firing on the search service"),
        {
            "root_cause": "revision 412 of the search deployment regressed p99 latency",
            "root_cause_category": "deployment_regression",
            "summary": "A rollout four minutes before the alert is the only change in the window.",
            "causal_chain": ["revision 412 rolled out", "p99 latency doubled"],
            "claims": [
                {
                    "statement": "revision 412 rolled out four minutes before the alert",
                    "evidence_ids": ["e1"],
                }
            ],
            "remediation_steps": ["roll back to revision 411"],
            "confidence": 0.78,
        },
    ),
    expected_category=RootCauseCategory.DEPLOYMENT_REGRESSION,
)

CHATTER = Scenario(
    key="chatter",
    raw=RawAlert(text="morning all — anyone got a minute to look at my PR?", received_at=AT),
    team=TeamContext(team_id="payments", integrations=("kubernetes",), destinations=("slack",)),
    tools=(
        backend_tool(
            "kubernetes_pod_events",
            evidence_source="kubernetes",
            summary="nothing should ask for this",
            content="",
        ),
    ),
    turns=(),
    structured=(
        _intake(
            is_incident=False,
            confidence=0.97,
            reason="a greeting and a code-review request, not a production problem",
            severity="unknown",
        ),
    ),
    expected_category=RootCauseCategory.UNKNOWN,
    expects_investigation=False,
)

#: Every scenario, for the assertions that hold across the whole corpus.
CORPUS: Sequence[Scenario] = (OOM_KILL, DEPLOY_REGRESSION, CHATTER)
