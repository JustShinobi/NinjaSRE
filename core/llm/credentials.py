"""The port a provider credential arrives through, and never anything else.

No adapter reads an environment variable. Every secret comes through a
:class:`CredentialResolver`, which the credential vault implements once it
exists; until then the environment-backed reference below stands in. The
indirection is the point: swapping the vault in later must not touch a single
adapter, and no call site should ever be a place a secret can be read from.

:class:`ProviderCredentials` will not print its values. ``repr`` reaches logs,
tracebacks, and pytest failure output, and a secret only has to escape once.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from config.constants.llm import (
    ANTHROPIC_API_KEY_ENV,
    ANTHROPIC_BASE_URL_ENV,
    AWS_ACCESS_KEY_ID_ENV,
    AWS_BEDROCK_ENDPOINT_ENV,
    AWS_PROFILE_ENV,
    AWS_REGION_ENV,
    AWS_SECRET_ACCESS_KEY_ENV,
    AWS_SESSION_TOKEN_ENV,
    AZURE_OPENAI_API_KEY_ENV,
    AZURE_OPENAI_API_VERSION_ENV,
    AZURE_OPENAI_DEPLOYMENT_ENV,
    AZURE_OPENAI_ENDPOINT_ENV,
    GOOGLE_API_KEY_ENV,
    GOOGLE_APPLICATION_CREDENTIALS_ENV,
    GOOGLE_CLOUD_LOCATION_ENV,
    GOOGLE_CLOUD_PROJECT_ENV,
    NVIDIA_API_KEY_ENV,
    NVIDIA_NIM_BASE_URL_ENV,
    OLLAMA_BASE_URL_ENV,
    OPENAI_API_KEY_ENV,
    OPENAI_BASE_URL_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL_ENV,
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    VLLM_BASE_URL_ENV,
)


class MissingCredentialError(LookupError):
    """A provider was configured without something it needs.

    Carries the credential's *name*, never a value, and never a hint about what
    a correct value looks like.
    """


class ProviderCredentials:
    """The resolved credentials for one provider.

    Not a dataclass, because a dataclass would generate a ``repr`` that prints
    every value it holds.
    """

    __slots__ = ("_values", "provider_id")

    def __init__(self, provider_id: str, values: Mapping[str, str]) -> None:
        self.provider_id = provider_id
        self._values = {name: value for name, value in values.items() if value}

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return one credential, or ``default`` when it was not supplied."""
        return self._values.get(name, default)

    def require(self, name: str) -> str:
        """Return one credential.

        Raises:
            MissingCredentialError: it was not supplied.
        """
        value = self._values.get(name)
        if not value:
            raise MissingCredentialError(
                f"provider {self.provider_id!r} is missing the {name!r} credential"
            )
        return value

    def has(self, name: str) -> bool:
        """Return whether ``name`` was supplied."""
        return bool(self._values.get(name))

    @property
    def names(self) -> tuple[str, ...]:
        """Return the credential names present, for a diagnostic that leaks nothing."""
        return tuple(sorted(self._values))

    def __repr__(self) -> str:
        """Return a representation naming the keys and none of the values."""
        return f"ProviderCredentials(provider_id={self.provider_id!r}, names={self.names!r})"

    __str__ = __repr__


@runtime_checkable
class CredentialResolver(Protocol):
    """Where a provider credential comes from."""

    def resolve(self, provider_id: str) -> ProviderCredentials:
        """Return the credentials configured for ``provider_id``."""


