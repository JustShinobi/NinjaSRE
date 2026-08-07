"""What an integration needs from the vendor, and how one need is checked.

A permission is a fact about the *credential*, not about the integration, and
that is why it has to be probed rather than declared. An operator who followed
the setup document and pasted a token that their organisation's policy scoped
differently has a working credential that cannot do half of what the integration
advertises. Nothing detects that except making the calls.

## Reading a failure correctly is most of the work

Four vendor answers, four different things to tell the operator, and three of
them are commonly collapsed into "permission denied":

``403`` — the permission is genuinely missing. Name it, say what stops working,
say where it is granted.

``404`` — **the call was permitted.** The resource is not there, which is
normal for a probe that names a log group or a project that this deployment does
not happen to have. Reporting it as a denial sends an operator into their
vendor's IAM console looking for a policy that is already correct, which is an
hour spent proving nothing was wrong.

``401`` — nothing was learned about the permission at all, because the
credential itself was rejected. Reporting it as denied sends them to re-issue
scopes on a key that simply needs replacing.

anything else — the check did not complete. Saying so is honest and useful;
saying "granted" because no denial arrived is how SC-005 becomes a claim nobody
can rely on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from integrations._base.errors import ErrorCategory, IntegrationError

#: One probe: given the proxy transport and who the call is for, make the
#: cheapest call that requires the permission. The signature is deliberately the
#: transport rather than a client, because a verifier constructs whichever
#: client it needs and the framework must not know how.
ProbeCall = Callable[[Any, Any], Awaitable[object]]


class ProbeState(StrEnum):
    """What one permission probe established."""

    #: The call the permission gates went through.
    GRANTED = "granted"
    #: The vendor refused it for authorisation reasons.
    DENIED = "denied"
    #: The call failed for a reason that says nothing about the permission.
    INCONCLUSIVE = "inconclusive"
    #: Not attempted, because the credential itself was rejected first.
    UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class RequiredPermission:
    """One thing the credential has to be allowed to do.

    ``capabilities`` is what makes the report actionable rather than
    informative: an operator reading "missing logs:FilterLogEvents" has to look
    it up, and one reading "so acme_log_statistics and acme_sample_logs cannot
    run" already knows whether they care.
    """

    name: str
    grants: str
    capabilities: tuple[str, ...] = ()
    where: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a permission must carry the vendor's own name for it")
        if not self.grants.strip():
            raise ValueError(
                f"{self.name}: a permission with no description of what it grants is a "
                f"string an operator has to go and look up"
            )


@dataclass(frozen=True, slots=True)
class PermissionOutcome:
    """What one probe found."""

    permission: RequiredPermission
    state: ProbeState
    detail: str = ""

    @property
    def granted(self) -> bool:
        """Return whether the permission is confirmed present."""
        return self.state is ProbeState.GRANTED

    @property
    def denied(self) -> bool:
        """Return whether the vendor refused for authorisation reasons."""
        return self.state is ProbeState.DENIED

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI or console renders."""
        return {
            "permission": self.permission.name,
            "grants": self.permission.grants,
            "state": self.state.value,
            "detail": self.detail,
            "capabilities": list(self.permission.capabilities),
        }


@dataclass(frozen=True, slots=True)
class PermissionProbe:
    """The cheapest call that proves one permission is present.

    ``fallback_note`` is FR-011 written down. A vendor with no way to introspect
    a permission is checked by making the cheapest read the capability itself
    makes, and the note says so — because a probe that quietly stands in for
    something else is a probe whose result nobody can interpret.
    """

    permission: RequiredPermission
    call: ProbeCall
    fallback_note: str = ""

    @property
    def is_fallback(self) -> bool:
        """Return whether this probe stands in for a verification endpoint the vendor lacks."""
        return bool(self.fallback_note.strip())

    async def run(self, transport: Any, context: Any) -> PermissionOutcome:
        """Make the call and return what it established about the permission."""
        try:
            await self.call(transport, context)
        except IntegrationError as error:
            return PermissionOutcome(
                permission=self.permission,
                state=_state_for(error.category),
                detail=str(error),
            )
        return PermissionOutcome(permission=self.permission, state=ProbeState.GRANTED)


#: How a classified failure reads as a statement about a permission. ``NOT_FOUND``
#: is the entry worth reading twice: the call went through, so the permission is
#: present, and only the resource named in the probe is absent.
_STATES: dict[ErrorCategory, ProbeState] = {
    ErrorCategory.PERMISSION: ProbeState.DENIED,
    ErrorCategory.NOT_FOUND: ProbeState.GRANTED,
    ErrorCategory.AUTH: ProbeState.UNCHECKED,
    ErrorCategory.RATE_LIMITED: ProbeState.INCONCLUSIVE,
    ErrorCategory.TRANSIENT: ProbeState.INCONCLUSIVE,
    ErrorCategory.UNAVAILABLE: ProbeState.INCONCLUSIVE,
    ErrorCategory.INVALID_REQUEST: ProbeState.INCONCLUSIVE,
}


def _state_for(category: ErrorCategory) -> ProbeState:
    """Return what ``category`` establishes about the permission that was probed."""
    return _STATES[category]


def client_probe[Client](
    permission: RequiredPermission,
    *,
    build: Callable[[Any, Any], Client],
    call: Callable[[Client], Awaitable[object]],
    fallback_note: str = "",
) -> PermissionProbe:
    """Return a probe that builds a client and makes one call with it.

    Almost every probe has this shape, and writing it out per permission is how
    one integration ends up constructing its client with a different retry
    policy than the rest and nobody notices until a verification run takes four
    minutes.
    """

    async def probe(transport: Any, context: Any) -> object:
        return await call(build(transport, context))

    return PermissionProbe(permission=permission, call=probe, fallback_note=fallback_note)


__all__ = [
    "PermissionOutcome",
    "PermissionProbe",
    "ProbeCall",
    "ProbeState",
    "RequiredPermission",
    "client_probe",
]
