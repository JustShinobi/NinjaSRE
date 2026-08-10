"""Which schema a credential write is checked against, whoever it belongs to.

Two kinds of thing take a credential on this surface and there is one route for
both. An installed integration declares its schema in its own package; a model
provider declares its fields in its onboarding descriptor. Both end up in a
``CredentialSchemaRegistry`` the vault validates against, so
``PUT /v1/integrations/{name}/credential`` is the whole of how a secret enters a
deployment over the network.

One path rather than two, deliberately. A second write for provider keys would
be a second place credentials live, and the second place is the one the audit
misses — the CLI's guided first run already stores a provider key by calling the
integration path with the provider's identifier, and this is what makes that
work over HTTP as well as in process.
"""

from __future__ import annotations

from core.llm.onboarding import UnknownProviderError, credential_schema_for, provider_names
from gateway.http.errors import ApiProblem, not_found
from integrations.registry import discover
from platform.credentials.schemas import CredentialSchema


def schema_for(name: str) -> CredentialSchema:
    """Return the credential schema ``name`` declares, integration or provider.

    Raises:
        ApiProblem: nothing installed and no supported provider answers to that
            name (404). The refusal names what does exist, so the next request
            is the right one.
    """
    descriptor = discover().get(name)
    if descriptor is not None:
        return descriptor.schema
    try:
        return credential_schema_for(name)
    except UnknownProviderError as unknown:
        raise _unknown(name) from unknown


def _unknown(name: str) -> ApiProblem:
    """Return the 404 for a name that is neither an integration nor a provider."""
    return not_found(
        f"no installed integration and no supported provider named {name!r}. "
        f"The providers this build supports are: {', '.join(provider_names())}"
    )


__all__ = ["schema_for"]
