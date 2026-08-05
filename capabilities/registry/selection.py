"""Choosing what fits in one turn, and writing down why.

The catalogue is unbounded and the turn is not. Every tool schema in a request
is paid for on that turn and on every turn after it that carries the same
conversation, so the cap is on the payload rather than on the registry: four
hundred capabilities can exist and thirty-two can be offered.

The order things are taken in is the whole design.

**Plan entries first.** A planning stage or a human naming a capability knows
something the declaration does not, and scoring must not overrule it.

**Then skills, and the tools they direct.** A selected skill that names tools
the model cannot call is worse than not selecting the skill: the methodology
reads as available and the capability is not there.

**Then score order, up to the primary budget.**

**Then the reserve.** The last few slots are held for cheap, vendor-free
reasoning and recall capabilities. Without the reserve, an incident on a
well-integrated vendor floods the ranking with that vendor's tools and the
model loses the ability to think or to remember — precisely when an
investigation is going badly enough to need both.

Everything selected carries the reason it was selected into the trace. A
selection nobody can explain is one nobody can improve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from capabilities.registry.catalogue import ResolvedCatalogue
from capabilities.registry.disclosure import DiscoveredSkill
from capabilities.registry.scoring import Incident, ScoredCapability, rank
from config.constants.capabilities import (
    MAX_SELECTED_SKILLS,
    SECONDARY_EVIDENCE_SOURCES,
)
from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MAX_SECONDARY_FALLBACK_TOOLS,
)
from core.capability.metadata import CapabilityKind
from core.capability.ports import EffectivenessProvider
from core.capability.registered import RegisteredTool
from core.llm.types import ToolSchema


class SelectionError(Exception):
    """The bounds a selection was asked for cannot be satisfied."""


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """The bounded set one turn carries, and the reason for every part of it."""

    tools: tuple[RegisteredTool, ...] = ()
    skills: tuple[DiscoveredSkill, ...] = ()
    rationale: tuple[str, ...] = ()
    scores: tuple[ScoredCapability, ...] = ()

    def tool_schemas(self) -> tuple[ToolSchema, ...]:
        """Return the schemas as the provider layer wants them, pre-normalisation."""
        return tuple(
            ToolSchema(
                name=found.name,
                description=found.metadata.description,
                parameters=found.input_schema,
            )
            for found in self.tools
        )

    def skill_bodies(self) -> tuple[tuple[str, str], ...]:
        """Return each selected skill's name and body, loading the bodies now.

        This is the moment progressive disclosure pays out: the only bodies
        read from disk in the whole turn are the ones that won a slot.
        """
        return tuple((skill.name, skill.body()) for skill in self.skills)

    @property
    def secondary(self) -> tuple[RegisteredTool, ...]:
        """Return the selected tools that occupy the reserve."""
        return tuple(found for found in self.tools if is_secondary(found))


def is_secondary(found: RegisteredTool) -> bool:
    """Return whether ``found`` is a cheap, vendor-free reasoning or recall tool."""
    return found.metadata.evidence_source.lower() in SECONDARY_EVIDENCE_SOURCES


def _append(
    chosen: dict[str, RegisteredTool],
    rationale: list[str],
    found: RegisteredTool,
    reason: str,
    limit: int,
) -> bool:
    """Add ``found`` if there is room and it is not already chosen."""
    if found.name in chosen or len(chosen) >= limit:
        return False
    chosen[found.name] = found
    rationale.append(f"{found.name}: {reason}")
    return True


def select(
    catalogue: ResolvedCatalogue,
    incident: Incident,
    *,
    effectiveness: EffectivenessProvider | None = None,
    max_schemas: int = MAX_AGENT_TOOL_SCHEMAS,
    reserved: int = MAX_SECONDARY_FALLBACK_TOOLS,
    max_skills: int = MAX_SELECTED_SKILLS,
) -> SelectionResult:
    """Return the capabilities one turn carries, under the cap, with the rationale."""
    if reserved >= max_schemas:
        raise SelectionError(
            f"the reserve ({reserved}) must leave room inside the cap ({max_schemas})"
        )

    scores = rank(catalogue.metadata(), incident, effectiveness=effectiveness)
    order = {scored.name: position for position, scored in enumerate(scores)}
    by_score = {scored.name: scored for scored in scores}

    tools_by_name = {found.name: found for found in catalogue.tools}
    skills_by_name = {skill.name: skill for skill in catalogue.skills}

    chosen: dict[str, RegisteredTool] = {}
    rationale: list[str] = []
    primary_limit = max_schemas - reserved

    # 1. Everything the plan named, in the order the plan named it.
    planned_skills: list[DiscoveredSkill] = []
    for name in incident.planned_capabilities:
        if name in tools_by_name:
            _append(chosen, rationale, tools_by_name[name], "named by the plan", primary_limit)
        elif name in skills_by_name:
            planned_skills.append(skills_by_name[name])

    # 2. Skills, plan entries first and then by score, up to the skill cap.
    selected_skills = list(planned_skills)
    for scored in scores:
        if len(selected_skills) >= max_skills:
            break
        if scored.kind is not CapabilityKind.SKILL or scored.suppressed:
            continue
        skill = skills_by_name.get(scored.name)
        if skill is not None and skill not in selected_skills and scored.score > 0.0:
            selected_skills.append(skill)

    for skill in selected_skills:
        rationale.append(
            f"{skill.name}: skill selected"
            + (
                f" ({'; '.join(by_score[skill.name].rationale)})"
                if by_score.get(skill.name) and by_score[skill.name].rationale
                else ""
            )
        )

    # 3. The tools those skills direct. A skill naming a tool the model cannot
    #    call is a methodology that reads as available and is not.
    directed = sorted(
        {name for skill in selected_skills for name in skill.metadata.directs_tools},
        key=lambda name: order.get(name, len(order)),
    )
    for name in directed:
        found = tools_by_name.get(name)
        if found is not None:
            _append(chosen, rationale, found, "directed by a selected skill", primary_limit)

    # 4. Score order, down to the primary budget.
    for scored in scores:
        if scored.kind is not CapabilityKind.TOOL or scored.suppressed:
            continue
        found = tools_by_name.get(scored.name)
        if found is not None:
            _append(
                chosen,
                rationale,
                found,
                f"score {scored.score:g}"
                + (f" ({'; '.join(scored.rationale)})" if scored.rationale else ""),
                primary_limit,
            )

    # 5. The reserve, which nothing above was allowed to spend.
    for scored in scores:
        if scored.kind is not CapabilityKind.TOOL:
            continue
        found = tools_by_name.get(scored.name)
        if found is not None and is_secondary(found):
            _append(chosen, rationale, found, "reserved slot for reasoning and recall", max_schemas)

    # 6. Anything still unspent goes back to score order rather than being lost.
    for scored in scores:
        if scored.kind is not CapabilityKind.TOOL or scored.suppressed:
            continue
        found = tools_by_name.get(scored.name)
        if found is not None:
            _append(chosen, rationale, found, f"score {scored.score:g}", max_schemas)

    return SelectionResult(
        tools=tuple(chosen.values()),
        skills=tuple(selected_skills),
        rationale=tuple(rationale),
        scores=scores,
    )


def selection_record(result: SelectionResult) -> dict[str, object]:
    """Return the selection as it enters the run trace.

    Scores for everything considered, not only for what was chosen. The
    interesting question after a bad investigation is usually why something was
    *not* offered, and a record of the winners cannot answer it.
    """
    return {
        "tools": [found.name for found in result.tools],
        "skills": [skill.name for skill in result.skills],
        "rationale": list(result.rationale),
        "scores": [
            {
                "name": scored.name,
                "kind": scored.kind.value,
                "score": scored.score,
                "rationale": list(scored.rationale),
            }
            for scored in result.scores
        ],
    }


def schemas_for(tools: Sequence[RegisteredTool]) -> tuple[ToolSchema, ...]:
    """Return provider-neutral schemas for ``tools``."""
    return tuple(
        ToolSchema(
            name=found.name,
            description=found.metadata.description,
            parameters=found.input_schema,
        )
        for found in tools
    )


__all__ = [
    "SelectionError",
    "SelectionResult",
    "is_secondary",
    "schemas_for",
    "select",
    "selection_record",
]
