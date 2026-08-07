"""The process that puts the console in front of a browser.

``app.py`` turns a path into a document and stops there, deliberately: what
serves it is a deployment decision, and a page test should not have to stand up
a server to assert what a page contains. This is that decision, made once — the
ASGI application the console image runs, and the only module in the package that
knows HTTP exists.

Three things live here because a renderer cannot do them, and each is the reason
the split is worth having.

**Sessions are held in the process, not in the cookie.** The cookie carries an
opaque handle; the bearer token never leaves this address space. A signed cookie
would work too, and would put a token into every browser cache, proxy log, and
screenshot — which is the thing ``session.py`` is built to prevent, and it would
be defeated here rather than there.

**A sign-in ends in a redirect.** Answering the POST with a page leaves the
browser holding a form submission it re-sends on reload, and a re-sent sign-in
is how somebody ends up reading a stale page and believing it.

**The store is bounded and swept.** An unbounded session map is a memory leak
with a login form in front of it. Expired entries go on every write, and the
oldest goes when the cap is reached.

Serving is plain ASGI over ``uvicorn`` rather than a web framework, for the
reason ``client.py`` gives for using the standard library: every package in the
runtime tree is one the operator has to audit, and a router buys nothing for
eleven paths that all end in the same call.
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import parse_qs

from config.constants.surfaces import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_CONSOLE_PORT,
    NINJASRE_ENDPOINT_ENV,
)
from platform.observability.logging import get_logger
from surfaces.console.app import STATUS_OK, STATUS_SEE_OTHER, Console
from surfaces.console.client import ConsoleApiError, ConsoleClient, UrllibTransport
from surfaces.console.pages.auth import sign_in_page
from surfaces.console.pages.shell import PageContext
from surfaces.console.permissions import Viewer
from surfaces.console.session import SIGN_IN_PATH, Session, sign_in

_LOGGER = get_logger(__name__)

#: The cookie holding the handle to a session. ``__Host-`` is deliberately not
#: used: the prefix requires ``Secure``, and a deployment reached over plain
#: HTTP on a private network — which the dev profile is — would then have no
#: session at all rather than an insecure one.
SESSION_COOKIE: Final = "ninjasre_console_session"

#: How many sessions the process holds before it starts dropping the oldest.
#: A console is a handful of on-call engineers, not a public site; the cap is
#: here so a stream of sign-in attempts costs bounded memory, not to size for
#: real use.
MAX_SESSIONS: Final = 512

#: Where a sign-out sends the browser.
SIGN_OUT_PATH: Final = "/sign-out"

#: Answered without touching the API, because liveness asks whether this process
#: should be restarted and no restart has ever fixed an unreachable dependency.
LIVENESS_PATH: Final = "/health/live"

#: Answered by asking the API, because a console that cannot reach the
#: deployment has nothing to show and should leave the load balancer.
READINESS_PATH: Final = "/health/ready"

STATUS_SERVICE_UNAVAILABLE: Final = 503

#: The one field the sign-in form posts.
TOKEN_FIELD: Final = "token"

#: What a form submission is allowed to weigh. A token is under a kilobyte; the
#: bound is what stops an unauthenticated POST from being an allocation
#: primitive.
MAX_FORM_BYTES: Final = 8 * 1024

Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class SessionStore:
    """The sessions this process is holding, by handle.

    In-process, and that is a property rather than a limitation to fix later:
    two console replicas behind a load balancer want sticky sessions or a shared
    store, and choosing between those is a deployment decision that a default
    should not make silently. One replica is what the standard profile runs.
    """

    sessions: dict[str, Session] = field(default_factory=dict)
    capacity: int = MAX_SESSIONS

    def get(self, handle: str) -> Session:
        """Return the session ``handle`` names, or an anonymous one."""
        if not handle:
            return Session()
        found = self.sessions.get(handle)
        if found is None:
            return Session()
        if _is_spent(found):
            self.sessions.pop(handle, None)
            return Session()
        return found

    def put(self, handle: str, session: Session) -> str:
        """Store ``session`` under ``handle``, minting one when there is none."""
        self._sweep()
        key = handle or secrets.token_urlsafe(32)
        self.sessions[key] = session
        return key

    def drop(self, handle: str) -> None:
        """Forget the session ``handle`` names. Idempotent."""
        self.sessions.pop(handle, None)

    def _sweep(self) -> None:
        """Drop what is spent, then the oldest if the store is still full."""
        for key in [key for key, held in self.sessions.items() if _is_spent(held)]:
            self.sessions.pop(key, None)
        while len(self.sessions) >= self.capacity:
            self.sessions.pop(next(iter(self.sessions)))


def _is_spent(session: Session) -> bool:
    """Return whether a stored session is no longer worth holding.

    ``Session.is_expired`` calls an anonymous session expired, which is right
    for "may this make a request" and wrong for "may this be thrown away": the
    anonymous session created when a visitor is bounced to sign-in is carrying
    the path they were going to, and discarding it loses the redirect that makes
    an alert link land on the run.
    """
    if session.is_authenticated:
        return session.is_expired()
    return not session.intended_path


def _is_worth_storing(session: Session) -> bool:
    """Return whether a session carries anything the next request needs.

    Without this, every anonymous page view mints a store entry and a cookie —
    so one crawler evicts every real session the process is holding.
    """
    return not _is_spent(session)


@dataclass(slots=True)
class ConsoleServer:
    """The ASGI application the console image runs."""

    client: ConsoleClient
    api_base: str = ""
    store: SessionStore = field(default_factory=SessionStore)
    secure_cookies: bool = False

    async def __call__(self, scope: MutableMapping[str, Any], receive: Receive, send: Send) -> None:
        """Answer one ASGI event, ignoring anything that is not an HTTP request."""
        if scope["type"] == "lifespan":
            await _drain_lifespan(receive, send)
            return
        if scope["type"] != "http":
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/")) or "/"
        handle = _cookie(scope, SESSION_COOKIE)

        if path == LIVENESS_PATH:
            await _text(send, STATUS_OK, "live")
            return
        if path == READINESS_PATH:
            await self._readiness(send)
            return
        if path == SIGN_OUT_PATH:
            self.store.drop(handle)
            await _redirect(send, SIGN_IN_PATH, cookie=self._expiring_cookie())
            return
        if path == SIGN_IN_PATH and method == "POST":
            await self._sign_in(receive, send, handle)
            return

        await self._page(scope, send, path, handle)

    # --- The three things a renderer cannot do --------------------------------

    async def _sign_in(self, receive: Receive, send: Send, handle: str) -> None:
        """Exchange the posted token for a session, or re-present the form.

        The token is verified by asking the API who it belongs to. A token that
        cannot describe its own principal is a token that does not work, and
        finding that out here is better than finding it out on the first page
        that needed a permission.
        """
        form = _form(await _body(receive))
        token = form.get(TOKEN_FIELD, "")
        intended = self.store.get(handle).intended_path

        try:
            principal = await self.client.with_token(token).principal()
        except ConsoleApiError as failure:
            _LOGGER.info("console.sign_in_refused", status=failure.status)
            await self._present_sign_in(send, failed=True)
            return

        self.store.drop(handle)
        established = self.store.put("", sign_in(token, principal, intended_path=intended))
        _LOGGER.info("console.signed_in", principal=str(principal.get("principal_id", "")))
        await _redirect(send, intended or "/runs", cookie=self._session_cookie(established))

    async def _page(
        self, scope: MutableMapping[str, Any], send: Send, path: str, handle: str
    ) -> None:
        """Render one path for whoever the handle says is looking."""
        query = _query(scope)
        console = Console(client=self.client, api_base=self.api_base)
        answer = await console.render(path, self.store.get(handle), query=query)

        cookie = ""
        if _is_worth_storing(answer.session):
            cookie = self._session_cookie(self.store.put(handle, answer.session))

        if answer.is_redirect:
            await _redirect(send, answer.location, cookie=cookie)
            return
        await _html(send, answer.status, answer.html(), cookie=cookie)

    async def _readiness(self, send: Send) -> None:
        """Report whether the console can reach the deployment it fronts."""
        try:
            await self.client.health()
        except ConsoleApiError as failure:
            await _text(send, STATUS_SERVICE_UNAVAILABLE, f"the API is unreachable: {failure}")
            return
        await _text(send, STATUS_OK, "ready")

    async def _present_sign_in(self, send: Send, *, failed: bool) -> None:
        """Render the sign-in page outside the router, for a refused sign-in."""
        document = sign_in_page(PageContext(viewer=Viewer(), path=SIGN_IN_PATH), failed=failed)
        await _html(send, STATUS_OK, document.render(), cookie="")

    # --- Cookies ---------------------------------------------------------------

    def _session_cookie(self, handle: str) -> str:
        """Return the ``Set-Cookie`` value carrying ``handle``."""
        parts = [
            f"{SESSION_COOKIE}={handle}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.secure_cookies:
            parts.append("Secure")
        return "; ".join(parts)

    def _expiring_cookie(self) -> str:
        """Return the ``Set-Cookie`` value that removes the session cookie."""
        return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


# --- ASGI plumbing -------------------------------------------------------------


async def _drain_lifespan(receive: Receive, send: Send) -> None:
    """Acknowledge startup and shutdown. The console owns no pool to open."""
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _body(receive: Receive) -> bytes:
    """Return the request body, refusing to accumulate more than the bound."""
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = bytes(message.get("body", b""))
        size += len(chunk)
        if size > MAX_FORM_BYTES:
            return b""
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _form(body: bytes) -> dict[str, str]:
    """Return the fields of a URL-encoded submission, first value per name."""
    parsed = parse_qs(body.decode(errors="replace"), keep_blank_values=True)
    return {name: values[0] for name, values in parsed.items() if values}


def _query(scope: Mapping[str, Any]) -> dict[str, str]:
    """Return the request's query parameters, first value per name."""
    raw = bytes(scope.get("query_string", b"")).decode(errors="replace")
    return {name: values[0] for name, values in parse_qs(raw).items() if values}


