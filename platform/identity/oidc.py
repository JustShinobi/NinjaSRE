"""Authorization Code with PKCE, and turning the result into a principal.

PKCE always, and ``plain`` is not offered. The specification allows it and an
operator who could choose it would eventually choose it by accident — the whole
value of the exchange is that the code is worthless without the verifier, and
``plain`` puts the verifier in the request that carries the code.

**The network is not in this module.** Building the authorisation URL, checking
`state`, and reading claims are pure functions over values; fetching the token
endpoint and the JWKS is the transport's job, and it hands the claims back here.
That is what makes the flow testable without a provider, and it is also what
lets ``sso_config.activate`` refuse an untested configuration — the test sign-in
runs exactly this code with exactly these settings.

**Group membership is re-evaluated every sign-in**. Nothing about a
user's team survives from the last session: the claims are read fresh and mapped
fresh, so revoking somebody's group in the directory takes effect the next time
they sign in rather than whenever a cache decided.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from config.constants.security import (
    OIDC_AUTHORISATION_TTL_SECONDS,
    OIDC_CLOCK_SKEW_SECONDS,
    OIDC_CODE_CHALLENGE_METHOD,
    OIDC_CODE_VERIFIER_BYTES,
    OIDC_STATE_BYTES,
)
from platform.identity.errors import SsoExchangeFailed
from platform.identity.sso_config import GroupMapping, SsoConfig, map_groups

AUTHORISATION_TTL = timedelta(seconds=OIDC_AUTHORISATION_TTL_SECONDS)
CLOCK_SKEW = timedelta(seconds=OIDC_CLOCK_SKEW_SECONDS)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


def _b64(raw: bytes) -> str:
    """Return URL-safe base64 without padding, which is what PKCE specifies."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass(frozen=True, slots=True)
class AuthorisationRequest:
    """One in-flight sign-in: where the user was sent, and what proves it was us.

    ``verifier`` never leaves this process until the exchange, and ``state`` is
    what ties the provider's redirect back to a request we made. Both are kept
    server-side; the redirect carries only their derivatives.
    """

    state: str
    verifier: str
    challenge: str
    url: str
    created_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """Return whether this request has been in flight too long."""
        return now - self.created_at >= AUTHORISATION_TTL


def begin(
    config: SsoConfig,
    *,
    clock: Callable[[], datetime] = _utc_now,
    nonce: str | None = None,
) -> AuthorisationRequest:
    """Return the authorisation request to send a user into."""
    verifier = _b64(secrets.token_bytes(OIDC_CODE_VERIFIER_BYTES))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state = nonce if nonce is not None else _b64(secrets.token_bytes(OIDC_STATE_BYTES))

    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(config.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": OIDC_CODE_CHALLENGE_METHOD,
        }
    )
    separator = "&" if "?" in config.authorisation_endpoint else "?"
    return AuthorisationRequest(
        state=state,
        verifier=verifier,
        challenge=challenge,
        url=f"{config.authorisation_endpoint}{separator}{query}",
        created_at=clock(),
    )


@dataclass(slots=True)
class PendingAuthorisations:
    """The requests currently in flight, keyed by state.

    Bounded by expiry rather than by count: an entry lives ten minutes, which is
    how long a redirect a human is actually completing can take. Anything older
    is a request they abandoned, and keeping it is how a replay window opens.
    """

    clock: Callable[[], datetime] = _utc_now
    _pending: dict[str, AuthorisationRequest] = field(default_factory=dict)

    def remember(self, request: AuthorisationRequest) -> None:
        """Keep ``request`` until its redirect comes back, or it expires."""
        self.prune()
        self._pending[request.state] = request

    def claim(self, state: str) -> AuthorisationRequest:
        """Return the request ``state`` names, removing it, or raise.

        Removing it is the point: a state parameter is good for one redirect, so
        a replayed callback finds nothing and is refused.
        """
        self.prune()
        found = self._pending.pop(state, None)
        if found is None:
            raise SsoExchangeFailed("the state parameter matches no request in flight")
        return found

    def prune(self) -> None:
        """Forget requests whose redirect never came back."""
        now = self.clock()
        for state in [key for key, request in self._pending.items() if request.is_expired(now)]:
            del self._pending[state]

    def __len__(self) -> int:
        """Return how many sign-ins are in flight."""
        return len(self._pending)


@dataclass(frozen=True, slots=True)
class Identity:
    """Who the provider says this is, and where their groups put them.

    ``mapping`` is carried rather than resolved later so that "which team did
    this sign-in land in, and did it have to fall back" is answered in one place
    and audited from there.
    """

    subject: str
    email: str
    display_name: str
    groups: tuple[str, ...]
    mapping: GroupMapping

    @property
    def node_id(self) -> str | None:
        """Return the node this sign-in resolves to."""
        return self.mapping.node_id

    @property
    def used_default_team(self) -> bool:
        """Return whether no group mapped and the default was used."""
        return self.mapping.used_default


def read_claims(
    config: SsoConfig,
    claims: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> Identity:
    """Return the identity ``claims`` describe, or raise ``SsoExchangeFailed``.

    The signature and the ``aud``/``iss``/``exp`` checks belong to whatever
    verified the token — this reads an already-verified set. What it does check
    is that the claims are *usable*: a subject and an email, because a principal
    with neither cannot be stored, matched to an existing user, or named in an
    audit row.
    """
    moment = now if now is not None else _utc_now()

    issuer = str(claims.get("iss", ""))
    if issuer and issuer != config.issuer:
        raise SsoExchangeFailed(f"it came from {issuer!r} rather than the configured issuer")

    expires = claims.get("exp")
    if isinstance(expires, int | float):
        expired_at = datetime.fromtimestamp(float(expires), tz=UTC)
        if expired_at <= moment - CLOCK_SKEW:
            raise SsoExchangeFailed("the identity token had already expired")

    subject = str(claims.get(config.claims.subject, "") or "")
    email = str(claims.get(config.claims.email, "") or "")
    if not subject:
        raise SsoExchangeFailed(f"it carried no {config.claims.subject!r} claim")
    if not email:
        raise SsoExchangeFailed(f"it carried no {config.claims.email!r} claim")

    groups = _as_groups(claims.get(config.claims.groups))
    return Identity(
        subject=subject,
        email=email,
        display_name=str(claims.get(config.claims.display_name, "") or email),
        groups=groups,
        mapping=map_groups(config, groups),
    )


def _as_groups(value: Any) -> tuple[str, ...]:
    """Return the group claim as a tuple, whichever shape the provider used.

    Providers send a list, a space-separated string, or a comma-separated one,
    and a deployment does not get to choose which. Absent or unrecognisable
    means no groups, which is a mapping question rather than an error.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        separator = "," if "," in value else " "
        return tuple(part.strip() for part in value.split(separator) if part.strip())
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item))
    return ()


__all__ = [
    "AUTHORISATION_TTL",
    "AuthorisationRequest",
    "Identity",
    "PendingAuthorisations",
    "begin",
    "read_claims",
]
