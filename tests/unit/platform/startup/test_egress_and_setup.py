"""SC-005, SC-008, and SC-001: no egress nobody configured, and fifteen minutes.

The egress tests answer the question a security review actually asks — "what can
this thing connect to?" — from the configuration rather than from a claim. The
list is derived, so it cannot grow by something reaching a host nobody declared;
that is the whole property Article X is about.

``unexpected`` is the other half, and it is what the network-monitor test in
``tests/contract/deployment/`` compares an observed connection list against.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    FIRST_INVESTIGATION_BUDGET_SECONDS,
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_EGRESS_ALLOWLIST_ENV,
    NINJASRE_OTEL_ENDPOINT_ENV,
)
from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    ANTHROPIC_BASE_URL_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
    OPENAI_API_KEY_ENV,
)
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from platform.startup.egress import (
    PURPOSE_PROVIDER,
    configured_destinations,
    external_destinations,
    host_of,
    is_on_host,
    permitted_hosts,
    provider_is_local,
    unexpected,
)
from platform.startup.profiles import DeploymentProfile
from platform.startup.setup import (
    admin_token_announcement,
    first_run_plan,
    generate_admin_token,
)

pytestmark = pytest.mark.unit

#: A hosted deployment. The Anthropic credential is what makes Anthropic
#: reachable — nothing in an environment names which provider a role runs on any
#: more, so a credential and an endpoint are the only things left that say
#: anything about where a model call could go.
HOSTED = {
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre:secret@postgres:5432/ninjasre",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}

AIR_GAPPED = {
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre:secret@postgres:5432/ninjasre",
    OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
    NINJASRE_AIR_GAPPED_ENV: "true",
}


# -- classification ------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "::1", "postgres", "ollama", "10.0.3.7", "192.168.1.5"],
)
def test_the_operators_own_infrastructure_is_not_egress(host: str) -> None:
    assert is_on_host(host)


@pytest.mark.parametrize("host", ["api.anthropic.com", "example.com", "8.8.8.8"])
def test_a_public_name_or_address_is_egress(host: str) -> None:
    assert not is_on_host(host)


def test_a_cluster_service_name_is_on_host() -> None:
    assert is_on_host("ninjasre-proxy.ninjasre.svc.cluster.local")


def test_an_unknown_vendor_endpoint_is_never_treated_as_local() -> None:
    """The one case that must not be mistaken for something on the host."""
    assert not is_on_host("")


def test_a_host_is_read_out_of_a_url_or_taken_as_it_stands() -> None:
    assert host_of("postgresql://user:pw@postgres:5432/db") == "postgres"
    assert host_of("https://API.Example.com/v1") == "api.example.com"
    assert host_of("proxy:8422") == "proxy"
    assert host_of("  ") == ""


# -- what a configuration permits ---------------------------------------------


def test_every_destination_names_the_setting_that_configured_it() -> None:
    """A destination nobody can trace to a setting is one nobody can remove."""
    for destination in configured_destinations(HOSTED):
        assert destination.setting
        assert destination.purpose


def test_a_provider_credential_is_what_makes_that_vendor_reachable() -> None:
    """The environment stopped naming a provider, so a credential is the signal left.

    An operator who put an Anthropic key in the manifest has equipped this
    deployment to reach Anthropic, whatever the configuration tree later binds
    any role to. That is a destination derived from a setting somebody can
    remove, which is the whole of what this report promises.
    """
    [destination] = [
        entry for entry in configured_destinations(HOSTED) if PURPOSE_PROVIDER in entry.purpose
    ]

    assert destination.setting == ANTHROPIC_API_KEY_ENV
    assert "anthropic" in destination.purpose


def test_an_environment_that_equips_no_provider_reports_no_provider_destination() -> None:
    """The report stopped inventing one.

    It used to synthesise a destination for whichever provider
    ``NINJASRE_LLM_PROVIDER`` named, falling back to the shipped default when
    nothing named one — so a deployment whose provider credential lives in the
    vault, which is the supported shape, had its egress report name a vendor no
    call would ever reach.
    """
    environ = {NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre"}

    assert configured_destinations(environ) == configured_destinations(
        environ | {NINJASRE_LLM_PROVIDER_ENV: "openai"}
    )
    assert not [
        entry for entry in configured_destinations(environ) if PURPOSE_PROVIDER in entry.purpose
    ]


def test_a_stale_provider_name_changes_nothing_about_what_is_reachable() -> None:
    """The variable is inert, and a report that still read it would say otherwise."""
    assert configured_destinations(HOSTED | {NINJASRE_LLM_PROVIDER_ENV: "ollama"}) == (
        configured_destinations(HOSTED)
    )


def test_every_provider_the_environment_equips_is_reported_not_just_one() -> None:
    """Two credentials are two destinations. Which one a role uses is not an
    environment's answer any more, so an egress report that picked one would be
    guessing at exactly the thing that went wrong."""
    environ = HOSTED | {OPENAI_API_KEY_ENV: "sk-not-a-real-key"}

    providers = [
        entry.purpose
        for entry in configured_destinations(environ)
        if PURPOSE_PROVIDER in entry.purpose
    ]

    assert len(providers) == 2


def test_a_hosted_provider_is_the_one_thing_that_leaves_the_host() -> None:
    external = external_destinations(HOSTED)

    assert len(external) == 1
    assert "anthropic" in external[0].purpose
    assert "vendor's own endpoint" in str(external[0])


def test_an_air_gapped_configuration_implies_no_egress_at_all() -> None:
    """SC-005: a local model is what makes a no-egress deployment fully functional."""
    assert external_destinations(AIR_GAPPED) == ()
    assert provider_is_local(AIR_GAPPED)


def test_a_hosted_provider_pointed_at_an_on_host_gateway_counts_as_local() -> None:
    """Which is how vLLM behind the OpenAI wire is configured."""
    environ = HOSTED | {ANTHROPIC_BASE_URL_ENV: "http://llm-gateway:8000/v1"}

    assert provider_is_local(environ)
    assert external_destinations(environ) == ()


def test_a_telemetry_endpoint_off_the_host_is_reported_as_egress() -> None:
    environ = AIR_GAPPED | {NINJASRE_OTEL_ENDPOINT_ENV: "https://collector.vendor.example/v1"}

    assert [d.setting for d in external_destinations(environ)] == [NINJASRE_OTEL_ENDPOINT_ENV]


def test_an_on_host_collector_is_not() -> None:
    environ = AIR_GAPPED | {NINJASRE_OTEL_ENDPOINT_ENV: "http://otel-collector:4317"}

    assert external_destinations(environ) == ()


def test_the_allow_list_adds_the_hosts_nothing_else_names() -> None:
    environ = HOSTED | {NINJASRE_EGRESS_ALLOWLIST_ENV: "api.pagerduty.com, api.datadoghq.com"}

    assert "api.pagerduty.com" in permitted_hosts(environ)
    assert "api.datadoghq.com" in permitted_hosts(environ)


def test_an_empty_allow_list_permits_nothing_extra() -> None:
    assert permitted_hosts(HOSTED | {NINJASRE_EGRESS_ALLOWLIST_ENV: " , ,"}) == permitted_hosts(
        HOSTED
    )


# -- SC-008: what a monitor should never see -----------------------------------


def test_a_run_that_reached_only_configured_destinations_reports_nothing() -> None:
    observed = ["postgres:5432", "http://proxy:8422/forward", "127.0.0.1:8420"]

    assert unexpected(observed, HOSTED) == ()


def test_a_connection_to_a_host_nobody_configured_is_reported() -> None:
    """SC-008. This is the assertion the network monitor makes."""
    observed = ["postgres:5432", "https://telemetry.vendor.example/collect"]

    assert unexpected(observed, HOSTED) == ("telemetry.vendor.example",)


def test_an_allow_listed_host_is_not_a_surprise() -> None:
    environ = HOSTED | {NINJASRE_EGRESS_ALLOWLIST_ENV: "api.pagerduty.com"}

    assert unexpected(["https://api.pagerduty.com/incidents"], environ) == ()


def test_the_same_surprise_is_reported_once_and_hosts_come_back_sorted() -> None:
    observed = ["https://b.example/one", "https://a.example/two", "https://b.example/three"]

    assert unexpected(observed, HOSTED) == ("a.example", "b.example")


# -- SC-001: the fifteen minutes -----------------------------------------------


@pytest.mark.parametrize("profile", list(DeploymentProfile))
def test_every_profile_fits_the_budget(profile: DeploymentProfile) -> None:
    """SC-001. A step added later has to be given a budget, and this is where that lands."""
    plan = first_run_plan(profile)

    assert plan.within_budget, plan.summary()
    assert plan.budget_seconds == FIRST_INVESTIGATION_BUDGET_SECONDS == 900


def test_the_standard_profile_ends_at_a_finished_investigation() -> None:
    plan = first_run_plan(DeploymentProfile.STANDARD)

    assert plan.steps[-1].name == "investigate"
    assert "answer" in plan.steps[-1].action


def test_most_of_the_path_is_automatic() -> None:
    """The operator's own time is the scarce part; the rest is a machine waiting."""
    plan = first_run_plan(DeploymentProfile.STANDARD)

    assert plan.manual_seconds < plan.total_seconds / 2


