"""What a capability hands back, including when it fails.

A tool that raises ends the turn and takes the trace with it. The model never
learns that the query timed out, the loop cannot try the other region, and the
investigation stops on an exception whose text nobody reads until afterwards.

So failure is a value here, classified into a closed set, with retryability a
property of the class rather than a judgement made at each call site. The loop
reads the classification and decides; the operator reads it in the trace and
knows which of "the tool is broken" and "the vendor was down" happened.

Evidence rides on both outcomes. A capability that timed out after two of three
regions still learned something about two regions, and throwing that away
because the third failed is how an investigation repeats work it already did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.capability.metadata import EvidenceType


class CapabilityErrorClass(StrEnum):
    """Why an invocation produced no usable result.

    Closed, like the provider taxonomy it mirrors. A failure nobody recognised
    is ``INTERNAL``, and ``INTERNAL`` is not retried: repeating a call whose
    failure nobody understands is how one broken tool becomes a spent budget.

    ``INVALID_ARGUMENTS`` has exactly two sources, and neither of them guesses:
    the schema check the wrapper makes before a tool runs, and a tool that
    returns this class about arguments it can see are wrong. It is never
    inferred from an exception a body raised, because by then the arguments have
    already passed the schema and whatever went wrong belongs to the call the
    tool made. Telling a model its arguments were bad is telling it to send
    different ones, so a wrong guess here does not merely mislabel a failure —
    it buys another.
    """

    INVALID_ARGUMENTS = "invalid_arguments"
    UNAVAILABLE = "unavailable"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_REQUIRED = "approval_required"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"

    @property
    def retryable(self) -> bool:
        """Return whether repeating the same call could plausibly succeed."""
        return self in _RETRYABLE_CLASSES


#: The only classes worth repeating. Re-sending invalid arguments produces the
#: same invalid arguments, and re-requesting a denied permission produces the
#: same denial — both burn an iteration to learn nothing.
_RETRYABLE_CLASSES: frozenset[CapabilityErrorClass] = frozenset(
    {
        CapabilityErrorClass.TIMEOUT,
        CapabilityErrorClass.RATE_LIMITED,
        CapabilityErrorClass.UPSTREAM_ERROR,
    }
)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One observation a capability produced.

    ``reference`` points back at the thing itself — a saved query, a snapshot
    identifier — so a conclusion drawn from this can be checked by someone who
    was not there. A summary with no reference is a claim; with one it is a
    finding.
    """

    source: str
    evidence_type: EvidenceType
    summary: str
    reference: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityError:
    """A classified failure, on its way back to the model as a value."""

    classification: CapabilityErrorClass
    message: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("a capability error must carry a message the model can act on")

    @property
    def retryable(self) -> bool:
        """Return whether repeating the same call could plausibly succeed."""
        return self.classification.retryable


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """The outcome of one invocation, successful or not.

    One shape for both outcomes, because the caller's handling is the same
    either way: record it, put it in the trace, hand it to the model. Branching
    on the type of the return value is how a failure path stops being tested.
    """

    capability: str
    value: Any = None
    error: CapabilityError | None = None
    evidence: tuple[Evidence, ...] = ()
    duration_seconds: float = 0.0
    truncated: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """Return whether the invocation produced a usable result."""
        return self.error is None

    @classmethod
    def ok(
        cls,
        capability: str,
        *,
        value: Any = None,
        evidence: tuple[Evidence, ...] | list[Evidence] = (),
        duration_seconds: float = 0.0,
        truncated: bool = False,
    ) -> CapabilityResult:
        """Return a successful result for ``capability``."""
        return cls(
            capability=capability,
            value=value,
            evidence=tuple(evidence),
            duration_seconds=duration_seconds,
            truncated=truncated,
        )

    @classmethod
    def failed(
        cls,
        capability: str,
        classification: CapabilityErrorClass,
        message: str,
        *,
        detail: str = "",
        evidence: tuple[Evidence, ...] | list[Evidence] = (),
        duration_seconds: float = 0.0,
    ) -> CapabilityResult:
        """Return a failed result carrying its classification and partial evidence."""
        return cls(
            capability=capability,
            error=CapabilityError(classification=classification, message=message, detail=detail),
            evidence=tuple(evidence),
            duration_seconds=duration_seconds,
        )


__all__ = [
    "CapabilityError",
    "CapabilityErrorClass",
    "CapabilityResult",
    "Evidence",
]
