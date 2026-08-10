"""SC-004 and SC-007: a dangling reference and a pasted credential, both refused
at the write.

The secret test uses the shipped guardrail ruleset rather than a pattern written
for the occasion. A rejection proven against a hand-written pattern proves only
that the pattern matched itself.
"""

from __future__ import annotations

import pytest

from platform.config_service.catalogue import (
    CapabilityDescription,
    CredentialField,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
)
from platform.config_service.errors import SecretInConfiguration
from platform.config_service.field_policy import FieldPolicy, PolicySet
from platform.config_service.validation import ConfigValidator
from platform.guardrails.engine import GuardrailEngine

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
                credential_fields=(
                    CredentialField(name="api_key", secret=True),
                    CredentialField(name="app_key", secret=True),
                ),
                settings_fields=(CredentialField(name="site", secret=False),),
            ),
            IntegrationSchema(name="kubernetes"),
        ]
    )


@pytest.fixture
def validator(
    catalogue: StaticCatalogue, directory: StaticIntegrationDirectory, engine: GuardrailEngine
) -> ConfigValidator:
    return ConfigValidator(catalogue=catalogue, integrations=directory, guardrails=engine)


# --- T024 / SC-004: capability cross-reference -------------------------------


def test_a_reference_to_a_capability_nobody_installed_fails_at_write(
    validator: ConfigValidator,
) -> None:
    outcome = validator.validate({"capabilities": {"disabled": ["kubectl-teleport"]}})

    assert not outcome.ok
    assert outcome.paths() == ("capabilities.kubectl-teleport",)


def test_a_reference_to_an_installed_capability_passes(validator: ConfigValidator) -> None:
    assert validator.validate({"capabilities": {"disabled": ["kubectl-get-pods"]}}).ok


def test_a_dangling_reference_inside_a_subagent_is_found(validator: ConfigValidator) -> None:
    outcome = validator.validate(
        {"agents": {"subagents": [{"name": "historian", "capabilities": ["git-log"]}]}}
    )

    assert outcome.paths() == ("capabilities.git-log",)


def test_a_dangling_reference_in_the_autonomous_allow_list_is_found(
    validator: ConfigValidator,
) -> None:
    outcome = validator.validate(
        {"policies": {"approvals": {"autonomous_capabilities": ["nuke-everything"]}}}
    )

    assert outcome.paths() == ("capabilities.nuke-everything",)


# --- T025: integration cross-reference ---------------------------------------


def test_a_reference_to_an_integration_nobody_installed_fails_at_write(
    validator: ConfigValidator,
) -> None:
    outcome = validator.validate({"integrations": {"active": [{"name": "pagerduty"}]}})

    assert outcome.paths() == ("integrations.pagerduty",)


def test_a_reference_to_an_installed_integration_passes(validator: ConfigValidator) -> None:
    assert validator.validate({"integrations": {"active": [{"name": "datadog"}]}}).ok


# --- T026 / SC-007: secret rejection -----------------------------------------


@pytest.mark.parametrize(
    ("path_value", "expected_path"),
    [
        (
            {"integrations": {"active": [{"name": "datadog", "site": "AKIAIOSFODNN7EXAMPLE"}]}},
            "integrations.active.0.site",
        ),
    ],
)
def test_an_access_key_pasted_into_a_field_is_refused(
    validator: ConfigValidator, path_value: dict[str, object], expected_path: str
) -> None:
    outcome = validator.validate(path_value)

    assert not outcome.ok
    assert any("vault" in error.message for error in outcome.errors)


def test_a_private_key_pasted_into_a_prompt_is_refused(validator: ConfigValidator) -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----"
    outcome = validator.validate({"agents": {"prompts": {"investigator": pem}}})

    assert outcome.paths() == ("agents.prompts.investigator",)
    assert "vault" in outcome.errors[0].message


def test_the_refusal_never_quotes_the_secret(validator: ConfigValidator) -> None:
    secret = "ghp_" + "a" * 36
    outcome = validator.validate(
        {"integrations": {"active": [{"name": "datadog", "site": secret}]}}
    )

    assert not outcome.ok
    assert all(secret not in error.message for error in outcome.errors)


def test_the_refusal_names_the_field_and_points_at_the_vault(
    validator: ConfigValidator,
) -> None:
    with pytest.raises(SecretInConfiguration) as raised:
        validator.check_secrets({"integrations": {"active": [{"credential": "ghp_" + "b" * 36}]}})

    assert raised.value.path == "integrations.active.0.credential"
    assert "vault" in str(raised.value)
    assert "ghp_" not in str(raised.value)


def test_a_secret_inside_a_list_entry_is_found(validator: ConfigValidator) -> None:
    outcome = validator.validate(
        {"policies": {"guardrails": {"disabled_rules": ["xoxb-1234567890-abcdefghijkl"]}}}
    )

    assert not outcome.ok