def test_every_step_has_a_budget_and_says_what_it_is() -> None:
    for profile in DeploymentProfile:
        for step in first_run_plan(profile).steps:
            assert step.budget_seconds > 0, f"{profile}/{step.name}"
            assert step.action.strip(), f"{profile}/{step.name}"


def test_the_plan_reports_its_headroom_rather_than_only_a_verdict() -> None:
    plan = first_run_plan(DeploymentProfile.STANDARD)

    assert plan.headroom_seconds == plan.budget_seconds - plan.total_seconds
    assert "headroom" in plan.summary()


def test_the_configure_step_names_how_to_produce_an_encryption_key() -> None:
    """FR-019: NinjaSRE never makes one, so the path has to say how the operator does."""
    configure = next(
        step
        for step in first_run_plan(DeploymentProfile.STANDARD).steps
        if step.name == "configure"
    )

    assert "openssl rand" in configure.action


# -- the admin token (T020) ----------------------------------------------------


def test_a_generated_admin_token_is_long_and_never_the_same_twice() -> None:
    first, second = generate_admin_token(), generate_admin_token()

    assert first != second
    assert len(first) >= 40


def test_the_first_start_announcement_shows_the_token_once_and_says_so() -> None:
    announcement = admin_token_announcement("a-token", profile=DeploymentProfile.STANDARD)

    assert "a-token" in announcement
    assert "only time this token is shown" in announcement
    assert "NINJASRE_ADMIN_TOKEN" in announcement


def test_the_announcement_states_the_profile_it_started() -> None:
    """So an operator who meant to start `standard` and started `dev` finds out now."""
    announcement = admin_token_announcement("a-token", profile=DeploymentProfile.DEV)

    assert "deployment profile dev" in announcement
    assert "credential proxy in_process" in announcement
