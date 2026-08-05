"""The record one capability call leaves behind.

The standard this has to meet is not "enough to debug with". It is: someone who
was not there, holding only the stored trace, can reconstruct the call and make
it again. A record that falls short of that is a summary of an investigation
rather than evidence of one, and the difference surfaces during the review that
needed it.

That is why arguments are stored structurally rather than as a rendered string,
and why they are filtered on the way *in*. A credential that reached the record
and was hidden at render time is a credential in the database — the agent holds
handles rather than secrets, so nothing should ever trip this, which is exactly
what makes it worth having for the day something does.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from config.constants.security import REDACTION_PLACEHOLDER
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence

#: Substrings that mark an argument name as credential-shaped. Matched against
#: the lowercased name, so ``Bearer_Token`` and ``bearerToken`` both hit.
_SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "authorization",
    "auth_header",
    "private_key",
    "session_id",
)


def _is_secret_name(name: str) -> bool:
    """Return whether ``name`` looks like it holds a credential."""
    lowered = name.replace("-", "_").lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def filter_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``arguments`` with credential-shaped values replaced.

    Only the values are replaced, never the keys, and never a value whose name
    carries no marker. Over-redaction is not the safe direction here: a record
    whose arguments were scrubbed cannot be replayed, and an unreplayable trace
    fails the standard this module exists to meet.
    """
    filtered: dict[str, Any] = {}
    for name, value in arguments.items():
        if _is_secret_name(name):
            filtered[name] = REDACTION_PLACEHOLDER
        elif isinstance(value, Mapping):
            filtered[name] = filter_arguments(value)
        else:
            filtered[name] = value
    return filtered


class InvocationOutcome(StrEnum):
    """Whether one call produced a usable result."""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class CapabilityInvocation:
    """One capability call, as it enters the run trace."""

    capability: str
    arguments: dict[str, Any]
    outcome: InvocationOutcome
    started_at: datetime
    duration_seconds: float
    side_effect_level: SideEffectLevel
    evidence: tuple[Evidence, ...] = ()
    error_class: CapabilityErrorClass | None = None
    error_message: str = ""
    run_id: str = ""
    iteration: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this invocation.

        The trace store speaks JSON, so anything that does not survive this
        round trip is not in the trace however carefully it was collected.
        """
        return {
            "capability": self.capability,
            "arguments": self.arguments,
            "outcome": self.outcome.value,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "side_effect_level": self.side_effect_level.value,
            "evidence": [
                {
                    "source": item.source,
                    "evidence_type": item.evidence_type.value,
                    "summary": item.summary,
                    "reference": item.reference,
                }
                for item in self.evidence
            ],
            "error_class": self.error_class.value if self.error_class else None,
            "error_message": self.error_message,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "metadata": self.metadata,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> CapabilityInvocation:
        """Return the invocation a stored record describes."""
        error_class = record.get("error_class")
        return cls(
            capability=str(record["capability"]),
            arguments=dict(record.get("arguments") or {}),
            outcome=InvocationOutcome(record["outcome"]),
            started_at=datetime.fromisoformat(str(record["started_at"])),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
            side_effect_level=SideEffectLevel(record["side_effect_level"]),
            evidence=tuple(
                Evidence(
                    source=str(item["source"]),
                    evidence_type=EvidenceType(item["evidence_type"]),
                    summary=str(item["summary"]),
                    reference=str(item.get("reference", "")),
                )
                for item in record.get("evidence") or ()
            ),
            error_class=CapabilityErrorClass(error_class) if error_class else None,
            error_message=str(record.get("error_message", "")),
            run_id=str(record.get("run_id", "")),
            iteration=int(record.get("iteration", 0)),
            metadata=dict(record.get("metadata") or {}),
        )


def invocation_from_result(
    registered: RegisteredTool,
    arguments: Mapping[str, Any],
    result: CapabilityResult,
    *,
    started_at: datetime,
    duration_seconds: float,
    run_id: str = "",
    iteration: int = 0,
) -> CapabilityInvocation:
    """Return the trace record for one completed call."""
    return CapabilityInvocation(
        capability=registered.name,
        arguments=filter_arguments(arguments),
        outcome=InvocationOutcome.SUCCESS if result.succeeded else InvocationOutcome.FAILURE,
        started_at=started_at,
        duration_seconds=duration_seconds,
        side_effect_level=registered.metadata.side_effect_level,
        evidence=result.evidence,
        error_class=result.error.classification if result.error else None,
        error_message=result.error.message if result.error else "",
        run_id=run_id,
        iteration=iteration,
    )


async def record_invocation(
    registered: RegisteredTool,
    arguments: Mapping[str, Any],
    *,
    run_id: str = "",
    iteration: int = 0,
) -> CapabilityInvocation:
    """Invoke ``registered`` and return the record of what happened.

    The call and its record are produced together so there is no path that
    performs one without the other. A tool result that never entered the trace
    did not happen, and the way that rule gets broken is a caller who invokes
    directly and means to record it afterwards.
    """
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    result = await registered.invoke(arguments)
    duration = time.perf_counter() - started

    return invocation_from_result(
        registered,
        arguments,
        result,
        started_at=started_at,
        duration_seconds=duration,
        run_id=run_id,
        iteration=iteration,
    )


__all__ = [
    "CapabilityInvocation",
    "InvocationOutcome",
    "filter_arguments",
    "invocation_from_result",
    "record_invocation",
]
