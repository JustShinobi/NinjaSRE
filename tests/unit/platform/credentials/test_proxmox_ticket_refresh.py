"""T-003: a Proxmox ticket login, on the proxy side, refreshed before it expires.

A ticket is Proxmox's second way in, for deployments that cannot issue an API
token. It is also the one that would break Article IV if it were done anywhere
else: exchanging a username and password for a ticket is an authenticated call,
and a client that could make it would be holding a password — a *longer-lived*
secret than the two-hour ticket it buys.

So the exchange lives beside the signing schemes, on the proxy side, and these
tests assert the three things that make it safe rather than merely working: the
password goes out exactly once and never comes back, a refusal is reported as a
refusal rather than as a stale credential, and the ticket carries a declared
expiry so the proxy renews it ahead of time instead of discovering it with a 401.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from platform.credentials.proxy.errors import RefreshFailed
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.refresh import needs_refresh
from platform.credentials.proxy.tickets import (
    TICKET_LIFETIME_SECONDS,
    TICKET_PATH,
    ProxmoxTicketRefresher,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

CREDENTIAL = {"username": "ninjasre@pve", "password": "the-operators-actual-password"}

LOGIN_RESPONSE = OutboundResponse(
    200,
    {"content-type": "application/json"},
    b'{"data":{"ticket":"PVE:ninjasre@pve:68A1B2C3::signature","CSRFPreventionToken":"68A1B2C3:tok"}}',
)


@dataclass(slots=True)
class ScriptedNode:
    """A Proxmox node's login endpoint, recorded."""

    response: OutboundResponse = LOGIN_RESPONSE
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the scripted login response."""
        self.sent.append(request)
        return self.response


def refresher(node: ScriptedNode) -> ProxmoxTicketRefresher:
    """Return a refresher pointed at ``node``, on a fixed clock."""
    return ProxmoxTicketRefresher(sender=node, host="pve01.acme.example", clock=lambda: AT)


async def test_a_login_returns_a_ticket_and_a_csrf_token() -> None:
    node = ScriptedNode()

    refreshed = await refresher(node).refresh("proxmox", CREDENTIAL)

    assert refreshed.values["ticket"].startswith("PVE:ninjasre@pve:")
    assert refreshed.values["csrf_token"] == "68A1B2C3:tok"


async def test_the_exchange_goes_to_the_nodes_own_login_path() -> None:
    node = ScriptedNode()

    await refresher(node).refresh("proxmox", CREDENTIAL)

    assert node.sent[0].method == "POST"
    assert node.sent[0].path == TICKET_PATH
    assert node.sent[0].host == "pve01.acme.example"


async def test_the_password_is_sent_once_and_never_returned() -> None:
    """The whole reason this is on the proxy side rather than in the client."""
    node = ScriptedNode()

    refreshed = await refresher(node).refresh("proxmox", CREDENTIAL)

    bodies = [request.body or b"" for request in node.sent]
    assert sum(b"the-operators-actual-password" in body for body in bodies) == 1
    assert "the-operators-actual-password" not in repr(refreshed)


async def test_the_ticket_carries_the_expiry_the_proxy_refreshes_ahead_of() -> None:
    node = ScriptedNode()

    refreshed = await refresher(node).refresh("proxmox", CREDENTIAL)

    assert refreshed.expires_at is not None
    assert (refreshed.expires_at - AT).total_seconds() == TICKET_LIFETIME_SECONDS
    assert not needs_refresh(refreshed.expires_at, AT)


async def test_a_ticket_inside_the_refresh_margin_is_refreshed_rather_than_used() -> None:
    node = ScriptedNode()
    refreshed = await refresher(node).refresh("proxmox", CREDENTIAL)

    assert refreshed.expires_at is not None
    almost_expired = refreshed.expires_at
    assert needs_refresh(almost_expired, almost_expired)


async def test_a_refused_login_says_the_realm_is_probably_missing() -> None:
    """'ninjasre' and 'ninjasre@pve' are one character apart and one of them works."""
    node = ScriptedNode(response=OutboundResponse(401, {}, b"authentication failure"))

    with pytest.raises(RefreshFailed, match="realm"):
        await refresher(node).refresh("proxmox", CREDENTIAL)


async def test_a_credential_with_no_password_is_refused_rather_than_attempted() -> None:
    node = ScriptedNode()

    with pytest.raises(RefreshFailed, match="username and a password"):
        await refresher(node).refresh("proxmox", {"api_token": "irrelevant"})

    assert not node.sent, "a login with nothing to log in with should not be attempted"


async def test_a_login_that_answers_with_no_ticket_is_a_failure_not_a_success() -> None:
    """Returning the stored values would turn an expiry into a 401 nothing can fix."""
    node = ScriptedNode(response=OutboundResponse(200, {}, b'{"data":{}}'))

    with pytest.raises(RefreshFailed, match="no ticket"):
        await refresher(node).refresh("proxmox", CREDENTIAL)


async def test_something_that_is_not_proxmox_on_the_address_says_so() -> None:
    node = ScriptedNode(response=OutboundResponse(200, {}, b"<html>login</html>"))

    with pytest.raises(RefreshFailed, match="not JSON"):
        await refresher(node).refresh("proxmox", CREDENTIAL)
