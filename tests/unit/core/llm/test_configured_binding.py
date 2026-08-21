"""Which provider a role runs on is configuration, not a deployment setting.

``binding_for`` used to read the environment and nothing else, which made the
choice of model provider something an operator changed by editing a manifest
and restarting. The configuration service already holds the answer —
``models.for_role(role)`` returns the provider and model bound to a role — and
this is the seam that lets it win.

The precedence is explicit argument, then configuration, then the environment,
then the shipped default. The environment keeps its place deliberately: a
deployment that names its provider in a manifest is a supported shape, and it
must not break when configuration is simply absent.

``binding_for`` is synchronous and reading configuration is not, so the
composition root resolves the tree once and publishes the result here rather
than this module learning to await.
"""

from __future__ import annotations

import pytest

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
    publish_configured_bindings({"investigator": (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding("investigator")

    assert binding.provider_id == PROVIDER_OLLAMA
    assert binding.model_id == "qwen2.5:7b"


def test_the_environment_still_answers_for_a_role_configuration_does_not_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration binding one role must not silently rebind every other."""
    monkeypatch.setenv(NINJASRE_LLM_PROVIDER_ENV, PROVIDER_OPENAI)
    publish_configured_bindings({"investigator": (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding("summariser")

    assert binding.provider_id == PROVIDER_OPENAI


def test_an_explicit_argument_still_wins_over_configuration() -> None:
    """A caller that named a provider asked a question configuration cannot answer."""
    publish_configured_bindings({"investigator": (PROVIDER_OLLAMA, "qwen2.5:7b")})

    binding = resolve_binding("investigator", provider_id=PROVIDER_OPENAI)

    assert binding.provider_id == PROVIDER_OPENAI


def test_nothing_configured_anywhere_still_resolves_to_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An investigation that cannot start is worse than one that starts and says so."""
    monkeypatch.delenv(NINJASRE_LLM_PROVIDER_ENV, raising=False)
    monkeypatch.delenv(NINJASRE_LLM_MODEL_ENV, raising=False)

    binding = resolve_binding("investigator")

    assert binding.provider_id == DEFAULT_PROVIDER


def test_a_configured_provider_with_no_model_takes_that_providers_default() -> None:
    """Choosing a provider at first run must not require also choosing a model."""
    publish_configured_bindings({"investigator": (PROVIDER_OLLAMA, "")})

    binding = resolve_binding("investigator")

    assert binding.provider_id == PROVIDER_OLLAMA
    assert binding.model_id != ""
