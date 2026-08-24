"""The one rule that opens a deployment's local sign-in, and the two callers that share it.

Before this module, a deployment's local sign-in existed only as a value an
operator set before the process started — the environment-configured account.
Two things it could not do: open later, without a restart, because the field
is read once at construction; and answer "who did this and when", because a
field carries no history.

Two callers reach the rule here, and neither owns it: the CLI's
``ninjasre setup admin`` and the route that exchanges the bootstrap credential
for a durable one. Both create the same shape of thing — a local
administrator, with a passphrase, granted the owner role — and both may be
the one that opens the door for a deployment that has never had one. Putting
the rule in either caller would leave the other maintaining a second copy of
it; this module exists so that neither has to.

**The door opens at most once, and the insert is the arbiter.** The first
successful ``open_local_sign_in`` wins; every other caller — racing it, or
simply arriving second — reads the same fact back rather than trying to
overwrite it. Creating a second, third, or fortieth administrator afterwards
never touches that fact again.

**Rotation revokes.** Replacing an administrator's passphrase is normally a
response to distrusting the old one, so a session opened with it does not
survive the replacement — the whole reason to rotate would otherwise still
work after the rotation.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from config.constants.security import (
    LOCAL_ADMIN_AUDIT_ACTION_ENROLLED,
    LOCAL_ADMIN_AUDIT_ACTION_ROTATED,
)
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.errors import LocalAdministratorNameTaken, LocalEnrolmentBlockedBySso
from platform.identity.local_accounts import hash_local_password
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.errors import DuplicateRecord
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.identity_repository import PrincipalKind, RoleBinding, User
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

#: Entropy in a freshly enrolled administrator's identifier. The same shape as
#: the identity route's own principal ids: caller-opaque, never derived from
#: the name given — a name is chosen by whoever calls, and an identifier taken
#: from it would make renaming indistinguishable from creating a second one.
_USER_ID_BYTES = 16

#: What an enrolment audit row names as the thing it acted on.
_AUDIT_RESOURCE_KIND = "local_administrator"

#: Named in a refusal rather than imported: platform/identity does not know
#: the HTTP path a route mounts break-glass at, only that this is the one the
#: route table declares public for it. A route-table lookup here would pull
#: gateway/ into platform/, which is the wrong direction.
BREAK_GLASS_ROUTE = "POST /auth/break-glass"


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class EnrolledAdministrator:
    """What one call to :func:`enrol_local_administrator` did."""

    user_id: str
    name: str
    #: ``True`` when an existing administrator's passphrase was replaced,
    #: ``False`` when a new one was created.
    rotated: bool
    #: ``True`` when this call is the one that opened this deployment's local
    #: sign-in. ``False`` for every call after the first, whichever caller —
    #: the CLI or the bootstrap exchange — happened to make it.
    opened: bool


async def identity_provider_is_active(gateway: PersistenceGateway, *, org_id: str) -> bool:
    """Return whether this deployment's identity provider is its way in.

    Read from the configuration tree's own ``policies.sso`` — the same field
    the console's SSO settings screen reads — resolved at the organisation
    root rather than at a caller's own node, because whether *this
    deployment* has an identity provider is a fact about the tenant as a
    whole, not about wherever a particular request happens to be scoped.
    """
    from platform.config_service.service import ConfigService

    scope = TenantScope(org_id=org_id)
    async with gateway.begin(scope) as uow:
        root = await uow.config.root()
    service = ConfigService(gateway=gateway, scope=scope)
    effective = await service.resolve(root.node_id)
    return bool(effective.config.policies.sso.is_active)


async def local_sign_in_is_open(gateway: PersistenceGateway, *, org_id: str) -> bool:
    """Return whether this deployment's local sign-in has ever opened."""
    scope = TenantScope(org_id=org_id)
    async with gateway.begin(scope) as uow:
        return await uow.identity.local_sign_in_opening() is not None


