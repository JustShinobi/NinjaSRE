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

from collections.abc import Mapping, Sequence

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
from platform.runs.recording import RunTraceRecordingHook


def investigation_hooks(*, recorder: RunTraceRecordingHook | None = None) -> HookRegistry:
    """Return the hooks an investigation runtime must be constructed with.

    The incident-window guard is always present. It belongs to the runtime
    rather than to a stage because it acts on the loop's calls, and it reads the
    window from the session it is guarding — so one registry serves every
    concurrent investigation on a shared loop.

    ``recorder`` is registered at ``on_turn_end`` only when the caller has
    one — a runner composed with somewhere to write (see
    ``gateway.runtime.investigator.ReActInvestigationRunner``). Without one,
    this returns exactly what it always returned: the window guard alone,
    which is what keeps a deployment that composed no store working
    unchanged.

    The runtime is constructed by the caller, because which capabilities it can
    execute is a per-team question. This is the part of that construction the
    pipeline is not willing to leave to whoever is doing it.
    """
    registry = HookRegistry()
    registry.register(HookPoint.PRE_TOOL_USE, IncidentWindowGuard(), name="incident_window")
    if recorder is not None:
        registry.register(HookPoint.ON_TURN_END, recorder.on_turn_end, name="run_trace_recorder")
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
    context: Mapping[str, str] | None = None,
    strict: bool = False,
) -> Pipeline:
    """Return the six-stage investigation pipeline.

    This is what a served investigation runs. The path that serves a request
    — ``gateway.runtime.investigator.ReActInvestigationRunner.investigate`` —
    builds one of these per run and drives it; the evaluation harness that runs
    the scenario corpus builds one too, which is what makes a measured run and
    a served run the same six stages rather than two shapes with one name.

    That was not always true, and the reason it is now is worth stating.
    `/agent` has always shown "the stages an investigation runs" — six of them,
    in order, with what each consults — while a served run ran a flat loop of
    numbered turns and none of the stages. A screen describing a shape the
    deployment does not have is the same class of defect as a panel naming a
    model no call reaches, and the stages are the product's own account of what
    an investigation is. So the account is what runs.

    What the serving path supplies is itself the seam worth knowing about. It
    has already resolved the team's catalogue and narrowed it twice before this
    is built, so it passes a ``FixedCatalogueResolver`` over exactly the tools
    the runtime it hands in is holding — a second resolution here would be a
    second answer to a question already answered, and the two could disagree.

    The runtime must have been built with ``investigation_hooks()`` attached,
    or the incident window is a suggestion in the prompt rather than a bound.
    A caller that also records what a run did registers its recorder there, on
    the runtime, rather than here: the recorder writes turns and calls, and
    turns are the loop's.

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

    ``context`` is what the deployment already established about the subject
    and no alert payload carries — which estate resource the alert resolved
    onto, and therefore which vendor holds it. It reaches the gathering stage,
    which states it to the model before the first turn. Empty is the honest
    default: a caller that established nothing says nothing.
    """
    return Pipeline(
        (
            ResolveIntegrationsStage(
                resolver if resolver is not None else FixedCatalogueResolver(NO_CATALOGUE)
            ),
            IntakeStage(llm=llm, index=incidents),
            PlanEvidenceStage(ranker=ranker),
            GatherEvidenceStage(
                runtime=runtime,
                stream=stream,
                system_prompt=system_prompt,
                context=dict(context or {}),
            ),
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
