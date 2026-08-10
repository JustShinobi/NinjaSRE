"""Which integrations this team can actually use, asked once and shared.

Two routes need the same answer for different reasons — a resource page needs to
know which source answers each question about it, and the catalogue needs to know
which entries are already connected — and two routes computing it separately is
how one screen says a log store is configured while the next says it is not.

"Configured" here means a live credential exists in the vault, which is the same
line ``platform/credentials/health.py`` draws. It deliberately does not mean the
credential *works*: proving that costs a live vendor call, and a resource page
that made ninety of them to render a row would be unusable. A signal map built
from this points at the source that should answer; the deep verify beside it is
what says whether it will.
"""

from __future__ import annotations

from gateway.http.deps import AuthenticatedRequest
from gateway.http.state import GatewayState
from integrations._catalogue.discovery import catalogue
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault


async def configured_integrations(
    state: GatewayState, auth: AuthenticatedRequest
) -> tuple[str, ...]:
    """Return every integration this caller's tenant holds a credential for.

    Reads metadata only. The vault's listing carries no field a secret could sit
    in — that is the type's guarantee rather than this function's discretion —
    which is what lets the answer travel into a response body.
    """
    schemas = CredentialSchemaRegistry.from_schemas(
        *(entry.descriptor.schema for entry in catalogue())
    )
    vault = Vault(gateway=state.gateway, schemas=schemas)
    stored = await vault.list(auth.scope)
    return tuple(sorted({version.integration for version in stored}))


__all__ = ["configured_integrations"]
