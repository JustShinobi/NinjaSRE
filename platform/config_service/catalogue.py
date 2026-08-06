"""What the console renders, and what validation checks a reference against.

Two ports and one view. The ports exist because this is tier 3 and the
capability catalogue is tier 2: ``platform/`` cannot import ``capabilities/`` or
``integrations/``, so the composition root supplies readers over both and this
package works against protocols. That is the same shape the topology discovery
adapters take, and for the same reason.

**The view is where the value is.** A capability missing from a team's list
looks identical whether it was never written, is disabled for that team, or
needs an integration nobody has connected — and only two of those are something
an operator can fix in a minute. So ``CatalogueView`` reports every capability
with its availability and, when it is unavailable, the reason. The console can
then show "Datadog tools: 14 available, 6 unavailable (no Datadog integration)"
instead of showing nothing.

**Integration schemas are data, not a form.** ``IntegrationSchema`` says which
fields a vendor's credential has and which are secret; the console renders from
that rather than hard-coding a vendor's field names, which is what keeps eighty
integrations addable one package at a time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from platform.config_service.schema.root import RootConfig


@dataclass(frozen=True, slots=True)
class CapabilityDescription:
    """One capability, as the configuration service needs to see it."""

    name: str
    kind: str = "tool"
    summary: str = ""
    tags: tuple[str, ...] = ()
    required_integrations: tuple[str, ...] = ()
    side_effect_level: str = "read"


@dataclass(frozen=True, slots=True)
class CredentialField:
    """One field of a vendor's credential, and whether it is secret.

    ``secret`` is what the console reads to decide between a password input and
    a text input, and what the write path reads to refuse the value outright —
    a secret field's value belongs in the vault, never in configuration.
    """

    name: str
    label: str = ""
    secret: bool = True
    required: bool = True
    help: str = ""


@dataclass(frozen=True, slots=True)
class IntegrationSchema:
    """What a vendor needs, in enough detail to render a form for it."""

    name: str
    display_name: str = ""
    credential_fields: tuple[CredentialField, ...] = ()
    settings_fields: tuple[CredentialField, ...] = ()
    hosts: tuple[str, ...] = ()


@runtime_checkable
class CapabilityCatalogueReader(Protocol):
    """Every capability this deployment has installed."""

    def names(self) -> tuple[str, ...]:
        """Return every installed capability's name, in name order."""

    def describe(self, name: str) -> CapabilityDescription | None:
        """Return what ``name`` is, or ``None`` if nothing answers to it."""


@runtime_checkable
class IntegrationDirectory(Protocol):
    """Every integration this deployment has installed."""

    def names(self) -> tuple[str, ...]:
        """Return every installed integration's name, in name order."""

    def schema(self, name: str) -> IntegrationSchema | None:
        """Return ``name``'s credential and settings schema, or ``None``."""


@dataclass(frozen=True, slots=True)
class StaticCatalogue:
    """A catalogue over a fixed set of descriptions.

    What a composition root builds from the live registry, and what a test uses
    when the point of the test is the configuration rather than discovery.
    """

    descriptions: Mapping[str, CapabilityDescription] = field(default_factory=dict)

    @classmethod
    def of(cls, descriptions: Sequence[CapabilityDescription]) -> StaticCatalogue:
        """Return a catalogue over ``descriptions``, keyed by name."""
        return cls(descriptions={each.name: each for each in descriptions})

    def names(self) -> tuple[str, ...]:
        """Return every installed capability's name, in name order."""
        return tuple(sorted(self.descriptions))

    def describe(self, name: str) -> CapabilityDescription | None:
        """Return what ``name`` is, or ``None`` if nothing answers to it."""
        return self.descriptions.get(name)


