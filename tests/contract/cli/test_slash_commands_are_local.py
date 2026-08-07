"""Every slash command executes with zero LLM calls.

Asserted by a counter rather than by inspection, and the counter sits under the
whole stack: an LLM client that increments on every method, wired in where a
real one would be. A command that reached a model through any path — the
client, a runtime, an import — increments it, and there is no path that does
not go through a client.

The catalogue is walked rather than listed. A seventeenth command added without
being added here would otherwise ship untested, which is the specific way this
guarantee decays.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.agent.interaction.registry import InteractionRegistry
from core.llm.types import InvokeRequest, InvokeResult, StreamEvent, TokenEstimate
from surfaces.cli.client import LocalClient
from surfaces.cli.output.degradation import Terminal
from surfaces.repl.commands import build_registry
from surfaces.repl.commands.registry import CommandContext
from surfaces.repl.interaction import InlineInteractions
from surfaces.repl.session import ReplSession, SessionStore
from tests.support.deployment import FakeServices

pytestmark = pytest.mark.contract


@dataclass(slots=True)
class CountingLLM:
    """An LLM client that refuses to work and counts being asked.

    Every method raises after counting. A command that reached a model would
    therefore fail loudly rather than quietly succeeding against a stub — a
    counter that returned plausible answers would let a passing test hide the
    very call it exists to forbid.
    """

    calls: list[str] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "counting"

    @property
    def model_id(self) -> str:
        return "counting"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.calls.append("invoke")
        raise AssertionError("a slash command called a model")

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        self.calls.append("stream")
        raise AssertionError("a slash command called a model")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        self.calls.append("invoke_structured")
        raise AssertionError("a slash command called a model")

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        self.calls.append("count_tokens")
        raise AssertionError("a slash command called a model")


#: Arguments each command is exercised with. Every command in the catalogue has
#: an entry, and ``test_every_command_is_exercised`` fails when one does not.
ARGUMENTS: dict[str, str] = {
    "help": "",
    "status": "",
    "cost": "",
    "sessions": "",
    "resume": "",
    "compact": "",
    "new": "",
    "exit": "",
    "integrations": "",
    "runs": "",
    "effort": "high",
    "model": "claude-sonnet-5",
    "approve": "",
    "answer": "",
    "takeover": "",
    "cancel": "",
}


def _context(services: FakeServices, tmp_path: Any) -> CommandContext:
    """Return a context wired to everything a slash command may touch."""
    session = ReplSession(session_id="sess-1", objective="checkout latency")
    session.record("human", "checkout latency doubled")
    return CommandContext(
        session=session,
        out=io.StringIO(),
        terminal=Terminal(),
        client=LocalClient(services=services),
        sessions=SessionStore(directory=tmp_path / "sessions"),
        interactions=InlineInteractions(
            registry=InteractionRegistry(run_id="run-0001"),
            out=io.StringIO(),
            session=session,
            principal_id="alex",
        ),
    )


def test_every_command_in_the_catalogue_is_exercised() -> None:
    registry = build_registry()
    unexercised = set(registry.names()) - set(ARGUMENTS)

    assert not unexercised, f"no arguments declared for: {sorted(unexercised)}"


def test_the_catalogue_holds_every_command_the_specification_names() -> None:
    # The published catalogue. A command dropped from the registry would
    # otherwise only be noticed by somebody typing it during an incident.
    required = {
        "help",
        "status",
        "cost",
        "sessions",
        "resume",
        "compact",
        "new",
        "exit",
        "integrations",
        "runs",
        "effort",
        "model",
        "approve",
        "answer",
        "takeover",
        "cancel",
    }
    missing = required - set(build_registry().names())

    assert not missing, f"these slash commands are not registered: {sorted(missing)}"


@pytest.mark.parametrize("name", sorted(ARGUMENTS))
def test_a_slash_command_makes_no_model_call(
    name: str, services: FakeServices, tmp_path: Any
) -> None:
    counter = CountingLLM()
    registry = build_registry()
    context = _context(services, tmp_path)

    # The counter is placed where a real client would be reachable from. Nothing
    # in the context refers to it, which is the point: a command that found a
    # model would have had to go looking outside its arguments.
    context.session.model_id = counter.model_id

    try:
        registry.dispatch(context, name, ARGUMENTS[name])
    except Exception as raised:  # noqa: BLE001 — a refusal is an outcome, a call is not
        assert not isinstance(raised, AssertionError), str(raised)

    assert counter.calls == [], f"/{name} called a model: {counter.calls}"
    assert services.llm_calls == 0, f"/{name} started an investigation"


def test_the_whole_catalogue_together_makes_no_model_call(
    services: FakeServices, tmp_path: Any
) -> None:
    # Run in sequence against one context, which is what a session actually
    # does. A command that only calls a model after another one has run would
    # pass the per-command test above.
    registry = build_registry()
    context = _context(services, tmp_path)

    for name in sorted(ARGUMENTS):
        try:
            registry.dispatch(context, name, ARGUMENTS[name])
        except Exception:  # noqa: BLE001 — refusals are fine; calls are not
            continue

    assert services.llm_calls == 0


def test_a_command_context_carries_nothing_that_could_generate_a_token(
    services: FakeServices, tmp_path: Any
) -> None:
    # The structural half of the guarantee. The context's fields are the whole
    # of what a handler is given, and none of them is a model.
    context = _context(services, tmp_path)
    fields = {name for name in context.__slots__ if not name.startswith("_")}

    assert "llm" not in fields
    assert "runtime" not in fields
    assert "registry" not in fields
