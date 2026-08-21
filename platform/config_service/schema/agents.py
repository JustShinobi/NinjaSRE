"""What the agent is told, how it is shaped, and what it runs on.

Three decisions are recorded here rather than in the fields.

**Prompt defaults are code; prompt overrides are configuration.** A fresh
deployment works with no configuration at all, because the defaults are the
constants in ``config/prompts/``. Customising is a configuration change rather
than a fork, and improving the shipped prompt is a diff somebody reviews rather
than a migration over every team's stored copy.

**Budgets are bounded above by the constants, not by the operator.** A team may
lower ``max_iterations``; it may not raise it past ``MAX_INVESTIGATION_LOOPS``.
Article II says the ceiling is a named constant, and a configuration field that
could exceed it would make the constant advisory.

**Sub-agent topology is configuration.** Which specialists exist for a team, and
what each is told, is the difference between a platform team's deployment and a
security team's — and it is not worth a code change.

**Overriding and adding are different fields.** ``PromptOverrides`` replaces the
shipped prompt; ``OperatingContext`` adds facts to whichever prompt is in force.
An operator who has only the first and wants the second copies the whole shipped
prompt to paste one sentence at the end of it, and is then frozen on the version
of that prompt they copied on the day they copied it — while the configuration
stays valid and nothing tells them the text has aged. The wrong field forces the
wrong use.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from config.constants.agents import (
    MAX_OPERATING_CONTEXT_NAME_CHARS,
    MAX_OPERATING_CONTEXT_SECTIONS,
    OPERATING_CONTEXT_ROLES,
    OPERATING_CONTEXT_TOKEN_BUDGET,
)
from config.constants.config_service import MODEL_ROLES, PROMPT_ROLES
from config.constants.investigation import (
    DEFAULT_SUBAGENT_ITERATIONS,
    DEFAULT_TOOL_BUDGET,
    MAX_INVESTIGATION_LOOPS,
    MAX_PARALLEL_SUBAGENTS,
    MAX_SUBAGENT_DEPTH,
)
from config.constants.llm import DEFAULT_MODEL_ID, DEFAULT_PROVIDER, SUPPORTED_PROVIDERS
from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from config.prompts.operating_context import (
    OPERATING_CONTEXT_HEADING,
    OPERATING_CONTEXT_SECTION,
)
from core.capability.tokens import estimate_tokens
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredInt,
    ConfiguredStr,
    ConfiguredStrList,
    field_help,
    section_help,
)

#: The character a section name may not contain, because a name is a path
#: segment in the provenance table as well as a heading in a prompt.
_PATH_SEPARATOR = "."


class PromptOverrides(ConfigSection):
    """A system prompt per agent role, each falling back to the shipped one.

    Three fields rather than an open mapping, because a role nobody declared is
    a prompt nobody sends — and the failure is silent: the console shows the
    override, the agent never receives it.
    """

    model_config = section_help(
        "Replace the instructions one agent role is given. Leave a role empty and it "
        "runs on the prompt this deployment ships with."
    )

    investigator: Annotated[
        ConfiguredStr,
        field_help(
            "Instructions for the role that runs the investigation. Empty means the shipped prompt."
        ),
    ] = ""
    intake: Annotated[
        ConfiguredStr,
        field_help(
            "Instructions for the role that reads an incoming alert and decides what it is. "
            "Empty means the shipped prompt."
        ),
    ] = ""
    diagnose: Annotated[
        ConfiguredStr,
        field_help(
            "Instructions for the role that turns evidence into a root cause. "
            "Empty means the shipped prompt."
        ),
    ] = ""

    def for_role(self, role: str) -> str:
        """Return the override for ``role``, or empty if there is none."""
        return str(getattr(self, role, "")) if role in PROMPT_ROLES else ""


class OperatingContext(ConfigSection):
    """Facts about *this* environment, added to the prompt of the roles that investigate.

    **A mapping of named sections, not a block of text**, because a section is
    the unit of inheritance. The merge recurses into mappings and replaces
    lists whole (``platform/config_service/merge.py``), so a mapping gives a
    child node the three operations the spec asks for — add a section, override
    one by name, empty one so it stops being sent — with per-section provenance
    for free, and a list would have given a child one operation: restate every
    section its ancestors wrote. That is the failure this feature exists to fix,
    one level down.

    Distinct names therefore need no validator. Two sections cannot share a name
    in a mapping, which is a stronger guarantee than a check: there is no
    document that could express the collision.

    **The budget is a refusal, never a truncation.** Every character here is
    paid on every model call of every investigation, so the ceiling is real —
    but it is enforced against a person who still has the text in front of them,
    which silent shrinking is not.
    """

    model_config = section_help(
        "Facts about your own environment, added to the end of the prompt for the roles "
        "that investigate. Every word here is sent on every model call, so keep it to "
        "what changes how an incident should be read."
    )

    #: Section name to body. An empty body is how a child stops an inherited
    #: section from being sent, and is deliberately different from clearing the
    #: field: clearing restores what the parent said, emptying overrules it.
    sections: Annotated[
        Mapping[str, ConfiguredStr],
        Field(max_length=MAX_OPERATING_CONTEXT_SECTIONS),
        field_help(
            "Named blocks of background, one per topic — what this estate is, what is "
            "critical, who owns what. Emptying a block's body stops it being sent while "
            "keeping the name; removing the block inherits whatever the level above says."
        ),
    ] = {}
    #: The ablation switch. Off keeps the text and sends none of it, so the
    #: contribution of this mechanism can be measured against the same
    #: deployment rather than against a different one.
    enabled: Annotated[
        bool,
        field_help(
            "Send this background with every investigation. Off keeps the text and sends "
            "none of it, which is how you measure what it is worth."
        ),
    ] = True

    @model_validator(mode="after")
    def _names_are_addressable(self) -> OperatingContext:
        """Refuse a name that cannot be a heading and a path segment both."""
        for name in self.sections:
            if not name.strip():
                raise ValueError("declares a section with no name")
            if _PATH_SEPARATOR in name:
                raise ValueError(
                    f"the section name {name!r} contains {_PATH_SEPARATOR!r}, which is the "
                    f"path separator provenance and removal are addressed by"
                )
            if len(name) > MAX_OPERATING_CONTEXT_NAME_CHARS:
                raise ValueError(
                    f"the section name {name!r} is longer than "
                    f"{MAX_OPERATING_CONTEXT_NAME_CHARS} characters; a name is a heading"
                )
        return self

    @model_validator(mode="after")
    def _within_budget(self) -> OperatingContext:
        """Refuse a document past the token budget, naming the overage.

        Measured over the written sections whether or not the context is
        switched on. A disabled document that is over budget would otherwise be
        stored happily and fail the day somebody enabled it, which is the worst
        moment to find out.
        """
        spent = estimate_tokens(self.document())
        if spent > OPERATING_CONTEXT_TOKEN_BUDGET:
            raise ValueError(
                f"is {spent - OPERATING_CONTEXT_TOKEN_BUDGET} tokens over the "
                f"{OPERATING_CONTEXT_TOKEN_BUDGET}-token operating-context budget "
                f"({spent} used). Every token here is spent on every model call of "
                f"every investigation; longer background belongs in the knowledge "
                f"corpus, which is retrieved when it is relevant."
            )
        return self

    def written(self) -> tuple[tuple[str, str], ...]:
        """Return the sections that carry a body, in the order the document declares them."""
        return written_sections(self.sections)

    def document(self) -> str:
        """Return the whole rendered block, whether or not it is switched on."""
        return render_sections(self.sections)

    def render(self) -> str:
        """Return the text the model receives, empty when there is none to send."""
        return self.document() if self.enabled else ""

    def tokens(self) -> int:
        """Return what this context costs, by the estimator the budget is set in."""
        return estimate_tokens(self.document())


def written_sections(sections: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Return the sections of ``sections`` that carry a body, in declared order."""
    return tuple((name, body.strip()) for name, body in sections.items() if body.strip())


