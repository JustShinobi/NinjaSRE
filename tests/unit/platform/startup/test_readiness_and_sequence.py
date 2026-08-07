"""Readiness that names the dependency, and a boot order that is checked rather than described.

The ordering tests are the ones that matter. The startup sequence's comments say
key verification happens before migrations because a wrong key should fail in
seconds rather than after a schema change — and a comment does not survive a
refactor. These do.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
)
from config.constants.llm import ANTHROPIC_API_KEY_ENV, NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from platform.startup.errors import ConfigurationInvalid, UnknownDeploymentProfile
from platform.startup.profiles import DeploymentProfile
from platform.startup.readiness import DependencyReadiness, DependencyState, report
from platform.startup.sequence import run_startup
from tests.unit.platform.startup.conftest import REVISIONS, FakeMigrator, SchemaState

pytestmark = pytest.mark.unit

STANDARD_ENV = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_LLM_PROVIDER_ENV: "anthropic",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}


# -- readiness ----------------------------------------------------------------


def test_a_deployment_with_every_dependency_up_is_ready() -> None:
    result = report(
        (
            DependencyReadiness(name="database", state=DependencyState.READY),
            DependencyReadiness(name="credential proxy", state=DependencyState.READY),
        )
    )

    assert result.ready
    assert result.reasons() == ()
    assert "every dependency is available" in result.summary()


def test_a_missing_required_dependency_is_named_rather_than_summed_into_a_boolean() -> None:
    """FR-008: which dependency is not ready is the half an on-call engineer needs."""
    result = report(
        (
            DependencyReadiness(
                name="database",
                state=DependencyState.UNAVAILABLE,
                detail="the schema is two revisions behind",
            ),
            DependencyReadiness(name="credential proxy", state=DependencyState.READY),
        )
    )

    assert not result.ready
    assert [entry.name for entry in result.blocking] == ["database"]
    assert "database" in result.summary()
    assert "two revisions behind" in result.summary()


def test_an_optional_dependency_that_is_down_is_reported_and_survived() -> None:
    """A degraded investigation is worse than a good one, not worse than none."""
    result = report(
        (
            DependencyReadiness(name="database", state=DependencyState.READY),
            DependencyReadiness(
                name="service topology",
                state=DependencyState.UNAVAILABLE,
                required=False,
                detail="the graph extension is not installed",
            ),
        )
    )

    assert result.ready
    assert [entry.name for entry in result.degraded] == ["service topology"]
    assert "degraded" in result.summary()


def test_an_unprobed_dependency_counts_as_not_ready() -> None:
    """A deployment reporting ready because nobody looked is the failure to avoid."""
    result = report((DependencyReadiness(name="database", state=DependencyState.UNKNOWN),))

    assert not result.ready


def test_a_draining_replica_is_not_ready_whatever_its_dependencies_say() -> None:
    result = report(
        (DependencyReadiness(name="database", state=DependencyState.READY),), draining=True
    )

    assert not result.ready
    assert "draining" in result.summary()


def test_a_report_can_be_asked_about_one_dependency_by_name() -> None:
    result = report((DependencyReadiness(name="database", state=DependencyState.READY),))

    assert result.named("database") is not None
    assert result.named("nothing") is None


def test_every_finding_reaches_the_record_a_health_endpoint_serves() -> None:
    result = report(
        (
            DependencyReadiness(
                name="database", state=DependencyState.UNAVAILABLE, detail="connection refused"
            ),
        )
    )

    record = result.to_record()

    assert record["ready"] is False
    assert record["blocking"] == ["database"]
    assert "connection refused" in str(record["reasons"])


# -- the sequence -------------------------------------------------------------


async def test_a_valid_deployment_resolves_its_profile_and_migrates(
    schema: SchemaState,
) -> None:
    result = await run_startup(environ=STANDARD_ENV, migrator=FakeMigrator(state=schema))

    assert result.profile is DeploymentProfile.STANDARD
    assert result.migration is not None
    assert result.migration.to_revision == REVISIONS[-1]
    assert result.validation.ok


async def test_an_invalid_configuration_stops_the_boot_before_the_database_is_touched(
    schema: SchemaState,
) -> None:
    environ = {key: value for key, value in STANDARD_ENV.items() if key != ANTHROPIC_API_KEY_ENV}

    with pytest.raises(ConfigurationInvalid) as caught:
        await run_startup(environ=environ, migrator=FakeMigrator(state=schema))

    assert ANTHROPIC_API_KEY_ENV in caught.value.settings
    assert schema.upgrades == 0


async def test_an_unknown_profile_stops_the_boot_first_of_all(schema: SchemaState) -> None:
    environ = STANDARD_ENV | {NINJASRE_DEPLOYMENT_PROFILE_ENV: "produciton"}

    with pytest.raises(UnknownDeploymentProfile):
        await run_startup(environ=environ, migrator=FakeMigrator(state=schema))

    assert schema.upgrades == 0


async def test_the_key_is_verified_before_the_schema_is_changed(schema: SchemaState) -> None:
    """FR-020, and the reason for its position: a wrong key must fail in seconds."""

    async def refuse() -> None:
        raise RuntimeError("stored credentials do not open with the configured key")

    with pytest.raises(RuntimeError):
        await run_startup(
            environ=STANDARD_ENV, migrator=FakeMigrator(state=schema), verify_credentials=refuse
        )

    assert schema.upgrades == 0, "a key mismatch must not leave a half-migrated database"
    assert schema.applied is None


async def test_a_verified_key_lets_the_boot_continue(schema: SchemaState) -> None:
    checked: list[str] = []

    async def accept() -> None:
        checked.append("verified")

    result = await run_startup(
        environ=STANDARD_ENV, migrator=FakeMigrator(state=schema), verify_credentials=accept
    )

    assert checked == ["verified"]
    assert result.credentials_verified
    assert schema.applied == REVISIONS[-1]


async def test_a_deployment_that_migrates_out_of_band_checks_without_writing(
    schema: SchemaState,
) -> None:
    """A Helm release runs the migration job; its replicas must not race it."""
    schema.applied = REVISIONS[-1]

    result = await run_startup(
        environ=STANDARD_ENV,
        migrator=FakeMigrator(state=schema),
        apply_migrations=False,
    )

    assert result.migration is not None
    assert not result.migration.ran
    assert schema.upgrades == 0


async def test_a_preflight_with_no_collaborators_validates_and_nothing_else() -> None:
    """An operator checking their .env before they have a database."""
    result = await run_startup(environ=STANDARD_ENV)

    assert result.migration is None
    assert not result.credentials_verified
    assert result.validation.ok


async def test_the_startup_summary_carries_the_profile_and_what_it_migrated(
    schema: SchemaState,
) -> None:
    result = await run_startup(
        environ=STANDARD_ENV,
        migrator=FakeMigrator(state=schema),
        readiness=report((DependencyReadiness(name="database", state=DependencyState.READY),)),
    )

    summary = result.summary()

    assert str(DeploymentProfile.STANDARD) in summary
    assert "schema migrated" in summary
    assert "every dependency is available" in summary