@dataclass(frozen=True, slots=True)
class StaticIntegrationDirectory:
    """A directory over a fixed set of integration schemas."""

    schemas: Mapping[str, IntegrationSchema] = field(default_factory=dict)

    @classmethod
    def of(cls, schemas: Sequence[IntegrationSchema]) -> StaticIntegrationDirectory:
        """Return a directory over ``schemas``, keyed by name."""
        return cls(schemas={each.name: each for each in schemas})

    def names(self) -> tuple[str, ...]:
        """Return every installed integration's name, in name order."""
        return tuple(sorted(self.schemas))

    def schema(self, name: str) -> IntegrationSchema | None:
        """Return ``name``'s credential and settings schema, or ``None``."""
        return self.schemas.get(name)


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """One capability, and whether this team can run it."""

    capability: CapabilityDescription
    available: bool
    reason: str | None = None

    @property
    def name(self) -> str:
        """Return the capability's name."""
        return self.capability.name


@dataclass(frozen=True, slots=True)
class CatalogueView:
    """What one team's configuration makes of the installed catalogue (FR-017)."""

    entries: tuple[CatalogueEntry, ...] = ()

    @classmethod
    def of(cls, catalogue: CapabilityCatalogueReader, config: RootConfig) -> CatalogueView:
        """Return every installed capability with its availability for ``config``.

        Three reasons a capability can be unavailable, checked in the order an
        operator would act on them: the team switched it off, the team switched
        its whole tag off, or the integration it needs is not connected.
        """
        connected = set(config.integrations.enabled_names())
        entries: list[CatalogueEntry] = []
        for name in catalogue.names():
            description = catalogue.describe(name)
            if description is None:
                continue
            reason = config.capabilities.refusal_for(name, description.tags)
            if reason is None:
                missing = tuple(
                    required
                    for required in description.required_integrations
                    if required not in connected
                )
                if missing:
                    reason = f"needs the {', '.join(missing)} integration"
            entries.append(
                CatalogueEntry(capability=description, available=reason is None, reason=reason)
            )
        return cls(entries=tuple(entries))

    def available(self) -> tuple[CatalogueEntry, ...]:
        """Return the entries this team can run."""
        return tuple(entry for entry in self.entries if entry.available)

    def unavailable(self) -> tuple[CatalogueEntry, ...]:
        """Return the entries this team cannot run, each carrying its reason."""
        return tuple(entry for entry in self.entries if not entry.available)

    def reason_for(self, name: str) -> str | None:
        """Return why ``name`` is unavailable, or ``None`` if it is available."""
        for entry in self.entries:
            if entry.name == name:
                return entry.reason
        return None

    def blocked_by_integration(self) -> Mapping[str, tuple[str, ...]]:
        """Return which capabilities each unconnected integration would unlock.

        The console's "connect Datadog to enable 14 capabilities" line, and the
        one piece of the picture an operator cannot assemble from a list of
        what they do have.
        """
        blocked: dict[str, list[str]] = {}
        for entry in self.unavailable():
            if entry.reason is None or not entry.reason.startswith("needs the "):
                continue
            for integration in entry.capability.required_integrations:
                blocked.setdefault(integration, []).append(entry.name)
        return {name: tuple(names) for name, names in sorted(blocked.items())}


def integration_forms(
    directory: IntegrationDirectory, config: RootConfig
) -> tuple[IntegrationSchema, ...]:
    """Return the schema of every installed integration, configured or not (FR-018).

    Configured ones first, in the order the team declared them, so the console
    renders what exists before what could. Both are returned because "connect
    another" is the second thing an operator does on that screen.
    """
    configured = [
        schema
        for name in config.integrations.referenced_names()
        if (schema := directory.schema(name)) is not None
    ]
    seen = {schema.name for schema in configured}
    return tuple(
        configured
        + [
            schema
            for name in directory.names()
            if name not in seen and (schema := directory.schema(name)) is not None
        ]
    )


__all__ = [
    "CapabilityCatalogueReader",
    "CapabilityDescription",
    "CatalogueEntry",
    "CatalogueView",
    "CredentialField",
    "IntegrationDirectory",
    "IntegrationSchema",
    "StaticCatalogue",
    "StaticIntegrationDirectory",
    "integration_forms",
]
