"""What this package raises, named so a caller can tell the cases apart.

Two rules run through every message here.

**A denial says what to ask for.** "Forbidden" is a dead end; an operator who
knows they need ``config.write`` at ``payments`` can request it, and the request
is reviewable. The reason it is a requirement is that a denial
nobody can act on is a denial they route around.

**A rejection never says which guess was close.** ``TokenRejected`` carries a
reason the *operator* can read in the audit trail, and the transport turns every
one of them into the same response. Telling a caller that their token was
recognised but expired tells them the token was recognised.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from platform.identity.permissions import Permission, Role, roles_granting


class IdentityError(Exception):
    """Base for every failure raised by the identity layer."""


# --- Authorisation -----------------------------------------------------------


class PermissionDenied(IdentityError):
    """A principal lacked the permission a route declared.

    Names the permission, the scope, and the least privileged role that would
    have granted it — so the message is a request somebody can approve rather
    than a wall.
    """

    def __init__(
        self,
        permission: Permission,
        *,
        node_id: str | None = None,
        principal_id: str | None = None,
    ) -> None:
        where = f"at {node_id!r}" if node_id is not None else "in this organisation"
        sufficient = roles_granting(permission)
        remedy = (
            f" The {sufficient[0].value!r} role grants it."
            if sufficient
            else " No role grants it, which is a defect in the catalogue."
        )
        super().__init__(f"This action needs {permission.value!r} {where}.{remedy}")
        self.permission = permission
        self.node_id = node_id
        self.principal_id = principal_id
        self.sufficient_roles = sufficient


class LastOwnerRemoval(IdentityError):
    """An operation would have left the organisation with no owner.

    Names who would have been the last one. An operator who meant to hand over
    ownership needs to know they have to grant the replacement first — or in the
    same call, which ``require_owner_retained`` supports.
    """

    def __init__(self, remaining_owner_ids: Sequence[str]) -> None:
        listed = ", ".join(sorted(remaining_owner_ids))
        super().__init__(
            f"This would leave the organisation with no owner ({listed} would be the last). "
            f"Grant ownership to somebody else first, or in the same operation."
        )
        self.remaining_owner_ids = tuple(sorted(remaining_owner_ids))


class UnknownRole(IdentityError):
    """A stored grant names a role this build does not have."""

    def __init__(self, name: str) -> None:
        listed = ", ".join(role.value for role in Role)
        super().__init__(f"No role named {name!r}. This deployment has: {listed}.")
        self.name = name


# --- Tokens ------------------------------------------------------------------


class TokenRejected(IdentityError):
    """A presented bearer token was not accepted.

    One type for every cause, and the cause in ``reason`` rather than in the
    class. A caller that could distinguish "expired" from "never existed" by
    catching a different exception would eventually distinguish them in a
    response body.
    """

    def __init__(self, reason: str, *, token_id: str | None = None) -> None:
        super().__init__("This token was rejected.")
        self.reason = reason
        self.token_id = token_id


class TokenLifetimeTooLong(IdentityError):
    """A token was asked for with an expiry beyond the ceiling."""

    def __init__(self, requested_days: int, limit_days: int) -> None:
        super().__init__(
            f"A {requested_days}-day token exceeds the {limit_days}-day ceiling. A token "
            f"nobody remembers issuing is the one still working after its owner leaves."
        )
        self.requested_days = requested_days
        self.limit_days = limit_days


class TooManyRevocations(IdentityError):
    """A bulk revocation covered more tokens than one operation may."""

    def __init__(self, requested: int, limit: int) -> None:
        super().__init__(
            f"This would revoke {requested} tokens and the limit is {limit}. A single call "
            f"that could revoke a whole deployment is not a control."
        )
        self.requested = requested
        self.limit = limit


# --- Sessions ----------------------------------------------------------------


class SessionRejected(IdentityError):
    """A presented session was not accepted: forged, expired, idle, or revoked."""

    def __init__(self, reason: str, *, session_id: str | None = None) -> None:
        super().__init__("This session is no longer valid. Sign in again.")
        self.reason = reason
        self.session_id = session_id


# --- Single sign-on ----------------------------------------------------------


class SsoConfigInvalid(IdentityError):
    """An SSO configuration was refused before it could be stored."""

    def __init__(self, problems: Sequence[str]) -> None:
        listed = "\n  - ".join(problems)
        super().__init__(f"This SSO configuration cannot be used:\n  - {listed}")
        self.problems = tuple(problems)


class SsoNotVerified(IdentityError):
    """An SSO configuration was activated before it had been tested.

    Refused rather than warned about. A misconfiguration that reaches live
    sign-in locks every human out of the tool they use to fix things.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider!r} SSO configuration has not passed a test sign-in. Run the test "
            f"first: activating an untested provider is how an operator locks themselves out."
        )
        self.provider = provider