def test_an_ordinary_configuration_value_is_not_mistaken_for_a_secret(
    validator: ConfigValidator,
) -> None:
    """A rule that fires on prose is a rule an operator disables within a week."""
    assert validator.validate(
        {
            "integrations": {
                "active": [
                    {"name": "datadog", "credential": "datadog-prod", "site": "datadoghq.eu"}
                ]
            },
            "agents": {
                "prompts": {
                    "investigator": (
                        "Never read a bearer token out of a log line, and never quote a "
                        "private key you find. Report the finding instead."
                    )
                }
            },
        }
    ).ok


def test_a_credential_reference_is_not_a_credential(validator: ConfigValidator) -> None:
    assert validator.validate(
        {"integrations": {"active": [{"name": "datadog", "credential": "vault://datadog-prod"}]}}
    ).ok


# --- A field a vendor calls secret cannot be a configuration field -----------
#
# ``IntegrationSettings`` is a closed schema, so ``api_key`` written beside
# ``name`` is already refused as a shape error. Its ``settings`` map is open,
# because the vendor defines what goes in it — and that is the way round the
# credential route that is left. The shape scan catches a value that *looks*
# like a credential; this catches a field the vendor's own schema calls secret,
# whose value looks like nothing in particular. A key an operator invented
# matches nobody's pattern.


def test_a_field_an_integration_calls_secret_is_refused_whatever_its_value_looks_like(
    validator: ConfigValidator,
) -> None:
    outcome = validator.validate(
        {"integrations": {"active": [{"name": "datadog", "settings": {"api_key": "hunter2"}}]}}
    )

    assert not outcome.ok
    assert outcome.paths() == ("integrations.active.0.settings.api_key",)
    assert "vault" in outcome.errors[0].message


def test_the_refusal_names_the_field_and_not_the_value(validator: ConfigValidator) -> None:
    outcome = validator.validate(
        {"integrations": {"active": [{"name": "datadog", "settings": {"app_key": "correcthorse"}}]}}
    )

    assert not outcome.ok
    assert "app_key" in outcome.errors[0].message
    assert all("correcthorse" not in error.message for error in outcome.errors)


def test_a_secret_field_smuggled_under_another_vendors_settings_is_found_too(
    validator: ConfigValidator,
) -> None:
    """A secret field name is one wherever it is written, not only under its own vendor."""
    outcome = validator.validate(
        {"integrations": {"active": [{"name": "kubernetes", "settings": {"api_key": "whatever"}}]}}
    )

    assert not outcome.ok
    assert outcome.paths() == ("integrations.active.0.settings.api_key",)


def test_a_field_the_same_vendor_calls_public_is_left_alone(
    validator: ConfigValidator,
) -> None:
    """``site`` is configuration a capability may legitimately see, and stays so."""
    assert validator.validate(
        {
            "integrations": {
                "active": [
                    {
                        "name": "datadog",
                        "site": "datadoghq.eu",
                        "settings": {"site": "datadoghq.eu"},
                    }
                ]
            }
        }
    ).ok


def test_a_deployment_with_no_integration_directory_refuses_nothing_on_this_pass() -> None:
    """The check is over what is installed, so it cannot be evaluated without it.

    Not a silent pass in production — ``ConfigService`` is always composed with a
    directory. This is the merge-test path, where the point is the merge.
    """
    assert (
        ConfigValidator()
        .validate({"integrations": {"active": [{"name": "datadog", "settings": {"api_key": "x"}}]}})
        .ok
    )


# --- Everything is reported at once ------------------------------------------


def test_shape_reference_and_secret_problems_are_reported_together(
    validator: ConfigValidator,
) -> None:
    outcome = validator.validate(
        {
            "agents": {"tool_budget": "eight"},
            "capabilities": {"disabled": ["nonexistent"]},
            "integrations": {"active": [{"name": "datadog", "site": "AKIAIOSFODNN7EXAMPLE"}]},
        }
    )

    assert set(outcome.paths()) == {
        "agents.tool_budget",
        "capabilities.nonexistent",
        "integrations.active.0.site",
    }


# --- Field policies join the same pass ---------------------------------------


def test_a_required_field_with_no_value_is_reported_alongside_shape_errors(
    validator: ConfigValidator,
) -> None:
    policies = PolicySet.of([FieldPolicy("integrations.active", required=True)])

    outcome = validator.validate({"agents": {"tool_budget": 4}}, policies)

    assert outcome.paths() == ("integrations.active",)


def test_a_value_outside_its_allowed_set_is_reported(validator: ConfigValidator) -> None:
    policies = PolicySet.of([FieldPolicy("policies.masking.level", allowed_values=("strict",))])

    outcome = validator.validate({"policies": {"masking": {"level": "off"}}}, policies)

    assert outcome.paths() == ("policies.masking.level",)


def test_a_partial_node_document_is_not_held_to_the_required_fields(
    validator: ConfigValidator,
) -> None:
    """A field required at the leaf may legitimately be supplied by an ancestor."""
    assert validator.validate({"agents": {"tool_budget": 4}}).ok


# --- Without a wired catalogue -----------------------------------------------


def test_without_a_catalogue_references_are_not_checked(engine: GuardrailEngine) -> None:
    """Stated, not accidental: the composition root always wires one."""
    assert (
        ConfigValidator(guardrails=engine)
        .validate({"capabilities": {"disabled": ["anything-at-all"]}})
        .ok
    )
