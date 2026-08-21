"""Which integrations a team has, and where their credentials are — not what they are.

The field that is *not* here is the point. There is no ``api_key``, no
``token``, no ``password``, and there never will be: an integration entry
carries a ``credential`` naming a vault entry, and the proxy resolves it at the
network edge. Article IV is satisfied by the absence of a field rather than by a
check that could be relaxed — and because the schema is closed, writing
``api_key`` is refused rather than ignored. Validation then refuses a
secret-shaped value anywhere in the document as a second line.

Everything else an integration needs — the region, the site, the base URL of a
self-hosted instance — is ordinary, non-secret configuration, and it belongs
here because a team's Datadog site is a team's decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import model_validator

from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    field_help,
    section_help,
)


class IntegrationSettings(ConfigSection):
    """One integration a team has configured, and where its secret lives."""

    model_config = section_help(
        "One vendor this team is connected to. No secret is entered here — the token "
        "lives in the vault and this entry names it."
    )

    #: Required: an entry that does not say which vendor it configures is not
    #: an entry, and a default would let the omission validate silently.
    name: Annotated[
        ConfiguredStr,
        field_help(
            "Which vendor this entry configures. Required, and must be one of the "
            "integrations this deployment has installed."
        ),
    ]
    credential: Annotated[
        ConfiguredStr,
        field_help("Which stored credential this integration authenticates with."),
    ] = ""
    region: Annotated[
        ConfiguredStr | None,
        field_help("The vendor region to talk to, for vendors that have more than one."),
    ] = None
    site: Annotated[
        ConfiguredStr | None,
        field_help("The vendor site to talk to, for vendors that name one."),
    ] = None
    base_url: Annotated[
        ConfiguredStr | None,
        field_help("The address of your own instance, for a vendor you host yourself."),
    ] = None
    enabled: Annotated[
        bool, field_help("Off keeps the entry and stops anything reaching the vendor.")
    ] = True
    #: The vendor's own non-secret options. Open because the vendor defines
    #: them; scanned for secret shapes like everything else.
    settings: Annotated[
        Mapping[str, Any],
        field_help(
            "Anything else this vendor needs, as it names it. Never a secret: a "
            "secret-shaped value here is refused."
        ),
    ] = {}


class IntegrationsConfig(ConfigSection):
    """Every integration a team has configured."""

    model_config = section_help(
        "The vendors this team is connected to. Each entry names a vendor and the stored "
        "credential it uses; no secret is ever typed into configuration."
    )

    active: Annotated[
        tuple[IntegrationSettings, ...],
        field_help("One entry per vendor. A vendor may appear only once."),
    ] = ()

    @model_validator(mode="after")
    def _names_are_distinct(self) -> IntegrationsConfig:
        """Refuse the same vendor configured twice."""
        seen: set[str] = set()
        for integration in self.active:
            if integration.name in seen:
                raise ValueError(f"configures {integration.name!r} more than once")
            seen.add(integration.name)
        return self

    def for_name(self, name: str) -> IntegrationSettings | None:
        """Return the entry for ``name``, or ``None``."""
        for integration in self.active:
            if integration.name == name:
                return integration
        return None

    def enabled_names(self) -> tuple[str, ...]:
        """Return the integrations a run may actually reach, in declared order."""
        return tuple(entry.name for entry in self.active if entry.enabled)

    def referenced_names(self) -> tuple[str, ...]:
        """Return every integration this configuration names, deduplicated."""
        return tuple(dict.fromkeys(entry.name for entry in self.active if entry.name))

    def credential_references(self) -> tuple[str, ...]:
        """Return the vault entries this configuration points at."""
        return tuple(dict.fromkeys(entry.credential for entry in self.active if entry.credential))


INTEGRATIONS_FIELDS: tuple[str, ...] = tuple(IntegrationsConfig.model_fields)
INTEGRATION_FIELDS: tuple[str, ...] = tuple(IntegrationSettings.model_fields)


__all__ = [
    "INTEGRATIONS_FIELDS",
    "INTEGRATION_FIELDS",
    "IntegrationSettings",
    "IntegrationsConfig",
]