def _cookie(scope: Mapping[str, Any], name: str) -> str:
    """Return one cookie's value from the request headers, or the empty string."""
    for key, value in _headers(scope):
        if key != "cookie":
            continue
        for pair in value.split(";"):
            found, _, held = pair.strip().partition("=")
            if found == name:
                return held
    return ""


def _headers(scope: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """Return the request headers, lowercased and decoded."""
    for name, value in scope.get("headers", ()):
        yield name.decode().lower(), value.decode()


async def _html(send: Send, status: int, body: str, *, cookie: str) -> None:
    """Send one HTML response."""
    await _respond(send, status, body.encode(), "text/html; charset=utf-8", cookie)


async def _text(send: Send, status: int, body: str) -> None:
    """Send one plain-text response."""
    await _respond(send, status, body.encode(), "text/plain; charset=utf-8", "")


async def _redirect(send: Send, location: str, *, cookie: str) -> None:
    """Send a see-other redirect to ``location``."""
    await _respond(send, STATUS_SEE_OTHER, b"", "text/plain; charset=utf-8", cookie, location)


async def _respond(
    send: Send,
    status: int,
    body: bytes,
    content_type: str,
    cookie: str,
    location: str = "",
) -> None:
    """Send one complete response.

    The security headers are set here rather than per route, so a route added
    tomorrow carries them by having been added. ``frame-ancestors 'none'``
    matters most: a console with approval buttons on it is worth clickjacking.
    """
    headers = [
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(body)).encode()),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
        (
            b"content-security-policy",
            b"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            b"frame-ancestors 'none'; base-uri 'none'",
        ),
    ]
    if location:
        headers.append((b"location", location.encode()))
    if cookie:
        headers.append((b"set-cookie", cookie.encode()))

    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


