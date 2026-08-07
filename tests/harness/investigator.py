"""Running the real pipeline against whatever is on the other end of the transport.

The synthetic harness stands up a vendor boundary that answers from recorded
fixtures. The chaos and end-to-end suites need the same investigation with a
*live* vendor on the far side, and the difference between the two must be one
object — the transport — or the suites are measuring two different products.

So this is the composition root the real-infrastructure suites use, and it is
deliberately thin: resolve the capabilities the team's integrations register,
bind the transport, build the canonical pipeline, run it, unbind. Everything
between the capability and the vendor is production code, exactly as it is in
the synthetic path, and the credential still never reaches this process — the
proxy on the far side of the transport injects it.

``Investigator`` is a protocol because the suites need to be assertable without
a cluster. A scripted investigator returns an observation the way a recorded
provider returns a turn, and the runner cannot tell the difference, which is
what lets the lock, the validity gate, and the cleanup path be proven offline.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from capabilities.registry.planning import CatalogueRanker
from core.agent.react_loop import ReActLoop
from core.capability.registered import RegisteredTool
from core.domain.alerts.normalisation import RawAlert
from core.llm.types import LLMClient
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import PipelineRun
from core.pipeline.ports import FixedCatalogueResolver, StaticCatalogue
from core.pipeline.state_factory import initial_state
from core.state.types import TeamContext
from integrations._base.access import IntegrationAccess, bind, restore
from tests.harness.runner import capabilities_for
from tests.harness.scoring.composite import Observation
from tests.harness.scoring.matching import steps_from_iterations


@dataclass(frozen=True, slots=True)
class LiveRun:
    """One investigation against live telemetry, and what scoring reads from it."""

    run: PipelineRun
    duration_seconds: float = 0.0
    provider_id: str = ""
    model_id: str = ""

    @property
    def run_id(self) -> str:
        """Return the identifier this investigation was recorded under."""
        return self.run.state.run_id

    @property
    def observation(self) -> Observation:
        """Return what this run did, in the shape the five scorers take."""
        return observation_of_run(
            self.run,
            duration_seconds=self.duration_seconds,
            provider_id=self.provider_id,
            model_id=self.model_id,
        )


@runtime_checkable
class InvestigationOutcome(Protocol):
    """What an investigation gives the suites: an identity and an observation.

    Structural, and narrow on purpose. ``LiveRun`` satisfies it by carrying a
    whole ``PipelineRun``; a scripted double satisfies it by carrying nothing
    but the observation, which is what lets the lock, validity, and cleanup
    paths be asserted without a cluster or a provider.
    """

    @property
    def run_id(self) -> str:
        """Return the identifier this investigation was recorded under."""

    @property
    def observation(self) -> Observation:
        """Return what the investigation did, as the five scorers read it."""


@runtime_checkable
class Investigator(Protocol):
    """Whatever turns an alert into an investigation the suites can score."""

    async def investigate(
        self, alert: RawAlert, *, team: TeamContext, run_id: str = ""
    ) -> InvestigationOutcome:
        """Return the investigation ``alert`` produced."""


def observation_of_run(
    run: PipelineRun,
    *,
    duration_seconds: float = 0.0,
    provider_id: str = "",
    model_id: str = "",
) -> Observation:
    """Return what one pipeline run did, in the shape the scorers take.

    The trajectory is grouped by the iteration each call was made in, matching
    what the synthetic path does — whatever the loop dispatched together is one
    position, whichever coroutine happened to finish first.
    """
    state = run.state
    entries = state.evidence.entries
    diagnosis = state.investigation.diagnosis

    return Observation(
        root_cause_category=(
            diagnosis.root_cause_category.value if diagnosis is not None else "unknown"
        ),
        answer_text=answer_text_of(run),
        evidence_sources=tuple(dict.fromkeys(entry.source for entry in entries)),
        validated_claims=diagnosis.validated_claims if diagnosis is not None else (),
        held_evidence_ids=state.evidence.ids,
        trajectory=steps_from_iterations(
            (entry.provenance.iteration, entry.capability) for entry in entries
        ),
        iterations=state.accounting.iterations,
        tokens=state.accounting.tokens.input_tokens + state.accounting.tokens.output_tokens,
        duration_seconds=duration_seconds,
        provider_id=provider_id,
        model_id=model_id,
    )


def answer_text_of(run: PipelineRun) -> str:
    """Return everything the agent said, as one body for keyword checking.

    Same composition the synthetic path uses: a keyword the agent only used in
    its recommended action still shows it identified the thing, and an answer
    key that could see only the summary would score that as a miss.
    """
    state = run.state
    parts: list[str] = [state.investigation.conclusion]
    diagnosis = state.investigation.diagnosis
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
    parts.extend(entry.summary for entry in state.evidence.entries)
    return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class PipelineInvestigator:
    """The canonical pipeline, over live integrations, for one tenant.

    ``transport`` is the seam. Point it at a proxy in front of the operator's own
    vendors and this runs against production telemetry; point it at the
    in-process proxy the harness stands up and the same code runs against
    recorded responses. Nothing between here and the vendor changes.
    """

    llm: LLMClient
    transport: Any
    org_id: str = "acme"
    tools: Sequence[RegisteredTool] | None = None
    #: Non-secret per-vendor options a client needs to find its target — a
    #: region, a site, a namespace. Never a credential; there is no parameter
    #: one could arrive through.
    options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    async def investigate(self, alert: RawAlert, *, team: TeamContext, run_id: str = "") -> LiveRun:
        """Return the investigation ``alert`` produced against live telemetry."""
        catalogue = (
            tuple(self.tools) if self.tools is not None else capabilities_for(team.integrations)
        )
        resolved = StaticCatalogue(
            tools=catalogue, declarations=tuple(found.metadata for found in catalogue)
        )
        loop = ReActLoop(llm=self.llm, tools=catalogue, hooks=investigation_hooks())

        previous = bind(
            IntegrationAccess(transport=self.transport, org_id=self.org_id, team_id=team.team_id)
        )
        started = time.perf_counter()
        try:
            pipeline = build_pipeline(
                llm=self.llm,
                runtime=loop,
                resolver=FixedCatalogueResolver(resolved),
                ranker=CatalogueRanker(),
            )
            run = await pipeline.run(
                initial_state(alert, team, run_id=run_id, started_at=alert.at())
            )
        finally:
            restore(previous)

        return LiveRun(
            run=run,
            duration_seconds=time.perf_counter() - started,
            provider_id=getattr(self.llm, "provider_id", ""),
            model_id=getattr(self.llm, "model_id", ""),
        )


__all__ = [
    "InvestigationOutcome",
    "Investigator",
    "LiveRun",
    "PipelineInvestigator",
    "answer_text_of",
    "observation_of_run",
]
