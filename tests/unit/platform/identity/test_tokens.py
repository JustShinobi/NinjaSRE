"""Machine credentials: issued once, verified cheaply, revoked immediately.

The assertions worth reading here are the ones about *time*. A token's secret
exists for one call and then only as a hash; an expiry is compared with a
tolerance so two hosts' clocks cannot page somebody at three in the morning; and
a revocation takes effect on the next request rather than when a cache felt like
noticing, which is the one property a caching layer makes easy to lose.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import (
    API_TOKEN_DEFAULT_LIFETIME_DAYS,
    API_TOKEN_MAX_LIFETIME_DAYS,
    API_TOKEN_PREFIX,
    MAX_BULK_REVOCATIONS,
    TOKEN_CLOCK_SKEW_SECONDS,
    TOKEN_EXPIRY_WARNING_DAYS,
    TOKEN_INACTIVITY_REVOCATION_DAYS,
    TOKEN_RESOLUTION_CACHE_TTL_SECONDS,
)
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.errors import TokenLifetimeTooLong, TokenRejected, TooManyRevocations
from platform.identity.permissions import Permission, Role, permissions_for
from platform.identity.tokens import TokenHasher, TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ActorKind,
    ConfigNode,
    ConfigNodeKind,
    PrincipalKind,
    RoleBinding,
    TenantScope,
    UnitOfWork,
    User,
)

ORG = "acme"
TEAM = "payments"
OWNER = "ada"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class Clock:
    """A clock a test moves on purpose."""

    def __init__(self, now: datetime = AT) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class CountingPersistence(FakePersistence):
    """The in-memory store, counting every unit of work it opens.

    What an authentication costs is measured in transactions, because on a
    real deployment every one of them is a round trip to another host.
    """

    def __init__(self) -> None:
        super().__init__()
        self.opened = 0

    @asynccontextmanager
    async def begin(self, scope: TenantScope) -> AsyncIterator[UnitOfWork]:
        self.opened += 1
        async with super().begin(scope) as uow:
            yield uow

    @asynccontextmanager
    async def begin_system(self):  # type: ignore[no-untyped-def]
        self.opened += 1
        async with super().begin_system() as uow:
            yield uow


async def build(clock: Clock) -> tuple[TokenService, CountingPersistence, TenantScope]:
    """Return a token service over a tenant with one user and one team."""
    gateway = CountingPersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    scope = TenantScope(org_id=ORG)
    async with gateway.begin(scope) as uow:
        root = await uow.config.root()
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM, kind=ConfigNodeKind.TEAM, name="Payments", parent_id=root.node_id
            )
        )
        await uow.identity.upsert_user(
            User(
                user_id=OWNER, email="ada@example.com", display_name="Ada", kind=PrincipalKind.USER
            )
        )

    service = TokenService(
        gateway=gateway,
        hasher=TokenHasher(pepper=b"a-deployment-pepper"),
        recorder=AuditRecorder(gateway=gateway, clock=clock),
        clock=clock,
    )
    return service, gateway, scope


def context() -> AuditContext:
    """Return the acting context an admin issuing a token carries."""
    return AuditContext(actor_kind=ActorKind.USER, actor_id=OWNER, source_address="203.0.113.7")


# --- Issuing -------------------------------------------------


async def test_an_issued_token_returns_a_prefixed_secret_and_stores_only_its_hash() -> None:
    """The plaintext is shown once and is not recoverable from anything stored."""
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="payments bot")

    assert issued.secret.startswith(API_TOKEN_PREFIX)
    assert issued.token.token_hash != issued.secret
    assert issued.secret not in issued.token.token_hash

    async with gateway.begin(scope) as uow:
        stored = await uow.identity.tokens_for_user(OWNER)
    assert [token.token_hash for token in stored] == [issued.token.token_hash]
    assert all(issued.secret not in str(token) for token in stored)


async def test_two_tokens_never_share_a_secret() -> None:
    """Entropy, asserted rather than assumed."""
    service, _, scope = await build(Clock())
    first = await service.issue(scope, context(), user_id=OWNER, name="one")
    second = await service.issue(scope, context(), user_id=OWNER, name="two")
    assert first.secret != second.secret
    assert first.token.token_hash != second.token.token_hash


async def test_a_token_carries_its_team_permissions_expiry_and_description() -> None:
    """Everything that bounds what a token can do is on the record."""
    service, _, scope = await build(Clock())
    issued = await service.issue(
        scope,
        context(),
        user_id=OWNER,
        name="payments bot",
        node_id=TEAM,
        permissions=(Permission.INVESTIGATION_RUN, Permission.CONFIG_READ),
        description="posts investigations into the payments channel",
        lifetime_days=30,
    )

    assert issued.token.team_node_id == TEAM
    assert set(issued.token.scopes) == {
        Permission.INVESTIGATION_RUN.value,
        Permission.CONFIG_READ.value,
    }
    assert issued.token.description == "posts investigations into the payments channel"
    assert issued.token.expires_at == AT + timedelta(days=30)


async def test_a_token_with_no_stated_lifetime_gets_the_default() -> None:
    """There is no token that never expires."""
    service, _, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")
    assert issued.token.expires_at == AT + timedelta(days=API_TOKEN_DEFAULT_LIFETIME_DAYS)


async def test_a_lifetime_beyond_the_ceiling_is_refused() -> None:
    """The ceiling is a refusal, not a silent truncation."""
    service, _, scope = await build(Clock())
    with pytest.raises(TokenLifetimeTooLong):
        await service.issue(
            scope,
            context(),
            user_id=OWNER,
            name="bot",
            lifetime_days=API_TOKEN_MAX_LIFETIME_DAYS + 1,
        )


async def test_issuing_is_audited() -> None:
    """Token lifecycle is an audited action class."""
    service, gateway, scope = await build(Clock())
    await service.issue(scope, context(), user_id=OWNER, name="bot")

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="token.issue")
    assert len(events) == 1
    assert events[0].actor_id == OWNER


# --- Verifying ----------------------------------------------------------------


async def test_a_live_token_authenticates_to_its_owner_and_scope() -> None:
    """The happy path, and the shape everything above this layer receives."""
    service, _, scope = await build(Clock())
    issued = await service.issue(
        scope,
        context(),
        user_id=OWNER,
        name="bot",
        node_id=TEAM,
        permissions=(Permission.INVESTIGATION_RUN,),
    )

    authenticated = await service.authenticate(issued.secret)

    assert authenticated.principal.principal_id == OWNER
    assert authenticated.principal.org_id == ORG
    assert authenticated.principal.token_id == issued.token.token_id
    assert authenticated.principal.node_id == TEAM


async def test_a_token_issued_with_no_permissions_declared_authenticates_to_nothing() -> None:
    """An owner-level user can still mint a token that can do nothing at all.

    Before this test, the only stored signal for "how wide is this token" was
    its scopes tuple, and an empty one was read as "as wide as its owner" —
    the same shape a browser session's token has. A machine token issued with
    no scope chosen must not silently inherit the owner's full permission set;
    that reading belongs only to a token this service issues as `unscoped`.
    """
    service, gateway, scope = await build(Clock())
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="ada-owner", user_id=OWNER, role=Role.OWNER.value)
        )
    issued = await service.issue(scope, context(), user_id=OWNER, name="ci-runner")

    authenticated = await service.authenticate(issued.secret)

    assert authenticated.permissions.permissions_at(None) == frozenset()


async def test_a_token_issued_with_explicit_permissions_carries_only_those() -> None:
    """The ordinary, scoped case: exactly what was asked for, nothing assumed."""
    service, gateway, scope = await build(Clock())
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="ada-owner", user_id=OWNER, role=Role.OWNER.value)
        )
    issued = await service.issue(
        scope,
        context(),
        user_id=OWNER,
        name="ci-runner",
        permissions=(Permission.WEBHOOK_DELIVER,),
    )

    authenticated = await service.authenticate(issued.secret)

    assert authenticated.permissions.permissions_at(None) == {Permission.WEBHOOK_DELIVER}


async def test_a_request_beyond_the_owners_own_permissions_is_narrowed_not_granted() -> None:
    """The ceiling holds through the whole issuance path, not only at the set layer.

    A viewer holds nothing that touches the organisation itself. A token
    issued to one that explicitly asks for `Permission.ORG_DELETE` must come
    back holding nothing, the same ceiling `PermissionSet.narrowed_to` already
    enforces on its own — exercised here through `TokenService.issue` and a
    live `authenticate()`, so the wiring between them is what is under test,
    not the set operation in isolation.
    """
    service, gateway, scope = await build(Clock())
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="ada-viewer", user_id=OWNER, role=Role.VIEWER.value)
        )
    issued = await service.issue(
        scope,
        context(),
        user_id=OWNER,
        name="ci-runner",
        permissions=(Permission.ORG_DELETE,),
    )

    authenticated = await service.authenticate(issued.secret)

    assert authenticated.permissions.permissions_at(None) == frozenset()


async def test_an_unscoped_token_still_authenticates_to_its_owners_full_permissions() -> None:
    """A session-style credential keeps carrying everything its owner holds.

    `unscoped` is what a browser sign-in and a durable owner credential ask
    for explicitly — never the default, and never reachable through the
    machine-token issuance route.
    """
    service, gateway, scope = await build(Clock())
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="ada-owner", user_id=OWNER, role=Role.OWNER.value)
        )
    issued = await service.issue(
        scope, context(), user_id=OWNER, name="Console sign-in", unscoped=True
    )

    authenticated = await service.authenticate(issued.secret)

    assert authenticated.permissions.permissions_at(None) == permissions_for(Role.OWNER)


async def test_an_unknown_token_is_rejected() -> None:
    """A string that was never issued gets the same answer as everything else."""
    service, _, _ = await build(Clock())
    with pytest.raises(TokenRejected):
        await service.authenticate(f"{API_TOKEN_PREFIX}never-issued")


async def test_an_expired_token_is_rejected_and_the_attempt_is_audited() -> None:
    """Acceptance scenario 4: rejected, and the attempt is on the record."""
    clock = Clock()
    service, gateway, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", lifetime_days=1)

    clock.advance(timedelta(days=2))
    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="token.reject")
    assert len(events) == 1


async def test_expiry_is_compared_with_a_tolerance_for_clock_skew() -> None:
    """A token that expired a moment ago on another host's clock still works.

    The tolerance applies to expiry alone. Revocation is immediate by
    definition, and the test below asserts no skew is granted there.
    """
    clock = Clock()
    service, _, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", lifetime_days=1)

    clock.advance(timedelta(days=1, seconds=TOKEN_CLOCK_SKEW_SECONDS - 5))
    assert await service.authenticate(issued.secret) is not None

    clock.advance(timedelta(seconds=10))
    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)


async def test_a_token_whose_owner_was_deactivated_is_rejected() -> None:
    """A credential does not outlive the person it belongs to."""
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")

    async with gateway.begin(scope) as uow:
        user = await uow.identity.get_user(OWNER)
        assert user is not None
        await uow.identity.upsert_user(
            User(
                user_id=user.user_id,
                email=user.email,
                display_name=user.display_name,
                kind=user.kind,
                is_active=False,
                created_at=user.created_at,
            )
        )

    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)


async def test_a_deactivation_announced_to_the_service_takes_effect_on_the_next_request() -> None:
    """The write that deactivates a person tells the service, and the cache is not consulted.

    The whole authentication is cached for a few seconds, so a write the
    service is not told about is seen once the window closes. A write that
    announces itself — the way every identity route does — is seen at once,
    which is the ordering ``revoke`` already guarantees for a token.
    """
    clock = Clock()
    service, gateway, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")
    await service.authenticate(issued.secret)

    async with gateway.begin(scope) as uow:
        user = await uow.identity.get_user(OWNER)
        assert user is not None
        await uow.identity.upsert_user(
            User(
                user_id=user.user_id,
                email=user.email,
                display_name=user.display_name,
                kind=user.kind,
                is_active=False,
                created_at=user.created_at,
            )
        )
    service.forget_user(OWNER)

    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)


async def test_a_deactivation_nobody_announced_is_seen_once_the_window_closes() -> None:
    """The TTL is the backstop for a write made behind the service's back."""
    clock = Clock()
    service, gateway, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")
    await service.authenticate(issued.secret)

    async with gateway.begin(scope) as uow:
        user = await uow.identity.get_user(OWNER)
        assert user is not None
        await uow.identity.upsert_user(
            User(
                user_id=user.user_id,
                email=user.email,
                display_name=user.display_name,
                kind=user.kind,
                is_active=False,
                created_at=user.created_at,
            )
        )

    clock.advance(timedelta(seconds=TOKEN_RESOLUTION_CACHE_TTL_SECONDS))
    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)


