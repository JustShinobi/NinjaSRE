"""The six-stage investigation pipeline.

A stage is a pure ``async (state) -> updates`` function, the lifecycle merges
what each returns through one function, and every transition is a typed event
on the stream. What the pipeline owns that the runtime does not is the shape of
an investigation: reject noise before it costs anything, give the loop a plan,
turn free text into a structured root cause, and ship it where the team is
already looking.

    from core.pipeline import build_pipeline, initial_state

    pipeline = build_pipeline(llm=get_llm("investigator"), runtime=loop)
    run = await pipeline.run(initial_state(raw, team))
"""

from __future__ import annotations

from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import (
    Pipeline,
    PipelineEndHook,
    PipelineOrderError,
    PipelineRun,
)
from core.pipeline.ownership import STAGE_WRITES, violations, writes_of
from core.pipeline.stage import Stage
from core.pipeline.state_factory import initial_state, new_run_id, state_from_text
from core.pipeline.streaming import (
    EventSink,
    EventStream,
    InvestigationView,
    PipelineEvent,
    PipelineEventKind,
    RecordingSink,
    replay,
)

__all__ = [
    "STAGE_WRITES",
    "EventSink",
    "EventStream",
    "InvestigationView",
    "Pipeline",
    "PipelineEndHook",
    "PipelineEvent",
    "PipelineEventKind",
    "PipelineOrderError",
    "PipelineRun",
    "RecordingSink",
    "Stage",
    "build_pipeline",
    "initial_state",
    "investigation_hooks",
    "new_run_id",
    "replay",
    "state_from_text",
    "violations",
    "writes_of",
]
