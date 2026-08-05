"""The tool-schema catalogue the normalisation contract is run against.

These are deliberately awkward. Each one is drawn from a construct that a real
JSON Schema author writes without thinking twice and that at least one provider
rejects outright: a nullable union, a `oneOf` discriminated union, a `$ref` into
`$defs`, an `additionalProperties` map, a `format` nobody implements, a name
longer than the cap, an optional field under a dialect that demands every
property be required.

The failure this catalogue exists to reproduce is **combinatorial**. A single
schema normalises correctly almost by accident; the turn breaks when every
selected tool is sent together and one of them is rejected, taking the whole
request with it. So the contract loads all of these at once, and grows as the
capability catalogue grows.
"""

from __future__ import annotations

from typing import Any

from core.llm.types import ToolSchema

#: A nullable union written the draft-07 way. Rejected by every provider whose
#: schema layer is an OpenAPI 3.0 subset.
_UNION_TYPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "namespace": {"type": ["string", "null"], "description": "Kubernetes namespace"},
        "since": {"type": ["string", "number"], "description": "RFC3339 or epoch seconds"},
    },
    "required": ["namespace"],
    "additionalProperties": False,
}

#: A discriminated union. `oneOf` is the natural spelling and the least portable.
_ONE_OF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"pod": {"type": "string"}},
                    "required": ["pod"],
                },
                {
                    "type": "object",
                    "properties": {"node": {"type": "string"}},
                    "required": ["node"],
                },
            ]
        }
    },
    "required": ["target"],
}

#: Nested composition — an `anyOf` whose branches themselves compose.
_NESTED_COMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selector": {
            "anyOf": [
                {"type": "string"},
                {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "object", "additionalProperties": {"type": "string"}},
                    ]
                },
            ]
        }
    },
    "required": ["selector"],
}

#: `$ref` into `$defs`. Idiomatic, and unsupported by most non-OpenAI dialects.
_REF_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "$defs": {
        "timeRange": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "format": "date-time"},
                "end": {"type": "string", "format": "date-time"},
            },
            "required": ["start", "end"],
        }
    },
    "properties": {
        "range": {"$ref": "#/$defs/timeRange"},
        "comparison_range": {"$ref": "#/$defs/timeRange"},
    },
    "required": ["range"],
}

#: An open-ended map, plus formats outside every provider's supported set.
_OPEN_MAP_AND_FORMAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "labels": {"type": "object", "additionalProperties": {"type": "string"}},
        "window": {"type": "string", "format": "duration"},
        "contact": {"type": "string", "format": "idn-email"},
        "dashboard": {"type": "string", "format": "uri"},
    },
    "required": ["labels"],
    "additionalProperties": True,
}

#: Validation keywords a strict dialect drops on the floor.
_VALIDATION_KEYWORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 4096},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 100},
        "step": {"type": "number", "multipleOf": 0.5},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    },
    "required": ["query"],
}

#: Optional properties. A dialect that demands every property be listed in
#: `required` must not answer by deleting the optional ones.
_OPTIONAL_PROPERTIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "service": {"type": "string"},
        "environment": {"type": "string", "enum": ["prod", "staging", "dev"]},
        "trace_id": {"type": "string"},
    },
    "required": ["service"],
}

#: Deeply nested objects, which several dialects flatten or truncate.
_DEEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filter": {
            "type": "object",
            "properties": {
                "must": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "match": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": ["string", "null"]},
                                    "operator": {"type": "string", "enum": ["eq", "ne", "re"]},
                                },
                                "required": ["value"],
                            },
                        },
                        "required": ["field", "match"],
                    },
                }
            },
            "required": ["must"],
        }
    },
    "required": ["filter"],
}

#: An empty-parameter tool. The degenerate case that a rule chain forgets.
_NO_PARAMETERS_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


CAPABILITY_SCHEMAS: tuple[ToolSchema, ...] = (
    ToolSchema(
        name="kubernetes_list_pods",
        description="List pods, optionally scoped to a namespace.",
        parameters=_UNION_TYPE_SCHEMA,
    ),
    ToolSchema(
        name="kubernetes_describe_target",
        description="Describe either a pod or a node.",
        parameters=_ONE_OF_SCHEMA,
    ),
    ToolSchema(
        name="prometheus_select_series",
        description="Select series by a string, a list, or a label map.",
        parameters=_NESTED_COMPOSITION_SCHEMA,
    ),
    ToolSchema(
        name="grafana_query_range",
        description="Query a dashboard panel over a time range.",
        parameters=_REF_SCHEMA,
    ),
    ToolSchema(
        name="loki_search",
        description="Search logs by label map within a window.",
        parameters=_OPEN_MAP_AND_FORMAT_SCHEMA,
    ),
    ToolSchema(
        name="elasticsearch_search",
        description="Run a bounded search query.",
        parameters=_VALIDATION_KEYWORD_SCHEMA,
    ),
    ToolSchema(
        name="pagerduty_incident_context",
        description="Fetch incident context for a service.",
        parameters=_OPTIONAL_PROPERTIES_SCHEMA,
    ),
    ToolSchema(
        name="opensearch_structured_filter",
        description="Apply a nested boolean filter.",
        parameters=_DEEP_SCHEMA,
    ),
    ToolSchema(
        name="runbook_list",
        description="List the runbooks available to this investigation.",
        parameters=_NO_PARAMETERS_SCHEMA,
    ),
    ToolSchema(
        # Longer than every provider's name cap, and carrying characters that
        # the stricter name patterns reject.
        name="observability.platform:query-metrics-across-every-configured-datasource-and-region",
        description="D" * 4_096,
        parameters=_UNION_TYPE_SCHEMA,
    ),
)
