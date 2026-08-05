"""SC-007. A benchmark invoked with the experimental runtime fails.

The claim this protects is the product's differentiator: trajectory quality is
measured against golden trajectories and a regression fails CI. That comparison
is only valid if every scenario ran the same way, and the cheapest way for it to
stop being valid is for somebody to leave an environment variable set.
"""

from __future__ import annotations

import pytest

from config.constants.investigation import (
    NINJASRE_RUNTIME_ENV,
    RUNTIME_CANONICAL,
    RUNTIME_CLAUDE_SDK,
)
from core.agent.adapters.claude_sdk import UNENFORCEABLE_GUARDRAILS, ClaudeAgentSdkRuntime
from core.agent.guard import (
    NonCanonicalRuntimeError,
    experimental_runtime_requested,
    require_canonical_runtime,
    selected_runtime_name,
)
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus, Runtime
from tests.unit.core.agent.conftest import ScriptedLLM, text_turn

pytestmark = pytest.mark.unit


def _canonical() -> ReActLoop:
    return ReActLoop(llm=ScriptedLLM([text_turn("done")]))


# --- the guard ------------------------------------------------------------------


def test_the_canonical_loop_passes_the_guard() -> None:
    loop = _canonical()

    assert require_canonical_runtime(loop, context="the scenario benchmark") is loop


def test_a_benchmark_invoked_with_the_adapter_fails() -> None:
    """SC-007."""
    with pytest.raises(NonCanonicalRuntimeError, match="scenario benchmark"):
        require_canonical_runtime(ClaudeAgentSdkRuntime(), context="the scenario benchmark")


def test_the_failure_says_how_to_fix_it() -> None:
    with pytest.raises(NonCanonicalRuntimeError) as raised:
        require_canonical_runtime(ClaudeAgentSdkRuntime(), context="the trajectory evaluation")

    assert NINJASRE_RUNTIME_ENV in str(raised.value)


def test_the_guard_reads_a_declared_property_rather_than_a_class_name() -> None:
    """A name check would pass the day somebody subclassed the adapter, and it
    would pass silently."""

    class Renamed(ClaudeAgentSdkRuntime):
        @property
        def name(self) -> str:
            return "ninjasre.react"

    with pytest.raises(NonCanonicalRuntimeError):
        require_canonical_runtime(Renamed(), context="the scenario benchmark")


# --- selection ------------------------------------------------------------------


def test_the_canonical_runtime_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NINJASRE_RUNTIME_ENV, raising=False)

    assert selected_runtime_name() == RUNTIME_CANONICAL
    assert not experimental_runtime_requested()


def test_an_experimental_runtime_needs_an_explicit_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(NINJASRE_RUNTIME_ENV, RUNTIME_CLAUDE_SDK)

    assert selected_runtime_name() == RUNTIME_CLAUDE_SDK
    assert experimental_runtime_requested()


def test_an_unrecognised_selection_reads_as_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo must not silently select something else."""
    monkeypatch.setenv(NINJASRE_RUNTIME_ENV, "clude-sdk")

    assert selected_runtime_name() == RUNTIME_CANONICAL


# --- the adapter ----------------------------------------------------------------


def test_the_adapter_satisfies_the_port_without_inheriting_it() -> None:
    assert isinstance(ClaudeAgentSdkRuntime(), Runtime)


def test_the_adapter_declares_itself_experimental() -> None:
    assert ClaudeAgentSdkRuntime().is_canonical is False
    assert _canonical().is_canonical is True


def test_the_adapter_lists_the_guardrails_it_cannot_enforce() -> None:
    """T050. The list is data as well as prose so a console can show it to an
    operator before they select it."""
    listed = ClaudeAgentSdkRuntime().unenforceable_guardrails

    assert listed == UNENFORCEABLE_GUARDRAILS
    joined = " ".join(listed).lower()
    for gap in ("iteration ceiling", "stagnation", "duplicate", "context budget", "masking"):
        assert gap in joined


def test_the_adapters_docstring_names_the_articles_it_cannot_satisfy() -> None:
    """Approval gating and masking are the two that matter most, and a reader
    should not have to infer them from a list of mechanisms."""
    import core.agent.adapters.claude_sdk as adapter

    assert adapter.__doc__ is not None
    assert "Articles III and IV cannot be enforced" in adapter.__doc__


async def test_the_adapter_reports_a_missing_extra_as_a_result_not_an_exception() -> None:
    """A caller that selected it should learn that in the same shape every other
    failure arrives in."""
    result = await ClaudeAgentSdkRuntime().run(RunRequest(objective="anything"))

    assert result.status is RunStatus.FAILED
    assert "claude_agent_sdk" in result.failure
    assert NINJASRE_RUNTIME_ENV in result.failure


def test_the_vendor_package_is_not_a_dependency() -> None:
    """Provider neutrality: a deployment with no permitted egress installs no
    vendor packages and is still fully functional."""
    import tomllib
    from pathlib import Path

    manifest = tomllib.loads(
        (Path(__file__).resolve().parents[4] / "pyproject.toml").read_text(encoding="utf-8")
    )
    required = manifest["project"].get("dependencies", [])

    assert not any("claude" in str(entry).lower() for entry in required)
