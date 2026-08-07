"""Which destinations this deployment's configuration permits it to reach.

Article X says no component makes an outbound connection the operator did not
configure. That is a property, and a property nobody can enumerate is a property
nobody can check — so this module enumerates it: every destination is derived
from a setting, and the setting's name travels with it.

The classification rule is the interesting part. A deployment talking to
``postgres:5432`` has not phoned home, and neither has one talking to
``10.0.3.7`` or ``ollama``. What counts as *outbound* here is a publicly
resolvable name or a public address — so the test is: loopback, a private or
link-local address, a cluster-internal suffix, or a bare hostname with no dot in
it is on-host; everything else is not.

A bare hostname is on-host because that is what a Compose service, a Kubernetes
service, and an ``/etc/hosts`` entry all look like, and none of them leaves the
operator's infrastructure. It is a heuristic, and it is the conservative
direction: it can only ever classify something as *internal* that a resolver
might send elsewhere, and the air-gapped deployment that actually matters is the
one with no route off the host to send it down.

The empty host is the case worth naming. A hosted provider used without a base
URL override reaches the vendor's own endpoint, whose address this code has no
business knowing — the SDK owns it. Such a destination is recorded with no host
and is never on-host, which is exactly the answer the air-gapped check needs.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from config.constants.deployment import (
    LOOPBACK_HOSTS,
    NINJASRE_EGRESS_ALLOWLIST_ENV,
    NINJASRE_OTEL_ENDPOINT_ENV,
    SETTING_LIST_SEPARATOR,
)
from config.constants.llm import (
    ANTHROPIC_BASE_URL_ENV,
    AWS_BEDROCK_ENDPOINT_ENV,
    AZURE_OPENAI_ENDPOINT_ENV,
    DEFAULT_PROVIDER,
    LOCAL_PROVIDERS,
    NINJASRE_LLM_PROVIDER_ENV,
    NVIDIA_NIM_BASE_URL_ENV,
    OLLAMA_BASE_URL_ENV,
    OPENAI_BASE_URL_ENV,
    OPENROUTER_BASE_URL_ENV,
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV

#: Where each provider's endpoint can be overridden. A provider absent from this
#: mapping has no override: it is reached at whatever address its SDK ships.
PROVIDER_ENDPOINT_ENV: Mapping[str, str] = {
    PROVIDER_ANTHROPIC: ANTHROPIC_BASE_URL_ENV,
    PROVIDER_OPENAI: OPENAI_BASE_URL_ENV,
    PROVIDER_AZURE_OPENAI: AZURE_OPENAI_ENDPOINT_ENV,
    PROVIDER_AWS_BEDROCK: AWS_BEDROCK_ENDPOINT_ENV,
    PROVIDER_OPENROUTER: OPENROUTER_BASE_URL_ENV,
    PROVIDER_NVIDIA_NIM: NVIDIA_NIM_BASE_URL_ENV,
    PROVIDER_OLLAMA: OLLAMA_BASE_URL_ENV,
}

#: Name suffixes that resolve inside a cluster or a private network.
_INTERNAL_SUFFIXES: tuple[str, ...] = (
    ".local",
    ".internal",
    ".svc",
    ".svc.cluster.local",
    ".cluster.local",
)

PURPOSE_DATABASE = "database"
PURPOSE_PROVIDER = "llm provider"
PURPOSE_PROXY = "credential proxy"
PURPOSE_TELEMETRY = "telemetry export"
PURPOSE_ALLOWED = "operator allow-list"


def host_of(url: str) -> str:
    """Return the hostname ``url`` addresses, or the input if it is a bare host."""
    candidate = url.strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"//{candidate}"
    split = urlsplit(candidate)
    return (split.hostname or "").strip().lower()


def is_on_host(host: str) -> bool:
    """Return whether ``host`` is somewhere the operator already runs.

    The empty host is not: it stands for a vendor endpoint whose address this
    code does not know, which is the one case that must never be mistaken for
    something local.
    """
    name = host.strip().lower()
    if not name:
        return False
    if name in LOOPBACK_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        return bool(address.is_private or address.is_loopback or address.is_link_local)
    if any(name.endswith(suffix) for suffix in _INTERNAL_SUFFIXES):
        return True
    return "." not in name


@dataclass(frozen=True, slots=True)
class EgressDestination:
    """One place this configuration says the deployment may connect to."""

    host: str
    purpose: str
    setting: str

    @property
    def on_host(self) -> bool:
        """Return whether reaching this destination leaves the operator's infrastructure."""
        return is_on_host(self.host)

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a startup report serves."""
        return {
            "host": self.host,
            "purpose": self.purpose,
            "setting": self.setting,
            "on_host": self.on_host,
        }

    def __str__(self) -> str:
        where = self.host or "the vendor's own endpoint"
        return f"{where} ({self.purpose}, from {self.setting})"


def _provider_of(source: Mapping[str, str]) -> str:
    return (source.get(NINJASRE_LLM_PROVIDER_ENV) or DEFAULT_PROVIDER).strip().lower()


def configured_destinations(
    environ: Mapping[str, str] | None = None,
) -> tuple[EgressDestination, ...]:
    """Return every destination this configuration implies, in a stable order.

    Deliberately derived rather than observed. A list built from what a run
    happened to connect to would grow a destination the first time something
    reached one, which is the opposite of the guarantee.
    """
    source = environ if environ is not None else os.environ
    found: list[EgressDestination] = []

    database = source.get(NINJASRE_DATABASE_URL_ENV, "")
    if database:
        found.append(
            EgressDestination(
                host=host_of(database),
                purpose=PURPOSE_DATABASE,
                setting=NINJASRE_DATABASE_URL_ENV,
            )
        )

    provider = _provider_of(source)
    endpoint_env = PROVIDER_ENDPOINT_ENV.get(provider, "")
    endpoint = source.get(endpoint_env, "") if endpoint_env else ""
    found.append(
        EgressDestination(
            host=host_of(endpoint),
            purpose=f"{PURPOSE_PROVIDER} {provider}",
            setting=endpoint_env or NINJASRE_LLM_PROVIDER_ENV,
        )
    )

    proxy = source.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, "")
    if proxy:
        found.append(
            EgressDestination(
                host=host_of(proxy),
                purpose=PURPOSE_PROXY,
                setting=NINJASRE_CREDENTIAL_PROXY_URL_ENV,
            )
        )

    telemetry = source.get(NINJASRE_OTEL_ENDPOINT_ENV, "")
    if telemetry:
        found.append(
            EgressDestination(
                host=host_of(telemetry),
                purpose=PURPOSE_TELEMETRY,
                setting=NINJASRE_OTEL_ENDPOINT_ENV,
            )
        )

    for host in allowed_hosts(source):
        found.append(
            EgressDestination(
                host=host,
                purpose=PURPOSE_ALLOWED,
                setting=NINJASRE_EGRESS_ALLOWLIST_ENV,
            )
        )

    return tuple(found)


def allowed_hosts(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return the hosts the operator listed explicitly, lower-cased and de-duplicated."""
    source = environ if environ is not None else os.environ
    raw = source.get(NINJASRE_EGRESS_ALLOWLIST_ENV, "")
    seen: dict[str, None] = {}
    for entry in raw.split(SETTING_LIST_SEPARATOR):
        host = host_of(entry)
        if host:
            seen.setdefault(host, None)
    return tuple(seen)


