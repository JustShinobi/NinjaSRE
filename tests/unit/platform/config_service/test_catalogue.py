"""FR-017 and FR-018: what the console can render, and why something is missing.

A capability absent from a team's list looks identical whether it was never
written, is switched off for that team, or needs an integration nobody has
connected. Two of those an operator fixes in a minute. So the view carries
reasons, and these tests are about the reasons rather than about the counts.
"""

from __future__ import annotations

import pytest

from platform.config_service.catalogue import (
    CapabilityDescription,
    CatalogueView,
    CredentialField,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
    integration_forms,
)
from platform.config_service.schema import RootConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def catalogue() -> StaticCatalogue:
    return StaticCatalogue.of(
        [
            CapabilityDescription(
                name="datadog-search-logs",
                tags=("datadog", "observability"),
                required_integrations=("datadog",),
            ),
            CapabilityDescription(
                name="datadog-query-metrics",
                tags=("datadog", "observability"),
                required_integrations=("datadog",),
            ),
            CapabilityDescription(name="kubectl-get-pods", tags=("kubernetes",)),
            CapabilityDescription(
                name="rollout-restart",
                tags=("kubernetes", "remediation"),
                side_effect_level="write_reversible",
            ),
        ]
    )


@pytest.fixture
def directory() -> StaticIntegrationDirectory:
    return StaticIntegrationDirectory.of(
        [
            IntegrationSchema(
                name="datadog",
                display_name="Datadog",
                credential_fields=(
                    CredentialField(name="api_key", label="API key"),
                    CredentialField(name="app_key", label="Application key"),
                ),
                settings_fields=(CredentialField(name="site", label="Site", secret=False),),
                hosts=("api.datadoghq.com",),
            ),
            IntegrationSchema(name="kubernetes", display_name="Kubernetes"),
            IntegrationSchema(name="pagerduty", display_name="PagerDuty"),
        ]
    )


# --- FR-017: the capability catalogue with reasons ---------------------------


def test_a_capability_whose_integration_is_connected_is_available(
    catalogue: StaticCatalogue,
) -> None:
    config = RootConfig.of({"integrations": {"active": [{"name": "datadog"}]}})

    view = CatalogueView.of(catalogue, config)

    assert view.reason_for("datadog-search-logs") is None
    assert "datadog-search-logs" in {entry.name for entry in view.available()}


def test_a_capability_whose_integration_is_missing_says_which_one(
    catalogue: StaticCatalogue,
) -> None:
    view = CatalogueView.of(catalogue, RootConfig.of({}))

    assert view.reason_for("datadog-search-logs") == "needs the datadog integration"


def test_a_capability_disabled_for_the_team_says_so(catalogue: StaticCatalogue) -> None:
    config = RootConfig.of({"capabilities": {"disabled": ["kubectl-get-pods"]}})

    assert CatalogueView.of(catalogue, config).reason_for("kubectl-get-pods") == (
        "disabled for this team"
    )


def test_a_capability_whose_tag_is_disabled_names_the_tag(catalogue: StaticCatalogue) -> None:
    config = RootConfig.of({"capabilities": {"disabled_tags": ["remediation"]}})

    reason = CatalogueView.of(catalogue, config).reason_for("rollout-restart")
    assert reason is not None
    assert "remediation" in reason


def test_a_capability_off_the_allow_list_says_so(catalogue: StaticCatalogue) -> None:
    config = RootConfig.of({"capabilities": {"enabled": ["kubectl-get-pods"]}})

    assert CatalogueView.of(catalogue, config).reason_for("rollout-restart") == (
        "not on this team's enabled list"
    )


def test_a_team_disable_is_reported_before_a_missing_integration(
    catalogue: StaticCatalogue,
) -> None:
    """The one the operator can act on without connecting anything comes first."""
    config = RootConfig.of({"capabilities": {"disabled": ["datadog-search-logs"]}})

    assert CatalogueView.of(catalogue, config).reason_for("datadog-search-logs") == (
        "disabled for this team"
    )


def test_the_console_can_say_what_connecting_an_integration_would_unlock(
    catalogue: StaticCatalogue,
) -> None:
    view = CatalogueView.of(catalogue, RootConfig.of({}))

    assert view.blocked_by_integration() == {
        "datadog": ("datadog-query-metrics", "datadog-search-logs")
    }


def test_a_disabled_integration_does_not_count_as_connected(
    catalogue: StaticCatalogue,
) -> None:
    config = RootConfig.of({"integrations": {"active": [{"name": "datadog", "enabled": False}]}})

    assert CatalogueView.of(catalogue, config).reason_for("datadog-search-logs") is not None


def test_every_installed_capability_appears_available_or_not(
    catalogue: StaticCatalogue,
) -> None:
    view = CatalogueView.of(catalogue, RootConfig.of({}))

    assert len(view.entries) == len(catalogue.names())
    assert len(view.available()) + len(view.unavailable()) == len(view.entries)


# --- FR-018: integration schemas for the console's forms ---------------------


def test_an_integration_schema_says_which_fields_are_secret(
    directory: StaticIntegrationDirectory,
) -> None:
    schema = directory.schema("datadog")

    assert schema is not None
    assert [f.name for f in schema.credential_fields] == ["api_key", "app_key"]
    assert all(f.secret for f in schema.credential_fields)
    assert not schema.settings_fields[0].secret


def test_configured_integrations_are_offered_before_the_rest(
    directory: StaticIntegrationDirectory,
) -> None:
    config = RootConfig.of({"integrations": {"active": [{"name": "kubernetes"}]}})

    forms = integration_forms(directory, config)

    assert forms[0].name == "kubernetes"
    assert {schema.name for schema in forms} == {"kubernetes", "datadog", "pagerduty"}


def test_every_installed_integration_is_offered_even_with_nothing_configured(
    directory: StaticIntegrationDirectory,
) -> None:
    forms = integration_forms(directory, RootConfig.of({}))

    assert [schema.name for schema in forms] == ["datadog", "kubernetes", "pagerduty"]
