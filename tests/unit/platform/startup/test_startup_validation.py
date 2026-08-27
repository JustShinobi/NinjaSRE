"""SC-006: every misconfiguration produces an error naming the setting and the problem.

The fixture set below is the whole point of this file. A validator is easy to
write and easy to write badly — the bad version reports "configuration error"
and leaves an operator reading source code at three in the morning — so each
fixture asserts three things about the failure it produces: that it happens at
all, that the message names the environment variable, and that it says what to
do about it.

The messages are asserted by substring rather than by equality on purpose.
Pinning the whole sentence would make every improvement to the wording a test
change, and the wording is the part that should be free to improve.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_DEV,
    DEPLOYMENT_PROFILE_ENTERPRISE,
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_CA_BUNDLE_ENV,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
)
from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)
from config.constants.persistence import (
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from config.constants.security import (
    NINJASRE_CREDENTIAL_PROXY_URL_ENV,
    NINJASRE_SANDBOX_PROFILE_ENV,
)
from platform.startup.validation import (
    PROVIDER_CREDENTIAL_SETTING,
    Severity,
    validate,
)

pytestmark = pytest.mark.unit


#: The smallest configuration that is actually valid on the standard profile:
#: one provider credential and a database. Everything else defaults (FR-010).
MINIMUM_VIABLE = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "A" * 43 + "=",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8081",
}


def without(*names: str) -> dict[str, str]:
    """Return the minimum viable configuration with ``names`` removed."""
    return {key: value for key, value in MINIMUM_VIABLE.items() if key not in names}


def with_(**overrides: str) -> dict[str, str]:
    """Return the minimum viable configuration with ``overrides`` applied."""
    return MINIMUM_VIABLE | overrides


# -- the fixture set (T001) ---------------------------------------------------


#: Each case is (label, environment, the setting the message must name, a phrase
#: the remedy must contain). The last element is what turns "it failed" into
#: "an operator knows what to type next".
MISCONFIGURATIONS: tuple[tuple[str, dict[str, str], str, str], ...] = (
    (
        "an encryption key that is not base64",
        with_(**{NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "not base64!!"}),
        NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
        "base64",
    ),
    (
        "an encryption key of the wrong length",
        with_(**{NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "c2hvcnQ="}),
        NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
        "32",
    ),
    (
        "no database at all",
        without(NINJASRE_DATABASE_URL_ENV),
        NINJASRE_DATABASE_URL_ENV,
        "postgresql://",
    ),
    (
        "a database URL that is not PostgreSQL",
        with_(**{NINJASRE_DATABASE_URL_ENV: "mysql://ninjasre@db/ninjasre"}),
        NINJASRE_DATABASE_URL_ENV,
        "PostgreSQL",
    ),
    (
        "an invalid deployment profile",
        with_(**{NINJASRE_DEPLOYMENT_PROFILE_ENV: "produciton"}),
        NINJASRE_DEPLOYMENT_PROFILE_ENV,
        DEPLOYMENT_PROFILE_STANDARD,
    ),
    (
        "a sandbox profile that contradicts the deployment profile",
        with_(**{NINJASRE_SANDBOX_PROFILE_ENV: "process"}),
        NINJASRE_SANDBOX_PROFILE_ENV,
        DEPLOYMENT_PROFILE_STANDARD,
    ),
    (
        "no credential proxy on a profile that runs one out of process",
        without(NINJASRE_CREDENTIAL_PROXY_URL_ENV),
        NINJASRE_CREDENTIAL_PROXY_URL_ENV,
        "proxy",
    ),
    (
        "air-gapped with a hosted provider's credential in the environment",
        with_(**{NINJASRE_AIR_GAPPED_ENV: "1"}),
        ANTHROPIC_API_KEY_ENV,
        "local",
    ),
    (
        "a trust bundle that is not on disk",
        with_(**{NINJASRE_CA_BUNDLE_ENV: "/etc/ssl/certs/nothing-is-here.pem"}),
        NINJASRE_CA_BUNDLE_ENV,
        "readable",
    ),
)


@pytest.mark.parametrize(
    ("label", "environ", "setting", "remedy_phrase"),
    MISCONFIGURATIONS,
    ids=[case[0] for case in MISCONFIGURATIONS],
)
def test_every_misconfiguration_names_its_setting_and_what_to_do(
    label: str,
    environ: dict[str, str],
    setting: str,
    remedy_phrase: str,
) -> None:
    """SC-006. A generic failure here is the defect this test exists to catch."""
    report = validate(environ)

    assert not report.ok, f"{label} was accepted"
    failures = [finding for finding in report.findings if finding.severity is Severity.FATAL]
    named = [finding for finding in failures if finding.setting == setting]
    assert named, f"{label} did not name {setting}; got {[f.setting for f in failures]}"

    finding = named[0]
    assert setting in str(finding), "the rendered message has to carry the setting name"
    assert remedy_phrase.lower() in finding.remedy.lower(), (
        f"the remedy for {label} does not mention {remedy_phrase!r}: {finding.remedy!r}"
    )


def test_the_minimum_viable_configuration_is_one_provider_credential() -> None:
    """FR-010: everything except a provider and a database has a working default."""
    assert validate(MINIMUM_VIABLE).ok


def test_the_dev_profile_needs_neither_a_proxy_url_nor_a_container_runtime() -> None:
    """FR-002: the dev profile runs the proxy in-process, so it configures none."""
    environ = {
        NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_DEV,
        NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@localhost:5432/ninjasre",
        ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    }

    report = validate(environ)

    assert report.ok, report.summary()


def test_an_air_gapped_deployment_with_a_local_model_is_valid() -> None:
    """FR-023 and SC-005: no-egress is a supported shape, not a broken one."""
    environ = with_(
        **{
            NINJASRE_AIR_GAPPED_ENV: "true",
            OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1",
        }
    )
    del environ[ANTHROPIC_API_KEY_ENV]

    report = validate(environ)

    assert report.ok, report.summary()


def test_the_enterprise_profile_wants_the_kubernetes_sandbox() -> None:
    environ = with_(
        **{
            NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_ENTERPRISE,
            NINJASRE_SANDBOX_PROFILE_ENV: "kubernetes",
        }
    )

    assert validate(environ).ok


def test_every_finding_is_reported_rather_than_the_first_one() -> None:
    """One restart per problem is how a ten-minute setup becomes an hour."""
    environ = without(ANTHROPIC_API_KEY_ENV, NINJASRE_DATABASE_URL_ENV)
    environ[NINJASRE_DATABASE_ENCRYPTION_KEY_ENV] = "not base64!!"

    report = validate(environ)

    settings = {finding.setting for finding in report.findings}
    assert {
        PROVIDER_CREDENTIAL_SETTING,
        NINJASRE_DATABASE_URL_ENV,
        NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    } <= settings


def test_the_summary_reads_as_something_an_operator_can_act_on() -> None:
    report = validate(without(NINJASRE_DATABASE_URL_ENV))

    summary = report.summary()

    assert NINJASRE_DATABASE_URL_ENV in summary
    assert summary.count("\n") >= 1, "one line per finding, so a boot log shows them all"


def test_a_valid_configuration_summarises_as_much() -> None:
    assert "no configuration problems" in validate(MINIMUM_VIABLE).summary().lower()


# -- the model provider is a first-run step, not a deployment setting ---------


def test_a_deployment_that_equips_no_provider_starts_and_is_told_it_equips_none() -> None:
    """Connecting a model provider is a first-run step, so the boot must reach it.

    The console ships a screen for exactly this state, and the setup checklist
    lists connecting a provider as its second step. A fatal finding here kills
    the process that would render either of them, so the absence is advisory:
    reported at every boot, and never a reason to refuse one.
    """
    report = validate(without(ANTHROPIC_API_KEY_ENV))

    assert report.ok, report.summary()
    advisory = [
        finding for finding in report.warnings if finding.setting == PROVIDER_CREDENTIAL_SETTING
    ]
    assert advisory, "a deployment equipping no provider should still be told that it equips none"
    assert "first run" in advisory[0].remedy.lower(), (
        f"the remedy should send the operator to the step that fixes it: {advisory[0].remedy!r}"
    )


def test_the_advisory_names_no_variable_that_does_nothing() -> None:
    """``NINJASRE_LLM_PROVIDER`` selects nothing, so telling somebody to set it is advice to type an inert line."""
    report = validate(without(ANTHROPIC_API_KEY_ENV))

    for finding in report.findings:
        assert NINJASRE_LLM_PROVIDER_ENV not in str(finding), str(finding)


def test_a_local_model_server_counts_as_a_provider_this_deployment_equips() -> None:
    """Ollama needs no credential, so a credential count alone would nag a working deployment."""
    environ = without(ANTHROPIC_API_KEY_ENV) | {OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1"}

    report = validate(environ)

    assert not [
        finding for finding in report.findings if finding.setting == PROVIDER_CREDENTIAL_SETTING
    ], report.summary()


def test_a_stale_provider_name_in_a_manifest_does_not_refuse_a_boot() -> None:
    """The availability half of the change this file's provider checks are about.

    ``NINJASRE_LLM_PROVIDER`` no longer selects anything: what a role runs on
    lives in the configuration tree, which validation cannot read because it
    runs before the database is open. So a value left in a manifest describes a
    provider this deployment may never call — and refusing to start over one,
    which is what a credential requirement keyed to the name did, takes a
    working deployment down for a line that has no effect.
    """
    report = validate(without(ANTHROPIC_API_KEY_ENV) | {NINJASRE_LLM_PROVIDER_ENV: "openai"})

    assert report.ok, report.summary()


def test_a_provider_name_nothing_supports_is_not_a_reason_to_refuse_a_boot() -> None:
    """It used to be fatal, and it was fatal about a spelling nothing reads."""
    report = validate(with_(**{NINJASRE_LLM_PROVIDER_ENV: "not-a-provider"}))

    assert report.ok, report.summary()


# -- the encryption key is what the provider requirement turned into ----------


def test_a_profile_that_runs_the_proxy_out_of_process_needs_the_encryption_key() -> None:
    """Every credential reaches the proxy through the vault, and the vault needs the key.

    Once the provider credential is stored rather than passed in the
    environment, a deployment without a key cannot complete its own first run:
    it reaches the provider step and fails at the write. Better to say so at
    boot, naming the setting, than at the first thing an operator tries.
    """
    report = validate(without(NINJASRE_DATABASE_ENCRYPTION_KEY_ENV))

    assert not report.ok, report.summary()
    named = [
        finding
        for finding in report.fatal
        if finding.setting == NINJASRE_DATABASE_ENCRYPTION_KEY_ENV
    ]
    assert named, f"got {[finding.setting for finding in report.fatal]}"


def test_the_dev_profile_still_survives_without_an_encryption_key() -> None:
    """dev runs the proxy in-process and may legitimately store nothing at all."""
    environ = {
        NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_DEV,
        NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@localhost:5432/ninjasre",
    }

    report = validate(environ)

    assert report.ok, report.summary()
    assert any(
        finding.setting == NINJASRE_DATABASE_ENCRYPTION_KEY_ENV for finding in report.warnings
    ), "the absence is still worth saying out loud"
