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

AUTONOMY_RULE: Final[dict[str, Any]] = _object(
    {
        "rule_id": _STRING,
        "scope": _STRING,
        "level": _STRING,
        "risk_bound": _STRING,
        "dry_run": _BOOLEAN,
    }
)

#: The posture as a document, kept whole beside the rendering so an export can
#: be edited and applied back without a translation step in between.
AUTONOMY_POLICY: Final[dict[str, Any]] = _object(
    {
        "node_id": _STRING,
        "dry_run": _BOOLEAN,
        "rules": _array(AUTONOMY_RULE),
        "document": {"type": "object"},
    }
)

CONSIDERED_RULE: Final[dict[str, Any]] = _object(
    {
        "rule_id": _STRING,
        "scope": _STRING,
        "level": _STRING,
        "applied": _BOOLEAN,
        "won": _BOOLEAN,
        "subject": _STRING,
        "reason": _STRING,
    }
)

AUTONOMY_EXPLANATION: Final[dict[str, Any]] = _object(
    {
        "decision": _STRING,
        "level": _STRING,
        "risk_bound": _STRING,
        "risk_class": _STRING,
        "dry_run": _BOOLEAN,
        "refused_by": _STRING,
        "reason": _STRING,
        "winning_rule": _STRING,
        "operation": _STRING,
        "considered": _array(CONSIDERED_RULE),
    }
)

AUTONOMY_BOUNDS: Final[dict[str, Any]] = _object(
    {
        "node_id": _STRING,
        "stopped": _BOOLEAN,
        "stop_reason": _STRING,
        "freezes": _array({"type": "object"}),
        "budgets": _array({"type": "object"}),
        "overrides": _array({"type": "object"}),
        "expired_overrides": _STRINGS,
    }
)

PREVIEWED_ACTION: Final[dict[str, Any]] = _object(
    {
        "action_id": _STRING,
        "capability": _STRING,
        "subjects": _STRINGS,
        "before": _STRING,
        "after": _STRING,
        "changed": _BOOLEAN,
        "more_autonomous": _BOOLEAN,
    }
)

POLICY_PREVIEW: Final[dict[str, Any]] = _object(
    {
        "summary": _STRING,
        "considered": _INTEGER,
        "changed": _INTEGER,
        "newly_autonomous": _INTEGER,
        "actions": _array(PREVIEWED_ACTION),
    }
)

KILL_SWITCH: Final[dict[str, Any]] = _object({"engaged": _BOOLEAN, "scopes": {"type": "object"}})

AUTONOMY_OVERRIDE: Final[dict[str, Any]] = _object(
    {
        "name": _STRING,
        "level": _STRING,
        "expires_at": _STRING,
        "granted_by": _STRING,
        "reason": _STRING,
        "scope": {"type": "object"},
    }
)


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

#: A counted breakdown — kind to how many, health to how many. Open on purpose,
#: which is the one exception in this file: an integration registers its own
#: resource kinds, so the *keys* are extensible by design and a closed object
#: would fail the first time somebody connected a hypervisor.
_COUNTS: Final[dict[str, Any]] = {"type": "object", "additionalProperties": _INTEGER}

ESTATE_RESOURCE: Final[dict[str, Any]] = _object(
    {
        "resource_id": _STRING,
        "kind": _STRING,
        "display_name": _STRING,
        "health": _STRING,
        "stored_health": _STRING,
        "source": _STRING,
        "sources": _STRINGS,
        "native_id": _STRING,
        "parent_id": _STRING,
        "is_stale": _BOOLEAN,
        "labels": _STRINGS,
        "last_seen_at": _STRING,
        "absent_since": _STRING,
        "maintenance_until": _STRING,
        "maintenance_reason": _STRING,
        "explanation": _STRING,
    }
)

#: The evidence map every observation and subject carries. Open on purpose: the
#: keys are whatever the detector measured, and a closed one would mean adding a
#: field here every time somebody declared a detector.
_EVIDENCE: Final[dict[str, Any]] = {"type": "object", "additionalProperties": _STRING}

