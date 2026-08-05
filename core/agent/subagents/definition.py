"""A specialist, declared rather than coded.

A sub-agent is four decisions: which capabilities it may call, how long it may
run, what it returns, and when it is worth dispatching. All four are data, so a
team adds a specialist by writing a definition rather than by writing a loop —
which is the property that lets feature 013 make the set configurable per team
without touching this package.

The capability subset accepts names *and* domains. Names are precise and are
what a tuned deployment ends up using; domains are what makes a shipped default
meaningful in a deployment whose vendor integrations nobody has configured yet.
A definition that matched only exact names would be dead weight until somebody
edited it, which is how a default set stops being used at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.investigation import (
    DEFAULT_SUBAGENT_ITERATIONS,
    MAX_INVESTIGATION_LOOPS,
    SUBAGENT_TOKEN_BUDGET_RATIO,
)
from core.agent.subagents.findings import FINDING_SCHEMA
from core.capability.metadata import SKILL_NAME_PATTERN, AppliesWhen
from core.capability.registered import RegisteredTool


@dataclass(frozen=True, slots=True)
class SubAgent:
    """One specialist's declaration.

    ``token_budget_ratio`` is a share of the parent's budget rather than an
    absolute number. A specialist that claimed a fixed token count would either
    starve on a small run or exhaust a large one, and neither failure is visible
    until it happens.
    """

    name: str
    description: str
    capabilities: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    max_iterations: int = DEFAULT_SUBAGENT_ITERATIONS
    token_budget_ratio: float = SUBAGENT_TOKEN_BUDGET_RATIO
    return_schema: Mapping[str, Any] = field(default_factory=lambda: FINDING_SCHEMA)
    applies_when: AppliesWhen = AppliesWhen()
    returns: str = ""

    def __post_init__(self) -> None:
        if not SKILL_NAME_PATTERN.match(self.name):
            raise ValueError(
                f"sub-agent name {self.name!r} does not match "
                f"{SKILL_NAME_PATTERN.pattern} — it must be lowercase and start with a letter"
            )
        if not self.description.strip():
            raise ValueError(f"{self.name}: description must say what this specialist is for")
        if not self.capabilities and not self.domains:
            raise ValueError(
                f"{self.name}: a specialist with no capability subset and no domain would "
                "run with the parent's whole catalogue, which is not a specialist"
            )
        if not 1 <= self.max_iterations <= MAX_INVESTIGATION_LOOPS:
            raise ValueError(
                f"{self.name}: max_iterations must be between 1 and {MAX_INVESTIGATION_LOOPS}, "
                f"got {self.max_iterations}"
            )
        if not 0.0 < self.token_budget_ratio <= 1.0:
            raise ValueError(f"{self.name}: token_budget_ratio must be above 0.0 and at most 1.0")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "domains", tuple(self.domains))

    def subset(self, available: Sequence[RegisteredTool]) -> tuple[RegisteredTool, ...]:
        """Return the capabilities from ``available`` this specialist may call.

        Order follows ``available`` so two dispatches of the same specialist
        against the same catalogue send the same schemas in the same order —
        which is what keeps a trajectory comparison comparing trajectories.
        """
        wanted = set(self.capabilities)
        domains = set(self.domains)
        return tuple(
            registered
            for registered in available
            if registered.name in wanted or registered.metadata.domain in domains
        )


@runtime_checkable
class SubAgentSource(Protocol):
    """Where the configured set of specialists comes from.

    A port because the answer is a team's configuration (feature 013) and the
    runtime cannot wait for it. The static default below is what runs until then,
    and substituting it is also how the evaluation suite ablates sub-agents
    entirely.
    """

    def definitions(self) -> tuple[SubAgent, ...]:
        """Return the specialists this deployment may dispatch."""


@dataclass(frozen=True, slots=True)
class StaticSubAgents:
    """Specialists from a fixed list, as a configuration file supplies them."""

    subagents: tuple[SubAgent, ...] = ()

    def definitions(self) -> tuple[SubAgent, ...]:
        """Return the configured specialists."""
        return self.subagents


# --- the shipped defaults -----------------------------------------------------
#
# Six, chosen because each one is a different *kind* of looking rather than a
# different vendor: what happened in the logs, what the numbers did, what the
# platform thinks its own state is, what changed in the cloud, what changed in
# the code, and what happened last time. A team replaces or extends them through
# the source port; nothing here is hard-coded into the loop.

LOG_ANALYST = SubAgent(
    name="log-analyst",
    description=(
        "Reads logs at volume: aggregates before samples, groups by error signature, "
        "and finds when a pattern started rather than that it exists."
    ),
    domains=("logs", "observability"),
    returns="Error signatures, temporal clusters, and representative samples.",
)

METRICS_ANALYST = SubAgent(
    name="metrics-analyst",
    description=(
        "Reads time series: finds the change point, the series that moved with it, "
        "and the window an anomaly occupies."
    ),
    domains=("metrics", "observability"),
    returns="Change points, correlated series, and anomaly windows.",
)

K8S_DEBUGGER = SubAgent(
    name="k8s-debugger",
    description=(
        "Triages a Kubernetes workload events-first: what the cluster says happened, "
        "then the workload's state, then what was rolled out recently."
    ),
    domains=("kubernetes", "orchestration"),
    returns="Workload state, cluster events, and recent rollouts.",
)

CLOUD_INSPECTOR = SubAgent(
    name="cloud-inspector",
    description=(
        "Reads a cloud control plane: what changed, what state a resource is actually "
        "in, and which quota or limit is being hit."
    ),
    domains=("cloud", "infrastructure"),
    returns="Recent changes, resource state, and quota or limit findings.",
)

CODE_HISTORIAN = SubAgent(
    name="code-historian",
    description=(
        "Correlates the incident window with what shipped: deploy timeline, the diffs "
        "that landed in it, and the pipelines that failed around it."
    ),
    domains=("vcs", "ci", "deployment"),
    returns="Deploy timeline, correlated diffs, and failing pipelines.",
)

MEMORY_RECALLER = SubAgent(
    name="memory-recaller",
    description=(
        "Looks backwards rather than outwards: similar past episodes, the playbooks "
        "that applied, and what the topology says is downstream of this."
    ),
    domains=("memory", "knowledge", "topology"),
    returns="Similar past episodes, applicable playbooks, and blast radius.",
)

#: The default set. Empty capability lists and domain matching are deliberate:
#: these are useful in a deployment that has configured any observability vendor
#: at all, rather than only in one that configured a particular vendor.
DEFAULT_SUBAGENTS: tuple[SubAgent, ...] = (
    LOG_ANALYST,
    METRICS_ANALYST,
    K8S_DEBUGGER,
    CLOUD_INSPECTOR,
    CODE_HISTORIAN,
    MEMORY_RECALLER,
)


def default_subagent_source() -> StaticSubAgents:
    """Return the shipped specialists, as a source the loop can be given."""
    return StaticSubAgents(subagents=DEFAULT_SUBAGENTS)


__all__ = [
    "CLOUD_INSPECTOR",
    "CODE_HISTORIAN",
    "DEFAULT_SUBAGENTS",
    "K8S_DEBUGGER",
    "LOG_ANALYST",
    "MEMORY_RECALLER",
    "METRICS_ANALYST",
    "StaticSubAgents",
    "SubAgent",
    "SubAgentSource",
    "default_subagent_source",
]
