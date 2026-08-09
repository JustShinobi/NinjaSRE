"""Checking a call's arguments against the schema the capability declared.

Two failures, and they are opposite mistakes with opposite corrections.

**An argument the schema does not declare.** The model has read some other
vendor's version of this tool. The call must not run — a capability handed a
parameter it never declared either ignores it, which produces evidence of a
query nobody asked for, or fails deep inside a vendor client with a message
about a field name. The correction names the parameter and lists what the
capability actually takes.

**A required argument missing.** The correction names it and asks for it, and
that is all it does. Filling one in would be the single most tempting repair in
this whole feature and the one that would make every conclusion downstream
worthless: an investigation that listed the pods in a namespace nobody chose has
observed something true about the wrong thing.

Neither check is a JSON Schema validator. Types, formats and nested constraints
belong to the capability's own contract and are enforced when it is invoked;
what a model gets wrong is the *shape* — a parameter that does not exist, or one
that does and is not there — and that is what a correction can act on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config.prompts.resilience import (
    MISSING_ARGUMENT_CORRECTION,
    UNKNOWN_ARGUMENT_CORRECTION,
)
from core.llm.types import ToolCall, ToolSchema


def declared_parameters(schema: ToolSchema) -> tuple[str, ...]:
    """Return the parameter names ``schema`` declares, in order."""
    properties = schema.parameters.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    return tuple(str(name) for name in properties)


def required_parameters(schema: ToolSchema) -> tuple[str, ...]:
    """Return the parameter names ``schema`` marks required, in order."""
    required = schema.parameters.get("required")
    if not isinstance(required, (list, tuple)):
        return ()
    return tuple(str(name) for name in required)


@dataclass(frozen=True, slots=True)
class ArgumentVerdict:
    """Whether one call may be made, and what is wrong with it if not.

    ``call`` is the call exactly as the model made it. It is carried unchanged
    on purpose: a verdict that returned a *fixed* call would be the one place
    invention could enter, and there is nothing here that could do the fixing
    without choosing a value.
    """

    call: ToolCall
    unknown: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def acceptable(self) -> bool:
        """Return whether this call may be executed."""
        return not self.unknown and not self.missing


def check_arguments(call: ToolCall, schema: ToolSchema) -> ArgumentVerdict:
    """Return what is wrong with ``call`` against ``schema``, if anything.

    A schema that declares no properties at all accepts anything: some
    capabilities genuinely take free-form arguments, and rejecting every call to
    one because its schema is open would be the check misreading its own input.
    """
    declared = declared_parameters(schema)
    if not declared:
        return ArgumentVerdict(call=call)

    supplied = set(call.arguments)
    return ArgumentVerdict(
        call=call,
        unknown=tuple(sorted(supplied - set(declared))),
        missing=tuple(name for name in required_parameters(schema) if name not in supplied),
    )


def correction_for(verdict: ArgumentVerdict, schema: ToolSchema) -> str:
    """Return what the model is told about ``verdict``.

    Unknown parameters are reported before missing ones. A model that supplied
    ``label_selector`` and omitted ``namespace`` has made one mistake — it is
    calling a different tool than the one it was given — and telling it about
    the missing argument first sends it to add ``namespace`` to a call that will
    be refused again for the parameter nobody mentioned.
    """
    if verdict.unknown:
        return UNKNOWN_ARGUMENT_CORRECTION.format(
            capability=schema.name,
            unknown=", ".join(verdict.unknown),
            declared=", ".join(declared_parameters(schema)) or "none",
        )
    if verdict.missing:
        return MISSING_ARGUMENT_CORRECTION.format(
            capability=schema.name,
            missing=", ".join(verdict.missing),
        )
    return ""


def signature(call: ToolCall) -> tuple[str, str]:
    """Return the identity two calls share when they are the same request.

    Sorted-key JSON rather than the mapping itself, because two dictionaries
    built in different orders are equal and two *tuples* of their items are not,
    and a repetition detector that missed a reordered repeat would be no
    detector at all.
    """
    import json

    rendered = json.dumps(_sortable(dict(call.arguments)), sort_keys=True, default=str)
    return (call.name, rendered)


def _sortable(value: Any) -> Any:
    """Return ``value`` with every mapping key rendered as a string."""
    if isinstance(value, Mapping):
        return {str(key): _sortable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sortable(item) for item in value]
    return value


__all__ = [
    "ArgumentVerdict",
    "check_arguments",
    "correction_for",
    "declared_parameters",
    "required_parameters",
    "signature",
]