# --- The process ---------------------------------------------------------------


def build_server(environ: Mapping[str, str] | None = None) -> ConsoleServer:
    """Return the console this deployment's configuration describes."""
    import os

    source = dict(environ if environ is not None else os.environ)
    endpoint = source.get(NINJASRE_ENDPOINT_ENV, "").strip() or (
        f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}"
    )
    return ConsoleServer(
        client=ConsoleClient(transport=UrllibTransport(base_url=endpoint)),
        api_base=endpoint,
        secure_cookies=endpoint.startswith("https://"),
    )


def main(argv: list[str] | None = None) -> int:
    """Serve the console. Returns the process exit code."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="ninjasre-console", description=__doc__)
    parser.add_argument("--host", default=DEFAULT_API_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_CONSOLE_PORT)
    arguments = parser.parse_args(argv)

    server = build_server()
    _LOGGER.info("console.serving", endpoint=server.api_base, port=arguments.port)
    print(  # noqa: T201 — an operator is reading a terminal
        f"NinjaSRE console on http://{arguments.host}:{arguments.port}, fronting {server.api_base}",
        file=sys.stderr,
    )
    uvicorn.run(server, host=arguments.host, port=arguments.port, log_config=None)
    return 0


if __name__ == "__main__":  # pragma: no cover — the container's entrypoint
    raise SystemExit(main())


__all__ = [
    "LIVENESS_PATH",
    "MAX_FORM_BYTES",
    "MAX_SESSIONS",
    "READINESS_PATH",
    "SESSION_COOKIE",
    "SIGN_OUT_PATH",
    "STATUS_SERVICE_UNAVAILABLE",
    "TOKEN_FIELD",
    "ConsoleServer",
    "SessionStore",
    "build_server",
    "main",
]
