"""Which team's handle an integration resolves to — one path, three callers.

Before this module existed, "which handle does this integration use" had two
different answers depending on who asked. A verification route asked as the
caller's own team (``auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM``,
repeated at every call site that needed it) and could show a credential
green. A tool binding or a provider's boot-time lease — composed once per
process, with no HTTP caller in sight — asked for the literal
organisation-wide handle, unconditionally, whether or not that was where the
credential actually lived. A credential written under a team's own handle
was verified and invisible in the same deployment, at the same time, because
the two questions were never the same question.

They are now. A caller that has a team of its own — a verification, a
credential write, a delete — states it as ``preferred_team`` and gets it
back, unconditionally and without touching the vault: this is what
"verification resolves as the caller's team" means in code, and it has to
keep meaning exactly what it already meant. A caller with no team of its own
— a composition root, wiring a process before any request has arrived — asks
with ``preferred_team`` unset, and the answer comes from the vault's own
metadata: the team that actually holds a credential for the integration, or
the organisation when nobody does, or the organisation with the ambiguity
named when more than one team does. Two teams holding the same integration is
a real, expected shape, not an error — the process does not choose one in
silence, and the deployment shows it.

Nothing here reads a credential value. ``Vault.list`` is the metadata-only
listing FR-003 exists for; the value stays behind the proxy, exactly as it
does everywhere else in this package.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


def _read_only_vault(gateway: PersistenceGateway) -> Vault:
    """Return a vault built for listing metadata alone.

    An empty schema registry is safe here: only ``store``/``rotate`` ever
    consult it, and nothing in this module calls either. Reading no value and
    validating no schema is the same boundary FR-050 draws, enforced by what
    this module is capable of rather than by a rule someone has to remember.
    """
    return Vault(gateway=gateway, schemas=CredentialSchemaRegistry.from_schemas())


async def credential_team_holders(
    gateway: PersistenceGateway, scope: TenantScope
) -> Mapping[str, tuple[str, ...]]:
    """Return, per integration, the teams that separately hold a credential for it.

    The organisation-wide holder is never in the result — this answers
    "which teams", and the organisation is not a team. One listing for the
    whole organisation rather than one per integration, so a caller that
    needs the whole picture (the catalogue screen, the process-wide binding)
    does not pay for it once per row.
    """
    held = await _read_only_vault(gateway).list(scope)
    by_integration: dict[str, set[str]] = {}
    for version in held:
        if version.handle.is_organisation_wide:
            continue
        by_integration.setdefault(version.integration, set()).add(version.handle.team_id)
    return {integration: tuple(sorted(teams)) for integration, teams in by_integration.items()}


@dataclass(frozen=True, slots=True)
class ResolvedHandle:
    """Which team one integration's credential resolves to, and whether it was a guess.

    ``integration`` is empty for the one caller that resolves a whole
    process's tool binding rather than a single integration's handle
    (``resolve_process_credential_team`` below).
    """

    integration: str
    team_id: str
    #: The teams that separately hold a credential, when there is more than
    #: one — empty in every other case. Non-empty is what turns an ambiguous
    #: resolution into something reportable instead of merely silent.
    ambiguous_teams: tuple[str, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        """Return whether more than one team held a credential and none was named."""
        return bool(self.ambiguous_teams)


def _from_holders(integration: str, holders: tuple[str, ...]) -> ResolvedHandle:
    if len(holders) == 1:
        return ResolvedHandle(integration=integration, team_id=holders[0])
    if len(holders) > 1:
        logger.warning(
            "credentials.handle_ambiguous",
            integration=integration or "(the process binding)",
            teams=list(holders),
        )
        return ResolvedHandle(
            integration=integration,
            team_id=CREDENTIAL_ORG_WIDE_TEAM,
            ambiguous_teams=holders,
        )
    return ResolvedHandle(integration=integration, team_id=CREDENTIAL_ORG_WIDE_TEAM)


async def resolve_credential_handle(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    integration: str,
    preferred_team: str | None = None,
) -> ResolvedHandle:
    """Return which team's handle ``integration`` resolves to.

    ``preferred_team`` is how a caller that already knows its own team —
    every HTTP route with an authenticated request — states it. Given, the
    answer is that team, or the organisation when it is empty, exactly as
    ``auth.team_node_id or CREDENTIAL_ORG_WIDE_TEAM`` already computed at
    every call site this replaces. No read happens in this branch: a
    verification is a question about one team, not a search.

    Omitted, the answer is discovered: the team that holds a credential for
    ``integration``, read from the vault's metadata. Nobody holding one, or
    more than one team holding one, both resolve to the organisation-wide
    handle — the second is also reported as ambiguous, logged by integration
    and by team, never by value.
    """
    if preferred_team is not None:
        return ResolvedHandle(
            integration=integration, team_id=preferred_team or CREDENTIAL_ORG_WIDE_TEAM
        )

    held = await _read_only_vault(gateway).list(scope, integration=integration)
    holders = tuple(
        sorted(
            {version.handle.team_id for version in held if not version.handle.is_organisation_wide}
        )
    )
    return _from_holders(integration, holders)


async def resolve_process_credential_team(
    gateway: PersistenceGateway, scope: TenantScope
) -> ResolvedHandle:
    """Return the one team a process-wide tool binding resolves as.

    A tool binding carries a single team for the whole process
    (``integrations._base.access.IntegrationAccess.team_id``), not one per
    integration — restructuring that would touch every vendor tool module and
    the transport layer beneath it, which is a larger change than one
    binding's resolution. This is the reconciliation: a single team that
    holds a credential for anything in the organisation is the team the
    process binds to, because the credential proxy's own team-then-
    organisation fallback (``platform.credentials.proxy.resolution.
    CredentialResolver.resolve``) still reaches the organisation-wide handle
    for any integration that team does not hold — nothing is lost for those.
    Nobody holding anything, or more than one distinct team holding
    something, anywhere in the organisation, both fall back to the
    organisation-wide handle — the second is also reported as ambiguous.
    """
    by_integration = await credential_team_holders(gateway, scope)
    holders = tuple(sorted({team for teams in by_integration.values() for team in teams}))
    return _from_holders("", holders)


__all__ = [
    "ResolvedHandle",
    "credential_team_holders",
    "resolve_credential_handle",
    "resolve_process_credential_team",
]
