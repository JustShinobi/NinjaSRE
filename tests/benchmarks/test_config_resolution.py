"""SC-003: what an effective-config resolution costs on a real hierarchy.

Resolution sits on the investigation path once per run. If it were expensive it
would be expensive on every incident, and the symptom — a few hundred
milliseconds before the first tool call — is the kind nobody attributes to
configuration.

The hierarchy is four levels and the configuration is large: forty capability
overrides, twenty integrations, eight sub-agents, and a system prompt at each
level, which is more than any real deployment carries and therefore the right
thing to measure. The merge is the cost, so the benchmark drives the pure path
rather than the database — a number that included the fake's deep copy would be
measuring the test double.

Both budgets are set well above what the current implementation spends. A
failure here means the merge has started doing something quadratic, not that CI
was busy.
"""

from __future__ import annotations

import time

import pytest

from config.constants.config_service import (
    EFFECTIVE_CONFIG_CACHED_BUDGET_MS,
    EFFECTIVE_CONFIG_COLD_BUDGET_MS,
)
from platform.config_service.document import NodeDocument
from platform.config_service.effective import (
    EffectiveConfigCache,
    HierarchyVersion,
    build,
)
from platform.persistence.ports import ConfigNode, ConfigNodeKind

pytestmark = [pytest.mark.benchmark]

#: How many times each measurement runs. Enough that a single scheduling hiccup
#: does not decide the result, few enough that the suite stays fast.
REPEATS = 50

LEVELS = ("org", "division", "team", "squad")


def large_settings(level: str) -> dict[str, object]:
    """Return a configuration larger than any real deployment carries."""
    return {
        "agents": {
            "prompts": {"investigator": f"You are investigating for {level}. " * 40},
            "max_iterations": 12,
            "tool_budget": 8,
            "subagents": [
                {
                    "name": f"{level}-specialist-{index}",
                    "description": f"Specialist {index} for {level}",
                    "system_prompt": "Look at one thing and report what you found. " * 10,
                    "capabilities": [f"cap-{index}-{step}" for step in range(6)],
                }
                for index in range(8)
            ],
        },
        "models": {
            role: {"provider": "anthropic", "model": f"model-{level}"}
            for role in ("investigator", "subagent", "intake", "diagnose")
        },
        "capabilities": {
            "disabled": [f"blocked-{level}-{index}" for index in range(40)],
            "parameters": {
                f"cap-{index}": {"limit": index, "window_minutes": 60} for index in range(40)
            },
        },
        "integrations": {
            "active": [
                {
                    "name": f"vendor-{index}",
                    "credential": f"vendor-{index}-{level}",
                    "region": "eu-west-1",
                    "settings": {"page_size": 100, "retries": 3},
                }
                for index in range(20)
            ]
        },
        "policies": {
            "memory": {"read_enabled": True, "write_enabled": True},
            "masking": {
                "level": "strict",
                "custom_patterns": [
                    {"name": f"ticket-{index}", "pattern": f"TICKET-{index}-[0-9]{{4}}"}
                    for index in range(10)
                ],
            },
        },
        "surfaces": {
            "channels": [
                {"platform": "slack", "channel": f"#{level}-{index}"} for index in range(10)
            ]
        },
    }


def four_level_chain() -> tuple[ConfigNode, ...]:
    """Return a four-level chain, each level carrying a large configuration."""
    nodes: list[ConfigNode] = []
    for depth, level in enumerate(LEVELS):
        document = NodeDocument.of(
            large_settings(level),
            locked=("policies.masking.level",) if depth == 0 else (),
        )
        nodes.append(
            ConfigNode(
                node_id=level,
                kind=ConfigNodeKind.ORGANISATION if depth == 0 else ConfigNodeKind.TEAM,
                name=level,
                parent_id=LEVELS[depth - 1] if depth else None,
                values=document.to_values(),
                version=depth + 1,
            )
        )
    return tuple(nodes)


def milliseconds_per_call(work: object, repeats: int = REPEATS) -> float:
    """Return the mean wall-clock cost of ``work`` in milliseconds."""
    assert callable(work)
    work()  # Warm the import and constant-folding paths, then measure.
    started = time.perf_counter()
    for _ in range(repeats):
        work()
    return (time.perf_counter() - started) * 1000.0 / repeats


def test_a_cold_resolution_on_a_four_level_hierarchy_stays_within_budget() -> None:
    """SC-003, the merge and the schema construction on top of it."""
    chain = four_level_chain()

    spent = milliseconds_per_call(lambda: build("squad", chain))

    assert spent < EFFECTIVE_CONFIG_COLD_BUDGET_MS, (
        f"a cold resolution took {spent:.2f}ms against a budget of "
        f"{EFFECTIVE_CONFIG_COLD_BUDGET_MS}ms"
    )


def test_a_cached_resolution_is_two_orders_of_magnitude_cheaper() -> None:
    """If it is not, the cache is not earning the invalidation risk it carries."""
    chain = four_level_chain()
    version = HierarchyVersion.of(chain)
    cache = EffectiveConfigCache()
    cache.put(build("squad", chain, version))

    spent = milliseconds_per_call(lambda: cache.get("squad", version))

    assert spent < EFFECTIVE_CONFIG_CACHED_BUDGET_MS, (
        f"a cached resolution took {spent:.4f}ms against a budget of "
        f"{EFFECTIVE_CONFIG_CACHED_BUDGET_MS}ms"
    )


def test_the_resolution_being_measured_is_a_real_one() -> None:
    """A benchmark over an empty merge would pass and mean nothing."""
    resolved = build("squad", four_level_chain())

    # Lists are single leaves — that is what "lists replace entirely" means —
    # so the count is of merged *fields*, not of the entries inside them.
    assert len(resolved.provenance) > 80
    assert resolved.value_at("policies.masking.level") == "strict"
    assert resolved.locked_by("policies.masking.level") == "org"
    assert len(resolved.config.agents.subagents) == 8
