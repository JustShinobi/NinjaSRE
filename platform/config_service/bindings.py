"""Filling the seams every other feature left for this one.

Memory, strategy, knowledge, masking, guardrails, and the sub-agent registry all
shipped with a ``for_team`` constructor or a source port and a docstring saying
the configuration service would fill it. This module is that filling, and it is
one module rather than a method on each because the property worth protecting is
that they are derived from *one* resolution.

Wiring them separately at each call site is how a deployment ends up with an
ablation that switched topology off in the query path and left the guidance
paragraph in the prompt telling the agent to query a graph it may not query.
``RuntimeBindings.of`` takes one ``EffectiveConfig`` and produces all of them, so
they cannot disagree about which team they are configuring.

**A sub-agent the configuration declares badly is dropped, not raised on.**
``SubAgent`` validates in its constructor — a specialist with no capabilities
and no domain would run with the parent's whole catalogue, which is not a
specialist — and a configuration that produced one would otherwise make the
whole investigation fail to start. Validation refused that document at write, so
reaching here means the document predates a schema change or was written
directly; dropping the entry and running with the rest is the behaviour that
still investigates the incident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from core.agent.subagents.definition import StaticSubAgents, SubAgent, default_subagent_source
from platform.config_service.effective import EffectiveConfig
from platform.config_service.guidance import OperatingContextGuidance
from platform.config_service.schema.agents import AgentsConfig, ModelSelection
from platform.config_service.schema.policies import GUARDRAIL_MODE_OBSERVING, PoliciesConfig
from platform.config_service.schema.root import RootConfig
from platform.knowledge.policy import KnowledgePolicy
from platform.masking.policy import CustomPattern, MaskingPolicy
from platform.memory.policy import MemoryPolicy
from platform.memory.strategy.policy import StrategyPolicy
from platform.observability.logging import get_logger
from platform.trust_controls import TrustControls

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeBindings:
    """Everything one run needs from configuration, derived from one resolution."""

    node_id: str
    config: RootConfig = field(default_factory=RootConfig)
    memory: MemoryPolicy = field(default_factory=MemoryPolicy)
    strategy: StrategyPolicy = field(default_factory=StrategyPolicy)
    knowledge: KnowledgePolicy = field(default_factory=KnowledgePolicy)
    trust: TrustControls = field(default_factory=TrustControls)
    subagents: StaticSubAgents = field(default_factory=StaticSubAgents)
    operating_context: OperatingContextGuidance = field(default_factory=OperatingContextGuidance)

    @classmethod
    def of(
        cls, effective: EffectiveConfig, *, guardrail_rules_path: Path | None = None
    ) -> RuntimeBindings:
        """Return every runtime binding ``effective`` implies."""
        config = effective.config
        return cls(
            node_id=effective.node_id,
            config=config,
            memory=memory_policy(config.policies),
            strategy=strategy_policy(config.policies),
            knowledge=knowledge_policy(config.policies),
            trust=trust_controls(config.policies, rules_path=guardrail_rules_path),
            subagents=subagent_source(config.agents),
            operating_context=OperatingContextGuidance.of(config.agents),
        )

    def model_for(self, role: str) -> ModelSelection:
        """Return the provider and model ``role`` runs on."""
        return self.config.models.for_role(role)

    def prompt_for(self, role: str) -> str:
        """Return the system prompt ``role`` runs with, shipped default included."""
        return self.config.agents.prompt_for(role)

    def system_prompt_for(self, role: str) -> str:
        """Return what ``role`` is actually sent: that prompt, plus the operating context.

        What the console previews and what the run composes, from one
        resolution. The hook does the appending for a session that runs through
        the loop; this is the same string for a caller that needs it before a
        session exists — and it is the same function underneath, so the two
        cannot drift.
        """
        return self.config.agents.system_prompt_for(role)

    def integration_names(self) -> tuple[str, ...]:
        """Return the integrations this team has connected, in declared order."""
        return self.config.integrations.enabled_names()

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace records about the configuration it ran under.

        The node is part of it. An ablation table over four teams that could not
        say which team produced which row would be four unlabelled columns.
        """
        return {"config_node": self.node_id, **dict(self.config.trace_summary())}


