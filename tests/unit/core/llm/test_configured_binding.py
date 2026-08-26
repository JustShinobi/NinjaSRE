"""Which provider a role runs on is configuration, and only configuration.

``binding_for`` once read the environment and nothing else, which made the
choice of model provider something an operator changed by editing a manifest
and restarting. Configuration was put above it, and the environment was left
underneath as a fallback for any role configuration did not name. That
remainder is what this module removes, and it is worth saying plainly why,
because it looked harmless.

A deployment bound its investigator to Gemini through the console and left the
other seven roles alone, which is the ordinary thing to do — the console offers
one provider box and says the rest follow it. Underneath, every unnamed role
fell past configuration into ``NINJASRE_LLM_PROVIDER``, which a manifest had
set to ``ollama`` long before, pointing at a host that no longer answered. So
episode extraction called a provider nobody had chosen and nobody could see,
and fifty investigations in a row lost their episode to a connection refused.
Nothing was misconfigured: the operator chose one provider, and the deployment
ran on two.

**So an unnamed role follows the investigator.** That is the promise the
console already makes in words, and it is the only fallback that cannot
surprise somebody: the provider they picked is the provider their deployment
uses. The shipped default answers only when nothing at all is configured, which
is a deployment nobody has set up yet.

The environment keeps the things it is genuinely for — an endpoint and a
credential — and loses the one it should never have decided: what this
deployment runs on. That answer is in the configuration tree, where the console
can show it, an audit can read it, and changing it does not need a restart.

``binding_for`` is synchronous and reading configuration is not, so the
composition root resolves the tree once and publishes the result here rather
than this module learning to await.
"""

from __future__ import annotations

import pytest

from config.constants.config_service import MODEL_ROLE_EXTRACTION, MODEL_ROLE_INVESTIGATOR
from config.constants.llm import (
    DEFAULT_PROVIDER,
    NINJASRE_LLM_MODEL_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
)
from core.llm.factory import (
    publish_configured_bindings,
    reset_configured_bindings,
    resolve_binding,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _forget_published_configuration():
    """Leave no published binding behind: this is process-wide state."""
    reset_configured_bindings()
    yield
    reset_configured_bindings()


def test_configuration_beats_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator's configured choice is the deployment's answer."""
    monkeypatch.setenv(NINJASRE_LLM_PROVIDER_ENV, PROVIDER_OPENAI)
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding(MODEL_ROLE_INVESTIGATOR)

    assert binding.provider_id == PROVIDER_OLLAMA
    assert binding.model_id == "qwen2.5:7b"


def test_a_role_nobody_bound_follows_the_investigator_not_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole defect, as one assertion.

    An operator who binds the investigator has chosen a provider for this
    deployment. A role they never opened must not quietly run on a different
    one because a manifest named it before they arrived.
    """
    monkeypatch.setenv(NINJASRE_LLM_PROVIDER_ENV, PROVIDER_OPENAI)
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding(MODEL_ROLE_EXTRACTION)

    assert binding.provider_id == PROVIDER_OLLAMA
    assert binding.model_id == "qwen2.5:7b"


def test_a_role_bound_to_its_own_provider_keeps_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Following the investigator is a fallback, never an override."""
    monkeypatch.delenv(NINJASRE_LLM_PROVIDER_ENV, raising=False)
    publish_configured_bindings(
        {
            MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "qwen2.5:7b"),
            MODEL_ROLE_EXTRACTION: (PROVIDER_OPENAI, "gpt-4o-mini"),
        }
    )

    binding = resolve_binding(MODEL_ROLE_EXTRACTION)

    assert binding.provider_id == PROVIDER_OPENAI
    assert binding.model_id == "gpt-4o-mini"


def test_the_environment_no_longer_chooses_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manifest may describe a deployment; it may not decide what it runs on."""
    monkeypatch.setenv(NINJASRE_LLM_PROVIDER_ENV, PROVIDER_OLLAMA)
    monkeypatch.setenv(NINJASRE_LLM_MODEL_ENV, "qwen2.5:7b")

    binding = resolve_binding(MODEL_ROLE_INVESTIGATOR)

    assert binding.provider_id == DEFAULT_PROVIDER
    assert binding.model_id != "qwen2.5:7b"


def test_an_explicit_argument_still_wins_over_configuration() -> None:
    """A caller that named a provider asked a question configuration cannot answer."""
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding(MODEL_ROLE_INVESTIGATOR, provider_id=PROVIDER_OPENAI)

    assert binding.provider_id == PROVIDER_OPENAI


def test_nothing_configured_anywhere_still_resolves_to_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An investigation that cannot start is worse than one that starts and says so."""
    monkeypatch.delenv(NINJASRE_LLM_PROVIDER_ENV, raising=False)
    monkeypatch.delenv(NINJASRE_LLM_MODEL_ENV, raising=False)

    binding = resolve_binding(MODEL_ROLE_INVESTIGATOR)

    assert binding.provider_id == DEFAULT_PROVIDER


def test_a_configured_provider_with_no_model_takes_that_providers_default() -> None:
    """Choosing a provider at first run must not require also choosing a model."""
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "")})

    binding = resolve_binding(MODEL_ROLE_INVESTIGATOR)

    assert binding.provider_id == PROVIDER_OLLAMA
    assert binding.model_id != ""
