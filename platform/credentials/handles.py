"""The non-secret reference a client sends instead of a secret.

A handle names a credential the way a foreign key names a row: it is safe in a
prompt, a tool argument, a log line, and a trace, because knowing it gets you
nothing without the vault. That is the whole trick of Article IV — the agent
holds the name and the proxy holds the thing.

The grammar is deliberately small.

``datadog/payments``
    The Datadog credential belonging to the ``payments`` team.
``datadog/-``
    The Datadog credential belonging to the organisation, used by every team
    that has not been given one of its own.
``datadog/payments@v3``
    Version three of that credential, as stored. Callers do not write this
    form; the vault does, and rotation writes ``@v4`` beside it rather than over
    it.

The organisation-wide team is a literal ``-`` rather than an empty string
because ``datadog/`` and ``datadog`` would otherwise be two spellings of one
handle, and the first bug that produces is a lookup that misses by a character
nobody can see.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.security import (
    CREDENTIAL_HANDLE_SEPARATOR,
    CREDENTIAL_ORG_WIDE_TEAM,
    CREDENTIAL_VERSION_SEPARATOR,
)
from platform.credentials.errors import MalformedHandle


@dataclass(frozen=True, slots=True)
class CredentialHandle:
    """Which integration, for which team, within one organisation.

    The organisation is not part of the handle. It comes from the tenant scope
    the unit of work was opened for, which is what makes a cross-tenant
    resolution impossible to phrase rather than merely refused — the same
    reasoning the repository ports use for ``org_id``.
    """

    integration: str
    team_id: str = CREDENTIAL_ORG_WIDE_TEAM

    def __post_init__(self) -> None:
        for label, part in (("integration", self.integration), ("team", self.team_id)):
            if not part:
                raise MalformedHandle(f"A credential handle needs a {label}.")
            if CREDENTIAL_HANDLE_SEPARATOR in part or CREDENTIAL_VERSION_SEPARATOR in part:
                raise MalformedHandle(
                    f"A handle's {label} may not contain "
                    f"{CREDENTIAL_HANDLE_SEPARATOR!r} or {CREDENTIAL_VERSION_SEPARATOR!r}; "
                    f"got {part!r}."
                )

    @classmethod
    def for_organisation(cls, integration: str) -> CredentialHandle:
        """Return the handle every team in the organisation falls back to."""
        return cls(integration=integration, team_id=CREDENTIAL_ORG_WIDE_TEAM)

    @classmethod
    def parse(cls, text: str) -> CredentialHandle:
        """Return the handle ``text`` spells, or raise ``MalformedHandle``.

        Accepts the versioned form and discards the version: a caller parsing a
        handle wants to know which credential, and which *version* is the
        vault's business.
        """
        base = text.split(CREDENTIAL_VERSION_SEPARATOR, 1)[0]
        integration, separator, team = base.partition(CREDENTIAL_HANDLE_SEPARATOR)
        if not separator:
            raise MalformedHandle(
                f"A credential handle is <integration>{CREDENTIAL_HANDLE_SEPARATOR}<team>; "
                f"got {text!r}."
            )
        return cls(integration=integration, team_id=team)

    @property
    def qualified(self) -> str:
        """Return the handle as it is written and stored."""
        return f"{self.integration}{CREDENTIAL_HANDLE_SEPARATOR}{self.team_id}"

    @property
    def is_organisation_wide(self) -> bool:
        """Return whether this handle belongs to the organisation rather than a team."""
        return self.team_id == CREDENTIAL_ORG_WIDE_TEAM

    def version_handle(self, version: int) -> str:
        """Return the storage handle for one version of this credential."""
        if version < 1:
            raise MalformedHandle(f"Credential versions start at 1; got {version}.")
        return f"{self.qualified}{CREDENTIAL_VERSION_SEPARATOR}{version}"

    def fallback(self) -> CredentialHandle | None:
        """Return the organisation-wide handle to try next, or ``None``.

        A team's own credential wins; a team with none uses the organisation's.
        Exactly one step, because a deeper chain would make "which credential
        did this call use" a question with a computed answer, and FR-019 wants
        it to be a recorded one.
        """
        if self.is_organisation_wide:
            return None
        return CredentialHandle.for_organisation(self.integration)


def version_of(stored_handle: str) -> int | None:
    """Return the version a storage handle names, or ``None`` when it names none."""
    _, separator, suffix = stored_handle.rpartition(CREDENTIAL_VERSION_SEPARATOR)
    if not separator or not suffix.isdigit():
        return None
    return int(suffix)


__all__ = [
    "CredentialHandle",
    "version_of",
]