def memory_policy(policies: PoliciesConfig) -> MemoryPolicy:
    """Return the memory switches ``policies`` sets (T049)."""
    return MemoryPolicy.for_team(
        read_enabled=policies.memory.read_enabled,
        write_enabled=policies.memory.write_enabled,
    )


def strategy_policy(policies: PoliciesConfig) -> StrategyPolicy:
    """Return the strategy-synthesis switch ``policies`` sets (T049)."""
    return StrategyPolicy.for_team(enabled=policies.strategy.enabled)


def knowledge_policy(policies: PoliciesConfig) -> KnowledgePolicy:
    """Return the topology and knowledge-base switches ``policies`` sets (T049)."""
    return KnowledgePolicy(
        topology_enabled=policies.knowledge.topology_enabled,
        knowledge_enabled=policies.knowledge.knowledge_base_enabled,
    )


def trust_controls(policies: PoliciesConfig, *, rules_path: Path | None = None) -> TrustControls:
    """Return the masking and guardrail controls ``policies`` sets (T049).

    Observe-only guardrails become an audit-only engine, which downgrades every
    action and alters nothing. There is no configuration that removes the
    engine, because the constitution's claim is that it cannot be removed from
    the boundary.
    """
    controls = TrustControls.for_team(
        level=policies.masking.level,
        custom_patterns=[
            CustomPattern(name=pattern.name, pattern=pattern.pattern)
            for pattern in policies.masking.custom_patterns
        ],
        rules_path=rules_path,
    )
    return TrustControls(
        policy=controls.policy,
        rules=controls.rules,
        masking_enabled=policies.masking.enabled,
        guardrails_enabled=policies.guardrails.mode != GUARDRAIL_MODE_OBSERVING,
    )


def subagent_source(agents: AgentsConfig) -> StaticSubAgents:
    """Return the sub-agent registry ``agents`` declares (T050).

    A team that declares none gets the shipped six. That is not a fallback so
    much as the whole design: the defaults are six *kinds* of looking rather
    than six vendors, and a team with nothing to add should not have to restate
    them to get them.
    """
    declared = agents.enabled_subagents()
    if not declared:
        return StaticSubAgents(subagents=default_subagent_source().definitions())

    built: list[SubAgent] = []
    for entry in declared:
        try:
            built.append(
                SubAgent(
                    name=entry.name,
                    description=entry.description or f"The {entry.name} specialist.",
                    capabilities=entry.capabilities,
                    max_iterations=entry.max_iterations,
                    returns=entry.system_prompt,
                )
            )
        except ValueError as rejected:
            logger.warning(
                "configured sub-agent skipped",
                subagent=entry.name,
                reason=str(rejected),
            )
    return StaticSubAgents(subagents=tuple(built))


def masking_policy(policies: PoliciesConfig) -> MaskingPolicy:
    """Return the masking policy alone, for a caller that wants only that."""
    return MaskingPolicy.from_level(
        policies.masking.level,
        custom_patterns=tuple(
            CustomPattern(name=pattern.name, pattern=pattern.pattern)
            for pattern in policies.masking.custom_patterns
        ),
    )


def configured_integrations(config: RootConfig) -> tuple[str, ...]:
    """Return the integration names capability selection should treat as available.

    What ``core.capability.ports.ConfiguredIntegrations`` is constructed from
    (T048). The availability port took a static list because this feature did
    not exist; this is the list.
    """
    return config.integrations.enabled_names()


def bindings_for(
    effective: EffectiveConfig, *, guardrail_rules_path: Path | None = None
) -> RuntimeBindings:
    """Return the bindings for ``effective``. The function form of ``of``."""
    return RuntimeBindings.of(effective, guardrail_rules_path=guardrail_rules_path)


def subagent_names(source: Sequence[SubAgent]) -> tuple[str, ...]:
    """Return the names in ``source``, in declared order."""
    return tuple(each.name for each in source)


__all__ = [
    "RuntimeBindings",
    "bindings_for",
    "configured_integrations",
    "knowledge_policy",
    "masking_policy",
    "memory_policy",
    "strategy_policy",
    "subagent_names",
    "subagent_source",
    "trust_controls",
]
