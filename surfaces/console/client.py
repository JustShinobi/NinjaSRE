"""The console's one way of reaching anything: the REST API, over a transport.

Every method here is the same three steps — request, status, payload — and the
only thing that differs between two screens is which path and which shape. There
is no method that computes, filters, merges, or decides: where a screen needs
something derived, the derivation is a route (``POST /v1/config/{id}/preview``
is the clearest case), because the CLI and the chat surfaces need the same
answer and three implementations of it would be three answers.

``Transport`` is a protocol for the same reason ``surfaces/cli/client.py``
states one: it is the seam. Production gets ``UrllibTransport``, which adds no
dependency to a tree the operator has to audit; a test gets one that dispatches
into the real ASGI application, which is what makes the parity and isolation
tests exercise the actual routes rather than a fake standing in for them.

**Credentials do not appear here.** There is no ``store_credential`` method,
deliberately: the console's integration form posts straight to the API's own
credential endpoint from the browser, so a secret never enters this process at
all. See ``pages/catalogue.py`` and SC-006.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.surfaces import JSON_SCHEMA_VERSION

#: How long a console request waits before reporting the deployment unreachable.
#: A console call is a control-plane call — an investigation is watched over the
#: event stream, never awaited through here — so this is generous.
REQUEST_TIMEOUT_SECONDS: Final = 30.0


@dataclass(frozen=True, slots=True)
class Response:
    """One answer from the API, before anything has decided what it means."""

    status: int
    body: Mapping[str, Any] = field(default_factory=dict)
    text: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return whether the API answered successfully."""
        return 200 <= self.status < 300


class ConsoleApiError(RuntimeError):
    """The API refused, or could not be reached.

    Carries the status so a page can tell the three cases apart that actually
    need different screens: not signed in (401), not permitted (403), and not
    there (404). Everything else is "the deployment is unhappy", which is one
    screen.
    """

    def __init__(self, status: int, path: str, detail: str = "") -> None:
        super().__init__(f"{path} answered {status}{f': {detail}' if detail else ''}")
        self.status = status
        self.path = path
        self.detail = detail

    @property
    def is_unauthenticated(self) -> bool:
        """Return whether this failure means "sign in again"."""
        return self.status == 401

    @property
    def is_forbidden(self) -> bool:
        """Return whether this failure means "you hold no permission for that"."""
        return self.status == 403

    @property
    def is_missing(self) -> bool:
        """Return whether this failure means "there is no such thing"."""
        return self.status == 404


@runtime_checkable
class Transport(Protocol):
    """Whatever carries one request to the API and brings back the answer."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Return the API's answer to one request."""


@dataclass(frozen=True, slots=True)
class UrllibTransport:
    """The shipped transport: the standard library's HTTP client and nothing else.

    No third-party HTTP dependency, for the same reason the CLI has none — every
    package in the runtime tree is one an operator has to audit, and this one
    buys nothing the standard library does not already do for a JSON API.
    """

    base_url: str
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
    opener: Any = None

    def resolve(self, path: str) -> str:
        """Return the absolute URL of ``path`` on this deployment."""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Return the API's answer, or raise ``ConsoleApiError`` if it did not answer."""
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.resolve(path),
            data=payload,
            method=method,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "x-ninjasre-schema": JSON_SCHEMA_VERSION,
                **dict(headers or {}),
            },
        )
        opener = self.opener or urllib.request.urlopen
        try:
            with opener(request, timeout=self.timeout_seconds) as answer:
                raw = answer.read().decode()
                return Response(
                    status=answer.status,
                    body=_document(raw),
                    text=raw,
                    headers={key.lower(): value for key, value in answer.headers.items()},
                )
        except urllib.error.HTTPError as failure:
            raw = failure.read().decode(errors="replace")
            return Response(status=failure.code, body=_document(raw), text=raw)
        except (urllib.error.URLError, TimeoutError, OSError) as failure:
            raise ConsoleApiError(503, path, f"could not reach {self.base_url}: {failure}") from (
                failure
            )