async def test_a_token_whose_team_was_deleted_is_rejected_with_a_clear_reason() -> None:
    """The edge case the specification names, and the reason an operator needs."""
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", node_id=TEAM)
    await service.authenticate(issued.secret)

    async with gateway.begin(scope) as uow:
        await uow.config.delete(TEAM)
    service.forget_team(TEAM)

    with pytest.raises(TokenRejected) as raised:
        await service.authenticate(issued.secret)
    assert "team" in raised.value.reason


# --- The cost of authenticating --------------------------


async def test_a_second_authentication_within_the_window_opens_no_transaction() -> None:
    """The first request pays for the resolution; the next few seconds do not.

    Every authenticated request on a deployment opened a unit of work and
    re-read the owner, every token the owner holds, the team node and the
    role bindings — six statements to re-prove what had been proved moments
    before, on a single-process gateway where those statements queue behind
    each other. The cache holds the whole answer now, not just the token row.
    """
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")

    first = await service.authenticate(issued.secret)
    opened = gateway.opened
    second = await service.authenticate(issued.secret)

    assert gateway.opened == opened
    assert second.principal == first.principal
    assert second.permissions.grants == first.permissions.grants


async def test_a_grant_announced_to_the_service_is_held_on_the_next_request() -> None:
    """Permissions change through the same door revocation uses: tell the service."""
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", unscoped=True)
    before = await service.authenticate(issued.secret)
    assert not before.permissions.allows(Permission.CONFIG_WRITE)

    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="ada-operator", user_id=OWNER, role=Role.OPERATOR.value)
        )
    service.forget_user(OWNER)

    after = await service.authenticate(issued.secret)
    assert after.permissions.allows(Permission.CONFIG_WRITE)


