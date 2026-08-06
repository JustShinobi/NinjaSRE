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

from collections.abc import Mapping
from dataclasses import dataclass, field

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
from platform.config_service.schema.reader import Reader

#: What a sub-agent declaration may say. Anything else is a typo, and a typo in
#: a topology entry is a specialist that is configured and never dispatched.
SUBAGENT_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "system_prompt",
    "capabilities",
    "max_iterations",
    "model_role",
    "enabled",
)

AGENTS_FIELDS: tuple[str, ...] = (
    "prompts",
    "subagents",
    "max_iterations",
    "max_subagent_iterations",
    "max_parallel_subagents",
    "max_subagent_depth",
    "tool_budget",
)

MODELS_FIELDS: tuple[str, ...] = MODEL_ROLES


@dataclass(frozen=True, slots=True)
class SubAgentConfig:
    """One specialist in a team's topology."""

    name: str
    description: str = ""
    system_prompt: str = ""
    capabilities: tuple[str, ...] = ()
    max_iterations: int = DEFAULT_SUBAGENT_ITERATIONS
    model_role: str = "subagent"
    enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> SubAgentConfig:
        """Return the sub-agent ``reader`` describes, recording what it cannot read."""
        reader.close(SUBAGENT_FIELDS)
        name = reader.string("name")
        if not name:
            reader.fail("name", "a sub-agent needs a name to be dispatched by")
        return cls(
            name=name,
            description=reader.string("description"),
            system_prompt=reader.string("system_prompt"),
            capabilities=reader.strings("capabilities"),
            max_iterations=reader.integer(
                "max_iterations",
                DEFAULT_SUBAGENT_ITERATIONS,
                minimum=1,
                maximum=MAX_INVESTIGATION_LOOPS,
            ),
            model_role=reader.string("model_role", "subagent", allowed=MODEL_ROLES),
            enabled=reader.boolean("enabled", True),
        )


@dataclass(frozen=True, slots=True)
class AgentsConfig:
    """Prompts, topology, and the budgets one run may spend."""

    prompts: Mapping[str, str] = field(default_factory=dict)
    subagents: tuple[SubAgentConfig, ...] = ()
    max_iterations: int = MAX_INVESTIGATION_LOOPS
    max_subagent_iterations: int = DEFAULT_SUBAGENT_ITERATIONS
    max_parallel_subagents: int = MAX_PARALLEL_SUBAGENTS
    max_subagent_depth: int = MAX_SUBAGENT_DEPTH
    tool_budget: int = DEFAULT_TOOL_BUDGET

    @classmethod
    def of(cls, reader: Reader) -> AgentsConfig:
        """Return the agent configuration ``reader`` describes."""
        reader.close(AGENTS_FIELDS)
        subagents = tuple(SubAgentConfig.of(each) for each in reader.sections("subagents"))
        _report_duplicate_names(reader, subagents)
        return cls(
            prompts=reader.keyed_strings("prompts", keys=PROMPT_ROLES),
            subagents=subagents,
            max_iterations=reader.integer(
                "max_iterations",
                MAX_INVESTIGATION_LOOPS,
                minimum=1,
                maximum=MAX_INVESTIGATION_LOOPS,
            ),
            max_subagent_iterations=reader.integer(
                "max_subagent_iterations",
                DEFAULT_SUBAGENT_ITERATIONS,
                minimum=1,
                maximum=MAX_INVESTIGATION_LOOPS,
            ),
            max_parallel_subagents=reader.integer(
                "max_parallel_subagents",
                MAX_PARALLEL_SUBAGENTS,
                minimum=1,
                maximum=MAX_PARALLEL_SUBAGENTS,
            ),
            max_subagent_depth=reader.integer(
                "max_subagent_depth", MAX_SUBAGENT_DEPTH, minimum=0, maximum=MAX_SUBAGENT_DEPTH
            ),
            tool_budget=reader.integer("tool_budget", DEFAULT_TOOL_BUDGET, minimum=1),
        )

    def prompt_for(self, role: str) -> str:
        """Return the system prompt for ``role``, falling back to the shipped one.

        The fallback is what makes a zero-configuration deployment work: no
        prompt is stored anywhere until somebody chooses to change one.
        """
        override = self.prompts.get(role, "").strip()
        return override or DEFAULT_RUNTIME_SYSTEM_PROMPT

    def subagent(self, name: str) -> SubAgentConfig | None:
        """Return the sub-agent called ``name``, or ``None``."""
        for subagent in self.subagents:
            if subagent.name == name:
                return subagent
        return None

    def enabled_subagents(self) -> tuple[SubAgentConfig, ...]:
        """Return the sub-agents a run may actually dispatch."""
        return tuple(subagent for subagent in self.subagents if subagent.enabled)


@dataclass(frozen=True, slots=True)
class ModelSelection:
    """The provider and model one role runs on."""

    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL_ID

    @classmethod
    def of(cls, reader: Reader) -> ModelSelection:
        """Return the selection ``reader`` describes."""
        reader.close(("provider", "model"))
        return cls(
            provider=reader.string("provider", DEFAULT_PROVIDER, allowed=SUPPORTED_PROVIDERS),
            model=reader.string("model", DEFAULT_MODEL_ID),
        )


@dataclass(frozen=True, slots=True)
class ModelsConfig:
    """Which provider and model each role resolves to.

    A role nobody configured resolves to the deployment default rather than
    failing: an investigation that cannot start is worse than one that starts on
    the default model and records which one in its trace.
    """

    roles: Mapping[str, ModelSelection] = field(default_factory=dict)

    @classmethod
    def of(cls, reader: Reader) -> ModelsConfig:
        """Return the model bindings ``reader`` describes."""
        reader.close(MODELS_FIELDS)
        return cls(
            roles={
                role: ModelSelection.of(reader.section(role))
                for role in MODEL_ROLES
                if reader.has(role)
            }
        )

    def for_role(self, role: str) -> ModelSelection:
        """Return what ``role`` runs on, or the deployment default."""
        return self.roles.get(role, ModelSelection())

    def bound_roles(self) -> tuple[str, ...]:
        """Return the roles this configuration binds explicitly, in role order."""
        return tuple(role for role in MODEL_ROLES if role in self.roles)


def _report_duplicate_names(reader: Reader, subagents: tuple[SubAgentConfig, ...]) -> None:
    """Record an error per repeated sub-agent name.

    Two sub-agents with one name is a dispatch that reaches whichever the merge
    happened to order last, which is not a decision anybody made.
    """
    seen: set[str] = set()
    for subagent in subagents:
        if subagent.name and subagent.name in seen:
            reader.fail("subagents", f"declares {subagent.name!r} more than once")
        seen.add(subagent.name)


__all__ = [
    "AGENTS_FIELDS",
    "AgentsConfig",
    "MODELS_FIELDS",
    "ModelSelection",
    "ModelsConfig",
    "SUBAGENT_FIELDS",
    "SubAgentConfig",
]
