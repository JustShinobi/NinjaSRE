"""Which capabilities a team may run, and what it passes them.

Two shapes, because operators reason in both directions. ``disabled`` names
individual capabilities; ``disabled_tags`` switches off a whole domain — every
remediation capability, every capability of a vendor being retired — without
anybody having to keep a list current as the catalogue grows.

``enabled`` is the allow-list form and is ``None`` rather than empty by default,
because those mean opposite things: unset is "everything the catalogue offers",
and an empty list is "nothing". A team that meant the first and stored the
second would resolve to a catalogue with no capabilities in it, and the
investigation would end with the zero-integration outcome for a reason nobody
could see.

Deny beats allow. A capability both allowed and disabled is disabled, because
the disable is the more recent, more specific, and more consequential of the
two statements.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from platform.config_service.schema.types import ConfigSection, ConfiguredStrList


class CapabilitiesConfig(ConfigSection):
    """The capability allow-list, deny-list, and per-capability parameters."""

    enabled: ConfiguredStrList | None = None
    disabled: ConfiguredStrList = ()
    disabled_tags: ConfiguredStrList = ()
    #: The one open door in the schema, and deliberately narrow: a capability's
    #: parameters are defined by that capability, not here. Everything else is a
    #: declared field.
    parameters: Mapping[str, Mapping[str, Any]] = {}

    def allows(self, name: str, tags: tuple[str, ...] = ()) -> bool:
        """Return whether a capability called ``name`` carrying ``tags`` may run."""
        if name in self.disabled:
            return False
        if any(tag in self.disabled_tags for tag in tags):
            return False
        return self.enabled is None or name in self.enabled

    def refusal_for(self, name: str, tags: tuple[str, ...] = ()) -> str | None:
        """Return why ``name`` is unavailable, or ``None`` if it is available.

        A capability missing from a team's catalogue looks identical whether it
        was never written or is simply switched off, and only one of those is
        something an operator can fix in a minute.
        """
        if name in self.disabled:
            return "disabled for this team"
        for tag in tags:
            if tag in self.disabled_tags:
                return f"the {tag!r} tag is disabled for this team"
        if self.enabled is not None and name not in self.enabled:
            return "not on this team's enabled list"
        return None

    def parameters_for(self, name: str) -> Mapping[str, Any]:
        """Return the parameter overrides for ``name``, empty if there are none."""
        return self.parameters.get(name, {})

    def referenced_names(self) -> tuple[str, ...]:
        """Return every capability this configuration names, deduplicated.

        What cross-reference validation checks against the live catalogue: a
        name here that no capability answers to is a setting that will never do
        anything, and finding that out at write time is the whole of SC-004.
        """
        named = list(self.enabled or ()) + list(self.disabled) + list(self.parameters)
        return tuple(dict.fromkeys(named))


CAPABILITIES_FIELDS: tuple[str, ...] = tuple(CapabilitiesConfig.model_fields)


__all__ = ["CAPABILITIES_FIELDS", "CapabilitiesConfig"]
