"""Exchanging a Proxmox password for a ticket, on this side of the boundary.

Proxmox's second authentication path is a login: a username and a password are
posted to ``/access/ticket`` and come back as a two-hour cookie and a CSRF
prevention token. Some deployments cannot use anything else — an old realm, a
directory-backed login, a cluster whose token creation is locked down — so
refusing it would be refusing the deployment rather than the credential.

**The exchange has to happen here.** It is itself an authenticated call, and the
thing it authenticates with is the password: a client that could exchange a
ticket would hold a *longer-lived* secret than the one it obtained, which is
exactly the inversion Article IV exists to prevent. So this sits beside the
signing schemes, on the proxy side, for the same reason they do — it needs the
secret at request-construction time.

**The refresher owns no transport of its own.** It is handed the same
``OutboundSender`` the engine forwards through, so the exchange goes out the way
every other call does, is bounded by the same timeout, and is testable against a
recorded response with no cluster in the room.

**A ticket's expiry is declared, not parsed.** Proxmox does not put an expiry in
the login response; the lifetime is a documented two hours. Declaring it means
the proxy refreshes ahead of expiry rather than discovering it with a 401, and
the single retry after an expiry-shaped rejection covers the case where a cluster
was configured with a shorter one.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlencode

from config.constants.security import CREDENTIAL_PROXY_TIMEOUT_SECONDS
from platform.credentials.proxy.errors import RefreshFailed
from platform.credentials.proxy.model import OutboundRequest, OutboundSender
from platform.credentials.proxy.refresh import RefreshedCredential

#: How long a Proxmox ticket is good for. Documented rather than returned, which
#: is why it is a constant here instead of a field read off the response.
TICKET_LIFETIME_SECONDS: Final = 7200

#: Where the exchange happens. One path, on every node.
TICKET_PATH: Final = "/api2/json/access/ticket"

#: What the login response carries. Named because the two are injected under
#: different names than Proxmox returns them by, and a rename in either place
#: should fail here rather than send an unauthenticated request.
_TICKET_FIELD: Final = "ticket"
_CSRF_FIELD: Final = "CSRFPreventionToken"


@dataclass(frozen=True, slots=True)
class ProxmoxTicketRefresher:
    """Turns a stored Proxmox username and password into a live ticket.

    Implements ``CredentialRefresher``. What comes back replaces the stored
    values for the life of one request, so the injections declared by
    ``ticket_rule_for`` find ``ticket`` and ``csrf_token`` where they expect
    them and the password never reaches the wire twice.
    """

    sender: OutboundSender
    #: Which node to log in against. Any node in the cluster answers, and
    #: composition supplies the one the deployment configured first.
    host: str
    port: int = 8006
    timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def refresh(
        self,
        integration: str,
        values: Mapping[str, str],
    ) -> RefreshedCredential:
        """Return a freshly issued ticket for ``integration``.

        Raises:
            RefreshFailed: the login was refused, answered with something that
                is not a Proxmox envelope, or carried no ticket. Never returns
                the stored values unchanged — a refresher that did would turn an
                expiry into a 401 the single retry cannot fix.
        """
        username = values.get("username", "")
        password = values.get("password", "")
        if not username or not password:
            raise RefreshFailed(
                integration,
                cause="the ticket login needs a username and a password, and this credential "
                "carries neither. A deployment that has an API token should declare the "
                "token rule rather than the ticket one.",
            )

        response = await self.sender.send(
            OutboundRequest(
                method="POST",
                url=f"https://{self.host}:{self.port}{TICKET_PATH}",
                headers={"content-type": "application/x-www-form-urlencoded"},
                body=urlencode({"username": username, "password": password}).encode("utf-8"),
            ),
            timeout_seconds=self.timeout_seconds,
        )
        if not response.succeeded:
            raise RefreshFailed(
                integration,
                cause=f"Proxmox refused the ticket login with {response.status_code}. The "
                f"username must carry its realm — 'ninjasre@pve', not 'ninjasre'.",
            )

        data = _login_data(integration, response.body)
        ticket = str(data.get(_TICKET_FIELD, ""))
        if not ticket:
            raise RefreshFailed(
                integration,
                cause="the Proxmox login succeeded and returned no ticket, so there is nothing "
                "to authenticate the next call with",
            )

        return RefreshedCredential(
            values={
                **values,
                "ticket": ticket,
                "csrf_token": str(data.get(_CSRF_FIELD, "")),
            },
            expires_at=self.clock() + timedelta(seconds=TICKET_LIFETIME_SECONDS),
        )


def _login_data(integration: str, body: bytes) -> Mapping[str, Any]:
    """Return the ``data`` object a Proxmox login answered with."""
    try:
        answer = json.loads(body)
    except json.JSONDecodeError as error:
        raise RefreshFailed(
            integration,
            cause=f"the Proxmox login answered with a body that is not JSON: {error.msg}. That "
            f"is usually something other than Proxmox on the configured address.",
        ) from error
    data = answer.get("data") if isinstance(answer, dict) else None
    return data if isinstance(data, dict) else {}


__all__ = ["TICKET_LIFETIME_SECONDS", "TICKET_PATH", "ProxmoxTicketRefresher"]