#: Which environment variable supplies which credential, per provider. This
#: table is the *only* place the two are associated, so the vault replacing the
#: environment is one new resolver and no other change.
_ENVIRONMENT_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    PROVIDER_ANTHROPIC: {
        "api_key": (ANTHROPIC_API_KEY_ENV,),
        "base_url": (ANTHROPIC_BASE_URL_ENV,),
    },
    PROVIDER_OPENAI: {
        "api_key": (OPENAI_API_KEY_ENV,),
        "base_url": (OPENAI_BASE_URL_ENV,),
    },
    PROVIDER_AZURE_OPENAI: {
        "api_key": (AZURE_OPENAI_API_KEY_ENV,),
        "endpoint": (AZURE_OPENAI_ENDPOINT_ENV,),
        "api_version": (AZURE_OPENAI_API_VERSION_ENV,),
        "deployment": (AZURE_OPENAI_DEPLOYMENT_ENV,),
    },
    PROVIDER_AWS_BEDROCK: {
        "region": (AWS_REGION_ENV,),
        "endpoint": (AWS_BEDROCK_ENDPOINT_ENV,),
        "access_key_id": (AWS_ACCESS_KEY_ID_ENV,),
        "secret_access_key": (AWS_SECRET_ACCESS_KEY_ENV,),
        "session_token": (AWS_SESSION_TOKEN_ENV,),
        "profile": (AWS_PROFILE_ENV,),
    },
    PROVIDER_GOOGLE_GEMINI: {
        "api_key": (GOOGLE_API_KEY_ENV,),
    },
    PROVIDER_GOOGLE_VERTEX_AI: {
        "project": (GOOGLE_CLOUD_PROJECT_ENV,),
        "location": (GOOGLE_CLOUD_LOCATION_ENV,),
        "service_account_file": (GOOGLE_APPLICATION_CREDENTIALS_ENV,),
    },
    PROVIDER_OPENROUTER: {
        "api_key": (OPENROUTER_API_KEY_ENV,),
        "base_url": (OPENROUTER_BASE_URL_ENV,),
    },
    PROVIDER_NVIDIA_NIM: {
        "api_key": (NVIDIA_API_KEY_ENV,),
        "base_url": (NVIDIA_NIM_BASE_URL_ENV,),
    },
    PROVIDER_OLLAMA: {
        # Either endpoint serves the same wire, so whichever the operator set
        # is the one to use.
        "base_url": (OLLAMA_BASE_URL_ENV, VLLM_BASE_URL_ENV),
    },
}


class EnvironmentCredentialResolver:
    """Reads credentials from the process environment.

    A stand-in until the credential vault lands. It exists so that no adapter
    ever grew the habit of reading the environment itself — replacing this class
    is a one-line change at the composition root, and nothing downstream
    notices.
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def resolve(self, provider_id: str) -> ProviderCredentials:
        """Return whatever the environment supplies for ``provider_id``."""
        sources = _ENVIRONMENT_SOURCES.get(provider_id, {})
        values: dict[str, str] = {}
        for name, candidates in sources.items():
            for variable in candidates:
                found = self._environ.get(variable)
                if found:
                    values[name] = found
                    break
        return ProviderCredentials(provider_id, values)


class StaticCredentialResolver:
    """Serves credentials handed to it directly.

    For tests, for preflight against a named deployment, and for a caller that
    already holds a vault lease.
    """

    def __init__(self, credentials: Mapping[str, Mapping[str, str]]) -> None:
        self._credentials = credentials

    def resolve(self, provider_id: str) -> ProviderCredentials:
        """Return the credentials registered for ``provider_id``."""
        return ProviderCredentials(provider_id, self._credentials.get(provider_id, {}))


def credential_names_for(provider_id: str) -> tuple[str, ...]:
    """Return the credential names a provider can be configured with."""
    return tuple(sorted(_ENVIRONMENT_SOURCES.get(provider_id, {})))


def environment_variables_for(provider_id: str) -> tuple[str, ...]:
    """Return the environment variables an operator sets for ``provider_id``.

    For the operator-facing documentation and for ``preflight``'s report; never
    for reading a value.
    """
    sources = _ENVIRONMENT_SOURCES.get(provider_id, {})
    return tuple(sorted({variable for group in sources.values() for variable in group}))


__all__ = [
    "CredentialResolver",
    "EnvironmentCredentialResolver",
    "MissingCredentialError",
    "ProviderCredentials",
    "StaticCredentialResolver",
    "credential_names_for",
    "environment_variables_for",
]
