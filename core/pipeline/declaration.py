"""The six stages as a declaration something outside the runtime can read.

Which stages exist is architecture rather than configuration — nothing here is
editable, and nothing here is a setting. What it is for is the other half of the
question: an operator deciding whether to trust an investigation needs to see
*what ran, in what order, and against what*, and until now that shape lived only
in the wiring of ``build_pipeline`` and in six module docstrings.

Three decisions are worth stating.

**The write set is derived, never repeated.** ``writes`` reads
``ownership.STAGE_WRITES``, the same table the purity test enforces. A second
copy of it here would agree on the day it was written and drift afterwards, and
the drift would arrive as a screen describing a pipeline the runtime does not
run.

**A stage that makes no model call names no role.** ``plan_evidence`` scores
capabilities with deterministic arithmetic, on purpose — an LLM ranker would
make two runs of one scenario incomparable — and ``resolve_integrations`` and
``deliver`` reach no model either. Giving them a role for symmetry would put a
model call on a screen where there is none.

**The role is the model's name here, and the provider is not.** Article VI: a
deployment chooses what each role runs on, so what this declares is the role.
Resolving it to a provider and a model is ``ModelsConfig``'s job, with the
provenance that says whether anybody chose it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config.constants.config_service import (
    MODEL_ROLE_DIAGNOSE,
    MODEL_ROLE_INTAKE,
    MODEL_ROLE_INVESTIGATOR,
)
from core.pipeline.ownership import STAGE_WRITES
from core.state.types import STAGE_ORDER, StageName


@dataclass(frozen=True, slots=True)
class StageDeclaration:
    """One stage of the investigation, as a reader outside the runtime sees it."""

    name: StageName
    summary: str
    #: What this stage reads before it decides anything. Short phrases rather
    #: than identifiers: the audience is an operator asking what was consulted.
    consults: tuple[str, ...]
    #: The model role this stage calls, or empty for a stage that calls none.
    model_role: str = ""
    #: Whether this stage dispatches the specialists a team declares.
    dispatches_subagents: bool = False

    @property
    def order(self) -> int:
        """Return this stage's position in the run, counting from zero."""
        return STAGE_ORDER.index(self.name)

    @property
    def writes(self) -> tuple[str, ...]:
        """Return the state paths this stage may change, in path order."""
        return tuple(sorted(STAGE_WRITES[self.name]))


#: Every stage, in the order the pipeline runs them.
PIPELINE_STAGES: Final[tuple[StageDeclaration, ...]] = (
    StageDeclaration(
        name=StageName.RESOLVE_INTEGRATIONS,
        summary=(
            "Works out what this team can actually call, and ends the run early when the "
            "answer is nothing."
        ),
        consults=(
            "the capability catalogue this node resolves to",
            "the integrations configured for this team",
        ),
    ),
    StageDeclaration(
        name=StageName.INTAKE,
        summary=(
            "Decides whether there is an incident at all, and links it to one already open "
            "when it is the same thing again."
        ),
        consults=(
            "the alert as it arrived, with whatever the adapter already parsed",
            "recent investigations, to recognise a duplicate",
        ),
        model_role=MODEL_ROLE_INTAKE,
    ),
    StageDeclaration(
        name=StageName.PLAN_EVIDENCE,
        summary=(
            "Scores the available capabilities against the alert and shortlists the ones "
            "worth starting from. Deterministic, so two runs of one scenario are comparable."
        ),
        consults=(
            "the capabilities resolved for this team",
            "the alert's source, severity and affected components",
            "the team's tool budget",
        ),
    ),
    StageDeclaration(
        name=StageName.GATHER_EVIDENCE,
        summary=(
            "The loop: calls capabilities, reads what comes back, and decides what to ask "
            "next, inside the iteration and tool ceilings."
        ),
        consults=(
            "every capability the catalogue allows, starting from the shortlist",
            "the incident window, which clamps every time-bounded argument",
            "the specialists this team declares, dispatched in parallel",
        ),
        model_role=MODEL_ROLE_INVESTIGATOR,
        dispatches_subagents=True,
    ),
    StageDeclaration(
        name=StageName.DIAGNOSE,
        summary=(
            "One call scoped to the conclusion and the evidence, then every claim checked "
            "against the observations that back it."
        ),
        consults=(
            "the evidence this run gathered",
            "the closed category taxonomy",
        ),
        model_role=MODEL_ROLE_DIAGNOSE,
    ),
    StageDeclaration(
        name=StageName.DELIVER,
        summary=(
            "Ships the finished report wherever the team is already looking, and records "
            "which destinations accepted it."
        ),
        consults=("the destinations configured for this team",),
    ),
)


def stage_declarations() -> tuple[StageDeclaration, ...]:
    """Return every stage, in the order the pipeline runs them."""
    return PIPELINE_STAGES


def declaration_for(name: StageName) -> StageDeclaration:
    """Return the declaration for ``name``, or raise naming the stage."""
    for entry in PIPELINE_STAGES:
        if entry.name is name:
            return entry
    raise KeyError(f"{name} is not a declared pipeline stage")


__all__ = [
    "PIPELINE_STAGES",
    "StageDeclaration",
    "declaration_for",
    "stage_declarations",
]
