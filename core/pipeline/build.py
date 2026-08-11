"""Assembling the six stages, in one place, so nobody assembles five.

Every surface that starts an investigation goes through here. The alternative
— each surface constructing its own stage list — is how the CLI and the webhook
route end up running subtly different pipelines and the difference only shows
up as a scenario that behaves unlike production.

Each port defaults to its neutral implementation, so a caller supplies only
what it has. That is not a convenience: a deployment with no catalogue resolver
gets the zero-integration outcome, which is the correct behaviour and a tested
one, rather than a stage that cannot be constructed.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.runtime_port import Runtime
from core.llm.types import LLMClient
from core.pipeline.lifecycle import Pipeline, PipelineEndHook
from core.pipeline.ports import (
    NO_CATALOGUE,
    NO_RECENT_INCIDENTS,
    UNRANKED,
    CapabilityRanker,
    CatalogueResolver,
    DeliveryDestination,
    FixedCatalogueResolver,
    IncidentIndex,
)
from core.pipeline.stages.deliver import DeliverStage
from core.pipeline.stages.diagnose.node import DiagnoseStage
from core.pipeline.stages.gather_evidence import GatherEvidenceStage
from core.pipeline.stages.intake.node import IntakeStage
from core.pipeline.stages.plan_evidence import PlanEvidenceStage
from core.pipeline.stages.resolve_integrations import ResolveIntegrationsStage
from core.pipeline.stages.window_guard import IncidentWindowGuard
from core.pipeline.streaming import EventStream


def investigation_hooks() -> HookRegistry:
    """Return the hooks an investigation runtime must be constructed with.

    One so far: the incident-window guard. It belongs to the runtime
    rather than to a stage because it acts on the loop's calls, and it reads the
    window from the session it is guarding — so one registry serves every
    concurrent investigation on a shared loop.

    The runtime is constructed by the caller, because which capabilities it can
    execute is a per-team question. This is the part of that construction the
    pipeline is not willing to leave to whoever is doing it.
    """
    registry = HookRegistry()
    registry.register(HookPoint.PRE_TOOL_USE, IncidentWindowGuard(), name="incident_window")
    return registry


def build_pipeline(
    *,
    llm: LLMClient,
    runtime: Runtime,
    resolver: CatalogueResolver | None = None,
    ranker: CapabilityRanker = UNRANKED,
    incidents: IncidentIndex = NO_RECENT_INCIDENTS,
    destinations: Sequence[DeliveryDestination] = (),
    stream: EventStream | None = None,
    end_hooks: Sequence[PipelineEndHook] = (),
    system_prompt: str = "",
    strict: bool = False,
) -> Pipeline:
    """Return the six-stage investigation pipeline.

    The runtime must have been built with ``investigation_hooks()`` attached,
    or the incident window is a suggestion in the prompt rather than a bound.

    ``llm`` serves both model calls — intake's classification and diagnosis's
    structuring. One client rather than two because they are the same role
    doing the same kind of work, and a deployment that wants them separate
    passes a client bound to whichever model it prefers.

    ``system_prompt`` is what the investigating half runs under — a team's
    prompt override with its operating context already appended, from
    ``RuntimeBindings.system_prompt_for``. Empty leaves the shipped default,
    which is the whole of what a deployment that configured nothing needs.
    Intake and diagnosis are deliberately not given it: they classify and
    structure rather than investigate, and both run on every alert including
    the ones that never become an investigation.
    """
    return Pipeline(
        (
            ResolveIntegrationsStage(
                resolver if resolver is not None else FixedCatalogueResolver(NO_CATALOGUE)
            ),
            IntakeStage(llm=llm, index=incidents),
            PlanEvidenceStage(ranker=ranker),
            GatherEvidenceStage(runtime=runtime, stream=stream, system_prompt=system_prompt),
            DiagnoseStage(llm=llm),
            DeliverStage(destinations=tuple(destinations)),
        ),
        stream=stream,
        end_hooks=end_hooks,
        strict=strict,
    )


__all__ = [
    "build_pipeline",
    "investigation_hooks",
]
