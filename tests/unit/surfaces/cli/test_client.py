"""The same commands operate against a local or a remote deployment.

The property worth protecting is that a command cannot tell which it got. So
what is asserted is that both implementations satisfy the same protocol, that
selection is one decision taken once, and that a remote failure becomes the
same exit code its local equivalent would.
"""

from __future__ import annotations

import asyncio
import io
import json
import urllib.error
from collections.abc import Mapping
from typing import Any

import pytest

from config.constants.surfaces import TRANSPORT_LOCAL, TRANSPORT_REMOTE
from surfaces.cli.client import (
    Endpoint,
    InvestigationRequest,
    LocalClient,
    PlatformClient,
    RemoteClient,
    endpoint_from,
    select_client,
)
from surfaces.cli.errors import (
    ApprovalRequiredError,
    CliError,
    ConfigurationError,
    DeniedError,
    NotFoundError,
    UnavailableError,
)
from tests.support.deployment import FakeServices, seeded

pytestmark = pytest.mark.unit


class _Response(io.BytesIO):
    """A minimal stand-in for what ``urlopen`` returns."""

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _opener(payload: Mapping[str, Any], *, ok: bool = True) -> Any:
    """Return an opener that answers every request with ``payload``."""

    def opener(request: Any, timeout: float = 0) -> _Response:
        document = {
            "schema": "ninjasre.cli.test.v1",
            "command": "test",
            "ok": ok,
            "data": dict(payload),
            "errors": [] if ok else ["the deployment reported a failure"],
        }
        return _Response(json.dumps(document).encode())

    return opener


def _failing(status: int) -> Any:
    """Return an opener that answers with an HTTP failure."""

    def opener(request: Any, timeout: float = 0) -> _Response:
        raise urllib.error.HTTPError(
            url="http://x/v1/runs", code=status, msg="no", hdrs=None, fp=None
        )

    return opener


def test_both_clients_satisfy_the_one_protocol() -> None:
    # The whole of it. A command holds a ``PlatformClient`` and cannot tell
    # which it got.
    local = LocalClient(services=seeded())
    remote = RemoteClient(endpoint=Endpoint(url="https://ninjasre.internal"))

    assert isinstance(local, PlatformClient)
    assert isinstance(remote, PlatformClient)


def test_each_client_reports_which_kind_it_is() -> None:
    assert LocalClient(services=seeded()).transport == TRANSPORT_LOCAL
    assert RemoteClient(endpoint=Endpoint(url="https://x")).transport == TRANSPORT_REMOTE


def test_an_endpoint_wins_over_a_local_composition() -> None:
    # An operator naming an endpoint is saying "not this machine". Silently
    # preferring a local deployment would run an investigation somewhere they
    # did not mean.
    chosen = select_client(services=seeded(), endpoint=Endpoint(url="https://ninjasre.internal"))

    assert chosen.transport == TRANSPORT_REMOTE


def test_with_no_endpoint_the_local_composition_is_used() -> None:
    assert select_client(services=seeded()).transport == TRANSPORT_LOCAL


def test_with_neither_the_failure_says_what_to_do() -> None:
    with pytest.raises(CliError, match="--endpoint"):
        select_client()


def test_an_endpoint_needs_a_scheme() -> None:
    with pytest.raises(CliError, match="not an endpoint"):
        endpoint_from("ninjasre.internal:8420")


def test_an_empty_endpoint_names_nothing() -> None:
    assert endpoint_from("") is None
    assert endpoint_from("   ") is None


def test_an_endpoint_resolves_paths_without_doubling_slashes() -> None:
    endpoint = Endpoint(url="https://ninjasre.internal/")

    assert endpoint.resolve("/v1/runs") == "https://ninjasre.internal/v1/runs"


def test_the_remote_client_reads_the_envelopes_payload() -> None:
    client = RemoteClient(
        endpoint=Endpoint(url="https://x"),
        opener=_opener({"episodes": 4, "components": 2, "mean_effectiveness": 0.5}),
    )

    stats = asyncio.run(client.memory_stats())

    assert stats.episodes == 4
    assert stats.components == 2


