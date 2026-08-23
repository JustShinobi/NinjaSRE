"""Every shipped write, invoked directly, refuses — and all of them say it the same way.

This is the one suite here that is born green, and the reason is worth writing
down: it is the net under the work that composes the gate. Wiring a gate over a
set of capabilities that already refuse is safe precisely because the refusal
stays; a change that made the gate work by loosening the body of a capability
would look like progress and would remove the guarantee that a write cannot
happen through a second entrance.

So it asserts three things a loosening would break, over the shipped catalogue
rather than over a list written here:

* every capability above ``read_sensitive`` refuses when it is called;
* the refusal is ``PERMISSION_DENIED`` rather than "waiting for a human",
  because nobody is being asked and the model must not retry;
* all of them refuse with **one** sentence, so an operator who sees it twice
  recognises it.

The arguments are built from each capability's own declared schema. A table of
per-capability arguments written here would drift from the capabilities, and the
first one to drift would be the one that silently stopped being covered.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.registry import build_registry
from capabilities.tools.remediation._base import UNGATED_REFUSAL
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityErrorClass, CapabilityResult

#: Where a gate-backed write lives. Four capabilities above ``read_sensitive``
#: are declared elsewhere — a notification, an acknowledgement, a knowledge
#: proposal — and they are a different kind of write: they have no state to
#: read, no undo to derive and no components registered, so they refuse by
#: naming what is unconfigured rather than by naming the gate. The last test
#: below pins that difference rather than papering over it, because it is
#: exactly the fact tool selection has to act on.
REMEDIATION_PACKAGE = "capabilities.tools.remediation"

#: One placeholder per JSON schema type. The values are never used — every one
#: of these calls refuses before it looks at an argument — and they exist so the
#: call can be made at all.
_PLACEHOLDERS: Mapping[str, Any] = {
    "string": "placeholder",
    "integer": 1,
    "number": 1.0,
    "boolean": True,
    "array": [],
    "object": {},
}


def _write_capabilities() -> tuple[RegisteredTool, ...]:
    """Return every registered tool that writes, in name order."""
    registry = build_registry()
    return tuple(
        registry.tools[name]
        for name in sorted(registry.tools)
        if registry.tools[name].metadata.side_effect_level.needs_approval
    )


def _gate_backed() -> tuple[RegisteredTool, ...]:
    """Return the writes the gate is composed over: the ones with components."""
    return tuple(
        tool for tool in _write_capabilities() if tool.source_module.startswith(REMEDIATION_PACKAGE)
    )


def _arguments_for(tool: RegisteredTool) -> dict[str, Any]:
    """Return one placeholder per required argument of ``tool``'s declared schema."""
    properties = tool.input_schema.get("properties", {})
    required = tool.input_schema.get("required", [])
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        return {}
    arguments: dict[str, Any] = {}
    for name in required:
        declared = properties.get(name, {})
        kind = declared.get("type", "string") if isinstance(declared, Mapping) else "string"
        arguments[str(name)] = _PLACEHOLDERS.get(str(kind), "placeholder")
    return arguments


async def _invoke(tool: RegisteredTool) -> CapabilityResult:
    """Call ``tool`` directly, the way a model that ignored the gate would."""
    answered = tool.call(**_arguments_for(tool))
    if inspect.isawaitable(answered):
        answered = await answered
    assert isinstance(answered, CapabilityResult)
    return answered


WRITES = _gate_backed()


def test_the_catalogue_still_ships_writes_to_cover() -> None:
    """A suite that covers nothing passes for the wrong reason."""
    assert len(WRITES) >= 20, (
        f"only {len(WRITES)} gate-backed writing capabilities were found. Either the "
        f"catalogue shrank or this suite stopped seeing it, and both are worth knowing."
    )


@pytest.mark.parametrize("tool", WRITES, ids=lambda tool: tool.name)
async def test_calling_a_write_directly_is_refused(tool: RegisteredTool) -> None:
    result = await _invoke(tool)

    assert not result.succeeded, (
        f"{tool.name} performed something when it was called directly. A write "
        f"reachable without the gate is a write with no plan, no decision and no "
        f"audit line."
    )
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.PERMISSION_DENIED, (
        f"{tool.name} refused as {result.error.classification.value}. A direct call is "
        f"not waiting on anybody, so a model told to wait would wait for ever."
    )


async def test_all_of_them_refuse_with_the_same_sentence() -> None:
    """One sentence, so somebody who has seen it once recognises it."""
    sentences = set()
    for tool in WRITES:
        result = await _invoke(tool)
        assert result.error is not None
        sentences.add(result.error.message)

    assert sentences == {UNGATED_REFUSAL}, (
        f"the shipped writes refuse in {len(sentences)} different ways: {sorted(sentences)}. "
        f"One refusal, named once, is what makes the second sighting recognisable."
    )


@pytest.mark.parametrize("tool", WRITES, ids=lambda tool: tool.name)
async def test_the_refusal_names_the_capability_it_came_from(tool: RegisteredTool) -> None:
    """A shared sentence still has to say which call it answered."""
    result = await _invoke(tool)
    assert result.capability == tool.name


def test_a_write_declared_outside_the_package_has_no_components_to_carry_it() -> None:
    """The fact tool selection acts on, asserted rather than assumed.

    A capability above ``read_sensitive`` with no registered components cannot
    be carried through the gate at all: there is nothing to read its state
    with, nothing to derive an undo from, and nothing to apply. Offering one to
    a turn spends a schema slot on a call that can only come back refused.
    """
    from capabilities.tools.remediation import COMPONENTS

    carried = {bundle.capability for bundle in COMPONENTS}
    outside = [
        tool.name
        for tool in _write_capabilities()
        if not tool.source_module.startswith(REMEDIATION_PACKAGE)
    ]

    assert outside, "the catalogue no longer declares a write outside the remediation package"
    assert not (set(outside) & carried), (
        f"{sorted(set(outside) & carried)} is declared outside {REMEDIATION_PACKAGE} and "
        f"still has remediation components registered. Two answers to 'can this "
        f"deployment carry that write' is one answer too many."
    )
