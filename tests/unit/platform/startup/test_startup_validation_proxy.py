"""The credential proxy's own configuration check, narrower than the deployment's.

``validate`` is the whole-deployment "minimum viable configuration" check and
it fatally requires a model provider. That rule makes no sense for the
credential proxy: it brokers credentials and never calls a model, so a
deployment with no provider configured anywhere is not a broken proxy.

The pair of assertions below is what makes ``validate_proxy`` a narrowing
rather than a deletion. A test that only proved the proxy now starts with no
provider would pass equally if every check had been removed; asserting that a
configuration missing something that genuinely is the proxy's own is still
refused is what tells the two apart.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_DEV,
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_CA_BUNDLE_ENV,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    NINJASRE_OTEL_ENDPOINT_ENV,
)
from config.constants.llm import NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import (
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from platform.startup.validation import validate_proxy

pytestmark = pytest.mark.unit


#: What the proxy's own boot needs on the standard profile — no provider
#: anywhere, deliberately, since that absence is exactly the claim this file
#: exists to prove is not the proxy's problem.
PROXY_OWN_CONFIGURATION = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}


def without(*names: str) -> dict[str, str]:
    """Return the proxy's own configuration with ``names`` removed."""
    return {key: value for key, value in PROXY_OWN_CONFIGURATION.items() if key not in names}


def test_a_configuration_with_no_model_provider_anywhere_is_valid_for_the_proxy() -> None:
    """The exact defect: the proxy never calls a model, so its absence is not
    a reason to refuse the boot."""
    report = validate_proxy(PROXY_OWN_CONFIGURATION)

    assert report.ok, report.summary()
    assert NINJASRE_LLM_PROVIDER_ENV not in {finding.setting for finding in report.findings}


@pytest.mark.parametrize(
    ("label", "removed", "expected_setting"),
    (
        ("its own database", NINJASRE_DATABASE_URL_ENV, NINJASRE_DATABASE_URL_ENV),
        (
            "its own address on a profile that runs it as its own service",
            NINJASRE_CREDENTIAL_PROXY_URL_ENV,
            NINJASRE_CREDENTIAL_PROXY_URL_ENV,
        ),
    ),
    ids=["database", "proxy-address"],
)
def test_the_proxy_still_refuses_a_configuration_missing_something_of_its_own(
    label: str, removed: str, expected_setting: str
) -> None:
    """Narrowed, not deleted: the settings that are genuinely the proxy's own
    still stop the boot, and the report still never blames the provider."""
    report = validate_proxy(without(removed))

    assert not report.ok, f"a configuration missing {label} was accepted"
    fatal_settings = {finding.setting for finding in report.fatal}
    assert expected_setting in fatal_settings, (
        f"missing {label} did not name {expected_setting}; got {fatal_settings}"
    )
    assert NINJASRE_LLM_PROVIDER_ENV not in fatal_settings, (
        "the proxy's own check must not also blame a setting it never reads"
    )


def test_the_dev_profile_needs_no_proxy_address_either() -> None:
    """Characterisation: the in-process profile never asks, matching what
    ``validate`` already establishes for the same rule."""
    environ = {
        NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_DEV,
        NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@localhost:5432/ninjasre",
    }

    report = validate_proxy(environ)

    assert report.ok, report.summary()


def test_an_encryption_key_that_is_not_base64_still_stops_the_proxy() -> None:
    """The key's *shape* is fatal even though its absence is only advisory —
    the same asymmetry ``validate`` applies, still enforced here."""
    environ = PROXY_OWN_CONFIGURATION | {NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "not base64!!"}

    report = validate_proxy(environ)

    assert not report.ok
    assert NINJASRE_DATABASE_ENCRYPTION_KEY_ENV in {f.setting for f in report.fatal}


def test_a_trust_bundle_that_is_not_on_disk_still_stops_the_proxy() -> None:
    environ = PROXY_OWN_CONFIGURATION | {
        NINJASRE_CA_BUNDLE_ENV: "/etc/ssl/certs/nothing-is-here.pem"
    }

    report = validate_proxy(environ)

    assert not report.ok
    assert NINJASRE_CA_BUNDLE_ENV in {f.setting for f in report.fatal}


def test_air_gapped_with_no_provider_configured_anywhere_is_still_valid() -> None:
    """The trap this file exists to catch: ``external_destinations`` always
    synthesises a model-provider destination, even from an unset provider
    falling back to the default. If the proxy's air-gapped check reused
    ``validate``'s unmodified, it would refuse over that synthesised
    destination too — the same mistake in a different disguise."""
    environ = PROXY_OWN_CONFIGURATION | {NINJASRE_AIR_GAPPED_ENV: "true"}

    report = validate_proxy(environ)

    assert report.ok, report.summary()


def test_air_gapped_still_refuses_a_genuine_non_provider_leak() -> None:
    """The rule is narrowed around the provider, not deleted: a destination
    that has nothing to do with the model provider still stops the boot."""
    environ = PROXY_OWN_CONFIGURATION | {
        NINJASRE_AIR_GAPPED_ENV: "true",
        NINJASRE_OTEL_ENDPOINT_ENV: "https://otel.example.com",
    }

    report = validate_proxy(environ)

    assert not report.ok
    fatal_settings = {finding.setting for finding in report.fatal}
    assert NINJASRE_OTEL_ENDPOINT_ENV in fatal_settings
    assert NINJASRE_LLM_PROVIDER_ENV not in fatal_settings
