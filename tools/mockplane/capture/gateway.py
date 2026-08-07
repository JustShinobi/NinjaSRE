"""Recording what a live deployment already answers, and reporting what it did not.

The half of the capture that needs no cluster: for every endpoint the gateway
serves today, one request, and the response recorded beside the request that
produced it and the contract version in force. An endpoint that could not be
reached is reported rather than silently absent — a fixture set with a hole in
it and no note about the hole is a fixture set that fails a coverage test for a
reason nobody can act on.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.fixtures import (
    NINJASRE_CAPTURE_ENDPOINT_ENV,
    NINJASRE_CAPTURE_TOKEN_ENV,
)
from tools.mockplane.endpoints import ConsoleEndpoint, gateway_endpoints, render_path
from tools.mockplane.records import CONTRACT_VERSION, CapturedRecord, Provenance, Request

#: How long one recorded request waits. Generous: a capture is taken once.
CAPTURE_TIMEOUT_SECONDS: Final = 60.0


@dataclass(frozen=True, slots=True)
class Answer:
    """One raw answer from a deployment."""

    status: int
    body: Any


@runtime_checkable
class Fetcher(Protocol):
    """Whatever carries one recorded request to a deployment."""

    def fetch(self, method: str, url: str, token: str) -> Answer:
        """Return the deployment's answer to one request."""


@dataclass(frozen=True, slots=True)
class UrllibFetcher:
    """The shipped fetcher: the standard library, and nothing added to the tree."""

    timeout_seconds: float = CAPTURE_TIMEOUT_SECONDS

    def fetch(self, method: str, url: str, token: str) -> Answer:
        """Return the deployment's answer, or the status it refused with."""
        request = urllib.request.Request(
            url,
            method=method,
            headers={
                "accept": "application/json",
                **({"authorization": f"Bearer {token}"} if token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as answer:
                raw = answer.read().decode()
                return Answer(status=answer.status, body=_document(raw))
        except urllib.error.HTTPError as refusal:
            return Answer(status=refusal.code, body=_document(refusal.read().decode("replace")))
        except (urllib.error.URLError, TimeoutError, OSError) as failure:
            raise GatewayUnreachable(f"{url} could not be reached: {failure}") from failure


class GatewayUnreachable(RuntimeError):
    """The deployment did not answer at all."""


@dataclass(frozen=True, slots=True)
class GatewayTarget:
    """Which deployment to record, and what to present to it."""

    base_url: str
    token: str = ""

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> GatewayTarget:
        """Return the configured deployment.

        Raises:
            GatewayUnreachable: nothing names one.
        """
        source = dict(environ if environ is not None else os.environ)
        base = source.get(NINJASRE_CAPTURE_ENDPOINT_ENV, "").strip()
        if not base:
            raise GatewayUnreachable(
                f"set {NINJASRE_CAPTURE_ENDPOINT_ENV} to the deployment to record"
            )
        return cls(base_url=base, token=source.get(NINJASRE_CAPTURE_TOKEN_ENV, "").strip())


@dataclass(frozen=True, slots=True)
class MissedEndpoint:
    """One endpoint the capture could not record, and why."""

    slug: str
    method: str
    path: str
    source: str
    reason: str

    def __str__(self) -> str:
        return f"{self.method} {self.path} ({self.source}): {self.reason}"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """What one capture produced, and what it did not."""

    records: tuple[CapturedRecord, ...] = field(default_factory=tuple)
    missed: tuple[MissedEndpoint, ...] = field(default_factory=tuple)

    def merged_with(self, other: CaptureResult) -> CaptureResult:
        """Return both captures as one result."""
        return CaptureResult(
            records=self.records + other.records,
            missed=self.missed + other.missed,
        )


def capture_gateway(
    target: GatewayTarget,
    fetcher: Fetcher,
    *,
    arguments: Mapping[str, Mapping[str, str]] | None = None,
    endpoints: Sequence[ConsoleEndpoint] | None = None,
) -> CaptureResult:
    """Return one record per gateway endpoint, and a note for every one it missed.

    ``arguments`` supplies the concrete values for templated paths, keyed by
    slug. An endpoint whose template has no arguments supplied is *missed*
    rather than skipped: "we never asked" and "it answered nothing" are
    different facts and a coverage report that conflated them would be useless.

    Only reads are recorded. A capture that posted an investigation to somebody's
    deployment would be a capture that changed the thing it was measuring.
    """
    supplied = dict(arguments or {})
    records: list[CapturedRecord] = []
    missed: list[MissedEndpoint] = []

    for endpoint in endpoints if endpoints is not None else gateway_endpoints():
        if endpoint.streaming:
            missed.append(
                MissedEndpoint(
                    endpoint.slug,
                    endpoint.method,
                    endpoint.path,
                    Provenance.GATEWAY.value,
                    "it is a stream; the mock generates it from the run's recorded events",
                )
            )
            continue
        if endpoint.method != "GET":
            missed.append(
                MissedEndpoint(
                    endpoint.slug,
                    endpoint.method,
                    endpoint.path,
                    Provenance.GATEWAY.value,
                    "it writes, and a capture does not change the deployment it measures",
                )
            )
            continue

        bound = supplied.get(endpoint.slug, {})
        try:
            path = render_path(endpoint.path, bound)
        except KeyError as missing:
            missed.append(
                MissedEndpoint(
                    endpoint.slug,
                    endpoint.method,
                    endpoint.path,
                    Provenance.GATEWAY.value,
                    f"no value was supplied for {missing.args[0]!r}",
                )
            )
            continue

        url = f"{target.base_url.rstrip('/')}{path}"
        try:
            answer = fetcher.fetch(endpoint.method, url, target.token)
        except GatewayUnreachable as failure:
            missed.append(
                MissedEndpoint(
                    endpoint.slug,
                    endpoint.method,
                    endpoint.path,
                    Provenance.GATEWAY.value,
                    str(failure),
                )
            )
            continue

        if answer.status != 200:
            missed.append(
                MissedEndpoint(
                    endpoint.slug,
                    endpoint.method,
                    endpoint.path,
                    Provenance.GATEWAY.value,
                    f"it answered {answer.status}",
                )
            )
            continue

        records.append(
            CapturedRecord(
                slug=endpoint.slug,
                arguments=dict(bound),
                status=answer.status,
                body=answer.body,
                provenance=Provenance.GATEWAY,
                request=Request(method=endpoint.method, path=path),
                contract_version=CONTRACT_VERSION,
            )
        )

    return CaptureResult(records=tuple(records), missed=tuple(missed))


def _document(raw: str) -> Any:
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


__all__ = [
    "CAPTURE_TIMEOUT_SECONDS",
    "Answer",
    "CaptureResult",
    "Fetcher",
    "GatewayTarget",
    "GatewayUnreachable",
    "MissedEndpoint",
    "UrllibFetcher",
    "capture_gateway",
]
