"""Human sessions: a signed value, two bounds, and a list of the ones withdrawn.

A session is a signed cookie rather than a database row. Validating one happens
on every request a human makes, and a row read there buys nothing the cookie is
not already carrying — the principal, the tenant, when it started, when it was
last seen.

What a signed value cannot do is stop being valid early, and signing out has to
mean something. So there is a revocation list, and the thing that makes it
workable is the absolute lifetime: an entry only has to be kept until the
session it names would have expired anyway, so the list holds at most the
sessions withdrawn in the last twelve hours rather than every session ever
issued.

**The list is in-process by default, and that is a real bound.** One replica's
revocation does not reach another's memory. A single-process deployment — which
is what a self-hosted install starts as — is fully correct; a multi-replica one
supplies a shared ``RevocationList``, and the absolute lifetime is the ceiling
on how long a missed revocation can matter either way.
"""

from __future__ import annotations

import base64
import hmac
import json
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    SESSION_ABSOLUTE_LIFETIME_SECONDS,
    SESSION_ID_BYTES,
    SESSION_IDLE_TIMEOUT_SECONDS,
)
from platform.identity.errors import SessionRejected
from platform.identity.models import Session

IDLE_TIMEOUT = timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
ABSOLUTE_LIFETIME = timedelta(seconds=SESSION_ABSOLUTE_LIFETIME_SECONDS)

#: Separates the payload from its signature. A dot, so a cookie is one token
#: with no characters needing escaping in a Set-Cookie header.
_SEPARATOR = "."


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


def _b64(raw: bytes) -> str:
    """Return URL-safe base64 without padding, which cookies dislike."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(encoded: str) -> bytes:
    """Return the bytes ``encoded`` stands for, padding restored."""
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


@dataclass(frozen=True, slots=True)
class SessionSigner:
    """Signs a session payload, and refuses one it did not sign.

    HMAC rather than a JWT. There is exactly one issuer and one verifier here,
    both this process, so the algorithm negotiation a JWT carries is a
    negotiation with nobody — and it is the part of JWT that has produced the
    interesting vulnerabilities.
    """

    key: bytes

    def sign(self, payload: dict[str, Any]) -> str:
        """Return the cookie value for ``payload``."""
        body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return f"{body}{_SEPARATOR}{self._tag(body)}"

    def unsign(self, cookie: str) -> dict[str, Any]:
        """Return the payload, or raise ``SessionRejected``.

        Every failure — a missing separator, bad base64, a wrong signature,
        something that is not an object — raises the same thing. Distinguishing
        them would tell whoever is probing which part they got right.
        """
        body, separator, signature = cookie.partition(_SEPARATOR)
        if not separator or not body or not signature:
            raise SessionRejected("malformed")
        if not hmac.compare_digest(signature, self._tag(body)):
            raise SessionRejected("bad signature")
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, UnicodeDecodeError) as broken:
            raise SessionRejected("malformed") from broken
        if not isinstance(payload, dict):
            raise SessionRejected("malformed")
        return payload

    def _tag(self, body: str) -> str:
        """Return the signature for an encoded body."""
        return _b64(hmac.new(self.key, body.encode("ascii"), sha256).digest())


@runtime_checkable
class RevocationList(Protocol):
    """The sessions withdrawn before their expiry.

    A protocol, because a deployment with more than one replica needs the list
    to be shared and the obvious implementations — a Redis set, a table — are
    not this package's business. The contract is small on purpose.
    """

    def add(self, session_id: str, *, until: datetime) -> None:
        """Withdraw ``session_id`` until it would have expired anyway."""

    def contains(self, session_id: str, *, now: datetime) -> bool:
        """Return whether ``session_id`` has been withdrawn and not yet lapsed."""

    def prune(self, *, now: datetime) -> None:
        """Forget entries whose sessions have expired on their own."""


@dataclass(slots=True)
class InMemoryRevocationList:
    """The default list: correct in one process, and bounded by the lifetime."""

    _entries: dict[str, datetime] = field(default_factory=dict)

    def add(self, session_id: str, *, until: datetime) -> None:
        """Withdraw ``session_id`` until ``until``."""
        self._entries[session_id] = until

    def contains(self, session_id: str, *, now: datetime) -> bool:
        """Return whether ``session_id`` is currently withdrawn."""
        until = self._entries.get(session_id)
        if until is None:
            return False
        if now >= until:
            del self._entries[session_id]
            return False
        return True

    def prune(self, *, now: datetime) -> None:
        """Forget entries whose sessions have expired on their own."""
        for session_id in [key for key, until in self._entries.items() if now >= until]:
            del self._entries[session_id]

    def __len__(self) -> int:
        """Return how many withdrawals are still being remembered."""
        return len(self._entries)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A session and the cookie that carries it."""

    session: Session
    cookie: str


