"""The bootstrap credential: a real credential, short, single-purpose, and gone.

Everything here drives the real ``TokenService`` over ``FakePersistence``.
Nothing about issuance, expiry, or revocation is mocked, because the failure
this feature exists to prevent was a token that everything *believed* had been
issued and that the identity system had never heard of.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from config.constants.first_run import (
    BOOTSTRAP_AUDIT_ACTION_ESTABLISH,
    BOOTSTRAP_AUDIT_ACTION_ISSUE,
    BOOTSTRAP_CREDENTIAL_FILENAME,
    BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS,
    BOOTSTRAP_PRINCIPAL_ID,
    DEFAULT_ORGANISATION_ID,
    DURABLE_CREDENTIAL_LIFETIME_DAYS,
    NINJASRE_ORGANISATION_ENV,
    NINJASRE_STATE_DIR_ENV,
)
from platform.identity.errors import TokenRejected
from platform.identity.permissions import Permission
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.transaction import TenantScope
from platform.startup.bootstrap import (
    BootstrapCredential,
    BringUp,
    announcement,
    bring_up,
    credential_path,
    establish_durable_credential,
    read_credential,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    """Return the environment a container brings up with."""
    return {NINJASRE_STATE_DIR_ENV: str(tmp_path / "state")}


@pytest.fixture
def store() -> FakePersistence:
    """Return a store with nothing in it at all."""
    return FakePersistence()


@pytest.fixture
def tokens(store: FakePersistence) -> TokenService:
    """Return the real token service over that store."""
    return TokenService(gateway=store)


# --- Issuance through the identity system -------------------------------------


async def test_bring_up_creates_the_organisation_the_credential_belongs_to(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ=environ)

    assert result.organisation_id == DEFAULT_ORGANISATION_ID
    async with store.begin_system() as system:
        assert await system.orgs.get_organisation(DEFAULT_ORGANISATION_ID) is not None


async def test_the_organisation_can_be_named(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ={**environ, NINJASRE_ORGANISATION_ENV: "acme"})

    assert result.organisation_id == "acme"


async def test_the_credential_authenticates_through_the_identity_system(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-001. Not a magic header and not an environment variable the gateway
    special-cases: an ordinary token the token service resolves."""
    result = await bring_up(store, tokens, environ=environ)

    authenticated = await tokens.authenticate(result.credential.secret)

    assert authenticated.principal.principal_id == BOOTSTRAP_PRINCIPAL_ID
    assert authenticated.scope.org_id == DEFAULT_ORGANISATION_ID


