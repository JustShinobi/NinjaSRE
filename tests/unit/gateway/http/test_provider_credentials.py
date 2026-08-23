"""The investigator's model key comes from the vault the console wrote it to.

`core.llm`'s factory defaults to `EnvironmentCredentialResolver`, and no
composition root had ever replaced it. So an operator pasted a provider key into
the first-run screen, watched it verify against the real endpoint — the verify
route resolves through the vault — and then had every investigation call the
same provider with whatever the container was started with, which in a
vault-configured deployment is nothing at all.

`platform/credentials/proxy/llm.py::provider_lease` was written for exactly this
and says so: "the composition root calls this and hands the result down". Only
the per-request verify route ever called it.

The environment keeps its place *under* the vault rather than losing it. Naming
a key in a manifest is a supported shape, and a deployment already running one
must not stop working because the vault holds nothing for that provider.
"""

from __future__ import annotations

import pytest

from core.llm.credentials import ProviderCredentials, StaticCredentialResolver
from gateway.http.provider_credentials import VaultFirstCredentials

pytestmark = pytest.mark.unit


class _Environment:
    """Stands in for the environment-backed resolver, with one provider in it."""

    def __init__(self, provider_id: str, values: dict[str, str]) -> None:
        self._provider_id = provider_id
        self._values = values

    def resolve(self, provider_id: str) -> ProviderCredentials:
        if provider_id != self._provider_id:
            return ProviderCredentials(provider_id, {})
        return ProviderCredentials(provider_id, self._values)


def test_the_vault_answers_where_it_holds_something() -> None:
    resolver = VaultFirstCredentials(
        vault=StaticCredentialResolver({"google_gemini": {"api_key": "from-the-vault"}}),
        environment=_Environment("google_gemini", {"api_key": "from-the-manifest"}),
    )

    resolved = resolver.resolve("google_gemini")

    assert resolved.names == ("api_key",)
    assert resolved.require("api_key") == "from-the-vault"


def test_the_environment_answers_where_the_vault_holds_nothing() -> None:
    """The supported shape this must not break: a key named in a manifest."""
    resolver = VaultFirstCredentials(
        vault=StaticCredentialResolver({}),
        environment=_Environment("anthropic", {"api_key": "from-the-manifest"}),
    )

    resolved = resolver.resolve("anthropic")

    assert resolved.require("api_key") == "from-the-manifest"


def test_a_provider_neither_source_holds_resolves_to_nothing() -> None:
    """Not to an error: a deployment that has configured one provider and not
    another is the ordinary state, and the preflight reports it."""
    resolver = VaultFirstCredentials(
        vault=StaticCredentialResolver({}),
        environment=_Environment("anthropic", {"api_key": "x"}),
    )

    assert resolver.resolve("openai").names == ()
