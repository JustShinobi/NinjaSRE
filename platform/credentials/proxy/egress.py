"""The allow-list, enforced before anything is resolved (FR-009).

An integration declares the hosts it lives at, and that declaration doubles as
the list of hosts it may reach. One tuple, not two, because two would drift.

The ordering here is the part worth stating: **the host is checked before the
vault is touched**. A request pointed somewhere it should not be is refused
without a credential ever being decrypted, so the failure costs nothing and
leaks nothing. That matters more than it looks: the realistic way a request
acquires a hostile URL is a prompt-injected log line the agent read, and the
last thing that path should be able to do is make the proxy fetch a secret.

Scheme is checked too. A vendor that is reachable over plain HTTP is a vendor
whose credential is on the wire in clear, and there is no operator toggle for
that — an integration that genuinely needs it is a different integration.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from platform.credentials.proxy.errors import EgressDenied, MalformedProxyRequest
from platform.credentials.proxy.injection import InjectionRule

#: The only scheme a proxied request may use. Deliberately not configurable.
PERMITTED_SCHEME: Final = "https"

#: Loopback is the exception, and only for a test double or a local emulator
#: standing in for a vendor. It is spelled out rather than pattern-matched so
#: that widening it is an edit somebody has to justify.
LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})


def host_of(url: str) -> str:
    """Return the host ``url`` addresses, without its port.

    Raises ``MalformedProxyRequest`` for anything that is not an absolute URL.
    A relative URL reaching here means a client built a request without a base,
    and letting it through would make the allow-list check pass on an empty
    host.
    """
    split = urlsplit(url)
    if not split.scheme or not split.hostname:
        raise MalformedProxyRequest(
            f"{url!r} is not an absolute URL, so there is no host to check against "
            f"the egress allow-list.",
            integration="",
        )
    return split.hostname


def enforce(rule: InjectionRule, url: str) -> str:
    """Return the host ``url`` addresses, or raise ``EgressDenied``.

    Returns the host rather than nothing so the caller does not parse the URL a
    second time — and so the audit line records the host that was actually
    checked rather than one re-derived later.
    """
    split = urlsplit(url)
    host = host_of(url)

    if split.scheme != PERMITTED_SCHEME and host not in LOOPBACK_HOSTS:
        raise EgressDenied(rule.integration, host=f"{split.scheme}://{host}", allowed=rule.hosts)
    if not rule.permits(host):
        raise EgressDenied(rule.integration, host=host, allowed=rule.hosts)
    return host


__all__ = [
    "LOOPBACK_HOSTS",
    "PERMITTED_SCHEME",
    "enforce",
    "host_of",
]
