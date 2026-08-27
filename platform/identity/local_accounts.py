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

**A created person is not the environment account, and signs in as themself.**
Somebody made through ``POST /identity/principals`` gets a stored local
password of their own (``User.local_password_hash``). ``LocalSignIn.sign_in``
accepts either that credential or the environment account's, and the token it
returns names whichever one actually matched — never the local administrator
by default. The door stays the same one: a deployment that never configured
``account`` still refuses everybody, a created person included, because that
field being set is the door, not this feature.
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


def hash_local_password(password: str) -> str:
    """Return the stored form of a person's initial local password.

    The same memory-hard hash the environment-configured account already
    uses (``LocalAccount.password_hash``, via ``hash_secret``) — one hashing
    path for every local passphrase this deployment stores, not a second one
    invented for whoever gets created after the first account did.
    """
    return hash_secret(password)


#: A syntactically valid hash that no stored passphrase produces, computed once
#: at import rather than per request. Compared against whenever a sign-in's
#: ``username`` does not resolve to a created principal with a stored local
#: password, so that comparison costs exactly what a real one costs. Skipping
#: it for an email that matches nobody would let the response time say what
#: the refusal message is built not to: whether that email belongs to anybody
#: at all.
_NO_SUCH_LOCAL_PASSWORD_HASH = hash_secret("no stored local password is ever this value")


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
        """Return a freshly issued token for whoever this credential names, or refuse.

        Two identities can answer: the environment-configured account, and a
        person created through ``POST /identity/principals`` with a local
        password of their own. Both are always checked, in full, whether or
        not the first one already matched — which one (if either) did is not
        something a caller, or a stopwatch, can tell apart from the outside.

        The refusal is one exception with one message for every way of being
        wrong — a wrong name, a wrong passphrase, no local sign-in enabled at
        all, or a principal that exists but has no stored password. The
        *audit* distinguishes the broad outcomes, because the operator reading
        it afterwards is on our side and the person at the form is not
        necessarily.

        Raises:
            LocalSignInRejected: the credential was not accepted.
        """
        scope = TenantScope(org_id=org_id)

        # The door is this field being set, deployment-wide — *or* a
        # deliberate opening somebody registered while this process was
        # already up, without a restart. Read unconditionally, before either
        # branch below, so the shape of a refusal never depends on which of
        # the two (if either) is why this deployment is open: a name that
        # exists and a name that does not must cost exactly the same,
        # whichever mechanism opened the door. A principal created through
        # the identity route opens neither of these on its own: creating one
        # must not turn a deployment that only has an identity provider into
        # a deployment with a second entrance.
        door_open = self.account is not None or await self._local_sign_in_is_open(scope)
        if not door_open:
            await self._record(scope, username, outcome="no local sign-in is enabled")
            raise LocalSignInRejected

        account_matches = self.account is not None and self.account.verify(username, password)
        created_principal_id = await self._resolve_created_principal(scope, username, password)

        if account_matches:
            await self._ensure_principal(scope)
            matched_user_id = LOCAL_ACCOUNT_PRINCIPAL_ID
        elif created_principal_id is not None:
            matched_user_id = created_principal_id
        else:
            await self._record(scope, username, outcome="rejected")
            _LOG.warning("identity.local_sign_in_rejected", username=username)
            raise LocalSignInRejected

        issued = await self.tokens.issue(
            scope,
            self._context(matched_user_id),
            user_id=matched_user_id,
            name=CREDENTIAL_NAME,
            description="Issued by a local sign-in.",
            lifetime=self.lifetime,
            # This token stands in for the person, not for one declared
            # purpose — it must keep resolving to whatever the account
            # currently holds, not to nothing.
            unscoped=True,
        )
        await self._record(
            scope,
            username,
            outcome="accepted",
            actor_id=matched_user_id,
            token_id=issued.token.token_id,
            success=True,
        )
        _LOG.info("identity.local_sign_in", principal=matched_user_id)
        return issued

    # --- The pieces ---------------------------------------------------------------

    async def _local_sign_in_is_open(self, scope: TenantScope) -> bool:
        """Return whether this deployment registered an opening.

        One indexed read of a single-row table, made unconditionally rather
        than short-circuited by anything the caller supplied — a passphrase
        never enters this decision.
        """
        async with self.gateway.begin(scope) as uow:
            return await uow.identity.local_sign_in_opening() is not None

    async def _resolve_created_principal(
        self, scope: TenantScope, username: str, password: str
    ) -> str | None:
        """Return the id of the created principal this credential names, or ``None``.

        Looked up by email, and verified in the same constant-time shape
        ``LocalAccount.verify`` already uses for the environment account: the
        passphrase always runs through ``verify_secret``, against the stored
        hash when ``username`` names somebody who has one, and against
        ``_NO_SUCH_LOCAL_PASSWORD_HASH`` otherwise. The comparison is never
        skipped, so an email that resolves to nobody costs exactly what a known
        email with the wrong passphrase costs.
        """
        async with self.gateway.begin(scope) as uow:
            candidate = await uow.identity.find_user_by_email(username)
        stored_hash = candidate.local_password_hash if candidate is not None else None
        matches = verify_secret(password, stored_hash or _NO_SUCH_LOCAL_PASSWORD_HASH)
        if candidate is None or stored_hash is None or not matches:
            return None
        return candidate.user_id

    async def _ensure_principal(self, scope: TenantScope) -> None:
        """Create the local admin and its owner grant, idempotently.

        ``upsert`` on both, so signing in twice writes the same two rows rather
        than accumulating an administrator per restart. Runs only when the
        environment account itself matched — a created principal already
        exists, made by ``POST /identity/principals``, and this must never
        touch it.
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

    def _context(self, user_id: str) -> AuditContext:
        return AuditContext(actor_kind=ActorKind.USER, actor_id=user_id)

    async def _record(
        self,
        scope: TenantScope,
        username: str,
        *,
        outcome: str,
        actor_id: str = LOCAL_ACCOUNT_PRINCIPAL_ID,
        token_id: str = "",
        success: bool = False,
    ) -> None:
        """File the attempt, accepted or not.

        The attempted name is recorded and the passphrase is not, in any form.
        A rejected sign-in whose username nobody kept is one an operator cannot
        tell from a typo six months later. ``actor_id`` is who the record
        attributes the attempt to: the principal that actually signed in, on
        success; the same placeholder this has always used on a refusal, since
        nobody has been authenticated yet to attribute it to instead.
        """
        if self.recorder is None:
            return
        await self.recorder.record(
            scope,
            self._context(actor_id),
            action=LOCAL_ACCOUNT_AUDIT_ACTION,
            resource_kind=_AUDIT_RESOURCE_KIND,
            resource_id=token_id or LOCAL_ACCOUNT_PRINCIPAL_ID,
            outcome=AuditOutcome.ALLOWED if success else AuditOutcome.DENIED,
            detail={"username": username, "outcome": outcome},
        )


__all__ = [
    "CREDENTIAL_NAME",
    "SESSION_LIFETIME",
    "LocalAccount",
    "LocalSignIn",
    "UnsafeDefaultPassword",
    "hash_local_password",
]