async def test_concurrent_first_requests_resolve_the_token_once() -> None:
    """A page render is a dozen requests in the same instant, all missing the cache.

    Without single-flight each of them resolved the token in full, so the
    burst cost twelve times what one request costs and the cache saved
    nothing on exactly the pattern it exists for.
    """
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")

    await service.authenticate(issued.secret)
    service.forget_user(OWNER)

    before = gateway.opened
    resolved = await asyncio.gather(*(service.authenticate(issued.secret) for _ in range(12)))

    assert len({token.token.token_id for token in resolved}) == 1
    assert gateway.opened - before <= 3, "twelve concurrent requests must share one resolution"


# --- Revocation ---------------------------------------------


async def test_a_revoked_token_is_rejected_immediately() -> None:
    """No cache window between the revocation and the rejection."""
    service, _, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")

    # Authenticate first, so the resolution is cached and the revocation has
    # something to invalidate. Without this the assertion would pass against a
    # cache that was simply never populated.
    await service.authenticate(issued.secret)

    revoked = await service.revoke(scope, context(), issued.token.token_id)
    assert revoked

    with pytest.raises(TokenRejected):
        await service.authenticate(issued.secret)


async def test_revoking_an_already_revoked_token_reports_no_change() -> None:
    """Idempotent, and honest about it."""
    service, _, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")
    assert await service.revoke(scope, context(), issued.token.token_id)
    assert not await service.revoke(scope, context(), issued.token.token_id)


