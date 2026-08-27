"""Two ways to declare a tool, one record downstream.

The decorator covers the common case in six lines; the base class exists for a
tool that needs state or a lifecycle. Both are used heavily, and neither is
going away — so the property that matters is that nothing downstream can tell
which one was used. Selection, approval, the trace, and the console see one
shape, and a tool can be rewritten from one form into the other without any of
them noticing.
"""

from __future__ import annotations

from typing import Any

import pytest

from config.constants.capabilities import MAX_CAPABILITY_ERROR_MESSAGE_CHARS
from core.capability.base import BaseTool
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.capability.result import CapabilityErrorClass, CapabilityResult

pytestmark = pytest.mark.unit


DESCRIPTION = "Aggregate counts over a log query before sampling any lines."


@tool(
    name="decorated_log_statistics",
    display_name="Log statistics",
    description=DESCRIPTION,
    evidence_source="datadog",
    evidence_type=EvidenceType.LOG,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    tags=["logs"],
)
async def decorated_log_statistics(query: str, limit: int = 100) -> dict[str, int]:
    """Return counts grouped by status for ``query``."""
    return {"count": limit if query else 0}


class ClassLogStatistics(BaseTool):
    """The same declaration, written as a class."""

    name = "decorated_log_statistics"
    display_name = "Log statistics"
    description = DESCRIPTION
    evidence_source = "datadog"
    evidence_type = EvidenceType.LOG
    side_effect_level = SideEffectLevel.READ
    parallel_safe = True
    tags = ("logs",)

    async def run(self, query: str, limit: int = 100) -> dict[str, int]:
        """Return counts grouped by status for ``query``."""
        return {"count": limit if query else 0}


def test_a_decorated_function_carries_its_registration() -> None:
    registered = capability_marker(decorated_log_statistics)

    assert isinstance(registered, RegisteredTool)
    assert registered.name == "decorated_log_statistics"


def test_a_base_tool_subclass_carries_its_registration() -> None:
    registered = capability_marker(ClassLogStatistics)

    assert isinstance(registered, RegisteredTool)
    assert registered.name == "decorated_log_statistics"


def test_both_declaration_styles_produce_the_same_metadata() -> None:
    decorated = capability_marker(decorated_log_statistics)
    classed = capability_marker(ClassLogStatistics)

    assert decorated is not None and classed is not None
    assert decorated.metadata == classed.metadata


def test_both_declaration_styles_derive_the_same_schemas() -> None:
    decorated = capability_marker(decorated_log_statistics)
    classed = capability_marker(ClassLogStatistics)

    assert decorated is not None and classed is not None
    assert decorated.input_schema == classed.input_schema
    assert decorated.output_schema == classed.output_schema


def test_the_derived_schema_matches_the_signature() -> None:
    registered = capability_marker(decorated_log_statistics)
    assert registered is not None

    schema = registered.input_schema
    assert schema["type"] == "object"
    assert set(schema["properties"]) == {"query", "limit"}
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["required"] == ["query"]


def test_the_decorated_function_is_still_directly_callable() -> None:
    """A declaration must not stop a tool being unit-tested as a function."""
    assert decorated_log_statistics.__doc__ is not None


async def test_both_styles_invoke_to_the_same_result() -> None:
    decorated = capability_marker(decorated_log_statistics)
    classed = capability_marker(ClassLogStatistics)
    assert decorated is not None and classed is not None

    from_function = await decorated.invoke({"query": "status:error", "limit": 5})
    from_class = await classed.invoke({"query": "status:error", "limit": 5})

    assert from_function.value == from_class.value == {"count": 5}


async def test_a_missing_required_argument_is_a_classified_result() -> None:
    registered = capability_marker(decorated_log_statistics)
    assert registered is not None

    result = await registered.invoke({})

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INVALID_ARGUMENTS
    assert "query" in result.error.message


