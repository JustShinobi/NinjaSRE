"""One scenario, end to end, through the canonical runtime and the real pipeline.

FR-012 is the requirement, and it is worth stating plainly: *nothing here is a
stand-in except the model and the vendors*. The six pipeline stages are the
production ones, the loop is the canonical ReAct loop with the real incident
window guard attached, the capabilities are the ones the integration packages
register, the clients are their own, and the credential proxy is the real engine
with each integration's real injection rule.

That is what makes a scenario failure informative. If the harness built its own
smaller pipeline, a green suite would prove the stages call each other; it would
prove nothing about whether an investigation works, and the first regression it
missed would be one in the code every investigation runs.

The runtime is checked rather than assumed (FR-023, Article V). An evaluation
number produced on an experimental adapter is a number nobody can attribute — a
change could be the model, the prompt, the memory, or the runtime — so the guard
in front of this entry point reads ``Runtime.is_canonical`` and refuses.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from capabilities.registry.planning import CatalogueRanker
from core.agent.guard import require_canonical_runtime
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import Runtime
from core.capability.registered import RegisteredTool, capability_marker
from core.domain.alerts.normalisation import RawAlert
from core.domain.diagnosis.result import Diagnosis
from core.llm.types import LLMClient
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import PipelineRun
from core.pipeline.ports import FixedCatalogueResolver, InMemoryIncidentIndex, StaticCatalogue
from core.pipeline.state_factory import initial_state
from core.state.types import TeamContext
from integrations._base.access import IntegrationAccess, bind, restore
from tests.harness.backends.base import MockVendorBoundary, VendorStack, stand_up
from tests.harness.loader import Scenario

#: What the scenario clock reads. Fixed, because an investigation's incident
#: window is computed from "now", and a window that moved between two runs of
#: the same scenario would make the two runs incomparable — which is exactly
#: what SC-002 asserts must not happen.
SCENARIO_CLOCK: datetime = datetime(2026, 8, 7, 12, 30, tzinfo=UTC)

#: The tenant every scenario runs in. One organisation, because a scenario is
#: about an incident and not about tenancy — the cross-tenant properties are
#: asserted where they belong, in the identity and persistence suites.
SCENARIO_ORG_ID = "acme"

#: The context a scenario says it wants a run to end in.
_CONTEXT_LABEL = "the synthetic scenario suite"


class ScenarioRunError(Exception):
    """A scenario could not be run at all, as opposed to running and failing.

    The distinction matters more than it looks. A scenario that ran and reached
    the wrong conclusion is a measurement; one that could not start is a broken
    harness, and reporting the second as the first is how a corpus quietly
    stops measuring anything.
    """


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    """One attempt at one scenario, and everything scoring it needs.

    Deliberately carries the whole ``PipelineRun`` and the whole vendor boundary
    rather than a summary. Feature 028 scores this, and a summary computed here
    would be this module deciding in advance which axes are worth having.
    """

    scenario: Scenario
    attempt: int
    run: PipelineRun
    boundary: MockVendorBoundary
    duration_seconds: float
    provider_id: str = ""
    model_id: str = ""
    credentials: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @property
    def diagnosis(self) -> Diagnosis | None:
        """Return the conclusion the investigation reached, if it reached one."""
        return self.run.state.investigation.diagnosis

    @property
    def root_cause_category(self) -> str:
        """Return the category the agent chose, or ``unknown``."""
        diagnosis = self.diagnosis
        return diagnosis.root_cause_category.value if diagnosis is not None else "unknown"

    @property
    def trajectory(self) -> tuple[str, ...]:
        """Return the capabilities the run executed, in the order it executed them."""
        return tuple(entry.capability for entry in self.run.state.evidence.entries)

    @property
    def evidence_sources(self) -> tuple[str, ...]:
        """Return every source the run's evidence came from, deduplicated in order."""
        seen: dict[str, None] = {}
        for entry in self.run.state.evidence.entries:
            seen[entry.source] = None
        return tuple(seen)

    @property
    def iterations(self) -> int:
        """Return how many loop iterations the investigation used."""
        return self.run.state.accounting.iterations

    @property
    def tokens(self) -> int:
        """Return the total tokens this attempt spent."""
        counts = self.run.state.accounting.tokens
        return counts.input_tokens + counts.output_tokens

    @property
    def answer_text(self) -> str:
        """Return everything the agent said, as one body for keyword checking.

        The conclusion, the diagnosis prose, its causal chain, and its
        remediation steps together. A keyword the agent used only in its
        recommended action still shows that it identified the thing — and an
        answer key that could only see the summary would score that as a miss.
        """
        parts: list[str] = [self.run.state.investigation.conclusion]
        diagnosis = self.diagnosis
        if diagnosis is not None:
            parts.extend(
                [
                    diagnosis.root_cause,
                    diagnosis.summary,
                    *diagnosis.causal_chain,
                    *diagnosis.remediation_steps,
                    *(claim.statement for claim in diagnosis.validated_claims),
                    *(claim.statement for claim in diagnosis.non_validated_claims),
                ]
            )
        parts.extend(entry.summary for entry in self.run.state.evidence.entries)
        return "\n".join(part for part in parts if part)


