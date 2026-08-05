"""SC-001. A pathological run terminates on all nine providers.

The claim Article II makes is not "the loop usually stops". It is that a run
designed to go forever stops within a bound, whichever provider is configured —
because a bound that holds on one vendor's wire shape and not another's is not a
bound, it is a coincidence.

Both directions are asserted. A model that never concludes must stop; a model
that does conclude must not be stopped early by the same machinery.
"""

from __future__ import annotations

import pytest

from config.constants.investigation import MAX_INVESTIGATION_LOOPS
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.turn import GuardrailActionKind
from core.llm.client import ProviderClient
from tests.contract.agent.conftest import LIST_PODS

pytestmark = pytest.mark.contract


async def test_a_run_that_would_never_stop_terminates(looping_client: ProviderClient) -> None:
    """SC-001, on every provider, from that provider's own wire shape."""
    loop = ReActLoop(llm=looping_client, tools=(LIST_PODS,))

    result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

    assert result.iterations <= MAX_INVESTIGATION_LOOPS
    assert result.session.status.is_terminal
    assert result.status in {RunStatus.COMPLETED, RunStatus.PARTIAL}


async def test_the_stagnation_breaker_is_what_stops_it(
    looping_client: ProviderClient,
) -> None:
    """The cassette repeats one call with one set of arguments, so this is the
    duplicate-only case rather than the ceiling case — and the breaker firing
    well inside the ceiling is the whole reason it exists."""
    loop = ReActLoop(llm=looping_client, tools=(LIST_PODS,))

    result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

    kinds = {action.kind for turn in result.turns for action in turn.guardrail_actions}
    assert GuardrailActionKind.TOOL_ACCESS_STRIPPED in kinds
    assert result.iterations < MAX_INVESTIGATION_LOOPS


async def test_the_recorded_tool_call_actually_executes(
    concluding_client: ProviderClient,
) -> None:
    """A termination claim is worth nothing if the loop never got as far as
    running what the provider asked for."""
    loop = ReActLoop(llm=concluding_client, tools=(LIST_PODS,))

    result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

    called = [execution.capability for turn in result.turns for execution in turn.executions]
    assert called == ["kubernetes_list_pods"]
    assert result.evidence


async def test_a_model_that_concludes_is_not_cut_short(
    concluding_client: ProviderClient,
) -> None:
    loop = ReActLoop(llm=concluding_client, tools=(LIST_PODS,))

    result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

    assert result.status is RunStatus.COMPLETED
    assert result.iterations == 2
    assert result.answer
