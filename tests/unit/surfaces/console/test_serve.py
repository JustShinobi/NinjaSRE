"""What the console process has to do beyond rendering: sessions, and the cookie.

``app.py`` answers "what does this path look like". This is the other half — the
part that has to exist before a browser can reach any of it — and the three
things asserted here are the three a renderer cannot do for itself.

**The token is not in the cookie.** The session lives in the process and the
cookie carries an opaque handle to it. A signed cookie would also work and would
be one more place a bearer token is written down, which is what
``session.py`` exists to avoid.

**A sign-in is a POST that ends in a redirect.** Answering the POST with the
page would leave the browser holding a form submission it re-sends on reload,
and re-sending a sign-in is how somebody ends up looking at a stale page and
believing it.

**The path they were going to survives the sign-in**, because an on-call
engineer arrives at the console by following a link to a run, not by browsing
to it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from surfaces.console.client import ConsoleClient, Response
from surfaces.console.serve import SESSION_COOKIE, ConsoleServer
from surfaces.console.session import SIGN_IN_PATH

PRINCIPAL: Mapping[str, Any] = {
    "principal_id": "ada",
    "display_name": "Ada",
    "team_node_id": "payments",
    "permissions": ["run.read", "config.read"],
    "roles": ["operator"],
}

TOKEN = "a-token-the-deployment-accepts"


@dataclass
class RecordingTransport:
    """A transport that answers from a table and remembers what it was asked."""

    answers: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    seen: list[tuple[str, str, str]] = field(default_factory=list)

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Return the canned answer for ``path``, recording the authorization sent."""
        self.seen.append((method, path, dict(headers or {}).get("authorization", "")))
        route = path.split("?")[0]
        if route == "/auth/me" and dict(headers or {}).get("authorization") != f"Bearer {TOKEN}":
            return Response(status=401, body={"detail": "no"})
        if route not in self.answers:
            return Response(status=404, body={"detail": f"no route {route}"})
        return Response(status=200, body=self.answers[route])


def server_for(transport: RecordingTransport) -> ConsoleServer:
    """Return a console server wired to ``transport``."""
    return ConsoleServer(client=ConsoleClient(transport=transport))


async def call(
    server: ConsoleServer,
    method: str,
    path: str,
    *,
    cookie: str = "",
    form: bytes = b"",
) -> tuple[int, dict[str, str], str]:
    """Drive one request through the ASGI app and return status, headers, and body."""
    headers: list[tuple[bytes, bytes]] = []
    if cookie:
        headers.append((b"cookie", f"{SESSION_COOKIE}={cookie}".encode()))
    if form:
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))

    target, _, query = path.partition("?")
    scope = {
        "type": "http",
        "method": method,
        "path": target,
        "query_string": query.encode(),
        "headers": headers,
        "scheme": "http",
    }

    messages: list[Mapping[str, Any]] = []
    sent = [{"type": "http.request", "body": form, "more_body": False}]

    async def receive() -> Mapping[str, Any]:
        return sent.pop(0) if sent else {"type": "http.disconnect"}

    async def send(message: Mapping[str, Any]) -> None:
        messages.append(message)

    await server(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        bytes(message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], _headers_of(start["headers"]), body.decode()


def _headers_of(raw: Sequence[tuple[bytes, bytes]]) -> dict[str, str]:
    """Return response headers as a lowercase-keyed mapping."""
    return {name.decode().lower(): value.decode() for name, value in raw}


def _handle_in(headers: Mapping[str, str]) -> str:
    """Return the session handle the response set, or the empty string."""
    cookie = headers.get("set-cookie", "")
    if f"{SESSION_COOKIE}=" not in cookie:
        return ""
    return cookie.split(f"{SESSION_COOKIE}=", 1)[1].split(";", 1)[0]


@pytest.mark.asyncio
async def test_a_visitor_with_no_session_is_shown_the_sign_in_and_nothing_else() -> None:
    status, _, body = await call(server_for(RecordingTransport()), "GET", "/runs")

    assert status == 200
    assert "/sign-in" in body
    # Nothing about the deployment: no navigation, no run list, no team names.
    assert "run-1" not in body


@pytest.mark.asyncio
async def test_signing_in_sets_a_cookie_that_does_not_contain_the_token() -> None:
    transport = RecordingTransport(answers={"/auth/me": PRINCIPAL})

    status, headers, _ = await call(
        server_for(transport), "POST", SIGN_IN_PATH, form=f"token={TOKEN}".encode()
    )

    assert status == 303
    cookie = headers["set-cookie"]
    assert TOKEN not in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


@pytest.mark.asyncio
async def test_a_signed_in_session_renders_the_page_and_presents_the_token_to_the_api() -> None:
    transport = RecordingTransport(
        answers={"/auth/me": PRINCIPAL, "/v1/runs": {"runs": [{"run_id": "run-1"}]}}
    )
    server = server_for(transport)

    _, headers, _ = await call(server, "POST", SIGN_IN_PATH, form=f"token={TOKEN}".encode())
    status, _, body = await call(server, "GET", "/runs", cookie=_handle_in(headers))

    assert status == 200
    assert "run-1" in body
    assert (
        "GET",
        "/v1/runs?limit=50",
        f"Bearer {TOKEN}",
    ) in transport.seen


@pytest.mark.asyncio
async def test_a_rejected_token_returns_to_the_sign_in_rather_than_a_session() -> None:
    status, headers, body = await call(
        server_for(RecordingTransport()), "POST", SIGN_IN_PATH, form=b"token=wrong"
    )

    assert status == 200
    assert _handle_in(headers) == ""
    assert "/sign-in" in body


@pytest.mark.asyncio
async def test_the_path_the_visitor_wanted_is_where_the_sign_in_sends_them() -> None:
    transport = RecordingTransport(answers={"/auth/me": PRINCIPAL})
    server = server_for(transport)

    _, headers, _ = await call(server, "GET", "/runs/run-1")
    _, signed_in, _ = await call(
        server,
        "POST",
        SIGN_IN_PATH,
        cookie=_handle_in(headers),
        form=f"token={TOKEN}".encode(),
    )

    assert signed_in["location"] == "/runs/run-1"


@pytest.mark.asyncio
async def test_signing_out_drops_the_session_the_handle_pointed_at() -> None:
    transport = RecordingTransport(answers={"/auth/me": PRINCIPAL, "/v1/runs": {"runs": []}})
    server = server_for(transport)

    _, headers, _ = await call(server, "POST", SIGN_IN_PATH, form=f"token={TOKEN}".encode())
    handle = _handle_in(headers)
    await call(server, "POST", "/sign-out", cookie=handle)

    status, _, body = await call(server, "GET", "/runs", cookie=handle)

    assert status == 200
    assert "/sign-in" in body


@pytest.mark.asyncio
async def test_liveness_answers_without_reaching_the_api() -> None:
    transport = RecordingTransport()

    status, _, _ = await call(server_for(transport), "GET", "/health/live")

    assert status == 200
    assert transport.seen == []
