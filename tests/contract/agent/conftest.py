"""Drives the canonical loop against all nine providers, from recorded documents.

The provider contract suite already owns the cassettes — the shapes the vendors
actually return, written down — and reusing them is the point: a termination
claim asserted against a hand-written fake proves the fake terminates. Asserting
it against the same documents the adapters are tested on proves the loop
terminates on what a provider really sends.

``tests/contract/llm`` goes on ``sys.path`` for the cassette module. pytest puts
each conftest's own directory there when there is no package ``__init__.py``,
which covers that directory's tests but not this one's — so it is done
explicitly rather than relied on.
"""

from __future__ import annotations

import sys
from collections import deque
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

_LLM_CONTRACT_DIR = Path(__file__).resolve().parents[1] / "llm"
if str(_LLM_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_LLM_CONTRACT_DIR))

from cassettes import text_response, tool_call_response  # noqa: E402

from config.constants.llm import SUPPORTED_PROVIDERS  # noqa: E402
from core.capability.decorator import tool  # noqa: E402
from core.capability.metadata import EvidenceType, SideEffectLevel  # noqa: E402
from core.capability.registered import RegisteredTool, capability_marker  # noqa: E402
from core.llm.client import ProviderClient  # noqa: E402
from core.llm.credentials import StaticCredentialResolver  # noqa: E402
from core.llm.providers import adapter_for  # noqa: E402
from core.llm.registry import build_default_registry  # noqa: E402
from core.llm.retry import RetryPolicy  # noqa: E402
from core.llm.transports import WireRequest, WireResponse  # noqa: E402

#: Credentials for every provider, so no test is skipped for want of one and
#: nothing here resembles a real key.
_TEST_CREDENTIALS = {
    provider_id: {
        "api_key": "test-key-not-a-real-credential",
        "endpoint": "https://example.invalid",
        "api_version": "2026-01-01",
        "deployment": "test-deployment",
        "region": "eu-west-1",
        "project": "test-project",
        "location": "europe-west1",
        "base_url": "https://example.invalid/v1",
    }
    for provider_id in SUPPORTED_PROVIDERS
}


class LoopingTransport:
    """Replays one document forever, and counts how many times it was asked.

    Forever is the whole fixture. A model that never stops asking for the same
    call is exactly the pathological case the iteration ceiling and the
    stagnation breaker exist for, and a transport that ran out of responses
    would end the run for the wrong reason.
    """

    def __init__(self, documents: Iterable[Mapping[str, Any]], *, final: Mapping[str, Any]) -> None:
        self._documents = deque(documents)
        self._final = final
        self.sent: list[WireRequest] = []

    @property
    def name(self) -> str:
        """Return this transport's identifier."""
        return "looping"

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the next document, repeating the last one indefinitely."""
        self.sent.append(request)
        if self._documents:
            return WireResponse(payload=self._documents.popleft())
        return WireResponse(payload=self._final)

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Yield nothing; the loop does not stream."""
        raise NotImplementedError("the loop does not stream")
        yield {}  # pragma: no cover — makes this an async generator


def build_client(provider_id: str, transport: LoopingTransport) -> ProviderClient:
    """Return a client for ``provider_id`` wired to ``transport``."""

    async def _no_sleep(_seconds: float) -> None:
        return None

    return ProviderClient(
        adapter=adapter_for(provider_id),
        descriptor=build_default_registry().default_for_provider(provider_id),
        transport=transport,
        credentials=StaticCredentialResolver(_TEST_CREDENTIALS),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.001),
        jitter=lambda: 0.0,
        sleeper=_no_sleep,
    )


@tool(
    name="kubernetes_list_pods",
    display_name="List pods",
    description="List the pods in a namespace and their phase.",
    domain="kubernetes",
    evidence_source="kubernetes",
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
def kubernetes_list_pods(namespace: str) -> dict[str, Any]:
    """Return a canned pod listing for ``namespace``.

    Named to match the cassettes' tool call: the point of the fixture is that
    the loop executes what the recorded document asked for.
    """
    return {"namespace": namespace, "pods": [{"name": "checkout-1", "phase": "Running"}]}


def _registration(function: Any) -> RegisteredTool:
    found = capability_marker(function)
    assert found is not None
    return found


LIST_PODS = _registration(kubernetes_list_pods)


@pytest.fixture(params=SUPPORTED_PROVIDERS, name="provider_id")
def _provider_id(request: pytest.FixtureRequest) -> str:
    """Run each contract test against every supported provider."""
    return str(request.param)


@pytest.fixture(name="looping_client")
def _looping_client(provider_id: str) -> ProviderClient:
    """Return a client whose model always asks for the same tool call."""
    return build_client(provider_id, LoopingTransport((), final=tool_call_response(provider_id)))


@pytest.fixture(name="concluding_client")
def _concluding_client(provider_id: str) -> ProviderClient:
    """Return a client that calls a tool once and then answers."""
    return build_client(
        provider_id,
        LoopingTransport((tool_call_response(provider_id),), final=text_response(provider_id)),
    )
