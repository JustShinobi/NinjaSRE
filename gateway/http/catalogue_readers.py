"""Live discovery, adapted to the two ports the configuration service reads.

``platform/`` is tier 3 and may not import ``capabilities/`` or
``integrations/``, so it declares ``CapabilityCatalogueReader`` and
``IntegrationDirectory`` and waits for somebody above to fill them in. This is
that somebody: tier 1, where both halves are legal to see at once.

Both adapters walk discovery once per reader rather than holding a
process-wide snapshot. A reader is built per request (``routes/config.py``
and ``routes/proposals.py`` call ``installed_catalogue()`` inside the
handler), so a capability added while the process runs is seen by the next
request — the property that makes "adding a capability edits no existing
file" true at runtime as well as at import time.

Once per *reader*, not once per *call*, because ``CatalogueView.of`` asks for
every name and then describes each one: a hundred-odd calls for one view. A
walk per call — sixteen thousand modules through ``pkgutil`` and every skill
manifest parsed from disk, each time — answered ``GET
/v1/config/{node}/catalogue`` in two seconds on a staging deployment, and
being synchronous held the gateway's one event loop for the whole of it, so
every other request from every other viewer waited behind it. The walk is
lazy: a reader that is built and never asked costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from capabilities.registry.discovery import discover as discover_capabilities
from integrations.registry import discover as discover_integrations
from platform.config_service.catalogue import (
    CapabilityDescription,
    CredentialField,
    IntegrationSchema,
)
from platform.credentials.schemas import CredentialField as CredentialSchemaField

#: Tools that reach a vendor live under that vendor's package. The package name
#: is therefore what the tool needs connected, and reading it from the module
#: path means a new vendor declares its requirement by existing rather than by
#: being added to a table here.
_INTEGRATION_PACKAGE_ROOT = "integrations."


def _required_integration(source_module: str) -> tuple[str, ...]:
    """Return the integration a tool declared in ``source_module`` needs, if any."""
    if not source_module.startswith(_INTEGRATION_PACKAGE_ROOT):
        return ()
    vendor = source_module[len(_INTEGRATION_PACKAGE_ROOT) :].partition(".")[0]
    return (vendor,) if vendor else ()


@dataclass(slots=True)
class InstalledCatalogue:
    """Every capability discovery finds, as the configuration service reads them."""

    #: The one walk this reader makes, taken on the first question and kept
    #: for the rest of the reader's life — which is one request.
    _snapshot: dict[str, CapabilityDescription] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def _descriptions(self) -> dict[str, CapabilityDescription]:
        """Return every discovered tool and skill, keyed by name, walking once."""
        if self._snapshot is None:
            self._snapshot = _discovered_descriptions()
        return self._snapshot

    def names(self) -> tuple[str, ...]:
        """Return every installed capability's name, in name order."""
        return tuple(sorted(self._descriptions()))

    def describe(self, name: str) -> CapabilityDescription | None:
        """Return what ``name`` is, or ``None`` if nothing answers to it."""
        return self._descriptions().get(name)


def _discovered_descriptions() -> dict[str, CapabilityDescription]:
    """Return every discovered tool and skill, keyed by name. One discovery walk."""
    catalogue = discover_capabilities()
    found: dict[str, CapabilityDescription] = {
        tool.name: CapabilityDescription(
            name=tool.name,
            kind="tool",
            summary=tool.metadata.description,
            tags=tuple(tool.metadata.tags),
            required_integrations=_required_integration(tool.source_module),
            side_effect_level=str(tool.metadata.side_effect_level),
        )
        for tool in catalogue.tools
    }
    found.update(
        {
            skill.name: CapabilityDescription(
                name=skill.name,
                kind="skill",
                summary=skill.metadata.description,
                tags=tuple(skill.metadata.tags),
            )
            for skill in catalogue.skills
        }
    )
    return found


@dataclass(slots=True)
class InstalledIntegrations:
    """Every installed integration's credential shape, as a form needs it.

    The translation is one-way on purpose. A vendor's schema says a field is
    ``FieldKind.SECRET``; this reports ``secret=True``, which is what decides
    between a password input and a text input. Nothing here can read a stored
    value, because the vault exposes no path that would.
    """

    #: The one walk this directory makes, kept for its life — one request.
    _snapshot: dict[str, IntegrationSchema] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def _schemas(self) -> dict[str, IntegrationSchema]:
        """Return every installed integration's form schema, keyed by name, walking once."""
        if self._snapshot is None:
            self._snapshot = _discovered_schemas()
        return self._snapshot

    def names(self) -> tuple[str, ...]:
        """Return every installed integration's name, in name order."""
        return tuple(sorted(self._schemas()))

    def schema(self, name: str) -> IntegrationSchema | None:
        """Return ``name``'s credential and settings schema, or ``None``."""
        return self._schemas().get(name)


def _discovered_schemas() -> dict[str, IntegrationSchema]:
    """Return every installed integration's form schema, keyed by name. One walk."""
    return {
        name: IntegrationSchema(
            name=name,
            display_name=name,
            # What the form asks for: the secrets, and the address, which
            # is not a secret and is asked for on the same screen because
            # neither works without the other. The write route splits them
            # again by kind — the secret to the vault, the address to the
            # configuration tree — so one form stays one request.
            #
            # ``settings_fields`` is the rest, and nothing renders it
            # today. Putting the address there would have reproduced, one
            # screen over, the failure the address field exists to fix: a
            # form an operator completes without connecting anything.
            credential_fields=tuple(
                _credential_field(each)
                for each in descriptor.schema.fields
                if each.is_secret or each.is_endpoint
            ),
            settings_fields=tuple(
                _credential_field(each)
                for each in descriptor.schema.fields
                if not (each.is_secret or each.is_endpoint)
            ),
            hosts=tuple(descriptor.rule.hosts),
        )
        for name, descriptor in discover_integrations().items()
    }


def _credential_field(declared: CredentialSchemaField) -> CredentialField:
    """Return the vendor's field as the form-facing shape.

    ``label`` reads ``display_label``, which is the vendor's own declared label
    when there is one and a derived reading of the field's name otherwise — so
    this stops inventing a label the moment a vendor package declares its own.
    """
    return CredentialField(
        name=declared.name,
        label=declared.display_label,
        secret=declared.is_secret,
        required=declared.required,
        help=declared.description,
        min_scope=declared.min_scope,
        guide_url=declared.guide_url,
    )


def installed_catalogue() -> InstalledCatalogue:
    """Return a reader over every capability this deployment has installed."""
    return InstalledCatalogue()


def installed_integrations() -> InstalledIntegrations:
    """Return a directory over every integration this deployment has installed."""
    return InstalledIntegrations()


__all__ = [
    "InstalledCatalogue",
    "InstalledIntegrations",
    "installed_catalogue",
    "installed_integrations",
]