async def test_an_unknown_argument_is_rejected_rather_than_passed_through() -> None:
    """A silently dropped argument is a tool that ran on something else."""
    registered = capability_marker(decorated_log_statistics)
    assert registered is not None

    result = await registered.invoke({"query": "x", "regoin": "eu-west"})

    assert not result.succeeded
    assert result.error is not None
    assert "regoin" in result.error.message


async def test_an_exception_inside_a_tool_becomes_a_result() -> None:
    """FR-017: the loop must never see an unhandled exception from a capability."""

    @tool(
        name="explodes",
        display_name="Explodes",
        description="Raises on every call, to prove the loop never sees it.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def explodes() -> None:
        raise RuntimeError("upstream went away")

    registered = capability_marker(explodes)
    assert registered is not None

    result = await registered.invoke({})

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INTERNAL
    assert "upstream went away" in result.error.detail


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (TimeoutError("slow"), CapabilityErrorClass.TIMEOUT),
        (PermissionError("nope"), CapabilityErrorClass.PERMISSION_DENIED),
        (ConnectionError("down"), CapabilityErrorClass.UPSTREAM_ERROR),
        (ValueError("bad"), CapabilityErrorClass.INTERNAL),
        (TypeError("bad"), CapabilityErrorClass.INTERNAL),
    ],
)
async def test_common_exceptions_are_classified_rather_than_lumped_together(
    raised: Exception, expected: CapabilityErrorClass
) -> None:
    """The loop's next move differs by class, so lumping them wastes iterations."""

    @tool(
        name="raises_on_demand",
        display_name="Raises on demand",
        description="Raises whatever the test asked for.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def raises_on_demand() -> None:
        raise raised

    registered = capability_marker(raises_on_demand)
    assert registered is not None

    result = await registered.invoke({})

    assert result.error is not None
    assert result.error.classification is expected


async def test_a_failure_inside_the_body_is_not_blamed_on_the_arguments() -> None:
    """Measured on staging, and the retry it caused is the expensive half.

    ``proxmox_guest_tasks`` was called with ``{"kind": "lxc", "node": "pve01",
    "vmid": 122}`` — correct in every field — and failed parsing the reply
    Proxmox sent back. ``ValueError`` classified as ``invalid_arguments``, so
    the model was told its arguments were wrong, and it did the only thing that
    advice permits: it called again with different ones, which failed the same
    way.

    Arguments are checked against the schema *before* the body runs, so an
    exception escaping the body says something about the call the tool made,
    never about the call the model made. ``internal`` is the class the module
    already reserves for a failure nobody recognised, and it is not retried.
    """

    @tool(
        name="parses_a_reply",
        display_name="Parses a reply",
        description="Fails the way a vendor's unexpected reply makes a parser fail.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def parses_a_reply(node: str) -> None:
        raise ValueError("invalid literal for int() with base 10: 'pve01'")

    registered = capability_marker(parses_a_reply)
    assert registered is not None

    result = await registered.invoke({"node": "pve01"})

    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INTERNAL
    assert not result.error.retryable


async def test_a_tool_can_still_say_the_arguments_were_wrong_itself() -> None:
    """The judgement moved to the only place that holds it, rather than being lost.

    A tool knows what its arguments meant; the wrapper only knows an exception
    type. So the wrapper stopped guessing, and a tool that really was sent
    something it cannot use returns the classification rather than raising for
    one.
    """

    @tool(
        name="refuses_an_argument",
        display_name="Refuses an argument",
        description="Refuses an argument it can see is wrong.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def refuses_an_argument(vmid: int) -> CapabilityResult:
        return CapabilityResult.failed(
            "refuses_an_argument",
            CapabilityErrorClass.INVALID_ARGUMENTS,
            "vmid must be positive",
        )

    registered = capability_marker(refuses_an_argument)
    assert registered is not None

    result = await registered.invoke({"vmid": -1})

    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INVALID_ARGUMENTS


async def test_the_failure_message_says_what_went_wrong_and_not_just_its_type() -> None:
    """A console that renders the message alone showed a reader the word "ValueError".

    The message is what the model reads and what the incident card prints; the
    detail is what the trace keeps. A message carrying only an exception class
    name tells neither of them anything, and both of them had it.
    """

    @tool(
        name="fails_with_something_to_say",
        display_name="Fails with something to say",
        description="Raises with a message worth putting in front of somebody.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def fails_with_something_to_say() -> None:
        raise RuntimeError("node pve01 answered 500")

    registered = capability_marker(fails_with_something_to_say)
    assert registered is not None

    result = await registered.invoke({})

    assert result.error is not None
    assert "node pve01 answered 500" in result.error.message
    assert "RuntimeError" in result.error.message


async def test_a_vendors_wall_of_text_does_not_become_the_whole_message() -> None:
    """An HTML error page is a plausible ``str(error)``, and it goes to a model."""

    @tool(
        name="fails_at_length",
        display_name="Fails at length",
        description="Raises with the kind of body a gateway returns on a bad day.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def fails_at_length() -> None:
        raise RuntimeError("x" * 10_000)

    registered = capability_marker(fails_at_length)
    assert registered is not None

    result = await registered.invoke({})

    assert result.error is not None
    assert len(result.error.message) <= MAX_CAPABILITY_ERROR_MESSAGE_CHARS + len(
        "fails_at_length failed with RuntimeError: "
    )
    assert result.error.detail == "x" * 10_000, "the trace still keeps the whole of it"


async def test_a_tool_returning_a_result_is_not_wrapped_twice() -> None:
    """A tool that classified its own failure keeps that classification."""

    @tool(
        name="classifies_itself",
        display_name="Classifies itself",
        description="Returns a failed result rather than raising.",
        evidence_source="datadog",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def classifies_itself() -> CapabilityResult:
        return CapabilityResult.failed(
            "classifies_itself", CapabilityErrorClass.RATE_LIMITED, "Slow down."
        )

    registered = capability_marker(classifies_itself)
    assert registered is not None

    result = await registered.invoke({})

    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.RATE_LIMITED


async def test_a_synchronous_tool_is_supported() -> None:
    """Not every capability does I/O; a pure computation should not need async."""

    @tool(
        name="adds_up",
        display_name="Adds up",
        description="Sums two numbers, with no I/O of any kind.",
        evidence_source="reasoning",
        evidence_type=EvidenceType.ANALYSIS,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    def adds_up(left: int, right: int) -> int:
        return left + right

    registered = capability_marker(adds_up)
    assert registered is not None

    assert (await registered.invoke({"left": 2, "right": 3})).value == 5


def test_a_declaration_records_where_it_came_from() -> None:
    """A duplicate name has to name both modules, so both have to be recorded."""
    registered = capability_marker(decorated_log_statistics)
    assert registered is not None

    assert registered.source_module.endswith("test_declaration")
    assert registered.source_qualname == "decorated_log_statistics"


def test_a_tool_may_declare_its_schema_by_hand() -> None:
    """Some inputs are not expressible as a signature, and hand-written wins."""

    @tool(
        name="hand_written",
        display_name="Hand written",
        description="Declares its own schema rather than deriving one.",
        evidence_source="datadog",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
        input_schema={
            "type": "object",
            "properties": {"filters": {"type": "object"}},
            "required": ["filters"],
        },
    )
    async def hand_written(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    registered = capability_marker(hand_written)
    assert registered is not None

    assert registered.input_schema["properties"] == {"filters": {"type": "object"}}


def test_a_tool_carrying_no_side_effect_level_cannot_be_declared() -> None:
    with pytest.raises(TypeError):

        @tool(  # type: ignore[call-arg]
            name="undeclared",
            display_name="Undeclared",
            description="Says nothing about what it does to the world.",
            evidence_source="datadog",
            evidence_type=EvidenceType.LOG,
            parallel_safe=True,
        )
        async def undeclared() -> None:
            return None
