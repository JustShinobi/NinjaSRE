"""The model provider's credential, taken from the vault instead of the environment.

Every other authenticated call in NinjaSRE reaches a vendor through the proxy,
which injects the secret at the network edge. The model provider is the one
exception, and it is a deliberate one: ADR 0008 makes the vendor's own SDK the
normative transport, and an SDK constructs its client with a key rather than
letting somebody else add a header later. So ``core.llm`` holds the provider's
key in process, and the honest thing is to say where the boundary actually is
rather than to pretend it is somewhere else.

What this module changes is *where the key comes from*. It used to come from
the environment, which meant it lived in a deployment manifest, a Helm value, or
a ``.env`` file — copied, committed, and rotated by editing infrastructure.
Now it comes from the vault, which is where an operator puts it at first run,
and rotating it is a write to the vault rather than a redeploy.

**Why this file is in ``proxy/``.** Reading a stored credential means calling
``CredentialStore.reveal``, and ``tools/check_direct_credentials.py`` fails the
build on a ``reveal`` call outside this package. That rule is not a formality to
route around — the exemption belongs to the trust boundary rather than to a file
name, so code that reads a credential belongs on this side of it. Nothing here
is imported by ``core.llm``; the composition root calls this and hands the
result down.

**Why it returns a lease rather than a resolver.**
``core.llm.credentials.CredentialResolver`` is synchronous and vault resolution
is not, so the vault cannot implement that port directly. It does not have to:
the port's second implementation, ``StaticCredentialResolver``, exists — in its
own words — "for a caller that already holds a vault lease". This is the code
that holds one. The lease is resolved once, for the tenant and team a request
belongs to, and is as current as the moment it was taken.
"""

from __future__ import annotations

from collections.abc import Sequence

from config.constants.llm import SUPPORTED_PROVIDERS
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from core.llm.credentials import StaticCredentialResolver
from platform.credentials.errors import CredentialNotConfigured
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.resolution import CredentialResolver
from platform.persistence.ports import TenantScope


async def provider_lease(
    resolver: CredentialResolver,
    scope: TenantScope,
    *,
    team_id: str = CREDENTIAL_ORG_WIDE_TEAM,
    providers: Sequence[str] = SUPPORTED_PROVIDERS,
) -> StaticCredentialResolver:
    """Return what the vault holds for each model provider, as a resolver ``core.llm`` accepts.

    One resolution per provider, each independent. A provider nobody has
    configured resolves to nothing rather than raising, because a deployment
    that has not been set up yet is the state every deployment starts in — the
    setup checklist reports it, the console renders a screen for it, and an
    exception here would make that absence indistinguishable from a vault that
    cannot be read.

    ``team_id`` defaults to the organisation-wide owner, which is who a caller
    with no team of its own resolves as. The vault's one step of fallback still
    applies underneath: a team with its own key uses it, a team without one uses
    the organisation's.

    Args:
        resolver: the proxy's own resolver — the only thing that reads a value.
        scope: the tenant this lease is taken for.
        team_id: which team's credentials to prefer.
        providers: which providers to resolve; every supported one by default.

    Returns:
        A resolver over the values that were live at the moment it was taken.
    """
    leased: dict[str, dict[str, str]] = {}

    for provider_id in providers:
        handle = CredentialHandle(integration=provider_id, team_id=team_id)
        try:
            resolved = await resolver.resolve(scope, handle)
        except CredentialNotConfigured:
            continue
        leased[provider_id] = dict(resolved.values)

    return StaticCredentialResolver(leased)


__all__ = ["provider_lease"]
