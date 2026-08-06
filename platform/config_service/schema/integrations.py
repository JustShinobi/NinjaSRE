"""Which integrations a team has, and where their credentials are — not what they are.

The field that is *not* here is the point. There is no ``api_key``, no
``token``, no ``password``, and there never will be: an integration entry
carries a ``credential`` naming a vault entry, and the proxy resolves it at the
network edge. Article IV is satisfied by the absence of a field rather than by a
check that could be relaxed, and validation refuses a secret-shaped value
anywhere in the document as a second line.

Everything else an integration needs — the region, the site, the base URL of a
self-hosted instance — is ordinary, non-secret configuration, and it belongs
here because a team's Datadog site is a team's decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from platform.config_service.schema.reader import Reader

#: What one integration entry may declare. ``settings`` is the vendor's own
#: non-secret options; everything above it is shape this package understands.
INTEGRATION_FIELDS: tuple[str, ...] = (
    "name",
    "credential",
    "region",
    "site",
    "base_url",
    "enabled",
    "settings",
)

INTEGRATIONS_FIELDS: tuple[str, ...] = ("active",)


@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    """One integration a team has configured, and where its secret lives."""

    name: str
    credential: str = ""
    region: str | None = None
    site: str | None = None
    base_url: str | None = None
    enabled: bool = True
    settings: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, reader: Reader) -> IntegrationSettings:
        """Return the integration ``reader`` describes."""
        reader.close(INTEGRATION_FIELDS)
        name = reader.string("name")
        if not name:
            reader.fail("name", "an integration entry needs the vendor's name")
        return cls(
            name=name,
            credential=reader.string("credential"),
            region=reader.optional_string("region"),
            site=reader.optional_string("site"),
            base_url=reader.optional_string("base_url"),
            enabled=reader.boolean("enabled", True),
            settings=reader.free_mapping("settings"),
        )


@dataclass(frozen=True, slots=True)
class IntegrationsConfig:
    """Every integration a team has configured."""

    active: tuple[IntegrationSettings, ...] = ()

    @classmethod
    def of(cls, reader: Reader) -> IntegrationsConfig:
        """Return the integration configuration ``reader`` describes."""
        reader.close(INTEGRATIONS_FIELDS)
        active = tuple(IntegrationSettings.of(each) for each in reader.sections("active"))
        _report_duplicate_names(reader, active)
        return cls(active=active)

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


def _report_duplicate_names(reader: Reader, integrations: tuple[IntegrationSettings, ...]) -> None:
    """Record an error per repeated integration name."""
    seen: set[str] = set()
    for integration in integrations:
        if integration.name and integration.name in seen:
            reader.fail("active", f"configures {integration.name!r} more than once")
        seen.add(integration.name)


__all__ = [
    "INTEGRATIONS_FIELDS",
    "INTEGRATION_FIELDS",
    "IntegrationSettings",
    "IntegrationsConfig",
]
