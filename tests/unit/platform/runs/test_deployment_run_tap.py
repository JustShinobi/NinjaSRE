"""The run broker, tapped once: four kinds forwarded, eleven held back.

`DeploymentPublishingRunEventBroker` stands in for the plain `RunEventBroker`
at the one place `gateway/http/asgi.py` builds it. No call site that already
holds a `broker` and calls `.publish()` on it changes; this proves the swap
alone is what makes the four run kinds FR-003 names reach the deployment
channel, and the other eleven `TraceEventKind` values never do.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.runs.deployment import (
    DeploymentEventBroker,
    DeploymentEventKind,
    DeploymentPublishingRunEventBroker,
    DeploymentScope,
    deployment_kind_of,
)
from platform.runs.events import RunEvent, TraceEventKind

_NOW = datetime(2026, 8, 27, tzinfo=UTC)

_FORWARDED = {
    TraceEventKind.RUN_STARTED: DeploymentEventKind.RUN_STARTED,
    TraceEventKind.STAGE_COMPLETED: DeploymentEventKind.STAGE_COMPLETED,
    TraceEventKind.ATTENTION_CHANGED: DeploymentEventKind.ATTENTION_CHANGED,
    TraceEventKind.RUN_FINISHED: DeploymentEventKind.RUN_FINISHED,
}


@pytest.mark.parametrize(
    ("kind", "expected"), sorted(_FORWARDED.items(), key=lambda pair: pair[0].value)
)
def test_each_of_the_four_named_kinds_translates(
    kind: TraceEventKind, expected: DeploymentEventKind
) -> None:
    event = RunEvent(run_id="r1", kind=kind, sequence=1, occurred_at=_NOW)
    assert deployment_kind_of(event) is expected


@pytest.mark.parametrize(
    "kind",
    sorted(set(TraceEventKind) - set(_FORWARDED), key=lambda item: item.value),
)
def test_every_other_kind_translates_to_nothing(kind: TraceEventKind) -> None:
    event = RunEvent(run_id="r1", kind=kind, sequence=1, occurred_at=_NOW)
    assert deployment_kind_of(event) is None


def test_the_eleven_and_the_four_together_are_the_whole_enum() -> None:
    assert len(_FORWARDED) == 4
    assert len(set(TraceEventKind) - set(_FORWARDED)) == 11


async def test_the_tapped_broker_still_delivers_to_its_own_run_subscribers() -> None:
    """No call site of the run broker's own API changes — it still fans out per run."""
    from platform.runs.cursor import Cursor

    broker = DeploymentPublishingRunEventBroker(deployment_events=None)
    subscription = broker.attach("r1", cursor=Cursor.start_of("r1"))

    await broker.publish(
        RunEvent(run_id="r1", kind=TraceEventKind.RUN_STARTED, sequence=1, occurred_at=_NOW)
    )

    delivered = [event async for event in subscription.drain()]
    assert [event.kind for event in delivered] == [TraceEventKind.RUN_STARTED]


async def test_a_forwarded_kind_reaches_the_deployment_channel_with_only_the_run_id() -> None:
    deployment_events = DeploymentEventBroker()
    broker = DeploymentPublishingRunEventBroker(deployment_events=deployment_events)
    deployment_subscription, _ = deployment_events.attach()

    await broker.publish(
        RunEvent(
            run_id="r1",
            kind=TraceEventKind.STAGE_COMPLETED,
            sequence=1,
            occurred_at=_NOW,
            payload={"stage": "diagnose", "finding": "a secret-shaped sentence"},
        )
    )

    delivered = [event async for event in deployment_subscription.drain()]
    assert len(delivered) == 1
    assert delivered[0].scope is DeploymentScope.RUN
    assert delivered[0].kind is DeploymentEventKind.STAGE_COMPLETED
    assert dict(delivered[0].payload) == {"run_id": "r1"}


async def test_an_unforwarded_kind_never_reaches_the_deployment_channel() -> None:
    deployment_events = DeploymentEventBroker()
    broker = DeploymentPublishingRunEventBroker(deployment_events=deployment_events)
    deployment_subscription, _ = deployment_events.attach()

    await broker.publish(
        RunEvent(run_id="r1", kind=TraceEventKind.CAPABILITY_CALLED, sequence=1, occurred_at=_NOW)
    )

    delivered = [event async for event in deployment_subscription.drain()]
    assert delivered == []


async def test_a_broker_with_no_deployment_channel_attached_still_works() -> None:
    """A tapped broker built with `deployment_events=None` behaves as a plain one."""
    broker = DeploymentPublishingRunEventBroker(deployment_events=None)
    await broker.publish(
        RunEvent(run_id="r1", kind=TraceEventKind.RUN_STARTED, sequence=1, occurred_at=_NOW)
    )
    # No assertion beyond "did not raise" — there is nowhere for a deployment
    # event to be observed when none was ever attached.
