"""Native structured output — the provider constrains generation to the schema.

The first choice whenever it is available, because it is the only mechanism
where a malformed result is impossible rather than merely unlikely. Each wire
family spells the request differently, and the adapter asks here for the fields
to merge into its payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.llm.registry import ModelDescriptor
from core.llm.schema import SchemaDialect, normalise_schema

#: The name a schema is given when a provider requires one alongside it.
STRUCTURED_OUTPUT_SCHEMA_NAME = "structured_output"


class WireFamily:
    """How a provider spells a native structured-output request.

    A plain class of constants rather than an enum: adapters compare against
    these and a new family is one more string, not a migration.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    NONE = "none"


def supports_native(descriptor: ModelDescriptor) -> bool:
    """Return whether ``descriptor`` can constrain generation to a schema."""
    return descriptor.supports_structured_output


def native_request_fields(
    schema: Mapping[str, Any],
    dialect: SchemaDialect,
    wire_family: str,
) -> dict[str, Any]:
    """Return the payload fields that ask ``wire_family`` for a schema-shaped answer.

    The schema is normalised first. A structured-output schema goes through the
    same dialect rules as a tool schema, and for the same reason: the provider
    validates it just as strictly, and rejects it just as completely.
    """
    normalised = normalise_schema(schema, dialect)

    if wire_family == WireFamily.OPENAI:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": STRUCTURED_OUTPUT_SCHEMA_NAME,
                    "schema": normalised,
                    "strict": True,
                },
            }
        }

    if wire_family == WireFamily.ANTHROPIC:
        return {"output_config": {"format": {"type": "json_schema", "schema": normalised}}}

    if wire_family == WireFamily.GOOGLE:
        return {
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": normalised,
            }
        }

    return {}


__all__ = [
    "STRUCTURED_OUTPUT_SCHEMA_NAME",
    "WireFamily",
    "native_request_fields",
    "supports_native",
]
