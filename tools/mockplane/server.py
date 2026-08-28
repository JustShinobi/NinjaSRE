"""The mock: the gateway's paths, methods and statuses, served from the fixture set.

It is an ASGI application with no framework under it, for the same reason the
credential proxy is: the whole surface is "match a path, apply an override,
write a body", and a routing library would add a dependency and a second place
for a path to be spelled.

Four behaviours are the point of it existing at all.

**Streaming**, with a controllable event rate, a controllable mid-stream
disconnection, and replay from ``Last-Event-ID`` on reconnect. Those are the
three things a live-transcript reducer has to survive, and they cannot be
exercised against a static file.

**Injected failure**, per endpoint: slow, refused, 500, 403, 404, truncated. A
panel's error state is only reviewable when the panel actually fails.

**Session-scoped writes.** An approval approved here is approved on the next
read, so optimistic updates and the approval flow can be exercised — and the
session resets, so one test cannot leave state for the next.

**No outbound network, ever.** Not "does not happen to make one": a request that
tried would fail loudly rather than falling through to whatever real service was
listening.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from config.constants.fixtures import (
    MOCK_DEPLOYMENT_STREAM_MAX_SECONDS,
    MOCK_DEPLOYMENT_STREAM_POLL_SECONDS,
    MOCK_SERVER_DEFAULT_PORT,
    MOCK_STREAM_EVENTS_PER_SECOND,
)
from config.constants.security import (
    LOCAL_ACCOUNT_DEFAULT_PASSWORD,
    LOCAL_ACCOUNT_USERNAME,
)
from tools.mockplane.endpoints import ConsoleEndpoint, match_request
from tools.mockplane.records import CapturedRecord, dumps
from tools.mockplane.scenarios import Override, Scenario, ScenarioData, arguments_key
from tools.mockplane.scenarios import load as load_scenario

#: The endpoint whose answer depends on the request body rather than on a
#: fixture lookup. Named here so the branch in ``answer`` reads as a rule rather
#: than as a string comparison somebody will wonder about.
SIGN_IN_SLUG: Final = "sign-in"


def _credential_accepted(body: Mapping[str, Any] | None) -> bool:
    """Return whether this sign-in body carries the demo profile's credential.

    The mock stands in for a deployment running the demo profile, and that
    profile's account is the one this project ships. Anything else is refused,
    exactly as the gateway refuses it.
    """
    if body is None:
        return False
    return (
        body.get("username") == LOCAL_ACCOUNT_USERNAME
        and body.get("password") == LOCAL_ACCOUNT_DEFAULT_PASSWORD
    )


#: The header a client presents to keep its writes separate from another's.
SESSION_HEADER: Final = "x-mockplane-session"

#: The session a client that names none gets.
DEFAULT_SESSION: Final = "default"

#: Where the mock's own telemetry answers. Resolved before the gateway's route
#: matching and never handed to it, so a caller asking "did the console reach
#: you" cannot collide with a path the console itself requests — no served
#: endpoint starts with two underscores, and this one is not in the fixture
#: set or the production binary either.
CONTROL_PATH_PREFIX: Final = "/__mockplane__"

#: The one control route this mock answers: how many times each route has
#: been requested, in the caller's own session. What proves a page was served
#: live rather than from a cache that never reached this process — a count
#: that goes up between two reads is a request that happened.
REQUEST_COUNTS_PATH: Final = f"{CONTROL_PATH_PREFIX}/requests"

#: How many events the stream emits before it drops the connection, when a
#: caller asks it to drop one. Far enough in that a reducer has state to lose.
DEFAULT_DISCONNECT_AFTER: Final = 5

Scope = MutableMapping[str, Any]
Receive = Callable[[], Any]
Send = Callable[[Mapping[str, Any]], Any]


class OutboundRequestRefused(RuntimeError):
    """Something tried to open a connection to the outside world."""


@contextlib.contextmanager
def no_outbound_network() -> Iterator[None]:
    """Make any outbound connection raise for the duration of the block.

    Loud rather than silent, and total rather than per-library: a mock that
    quietly fell through to a real service would produce a green test suite
    whose green meant nothing.
    """
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def refuse(*positional: Any, **named: Any) -> Any:
        """Refuse, naming the address, whichever calling convention was used.

        One function for both hooks: ``socket.connect`` is a bound method whose
        second argument is the address and ``create_connection`` takes it first,
        and a signature that named them separately would be two functions
        saying the same thing.
        """
        candidates = [*positional[1:], *positional[:1], *named.values()]
        address = next((item for item in candidates if isinstance(item, tuple | str)), "somewhere")
        raise OutboundRequestRefused(
            f"the mock data plane refuses outbound connections; something tried to reach "
            f"{address!r}. Nothing in a fixture-served test may leave the machine."
        )

    # Replacing a method on a stdlib class is what this does, and mypy is right
    # that it is unusual. It is also the only way to make the refusal total
    # rather than per-library: every HTTP client in the tree ends here.
    socket.socket.connect = refuse  # type: ignore[method-assign]
    socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.create_connection = original_create


#: The epoch every mock process's deployment stream reports itself as. A fixed
#: string rather than one generated at start-up: the real gateway's epoch
#: changes across process restarts and a reconnecting client is expected to
#: notice, but the mock never restarts mid-scenario, and a fixed epoch is one
#: a fixture or a test can name without reading it back first.
DEPLOYMENT_STREAM_EPOCH: Final = "mockplane"


@dataclass(slots=True)
class Session:
    """One client's writes, on top of the scenario's records."""

    written: dict[tuple[str, str], CapturedRecord] = field(default_factory=dict)
    #: The deployment-scoped channel's events this session has published,
    #: oldest first. Session-scoped rather than shared across sessions for the
    #: same reason `written` is: a test's writes must not leak into another
    #: test's mock, and a session that reset must start this empty too.
    deployment_events: list[dict[str, Any]] = field(default_factory=list)

    def clear(self) -> None:
        """Forget everything this session wrote."""
        self.written.clear()
        self.deployment_events.clear()


@dataclass(frozen=True, slots=True)
class StreamControl:
    """How the stream behaves for one run of the mock."""

    events_per_second: float = MOCK_STREAM_EVENTS_PER_SECOND
    #: Drop the connection after this many events. ``0`` never drops.
    disconnect_after: int = 0
    #: Whether a reconnection that presents no cursor replays from the start.
    replay_from_start: bool = True


@dataclass(frozen=True, slots=True)
class Answer:
    """One prepared answer, before it is written to the wire."""

    status: int
    body: bytes
    content_type: str = "application/json"
    latency_ms: int = 0
    refuse: bool = False


class MockPlane:
    """The ASGI application. One instance per scenario, reusable across requests."""

    def __init__(
        self,
        data: ScenarioData,
        *,
        stream: StreamControl | None = None,
    ) -> None:
        self._data = data
        self._stream = stream if stream is not None else StreamControl()
        self._sessions: dict[str, Session] = {}
        #: How many times each ``"METHOD path"`` has actually reached this
        #: process, per session. Distinct from anything the fixture set
        #: describes: this is telemetry about requests, not an answer to one.
        self._counts: dict[str, dict[str, int]] = {}

    # --- What it is serving ---------------------------------------------------

    @property
    def scenario(self) -> Scenario:
        """Return the scenario this instance serves."""
        return self._data.scenario

    def with_override(self, override: Override) -> MockPlane:
        """Return a mock serving the same records with ``override`` on top.

        The composition a test uses to take ``populated`` and make one endpoint
        fail, without a new scenario and without touching the console.
        """
        return MockPlane(
            ScenarioData(
                scenario=self._data.scenario.with_override(override),
                records=self._data.records,
            ),
            stream=self._stream,
        )

    def with_stream(self, stream: StreamControl) -> MockPlane:
        """Return a mock serving the same records with a different stream behaviour."""
        return MockPlane(self._data, stream=stream)

    def session(self, name: str = DEFAULT_SESSION) -> Session:
        """Return one client's session, creating it on first sight."""
        return self._sessions.setdefault(name, Session())

    def reset(self) -> None:
        """Forget every session's writes and request counts. What a test does between cases."""
        self._sessions.clear()
        self._counts.clear()

    def request_counts(self, session: str = DEFAULT_SESSION) -> dict[str, int]:
        """Return how many times each route has been requested, in ``session``.

        Keyed by ``"METHOD path"`` of the request as it actually arrived — the
        gateway's own path, never the fixture slug — so the count answers
        exactly the question a caller asks the control route: did a request
        for this route reach the process at all.
        """
        return dict(self._counts.get(session, {}))

    def _record_request(self, method: str, path: str, session: str) -> None:
        """Count one request toward ``session``'s tally, before it is answered.

        Recorded here — ahead of route matching, fixture lookup and any
        override — so the count reflects that a request *arrived*, which is
        the only claim this feature's dynamism tests make. Whether the mock
        could answer it is a separate fact this counter does not carry.
        """
        bucket = self._counts.setdefault(session, {})
        key = f"{method} {path}"
        bucket[key] = bucket.get(key, 0) + 1

    # --- Answering ------------------------------------------------------------

    def answer(
        self,
        method: str,
        path: str,
        *,
        session: str = DEFAULT_SESSION,
        body: Mapping[str, Any] | None = None,
    ) -> Answer:
        """Return the answer to one request, without any transport involved.

        The programmatic entry point: a test drives this directly, and the ASGI
        application below is a thin shell over it, so the two can never disagree
        about what the mock would have said.
        """
        resolved = match_request(method, path)
        if resolved is None:
            return Answer(
                404, self._problem(f"{method} {path} is not an endpoint this mock serves")
            )
        endpoint, arguments = resolved

        # Signing in is the one endpoint whose answer depends on what was sent
        # rather than on which record was asked for. A mock that accepted every
        # passphrase would leave the console's refusal path — the error the form
        # renders — with nothing that ever exercises it.
        if endpoint.slug == SIGN_IN_SLUG and not _credential_accepted(body):
            return Answer(401, self._problem("the credential was not accepted"))

        override = self._data.scenario.override_for(endpoint.slug)
        if override is not None and override.refuse:
            return Answer(0, b"", refuse=True, latency_ms=override.latency_ms)

        record = self._lookup(endpoint, arguments, session)
        if record is None:
            return Answer(
                404,
                self._problem(f"{endpoint.slug} has no fixture for {arguments or 'no arguments'}"),
                latency_ms=override.latency_ms if override else 0,
            )

        if endpoint.method != "GET":
            self._apply_write(endpoint, arguments, record, session, body)

        payload = record.body
        status = record.status
        latency = 0
        if override is not None:
            latency = override.latency_ms
            if override.status is not None:
                status = override.status
                payload = self._problem_body(status, endpoint)
            elif override.body is not None:
                payload = override.body
            elif override.empty:
                payload = _emptied(record.body, endpoint)

        encoded = dumps(payload).encode()
        if override is not None and override.truncate and override.status is None:
            encoded = encoded[: max(len(encoded) // 2, 1)]
        return Answer(status, encoded, latency_ms=latency)

    def events_for(self, run_id: str, after: int = -1) -> tuple[dict[str, Any], ...]:
        """Return the events of one run, resuming after a sequence number."""
        record = self._data.lookup("run-stream", {"run_id": run_id})
        if record is None or not isinstance(record.body, Mapping):
            return ()
        raw = record.body.get("events")
        if not isinstance(raw, list):
            return ()
        return tuple(
            event
            for event in raw
            if isinstance(event, dict) and int(event.get("sequence", -1)) > after
        )

    def deployment_events_for(self, session: str, *, after: int = -1) -> tuple[dict[str, Any], ...]:
        """Return this session's deployment-channel events, resuming after a sequence number.

        Session-scoped, unlike `events_for`: the deployment channel has no
        fixture recording to replay — every event on it exists because
        `_publish_deployment_event` put it there, in reaction to a write this
        session made, and a session that never wrote sees nothing here.
        """
        return tuple(
            event
            for event in self.session(session).deployment_events
            if int(event.get("sequence", -1)) > after
        )

    def _publish_deployment_event(
        self, session: str, *, scope: str, kind: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Append one deployment-channel event to ``session`` and return it.

        The allowlist FR-002 declares for the real channel is not re-enforced
        here: this is a fixture-authoring seam, not the contract under test —
        `tests/contract/gateway/test_deployment_stream.py` holds the real
        broker to that allowlist directly.
        """
        events = self.session(session).deployment_events
        event = {
            "scope": scope,
            "kind": kind,
            "sequence": len(events) + 1,
            "occurred_at": datetime.now(UTC).isoformat(),
            "payload": dict(payload),
        }
        events.append(event)
        return event

    # --- The ASGI shell -------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one connection."""
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":  # pragma: no cover — nothing else is served
            return

        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", "/"))
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        session = headers.get(SESSION_HEADER, DEFAULT_SESSION)

        if path.startswith(CONTROL_PATH_PREFIX):
            await self._serve_control(method, path, session, send)
            return

        self._record_request(method, path, session)

        resolved = match_request(method, path)
        if resolved is not None and resolved[0].streaming:
            # The deployment channel is not scoped by a run_id, carries
            # several scopes' events and uses an epoch:sequence cursor
            # instead of `_serve_stream`'s plain integer — declaring it
            # streaming in the catalogue is not sufficient on its own, so it
            # gets its own serving path rather than falling into the one
            # built for a single run's canned replay.
            if resolved[0].slug == "deployment-stream":
                await self._serve_deployment_stream(resolved[0], headers, session, send)
            else:
                await self._serve_stream(resolved[0], resolved[1], headers, send)
            return

        payload = await self._read_body(receive)
        answer = self.answer(method, path, session=session, body=payload)
        if answer.latency_ms:
            await asyncio.sleep(answer.latency_ms / 1000.0)
        if answer.refuse:
            # No response at all: the connection closes with nothing on it,
            # which is what a refused endpoint looks like from a browser.
            await send({"type": "http.response.start", "status": 502, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
        await send(
            {
                "type": "http.response.start",
                "status": answer.status,
                "headers": [
                    (b"content-type", answer.content_type.encode()),
                    (b"content-length", str(len(answer.body)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": answer.body})

    async def _serve_control(self, method: str, path: str, session: str, send: Send) -> None:
        """Answer the mock's own telemetry route, never a fixture-served one.

        Outside the gateway's path space by construction — ``CONTROL_PATH_PREFIX``
        is checked before ``match_request`` ever runs, so this can never shadow
        or be shadowed by an endpoint the fixture set declares.
        """
        if method == "GET" and path == REQUEST_COUNTS_PATH:
            body = dumps({"session": session, "counts": self.request_counts(session)}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self._problem(f"{method} {path} is not a control route this mock serves"),
            }
        )

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _serve_stream(
        self,
        endpoint: ConsoleEndpoint,
        arguments: Mapping[str, str],
        headers: Mapping[str, str],
        send: Send,
    ) -> None:
        run_id = arguments.get("run_id", "")
        after = _sequence_of(headers.get("last-event-id", ""))
        override = self._data.scenario.override_for(endpoint.slug)
        if override is not None and override.status is not None:
            body = self._problem_body(override.status, endpoint)
            encoded = dumps(body).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": override.status,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": encoded})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        async for frame in self.stream_frames(run_id, after=after):
            await send({"type": "http.response.body", "body": frame, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def stream_frames(self, run_id: str, *, after: int = -1) -> AsyncIterator[bytes]:
        """Yield the run's events as server-sent-event frames, at the declared rate.

        Stops early when the stream control says to drop the connection, which
        is how a mid-stream disconnection becomes a test rather than a network
        fault somebody has to arrange.
        """
        delay = 0.0 if self._stream.events_per_second <= 0 else 1.0 / self._stream.events_per_second
        for emitted, event in enumerate(self.events_for(run_id, after=after)):
            if self._stream.disconnect_after and emitted >= self._stream.disconnect_after:
                return
            yield _sse_frame(event)
            if delay:
                await asyncio.sleep(delay)

    async def _serve_deployment_stream(
        self,
        endpoint: ConsoleEndpoint,
        headers: Mapping[str, str],
        session: str,
        send: Send,
        *,
        max_seconds: float = MOCK_DEPLOYMENT_STREAM_MAX_SECONDS,
        poll_seconds: float = MOCK_DEPLOYMENT_STREAM_POLL_SECONDS,
    ) -> None:
        """Serve the deployment-wide channel: no run_id, several scopes, a live poll.

        Genuinely live, unlike `_serve_stream`'s canned replay: a write this
        same session makes through `answer` while the connection is open —
        `_apply_write`'s `investigation-start` case, for one — reaches this
        generator on its next poll, which is what lets an acceptance spec
        start an investigation through the UI on one page and see the
        deployment channel carry it to another. Bounded by
        `MOCK_DEPLOYMENT_STREAM_MAX_SECONDS` because this ASGI shell is never
        handed `receive`, so it has no transport-level signal that the client
        went away — see that constant's own docstring.
        """
        epoch, after = _deployment_cursor_of(headers.get("last-event-id", ""))
        override = self._data.scenario.override_for(endpoint.slug)
        if override is not None and override.status is not None:
            body = self._problem_body(override.status, endpoint)
            encoded = dumps(body).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": override.status,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": encoded})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )

        if epoch != "" and epoch != DEPLOYMENT_STREAM_EPOCH:
            # A cursor from a foreign epoch: the same confession the real
            # broker makes, and nothing this mock can honestly replay past.
            await send(
                {
                    "type": "http.response.body",
                    "body": _deployment_sse_frame({"kind": "resync", "sequence": 0, "payload": {}}),
                    "more_body": True,
                }
            )
            after = -1

        emitted = 0
        deadline = time.monotonic() + max_seconds
        while time.monotonic() < deadline:
            for event in self.deployment_events_for(session, after=after):
                if self._stream.disconnect_after and emitted >= self._stream.disconnect_after:
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
                await send(
                    {
                        "type": "http.response.body",
                        "body": _deployment_sse_frame(event),
                        "more_body": True,
                    }
                )
                after = int(event["sequence"])
                emitted += 1
            await asyncio.sleep(poll_seconds)
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    # --- Internals ------------------------------------------------------------

    def _lookup(
        self, endpoint: ConsoleEndpoint, arguments: Mapping[str, str], session: str
    ) -> CapturedRecord | None:
        written = self._sessions.get(session)
        if written is not None:
            found = written.written.get((endpoint.slug, arguments_key(arguments)))
            if found is None:
                found = written.written.get((endpoint.slug, ""))
            if found is not None:
                return found
        return self._data.lookup(endpoint.slug, arguments)

    def _apply_write(
        self,
        endpoint: ConsoleEndpoint,
        arguments: Mapping[str, str],
        answer: CapturedRecord,
        session: str,
        body: Mapping[str, Any] | None,
    ) -> None:
        """Reflect one write in what this session reads next.

        Deliberately narrow: each write updates the reads a person would look at
        immediately afterwards, and nothing else. A mock that tried to be a
        database would be a second implementation of the platform, and the first
        time the two disagreed the console would be built against the wrong one.
        """
        store = self.session(session)

        def amend(slug: str, key: Mapping[str, str], change: Callable[[Any], Any]) -> None:
            current = self._lookup_slug(slug, key, session)
            if current is None:
                return
            store.written[(slug, arguments_key(key))] = current.with_body(
                change(json.loads(json.dumps(current.body)))
            )

        match endpoint.slug:
            case "investigation-start":
                started = answer.body if isinstance(answer.body, Mapping) else {}
                amend("runs", {}, lambda document: _prepend(document, "runs", dict(started)))
                run_id = str(started.get("run_id", ""))
                if run_id:
                    self._publish_deployment_event(
                        session, scope="run", kind="run_started", payload={"run_id": run_id}
                    )
            case "investigation-cancel":
                run_id = arguments.get("run_id", "")
                amend(
                    "runs",
                    {},
                    lambda document: _patch_in(document, "runs", "run_id", run_id, "cancelling"),
                )
            case "interaction-answer" | "interaction-approve" | "interaction-reject":
                closed = answer.body if isinstance(answer.body, Mapping) else {}
                run_id = str(closed.get("run_id", ""))
                identifier = arguments.get("interaction_id", "")
                reason = str(closed.get("reason", "closed"))
                amend(
                    "interactions",
                    {"run_id": run_id},
                    lambda document: _close_interaction(document, identifier, reason),
                )
            case "config-write":
                node_id = arguments.get("node_id", "")
                patch = dict(body.get("patch", {})) if isinstance(body, Mapping) else {}
                amend(
                    "config-effective",
                    {"node_id": node_id},
                    lambda document: _merge_values(document, patch, node_id),
                )
            case "token-create":
                issued = answer.body.get("token") if isinstance(answer.body, Mapping) else None
                if isinstance(issued, Mapping):
                    amend(
                        "tokens",
                        {},
                        lambda document: _prepend(document, "tokens", dict(issued)),
                    )
            case "token-revoke":
                revoked = list(body.get("token_ids", [])) if isinstance(body, Mapping) else []
                amend("tokens", {}, lambda document: _revoke(document, revoked))
            case "approval-rollback":
                identifier = arguments.get("approval_id", "")
                amend(
                    "approvals",
                    {},
                    lambda document: _patch_in(
                        document, "approvals", "approval_id", identifier, "rolled_back"
                    ),
                )
            case _:
                return

    def _lookup_slug(
        self, slug: str, arguments: Mapping[str, str], session: str
    ) -> CapturedRecord | None:
        written = self._sessions.get(session)
        if written is not None:
            found = written.written.get((slug, arguments_key(arguments)))
            if found is not None:
                return found
        return self._data.lookup(slug, arguments)

    async def _read_body(self, receive: Receive) -> Mapping[str, Any] | None:
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b"") or b"")
            if not message.get("more_body"):
                break
        raw = b"".join(chunks)
        if not raw.strip():
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _problem(self, detail: str) -> bytes:
        return dumps({"detail": detail}).encode()

    def _problem_body(self, status: int, endpoint: ConsoleEndpoint) -> dict[str, Any]:
        reasons = {
            403: "you hold no permission for this",
            404: "there is no such thing",
            500: "the deployment is unhappy",
            502: "the deployment did not answer",
            503: "the deployment is not accepting requests",
        }
        return {
            "detail": f"{endpoint.method} {endpoint.path}: "
            f"{reasons.get(status, 'the deployment refused')}"
        }


def _sse_frame(event: Mapping[str, Any]) -> bytes:
    """Return one event as the ``id``/``event``/``data`` frame the API sends."""
    payload = json.dumps(event, separators=(",", ":"), sort_keys=True)
    return (
        f"id: {event.get('run_id', '')}:{event.get('sequence', 0)}\n"
        f"event: {event.get('kind', '')}\n"
        f"data: {payload}\n\n"
    ).encode()


def _sequence_of(cursor: str) -> int:
    run_id, separator, raw = cursor.rpartition(":")
    if not separator or not run_id:
        return -1
    try:
        return int(raw)
    except ValueError:
        return -1


def _deployment_sse_frame(event: Mapping[str, Any]) -> bytes:
    """Return one deployment-channel event as an ``id``/``event``/``data`` frame.

    ``id`` is ``epoch:sequence`` — always this mock's own fixed epoch, never
    a run id, because the deployment channel has no single run every frame is
    a position within.
    """
    payload = json.dumps(event, separators=(",", ":"), sort_keys=True)
    return (
        f"id: {DEPLOYMENT_STREAM_EPOCH}:{event.get('sequence', 0)}\n"
        f"event: {event.get('kind', '')}\n"
        f"data: {payload}\n\n"
    ).encode()


def _deployment_cursor_of(cursor: str) -> tuple[str, int]:
    """Return the ``(epoch, sequence)`` a ``Last-Event-ID`` header spells.

    ``("", -1)`` for an absent or unparsable header, which a first connection
    presents no cursor at all and reads the same way a malformed one does:
    nothing to resume from.
    """
    epoch, separator, raw = cursor.rpartition(":")
    if not separator or not epoch:
        return "", -1
    try:
        return epoch, int(raw)
    except ValueError:
        return "", -1


def _emptied(body: Any, endpoint: ConsoleEndpoint) -> Any:
    """Return ``body`` with its records removed and its shape kept."""
    if not isinstance(body, Mapping):
        return body
    emptied = dict(body)
    for key, value in body.items():
        if isinstance(value, list):
            emptied[key] = []
        elif key == "total" and isinstance(value, int):
            emptied[key] = 0
    if endpoint.records_key and endpoint.records_key in emptied:
        emptied[endpoint.records_key] = []
    return emptied


def _prepend(document: Any, key: str, item: Mapping[str, Any]) -> Any:
    if isinstance(document, dict) and isinstance(document.get(key), list):
        document[key] = [dict(item), *document[key]]
    return document


def _patch_in(document: Any, key: str, id_key: str, identifier: str, status: str) -> Any:
    if isinstance(document, dict) and isinstance(document.get(key), list):
        for item in document[key]:
            if isinstance(item, dict) and item.get(id_key) == identifier:
                item["state" if "state" in item else "status"] = status
    return document


def _close_interaction(document: Any, identifier: str, reason: str) -> Any:
    if isinstance(document, dict) and isinstance(document.get("interactions"), list):
        for item in document["interactions"]:
            if isinstance(item, dict) and item.get("interaction_id") == identifier:
                item["is_open"] = False
                item["reason"] = reason
    return document


def _merge_values(document: Any, patch: Mapping[str, Any], node_id: str) -> Any:
    if isinstance(document, dict) and isinstance(document.get("values"), dict):
        document["values"].update(patch)
        provenance = document.get("provenance")
        if isinstance(provenance, dict):
            for key in patch:
                provenance[key] = node_id
    return document


def _revoke(document: Any, token_ids: list[Any]) -> Any:
    if isinstance(document, dict) and isinstance(document.get("tokens"), list):
        for item in document["tokens"]:
            if isinstance(item, dict) and item.get("token_id") in token_ids:
                item["revoked"] = True
    return document


def build_mock(
    scenario: str = "",
    root: Path | None = None,
    *,
    stream: StreamControl | None = None,
    overrides: tuple[Override, ...] = (),
) -> MockPlane:
    """Return a mock serving ``scenario``. The programmatic entry point for tests."""
    data = load_scenario(scenario, root)
    for override in overrides:
        data = ScenarioData(scenario=data.scenario.with_override(override), records=data.records)
    return MockPlane(data, stream=stream)


def serve(
    scenario: str = "",
    *,
    host: str = "127.0.0.1",
    port: int = MOCK_SERVER_DEFAULT_PORT,
    root: Path | None = None,
) -> None:  # pragma: no cover — the development loop's entry point
    """Serve ``scenario`` on ``host``:``port`` until interrupted."""
    import uvicorn

    uvicorn.run(build_mock(scenario, root), host=host, port=port, log_config=None)


__all__ = [
    "CONTROL_PATH_PREFIX",
    "DEFAULT_DISCONNECT_AFTER",
    "DEFAULT_SESSION",
    "DEPLOYMENT_STREAM_EPOCH",
    "REQUEST_COUNTS_PATH",
    "SESSION_HEADER",
    "Answer",
    "MockPlane",
    "OutboundRequestRefused",
    "Session",
    "StreamControl",
    "build_mock",
    "no_outbound_network",
    "serve",
]
