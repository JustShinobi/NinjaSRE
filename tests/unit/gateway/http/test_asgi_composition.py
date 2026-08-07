"""What the container's entry point composes, and what it refuses to guess.

The composition root is the one place allowed to name a backend, so this is the
one place that test has to be. What is worth pinning is not the wiring — mypy
covers that — but the two decisions:

Validation runs *before* a connection is opened, so an unset database URL
reports as an unset database URL rather than as a connection failure ten seconds
later.

And an investigation runtime nobody named is a refusal with a remedy in it,
raised when a request asks for one, rather than a refusal to start. A deployment
whose console, history, configuration, and health all work is worth having up
while somebody wires the runtime.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    NINJASRE_INVESTIGATOR_ENV,
)
from config.constants.llm import ANTHROPIC_API_KEY_ENV, NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from gateway.http.asgi import (
    InvestigatorNotConfigured,
    UnconfiguredInvestigator,
    load_investigator,
)
from gateway.http.services import InvestigationRunner, InvestigationStart
from platform.startup.errors import ConfigurationInvalid
from platform.startup.readiness import DependencyState

pytestmark = pytest.mark.unit

STANDARD = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_LLM_PROVIDER_ENV: "anthropic",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}


def test_the_stand_in_is_the_port_the_routes_hold() -> None:
    """The routes must not need a branch for "no runtime is configured"."""
    assert isinstance(UnconfiguredInvestigator(), InvestigationRunner)


async def test_starting_an_investigation_refuses_by_naming_the_setting() -> None:
    stand_in = UnconfiguredInvestigator()

    with pytest.raises(InvestigatorNotConfigured) as caught:
        await stand_in.investigate(
            InvestigationStart(
                run_id="r-1",
                objective="why is checkout slow",
                team_node_id="payments",
                principal_id="operator",
            )
        )

    assert NINJASRE_INVESTIGATOR_ENV in str(caught.value)
    assert "module:factory" in str(caught.value)


async def test_listing_interactions_answers_rather_than_refusing() -> None:
    """A run that does not exist has no open questions; that is an answer, not an error."""
    stand_in = UnconfiguredInvestigator()

    assert await stand_in.pending_interactions("r-1") == ()
    assert await stand_in.find_interaction("i-1") is None


def test_a_factory_reference_that_is_not_module_colon_name_is_refused() -> None:
    with pytest.raises(ConfigurationInvalid) as caught:
        load_investigator("not-a-reference")

    assert NINJASRE_INVESTIGATOR_ENV in caught.value.settings


def test_a_factory_that_cannot_be_imported_fails_at_boot_and_names_why() -> None:
    """An import error an operator can fix, rather than a 500 during an incident."""
    with pytest.raises(ConfigurationInvalid) as caught:
        load_investigator("tests.unit.gateway.http.test_asgi_composition:nothing_here")

    assert "could not be imported" in str(caught.value)


def test_a_factory_that_exists_is_called_and_its_runner_returned() -> None:
    runner = load_investigator("tests.unit.gateway.http.test_asgi_composition:build_stand_in")

    assert isinstance(runner, UnconfiguredInvestigator)


def build_stand_in() -> InvestigationRunner:
    """A factory in the shape ``NINJASRE_INVESTIGATOR`` names, for the test above."""
    return UnconfiguredInvestigator()


def test_composition_validates_before_it_opens_a_connection() -> None:
    """An unset database URL must report as an unset database URL."""
    from gateway.http.asgi import build_deployment

    environ = {key: value for key, value in STANDARD.items() if key != NINJASRE_DATABASE_URL_ENV}

    with pytest.raises(ConfigurationInvalid) as caught:
        build_deployment(environ)

    assert NINJASRE_DATABASE_URL_ENV in caught.value.settings


def test_readiness_breaks_the_store_probe_into_the_dependencies_it_covered() -> None:
    """ "Not ready" is not an answer; "the schema is behind" is."""
    from gateway.http.serve import readiness_of
    from platform.persistence.health import summarise
    from platform.persistence.ports.health import ExtensionStatus, MigrationStatus

    health = summarise(
        connected=True,
        server_version=16,
        extensions=(
            ExtensionStatus(name="vector", available=True),
            ExtensionStatus(name="age", available=False),
        ),
        migrations=MigrationStatus(head_revision="0004", applied_revision="0004"),
    )

    entries = {entry.name: entry for entry in readiness_of(health)}

    assert entries["database"].state is DependencyState.READY
    assert entries["schema"].state is DependencyState.READY
    assert entries["extension vector"].state is DependencyState.READY
    assert entries["extension age"].state is DependencyState.UNAVAILABLE
    assert entries["extension age"].required is False, "no graph is degraded, not down"


def test_an_unmigrated_schema_keeps_the_deployment_out_of_rotation() -> None:
    from gateway.http.serve import readiness_of
    from platform.persistence.health import summarise
    from platform.persistence.ports.health import MigrationStatus
    from platform.startup.readiness import report

    health = summarise(
        connected=True,
        server_version=16,
        migrations=MigrationStatus(head_revision="0004", applied_revision="0002"),
    )

    readiness = report(readiness_of(health))

    assert not readiness.ready
    assert "schema" in readiness.summary()


def test_a_deployment_that_cannot_decrypt_its_credentials_is_degraded_and_says_so() -> None:
    from gateway.http.serve import readiness_of
    from platform.persistence.health import summarise
    from platform.persistence.ports.health import MigrationStatus
    from platform.startup.readiness import report

    health = summarise(
        connected=True,
        server_version=16,
        migrations=MigrationStatus(head_revision="0004", applied_revision="0004"),
        undecryptable_credentials=("pagerduty::payments",),
    )

    readiness = report(readiness_of(health))

    assert readiness.ready, "a wrong key is not a reason to stop serving history"
    assert any("stored credentials" in reason for reason in readiness.reasons())