def external_destinations(
    environ: Mapping[str, str] | None = None,
) -> tuple[EgressDestination, ...]:
    """Return the configured destinations that leave the operator's infrastructure."""
    return tuple(
        destination for destination in configured_destinations(environ) if not destination.on_host
    )


def provider_is_local(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the configured provider runs on the operator's own infrastructure.

    True for a provider that is local by nature, and for any provider whose
    endpoint the operator has pointed at something on-host — which is how a
    vLLM or a gateway in front of one is configured.
    """
    source = environ if environ is not None else os.environ
    provider = _provider_of(source)
    if provider in LOCAL_PROVIDERS:
        return True
    endpoint_env = PROVIDER_ENDPOINT_ENV.get(provider, "")
    endpoint = source.get(endpoint_env, "") if endpoint_env else ""
    return bool(endpoint) and is_on_host(host_of(endpoint))


def permitted_hosts(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """Return every host this configuration permits a connection to."""
    return frozenset(
        destination.host for destination in configured_destinations(environ) if destination.host
    )


def unexpected(
    observed: Iterable[str],
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return the observed hosts this configuration never permitted (SC-008).

    On-host destinations are not reported. A deployment reaching its own
    database, its own proxy, and its own sandbox over loopback is what it is
    supposed to do, and a monitor that flagged those would be one nobody could
    keep green.
    """
    permitted = permitted_hosts(environ)
    surprises: dict[str, None] = {}
    for entry in observed:
        host = host_of(entry)
        if not host or host in permitted or is_on_host(host):
            continue
        surprises.setdefault(host, None)
    return tuple(sorted(surprises))


__all__ = [
    "PROVIDER_ENDPOINT_ENV",
    "PURPOSE_ALLOWED",
    "PURPOSE_DATABASE",
    "PURPOSE_PROVIDER",
    "PURPOSE_PROXY",
    "PURPOSE_TELEMETRY",
    "EgressDestination",
    "allowed_hosts",
    "configured_destinations",
    "external_destinations",
    "host_of",
    "is_on_host",
    "permitted_hosts",
    "provider_is_local",
    "unexpected",
]