class SsoExchangeFailed(IdentityError):
    """An authorisation code exchange did not produce a usable identity."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"The identity provider's response could not be used: {reason}")
        self.reason = reason


# --- Impersonation and break-glass -------------------------------------------


class ImpersonationRejected(IdentityError):
    """An impersonation was refused, or an expired one was presented."""

    def __init__(self, reason: str, *, expires_at: datetime | None = None) -> None:
        super().__init__(f"This impersonation cannot be used: {reason}")
        self.reason = reason
        self.expires_at = expires_at


class BreakGlassRejected(IdentityError):
    """A break-glass session was refused.

    The reason is in the message because the person reading it is an operator
    standing in front of an outage with no other way in. Ambiguity costs them
    minutes they do not have.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Break-glass access was refused: {reason}")
        self.reason = reason


class LocalSignInRejected(IdentityError):
    """A sign-in with the local account's name and passphrase was refused.

    Unlike break-glass, the message carries no reason and is the same for every
    refusal. The person reading this one is at a sign-in page rather than in an
    outage, and the difference between "no such account" and "wrong passphrase"
    is worth more to somebody guessing than to them.
    """

    def __init__(self) -> None:
        super().__init__("the credential was not accepted")


# --- Local administrator enrolment --------------------------------------------


class LocalAdministratorNameTaken(IdentityError):
    """The name a caller asked to create already signs in to this deployment.

    Distinct from a plain duplicate: the remedy is in the message, because
    the caller almost certainly meant one of two things — create somebody
    else, or rotate this name's passphrase — and guessing which one silently
    would be wrong exactly as often as it was right.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name!r} already signs in to this deployment. To replace that "
            f"passphrase instead of creating a new administrator, run the same "
            f"command again with rotation requested explicitly."
        )
        self.name = name


class LocalSignInAlreadyOpen(IdentityError):
    """The bootstrap credential was exchanged, but this deployment is already administered.

    Distinct from the bootstrap credential simply being spent or missing —
    ``TokenRejected`` already covers that. This is the case where the
    credential file is still on the host, still authenticates, and the
    exchange would otherwise mint a second, unintended administrator: a
    stale file left over from before somebody ran the CLI command, or from
    an identity provider that was activated afterwards.
    """

    def __init__(self) -> None:
        super().__init__(
            "this deployment already has a local administrator. Use "
            "'ninjasre setup admin --rotate' to change a passphrase, or "
            "create another administrator with a different name."
        )


class LocalEnrolmentBlockedBySso(IdentityError):
    """A local administrator cannot be created or rotated while SSO is active.

    Deliberately offers no override: a flag that bypassed this would be the
    second door the product exists to not have. Whoever is locked out has the
    break-glass path instead, which already carries its own deadline, its own
    written reason, and its own error-level log line.
    """

    def __init__(self, *, emergency_path: str) -> None:
        super().__init__(
            f"This deployment's identity provider is its way in. Local "
            f"administrator accounts cannot be created or changed while it is "
            f"active. If you are locked out, use {emergency_path} instead."
        )
        self.emergency_path = emergency_path


class UnsafeDefaultPassword(IdentityError):
    """A deployment that is not the demo still has the shipped passphrase.

    Raised while the account is being resolved, so it stops the process coming
    up rather than the first sign-in. A deployment that boots and only refuses
    later is one somebody puts in front of users first.
    """

    def __init__(self, hash_env: str, demo_env: str) -> None:
        super().__init__(
            f"{hash_env} is still the passphrase this project ships with. Set it to the "
            f"stored form of a passphrase of your own, or set {demo_env} if this really is "
            f"a demonstration deployment."
        )


# --- Audit -------------------------------------------------------------------


class AuditWriteFailed(IdentityError):
    """An audit record could not be stored.

    Raised *after* the fallback has been written, never instead of it. The
    action being audited has usually already happened, and the one outcome that
    is not acceptable is proceeding as though nothing needed recording.
    """

    def __init__(self, action: str, *, fallback_path: str | None = None) -> None:
        where = f" It was written to {fallback_path}." if fallback_path else ""
        super().__init__(
            f"The audit record for {action!r} could not be stored.{where} "
            f"This is a serious error: the action happened and the trail is incomplete."
        )
        self.action = action
        self.fallback_path = fallback_path


class AuditMutationPath(IdentityError):
    """A repository exposed a way to change or remove an audit record.

    Raised at startup by ``audit.guard``, so a build that grew one fails to boot
    rather than failing a review months later.
    """

    def __init__(self, subject: str, methods: Sequence[str]) -> None:
        listed = ", ".join(sorted(methods))
        super().__init__(
            f"{subject} exposes {listed}, which would make the audit log editable. An audit "
            f"log an administrator can edit is not evidence. Remove the method."
        )
        self.subject = subject
        self.methods = tuple(sorted(methods))


__all__ = [
    "AuditMutationPath",
    "AuditWriteFailed",
    "BreakGlassRejected",
    "IdentityError",
    "ImpersonationRejected",
    "LastOwnerRemoval",
    "LocalAdministratorNameTaken",
    "LocalEnrolmentBlockedBySso",
    "LocalSignInAlreadyOpen",
    "LocalSignInRejected",
    "PermissionDenied",
    "SessionRejected",
    "SsoConfigInvalid",
    "SsoExchangeFailed",
    "SsoNotVerified",
    "TokenLifetimeTooLong",
    "TokenRejected",
    "TooManyRevocations",
    "UnknownRole",
    "UnsafeDefaultPassword",
]