#: The ledger of what one remediation did. ``awaiting_verification`` is a field
#: rather than a value a consumer derives from an absent verdict, so a script
#: that polls this cannot mistake "still settling" for "worked".
REMEDIATION_OUTCOME: Final[dict[str, Any]] = _object(
    {
        "action_id": _STRING,
        "capability": _STRING,
        "resource_id": _STRING,
        "condition_key": _STRING,
        "incident_id": _STRING,
        "executed_at": _STRING,
        "due_at": _STRING,
        "settle_seconds": _INTEGER,
        "awaiting_verification": _BOOLEAN,
        "verdict": _STRING,
        "verified_at": _STRING,
        "before": {"type": "object", "additionalProperties": _NUMBER},
        "after": {"type": "object", "additionalProperties": _NUMBER},
        "rollback": _STRING,
        "rollback_detail": _STRING,
        "autonomous": _BOOLEAN,
        "detail": _STRING,
    }
)

REMEDIATION_EFFECTIVENESS: Final[dict[str, Any]] = _object(
    {
        "capability": _STRING,
        "resource_id": _STRING,
        "condition_key": _STRING,
        "total": _INTEGER,
        "verified": _INTEGER,
        "awaiting": _INTEGER,
        "success_ratio": _NUMBER,
        "counts": {"type": "object", "additionalProperties": _INTEGER},
        "last_verdict": _STRING,
        "known": _BOOLEAN,
        "discouraged": _BOOLEAN,
        "summary": _STRING,
    }
)

RECURRING_PROBLEM: Final[dict[str, Any]] = _object(
    {
        "problem_id": _STRING,
        "pattern_key": _STRING,
        "capability": _STRING,
        "resource_id": _STRING,
        "title": _STRING,
        "summary": _STRING,
        "raised_at": _STRING,
        "occurrences": _INTEGER,
        "window_seconds": _INTEGER,
        "suppresses_autonomy": _BOOLEAN,
        "live": _BOOLEAN,
        "close_reason": _STRING,
        "closed_by": _STRING,
    }
)

AUTONOMY_SUSPENSION: Final[dict[str, Any]] = _object(
    {
        "resource_id": _STRING,
        "since": _STRING,
        "reason": _STRING,
        "action_id": _STRING,
        "live": _BOOLEAN,
        "cleared_by": _STRING,
        "clear_reason": _STRING,
    }
)


INCIDENT: Final[dict[str, Any]] = _object(
    {
        "incident_id": _STRING,
        "title": _STRING,
        "summary": _STRING,
        "state": _STRING,
        "severity": _STRING,
        "origin": _STRING,
        "detector": _STRING,
        "subjects": _STRINGS,
        "opened_at": _STRING,
        "closed_at": _STRING,
        "run_id": _STRING,
        "self_resolved": _BOOLEAN,
        "suppressed_by": _STRING,
        "close_reason": _STRING,
    }
)

INCIDENT_SUBJECT: Final[dict[str, Any]] = _object(
    {
        "resource_id": _STRING,
        "detail": _STRING,
        "evidence": _EVIDENCE,
        "observed_at": _STRING,
        "absent_since": _STRING,
    }
)

INCIDENT_TIMELINE: Final[dict[str, Any]] = _object(
    {"at": _STRING, "kind": _STRING, "actor": _STRING, "cause": _STRING, "detail": _STRING}
)

INCIDENT_DETAIL: Final[dict[str, Any]] = _object(
    {
        "incident": INCIDENT,
        "subjects": _array(INCIDENT_SUBJECT),
        "timeline": _array(INCIDENT_TIMELINE),
        "actions": _STRINGS,
    }
)

DETECTOR: Final[dict[str, Any]] = _object(
    {
        "detector_id": _STRING,
        "name": _STRING,
        "description": _STRING,
        "severity": _STRING,
        "signal": _STRING,
        "enabled": _BOOLEAN,
        "subjects_covered": _INTEGER,
        "subjects_total": _INTEGER,
        "last_verdict": _STRING,
        "last_evaluated_at": _STRING,
    }
)