async def test_the_credential_is_short_lived(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-003. An hour, not the identity layer's default year."""
    before = datetime.now(UTC)
    result = await bring_up(store, tokens, environ=environ)

    lifetime = result.credential.expires_at - before
    assert lifetime <= timedelta(seconds=BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS + 5)
    assert lifetime > timedelta(seconds=BOOTSTRAP_CREDENTIAL_LIFETIME_SECONDS - 60)


async def test_the_credential_carries_one_purpose_and_not_the_owner_role(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-003. It may see who it is and establish a durable credential. That is all.

    The principal behind it holds ``owner`` — it has to, or the durable
    credential it establishes could not be granted anything. The *token* is
    narrowed to two permissions, which is the ceiling the token service applies
    on top of the grant.
    """
    result = await bring_up(store, tokens, environ=environ)

    authenticated = await tokens.authenticate(result.credential.secret)
    held = authenticated.permissions.permissions_at(None)

    assert held == {Permission.INVESTIGATION_READ, Permission.TOKEN_MANAGE}
    assert Permission.CONFIG_WRITE not in held
    assert Permission.REMEDIATION_EXECUTE not in held


# --- Delivery to the host ------------------------------------------------------


async def test_the_credential_is_written_where_the_operator_reads_it(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-002. A file, so closing the terminal is not a lost deployment."""
    result = await bring_up(store, tokens, environ=environ)

    path = credential_path(environ)
    assert path.name == BOOTSTRAP_CREDENTIAL_FILENAME
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["secret"] == result.credential.secret
    assert written["expires_at"] == result.credential.expires_at.isoformat()


async def test_the_credential_file_is_owner_only(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    await bring_up(store, tokens, environ=environ)

    assert credential_path(environ).stat().st_mode & 0o777 == 0o600


async def test_the_credential_reads_back_from_the_host_without_a_restart(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-002. Same object, read off the disk rather than out of the process."""
    result = await bring_up(store, tokens, environ=environ)

    again = read_credential(environ)

    assert again is not None
    assert again == result.credential


async def test_reading_a_credential_that_was_never_written_returns_nothing(
    environ: dict[str, str],
) -> None:
    assert read_credential(environ) is None


async def test_the_announcement_states_the_expiry_and_where_to_read_it_again(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-002. An expiry a person can act on, and the path, in the printed block."""
    result = await bring_up(store, tokens, environ=environ)

    printed = announcement(result.credential, path=credential_path(environ))

    assert result.credential.secret in printed
    assert result.credential.expires_at.isoformat() in printed
    assert str(credential_path(environ)) in printed


# --- Idempotence ---------------------------------------------------------------


async def test_bringing_up_twice_changes_nothing(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-005. No reset, no wipe, no second credential."""
    first = await bring_up(store, tokens, environ=environ)
    second = await bring_up(store, tokens, environ=environ)

    assert second.credential == first.credential
    assert second.issued is False
    async with store.begin(TenantScope(org_id=DEFAULT_ORGANISATION_ID)) as uow:
        live = [
            token
            for token in await uow.identity.tokens_for_user(BOOTSTRAP_PRINCIPAL_ID)
            if token.revoked_at is None
        ]
    assert len(live) == 1


async def test_bringing_up_twice_does_not_duplicate_the_organisation_or_the_grant(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    await bring_up(store, tokens, environ=environ)
    await bring_up(store, tokens, environ=environ)

    async with store.begin_system() as system:
        assert len(await system.orgs.list_organisations()) == 1
    async with store.begin(TenantScope(org_id=DEFAULT_ORGANISATION_ID)) as uow:
        bindings = await uow.identity.role_bindings_for_user(BOOTSTRAP_PRINCIPAL_ID)
    assert len(bindings) == 1


async def test_a_credential_that_expired_is_replaced_rather_than_reused(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """Idempotent is not "never issue again". A deployment restarted a day later
    has to be enterable, and the hour-old credential in the file is not."""
    first = await bring_up(store, tokens, environ=environ)

    stale = BootstrapCredential(
        secret=first.credential.secret,
        token_id=first.credential.token_id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        organisation_id=first.credential.organisation_id,
    )
    credential_path(environ).write_text(json.dumps(stale.to_record()), encoding="utf-8")

    second = await bring_up(store, tokens, environ=environ)

    assert second.issued is True
    assert second.credential.secret != first.credential.secret


async def test_a_credential_the_store_no_longer_holds_is_replaced(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """The file is a copy, not the record. If the two disagree the store wins —
    otherwise a restored backup would leave a file nobody can sign in with."""
    first = await bring_up(store, tokens, environ=environ)
    await tokens.revoke(
        TenantScope(org_id=DEFAULT_ORGANISATION_ID),
        _context(),
        first.credential.token_id,
    )

    second = await bring_up(store, tokens, environ=environ)

    assert second.issued is True
    assert second.credential.secret != first.credential.secret


# --- Establishing a durable credential ------------------------------------------


async def test_establishing_a_durable_credential_expires_the_bootstrap_one(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """FR-003, SC-002. It establishes one thing and then it is over."""
    result = await bring_up(store, tokens, environ=environ)

    durable = await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
    )

    assert durable.secret != result.credential.secret
    with pytest.raises(TokenRejected):
        await tokens.authenticate(result.credential.secret)


async def test_the_durable_credential_is_a_full_owner(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ=environ)

    durable = await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
    )

    authenticated = await tokens.authenticate(durable.secret)
    held = authenticated.permissions.permissions_at(None)
    assert Permission.CONFIG_WRITE in held
    assert Permission.OWNER_ASSIGN in held


async def test_the_durable_credential_outlives_the_bootstrap_one_by_months(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ=environ)

    durable = await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
    )

    remaining = durable.expires_at - datetime.now(UTC)
    assert remaining > timedelta(days=DURABLE_CREDENTIAL_LIFETIME_DAYS - 1)


async def test_the_bootstrap_credential_file_is_removed_once_it_is_spent(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    """A dead credential left on disk is a credential somebody tries for an hour."""
    result = await bring_up(store, tokens, environ=environ)
    assert credential_path(environ).exists()

    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
        environ=environ,
    )

    assert not credential_path(environ).exists()


async def test_establishing_twice_with_the_same_bootstrap_credential_is_refused(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ=environ)
    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
    )

    with pytest.raises(TokenRejected):
        await establish_durable_credential(
            store,
            tokens,
            bootstrap=result.credential,
            user_id="grace",
            email="grace@example.test",
            display_name="Grace",
        )


# --- The record ------------------------------------------------------------------


async def test_both_halves_of_the_exchange_are_audited(
    store: FakePersistence, tokens: TokenService, environ: dict[str, str]
) -> None:
    result = await bring_up(store, tokens, environ=environ)
    await establish_durable_credential(
        store,
        tokens,
        bootstrap=result.credential,
        user_id="ada",
        email="ada@example.test",
        display_name="Ada",
    )

    async with store.begin(TenantScope(org_id=DEFAULT_ORGANISATION_ID)) as uow:
        events = await uow.audit.query()
    actions = {event.action for event in events}

    assert BOOTSTRAP_AUDIT_ACTION_ISSUE in actions
    assert BOOTSTRAP_AUDIT_ACTION_ESTABLISH in actions


def test_a_credential_round_trips_through_its_record() -> None:
    credential = BootstrapCredential(
        secret="nsr_abc",
        token_id="tok-1",
        expires_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        organisation_id="default",
    )

    assert BootstrapCredential.from_record(credential.to_record()) == credential


def test_a_bring_up_result_says_whether_it_issued_anything() -> None:
    credential = BootstrapCredential(
        secret="nsr_abc",
        token_id="tok-1",
        expires_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        organisation_id="default",
    )

    assert BringUp(credential=credential, issued=True).issued is True


def _context() -> object:
    from platform.identity.audit.recorder import AuditContext
    from platform.persistence.ports.audit_repository import ActorKind

    return AuditContext(actor_kind=ActorKind.SYSTEM, actor_id="test")
