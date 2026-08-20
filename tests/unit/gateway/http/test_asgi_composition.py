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


class _MarkerInvestigator:
    """Distinguishable from ``UnconfiguredInvestigator`` by identity alone.

    Not a real ``InvestigationRunner`` — nothing here calls any of its methods
    — it exists only so a test can tell "the factory's own object was
    installed" apart from "the stand-in was silently substituted for it".
    """

    marker = True


def build_marker() -> InvestigationRunner:
    """A factory whose runner is never the stand-in, for the tests below."""
    return _MarkerInvestigator()  # type: ignore[return-value]


def test_a_reference_that_will_not_load_keeps_the_deployment_up() -> None:
    """A named but unloadable factory degrades to the stand-in instead of crashing boot.

    This is the runtime user story's own acceptance scenario for a broken
    reference: the process still comes up, behaving like a deployment with no
    runtime — never crashing, and never behaving like one that has a runtime
    after all. Only ``validate(source)`` may refuse to boot outright.
    """
    from gateway.http.asgi import build_deployment
    from gateway.http.runtime import runtime_composed

    environ = {**STANDARD, NINJASRE_INVESTIGATOR_ENV: "not-a-real-module:not-a-real-factory"}

    deployment = build_deployment(environ)

    assert isinstance(deployment.state.investigator, UnconfiguredInvestigator)
    assert runtime_composed(deployment.state) is False


def test_a_working_reference_is_installed_verbatim_not_substituted() -> None:
    """A factory that does load is what the deployment composes — no silent swap.

    Paired with the test above so neither claim is provable by the other: a
    broken reference degrading to the stand-in says nothing about whether a
    *working* reference reaches the deployment untouched.
    """
    from gateway.http.asgi import build_deployment
    from gateway.http.runtime import runtime_composed

    environ = {
        **STANDARD,
        NINJASRE_INVESTIGATOR_ENV: "tests.unit.gateway.http.test_asgi_composition:build_marker",
    }

    deployment = build_deployment(environ)

    assert not isinstance(deployment.state.investigator, UnconfiguredInvestigator)
    assert getattr(deployment.state.investigator, "marker", False) is True
    assert runtime_composed(deployment.state) is True


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


async def test_the_boot_installs_the_encryption_key_the_operator_configured() -> None:
    """The defect this covers made every credential write a 500, on every deployment.

    The sequence's "verify the key" step only proved that stored credentials
    open. On a deployment that has stored none — which is every deployment on
    its first day — that passed without loading anything, and the key ring was
    still empty when somebody pasted their first provider key. The gateway
    carried the only call that loads it, in a method nothing called.
    """
    import os
    from unittest.mock import patch

    from gateway.http.serve import boot
    from platform.persistence.ports.health import HealthState, StoreHealth
    from platform.persistence.postgres.crypto import KEY_RING

    key = "0" * 43 + "="
    KEY_RING.clear()
    assert not KEY_RING.is_configured

    class Store:
        def migrator(self) -> None:
            return None

        def install_encryption_key(self) -> bool:
            return KEY_RING.configure_from_environment()

        async def health(self) -> StoreHealth:
            return StoreHealth(state=HealthState.HEALTHY, connected=True)

    class Deployment:
        store = Store()

    try:
        environment = {
            "NINJASRE_DATABASE_ENCRYPTION_KEY": key,
            "NINJASRE_DATABASE_URL": "postgresql://localhost/ninjasre",
            "NINJASRE_LLM_PROVIDER": "ollama",
        }
        with patch.dict(os.environ, environment, clear=False):
            result = await boot(Deployment())  # type: ignore[arg-type]
        assert KEY_RING.is_configured, "the boot left the key ring empty"
        assert result.key_installed
    finally:
        KEY_RING.clear()
