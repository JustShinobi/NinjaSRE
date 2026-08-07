"""Deciding whether a declared schema can be given to a model, and rewriting it.

A bridged tool's input schema is written by somebody else, for a server that may
never have been used with any of the nine providers NinjaSRE supports. Two
things can be wrong with it and they are kept apart on purpose, because an
operator's next action differs.

**Malformed.** The server broke the protocol: the schema is not an object, its
``properties`` is a list, its ``required`` holds numbers. That is a bug in the
server, it is rejected with an error naming the tool and the field (FR-012), and
the operator takes it to whoever runs the server.

**Unnormalisable.** The schema is valid JSON Schema and still cannot be a tool
schema — a root that is an array, or a required argument that normalisation
drops so the model would be asked for something it is never told about. That is
excluded with a recorded reason (FR-004) and nobody is at fault.

Normalisation itself is feature 002's, applied against the *strictest* dialect
rather than the configured provider's. A bridged tool is discovered once and
stored; normalising it for whichever provider happened to be configured at
registration time would produce a schema that is wrong the day somebody switches
provider, and the symptom would be a rejected turn rather than an error here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from capabilities.protocols.port import MalformedToolSchema
from core.llm.schema import SchemaDialect, normalise_schema

#: The dialect every bridged schema is normalised against. An unregistered
#: provider id gets ``SchemaDialect``'s defaults, which are documented as the
#: strictest reading of every rule — so a schema that survives this survives all
#: nine, and a tenth provider added later inherits the same guarantee.
STRICTEST_DIALECT: Final[SchemaDialect] = SchemaDialect(provider_id="")

#: What a server declaring no schema at all means: a tool taking no arguments.
#: The MCP specification permits the omission, so treating it as a violation
#: would exclude working tools over something allowed.
NO_ARGUMENTS_SCHEMA: Final[Mapping[str, Any]] = {"type": "object", "properties": {}}


def validate_tool_schema(schema: Any, *, server: str, tool: str) -> Mapping[str, Any]:
    """Return ``schema`` unchanged, or raise ``MalformedToolSchema`` naming the fault.

    Shape only. Whether the schema *means* anything sensible is the server's
    business; whether it is the kind of document a tool declaration may be is
    ours, and a list where a mapping belongs is how a catalogue build ends in a
    ``TypeError`` three modules away from the server that caused it.
    """
    where = f"{server}.{tool}"
    if schema is None:
        return NO_ARGUMENTS_SCHEMA
    if not isinstance(schema, Mapping):
        raise MalformedToolSchema(
            f"{where}: inputSchema is a {type(schema).__name__}, and a tool's input "
            f"schema must be a JSON object"
        )

    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        raise MalformedToolSchema(
            f"{where}: inputSchema.properties is a {type(properties).__name__}, and it "
            f"must be a JSON object mapping argument names to their schemas"
        )
    if isinstance(properties, Mapping):
        for name, declaration in properties.items():
            if not isinstance(declaration, Mapping):
                raise MalformedToolSchema(
                    f"{where}: the {name!r} argument is declared as a "
                    f"{type(declaration).__name__}, and every property's declaration "
                    f"must be a JSON object"
                )

    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list | tuple):
            raise MalformedToolSchema(
                f"{where}: inputSchema.required is a {type(required).__name__}, and it "
                f"must be a list of argument names"
            )
        for entry in required:
            if not isinstance(entry, str):
                raise MalformedToolSchema(
                    f"{where}: inputSchema.required holds a {type(entry).__name__}, and "
                    f"every entry must be an argument name"
                )

    return schema


def normalisation_failure(schema: Mapping[str, Any]) -> str | None:
    """Return why ``schema`` cannot become a tool schema, or ``None`` when it can.

    Two ways to fail, and both are about what the *model* would end up holding
    rather than about JSON Schema pedantry.
    """
    try:
        normalised = normalise_schema(schema, STRICTEST_DIALECT)
    except (RecursionError, TypeError, ValueError) as error:
        return f"the schema could not be normalised for any provider: {error}"

    if normalised.get("type") != "object":
        return (
            f"the schema's root type is {normalised.get('type')!r}; a tool's arguments "
            f"must be an object, because that is the only shape a provider accepts"
        )

    properties = normalised.get("properties")
    available = set(properties) if isinstance(properties, Mapping) else set()
    declared_required = schema.get("required")
    required = (
        {entry for entry in declared_required if isinstance(entry, str)}
        if isinstance(declared_required, list | tuple)
        else set()
    )
    missing = sorted(required - available)
    if missing:
        return (
            f"the schema requires {', '.join(missing)}, which normalisation leaves the "
            f"model no way to supply — every call would be rejected as invalid"
        )
    return None


def normalised_input_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``schema`` rewritten into the form every provider accepts."""
    return normalise_schema(schema, STRICTEST_DIALECT)


__all__ = [
    "NO_ARGUMENTS_SCHEMA",
    "STRICTEST_DIALECT",
    "normalisation_failure",
    "normalised_input_schema",
    "validate_tool_schema",
]
