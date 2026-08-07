"""The published shape of every ``--json`` document, and a validator for it.

Two things live here and they are deliberately together.

**The schemas.** One per command, as JSON Schema, keyed by the command's
dotted name. Publishing them is what makes ``--json`` a contract rather than a
convenience: an operator writing a script against ``runs list`` is entitled to
know the shape will not change under them, and a change that alters one is a
change to a published document rather than an implementation detail.

**A validator over the subset the schemas use.** Objects, arrays, strings,
numbers, booleans, ``required``, and ``additionalProperties``. Not a general
JSON Schema implementation and not trying to be — a dependency that validated
everything would be carrying a specification's worth of behaviour for the seven
keywords these documents use, and the contract suite has to be able to say
*which field* diverged, which a general validator says less well than one that
knows it is checking a payload.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from config.constants.surfaces import (
    JSON_ENVELOPE_KEYS,
    JSON_SCHEMA_PREFIX,
    JSON_SCHEMA_VERSION,
)

JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"


def schema_id(command: str) -> str:
    """Return the published identifier of ``command``'s output schema."""
    return f"{JSON_SCHEMA_PREFIX}.{command.replace(' ', '.')}.{JSON_SCHEMA_VERSION}"


def _object(
    properties: Mapping[str, Any],
    *,
    required: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a closed object schema.

    Closed by default. An open one would let a payload grow a field the
    published document never mentioned, which is exactly the drift the schemas
    exist to catch.
    """
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required if required is not None else properties.keys()),
        "additionalProperties": False,
    }


def _array(items: Mapping[str, Any]) -> dict[str, Any]:
    """Return an array schema over ``items``."""
    return {"type": "array", "items": dict(items)}


_STRING: Final[dict[str, Any]] = {"type": "string"}
_INTEGER: Final[dict[str, Any]] = {"type": "integer"}
_NUMBER: Final[dict[str, Any]] = {"type": "number"}
_BOOLEAN: Final[dict[str, Any]] = {"type": "boolean"}
_STRINGS: Final[dict[str, Any]] = _array(_STRING)

COST: Final[dict[str, Any]] = _object(
    {
        "runs": _INTEGER,
        "turns": _INTEGER,
        "prompt_tokens": _INTEGER,
        "completion_tokens": _INTEGER,
        "total_tokens": _INTEGER,
        "cost": _NUMBER,
        "unpriced_runs": _INTEGER,
    }
)

SPEND_LINE: Final[dict[str, Any]] = _object(
    {
        "label": _STRING,
        "runs": _INTEGER,
        "turns": _INTEGER,
        "prompt_tokens": _INTEGER,
        "completion_tokens": _INTEGER,
        "total_tokens": _INTEGER,
        "cost": _NUMBER,
        "unpriced_runs": _INTEGER,
        "complete": _BOOLEAN,
    }
)

SPEND_REPORT: Final[dict[str, Any]] = _object(
    {
        "since": _STRING,
        "until": _STRING,
        "total": SPEND_LINE,
        "by_team": _array(SPEND_LINE),
        "by_run": _array(SPEND_LINE),
    }
)

INTEGRATION_HEALTH: Final[dict[str, Any]] = _object(
    {
        "headline": _STRING,
        "all_healthy": _BOOLEAN,
        "healthy": _STRINGS,
        "unhealthy": _STRINGS,
        "unconfigured": _STRINGS,
    }
)

RUN_SUMMARY: Final[dict[str, Any]] = _object(
    {
        "run_id": _STRING,
        "status": _STRING,
        "trigger": _STRING,
        "objective": _STRING,
        "team_node_id": _STRING,
        "principal_id": _STRING,
        "started_at": _STRING,
        "ended_at": _STRING,
        "awaiting": _STRING,
    }
)

STAGE: Final[dict[str, Any]] = _object(
    {
        "stage": _STRING,
        "started_at": _STRING,
        "ended_at": _STRING,
        "failed": _BOOLEAN,
    }
)

RUN_DETAIL: Final[dict[str, Any]] = _object(
    {
        "run": RUN_SUMMARY,
        "stages": _array(STAGE),
        "evidence_ids": _STRINGS,
        "result": _STRING,
        "errors": _STRINGS,
        "cost": COST,
    }
)

PROVIDER_STATUS: Final[dict[str, Any]] = _object(
    {
        "provider_id": _STRING,
        "configured": _BOOLEAN,
        "local": _BOOLEAN,
        "verified": _BOOLEAN,
        "model_id": _STRING,
        "detail": _STRING,
    }
)

INTEGRATION_STATUS: Final[dict[str, Any]] = _object(
    {
        "integration": _STRING,
        "configured": _BOOLEAN,
        "healthy": _BOOLEAN,
        "credential_state": _STRING,
        "detail": _STRING,
    }
)

CONFIG_ENTRY: Final[dict[str, Any]] = _object(
    {"path": _STRING, "value": _STRING, "source_node_id": _STRING}
)

SCHEDULE_SUMMARY: Final[dict[str, Any]] = _object(
    {
        "job_id": _STRING,
        "objective": _STRING,
        "cron": _STRING,
        "timezone": _STRING,
        "enabled": _BOOLEAN,
        "team_node_id": _STRING,
        "next_fire_at": _STRING,
        "disabled_reason": _STRING,
    }
)

MEMORY_HIT: Final[dict[str, Any]] = _object(
    {
        "episode_id": _STRING,
        "title": _STRING,
        "score": _NUMBER,
        "components": _STRINGS,
        "occurred_at": _STRING,
        "root_cause": _STRING,
    }
)

DIAGNOSTIC_CHECK: Final[dict[str, Any]] = _object(
    {"name": _STRING, "state": _STRING, "detail": _STRING, "remedy": _STRING}
)

DIAGNOSTIC_REPORT: Final[dict[str, Any]] = _object(
    {
        "healthy": _BOOLEAN,
        "version": _STRING,
        "checks": _array(DIAGNOSTIC_CHECK),
        "failures": _INTEGER,
        "warnings": _INTEGER,
    }
)

LIFECYCLE_OUTCOME: Final[dict[str, Any]] = _object(
    {
        "action": _STRING,
        "changed": _BOOLEAN,
        "from_version": _STRING,
        "to_version": _STRING,
        "removed": _STRINGS,
        "detail": _STRING,
    }
)

#: Every command's ``data`` payload, by the command's dotted name. The contract
#: suite walks the typer application and fails on a command with no entry here,
#: so a new command cannot ship with an undocumented ``--json``.
COMMAND_SCHEMAS: Final[Mapping[str, Mapping[str, Any]]] = {
    "investigate": _object(
        {
            "run_id": _STRING,
            "status": _STRING,
            "summary": _STRING,
            "report_path": _STRING,
            "evidence_count": _INTEGER,
            "cost": COST,
        }
    ),
    "runs.list": _object({"runs": _array(RUN_SUMMARY), "cost": COST}),
    "runs.show": RUN_DETAIL,
    "runs.replay": _object(
        {
            "run_id": _STRING,
            "events": _array({"type": "object"}),
            "view": {"type": "object"},
        }
    ),
    "config.show": _object({"node_id": _STRING, "entries": _array(CONFIG_ENTRY)}),
    "config.set": _object(
        {
            "node_id": _STRING,
            "path": _STRING,
            "before": _STRING,
            "after": _STRING,
            "applied": _BOOLEAN,
            "requires_approval": _BOOLEAN,
            "detail": _STRING,
        }
    ),
    "config.diff": _object(
        {
            "left_node_id": _STRING,
            "right_node_id": _STRING,
            "deltas": _array(_object({"path": _STRING, "left": _STRING, "right": _STRING})),
        }
    ),
    "schedule.list": _object({"schedules": _array(SCHEDULE_SUMMARY)}),
    "schedule.add": SCHEDULE_SUMMARY,
    "schedule.remove": _object({"job_id": _STRING, "removed": _BOOLEAN}),
    "memory.search": _object({"query": _STRING, "hits": _array(MEMORY_HIT)}),
    "memory.stats": _object(
        {
            "episodes": _INTEGER,
            "components": _INTEGER,
            "mean_effectiveness": _NUMBER,
            "oldest_at": _STRING,
            "newest_at": _STRING,
            "read_enabled": _BOOLEAN,
            "write_enabled": _BOOLEAN,
        }
    ),
    "providers.list": _object({"providers": _array(PROVIDER_STATUS)}),
    "providers.verify": PROVIDER_STATUS,
    "cost": SPEND_REPORT,
    "integrations.list": _object({"integrations": _array(INTEGRATION_STATUS)}),
    "integrations.health": INTEGRATION_HEALTH,
    "integrations.setup": INTEGRATION_STATUS,
    "integrations.verify": INTEGRATION_STATUS,
    "onboard": _object(
        {
            "provider_id": _STRING,
            "model_id": _STRING,
            "integrations": _array(INTEGRATION_STATUS),
            "verified": _BOOLEAN,
            "steps": _STRINGS,
            "detail": _STRING,
        }
    ),
    "doctor": DIAGNOSTIC_REPORT,
    "update": LIFECYCLE_OUTCOME,
    "uninstall": LIFECYCLE_OUTCOME,
}

#: The envelope every document is wrapped in, whatever the command.
ENVELOPE_SCHEMA: Final[Mapping[str, Any]] = _object(
    {
        "schema": _STRING,
        "command": _STRING,
        "ok": _BOOLEAN,
        "data": {"type": "object"},
        "errors": _STRINGS,
    },
    required=JSON_ENVELOPE_KEYS,
)


_TYPE_CHECKS: Final[Mapping[str, tuple[type, ...]]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
}


def _type_matches(value: Any, expected: str) -> bool:
    """Return whether ``value`` is of the JSON type ``expected``.

    ``bool`` is excluded from the numeric types explicitly. Python says a bool
    is an int, JSON does not, and a payload that reported ``true`` where a
    reader expected a token count would pass a naive check.
    """
    if expected in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, _TYPE_CHECKS[expected])


def problems(document: Any, schema: Mapping[str, Any], *, at: str = "$") -> tuple[str, ...]:
    """Return every way ``document`` diverges from ``schema``, each located.

    Located, because "a field is wrong" is not actionable on a document with
    forty of them. Every message starts with the JSON path so the failure names
    the field rather than the payload.
    """
    found: list[str] = []
    expected = schema.get("type")

    if isinstance(expected, str) and not _type_matches(document, expected):
        # Stops here rather than accumulating: every message a wrongly-typed
        # value would go on to produce is a consequence of this one.
        return (f"{at}: expected {expected}, got {type(document).__name__}",)

    if expected == "object" and isinstance(document, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in document:
                found.append(f"{at}.{name}: required and missing")
        if schema.get("additionalProperties") is False:
            for name in document:
                if name not in properties:
                    found.append(f"{at}.{name}: not in the published schema")
        for name, sub in properties.items():
            if name in document:
                found.extend(problems(document[name], sub, at=f"{at}.{name}"))

    if expected == "array" and isinstance(document, list | tuple):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, element in enumerate(document):
                found.extend(problems(element, items, at=f"{at}[{index}]"))

    return tuple(found)


def validate(document: Any, schema: Mapping[str, Any]) -> None:
    """Raise if ``document`` diverges from ``schema``.

    Raises:
        ValueError: naming every divergence, one per line.
    """
    found = problems(document, schema)
    if found:
        joined = "\n  ".join(found)
        raise ValueError(f"document does not match its published schema:\n  {joined}")


def published(command: str) -> Mapping[str, Any]:
    """Return ``command``'s published payload schema, as a JSON Schema document.

    Raises:
        KeyError: nothing is published for that command, which is a command
            that shipped without a documented ``--json``.
    """
    payload = COMMAND_SCHEMAS[command]
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": schema_id(command),
        "title": f"ninjasre {command.replace('.', ' ')} --json",
        **dict(ENVELOPE_SCHEMA),
        "properties": {**dict(ENVELOPE_SCHEMA["properties"]), "data": dict(payload)},
    }


__all__ = [
    "COMMAND_SCHEMAS",
    "ENVELOPE_SCHEMA",
    "JSON_SCHEMA_DIALECT",
    "problems",
    "published",
    "schema_id",
    "validate",
]