async def enrol_local_administrator(
    gateway: PersistenceGateway,
    tokens: TokenService,
    *,
    org_id: str,
    name: str,
    password: str,
    rotate: bool = False,
    opened_via: str,
    recorder: AuditRecorder | None = None,
    clock: Callable[[], datetime] = _utc_now,
    user_id: str | None = None,
    display_name: str | None = None,
) -> EnrolledAdministrator:
    """Create or rotate a local administrator, opening the door on the way if needed.

    Two clients share this: the CLI's administrator command, and the route
    that exchanges the bootstrap credential. Both end up here so that "how a
    local administrator is created" has exactly one answer.

    ``user_id`` and ``display_name`` are for the second of those two
    callers, which already has its own identifier for the principal — the
    one the durable token it issues alongside this call has to share — and
    its own display name from the request that reached it. The CLI supplies
    neither: a freshly generated id, and ``name`` doubling as the display
    name, are exactly what creating an administrator from a terminal needs.

    Raises:
        LocalEnrolmentBlockedBySso: this deployment's identity provider is
            active. There is no override — the emergency path for somebody
            locked out is break-glass, not a flag here.
        LocalAdministratorNameTaken: ``name`` already signs in and ``rotate``
            was not asked for.
    """
    if await identity_provider_is_active(gateway, org_id=org_id):
        raise LocalEnrolmentBlockedBySso(emergency_path=BREAK_GLASS_ROUTE)

    scope = TenantScope(org_id=org_id)
    now = clock()
    opened_here = False

    async with gateway.begin(scope) as uow:
        opening = await uow.identity.local_sign_in_opening()
        if opening is None:
            try:
                await uow.identity.open_local_sign_in(opened_at=now, opened_via=opened_via)
                opened_here = True
            except DuplicateRecord:
                # Lost the race: another caller's insert landed first, in the
                # instant between our read and our own attempt. The door is
                # open either way, by whichever of us actually won it.
                pass

        existing = await uow.identity.find_user_by_email(name)
        password_hash = hash_local_password(password)
        if existing is not None:
            if not rotate:
                raise LocalAdministratorNameTaken(name)
            await uow.identity.set_local_password(existing.user_id, password_hash=password_hash)
            user_id = existing.user_id
            rotated = True
        else:
            if user_id is None:
                user_id = secrets.token_hex(_USER_ID_BYTES)
            if display_name is None:
                display_name = name
            await uow.identity.upsert_user(
                User(
                    user_id=user_id,
                    email=name,
                    display_name=display_name,
                    kind=PrincipalKind.USER,
                )
            )
            await uow.identity.upsert_role_binding(
                RoleBinding(
                    binding_id=f"{user_id}-owner",
                    user_id=user_id,
                    role=Role.OWNER.value,
                    node_id=None,
                )
            )
            await uow.identity.set_local_password(user_id, password_hash=password_hash)
            rotated = False

    if rotated:
        # The reason somebody rotates a passphrase is normally that they no
        # longer trust it. A session opened with the old one surviving the
        # rotation would undo the reason for rotating at all.
        await tokens.revoke_all(
            scope,
            AuditContext(actor_kind=ActorKind.SYSTEM, actor_id=user_id),
            user_id=user_id,
            reason="the local administrator's passphrase was rotated",
        )

    if recorder is not None:
        await recorder.record(
            scope,
            AuditContext(actor_kind=ActorKind.SYSTEM, actor_id=user_id),
            action=(
                LOCAL_ADMIN_AUDIT_ACTION_ROTATED if rotated else LOCAL_ADMIN_AUDIT_ACTION_ENROLLED
            ),
            resource_kind=_AUDIT_RESOURCE_KIND,
            resource_id=user_id,
            # No passphrase, no hash — the name and how the door was reached,
            # which is what a reviewer asking "who can sign in, and since
            # when" needs.
            detail={"name": name, "opened_via": opened_via if opened_here else ""},
        )

    return EnrolledAdministrator(user_id=user_id, name=name, rotated=rotated, opened=opened_here)


__all__ = [
    "BREAK_GLASS_ROUTE",
    "EnrolledAdministrator",
    "enrol_local_administrator",
    "identity_provider_is_active",
    "local_sign_in_is_open",
]
