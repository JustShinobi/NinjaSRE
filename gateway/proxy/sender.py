"""What actually puts the proxy's bytes on the wire, and what it trusts while doing it.

The standard library rather than an HTTP client library, for one reason that is
specific to this component: the credential proxy is the process that holds the
secrets, and the smallest dependency tree in the deployment belongs here. An
async client would be faster under load; nothing here is on an investigation's
critical path more than once per tool call, and "what is in this container" is a
question a security review asks about this container in particular.

``urllib`` is synchronous, so each send runs in a worker thread. That is a
thread per in-flight outbound call, bounded by the deployment's own concurrency
ceiling — which is a profile-scoped named constant, so the bound exists.

**The trust store is the other half.** An operator behind a proxy that
terminates TLS has a certificate authority the system store does not know, and
the failure mode without it is every outbound call failing verification at once
(FR-025). ``NINJASRE_CA_BUNDLE`` names a bundle to trust *in addition to* the
system's. There is deliberately no setting that turns verification off: a
deployment that skipped it would send credentials to whoever answered.

**Naming a bundle also drops RFC 5280 strictness, and only that.** Python 3.13
turned ``VERIFY_X509_STRICT`` on by default, which requires a certificate
authority to carry ``keyUsage=keyCertSign,cRLSign``. An appliance that mints
its own authority predictably omits it — Proxmox VE does — so a deployment
pointed at its own cluster fails every call with "CA cert does not include key
usage extension" no matter how correctly the bundle was configured. Chain
building, expiry and hostname checking all stay on; what is relaxed is one
conformance rule about how the operator's own authority was minted, and the
operator naming the bundle is the decision that relaxes it.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from config.constants.deployment import NINJASRE_CA_BUNDLE_ENV
from config.constants.security import CREDENTIAL_PROXY_TIMEOUT_SECONDS
from platform.credentials.proxy.errors import UpstreamUnreachable
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse


def trust_context(environ: Mapping[str, str] | None = None) -> ssl.SSLContext:
    """Return the TLS context outbound calls verify against (FR-025).

    The system store, plus the operator's bundle when they named one. Raises
    rather than falling back to the system store alone if the bundle cannot be
    loaded: a deployment that silently ignored its configured trust anchor
    would fail every call to the vendor behind the intercepting proxy, and the
    reason would be nowhere.

    A deployment that named no bundle stays as strict as the standard library
    is, so nothing about verifying a public vendor changes here.
    """
    source = environ if environ is not None else os.environ
    context = ssl.create_default_context()
    bundle = source.get(NINJASRE_CA_BUNDLE_ENV, "").strip()
    if bundle:
        context.load_verify_locations(cafile=str(Path(bundle)))
        # See the module docstring: an appliance's own authority is minted
        # without the extension RFC 5280 wants, and refusing it would make the
        # bundle setting useless for the case it exists to serve.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


class HttpOutboundSender:
    """Sends one already-authenticated request and returns what came back.

    Never retries. Retry policy belongs to the integration client, which knows
    whether the operation is idempotent; a proxy that retried on its own would
    turn one write into two for every vendor whose timeout is optimistic.
    """

    __slots__ = ("_context",)

    def __init__(self, *, context: ssl.SSLContext | None = None) -> None:
        self._context = context if context is not None else trust_context()

    async def send(
        self,
        request: OutboundRequest,
        *,
        timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS,
    ) -> OutboundResponse:
        """Send ``request`` and return the vendor's answer.

        Raises ``UpstreamUnreachable`` when nothing came back at all. A
        status the vendor sent and a failure the proxy invented lead to
        different operator actions, so an invented 502 is never returned.
        """
        return await asyncio.to_thread(self._send, request, timeout_seconds)

    def _send(self, request: OutboundRequest, timeout_seconds: float) -> OutboundResponse:
        prepared = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method.upper(),
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 — the URL is allow-listed upstream
                prepared, timeout=timeout_seconds, context=self._context
            ) as answer:
                return OutboundResponse(
                    status_code=int(answer.status),
                    headers={key.lower(): value for key, value in answer.headers.items()},
                    body=answer.read(),
                )
        except urllib.error.HTTPError as answer:
            # A status the vendor actually sent. Not an error from the proxy's
            # point of view: a 401 is the answer to "is this credential valid",
            # and swallowing it would lose the one thing the caller needed.
            return OutboundResponse(
                status_code=int(answer.code),
                headers={key.lower(): value for key, value in answer.headers.items()},
                body=answer.read(),
            )
        except (urllib.error.URLError, ssl.SSLError, OSError) as error:
            # No integration name: this layer is handed a request, not the
            # rule that authenticated it. The engine catches this and re-raises
            # with the integration attached, which is where that fact lives.
            raise UpstreamUnreachable(
                "",
                host=request.host or urlsplit(request.url).hostname or request.url,
                cause=f"{type(error).__name__}: {error}",
            ) from error


__all__ = ["HttpOutboundSender", "trust_context"]