async def test_revocation_is_audited() -> None:
    """A credential disappearing is a thing somebody may need to explain."""
    service, gateway, scope = await build(Clock())
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot")
    await service.revoke(scope, context(), issued.token.token_id)

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="token.revoke")
    assert [event.resource_id for event in events] == [issued.token.token_id]


async def test_bulk_revocation_covers_a_team_at_once() -> None:
    """What incident response reaches for."""
    service, _, scope = await build(Clock())
    inside = [
        await service.issue(scope, context(), user_id=OWNER, name=f"bot-{n}", node_id=TEAM)
        for n in range(3)
    ]
    outside = await service.issue(scope, context(), user_id=OWNER, name="org-wide")

    revoked = await service.revoke_all(scope, context(), node_id=TEAM)

    assert set(revoked) == {issued.token.token_id for issued in inside}
    assert await service.authenticate(outside.secret) is not None


async def test_bulk_revocation_is_bounded() -> None:
    """A single call that could revoke a whole deployment is not a control."""
    service, _, scope = await build(Clock())
    with pytest.raises(TooManyRevocations):
        await service.revoke_all(
            scope,
            context(),
            token_ids=tuple(f"t-{n}" for n in range(MAX_BULK_REVOCATIONS + 1)),
        )


# --- Inactivity and expiry warnings -------------------------


