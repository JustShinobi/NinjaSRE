"""Turning real vendor responses into fixtures, with the secrets taken out.

A fixture is only worth having if it is what the vendor really sends. Written
by hand it is what its author believed the vendor sends, which is the same
document right up until the vendor adds a field, renames one, or starts
paginating — and then the suite goes on passing against a shape nothing
produces.

So fixtures are recorded. A ``RecordingSender`` sits where the mock boundary
normally sits, in front of a real sender, and writes what came back into the
fixture documents the loader reads.

**Nothing is written before it is scrubbed.** A recorded response is a file that
gets committed, and a vendor response routinely carries more than the caller
asked for: a bearer token echoed in an error, a signed URL with its signature,
an account id, a connection string. The scrubber removes the credential values
it was given by identity, and the shapes it recognises by pattern, and it is
deliberately eager: a false positive costs a fixture one unreadable field, and a
false negative costs a repository a live credential in its history.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse

#: What a removed secret is replaced with. One token, so a reviewer scanning a
#: fixture diff can see at a glance that scrubbing ran.
REDACTED: Final = "REDACTED"

#: Secret shapes worth removing whether or not anybody named them. Each one is a
#: value that has appeared inside a real vendor response body.
_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # AWS access key identifiers, permanent and temporary.
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # A JSON Web Token, which is what most bearer credentials look like.
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"),
    # An Authorization header echoed back into a body.
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    # A PEM block of any kind.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # A signed-URL signature, which is a credential with an expiry.
    re.compile(r"(?i)(?:x-amz-signature|signature|sig)=[A-Za-z0-9%._~+/=-]{16,}"),
    # A named secret field in a JSON body.
    re.compile(
        r'(?i)"(?:api[_-]?key|secret[_-]?\w*|token|pass\w*|credential\w*)"\s*:\s*"[^"]{4,}"'
    ),
)


@runtime_checkable
class OutboundSender(Protocol):
    """What the proxy hands a request to. Recording wraps one of these."""

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Return the vendor's answer to ``request``."""


def scrub(text: str, secrets: Sequence[str] = ()) -> str:
    """Return ``text`` with every known and every recognised secret removed.

    ``secrets`` are the credential values used for the recording, removed by
    identity. Everything else goes by pattern. Both run, and in that order, so
    a credential that also matches a pattern is removed once rather than
    partially.
    """
    cleaned = text
    for secret in sorted((value for value in secrets if len(value) >= 4), key=len, reverse=True):
        cleaned = cleaned.replace(secret, REDACTED)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(_replacement, cleaned)
    return cleaned


def _replacement(match: re.Match[str]) -> str:
    """Return what one recognised secret is replaced with.

    A JSON field keeps its key and its quotes, because a fixture whose shape
    changed under scrubbing would no longer be the shape the client parses —
    which is the one property the recording exists to preserve.
    """
    found = match.group(0)
    if found.startswith('"') and '":' in found:
        key, _, _ = found.partition(":")
        return f'{key}: "{REDACTED}"'
    if "=" in found and not found.startswith("-----"):
        key, _, _ = found.partition("=")
        return f"{key}={REDACTED}"
    return REDACTED


def scrub_document(document: Any, secrets: Sequence[str] = ()) -> Any:
    """Return ``document`` with every string value scrubbed, structure intact."""
    if isinstance(document, str):
        return scrub(document, secrets)
    if isinstance(document, Mapping):
        return {key: scrub_document(value, secrets) for key, value in document.items()}
    if isinstance(document, list):
        return [scrub_document(value, secrets) for value in document]
    return document


@dataclass(slots=True)
class RecordingSender:
    """A sender that answers from the real vendor and keeps what it answered.

    Drop-in for the mock boundary: same port, same position in the proxy. That
    is what makes a recording session and a replay session the same code path
    with one object swapped, rather than two procedures that have to be kept in
    agreement.
    """

    inner: OutboundSender
    #: Vendor host to integration name, so each response lands in the fixture
    #: file for the integration that produced it.
    hosts: Mapping[str, str] = field(default_factory=dict)
    #: The credential values this session used. Removed by identity.
    secrets: tuple[str, ...] = ()
    captured: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Return the vendor's real answer, and record a scrubbed copy of it."""
        response = await self.inner.send(request, timeout_seconds=timeout_seconds)
        integration = self.hosts.get(request.host.lower(), request.host.lower())
        self.captured.append((integration, self._document(request, response)))
        return response

    def _document(self, request: OutboundRequest, response: OutboundResponse) -> dict[str, Any]:
        """Return one recorded response, scrubbed, in the fixture's own schema."""
        content_type = ""
        for name, value in response.headers.items():
            if name.lower() == "content-type":
                content_type = value
                break

        raw = response.body.decode("utf-8", errors="replace")
        recorded: dict[str, Any] = {
            "match": {"method": request.method, "path_contains": scrub(request.path, self.secrets)},
            "status": response.status_code,
        }
        if content_type:
            recorded["content_type"] = content_type

        if "json" in content_type.lower():
            try:
                recorded["body"] = scrub_document(json.loads(raw), self.secrets)
                return recorded
            except json.JSONDecodeError:
                # A vendor that declared JSON and sent something else is worth
                # recording verbatim: that discrepancy is the bug a live
                # contract run exists to find.
                pass
        recorded["body_text"] = scrub(raw, self.secrets)
        return recorded

    def documents(self) -> dict[str, dict[str, Any]]:
        """Return one evidence fixture document per integration, keyed by filename."""
        by_integration: dict[str, list[dict[str, Any]]] = {}
        for integration, recorded in self.captured:
            by_integration.setdefault(integration, []).append(recorded)
        return {
            f"{integration}.json": {"integration": integration, "responses": responses}
            for integration, responses in sorted(by_integration.items())
        }

    def write(self, directory: Path) -> tuple[Path, ...]:
        """Write the recorded fixtures into ``directory`` and return their paths."""
        directory.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for filename, document in self.documents().items():
            path = directory / filename
            path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
        return tuple(written)


__all__ = [
    "REDACTED",
    "OutboundSender",
    "RecordingSender",
    "scrub",
    "scrub_document",
]
