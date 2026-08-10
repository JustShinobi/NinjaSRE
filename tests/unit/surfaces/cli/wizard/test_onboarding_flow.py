"""The guided first run: nothing configured to something that verifies.

Two things are asserted that are easy to lose and expensive to discover late.

**All nine providers are offered, and none of them is special.** A listing that
buried the local option under a heading would make provider neutrality true in
the adapter layer and false where somebody actually decides. What each provider
*declares* is asserted where the declarations live, in
``tests/unit/core/llm/test_provider_onboarding.py``.

**The flow ends in a verification, not a claim.** "That should do it" and "a
request went out and came back" are different statements, and the difference is
discovered at 03:00 by somebody who was told the first one.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.llm import SUPPORTED_PROVIDERS
from surfaces.cli.client import LocalClient, PlatformClient
from surfaces.cli.errors import ConfigurationError
from surfaces.cli.wizard.flow import OnboardingFlow, onboard
from surfaces.cli.wizard.integrations import collect, setup, setup_many
from surfaces.cli.wizard.prompts import PromptAbandoned, ScriptedPrompter
from tests.support.deployment import CREDENTIAL_FIELDS, FakeServices

pytestmark = pytest.mark.unit


def test_the_local_provider_is_offered_alongside_the_rest() -> None:
    # Not under a heading, not last. A listing that buried it would make
    # provider neutrality true in the adapter layer and false where somebody
    # actually decides.
    services = FakeServices()
    prompter = ScriptedPrompter(answers=["ollama", "http://127.0.0.1:11434/v1", "llama4:70b", ""])

    outcome = asyncio.run(onboard(LocalClient(services=services), prompter))

    offered = "\n".join(prompter.said)
    for provider in SUPPORTED_PROVIDERS:
        assert provider in offered, f"{provider} was not offered"
    assert outcome.provider_id == "ollama"


def test_an_unknown_provider_is_refused_with_the_ones_that_exist() -> None:
    """In this surface's error vocabulary, not the descriptor package's.

    The descriptors moved below the surfaces and raise a lookup failure of their
    own. What an operator has to get back is a ``ConfigurationError``, because
    that is what carries the exit code their script branches on.
    """
    flow = OnboardingFlow(
        client=LocalClient(services=FakeServices()),
        prompter=ScriptedPrompter(answers=[]),
        provider_id="anthropik",
    )

    with pytest.raises(ConfigurationError, match="anthropik") as refused:
        asyncio.run(flow.choose_provider())

    assert "anthropic" in (refused.value.remedy or "")


def test_the_flow_stores_the_credential_and_verifies_the_provider() -> None:
    services = FakeServices()
    prompter = ScriptedPrompter(answers=["a-key", "claude-sonnet-5", ""])

    outcome = asyncio.run(
        onboard(LocalClient(services=services), prompter, provider_id="anthropic")
    )

    assert services.vault["anthropic"] == {"ANTHROPIC_API_KEY": "a-key"}
    assert outcome.verified
    assert outcome.model_id == "claude-sonnet-5"


def test_a_flow_that_could_not_verify_reports_it_rather_than_claiming_success() -> None:
    services = FakeServices()
    # No credential entered: the required field is left empty, so nothing is
    # stored and the provider cannot verify.
    prompter = ScriptedPrompter(answers=["", "claude-sonnet-5", ""])

    outcome = asyncio.run(
        onboard(LocalClient(services=services), prompter, provider_id="anthropic")
    )

    assert not outcome.verified
    assert "anthropic" not in services.vault


def test_the_transcript_says_what_happened_at_each_step() -> None:
    services = FakeServices()
    prompter = ScriptedPrompter(answers=["a-key", "claude-sonnet-5", "kubernetes", "a-kubeconfig"])

    outcome = asyncio.run(
        onboard(LocalClient(services=services), prompter, provider_id="anthropic")
    )

    joined = "\n".join(outcome.steps)
    assert "provider: anthropic" in joined
    assert "credential stored in the vault" in joined
    assert "model: claude-sonnet-5" in joined
    assert "integration kubernetes: verified" in joined
    assert "verified" in joined


def test_integrations_can_be_chosen_ahead_of_the_flow() -> None:
    services = FakeServices()
    prompter = ScriptedPrompter(answers=["a-key", "claude-sonnet-5", "a-kubeconfig"])

    outcome = asyncio.run(
        onboard(
            LocalClient(services=services),
            prompter,
            provider_id="anthropic",
            integrations=("kubernetes",),
        )
    )

    assert [status.integration for status in outcome.integrations] == ["kubernetes"]
    assert services.vault["kubernetes"] == {"kubeconfig": "a-kubeconfig"}


def test_choosing_no_integrations_still_finishes(client: PlatformClient) -> None:
    # A deployment with a provider and no integrations still investigates, from
    # what it is told. Forcing a choice here is how somebody abandons the flow.
    prompter = ScriptedPrompter(answers=["a-key", "claude-sonnet-5", ""])

    outcome = asyncio.run(onboard(client, prompter, provider_id="anthropic"))

    assert outcome.integrations == ()
    assert outcome.verified


# -- integration setup --------------------------------------------------------


def test_prompts_are_generated_from_the_integrations_own_schema(
    client: PlatformClient,
) -> None:
    # Not from a list in the wizard. That is what makes adding a vendor a
    # package rather than an edit here.
    prompter = ScriptedPrompter(answers=["a-key", "an-app-key", "datadoghq.eu"])

    asyncio.run(setup(client, "datadog", prompter))

    assert prompter.asked[: len(CREDENTIAL_FIELDS["datadog"])] == [
        spec.prompt for spec in CREDENTIAL_FIELDS["datadog"]
    ]


def test_only_the_secret_fields_are_read_without_echo(client: PlatformClient) -> None:
    prompter = ScriptedPrompter(answers=["a-key", "an-app-key", "datadoghq.eu"])

    asyncio.run(setup(client, "datadog", prompter))

    assert prompter.secrets_asked == ["API key", "Application key"]


def test_an_optional_field_left_empty_is_absent_rather_than_empty(
    services: FakeServices, client: PlatformClient
) -> None:
    # A schema that distinguishes "not set" from "set to nothing" has to keep
    # being able to.
    prompter = ScriptedPrompter(answers=["a-key", "an-app-key", ""])

    outcome = asyncio.run(setup(client, "datadog", prompter))

    assert "site" not in services.vault["datadog"]
    assert outcome.skipped == ("site",)


def test_a_required_field_left_empty_is_refused(client: PlatformClient) -> None:
    with pytest.raises(ConfigurationError, match="API key is required"):
        asyncio.run(setup(client, "datadog", ScriptedPrompter(answers=["", "x", ""])))


def test_an_integration_that_declares_nothing_is_refused(client: PlatformClient) -> None:
    with pytest.raises(ConfigurationError, match="declares no credential fields"):
        asyncio.run(setup(client, "nonesuch", ScriptedPrompter()))


def test_setting_several_up_continues_past_one_that_fails(
    services: FakeServices, client: PlatformClient
) -> None:
    # An operator who mistyped a Datadog key should still finish configuring
    # Kubernetes rather than starting the whole flow again.
    prompter = ScriptedPrompter(answers=["", "a-kubeconfig"])

    outcomes = asyncio.run(setup_many(client, ("datadog", "kubernetes"), prompter))

    assert [outcome.status.integration for outcome in outcomes] == ["datadog", "kubernetes"]
    assert not outcomes[0].usable
    assert outcomes[1].usable
    assert services.vault == {"kubernetes": {"kubeconfig": "a-kubeconfig"}}


def test_collect_returns_only_what_was_entered() -> None:
    values = collect(
        CREDENTIAL_FIELDS["datadog"],
        ScriptedPrompter(answers=["a-key", "an-app-key", ""]),
    )

    assert values == {"api_key": "a-key", "app_key": "an-app-key"}


def test_a_script_that_runs_out_stops_rather_than_inventing_an_answer() -> None:
    with pytest.raises(PromptAbandoned):
        collect(CREDENTIAL_FIELDS["datadog"], ScriptedPrompter(answers=["only-one"]))


def test_the_operator_is_told_where_to_get_the_credential() -> None:
    services = FakeServices()
    prompter = ScriptedPrompter(answers=["a-key", "claude-sonnet-5", ""])

    asyncio.run(onboard(LocalClient(services=services), prompter, provider_id="anthropic"))

    said = "\n".join(prompter.said)
    assert "console.anthropic.com" in said


def test_the_flow_can_be_driven_step_by_step(client: PlatformClient) -> None:
    # Held as a value so a caller that already knows some answers — an
    # unattended install, the REPL's first-run path — can drive it directly.
    flow = OnboardingFlow(
        client=client,
        prompter=ScriptedPrompter(answers=["claude-sonnet-5"]),
        provider_id="anthropic",
    )

    chosen = asyncio.run(flow.choose_provider())
    model = asyncio.run(flow.choose_model(chosen))

    assert chosen.provider_id == "anthropic"
    assert model == "claude-sonnet-5"