def render_sections(sections: Mapping[str, str]) -> str:
    """Return the framed block ``sections`` renders to, empty when none carries a body.

    A function rather than only a method, because the one caller that most needs
    to measure a context is the preview — and the document it has to measure is
    precisely the one too long to build into an ``OperatingContext`` at all.
    """
    written = written_sections(sections)
    if not written:
        return ""
    return "\n\n".join(
        (
            OPERATING_CONTEXT_HEADING,
            *(OPERATING_CONTEXT_SECTION.format(name=name, body=body) for name, body in written),
        )
    )


def with_operating_context(prompt: str, context: str) -> str:
    """Return ``prompt`` with ``context`` appended, or ``prompt`` unchanged.

    The one place the two are joined, so the text the console previews and the
    text the model receives cannot be assembled two ways. Appended rather than
    prepended: the system prompt is what the investigation is framed as, and
    putting an estate description ahead of it would reframe every run.
    """
    if not context.strip():
        return prompt
    return f"{prompt.rstrip()}\n\n{context.strip()}"


class SubAgentConfig(ConfigSection):
    """One specialist in a team's topology."""

    model_config = section_help(
        "One specialist the investigation can hand a narrower question to — a database "
        "specialist, a network specialist. It runs with its own instructions and its own "
        "set of capabilities."
    )

    #: Required: a specialist with no name is one nothing can dispatch, and a
    #: default here would let the omission validate silently.
    name: Annotated[
        ConfiguredStr,
        field_help("What this specialist is called. Required, and how it is dispatched."),
    ]
    description: Annotated[
        ConfiguredStr,
        field_help(
            "When this specialist should be asked. Read by the investigation when it "
            "decides whether to hand the question over."
        ),
    ] = ""
    system_prompt: Annotated[
        ConfiguredStr,
        field_help("Instructions this specialist runs on. Empty means the shipped prompt."),
    ] = ""
    capabilities: Annotated[
        ConfiguredStrList,
        field_help(
            "The capabilities this specialist may call. Empty means everything the team "
            "already allows."
        ),
    ] = ()
    max_iterations: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_INVESTIGATION_LOOPS),
        field_help("How many turns this specialist may take before it has to report back."),
    ] = DEFAULT_SUBAGENT_ITERATIONS
    model_role: Annotated[
        ConfiguredStr,
        field_help(
            "Which model role this specialist runs on, so it can be given a cheaper or a "
            "stronger model than the investigation itself."
        ),
    ] = "subagent"
    enabled: Annotated[
        bool, field_help("Off keeps the specialist configured and stops it being dispatched.")
    ] = True

    @field_validator("model_role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        """Refuse a model role nothing resolves."""
        if value not in MODEL_ROLES:
            raise ValueError(f"must be one of {', '.join(MODEL_ROLES)}; found {value!r}")
        return value


class AgentsConfig(ConfigSection):
    """Prompts, topology, and the budgets one run may spend."""

    model_config = section_help(
        "What the agent is told, which specialists it can call on, and how much one "
        "investigation may spend before it has to stop and report."
    )

    prompts: PromptOverrides = PromptOverrides()
    #: What this deployment is, added to the prompt rather than replacing it.
    operating_context: OperatingContext = OperatingContext()
    subagents: Annotated[
        tuple[SubAgentConfig, ...],
        field_help("The specialists this team can dispatch. Only the enabled ones are ever used."),
    ] = ()
    max_iterations: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_INVESTIGATION_LOOPS),
        field_help(
            "How many times one investigation may look, think and look again before it "
            "stops and reports what it has. Lower it to cap what a run can cost; it "
            "cannot be raised past the platform ceiling."
        ),
    ] = MAX_INVESTIGATION_LOOPS
    max_subagent_iterations: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_INVESTIGATION_LOOPS),
        field_help("The same ceiling, for a specialist working on a handed-over question."),
    ] = DEFAULT_SUBAGENT_ITERATIONS
    max_parallel_subagents: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_PARALLEL_SUBAGENTS),
        field_help("How many specialists may be working at the same moment."),
    ] = MAX_PARALLEL_SUBAGENTS
    max_subagent_depth: Annotated[
        ConfiguredInt,
        Field(ge=0, le=MAX_SUBAGENT_DEPTH),
        field_help(
            "How many levels of hand-over are allowed. Zero means a specialist may not "
            "dispatch another one."
        ),
    ] = MAX_SUBAGENT_DEPTH
    tool_budget: Annotated[
        ConfiguredInt,
        Field(ge=1),
        field_help("How many capability calls one investigation may make in total."),
    ] = DEFAULT_TOOL_BUDGET

    @model_validator(mode="after")
    def _names_are_distinct(self) -> AgentsConfig:
        """Refuse two specialists sharing one name.

        A dispatch would otherwise reach whichever the merge happened to order
        last, which is not a decision anybody made.
        """
        seen: set[str] = set()
        for subagent in self.subagents:
            if subagent.name in seen:
                raise ValueError(f"declares {subagent.name!r} more than once")
            seen.add(subagent.name)
        return self

    def prompt_for(self, role: str) -> str:
        """Return the system prompt for ``role``, falling back to the shipped one.

        The fallback is what makes a zero-configuration deployment work: no
        prompt is stored anywhere until somebody chooses to change one.
        """
        return self.prompts.for_role(role).strip() or DEFAULT_RUNTIME_SYSTEM_PROMPT

    def system_prompt_for(self, role: str) -> str:
        """Return the whole system prompt ``role`` receives, context included.

        The assembly site: the shipped-or-overridden prompt first, this
        deployment's own facts after it, and only for the roles that
        investigate (``OPERATING_CONTEXT_ROLES``). Every other role is
        byte-identical to ``prompt_for``, which is what keeps a deployment that
        configured none of this paying nothing.
        """
        prompt = self.prompt_for(role)
        if role not in OPERATING_CONTEXT_ROLES:
            return prompt
        return with_operating_context(prompt, self.operating_context.render())

    def subagent(self, name: str) -> SubAgentConfig | None:
        """Return the sub-agent called ``name``, or ``None``."""
        for subagent in self.subagents:
            if subagent.name == name:
                return subagent
        return None

    def enabled_subagents(self) -> tuple[SubAgentConfig, ...]:
        """Return the sub-agents a run may actually dispatch."""
        return tuple(subagent for subagent in self.subagents if subagent.enabled)


class ModelSelection(ConfigSection):
    """The provider and model one role runs on."""

    model_config = section_help(
        "Which provider and model this one role runs on. A role left alone runs on the "
        "deployment default, so you can give the expensive work a stronger model and "
        "leave the rest."
    )

    provider: Annotated[
        ConfiguredStr,
        field_help("The provider this role calls. Must be one this deployment has installed."),
    ] = DEFAULT_PROVIDER
    model: Annotated[
        ConfiguredStr, field_help("The model identifier, as that provider spells it.")
    ] = DEFAULT_MODEL_ID

    @field_validator("provider")
    @classmethod
    def _installed(cls, value: str) -> str:
        """Refuse a provider no adapter answers to."""
        if value not in SUPPORTED_PROVIDERS:
            raise ValueError(f"must be one of {', '.join(SUPPORTED_PROVIDERS)}; found {value!r}")
        return value


class ModelsConfig(ConfigSection):
    """Which provider and model each role resolves to.

    One field per role rather than an open mapping. A typo in a role name would
    otherwise be configuration nobody ever reads, leaving that role on the
    default while the console showed it bound.

    A role nobody configured resolves to the deployment default rather than
    failing: an investigation that cannot start is worse than one that starts on
    the default model and records which one in its trace.
    """

    model_config = section_help("Which provider and model each role of the agent runs on.")

    investigator: ModelSelection = ModelSelection()
    subagent: ModelSelection = ModelSelection()
    intake: ModelSelection = ModelSelection()
    diagnose: ModelSelection = ModelSelection()
    extraction: ModelSelection = ModelSelection()
    embedding: ModelSelection = ModelSelection()
    selection: ModelSelection = ModelSelection()
    summarisation: ModelSelection = ModelSelection()

    def for_role(self, role: str) -> ModelSelection:
        """Return what ``role`` runs on, or the deployment default."""
        found = getattr(self, role, None) if role in MODEL_ROLES else None
        return found if isinstance(found, ModelSelection) else ModelSelection()

    def selection_for(self, role: str) -> tuple[str, str] | None:
        """Return the provider and model bound to ``role``, or ``None``.

        The task router's source. ``None`` rather than the default pair is the
        whole of what this adds over ``for_role``: the router has to be able to
        tell a role somebody chose from one that fell through, and a default that
        looks like a choice is how a deployment ends up believing it split its
        models when it did not.
        """
        if role not in self.declared():
            return None
        found = self.for_role(role)
        return (found.provider, found.model)

    def bound_roles(self) -> tuple[str, ...]:
        """Return the roles this configuration binds explicitly, in role order.

        Explicitly: a role resolving to the deployment default must not appear
        as though somebody had chosen it.
        """
        declared = self.declared()
        return tuple(role for role in MODEL_ROLES if role in declared)


#: What each section declares, for the console's form. Read off the models
#: rather than repeated beside them, so a field cannot be added without the
#: form learning about it.
AGENTS_FIELDS: tuple[str, ...] = tuple(AgentsConfig.model_fields)
MODELS_FIELDS: tuple[str, ...] = tuple(ModelsConfig.model_fields)
SUBAGENT_FIELDS: tuple[str, ...] = tuple(SubAgentConfig.model_fields)


__all__ = [
    "AGENTS_FIELDS",
    "MODELS_FIELDS",
    "SUBAGENT_FIELDS",
    "AgentsConfig",
    "ModelSelection",
    "ModelsConfig",
    "OperatingContext",
    "PromptOverrides",
    "SubAgentConfig",
    "render_sections",
    "with_operating_context",
    "written_sections",
]
