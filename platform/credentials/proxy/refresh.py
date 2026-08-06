"""Short-lived credentials, refreshed before they expire and retried once after.

OAuth access tokens and STS session credentials are the awkward case for a proxy
that is supposed to be the only thing holding a secret, because refreshing one
*is* an authenticated call. Doing it here rather than in the client is the only
option consistent with Article IV: a client that could refresh a token would
hold the refresh token, which is a longer-lived secret than the one it replaces.

FR-013 asks for two behaviours and they are different.

**Refresh ahead of expiry.** A credential whose expiry is inside the margin is
refreshed before the request goes out. The margin is wide enough that a request
starting just inside it still finishes with a valid token — the failure this
prevents is the one where a long vendor call outlives the credential it started
with.

**Retry exactly once after an expiry failure.** Clocks disagree, vendors revoke
early, and a token that looked valid can be rejected. One retry, with a forced
refresh, converts that into a success. A second retry would be a retry against a
credential that has already been refreshed once, so the failure is something
other than expiry — and repeating it spends the vendor's rate limit to learn
nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from config.constants.security import CREDENTIAL_REFRESH_MARGIN_SECONDS

#: The vendor statuses that mean "this credential is no longer good", as opposed
#: to "you may not do that". A 403 is deliberately included: several vendors
#: answer an expired token with one, and the cost of one extra refresh on a
#: genuine permission error is a wasted call, while the cost of not retrying is
#: a failed investigation step.
EXPIRY_STATUS_CODES: frozenset[int] = frozenset({401, 403})


@dataclass(frozen=True, slots=True)
class RefreshedCredential:
    """A freshly issued short-lived credential and when it stops being one."""

    values: Mapping[str, str] = field(repr=False)
    expires_at: datetime | None = None

    def __repr__(self) -> str:
        return f"RefreshedCredential(fields={sorted(self.values)}, expires_at={self.expires_at})"


@runtime_checkable
class CredentialRefresher(Protocol):
    """How one integration turns a stored credential into a live short-lived one.

    Implemented per vendor, on the proxy side. The stored credential is the
    long-lived half — a refresh token, an IAM role to assume — and what comes
    back is what goes on the wire.
    """

    async def refresh(
        self,
        integration: str,
        values: Mapping[str, str],
    ) -> RefreshedCredential:
        """Return a freshly issued credential for ``integration``.

        Raises rather than returning the input unchanged when the vendor
        refuses: a refresher that silently returned a stale credential would
        turn an expiry into a 401 the retry cannot fix.
        """


def needs_refresh(
    expires_at: datetime | None,
    now: datetime,
    *,
    margin_seconds: float = CREDENTIAL_REFRESH_MARGIN_SECONDS,
) -> bool:
    """Return whether a credential expiring at ``expires_at`` should be refreshed now.

    ``None`` means no expiry, which means no refresh. A credential with no
    expiry that a vendor nonetheless rejects is handled by the single retry, not
    by refreshing something on a schedule nobody declared.
    """
    if expires_at is None:
        return False
    return expires_at - timedelta(seconds=margin_seconds) <= now


def is_expiry_failure(status_code: int) -> bool:
    """Return whether a vendor status means the credential itself was rejected."""
    return status_code in EXPIRY_STATUS_CODES


__all__ = [
    "EXPIRY_STATUS_CODES",
    "CredentialRefresher",
    "RefreshedCredential",
    "is_expiry_failure",
    "needs_refresh",
]
