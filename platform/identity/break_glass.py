"""The way in when the identity provider is not.

A local admin account is a weakness on any other day and the difference between
a bad hour and a bad week on this one. An SSO outage locks every human out of
the platform they would use to investigate the outage; "wait for the identity
provider" is not an incident response.

So it exists, and everything about it is arranged to make it expensive to abuse
and cheap to detect:

**It depends on nothing that can be down.** A password hash in the deployment's
own configuration, verified in this process. No directory, no network, no
provider — because the situation it exists for is the one where those are gone.

**It is short.** Fifteen minutes, shorter than an ordinary session and shorter
than an impersonation, because it should expire before the outage does.

**It has to say why, and the reason is kept.** At least a sentence, recorded on
the audit event, and refused if absent. The row an operator reads six months
later needs to answer "why did somebody use this", and nothing reconstructs that
after the fact.

**Every use is loud.** An audit event flagged as break-glass, and an error-level
log line — not informational. A break-glass sign-in that nobody noticed is the
one that was not an emergency.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config.constants.security import (
    BREAK_GLASS_AUDIT_ACTION,
    BREAK_GLASS_MAX_DURATION_SECONDS,
    BREAK_GLASS_MIN_REASON_CHARS,
    BREAK_GLASS_PRINCIPAL_ID,
    IDENTITY_AUDIT_RESOURCE_KIND_SESSION,
)
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.authorisation import PermissionSet
from platform.identity.errors import BreakGlassRejected
from platform.identity.models import Grant, Principal
from platform.identity.permissions import Role
from platform.identity.sessions import IssuedSession, SessionStore
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, PrincipalKind, TenantScope

_LOG = get_logger(__name__)

MAX_DURATION = timedelta(seconds=BREAK_GLASS_MAX_DURATION_SECONDS)

#: scrypt parameters. The cost is deliberately high for a credential used a
#: handful of times a year: the account is a standing target and nothing about
#: an emergency is made worse by a sign-in taking a fraction of a second longer.
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_BYTES = 32
_SALT_BYTES = 16

#: scrypt needs ``128 · N · r`` bytes, and OpenSSL refuses outright rather than
#: allocating more than it was told it could. Stated as the formula so changing
#: the cost above cannot leave a ceiling behind that rejects every sign-in.
_SCRYPT_MAX_MEMORY = 2 * 128 * _SCRYPT_N * _SCRYPT_R


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


def hash_secret(secret: str, *, salt: bytes | None = None) -> str:
    """Return the stored form of a break-glass secret.

    A memory-hard KDF, unlike the token hasher next door. A token is 256 random
    bits and cannot be guessed; this is a passphrase a human types, and the
    entire defence against an offline attack on it is how slow each guess is.
    """
    used = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=used,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_BYTES,
        maxmem=_SCRYPT_MAX_MEMORY,
    )
    return f"scrypt${used.hex()}${derived.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    """Return whether ``secret`` matches ``stored``, in constant time."""
    try:
        scheme, salt_hex, _ = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(hash_secret(secret, salt=salt), stored)


@dataclass(frozen=True, slots=True)
class BreakGlassAccount:
    """The local admin, as a deployment configures it.

    Enabling it is explicit. A deployment that has an identity provider and no
    intention of ever using this leaves it disabled, and then there is no
    account to attack.
    """

    secret_hash: str
    principal_id: str = BREAK_GLASS_PRINCIPAL_ID
    enabled: bool = True

    def principal(self, org_id: str) -> Principal:
        """Return the principal a break-glass session acts as."""
        return Principal(
            principal_id=self.principal_id,
            org_id=org_id,
            kind=PrincipalKind.USER,
            display_name="Break-glass local administrator",
        )

    def permissions(self) -> PermissionSet:
        """Return what this account holds: ``owner``, over the organisation.

        Built in memory rather than read from a grant, and that is the point.
        The account has to work when the identity data an ordinary sign-in
        depends on is unusable — including the case where somebody removed the
        last owner's access by mistake, which is one of the two reasons this
        path exists at all.
        """
        return PermissionSet(
            grants=(
                Grant(
                    grant_id=f"{self.principal_id}-owner",
                    principal_id=self.principal_id,
                    role=Role.OWNER,
                    node_id=None,
                ),
            )
        )


@dataclass(slots=True)
class BreakGlass:
    """Opens a short, loudly audited local admin session."""

    sessions: SessionStore
    account: BreakGlassAccount | None = None
    recorder: AuditRecorder | None = None
    duration: timedelta = MAX_DURATION
    clock: Callable[[], datetime] = _utc_now

    async def open(
        self,
        scope: TenantScope,
        *,
        secret: str,
        reason: str,
        source_address: str | None = None,
    ) -> IssuedSession:
        """Return a break-glass session, or raise saying why not.

        The refusals do not distinguish a wrong secret from a disabled account,
        for the usual reason. The *audit* distinguishes them, because the
        operator reading it afterwards is on our side.
        """
        if self.account is None or not self.account.enabled:
            await self._record(scope, reason, source_address, outcome="no local account")
            raise BreakGlassRejected("no local administrator is configured for this deployment")

        if len(reason.strip()) < BREAK_GLASS_MIN_REASON_CHARS:
            raise BreakGlassRejected(
                f"a break-glass sign-in has to say why, in at least "
                f"{BREAK_GLASS_MIN_REASON_CHARS} characters"
            )
        if self.duration > MAX_DURATION:
            raise BreakGlassRejected(f"a break-glass session may last at most {MAX_DURATION}")

        if not verify_secret(secret, self.account.secret_hash):
            await self._record(scope, reason, source_address, outcome="rejected")
            raise BreakGlassRejected("the credential was not accepted")

        issued = self.sessions.issue(
            principal_id=self.account.principal_id,
            org_id=scope.org_id,
            break_glass=True,
            lifetime=self.duration,
        )
        await self._record(scope, reason, source_address, outcome="opened", issued=issued)
        return issued

    def context(self, source_address: str | None = None) -> AuditContext:
        """Return the acting context every action in this session carries."""
        principal_id = (
            self.account.principal_id if self.account is not None else BREAK_GLASS_PRINCIPAL_ID
        )
        return AuditContext(
            actor_kind=ActorKind.USER,
            actor_id=principal_id,
            break_glass=True,
            source_address=source_address,
        )

    async def _record(
        self,
        scope: TenantScope,
        reason: str,
        source_address: str | None,
        *,
        outcome: str,
        issued: IssuedSession | None = None,
    ) -> None:
        """Audit the attempt, and say so in the log at error level.

        Error level for a *successful* sign-in, which is unusual and deliberate.
        The severity is about how much attention the event deserves, and this one
        deserves somebody's, whether or not it worked.
        """
        _LOG.error(
            "identity.break_glass",
            org_id=scope.org_id,
            outcome=outcome,
            reason=reason,
            source_address=source_address,
        )
        if self.recorder is None:
            return
        await self.recorder.record(
            scope,
            self.context(source_address),
            action=BREAK_GLASS_AUDIT_ACTION,
            resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_SESSION,
            resource_id=issued.session.session_id if issued is not None else "-",
            detail={
                "reason": reason,
                "result": outcome,
                "expires_at": issued.session.expires_at.isoformat() if issued else None,
            },
        )


__all__ = [
    "MAX_DURATION",
    "BreakGlass",
    "BreakGlassAccount",
    "hash_secret",
    "verify_secret",
]
