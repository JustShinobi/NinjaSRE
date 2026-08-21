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

**Bridged servers live here too**, because a protocol server is a capability
*source* — the same kind of thing as the shipped catalogue, arriving from
somewhere else. Two fields: which servers a team has, and what an operator has
decided each of their tools does. The second one is separate from the first
because it survives a server being re-registered, and because it is the field
whose absence means "not allowed to run".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import model_validator

from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    ConfiguredStrList,
)


class ProtocolServerSettings(ConfigSection):
    """One bridged server a team has registered.

    No credential field, for the same reason ``IntegrationSettings`` has none:
    the proxy resolves one from the vault at the network edge, and a field here
    would be a place to put a token.
    """

    #: Required. A server with no name has no tools, because a bridged tool's
    #: catalogue name is built from it.
    name: ConfiguredStr
    protocol: ConfiguredStr = "mcp"
    transport: ConfiguredStr = "http"
    #: The HTTP endpoint, for an ``http`` server.
    url: ConfiguredStr = ""
    #: The command, for a ``stdio`` server. Run inside a sandbox, never on the host.
    command: ConfiguredStrList = ()
    #: What the proxy resolves this server's credential and egress allow-list
    #: under. Defaults to one derived from the server's name, so a team that
    #: registers a server and stores a credential for it needs no third setting.
    credential: ConfiguredStr = ""
    enabled: bool = True


class CapabilitiesConfig(ConfigSection):
    """The capability allow-list, deny-list, parameters, and bridged servers."""

    enabled: ConfiguredStrList | None = None
    disabled: ConfiguredStrList = ()
    disabled_tags: ConfiguredStrList = ()
    #: The one open door in the schema, and deliberately narrow: a capability's
    #: parameters are defined by that capability, not here. Everything else is a
    #: declared field.
    parameters: Mapping[str, Mapping[str, Any]] = {}
    #: The protocol servers this team bridges in. Empty for every deployment
    #: that enables none, which is what FR-020 asks for.
    protocol_servers: tuple[ProtocolServerSettings, ...] = ()
    #: ``<server>.<tool>`` to a side-effect level, as an operator decided it. A
    #: tool absent from this mapping is unclassified, which is a write, which
    #: cannot run.
    protocol_classifications: Mapping[str, str] = {}

    @model_validator(mode="after")
    def _server_names_are_distinct(self) -> CapabilitiesConfig:
        """Refuse the same bridged server registered twice."""
        seen: set[str] = set()
        for server in self.protocol_servers:
            if server.name in seen:
                raise ValueError(f"registers the {server.name!r} protocol server more than once")
            seen.add(server.name)
        return self

    def enabled_protocol_servers(self) -> tuple[ProtocolServerSettings, ...]:
        """Return the registered servers a team has switched on."""
        return tuple(server for server in self.protocol_servers if server.enabled)

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


__all__ = ["CAPABILITIES_FIELDS", "CapabilitiesConfig", "ProtocolServerSettings"]