async def test_an_unused_token_is_revoked_after_the_inactivity_window() -> None:
    """A credential nobody uses is a credential nobody is watching."""
    clock = Clock()
    service, _, scope = await build(clock)
    stale = await service.issue(scope, context(), user_id=OWNER, name="forgotten")
    fresh = await service.issue(scope, context(), user_id=OWNER, name="in use")

    clock.advance(timedelta(days=TOKEN_INACTIVITY_REVOCATION_DAYS - 1))
    await service.authenticate(fresh.secret)

    clock.advance(timedelta(days=2))
    revoked = await service.sweep_inactive(scope, context())

    assert [entry.token.token_id for entry in revoked] == [stale.token.token_id]
    assert revoked[0].owner_id == OWNER


async def test_the_inactivity_sweep_leaves_a_token_used_within_the_window() -> None:
    """The other half of the assertion above, so it is not vacuous."""
    clock = Clock()
    service, _, scope = await build(clock)
    await service.issue(scope, context(), user_id=OWNER, name="new")

    clock.advance(timedelta(days=TOKEN_INACTIVITY_REVOCATION_DAYS - 1))
    assert await service.sweep_inactive(scope, context()) == ()


async def test_an_inactivity_revocation_is_audited_with_its_reason() -> None:
    """A token that stopped working needs an answer for its owner."""
    clock = Clock()
    service, gateway, scope = await build(clock)
    await service.issue(scope, context(), user_id=OWNER, name="forgotten")

    clock.advance(timedelta(days=TOKEN_INACTIVITY_REVOCATION_DAYS + 1))
    await service.sweep_inactive(scope, context())

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="token.revoke")
    assert len(events) == 1
    assert "inactiv" in str(events[0].detail).lower()


async def test_a_token_nearing_expiry_is_reported_once_the_warning_window_opens() -> None:
    """Warned in advance, so a renewal is not an incident."""
    clock = Clock()
    service, _, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", lifetime_days=30)

    assert await service.expiring_soon(scope) == ()

    clock.advance(timedelta(days=30 - TOKEN_EXPIRY_WARNING_DAYS + 1))
    warned = await service.expiring_soon(scope)
    assert [entry.token.token_id for entry in warned] == [issued.token.token_id]


async def test_an_expiry_warning_is_not_repeated_for_a_revoked_token() -> None:
    """Nobody needs telling that a token they revoked is about to expire."""
    clock = Clock()
    service, _, scope = await build(clock)
    issued = await service.issue(scope, context(), user_id=OWNER, name="bot", lifetime_days=30)
    await service.revoke(scope, context(), issued.token.token_id)

    clock.advance(timedelta(days=30 - TOKEN_EXPIRY_WARNING_DAYS + 1))
    assert await service.expiring_soon(scope) == ()


# --- Hashing ------------------------------------------------------------------


def test_hashing_is_deterministic_and_hides_the_secret() -> None:
    """Resolution is a lookup, so the hash has to be stable — and one-way."""
    hasher = TokenHasher(pepper=b"pepper")
    secret = f"{API_TOKEN_PREFIX}abc123"
    assert hasher.hash(secret) == hasher.hash(secret)
    assert secret not in hasher.hash(secret)


def test_two_deployments_with_different_peppers_do_not_share_hashes() -> None:
    """A hash lifted from one deployment's dump is not a token in another."""
    secret = f"{API_TOKEN_PREFIX}abc123"
    assert TokenHasher(pepper=b"one").hash(secret) != TokenHasher(pepper=b"two").hash(secret)
