"""Which servers a team has bridged, and everything that follows from saying so.

A registration is one line of a team's configuration, and four things are
derived from it rather than configured separately — because four settings that
have to agree are four settings that eventually do not.

**The credential handle.** Each server gets its own integration name at the
proxy, derived from the server's name unless an operator names a shared one. Two
teams' servers therefore cannot resolve each other's credential: the handle is
``<integration>/<team>`` and the integration differs.

**The egress allow-list.** A server's URL names the one host it may be reached
at, and that tuple is both the proxy's allow-list and — for a stdio server
running in a sandbox — the sandbox's. One declaration, so widening the address
widens the permission in the same edit (T045).

**The injection rule.** How the secret is attached, declared here and applied
proxy-side. There is no field on a registration that could hold a value.

**Nothing at all, for stdio.** A local command cannot be given a credential:
the only places to put one are its environment and its arguments, and Article IV
forbids both. A stdio server is unauthenticated by construction, and declaring
otherwise is refused at registration rather than discovered at the first call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

from capabilities.protocols.classification import ClassificationTable
from capabilities.protocols.namespacing import validate_server_name
from capabilities.protocols.port import ProtocolKind
from config.constants.protocols import MAX_PROTOCOL_SERVERS_PER_TEAM
from platform.config_service.schema.capabilities import (
    CapabilitiesConfig,
    ProtocolServerSettings,
)
from platform.credentials.proxy.injection import (
    BearerTokenInjection,
    HeaderInjection,
    InjectionRule,
)

#: Prefix for the integration name a server's credential is stored under, when
#: an operator has not named a shared one. Distinct from every vendor package
#: name, so a bridged server can never resolve a native integration's secret.
BRIDGE_CREDENTIAL_PREFIX: Final = "bridge_"

#: The vault field a bridged server's secret is stored in. One name, because a
#: bridged server's credential is a token and there is nothing else it could be.
BRIDGE_CREDENTIAL_FIELD: Final = "token"

#: What a header-authenticated server's header is called when nobody said.
DEFAULT_AUTH_HEADER: Final = "Authorization"

_HTTPS: Final = "https"


class TransportKind(StrEnum):
    """How a registered server is reached."""

    HTTP = "http"
    STDIO = "stdio"


class AuthKind(StrEnum):
    """How a server's credential is attached, proxy-side."""

    NONE = "none"
    BEARER = "bearer"
    HEADER = "header"


@dataclass(frozen=True, slots=True)
class ServerRegistration:
    """One bridged server, as a team registered it.

    Validated at construction rather than at first use. A server whose name
    cannot namespace a tool, whose URL is not TLS, or which claims a credential
    it has nowhere to put is a configuration error, and finding it during an
    incident is finding it at the worst possible time.
    """

    name: str
    protocol: ProtocolKind = ProtocolKind.MCP
    transport: TransportKind = TransportKind.HTTP
    url: str = ""
    command: tuple[str, ...] = ()
    credential: str = ""
    auth: AuthKind = AuthKind.NONE
    auth_header: str = DEFAULT_AUTH_HEADER
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_server_name(self.name)
        object.__setattr__(self, "command", tuple(self.command))

        if self.transport is TransportKind.HTTP:
            if not self.url:
                raise ValueError(
                    f"the {self.name!r} server is registered over http and declares no url, "
                    f"so there is nowhere to send a request"
                )
            split = urlsplit(self.url)
            if split.scheme != _HTTPS or not split.hostname:
                raise ValueError(
                    f"the {self.name!r} server's url must be an absolute https address; "
                    f"a bridged server reached over plain http puts its credential on the "
                    f"wire in clear, and there is no toggle for that"
                )
            return

        if not self.command:
            raise ValueError(
                f"the {self.name!r} server is registered over stdio and declares no command, "
                f"so there is nothing to run"
            )
        if self.auth is not AuthKind.NONE:
            raise ValueError(
                f"the {self.name!r} server is registered over stdio and declares "
                f"{self.auth.value!r} authentication. A local command can only be given a "
                f"credential through its environment or its arguments, and Article IV "
                f"forbids both — expose the server over https instead."
            )
        if self.url:
            raise ValueError(
                f"the {self.name!r} server declares both a command and a url; one server "
                f"is reached one way, and guessing which would be guessing"
            )

    @property
    def integration(self) -> str:
        """Return the name the proxy resolves this server's credential under."""
        return self.credential or f"{BRIDGE_CREDENTIAL_PREFIX}{self.name}"

    def egress_hosts(self) -> tuple[str, ...]:
        """Return the hosts this server may be reached at — its allow-list."""
        if self.transport is not TransportKind.HTTP:
            return ()
        host = urlsplit(self.url).hostname
        return (host,) if host else ()

    def injection_rule(self) -> InjectionRule | None:
        """Return how the proxy attaches this server's secret, or ``None`` if there is none."""
        if self.auth is AuthKind.NONE:
            return None
        injection = (
            BearerTokenInjection(field=BRIDGE_CREDENTIAL_FIELD)
            if self.auth is AuthKind.BEARER
            else HeaderInjection(header=self.auth_header, field=BRIDGE_CREDENTIAL_FIELD)
        )
        return InjectionRule(
            integration=self.integration,
            hosts=self.egress_hosts(),
            injections=(injection,),
        )


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """What changed when a server's tool set was read again.

    ``added`` is the part with teeth: a tool that appeared since the last
    refresh is unclassified, and unclassified cannot execute. A server that
    quietly renames ``list_deploys`` to ``manage_deploys`` therefore loses the
    classification along with the name, which is the correct outcome and not a
    convenience.
    """

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()
    classifications: ClassificationTable = field(default_factory=ClassificationTable)

    @property
    def changed(self) -> bool:
        """Return whether the tool set moved at all."""
        return bool(self.added or self.removed)


