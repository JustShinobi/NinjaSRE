"""The ordinary way in when there is no identity provider: a name and a passphrase.

Somebody has to be able to sign in to a deployment on its first day, and on that
day there is no directory to authenticate against and nowhere an API token could
have come from. "Paste a token" is a sign-in that presumes an earlier sign-in.

So a local account exists, and it is deliberately the *dull* sibling of
break-glass next door. Break-glass is the emergency path — fifteen minutes, a
written reason, an error-level log line, permissions built in memory so it works
when the identity data does not. This one is none of that. It is how a person
signs in on an ordinary Tuesday, and everything about it is arranged to be
ordinary:

**It ends in a token, not a session of its own.** Verifying the passphrase is
the only thing this module does that is new; what it hands back is an API token
issued through the same service every other credential comes from. That is what
lets the rest of the deployment stay ignorant of how somebody signed in — the
bearer on the next request is a token, resolvable by the one code path that
resolves tokens, expiring and revocable like any other.

**The account is a real principal.** Upserted, with an owner grant, so a second
sign-in writes the same row rather than a second admin, and so the permissions
it holds come from the catalogue rather than from a special case.

**The shipped passphrase cannot reach production.** It is refused unless the
deployment also declares itself a demonstration — see ``from_environment``. A
default credential that is merely documented as "change this" is a default
credential that ships.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from config.constants.security import (
    LOCAL_ACCOUNT_AUDIT_ACTION,
    LOCAL_ACCOUNT_DEFAULT_PASSWORD,
    LOCAL_ACCOUNT_DEMO_ENV,
    LOCAL_ACCOUNT_PASSWORD_HASH_ENV,
    LOCAL_ACCOUNT_PRINCIPAL_ID,
    LOCAL_ACCOUNT_SESSION_SECONDS,
    LOCAL_ACCOUNT_USERNAME,
    LOCAL_ACCOUNT_USERNAME_ENV,
)
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.break_glass import hash_secret, verify_secret
from platform.identity.errors import LocalSignInRejected, UnsafeDefaultPassword
from platform.identity.models import IssuedToken
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, PrincipalKind, TenantScope
from platform.persistence.ports.audit_repository import AuditOutcome
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.transaction import PersistenceGateway

_LOG = get_logger(__name__)

#: How long a token issued by a local sign-in lasts.
SESSION_LIFETIME = timedelta(seconds=LOCAL_ACCOUNT_SESSION_SECONDS)

#: What the issued token is called in the token list, so an operator reading it
#: can tell a sign-in from a machine credential somebody minted on purpose.
CREDENTIAL_NAME = "Console sign-in"

#: The resource kind the audit trail files a sign-in under.
_AUDIT_RESOURCE_KIND = "session"


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LocalAccount:
    """The account a deployment configures, as a name and a stored passphrase."""

    password_hash: str
    username: str = LOCAL_ACCOUNT_USERNAME
    display_name: str = "Local administrator"

    def verify(self, username: str, password: str) -> bool:
        """Return whether this pair is the account's, in constant time.

        Both halves are compared even when the name is already wrong. Returning
        early on the name would make a wrong name measurably faster than a wrong
        passphrase, which is the same answer the error message refuses to give,
        arrived at with a stopwatch.
        """
        name_matches = hmac.compare_digest(username, self.username)
        password_matches = verify_secret(password, self.password_hash)
        return name_matches and password_matches

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> LocalAccount | None:
        """Return the account this environment configures, or ``None`` for no account.

        ``None`` rather than a default-on account: a way in that nobody asked
        for is a way in, and a deployment that has an identity provider should
        not acquire a second door by installing this release.

        Raises:
            UnsafeDefaultPassword: the passphrase is the one this project ships
                with and the deployment has not declared itself a demonstration.
        """
        stored = environ.get(LOCAL_ACCOUNT_PASSWORD_HASH_ENV, "").strip()
        is_demo = environ.get(LOCAL_ACCOUNT_DEMO_ENV, "").strip() != ""
        username = environ.get(LOCAL_ACCOUNT_USERNAME_ENV, "").strip() or LOCAL_ACCOUNT_USERNAME

        if not stored:
            # The demo profile is the one case where an unconfigured deployment
            # still gets an account: the whole point of that profile is that it
            # comes up ready to be looked at.
            if not is_demo:
                return None
            return cls(password_hash=hash_secret(LOCAL_ACCOUNT_DEFAULT_PASSWORD), username=username)

        if not is_demo and verify_secret(LOCAL_ACCOUNT_DEFAULT_PASSWORD, stored):
            raise UnsafeDefaultPassword(LOCAL_ACCOUNT_PASSWORD_HASH_ENV, LOCAL_ACCOUNT_DEMO_ENV)

        return cls(password_hash=stored, username=username)


@dataclass(slots=True)
class LocalSignIn:
    """Turns a name and a passphrase into a token the rest of the deployment accepts."""

    gateway: PersistenceGateway
    tokens: TokenService
    account: LocalAccount | None = None
    recorder: AuditRecorder | None = None
    clock: Callable[[], datetime] = _utc_now
    lifetime: timedelta = field(default=SESSION_LIFETIME)

    async def sign_in(self, username: str, password: str, *, org_id: str) -> IssuedToken:
        """Return a freshly issued token for the local account, or refuse.

        The refusal is one exception with one message for every way of being
        wrong, including "this deployment has no local account at all". The
        *audit* distinguishes them, because the operator reading it afterwards is
        on our side and the person at the form is not necessarily.

        Raises:
            LocalSignInRejected: the credential was not accepted.
        """
        scope = TenantScope(org_id=org_id)

        if self.account is None:
            await self._record(scope, username, outcome="no local account is configured")
            raise LocalSignInRejected

        if not self.account.verify(username, password):
            await self._record(scope, username, outcome="rejected")
            _LOG.warning("identity.local_sign_in_rejected", username=username)
            raise LocalSignInRejected

        await self._ensure_principal(scope)
        issued = await self.tokens.issue(
            scope,
            self._context(),
            user_id=LOCAL_ACCOUNT_PRINCIPAL_ID,
            name=CREDENTIAL_NAME,
            description="Issued by a local sign-in.",
            lifetime=self.lifetime,
        )
        await self._record(
            scope,
            username,
            outcome="accepted",
            token_id=issued.token.token_id,
            success=True,
        )
        _LOG.info("identity.local_sign_in", principal=LOCAL_ACCOUNT_PRINCIPAL_ID)
        return issued

    # --- The pieces ---------------------------------------------------------------

    async def _ensure_principal(self, scope: TenantScope) -> None:
        """Create the local admin and its owner grant, idempotently.

        ``upsert`` on both, so signing in twice writes the same two rows rather
        than accumulating an administrator per restart.
        """
        async with self.gateway.begin(scope) as uow:
            await uow.identity.upsert_user(
                User(
                    user_id=LOCAL_ACCOUNT_PRINCIPAL_ID,
                    email=f"{LOCAL_ACCOUNT_PRINCIPAL_ID}@localhost",
                    display_name="Local administrator",
                    kind=PrincipalKind.USER,
                )
            )
            await uow.identity.upsert_role_binding(
                RoleBinding(
                    binding_id=f"{LOCAL_ACCOUNT_PRINCIPAL_ID}-owner",
                    user_id=LOCAL_ACCOUNT_PRINCIPAL_ID,
                    role=Role.OWNER.value,
                    node_id=None,
                )
            )

    def _context(self) -> AuditContext:
        return AuditContext(actor_kind=ActorKind.USER, actor_id=LOCAL_ACCOUNT_PRINCIPAL_ID)

    async def _record(
        self,
        scope: TenantScope,
        username: str,
        *,
        outcome: str,
        token_id: str = "",
        success: bool = False,
    ) -> None:
        """File the attempt, accepted or not.

        The attempted name is recorded and the passphrase is not, in any form.
        A rejected sign-in whose username nobody kept is one an operator cannot
        tell from a typo six months later.
        """
        if self.recorder is None:
            return
        await self.recorder.record(
            scope,
            self._context(),
            action=LOCAL_ACCOUNT_AUDIT_ACTION,
            resource_kind=_AUDIT_RESOURCE_KIND,
            resource_id=token_id or LOCAL_ACCOUNT_PRINCIPAL_ID,
            outcome=AuditOutcome.ALLOWED if success else AuditOutcome.DENIED,
            detail={"username": username, "outcome": outcome},
        )


__all__ = ["CREDENTIAL_NAME", "SESSION_LIFETIME", "LocalAccount", "LocalSignIn"]
