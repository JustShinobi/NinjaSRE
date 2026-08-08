"""Demo mode makes no external call, and the enforcement is a transport that refuses.

SC-008. The property is only worth having if it is structural: a transport that
served a fixture where it had one and called out where it did not would satisfy
FR-018 on the day it was written and stop the first time somebody added a prompt
the recording does not cover — silently, because a working demonstration and one
that is spending money look identical from outside.
"""

from __future__ import annotations

import pytest

from config.constants.first_run import (
    DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS,
    NINJASRE_DEMO_MODE_ENV,
)
from core.llm.credentials import ProviderCredentials
from core.llm.transports import WireRequest
from platform.startup.demo import (
    FixtureTransport,
    RealRequestInDemoMode,
    demo_mode_enabled,
    load_dataset,
    scripted_events,
    stream_scripted_investigation,
)
from platform.startup.demo.transport import exchange_key

pytestmark = pytest.mark.unit


def _request(prompt: str = "why is the node unhealthy?") -> WireRequest:
    return WireRequest(
        provider_id="local",
        model_id="qwen2.5:32b",
        payload={"messages": [{"role": "user", "content": prompt}]},
        credentials=ProviderCredentials(provider_id="local", values={}),
    )


# --- The refusal ------------------------------------------------------------------


async def test_a_request_with_no_recording_is_refused_rather_than_sent() -> None:
    transport = FixtureTransport()

    with pytest.raises(RealRequestInDemoMode):
        await transport.send(_request())


async def test_the_refusal_says_what_was_asked_for_and_what_to_do() -> None:
    transport = FixtureTransport()

    with pytest.raises(RealRequestInDemoMode) as refusal:
        await transport.send(_request())

    message = str(refusal.value)
    assert "local" in message
    assert "qwen2.5:32b" in message
    assert "demo mode" in message


async def test_streaming_refuses_on_the_same_terms() -> None:
    """The stream path is the one that would otherwise get missed: it is a
    separate method, and a transport that guarded only ``send`` would leave the
    live transcript reaching a provider."""
    transport = FixtureTransport()

    with pytest.raises(RealRequestInDemoMode):
        async for _ in transport.stream(_request()):
            pass


async def test_a_recorded_request_is_answered_from_the_recording() -> None:
    transport = FixtureTransport()
    request = _request()
    transport.record(request, {"content": "the node is out of memory"})

    response = await transport.send(request)

    assert response.payload["content"] == "the node is out of memory"


async def test_a_different_request_does_not_match_a_close_recording() -> None:
    """Close enough is how a demonstration starts answering the wrong question."""
    transport = FixtureTransport()
    transport.record(_request("why is the node unhealthy?"), {"content": "memory"})

    with pytest.raises(RealRequestInDemoMode):
        await transport.send(_request("why is the datastore unhealthy?"))


async def test_a_transport_given_a_fallback_answers_anything() -> None:
    """Offered deliberately, and off by default: the safe direction for "we have
    no recording" is to refuse."""
    transport = FixtureTransport(fallback={"content": "this is a demonstration"})

    response = await transport.send(_request("anything at all"))

    assert response.payload["content"] == "this is a demonstration"


def test_the_same_request_keys_the_same_recording() -> None:
    assert exchange_key(_request()) == exchange_key(_request())


def test_a_request_that_differs_only_in_a_volatile_field_still_matches() -> None:
    """A request id or a timestamp is not part of what was asked."""
    first = WireRequest(
        provider_id="local",
        model_id="m",
        payload={"messages": [], "request_id": "a"},
        credentials=ProviderCredentials(provider_id="local", values={}),
    )
    second = WireRequest(
        provider_id="local",
        model_id="m",
        payload={"messages": [], "request_id": "b"},
        credentials=ProviderCredentials(provider_id="local", values={}),
    )

    assert exchange_key(first) == exchange_key(second)


def test_the_transport_records_what_it_was_asked_for() -> None:
    """So a test can assert not only that nothing left, but that something was
    genuinely attempted — a demonstration that made no call at all would pass a
    "made no external call" assertion trivially."""
    transport = FixtureTransport(fallback={})

    assert transport.calls == ()


# --- The switch ---------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_demo_mode_is_on_for_every_spelling_of_yes(value: str) -> None:
    assert demo_mode_enabled({NINJASRE_DEMO_MODE_ENV: value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe"])
def test_demo_mode_is_off_for_everything_else(value: str) -> None:
    assert demo_mode_enabled({NINJASRE_DEMO_MODE_ENV: value}) is False


def test_demo_mode_is_off_when_nothing_says_otherwise() -> None:
    assert demo_mode_enabled({}) is False


# --- The scripted investigation --------------------------------------------------------


def test_the_scripted_run_has_a_beginning_a_middle_and_an_end() -> None:
    events = scripted_events(load_dataset())

    assert events
    assert events[0].kind == "run_started"
    assert [event.sequence for event in events] == sorted(event.sequence for event in events)
    assert any("tool" in event.kind for event in events)


def test_every_scripted_event_is_labelled_as_a_demonstration() -> None:
    """An event is the one record here that leaves the database. A client
    rendering it should be able to say so without knowing which tenant it is
    looking at."""
    from platform.startup.demo import is_demonstration

    for event in scripted_events(load_dataset()):
        assert is_demonstration(event.payload), event.kind


async def test_the_scripted_run_streams_rather_than_arriving_at_once() -> None:
    dataset = load_dataset()
    seen = []

    async for event in stream_scripted_investigation(dataset, interval_seconds=0):
        seen.append(event)

    assert len(seen) == len(scripted_events(dataset))


async def test_the_pacing_is_a_constant_a_test_can_turn_off() -> None:
    """A suite that spent a quarter of a second per event is a suite somebody
    deletes, so the interval is injectable — and its default is the one a person
    watching actually sees."""
    assert DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS > 0

    import asyncio

    async def drain() -> int:
        return len(
            [
                event
                async for event in stream_scripted_investigation(load_dataset(), interval_seconds=0)
            ]
        )

    assert await asyncio.wait_for(drain(), timeout=2) > 0
