"""Credential resolution and client caching.

Two properties matter here. A credential is reached through the port and never
read at a call site, so the vault replacing the environment is one new class.
And a cache key names every input to the client it identifies — a key that omits
one hands a caller somebody else's client, and the symptom appears somewhere
unrelated.
"""

from __future__ import annotations

import pytest

from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    OLLAMA_BASE_URL_ENV,
    PROVIDER_ANTHROPIC,
    PROVIDER_OLLAMA,
    SUPPORTED_PROVIDERS,
    TRANSPORT_LITELLM,
    TRANSPORT_SDK,
    VLLM_BASE_URL_ENV,
)
from core.llm.credentials import (
    EnvironmentCredentialResolver,
    MissingCredentialError,
    ProviderCredentials,
    StaticCredentialResolver,
    environment_variables_for,
)
from core.llm.internal.client_cache import ClientCache
from core.llm.internal.client_cache_key import ClientCacheKey

pytestmark = pytest.mark.unit


# --- Credentials --------------------------------------------------------------


def test_the_environment_resolver_reads_the_names_the_constants_declare() -> None:
    resolver = EnvironmentCredentialResolver({ANTHROPIC_API_KEY_ENV: "value-from-the-environment"})

    assert resolver.resolve(PROVIDER_ANTHROPIC).require("api_key") == "value-from-the-environment"


def test_a_missing_credential_names_itself_and_nothing_else() -> None:
    resolver = EnvironmentCredentialResolver({})

    with pytest.raises(MissingCredentialError) as caught:
        resolver.resolve(PROVIDER_ANTHROPIC).require("api_key")

    assert "api_key" in str(caught.value)
    assert PROVIDER_ANTHROPIC in str(caught.value)


def test_an_empty_value_counts_as_absent() -> None:
    """An exported-but-blank variable is a misconfiguration, not a credential."""
    resolver = EnvironmentCredentialResolver({ANTHROPIC_API_KEY_ENV: ""})

    assert resolver.resolve(PROVIDER_ANTHROPIC).has("api_key") is False


def test_either_local_endpoint_variable_serves_the_local_provider() -> None:
    """Ollama and vLLM speak the same wire, so whichever is set is the one to use."""
    from_ollama = EnvironmentCredentialResolver({OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1"})
    from_vllm = EnvironmentCredentialResolver({VLLM_BASE_URL_ENV: "http://vllm:8000/v1"})

    assert from_ollama.resolve(PROVIDER_OLLAMA).get("base_url") == "http://ollama:11434/v1"
    assert from_vllm.resolve(PROVIDER_OLLAMA).get("base_url") == "http://vllm:8000/v1"


def test_the_first_variable_listed_wins_when_both_are_set() -> None:
    resolver = EnvironmentCredentialResolver(
        {OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1", VLLM_BASE_URL_ENV: "http://vllm:8000/v1"}
    )

    assert resolver.resolve(PROVIDER_OLLAMA).get("base_url") == "http://ollama:11434/v1"


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_every_provider_documents_the_variables_an_operator_sets(provider_id: str) -> None:
    """Except the local one, which needs no credential at all."""
    variables = environment_variables_for(provider_id)
    assert variables, f"{provider_id} documents no configuration"


def test_a_static_resolver_serves_what_it_was_given() -> None:
    resolver = StaticCredentialResolver({PROVIDER_ANTHROPIC: {"api_key": "held-by-the-caller"}})

    assert resolver.resolve(PROVIDER_ANTHROPIC).require("api_key") == "held-by-the-caller"


def test_an_unconfigured_provider_resolves_to_nothing_rather_than_raising() -> None:
    """The failure belongs at ``require``, where it can name what is missing."""
    resolver = StaticCredentialResolver({})

    assert resolver.resolve("nobody-configured-this").names == ()


def test_credential_names_are_reportable_without_the_values() -> None:
    credentials = ProviderCredentials(PROVIDER_ANTHROPIC, {"api_key": "s3cret", "base_url": "u"})

    assert credentials.names == ("api_key", "base_url")


# --- Client cache -------------------------------------------------------------


def _key(**overrides: str) -> ClientCacheKey:
    fields = {
        "role": "investigator",
        "provider_id": PROVIDER_ANTHROPIC,
        "model_id": "claude-sonnet-5",
        "transport": TRANSPORT_SDK,
    }
    fields.update(overrides)
    return ClientCacheKey(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "difference",
    [
        {"role": "reporter"},
        {"provider_id": "openai"},
        {"model_id": "claude-opus-5"},
        {"transport": TRANSPORT_LITELLM},
        {"base_url": "http://vllm.internal:8000/v1"},
        {"deployment_id": "prod-eu-west-1"},
    ],
)
def test_every_input_that_changes_behaviour_changes_the_key(difference: dict[str, str]) -> None:
    """A key missing one of these hands a caller somebody else's client."""
    assert _key() != _key(**difference)


def test_two_identical_configurations_share_one_client() -> None:
    cache = ClientCache()
    built = []

    def factory() -> object:
        built.append(object())
        return built[-1]

    first = cache.get_or_create(_key(), factory)  # type: ignore[arg-type]
    second = cache.get_or_create(_key(), factory)  # type: ignore[arg-type]

    assert first is second
    assert len(built) == 1


def test_a_different_configuration_gets_its_own_client() -> None:
    cache = ClientCache()

    first = cache.get_or_create(_key(), object)  # type: ignore[arg-type]
    second = cache.get_or_create(_key(role="reporter"), object)  # type: ignore[arg-type]

    assert first is not second
    assert len(cache) == 2


def test_invalidating_one_key_rebuilds_only_that_client() -> None:
    """For a credential rotation, which must not disturb every other role."""
    cache = ClientCache()
    first = cache.get_or_create(_key(), object)  # type: ignore[arg-type]
    other = cache.get_or_create(_key(role="reporter"), object)  # type: ignore[arg-type]

    cache.invalidate(_key())
    rebuilt = cache.get_or_create(_key(), object)  # type: ignore[arg-type]

    assert rebuilt is not first
    assert cache.get_or_create(_key(role="reporter"), object) is other  # type: ignore[arg-type]


def test_swapping_the_transport_keeps_everything_else() -> None:
    key = _key()
    swapped = key.replace_transport(TRANSPORT_LITELLM)

    assert swapped.transport == TRANSPORT_LITELLM
    assert swapped.role == key.role
    assert swapped.model_id == key.model_id
