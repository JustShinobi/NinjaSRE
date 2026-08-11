"""What the agent is, over the API: the stages it runs, in the order it runs them.

A read of a declaration rather than of a document. Which stages exist is
architecture — nothing here is editable and nothing here is a setting — so the
route takes no node and answers the same thing for every caller in a given
build.

**No provider and no model identifier leaves here.** A stage names the *role* it
calls, and what a role resolves to is a configuration value with provenance,
served by ``GET /v1/config/{node_id}/fields`` like every other. Article VI: a
surface that printed a vendor's model beside each stage would be presenting one
deployment's choice as though it were the shape of the software.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.config_service import MODEL_ROLES
from core.pipeline.declaration import stage_declarations
from gateway.http.deps import authorized

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class StageView(BaseModel):
    """One stage: where it sits, what it reads, and what it is allowed to change."""

    name: str
    order: int
    summary: str
    consults: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    #: Empty for a stage that makes no model call. A role, never a model.
    model_role: str = ""
    dispatches_subagents: bool = False


class PipelineView(BaseModel):
    """The investigation's shape, and the roles a deployment may bind."""

    stages: list[StageView] = Field(default_factory=list)
    #: Every role this build resolves, so a surface listing them cannot hold a
    #: shorter list than the configuration that binds them.
    model_roles: list[str] = Field(default_factory=list)


@router.get("/pipeline", response_model=PipelineView, dependencies=[Depends(authorized)])
async def read_pipeline() -> PipelineView:
    """Return the stages an investigation runs, in order, with what each consults."""
    return PipelineView(
        stages=[
            StageView(
                name=entry.name.value,
                order=entry.order,
                summary=entry.summary,
                consults=list(entry.consults),
                writes=list(entry.writes),
                model_role=entry.model_role,
                dispatches_subagents=entry.dispatches_subagents,
            )
            for entry in stage_declarations()
        ],
        model_roles=list(MODEL_ROLES),
    )


__all__ = ["router"]
