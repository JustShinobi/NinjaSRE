"""Does this credential actually work? Answered by using it (FR-021).

The operator request behind this is always the same: something is failing, and
they want to know whether the credential is the problem. The instinct is to show
them the value so they can compare it against their password manager, and that
instinct is what the whole feature exists to defeat.

So the answer comes from a call instead. The verifier makes one cheap, read-only
request through the proxy and reports what the vendor said. That answers the
question better than showing the value would — a key that looks right and has
been revoked looks exactly as right as one that works — and it answers it
without the value ever leaving the proxy.

The failure detail is the actionable half. "401 Unauthorized" tells an operator
to re-issue the key; "403 Forbidden" tells them the key is fine and the scope is
wrong; "could not reach the host" tells them to look at egress. Collapsing those
into "verification failed" would send them to the wrong place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from platform.credentials.descriptor import IntegrationDescriptor
from platform.credentials.errors import UnknownIntegration
from platform.credentials.proxy.errors import ProxyError


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """What one end-to-end check found.

    ``detail`` is the vendor's own words where there are any. It is not a
    credential — a vendor rejecting a key does not echo it back — but it is the
    part that tells an operator which of the several possible problems they
    have.
    """

    integration: str
    ok: bool
    detail: str = ""
    status_code: int | None = None

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI or console renders."""
        return {
            "integration": self.integration,
            "ok": self.ok,
            "detail": self.detail,
            "status_code": self.status_code,
        }


@runtime_checkable
class VerificationProbe(Protocol):
    """One vendor's cheapest read-only call, used to prove the credential works.

    Deliberately narrow. A verifier that ran a real query would be a verifier
    that costs the operator quota every time they ask a diagnostic question,
    and that is how a useful command becomes one nobody runs.
    """

    @property
    def integration(self) -> str:
        """Return the integration this probe checks."""

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Make the check call and return what the vendor said."""


class CredentialVerification:
    """Runs the declared probe for one integration, or for all of them."""

    __slots__ = ("_descriptors",)

    def __init__(self, descriptors: dict[str, IntegrationDescriptor]) -> None:
        self._descriptors = dict(descriptors)

    async def verify(
        self,
        integration: str,
        *,
        transport: object,
        context: object,
    ) -> VerificationResult:
        """Return what the vendor said when this credential was used.

        A proxy refusal is a result, not an exception: "no credential is
        configured" is precisely the answer the operator asked for, and raising
        would make the caller handle the expected case in an ``except``.
        """
        descriptor = self._descriptors.get(integration)
        if descriptor is None:
            raise UnknownIntegration(integration, known=tuple(sorted(self._descriptors)))

        probe = descriptor.verifier
        if not isinstance(probe, VerificationProbe):
            return VerificationResult(
                integration=integration,
                ok=False,
                detail="this integration declares a verifier that cannot make a check call",
            )
        try:
            return await probe.probe(transport, context)
        except ProxyError as error:
            return VerificationResult(integration=integration, ok=False, detail=str(error))

    async def verify_all(
        self,
        *,
        transport: object,
        context: object,
    ) -> tuple[VerificationResult, ...]:
        """Return a result for every declared integration, in name order."""
        return tuple(
            [
                await self.verify(name, transport=transport, context=context)
                for name in sorted(self._descriptors)
            ]
        )


__all__ = [
    "CredentialVerification",
    "VerificationProbe",
    "VerificationResult",
]
