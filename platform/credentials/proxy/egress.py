"""The allow-list, enforced before anything is resolved (FR-009).

An integration declares the hosts it lives at, and that declaration doubles as
the list of hosts it may reach. One tuple, not two, because two would drift.

The ordering here is the part worth stating: **the host is checked before the
vault is touched**. A request pointed somewhere it should not be is refused
without a credential ever being decrypted, so the failure costs nothing and
leaks nothing. That matters more than it looks: the realistic way a request
acquires a hostile URL is a prompt-injected log line the agent read, and the
last thing that path should be able to do is make the proxy fetch a secret.

Scheme is checked too, and the rule is about the credential rather than about
the scheme. A vendor reached over plain HTTP while a credential is injected is a
credential on the wire in clear, and there is no operator toggle for that. A
vendor reached over plain HTTP with **nothing** injected puts nothing in the
clear — and that is the ordinary shape of a self-hosted Alertmanager or
Prometheus, which ship no authentication at all and sit on a private address.
Refusing those was refusing a class of deployment over a risk it did not carry.

So the check is split. The host is checked here, before the vault; the
confidentiality check happens once it is known whether a credential resolved,
which is the fact it actually depends on.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from platform.credentials.proxy.errors import EgressDenied, MalformedProxyRequest
from platform.credentials.proxy.injection import InjectionRule

#: The scheme a proxied request carrying a credential may use. Deliberately not
#: configurable: an operator toggle here is a toggle for putting a key in clear.
PERMITTED_SCHEME: Final = "https"

#: Every scheme the proxy will forward at all. Anything else is not a request
#: this component knows how to make, whatever it carries.
FORWARDABLE_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

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

    Says nothing about whether the scheme is safe for what this request will
    carry. That is ``refuse_credential_in_clear`` below, and it runs later
    because it depends on whether a credential resolved.
    """
    split = urlsplit(url)
    host = host_of(url)

    if split.scheme not in FORWARDABLE_SCHEMES:
        raise EgressDenied(rule.integration, host=f"{split.scheme}://{host}", allowed=rule.hosts)
    if not rule.permits(host):
        raise EgressDenied(rule.integration, host=host, allowed=rule.hosts)
    return host


def refuse_credential_in_clear(rule: InjectionRule, url: str) -> None:
    """Raise ``EgressDenied`` if a credential would go out over plain HTTP.

    Called only where a credential actually resolved. The question this answers
    is not "is the scheme https" but "is a secret about to cross an unencrypted
    connection", and those differ exactly where it matters: an integration whose
    rule is optional and whose operator configured no credential sends nothing
    worth protecting, over any scheme.

    Loopback is the same exception it has always been, and for the same reason:
    a test double or a local emulator standing in for a vendor.
    """
    split = urlsplit(url)
    host = host_of(url)
    if split.scheme != PERMITTED_SCHEME and host not in LOOPBACK_HOSTS:
        raise EgressDenied(rule.integration, host=f"{split.scheme}://{host}", allowed=rule.hosts)


__all__ = [
    "FORWARDABLE_SCHEMES",
    "LOOPBACK_HOSTS",
    "PERMITTED_SCHEME",
    "enforce",
    "host_of",
    "refuse_credential_in_clear",
]