OBSERVATION: Final[dict[str, Any]] = _object(
    {
        "detector": _STRING,
        "subject": _STRING,
        "verdict": _STRING,
        "detail": _STRING,
        "evidence": _EVIDENCE,
        "observed_at": _STRING,
    }
)

DRY_RUN: Final[dict[str, Any]] = _object(
    {
        "detector_id": _STRING,
        "would_fire": _BOOLEAN,
        "observations": _array(OBSERVATION),
        "fired": _BOOLEAN,
    }
)

ESTATE_SIGNAL: Final[dict[str, Any]] = _object(
    {"name": _STRING, "value": _STRING, "observed_at": _STRING, "source": _STRING}
)

ESTATE_TRANSITION: Final[dict[str, Any]] = _object(
    {"occurred_at": _STRING, "state": _STRING, "previous_state": _STRING, "rule": _STRING}
)

ESTATE_REFERENCE: Final[dict[str, Any]] = _object(
    {
        "reference_kind": _STRING,
        "reference_id": _STRING,
        "recorded_at": _STRING,
        "summary": _STRING,
    }
)

ESTATE_DETAIL: Final[dict[str, Any]] = _object(
    {
        "resource": ESTATE_RESOURCE,
        "rule": _STRING,
        "raw_status": _STRING,
        "explanation": _STRING,
        "freshness_seconds": _INTEGER,
        "rollup_rule": _STRING,
        "signals": _array(ESTATE_SIGNAL),
        "transitions": _array(ESTATE_TRANSITION),
        "references": _array(ESTATE_REFERENCE),
        "children": _array(ESTATE_RESOURCE),
    }
)

ESTATE_SUMMARY: Final[dict[str, Any]] = _object(
    {
        "total": _INTEGER,
        "problems": _INTEGER,
        "maintenance": _INTEGER,
        "absent": _INTEGER,
        "captured_at": _STRING,
        "by_kind": _COUNTS,
        "by_health": _COUNTS,
        "by_source": _COUNTS,
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
    "estate.list": _object({"resources": _array(ESTATE_RESOURCE)}),
    "estate.summary": ESTATE_SUMMARY,
    "estate.show": ESTATE_DETAIL,
    "estate.maintain": ESTATE_RESOURCE,
    "estate.release": ESTATE_RESOURCE,
    "incidents.list": _object(
        {"incidents": _array(INCIDENT), "paused": _BOOLEAN, "pause_reason": _STRING}
    ),
    "incidents.show": INCIDENT_DETAIL,
    "incidents.close": INCIDENT,
    "incidents.suppress": INCIDENT,
    "detectors.list": _object(
        {"detectors": _array(DETECTOR), "paused": _BOOLEAN, "pause_reason": _STRING}
    ),
    "detectors.observations": _object({"observations": _array(OBSERVATION)}),
    "detectors.enable": DETECTOR,
    "detectors.disable": DETECTOR,
    "detectors.dry-run": DRY_RUN,
    "remediation.list": _object({"outcomes": _array(REMEDIATION_OUTCOME), "awaiting": _INTEGER}),
    "remediation.effectiveness": REMEDIATION_EFFECTIVENESS,
    "remediation.problems": _object({"problems": _array(RECURRING_PROBLEM)}),
    "remediation.close-problem": RECURRING_PROBLEM,
    "remediation.suspensions": _object({"suspensions": _array(AUTONOMY_SUSPENSION)}),
    "remediation.clear-suspension": AUTONOMY_SUSPENSION,
    "autonomy.show": AUTONOMY_POLICY,
    "autonomy.apply": AUTONOMY_POLICY,
    "autonomy.dry-run": AUTONOMY_POLICY,
    "autonomy.why": AUTONOMY_EXPLANATION,
    "autonomy.bounds": AUTONOMY_BOUNDS,
    "autonomy.preview": POLICY_PREVIEW,
    "autonomy.override": AUTONOMY_OVERRIDE,
    "autonomy.stop": KILL_SWITCH,
    "autonomy.resume": KILL_SWITCH,
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