def refresh_classifications(
    previous: ClassificationTable, *, offered: Sequence[str]
) -> RefreshOutcome:
    """Return the classification table after a server's tool set was read again.

    Removed tools are dropped rather than kept dormant. A stored verdict about a
    name the server no longer offers would be inherited by whatever the server
    calls that name next, and "the operator already approved this" would be true
    of a tool they never saw.
    """
    current = tuple(dict.fromkeys(offered))
    known = set(previous.entries)
    added = tuple(name for name in current if name not in known)
    retained = tuple(name for name in current if name in known)
    removed = tuple(sorted(known - set(current)))
    return RefreshOutcome(
        added=added,
        removed=removed,
        retained=retained,
        classifications=previous.restricted_to(current),
    )


@dataclass(frozen=True, slots=True)
class ProtocolRegistry:
    """Everything one team declared about bridged servers, read once.

    Holds no connection and performs no I/O. Composition turns these
    registrations into transports and an adapter; keeping the declaration
    separate from the connection is what lets the console show a team's servers
    without contacting any of them.
    """

    registrations: tuple[ServerRegistration, ...] = ()
    classifications: ClassificationTable = field(default_factory=ClassificationTable)

    @classmethod
    def from_config(cls, capabilities: CapabilitiesConfig) -> ProtocolRegistry:
        """Return the registry one team's configuration describes."""
        return cls(
            registrations=registrations_from_config(capabilities),
            classifications=ClassificationTable.of(dict(capabilities.protocol_classifications)),
        )

    def servers_for(self, protocol: ProtocolKind) -> tuple[str, ...]:
        """Return the enabled servers speaking ``protocol``, in declaration order."""
        return tuple(
            item.name for item in self.registrations if item.protocol is protocol and item.enabled
        )

    def registration(self, name: str) -> ServerRegistration | None:
        """Return the registration called ``name``, or ``None``."""
        for item in self.registrations:
            if item.name == name:
                return item
        return None

    def injection_rules(self) -> tuple[InjectionRule, ...]:
        """Return every rule the proxy needs to authenticate this team's servers."""
        rules = (item.injection_rule() for item in self.registrations if item.enabled)
        return tuple(rule for rule in rules if rule is not None)

    def egress_hosts(self) -> tuple[str, ...]:
        """Return every host this team's bridged servers may be reached at."""
        hosts: list[str] = []
        for item in self.registrations:
            if item.enabled:
                hosts.extend(item.egress_hosts())
        return tuple(dict.fromkeys(hosts))

    def __bool__(self) -> bool:
        """Return whether this team bridges anything at all."""
        return any(item.enabled for item in self.registrations)


def registrations_from_config(
    capabilities: CapabilitiesConfig,
) -> tuple[ServerRegistration, ...]:
    """Return the enabled servers a team's capabilities configuration declares.

    Raises rather than truncating past the cap. A team that declared seventeen
    servers meant all seventeen, and quietly dropping the last one would produce
    an investigation missing tools nobody could account for.
    """
    enabled = capabilities.enabled_protocol_servers()
    if len(enabled) > MAX_PROTOCOL_SERVERS_PER_TEAM:
        raise ValueError(
            f"this team registers {len(enabled)} protocol servers and the cap is "
            f"{MAX_PROTOCOL_SERVERS_PER_TEAM}; every one of them is contacted before an "
            f"investigation starts"
        )
    return tuple(_registration_from(settings) for settings in enabled)


def _registration_from(settings: ProtocolServerSettings) -> ServerRegistration:
    """Return the registration one configuration entry describes."""
    return ServerRegistration(
        name=settings.name,
        protocol=_protocol_of(settings.protocol, settings.name),
        transport=_transport_of(settings.transport, settings.name),
        url=settings.url,
        command=tuple(settings.command),
        credential=settings.credential,
        auth=AuthKind.BEARER if settings.credential else AuthKind.NONE,
        enabled=settings.enabled,
    )


def _protocol_of(value: str, server: str) -> ProtocolKind:
    """Return the protocol ``value`` names, or raise saying which are known."""
    try:
        return ProtocolKind(value.strip().lower())
    except ValueError as error:
        raise ValueError(
            f"the {server!r} server declares protocol {value!r}; the bridges are "
            f"{', '.join(kind.value for kind in ProtocolKind)}"
        ) from error


def _transport_of(value: str, server: str) -> TransportKind:
    """Return the transport ``value`` names, or raise saying which are known."""
    try:
        return TransportKind(value.strip().lower())
    except ValueError as error:
        raise ValueError(
            f"the {server!r} server declares transport {value!r}; the transports are "
            f"{', '.join(kind.value for kind in TransportKind)}"
        ) from error


__all__ = [
    "BRIDGE_CREDENTIAL_FIELD",
    "BRIDGE_CREDENTIAL_PREFIX",
    "AuthKind",
    "ProtocolRegistry",
    "RefreshOutcome",
    "ServerRegistration",
    "TransportKind",
    "refresh_classifications",
    "registrations_from_config",
]
