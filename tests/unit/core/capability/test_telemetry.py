"""A trace record is enough to reconstruct the call, or it is decoration.

The test that matters here is the replay. Serialise an invocation, throw the
process away, read the record back, and make the same call again — if that
produces the same result, the trace is genuinely a record of what happened. If
it does not, the trace is a story about what happened, and the difference only
becomes visible during the post-incident review that needed it.

Arguments are filtered on the way in, not on the way out. A secret that reached
the record and was redacted at render time is a secret that was written to the
database.
"""

from __future__ import annotations

import json

import pytest

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import capability_marker
from core.capability.result import CapabilityErrorClass
from core.capability.telemetry import (
    CapabilityInvocation,
    InvocationOutcome,
    filter_arguments,
    record_invocation,
)

pytestmark = pytest.mark.unit


@tool(
    name="replayable",
    display_name="Replayable",
    description="Returns a deterministic value so a replay can be compared.",
    evidence_source="datadog",
    evidence_type=EvidenceType.LOG,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
async def replayable(query: str, limit: int = 10) -> dict[str, object]:
    """Return the arguments it was given, so a replay is checkable."""
    return {"query": query, "limit": limit}


async def test_an_invocation_records_everything_the_contract_names() -> None:
    registered = capability_marker(replayable)
    assert registered is not None

    invocation = await record_invocation(registered, {"query": "status:error", "limit": 5})

    assert invocation.capability == "replayable"
    assert invocation.arguments == {"query": "status:error", "limit": 5}
    assert invocation.outcome is InvocationOutcome.SUCCESS
    assert invocation.duration_seconds >= 0.0
    assert invocation.side_effect_level is SideEffectLevel.READ
    assert invocation.error_class is None


async def test_a_failure_records_its_classification() -> None:
    registered = capability_marker(replayable)
    assert registered is not None

    invocation = await record_invocation(registered, {})

    assert invocation.outcome is InvocationOutcome.FAILURE
    assert invocation.error_class is CapabilityErrorClass.INVALID_ARGUMENTS
    assert invocation.error_message


async def test_a_record_survives_a_round_trip_through_json() -> None:
    """The trace store speaks JSON; anything that does not survive it is lost."""
    registered = capability_marker(replayable)
    assert registered is not None

    invocation = await record_invocation(registered, {"query": "status:error"})
    restored = CapabilityInvocation.from_record(json.loads(json.dumps(invocation.to_record())))

    assert restored == invocation


async def test_a_trace_is_sufficient_to_replay_the_call() -> None:
    """SC-006, stated as the thing it is actually for.

    The replay uses nothing but the record: the capability name and the stored
    arguments. If reconstructing the call needed anything held in the process
    that made it, this would not run.
    """
    registered = capability_marker(replayable)
    assert registered is not None

    original = await registered.invoke({"query": "status:error", "limit": 5})
    invocation = await record_invocation(registered, {"query": "status:error", "limit": 5})

    record = json.loads(json.dumps(invocation.to_record()))
    restored = CapabilityInvocation.from_record(record)

    catalogue = {registered.name: registered}
    replayed = await catalogue[restored.capability].invoke(restored.arguments)

    assert replayed.value == original.value


@pytest.mark.parametrize(
    "secret_key",
    ["api_key", "password", "token", "secret", "authorization", "access_token"],
)
def test_credential_shaped_arguments_never_reach_the_record(secret_key: str) -> None:
    """Article IV: no credential in tool arguments, and none in the trace.

    Nothing should be putting one here — the agent holds handles, not secrets —
    so this is the check that catches the day something does.
    """
    filtered = filter_arguments({secret_key: "hunter2", "query": "status:error"})

    assert filtered[secret_key] != "hunter2"
    assert filtered["query"] == "status:error"


def test_filtering_is_case_and_shape_insensitive() -> None:
    filtered = filter_arguments({"Bearer_Token": "abc", "nested": {"api_key": "def"}})

    assert filtered["Bearer_Token"] != "abc"
    assert filtered["nested"] == {"api_key": "[REDACTED]"}


def test_an_ordinary_argument_is_left_exactly_as_written() -> None:
    """Over-redaction makes a trace unreplayable, which is the failure this fixes."""
    arguments = {"query": "status:error", "limit": 5, "regions": ["eu-west", "us-east"]}

    assert filter_arguments(arguments) == arguments