@dataclass(slots=True)
class SessionStore:
    """Issues, validates, refreshes, and withdraws human sessions."""

    signer: SessionSigner
    revoked: RevocationList = field(default_factory=InMemoryRevocationList)
    idle_timeout: timedelta = IDLE_TIMEOUT
    absolute_lifetime: timedelta = ABSOLUTE_LIFETIME
    clock: Callable[[], datetime] = _utc_now
    #: Which principals have had *every* session withdrawn, and from when. Kept
    #: separately from the per-session list because "sign this person out
    #: everywhere" must also cover sessions this replica has never seen.
    _revoked_principals: dict[str, datetime] = field(default_factory=dict)

    def issue(
        self,
        *,
        principal_id: str,
        org_id: str,
        node_id: str | None = None,
        groups: Iterable[str] = (),
        break_glass: bool = False,
        lifetime: timedelta | None = None,
    ) -> IssuedSession:
        """Return a new session and the cookie it travels in.

        ``lifetime`` may only shorten. A caller that could lengthen it would be
        a caller that had opted out of the absolute bound, which is the one an
        active user cannot extend by staying active.
        """
        now = self.clock()
        bound = min(lifetime, self.absolute_lifetime) if lifetime else self.absolute_lifetime
        session = Session(
            session_id=secrets.token_urlsafe(SESSION_ID_BYTES),
            principal_id=principal_id,
            org_id=org_id,
            issued_at=now,
            last_seen_at=now,
            expires_at=now + bound,
            node_id=node_id,
            break_glass=break_glass,
            groups=tuple(groups),
        )
        return IssuedSession(session=session, cookie=self.signer.sign(_encode(session)))

    def validate(self, cookie: str) -> Session:
        """Return the session ``cookie`` carries, or raise ``SessionRejected``."""
        session = _decode(self.signer.unsign(cookie))
        now = self.clock()

        if session.is_expired(now, idle_timeout=self.idle_timeout):
            raise SessionRejected("expired or idle", session_id=session.session_id)
        if self.revoked.contains(session.session_id, now=now):
            raise SessionRejected("revoked", session_id=session.session_id)

        withdrawn_at = self._revoked_principals.get(session.principal_id)
        if withdrawn_at is not None and session.issued_at <= withdrawn_at:
            raise SessionRejected("the principal was signed out", session_id=session.session_id)
        return session

    def touch(self, cookie: str) -> IssuedSession:
        """Return the session refreshed against the idle bound.

        The absolute expiry is carried over untouched. Re-deriving it here is
        how an idle timeout quietly becomes the only bound there is.
        """
        session = self.validate(cookie)
        refreshed = Session(
            session_id=session.session_id,
            principal_id=session.principal_id,
            org_id=session.org_id,
            issued_at=session.issued_at,
            last_seen_at=self.clock(),
            expires_at=session.expires_at,
            node_id=session.node_id,
            break_glass=session.break_glass,
            groups=session.groups,
        )
        return IssuedSession(session=refreshed, cookie=self.signer.sign(_encode(refreshed)))

    def revoke(self, session_id: str) -> None:
        """Withdraw one session, until it would have expired anyway."""
        self.revoked.add(session_id, until=self.clock() + self.absolute_lifetime)

    def revoke_for_principal(self, principal_id: str) -> None:
        """Withdraw every session this principal holds, present and in flight."""
        self._revoked_principals[principal_id] = self.clock()

    def prune(self) -> None:
        """Forget withdrawals whose sessions have expired on their own."""
        now = self.clock()
        self.revoked.prune(now=now)
        cutoff = now - self.absolute_lifetime
        for principal_id in [key for key, at in self._revoked_principals.items() if at <= cutoff]:
            del self._revoked_principals[principal_id]


def _encode(session: Session) -> dict[str, Any]:
    """Return the payload a cookie carries. Short keys: a cookie has a size limit."""
    return {
        "sid": session.session_id,
        "sub": session.principal_id,
        "org": session.org_id,
        "iat": session.issued_at.isoformat(),
        "seen": session.last_seen_at.isoformat(),
        "exp": session.expires_at.isoformat(),
        "node": session.node_id,
        "bg": session.break_glass,
        "grp": list(session.groups),
    }


def _decode(payload: dict[str, Any]) -> Session:
    """Return the session ``payload`` describes, or raise if it is not one.

    The signature has already been checked, so this is not defending against
    forgery — it is defending against a payload written by an older version of
    this code, which is a thing that happens on every rolling deployment.
    """
    try:
        return Session(
            session_id=str(payload["sid"]),
            principal_id=str(payload["sub"]),
            org_id=str(payload["org"]),
            issued_at=datetime.fromisoformat(str(payload["iat"])),
            last_seen_at=datetime.fromisoformat(str(payload["seen"])),
            expires_at=datetime.fromisoformat(str(payload["exp"])),
            node_id=None if payload.get("node") is None else str(payload["node"]),
            break_glass=bool(payload.get("bg", False)),
            groups=tuple(str(group) for group in payload.get("grp", ())),
        )
    except (KeyError, TypeError, ValueError) as broken:
        raise SessionRejected("malformed") from broken


__all__ = [
    "ABSOLUTE_LIFETIME",
    "IDLE_TIMEOUT",
    "InMemoryRevocationList",
    "IssuedSession",
    "RevocationList",
    "SessionSigner",
    "SessionStore",
]