@dataclass(frozen=True, slots=True)
class ConsoleClient:
    """Everything the console asks of a deployment, and nothing it computes itself."""

    transport: Transport
    token: str = ""

    def with_token(self, token: str) -> ConsoleClient:
        """Return this client presenting ``token`` instead."""
        return ConsoleClient(transport=self.transport, token=token)

    # --- The one place a request is made -------------------------------------

    async def _get(self, path: str, **query: Any) -> Mapping[str, Any]:
        """Return the payload of one read, or raise naming the status."""
        return await self._call("GET", _with_query(path, query))

    async def _post(self, path: str, body: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Return the payload of one write."""
        return await self._call("POST", path, body=body if body is not None else {})

    async def _call(
        self, method: str, path: str, *, body: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """Return the payload of one request, raising on anything that is not success."""
        answer = await self.transport.request(
            method,
            path,
            body=body,
            headers={"authorization": f"Bearer {self.token}"} if self.token else {},
        )
        if not answer.ok:
            raise ConsoleApiError(answer.status, path, _detail_of(answer))
        return answer.body

    # --- Who is looking ------------------------------------------------------

    async def principal(self) -> Mapping[str, Any]:
        """Return the calling principal and the permissions it holds (FR-023)."""
        return await self._get("/auth/me")

    # --- Runs ----------------------------------------------------------------

    async def runs(self, *, limit: int = 50) -> Sequence[Mapping[str, Any]]:
        """Return recent runs, newest first (FR-001)."""
        return _records(await self._get("/v1/runs", limit=limit), "runs")

    async def run(self, run_id: str) -> Mapping[str, Any]:
        """Return one run."""
        return await self._get(f"/v1/runs/{run_id}")

    async def replay(self, run_id: str) -> Mapping[str, Any]:
        """Return ``run_id`` rebuilt from its recorded events alone (FR-002)."""
        return await self._get(f"/v1/runs/{run_id}/replay")

    async def turns(self, run_id: str) -> Mapping[str, Any]:
        """Return one run's conversation, its capability calls attached."""
        return await self._get(f"/v1/investigations/{run_id}/threads")

    async def start_investigation(
        self, objective: str, *, context: Mapping[str, str] | None = None
    ) -> Mapping[str, Any]:
        """Start an investigation and return its identity (FR-006)."""
        return await self._post(
            "/v1/investigations", {"objective": objective, "context": dict(context or {})}
        )

    async def add_context(self, run_id: str, text: str) -> Mapping[str, Any]:
        """Queue a message for delivery on the run's next turn (FR-006)."""
        return await self._post(f"/v1/investigations/{run_id}/messages", {"text": text})

    async def cancel(self, run_id: str) -> Mapping[str, Any]:
        """Ask a running investigation to stop at its next safe point (FR-006)."""
        return await self._post(f"/v1/investigations/{run_id}/cancel")

    # --- Interactions --------------------------------------------------------

    async def interactions(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return one run's open questions and approvals (FR-008)."""
        return _records(
            await self._get(f"/v1/investigations/{run_id}/interactions"), "interactions"
        )

    async def answer(
        self, interaction_id: str, text: str, *, selected_option: str = ""
    ) -> Mapping[str, Any]:
        """Answer a pending question."""
        return await self._post(
            f"/v1/interactions/{interaction_id}/answer",
            {"text": text, "selected_option": selected_option},
        )

    async def approve(self, interaction_id: str) -> Mapping[str, Any]:
        """Approve a pending change."""
        return await self._post(f"/v1/interactions/{interaction_id}/approve")

    async def reject(self, interaction_id: str, reason: str) -> Mapping[str, Any]:
        """Reject a pending change, with a reason."""
        return await self._post(f"/v1/interactions/{interaction_id}/reject", {"reason": reason})

    # --- Approvals and rollback ----------------------------------------------

    async def approvals(self, *, run_id: str = "", limit: int = 50) -> Sequence[Mapping[str, Any]]:
        """Return undecided approvals, longest-waiting first (FR-008)."""
        return _records(await self._get("/v1/approvals", run_id=run_id, limit=limit), "approvals")

    async def approval(self, approval_id: str) -> Mapping[str, Any]:
        """Return one approval with its rollback plan and evidence (FR-009)."""
        return await self._get(f"/v1/approvals/{approval_id}")

    async def rollback(self, approval_id: str) -> Mapping[str, Any]:
        """Record that an executed remediation was rolled back (FR-011)."""
        return await self._post(f"/v1/approvals/{approval_id}/rollback")

    # --- Memory and knowledge -------------------------------------------------

    async def episodes(
        self, *, component: str = "", limit: int = 20
    ) -> Sequence[Mapping[str, Any]]:
        """Return episodes involving ``component``, most recent first (FR-012)."""
        return _records(
            await self._get("/v1/memory/search", component=component, limit=limit), "episodes"
        )

    async def memory_stats(self) -> Mapping[str, Any]:
        """Return what the episodic corpus holds."""
        return await self._get("/v1/memory/stats")

    async def topology(self, node_id: str) -> Mapping[str, Any]:
        """Return a service's dependencies, dependents, and blast radius (FR-014)."""
        return await self._get(f"/v1/topology/{node_id}")

    async def documents(self, *, limit: int = 50) -> Sequence[Mapping[str, Any]]:
        """Return the ingested knowledge documents (FR-015)."""
        return _records(await self._get("/v1/knowledge/documents", limit=limit), "documents")

    async def document(self, document_id: str) -> Mapping[str, Any]:
        """Return one knowledge document with its passages."""
        return await self._get(f"/v1/knowledge/documents/{document_id}")

    # --- Configuration --------------------------------------------------------

    async def config_tree(self) -> Sequence[Mapping[str, Any]]:
        """Return the organisation tree, as one document (FR-016)."""
        return _records(await self._get("/v1/config"), "nodes")

    async def effective_config(self, node_id: str) -> Mapping[str, Any]:
        """Return a node's effective configuration, every value attributed."""
        return await self._get(f"/v1/config/{node_id}")

    async def preview_config(self, node_id: str, patch: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return what saving ``patch`` would resolve to, computed by the server.

        The console does not merge. It could — the algorithm is not difficult —
        and the day its copy drifted from the server's, somebody would save a
        change that did something other than what this screen showed them
        (FR-017, SC-005).
        """
        return await self._call("POST", f"/v1/config/{node_id}/preview", body={"patch": patch})

    async def write_config(self, node_id: str, patch: Mapping[str, Any]) -> Mapping[str, Any]:
        """Apply a patch to a node's own settings."""
        return await self._call("PUT", f"/v1/config/{node_id}", body={"patch": patch})

    async def catalogue(self, node_id: str) -> Mapping[str, Any]:
        """Return what a node can run, and why anything else it cannot (FR-021)."""
        return await self._get(f"/v1/config/{node_id}/catalogue")

    async def guardian(self, node_id: str) -> Mapping[str, Any]:
        """Return the shipped detector set as this node runs it, resolved server-side."""
        return await self._get(f"/v1/config/{node_id}/guardian")

    async def integration_schemas(self, node_id: str) -> Sequence[Mapping[str, Any]]:
        """Return the schemas a credential form is generated from (FR-020)."""
        return _records(await self._get(f"/v1/config/{node_id}/integration-schemas"), "schemas")

    async def integrations(self) -> Sequence[Mapping[str, Any]]:
        """Return every installed integration."""
        return _records(await self._get("/v1/integrations"), "integrations")

    # --- Administration --------------------------------------------------------

    async def principals(self) -> Sequence[Mapping[str, Any]]:
        """Return everyone in this organisation (FR-023)."""
        return _records(await self._get("/identity/principals"), "users")

    async def grants(self) -> Sequence[Mapping[str, Any]]:
        """Return the role grants held in this organisation."""
        return _records(await self._get("/identity/grants"), "grants")

    async def tokens(self) -> Sequence[Mapping[str, Any]]:
        """Return this organisation's machine tokens (FR-026)."""
        return _records(await self._get("/identity/tokens"), "tokens")

    async def create_token(self, name: str, *, node_id: str | None = None) -> Mapping[str, Any]:
        """Issue a machine token; its secret comes back exactly once."""
        return await self._post("/identity/tokens", {"name": name, "node_id": node_id})

    async def revoke_tokens(
        self, *, token_ids: Sequence[str] = (), user_id: str = ""
    ) -> Mapping[str, Any]:
        """Revoke tokens by id or by owner (FR-026)."""
        return await self._post(
            "/identity/tokens/revoke", {"token_ids": list(token_ids), "user_id": user_id}
        )

    async def audit_events(self, **filters: Any) -> Mapping[str, Any]:
        """Return matching audit events, most recent first (FR-025)."""
        return await self._get("/audit/events", **filters)

    async def capabilities(self) -> Mapping[str, Any]:
        """Return every declared tool and skill."""
        return await self._get("/v1/capabilities")

    async def health(self) -> Mapping[str, Any]:
        """Return what the deployment reports about itself."""
        return await self._get("/health/ready")


def _with_query(path: str, query: Mapping[str, Any]) -> str:
    """Return ``path`` with the non-empty parts of ``query`` appended."""
    parameters = {
        name: str(value) for name, value in query.items() if value is not None and str(value) != ""
    }
    if not parameters:
        return path
    return f"{path}?{urllib.parse.urlencode(parameters)}"


def _records(payload: Mapping[str, Any], key: str) -> Sequence[Mapping[str, Any]]:
    """Return the list under ``key``, or an empty one if it is missing or wrong-shaped."""
    found = payload.get(key)
    if not isinstance(found, list):
        return ()
    return tuple(record for record in found if isinstance(record, Mapping))


def _document(raw: str) -> Mapping[str, Any]:
    """Return the JSON object in ``raw``, or an empty mapping if there is none."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _detail_of(answer: Response) -> str:
    """Return what the API said was wrong, if it said anything a user should read."""
    for key in ("detail", "message", "error"):
        value = answer.body.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


__all__ = [
    "REQUEST_TIMEOUT_SECONDS",
    "ConsoleApiError",
    "ConsoleClient",
    "Response",
    "Transport",
    "UrllibTransport",
]
