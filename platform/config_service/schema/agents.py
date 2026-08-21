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
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator, model_validator

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
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredInt,
    ConfiguredStr,
    ConfiguredStrList,
)


class PromptOverrides(ConfigSection):
    """A system prompt per agent role, each falling back to the shipped one.

    Three fields rather than an open mapping, because a role nobody declared is
    a prompt nobody sends — and the failure is silent: the console shows the
    override, the agent never receives it.
    """

    investigator: ConfiguredStr = ""
    intake: ConfiguredStr = ""
    diagnose: ConfiguredStr = ""

    def for_role(self, role: str) -> str:
        """Return the override for ``role``, or empty if there is none."""
        return str(getattr(self, role, "")) if role in PROMPT_ROLES else ""


class SubAgentConfig(ConfigSection):
    """One specialist in a team's topology."""

    #: Required: a specialist with no name is one nothing can dispatch, and a
    #: default here would let the omission validate silently.
    name: ConfiguredStr
    description: ConfiguredStr = ""
    system_prompt: ConfiguredStr = ""
    capabilities: ConfiguredStrList = ()
    max_iterations: Annotated[ConfiguredInt, Field(ge=1, le=MAX_INVESTIGATION_LOOPS)] = (
        DEFAULT_SUBAGENT_ITERATIONS
    )
    model_role: ConfiguredStr = "subagent"
    enabled: bool = True

    @field_validator("model_role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        """Refuse a model role nothing resolves."""
        if value not in MODEL_ROLES:
            raise ValueError(f"must be one of {', '.join(MODEL_ROLES)}; found {value!r}")
        return value


class AgentsConfig(ConfigSection):
    """Prompts, topology, and the budgets one run may spend."""

    prompts: PromptOverrides = PromptOverrides()
    subagents: tuple[SubAgentConfig, ...] = ()
    max_iterations: Annotated[ConfiguredInt, Field(ge=1, le=MAX_INVESTIGATION_LOOPS)] = (
        MAX_INVESTIGATION_LOOPS
    )
    max_subagent_iterations: Annotated[ConfiguredInt, Field(ge=1, le=MAX_INVESTIGATION_LOOPS)] = (
        DEFAULT_SUBAGENT_ITERATIONS
    )
    max_parallel_subagents: Annotated[ConfiguredInt, Field(ge=1, le=MAX_PARALLEL_SUBAGENTS)] = (
        MAX_PARALLEL_SUBAGENTS
    )
    max_subagent_depth: Annotated[ConfiguredInt, Field(ge=0, le=MAX_SUBAGENT_DEPTH)] = (
        MAX_SUBAGENT_DEPTH
    )
    tool_budget: Annotated[ConfiguredInt, Field(ge=1)] = DEFAULT_TOOL_BUDGET

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

    provider: ConfiguredStr = DEFAULT_PROVIDER
    model: ConfiguredStr = DEFAULT_MODEL_ID

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
    "PromptOverrides",
    "SubAgentConfig",
]