def capabilities_for(integrations: Sequence[str]) -> tuple[RegisteredTool, ...]:
    """Return every capability the given integrations register, as the agent sees them.

    Walks the vendors' own ``tools`` packages, which is how the real catalogue
    is built. A scenario therefore offers the agent exactly the tools a team
    with those integrations configured would have — including the ones the
    scenario planted no evidence for, which is what makes the empty-but-valid
    fallback matter.
    """
    import importlib

    found: list[RegisteredTool] = []
    for name in integrations:
        try:
            module = importlib.import_module(f"integrations.{name}.tools")
        except ModuleNotFoundError as error:  # pragma: no cover - a catalogue defect
            raise ScenarioRunError(
                f"the integration {name!r} declares no tools package, so a scenario naming it "
                f"would offer the agent nothing to call"
            ) from error
        for attribute in vars(module).values():
            registered = capability_marker(attribute)
            if registered is not None and registered not in found:
                found.append(registered)
    return tuple(found)


def alert_for(scenario: Scenario) -> RawAlert:
    """Return the trigger ``scenario`` declares, as the pipeline receives one."""
    received = scenario.alert.get("received_at", "")
    try:
        at = datetime.fromisoformat(received) if received else SCENARIO_CLOCK
    except ValueError as error:
        raise ScenarioRunError(
            f"{scenario.key}: alert.json's received_at is not an ISO 8601 timestamp: {received!r}"
        ) from error
    return RawAlert(
        text=scenario.alert.get("text", ""),
        payload=scenario.alert.get("payload", {}),
        source_hint=scenario.alert.get("source_hint", ""),
        received_at=at,
    )


async def run_scenario(
    scenario: Scenario,
    *,
    llm: LLMClient,
    runtime: Runtime | None = None,
    attempt: int = 1,
    tools: Sequence[RegisteredTool] | None = None,
) -> ScenarioRun:
    """Return the outcome of running ``scenario`` once.

    ``runtime`` defaults to the canonical loop built over this scenario's own
    capabilities. Passing one is for the test that proves an experimental
    runtime is refused; passing anything non-canonical raises.

    Raises:
        NonCanonicalRuntimeError: the runtime may not produce a published number.
        ScenarioRunError: the scenario could not be started.
    """
    catalogue = tuple(tools) if tools is not None else capabilities_for(scenario.integrations)
    stack = await stand_up(
        scenario.integrations,
        scenario.evidence,
        org_id=SCENARIO_ORG_ID,
        team_id=scenario.team_id,
        at=SCENARIO_CLOCK,
    )
    loop = (
        runtime
        if runtime is not None
        else ReActLoop(llm=llm, tools=catalogue, hooks=investigation_hooks())
    )
    require_canonical_runtime(loop, context=_CONTEXT_LABEL)

    started = time.perf_counter()
    run = await _drive(scenario, stack, catalogue, llm=llm, runtime=loop, attempt=attempt)
    elapsed = time.perf_counter() - started

    return ScenarioRun(
        scenario=scenario,
        attempt=attempt,
        run=run,
        boundary=stack.boundary,
        duration_seconds=elapsed,
        provider_id=getattr(llm, "provider_id", ""),
        model_id=getattr(llm, "model_id", ""),
        credentials=stack.credentials,
    )


async def _drive(
    scenario: Scenario,
    stack: VendorStack,
    catalogue: Sequence[RegisteredTool],
    *,
    llm: LLMClient,
    runtime: Runtime,
    attempt: int,
) -> PipelineRun:
    """Run the real pipeline with this scenario's stack bound, and unbind after."""
    resolved = StaticCatalogue(
        tools=tuple(catalogue), declarations=tuple(found.metadata for found in catalogue)
    )
    previous = bind(
        IntegrationAccess(
            transport=stack.transport, org_id=SCENARIO_ORG_ID, team_id=scenario.team_id
        )
    )
    try:
        pipeline = build_pipeline(
            llm=llm,
            runtime=runtime,
            resolver=FixedCatalogueResolver(resolved),
            ranker=CatalogueRanker(),
            incidents=InMemoryIncidentIndex(),
        )
        return await pipeline.run(
            initial_state(
                alert_for(scenario),
                TeamContext(
                    team_id=scenario.team_id,
                    integrations=scenario.integrations,
                    destinations=(),
                ),
                run_id=f"scenario-{scenario.suite}-{scenario.scenario_id}-{attempt}",
                started_at=SCENARIO_CLOCK,
            )
        )
    finally:
        restore(previous)


def scenario_summary(run: ScenarioRun) -> dict[str, Any]:
    """Return the small record a console line or a progress report reads."""
    return {
        "scenario": run.scenario.key,
        "attempt": run.attempt,
        "difficulty": run.scenario.difficulty,
        "failure_mode": run.scenario.failure_mode,
        "root_cause_category": run.root_cause_category,
        "iterations": run.iterations,
        "tokens": run.tokens,
        "duration_seconds": round(run.duration_seconds, 3),
        "vendor_calls": len(run.boundary.calls),
        "unmatched_vendor_calls": len(run.boundary.unmatched),
    }


__all__ = [
    "SCENARIO_CLOCK",
    "SCENARIO_ORG_ID",
    "ScenarioRun",
    "ScenarioRunError",
    "alert_for",
    "capabilities_for",
    "run_scenario",
    "scenario_summary",
]
