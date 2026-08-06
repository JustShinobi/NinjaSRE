"""The vault: what it validates, what it versions, and what it refuses to return.

Three properties carry the weight here.

**Validation happens on write** (FR-005), so a credential with a copy-paste
newline is rejected while somebody is looking at the screen rather than at 03:00
during the incident that needed it.

**Rotation writes a version** (FR-002), so rolling back is a pointer move and
not a restore from somebody's password manager. SC-004 — rotation takes effect on
the next request — falls out of that, and is asserted through the proxy in
``test_rotation_and_isolation.py`` where it belongs.

**Nothing here returns a value** (FR-003). The last test in this file is an
assertion about the class surface, because that is what the guarantee actually
is: not a check that could be removed, but the absence of a method.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.credentials.errors import (
    CredentialNotConfigured,
    CredentialSchemaViolation,
    CredentialVersionNotFound,
    MalformedHandle,
    UnknownIntegration,
)
from platform.credentials.handles import CredentialHandle, version_of
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import CredentialVersion, Vault, encode_payload
from tests.unit.platform.credentials.conftest import (
    INTEGRATION,
    OTHER_TEAM_ID,
    SCHEMA,
    TEAM_ID,
    Harness,
)

pytestmark = pytest.mark.unit

GOOD = {"api_key": "abcdefabcdefabcdefabcdef", "region": "eu"}


# -- handles ------------------------------------------------------------------


def test_a_handle_renders_as_integration_and_team() -> None:
    assert CredentialHandle(integration="datadog", team_id="payments").qualified == (
        "datadog/payments"
    )


def test_an_organisation_wide_handle_is_spelled_with_a_dash() -> None:
    """Not the empty string: ``datadog/`` and ``datadog`` would be two spellings of one."""
    handle = CredentialHandle.for_organisation("datadog")

    assert handle.qualified == "datadog/-"
    assert handle.is_organisation_wide


def test_a_handle_round_trips_through_its_written_form() -> None:
    handle = CredentialHandle(integration="datadog", team_id="payments")

    assert CredentialHandle.parse(handle.qualified) == handle
    assert CredentialHandle.parse(handle.version_handle(4)) == handle


@pytest.mark.parametrize("text", ["datadog", "", "datadog@v2"])
def test_an_unparseable_handle_is_refused(text: str) -> None:
    with pytest.raises(MalformedHandle):
        CredentialHandle.parse(text)


@pytest.mark.parametrize("part", ["data/dog", "data@vdog"])
def test_a_handle_may_not_carry_a_reserved_separator(part: str) -> None:
    with pytest.raises(MalformedHandle):
        CredentialHandle(integration=part, team_id="payments")


def test_a_team_handle_falls_back_to_the_organisation_and_stops_there() -> None:
    """One step. A deeper chain makes "which credential" a computed answer."""
    team = CredentialHandle(integration="datadog", team_id="payments")

    fallback = team.fallback()
    assert fallback is not None
    assert fallback.is_organisation_wide
    assert fallback.fallback() is None


def test_a_version_is_read_back_out_of_a_stored_handle() -> None:
    assert version_of("datadog/payments@v7") == 7
    assert version_of("datadog/payments") is None


# -- validation on write ------------------------------------------------------


async def test_a_credential_that_fits_the_schema_is_stored(harness: Harness) -> None:
    stored = await harness.vault.store(harness.scope(), harness.handle(), GOOD)

    assert isinstance(stored, CredentialVersion)
    assert stored.version == 1
    assert stored.is_active
    assert stored.integration == INTEGRATION


async def test_a_missing_required_field_is_refused(harness: Harness) -> None:
    with pytest.raises(CredentialSchemaViolation) as raised:
        await harness.vault.store(harness.scope(), harness.handle(), {"region": "eu"})

    assert raised.value.integration == INTEGRATION
    assert any("api_key" in problem for problem in raised.value.problems)


async def test_a_pasted_newline_is_refused_at_the_moment_it_is_entered(
    harness: Harness,
) -> None:
    """The classic copy-paste artefact, caught while somebody is still looking."""
    with pytest.raises(CredentialSchemaViolation) as raised:
        await harness.vault.store(
            harness.scope(), harness.handle(), {"api_key": "abcdefabcdefabcdef\n"}
        )

    assert any("whitespace" in problem for problem in raised.value.problems)


async def test_a_field_the_schema_does_not_declare_is_refused(harness: Harness) -> None:
    with pytest.raises(CredentialSchemaViolation) as raised:
        await harness.vault.store(
            harness.scope(), harness.handle(), {**GOOD, "app_key": "surprise"}
        )

    assert any("app_key" in problem for problem in raised.value.problems)


async def test_the_violation_never_quotes_the_value(harness: Harness) -> None:
    """An exception reaches places a log does not, so it names fields and not values."""
    secret = "  a-value-nobody-should-see  "

    with pytest.raises(CredentialSchemaViolation) as raised:
        await harness.vault.store(harness.scope(), harness.handle(), {"api_key": secret})

    assert secret.strip() not in str(raised.value)
    assert "api_key" in str(raised.value)


async def test_an_undeclared_integration_is_refused(harness: Harness) -> None:
    with pytest.raises(UnknownIntegration):
        await harness.vault.store(
            harness.scope(), CredentialHandle(integration="nowhere", team_id=TEAM_ID), GOOD
        )


def test_every_problem_is_reported_at_once() -> None:
    """An operator entering a credential fixes all of it in one pass."""
    with pytest.raises(CredentialSchemaViolation) as raised:
        SCHEMA.validate({"region": "eu", "nonsense": "x"})

    assert len(raised.value.problems) == 2


# -- versioning ---------------------------------------------------------------


async def test_rotation_writes_a_new_version_rather_than_overwriting(
    harness: Harness,
) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), GOOD)
    rotated = await harness.vault.rotate(
        harness.scope(), harness.handle(), {"api_key": "222222222222222222222222"}
    )

    versions = await harness.vault.versions(harness.scope(), harness.handle())
    assert rotated.version == 2
    assert [version.version for version in versions] == [1, 2]
    assert [version.is_active for version in versions] == [False, True]


async def test_rotating_something_that_was_never_configured_is_an_error(
    harness: Harness,
) -> None:
    """A silent create would hide an operator rotating the wrong handle."""
    with pytest.raises(CredentialNotConfigured):
        await harness.vault.rotate(harness.scope(), harness.handle(), GOOD)


async def test_rollback_moves_the_pointer_without_touching_a_value(
    harness: Harness,
) -> None:
    """FR-002. The operator does not need to still possess the old credential."""
    await harness.vault.store(harness.scope(), harness.handle(), GOOD)
    await harness.vault.rotate(
        harness.scope(), harness.handle(), {"api_key": "222222222222222222222222"}
    )

    restored = await harness.vault.activate(harness.scope(), harness.handle(), 1)

    assert restored.version == 1
    active = await harness.vault.active(harness.scope(), harness.handle())
    assert active is not None
    assert active.version == 1


async def test_rolling_back_to_a_version_that_does_not_exist_is_an_error(
    harness: Harness,
) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), GOOD)

    with pytest.raises(CredentialVersionNotFound):
        await harness.vault.activate(harness.scope(), harness.handle(), 9)


async def test_the_expiry_is_kept_with_the_version(harness: Harness) -> None:
    expiry = datetime.now(UTC) + timedelta(hours=1)

    stored = await harness.vault.store(harness.scope(), harness.handle(), GOOD, expires_at=expiry)

    assert stored.expires_at == expiry
    assert not stored.is_expired(datetime.now(UTC))
    assert stored.is_expired(expiry + timedelta(seconds=1))


# -- the metadata-only read API -----------------------------------------------


async def test_listing_returns_the_live_version_of_each_handle(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), GOOD)
    await harness.vault.store(harness.scope(), harness.handle(OTHER_TEAM_ID), GOOD)
    await harness.vault.rotate(
        harness.scope(), harness.handle(), {"api_key": "333333333333333333333333"}
    )

    listed = await harness.vault.list(harness.scope())

    assert [entry.handle.team_id for entry in listed] == [TEAM_ID, OTHER_TEAM_ID]
    assert [entry.version for entry in listed] == [2, 1]


async def test_an_unconfigured_handle_reads_as_none(harness: Harness) -> None:
    assert await harness.vault.active(harness.scope(), harness.handle()) is None


async def test_deleting_removes_every_version_and_the_pointer(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), GOOD)
    await harness.vault.rotate(
        harness.scope(), harness.handle(), {"api_key": "444444444444444444444444"}
    )

    removed = await harness.vault.delete(harness.scope(), harness.handle())

    assert removed == 2
    assert await harness.vault.active(harness.scope(), harness.handle()) is None
    assert await harness.vault.versions(harness.scope(), harness.handle()) == ()


# -- FR-003, as a property of the class surface -------------------------------


def test_the_vault_has_no_method_that_returns_a_credential() -> None:
    """The guarantee is an absence, so this is what asserting it looks like.

    A check that inspected return values could be satisfied by a method that
    returns a value in one branch. There being no such method cannot be.
    """
    public = {name for name in dir(Vault) if not name.startswith("_")}

    assert "reveal" not in public
    assert public == {
        "activate",
        "active",
        "delete",
        "list",
        "rotate",
        "store",
        "undecryptable",
        "versions",
    }


def test_the_version_record_has_no_field_that_could_hold_a_secret() -> None:
    fields = set(CredentialVersion.__dataclass_fields__)

    assert not fields & {"value", "values", "secret", "payload", "api_key"}


def test_the_stored_payload_is_stable_across_dictionary_ordering() -> None:
    """Two encodings of the same credential are the same bytes.

    Otherwise "did this rotation change anything" is unanswerable, because every
    write produces different ciphertext whether or not the value moved.
    """
    assert encode_payload({"b": "2", "a": "1"}) == encode_payload({"a": "1", "b": "2"})


def test_a_schema_registry_names_what_it_knows_when_asked_for_what_it_does_not() -> None:
    registry = CredentialSchemaRegistry.from_schemas(SCHEMA)

    with pytest.raises(UnknownIntegration) as raised:
        registry.get("typo")

    assert INTEGRATION in str(raised.value)
