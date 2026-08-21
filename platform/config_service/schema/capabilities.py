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
from typing import Annotated, Any

from pydantic import model_validator

from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    ConfiguredStrList,
    field_help,
    section_help,
)


class ProtocolServerSettings(ConfigSection):
    """One bridged server a team has registered.

    No credential field, for the same reason ``IntegrationSettings`` has none:
    the proxy resolves one from the vault at the network edge, and a field here
    would be a place to put a token.
    """

    model_config = section_help(
        "An outside tool server this team has registered. Its tools join the catalogue "
        "alongside the shipped ones. No secret is entered here: the token is stored in "
        "the vault and named below."
    )

    #: Required. A server with no name has no tools, because a bridged tool's
    #: catalogue name is built from it.
    name: Annotated[
        ConfiguredStr,
        field_help(
            "What this server is called. Required: every tool it offers is listed under this name."
        ),
    ]
    protocol: Annotated[ConfiguredStr, field_help("The protocol the server speaks.")] = "mcp"
    transport: Annotated[
        ConfiguredStr,
        field_help(
            "How the server is reached: over HTTP at a URL, or by running a command in a sandbox."
        ),
    ] = "http"
    #: The HTTP endpoint, for an ``http`` server.
    url: Annotated[
        ConfiguredStr, field_help("The address of the server, when it is reached over HTTP.")
    ] = ""
    #: The command, for a ``stdio`` server. Run inside a sandbox, never on the host.
    command: Annotated[
        ConfiguredStrList,
        field_help(
            "The command that starts the server, when it is run locally. It runs in a "
            "sandbox, never directly on the host."
        ),
    ] = ()
    #: What the proxy resolves this server's credential and egress allow-list
    #: under. Defaults to one derived from the server's name, so a team that
    #: registers a server and stores a credential for it needs no third setting.
    credential: Annotated[
        ConfiguredStr,
        field_help(
            "Which stored credential this server authenticates with. Leave it empty and "
            "the one named after the server is used."
        ),
    ] = ""
    enabled: Annotated[
        bool, field_help("Off keeps the server registered and offers none of its tools.")
    ] = True


class CapabilitiesConfig(ConfigSection):
    """The capability allow-list, deny-list, parameters, and bridged servers."""

    model_config = section_help(
        "Which of the platform's capabilities this team may run, what they are called "
        "with, and any outside tool servers it has registered. A capability that is both "
        "allowed and blocked is blocked."
    )

    enabled: Annotated[
        ConfiguredStrList | None,
        field_help(
            "The only capabilities this team may run. Leave it unset for everything the "
            "catalogue offers; an empty list means nothing at all, which is rarely what "
            "is meant."
        ),
    ] = None
    disabled: Annotated[
        ConfiguredStrList,
        field_help("Capabilities this team may never run, whatever else allows them."),
    ] = ()
    disabled_tags: Annotated[
        ConfiguredStrList,
        field_help(
            "Whole families switched off at once — every remediation capability, every "
            "capability of a vendor being retired — so the list stays right as the "
            "catalogue grows."
        ),
    ] = ()
    #: The one open door in the schema, and deliberately narrow: a capability's
    #: parameters are defined by that capability, not here. Everything else is a
    #: declared field.
    parameters: Annotated[
        Mapping[str, Mapping[str, Any]],
        field_help(
            "Per-capability argument defaults, keyed by capability name. Only for "
            "capabilities that accept them."
        ),
    ] = {}
    #: The protocol servers this team bridges in. Empty for every deployment
    #: that registers none.
    protocol_servers: Annotated[
        tuple[ProtocolServerSettings, ...],
        field_help("Outside tool servers this team has registered."),
    ] = ()
    #: ``<server>.<tool>`` to a side-effect level, as an operator decided it. A
    #: tool absent from this mapping is unclassified, which is a write, which
    #: cannot run.
    protocol_classifications: Annotated[
        Mapping[str, str],
        field_help(
            "What each bridged tool is allowed to do, keyed by server and tool name. A "
            "tool nobody has classified is treated as a write and cannot run."
        ),
    ] = {}

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
        anything, and it is worth finding out at write time rather than during an
        investigation.
        """
        named = list(self.enabled or ()) + list(self.disabled) + list(self.parameters)
        return tuple(dict.fromkeys(named))


CAPABILITIES_FIELDS: tuple[str, ...] = tuple(CapabilitiesConfig.model_fields)


__all__ = ["CAPABILITIES_FIELDS", "CapabilitiesConfig", "ProtocolServerSettings"]
