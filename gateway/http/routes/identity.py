"""Who is calling, who exists, and the machine tokens in between.

``/auth/me`` is the one a client cannot work without. A surface that renders by
permission has to know which permissions the caller holds, and the only correct
source for that is the deployment that enforces them — a client inferring them
from a role name would drift the moment the catalogue changed, and the drift
would show up as a control somebody can see and cannot use.

The permission set returned is resolved at the caller's own node, so it is what
they may do *here*, not what the role means in the abstract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.security import (
    IDENTITY_AUDIT_RESOURCE_KIND_GRANT,
    ORGANISATION_WIDE,
    PERMISSION_AUDIT_ACTION_GRANT,
    PERMISSION_AUDIT_ACTION_REVOKE,
)
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, conflict, not_found, unauthorized
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.authorisation import require_owner_retained
from platform.identity.errors import (
    LastOwnerRemoval,
    LocalSignInRejected,
    TooManyRevocations,
)
from platform.identity.models import Grant
from platform.identity.permissions import Permission, Role
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.identity_repository import ApiToken, RoleBinding, User
from platform.startup.bootstrap import organisation_id

auth_router = APIRouter(prefix="/auth", tags=["identity"])
identity_router = APIRouter(prefix="/identity", tags=["identity"])


class PrincipalView(BaseModel):
    principal_id: str
    kind: str
    display_name: str
    email: str | None = None
    team_node_id: str = ""
    #: Resolved at the caller's own node. What they may do here, not what the
    #: role means somewhere else in the tree.
    permissions: list[str]
    roles: list[str]
    #: Whether this session is somebody acting as somebody else. A client is
    #: expected to make that unmistakable, and cannot if it is not told.
    impersonating: bool = False
    impersonated_by: str | None = None


class UserView(BaseModel):
    user_id: str
    email: str
    display_name: str
    kind: str
    is_active: bool


class UserList(BaseModel):
    users: list[UserView]


class GrantView(BaseModel):
    grant_id: str
    principal_id: str
    role: str
    node_id: str | None = None


class GrantList(BaseModel):
    grants: list[GrantView]


class GrantRequest(BaseModel):
    """A role for somebody, somewhere in the tree.

    ``node_id`` absent means the organisation as a whole, which is a different
    thing from a grant at the root node: an organisation-wide grant survives the
    tree being reshaped and a grant at a node does not.
    """

    principal_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    node_id: str | None = None


class GrantRemovedView(BaseModel):
    """Which grant went, and whose it was."""

    grant_id: str
    principal_id: str
    role: str
    node_id: str | None = None


class TokenView(BaseModel):
    token_id: str
    user_id: str
    name: str
    description: str | None = None
    team_node_id: str | None = None
    scopes: list[str]
    created_at: str | None = None
    expires_at: str | None = None
    last_used_at: str | None = None
    revoked: bool


class TokenList(BaseModel):
    tokens: list[TokenView]


class IssueTokenRequest(BaseModel):
    name: str = Field(min_length=1)
    user_id: str = ""
    node_id: str | None = None
    description: str | None = None
    lifetime_days: int | None = None
    #: A ceiling, not a grant: the token may do these and nothing else, and
    #: never more than its owner already holds. Empty means "as wide as the
    #: owner", which is what a personal access token is. Naming a permission
    #: this build does not have is a refusal rather than a silent drop — a
    #: mistyped scope that quietly widened the token would be the worst
    #: possible outcome of a typo.
    permissions: list[str] = Field(default_factory=list)


class IssuedTokenView(BaseModel):
    token: TokenView
    #: Returned exactly once, at creation. There is no route that reads it back,
    #: because the store holds a hash and nothing else.
    secret: str


class BulkRevokeRequest(BaseModel):
    token_ids: list[str] = Field(default_factory=list)
    user_id: str = ""
    node_id: str = ""
    reason: str = "bulk revocation"


class RevocationResult(BaseModel):
    revoked: int
    token_ids: list[str]


def _token_view(token: ApiToken) -> TokenView:
    return TokenView(
        token_id=token.token_id,
        user_id=token.user_id,
        name=token.name,
        description=token.description,
        team_node_id=token.team_node_id,
        scopes=list(token.scopes),
        created_at=token.created_at.isoformat() if token.created_at else None,
        expires_at=token.expires_at.isoformat() if token.expires_at else None,
        last_used_at=token.last_used_at.isoformat() if token.last_used_at else None,
        revoked=token.is_revoked,
    )


def _user_view(user: User) -> UserView:
    return UserView(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        kind=user.kind.value,
        is_active=user.is_active,
    )


def _grant_view(binding: RoleBinding) -> GrantView:
    return GrantView(
        grant_id=binding.binding_id,
        principal_id=binding.user_id,
        role=binding.role,
        node_id=binding.node_id,
    )


def _permissions(names: list[str]) -> tuple[Permission, ...]:
    """Return the permissions ``names`` describes, refusing one this build lacks.

    Refused rather than dropped. A dropped scope widens the token — a typo in
    one entry of a two-entry list would issue a credential holding everything
    its owner does — and the caller has no way to notice, because the response
    reports the scopes it stored rather than the ones it was asked for.
    """
    resolved: list[Permission] = []
    for name in names:
        try:
            resolved.append(Permission(name))
        except ValueError as unknown:
            raise bad_request(
                f"{name!r} is not a permission this deployment has. A token scoped to a "
                f"name nothing recognises would be as wide as its owner."
            ) from unknown
    return tuple(resolved)


def _audit_context(auth: AuthenticatedRequest) -> AuditContext:
    """Return the audit context this request acts under."""
    return AuditContext(actor_kind=ActorKind.USER, actor_id=auth.principal_id)


class SignInRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SignInView(BaseModel):
    """What a successful sign-in hands back: a credential, and when it dies.

    The token is in the body and in nothing else — not a redirect, not a
    ``Set-Cookie``. Who stores it and how is the client's decision, and the
    console's answer is an HTTP-only cookie the browser cannot read.
    """

    token: str
    expires_at: str
    principal_id: str


@auth_router.post("/sign-in", response_model=SignInView)
async def sign_in(
    body: SignInRequest,
    state: GatewayState = Depends(get_state),
) -> SignInView:
    """Exchange the local account's name and passphrase for an API token.

    Public by declaration, because it is where the credential every other route
    demands comes from. A deployment with no local account configured refuses
    everything here, with the same 401 a wrong passphrase gets.
    """
    if state.local_sign_in is None:
        raise unauthorized("the credential was not accepted")
    try:
        issued = await state.local_sign_in.sign_in(
            body.username, body.password, org_id=organisation_id()
        )
    except LocalSignInRejected as refused:
        raise unauthorized(str(refused)) from refused

    expires_at = issued.token.expires_at or datetime.now(UTC)
    return SignInView(
        token=issued.secret,
        expires_at=expires_at.isoformat(),
        principal_id=issued.token.user_id,
    )


@auth_router.get("/me", response_model=PrincipalView)
async def whoami(auth: AuthenticatedRequest = Depends(authorized)) -> PrincipalView:
    """Return the calling principal and what it may do at its own node (FR-023)."""
    principal = auth.context.principal
    node_id = auth.team_node_id or None
    return PrincipalView(
        principal_id=principal.principal_id,
        kind=principal.kind.value,
        display_name=principal.display_name,
        email=principal.email,
        team_node_id=auth.team_node_id,
        permissions=sorted(
            permission.value for permission in auth.context.permissions.permissions_at(node_id)
        ),
        roles=sorted(role.value for role in auth.context.permissions.roles_at(node_id)),
        impersonating=principal.principal_id != auth.token.token.user_id,
        impersonated_by=(
            auth.token.token.user_id if principal.principal_id != auth.token.token.user_id else None
        ),
    )


@identity_router.get("/principals", response_model=UserList)
async def list_principals(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> UserList:
    """Return everyone in this organisation."""
    async with state.gateway.begin(auth.scope) as uow:
        users = await uow.identity.list_users()
    return UserList(users=[_user_view(user) for user in users])


@identity_router.get("/grants", response_model=GrantList)
async def list_grants(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    principal_id: str = "",
) -> GrantList:
    """Return the role grants held in this organisation."""
    async with state.gateway.begin(auth.scope) as uow:
        if principal_id:
            bindings = await uow.identity.role_bindings_for_user(principal_id)
        else:
            # An explicit loop rather than a comprehension: an ``await`` inside a
            # generator expression makes it an *async* generator, which is not
            # iterable and fails at the point somebody tries to use it.
            collected: list[RoleBinding] = []
            for user in await uow.identity.list_users():
                collected.extend(await uow.identity.role_bindings_for_user(user.user_id))
            bindings = tuple(collected)
    return GrantList(grants=[_grant_view(binding) for binding in bindings])


def _grant_id(principal_id: str, role: str, node_id: str | None) -> str:
    """Return the identifier a grant of ``role`` to ``principal_id`` at ``node_id`` has.

    Derived rather than random, which makes granting the same role at the same
    node twice one grant instead of two. Two identical bindings are one fact
    stored twice, and the second one is only ever discovered by whoever tries to
    revoke the role and finds it still held.
    """
    return f"grant:{principal_id}:{role}:{node_id or ORGANISATION_WIDE}"


def _role(name: str) -> Role:
    """Return the role ``name`` describes, or refuse naming the ones that exist."""
    try:
        return Role(name)
    except ValueError as unknown:
        raise bad_request(
            f"{name!r} is not a role this deployment has; expected one of "
            f"{', '.join(sorted(role.value for role in Role))}"
        ) from unknown


async def _all_grants(state: GatewayState, auth: AuthenticatedRequest) -> tuple[Grant, ...]:
    """Return every role grant in this organisation."""
    collected: list[Grant] = []
    async with state.gateway.begin(auth.scope) as uow:
        for user in await uow.identity.list_users():
            for binding in await uow.identity.role_bindings_for_user(user.user_id):
                collected.append(Grant.of_binding(binding))
    return tuple(collected)


@identity_router.post("/grants", response_model=GrantView, status_code=201)
async def add_grant(
    body: GrantRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> GrantView:
    """Give somebody a role, and record who gave it to them.

    The principal has to exist first. Creating one here would make a typo in an
    identifier into a new account holding a role, which is the shape of mistake
    an identity surface must not be able to make quietly.
    """
    role = _role(body.role)
    async with state.gateway.begin(auth.scope) as uow:
        if await uow.identity.get_user(body.principal_id) is None:
            raise not_found(f"no principal {body.principal_id!r}")
        stored = await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=_grant_id(body.principal_id, role.value, body.node_id),
                user_id=body.principal_id,
                role=role.value,
                node_id=body.node_id,
            )
        )
    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        _audit_context(auth),
        action=PERMISSION_AUDIT_ACTION_GRANT,
        resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_GRANT,
        resource_id=stored.binding_id,
        detail={
            "principal_id": stored.user_id,
            "role": stored.role,
            "node_id": stored.node_id or ORGANISATION_WIDE,
        },
    )
    return _grant_view(stored)


@identity_router.delete("/grants/{grant_id}", response_model=GrantRemovedView)
async def remove_grant(
    grant_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> GrantRemovedView:
    """Take a role away, unless doing so would leave nobody able to give it back.

    The last-owner rule is evaluated over the whole organisation rather than
    over the grant being removed, which is why it lives in
    ``require_owner_retained`` and not here: handing ownership over is allowed
    and removing the last owner is not, and a per-grant check gets one of those
    two wrong whichever way it is written.
    """
    grants = await _all_grants(state, auth)
    held = next((grant for grant in grants if grant.grant_id == grant_id), None)
    if held is None:
        raise not_found(f"no grant {grant_id!r}")
    try:
        require_owner_retained(grants, removing=(grant_id,))
    except LastOwnerRemoval as refused:
        raise conflict(str(refused)) from refused

    async with state.gateway.begin(auth.scope) as uow:
        await uow.identity.remove_role_binding(grant_id)
    await AuditRecorder(gateway=state.gateway).record(
        auth.scope,
        _audit_context(auth),
        action=PERMISSION_AUDIT_ACTION_REVOKE,
        resource_kind=IDENTITY_AUDIT_RESOURCE_KIND_GRANT,
        resource_id=grant_id,
        detail={
            "principal_id": held.principal_id,
            "role": held.role.value,
            "node_id": held.node_id or ORGANISATION_WIDE,
        },
    )
    return GrantRemovedView(
        grant_id=grant_id,
        principal_id=held.principal_id,
        role=held.role.value,
        node_id=held.node_id,
    )


@identity_router.get("/tokens", response_model=TokenList)
async def list_tokens(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    user_id: str = "",
) -> TokenList:
    """Return this organisation's machine tokens, revoked ones included (FR-026).

    Revoked ones are listed rather than filtered out. "This token was revoked
    last Tuesday" is the answer to the question somebody is actually asking when
    they open this screen.
    """
    async with state.gateway.begin(auth.scope) as uow:
        tokens = (
            await uow.identity.tokens_for_user(user_id)
            if user_id
            else await uow.identity.list_tokens()
        )
    return TokenList(tokens=[_token_view(token) for token in tokens])


@identity_router.post("/tokens", response_model=IssuedTokenView, status_code=201)
async def issue_token(
    body: IssueTokenRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IssuedTokenView:
    """Issue a machine token and return its secret exactly once."""
    issued = await state.tokens.issue(
        auth.scope,
        _audit_context(auth),
        user_id=body.user_id or auth.principal_id,
        name=body.name,
        node_id=body.node_id,
        description=body.description,
        lifetime_days=body.lifetime_days,
        permissions=_permissions(body.permissions),
    )
    return IssuedTokenView(token=_token_view(issued.token), secret=issued.secret)


@identity_router.delete("/tokens/{token_id}", response_model=RevocationResult)
async def revoke_token(
    token_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RevocationResult:
    """Revoke one token."""
    revoked = await state.tokens.revoke(auth.scope, _audit_context(auth), token_id)
    if not revoked:
        raise not_found(f"no live token {token_id!r}")
    return RevocationResult(revoked=1, token_ids=[token_id])


@identity_router.post("/tokens/revoke", response_model=RevocationResult)
async def revoke_tokens(
    body: BulkRevokeRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RevocationResult:
    """Revoke a set of tokens at once, selected by id, by owner, or by team."""
    try:
        revoked = await state.tokens.revoke_all(
            auth.scope,
            _audit_context(auth),
            token_ids=body.token_ids or None,
            user_id=body.user_id or None,
            node_id=body.node_id or None,
            reason=body.reason,
        )
    except TooManyRevocations as refused:
        raise bad_request(str(refused)) from refused
    return RevocationResult(revoked=len(revoked), token_ids=list(revoked))


def _now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


__all__ = ["auth_router", "identity_router"]