def test_a_deployment_that_reports_a_failure_raises() -> None:
    client = RemoteClient(endpoint=Endpoint(url="https://x"), opener=_opener({}, ok=False))

    with pytest.raises(CliError, match="reported a failure"):
        asyncio.run(client.memory_stats())


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, DeniedError),
        (403, DeniedError),
        (404, NotFoundError),
        (409, ApprovalRequiredError),
        (422, ConfigurationError),
        (500, UnavailableError),
        (503, UnavailableError),
    ],
)
def test_a_remote_failure_becomes_the_same_error_a_local_one_would(
    status: int, expected: type[CliError]
) -> None:
    # The exit code an operator's script branches on has to be the same whether
    # the deployment is local or remote.
    client = RemoteClient(endpoint=Endpoint(url="https://x"), opener=_failing(status))

    with pytest.raises(expected):
        asyncio.run(client.memory_stats())


def test_an_unreachable_deployment_is_reported_as_unavailable() -> None:
    def opener(request: Any, timeout: float = 0) -> None:
        raise urllib.error.URLError("connection refused")

    client = RemoteClient(endpoint=Endpoint(url="https://x"), opener=opener)

    with pytest.raises(UnavailableError, match="could not reach"):
        asyncio.run(client.memory_stats())


def test_something_that_is_not_a_ninjasre_deployment_says_so() -> None:
    def opener(request: Any, timeout: float = 0) -> _Response:
        return _Response(b"<html>hello</html>")

    client = RemoteClient(endpoint=Endpoint(url="https://x"), opener=opener)

    with pytest.raises(UnavailableError, match="not JSON"):
        asyncio.run(client.memory_stats())


def test_a_bearer_token_is_presented_when_one_was_given() -> None:
    seen: list[Any] = []

    def opener(request: Any, timeout: float = 0) -> _Response:
        seen.append(request)
        return _opener({"episodes": 0})(request, timeout)

    client = RemoteClient(endpoint=Endpoint(url="https://x", token="tok-123"), opener=opener)
    asyncio.run(client.memory_stats())

    assert seen[0].get_header("Authorization") == "Bearer tok-123"


def test_a_credential_goes_in_the_body_and_never_the_query_string() -> None:
    # A query parameter would put the secret in the deployment's access log.
    seen: list[Any] = []

    def opener(request: Any, timeout: float = 0) -> _Response:
        seen.append(request)
        return _opener({"integration": "datadog", "configured": True})(request, timeout)

    client = RemoteClient(endpoint=Endpoint(url="https://x"), opener=opener)
    asyncio.run(client.store_integration_credential("datadog", {"api_key": "SECRET"}))

    assert "SECRET" not in seen[0].full_url
    assert b"SECRET" in seen[0].data


def test_the_local_client_names_a_run_that_does_not_exist() -> None:
    client = LocalClient(services=seeded())

    with pytest.raises(NotFoundError, match="run-9999"):
        asyncio.run(client.show_run("run-9999"))


def test_replaying_a_run_with_no_trace_is_reported_as_not_found() -> None:
    services = FakeServices()
    asyncio.run(services.investigate(InvestigationRequest(objective="something")))
    client = LocalClient(services=services)

    with pytest.raises(NotFoundError, match="no recorded events"):
        asyncio.run(client.replay_run("run-0001"))


def test_a_diff_is_computed_the_same_way_for_both_transports() -> None:
    # Computed by the client rather than asked of the deployment, so a diff
    # between a local node and a remote one is the same function.
    client = LocalClient(services=seeded())

    diff = asyncio.run(client.diff_config("payments", "root"))

    assert [delta.path for delta in diff.deltas] == ["settings.masking"]
    assert diff.deltas[0].left == "standard"
    assert diff.deltas[0].right == "strict"


def test_an_investigation_needs_something_to_investigate() -> None:
    with pytest.raises(ValueError, match="needs an alert or a description"):
        InvestigationRequest()
