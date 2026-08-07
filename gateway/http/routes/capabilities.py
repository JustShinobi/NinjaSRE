"""The capability catalogue, read-only, for console rendering (T032).

Discovery rather than a stored list — the same walk
``capabilities/registry/discovery.py`` runs for the agent runtime itself, so
this can never report a catalogue the runtime disagrees with.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from capabilities.registry.discovery import discover

router = APIRouter(prefix="/v1/capabilities", tags=["capabilities"])


class ToolView(BaseModel):
    name: str
    display_name: str
    description: str
    domain: str
    side_effect_level: str


class SkillView(BaseModel):
    name: str
    description: str


class CapabilityCatalogue(BaseModel):
    tools: list[ToolView]
    skills: list[SkillView]


@router.get("", response_model=CapabilityCatalogue)
async def list_capabilities() -> CapabilityCatalogue:
    """Return every declared tool and skill."""
    catalogue = discover()
    return CapabilityCatalogue(
        tools=[
            ToolView(
                name=tool.name,
                display_name=tool.metadata.display_name,
                description=tool.metadata.description,
                domain=tool.metadata.domain,
                side_effect_level=str(tool.metadata.side_effect_level),
            )
            for tool in catalogue.tools
        ],
        skills=[
            SkillView(name=skill.name, description=skill.metadata.description)
            for skill in catalogue.skills
        ],
    )


__all__ = ["router"]
