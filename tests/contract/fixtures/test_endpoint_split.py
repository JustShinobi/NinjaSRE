"""The endpoint catalogue, and the line between what exists and what is projected.

The console reaches a deployment through exactly one module — its API client —
so "every endpoint the console consumes" is an enumerable fact rather than a
judgement, and this suite is what keeps the enumeration honest.

The split matters more than the list. Half of what these screens show is served
by features that have not landed: the estate inventory, continuous observation,
and the Proxmox integration. Fixtures for those are *projections* — written
against the shapes those endpoints will return. A projection for an endpoint the
gateway already serves is not a projection, it is a second source of truth, and
the assertion below is what stops one appearing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.mockplane.contract import openapi_document
from tools.mockplane.endpoints import (
    CONSOLE_ENDPOINTS,
    EndpointSource,
    endpoint_by_slug,
    gateway_endpoints,
    match_request,
    projected_endpoints,
)

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
CONSOLE_CLIENT = REPO_ROOT / "surfaces" / "console" / "client.py"


def _paths_the_console_client_names() -> set[str]:
    """Return every request path spelled in the console's API client.

    Read from the source rather than by calling the methods: a path built inside
    a method body is still a path the console consumes, and calling every method
    would need a deployment.
    """
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        # An f-string is rendered whole and never descended into: its literal
        # pieces are fragments, and collecting them would report ``/answer`` as
        # a path the console asks for.
        if isinstance(node, ast.JoinedStr):
            rendered = "".join(
                part.value
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
                else "*"
                for part in node.values
            )
            if rendered.startswith("/"):
                found.add(rendered)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("/"):
                found.add(node.value)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(ast.parse(CONSOLE_CLIENT.read_text(encoding="utf-8")))
    return found


def _template_as_wildcards(path: str) -> str:
    """Return ``path`` with each ``{name}`` segment replaced by ``*``."""
    out: list[str] = []
    depth = 0
    for character in path:
        if character == "{":
            depth += 1
            if depth == 1:
                out.append("*")
        elif character == "}":
            depth -= 1
        elif depth == 0:
            out.append(character)
    return "".join(out)


def test_the_catalogue_names_every_path_the_console_client_asks_for() -> None:
    catalogued = {_template_as_wildcards(endpoint.path) for endpoint in CONSOLE_ENDPOINTS}
    missing = sorted(_paths_the_console_client_names() - catalogued)
    assert not missing, (
        "the console asks for paths the fixture catalogue does not name: " + ", ".join(missing)
    )


def test_every_gateway_endpoint_is_one_the_document_actually_serves() -> None:
    document = openapi_document()
    served = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
    }
    unserved = sorted(
        f"{endpoint.method} {endpoint.path}"
        for endpoint in gateway_endpoints()
        if (endpoint.method, endpoint.path) not in served
    )
    assert not unserved, (
        "declared as served by the gateway, but absent from its OpenAPI document: "
        + ", ".join(unserved)
    )


def test_a_projected_endpoint_is_not_one_the_gateway_already_serves() -> None:
    document = openapi_document()
    served = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
    }
    overlapping = sorted(
        f"{endpoint.method} {endpoint.path} (projected for {endpoint.arrives_with})"
        for endpoint in projected_endpoints()
        if (endpoint.method, endpoint.path) in served
    )
    assert not overlapping, (
        "these endpoints are projected but the gateway now serves them; take them from the "
        "gateway and delete the projection rather than keeping a second way to produce the "
        "same fixture: " + ", ".join(overlapping)
    )


def test_every_projection_names_the_work_that_will_replace_it() -> None:
    unattributed = sorted(
        f"{endpoint.method} {endpoint.path}"
        for endpoint in projected_endpoints()
        if not endpoint.arrives_with
    )
    assert not unattributed, (
        "a projection with nobody to hand over to is a fixture nobody will ever delete: "
        + ", ".join(unattributed)
    )


def test_the_two_sources_are_disjoint_and_together_are_the_whole_catalogue() -> None:
    assert set(gateway_endpoints()).isdisjoint(projected_endpoints())
    assert set(gateway_endpoints()) | set(projected_endpoints()) == set(CONSOLE_ENDPOINTS)


def test_slugs_are_unique_so_one_fixture_file_means_one_endpoint() -> None:
    slugs = [endpoint.slug for endpoint in CONSOLE_ENDPOINTS]
    assert len(slugs) == len(set(slugs)), "two endpoints share a fixture filename"
    for endpoint in CONSOLE_ENDPOINTS:
        assert endpoint_by_slug(endpoint.slug) is endpoint


def test_a_concrete_request_path_resolves_to_the_endpoint_that_templates_it() -> None:
    resolved = match_request("GET", "/v1/runs/run-0007")
    assert resolved is not None
    endpoint, arguments = resolved
    assert endpoint.path == "/v1/runs/{run_id}"
    assert arguments == {"run_id": "run-0007"}


def test_a_longer_path_does_not_match_a_shorter_template() -> None:
    resolved = match_request("GET", "/v1/runs/run-0007/replay")
    assert resolved is not None
    endpoint, _ = resolved
    assert endpoint.path == "/v1/runs/{run_id}/replay"


def test_a_literal_segment_wins_over_a_templated_one() -> None:
    # ``/v1/knowledge/documents`` and ``/v1/knowledge/documents/{document_id}``
    # differ by one segment; a template that swallowed the collection would make
    # the list screen serve a detail payload.
    resolved = match_request("GET", "/v1/knowledge/documents")
    assert resolved is not None
    assert resolved[0].path == "/v1/knowledge/documents"


def test_a_path_nothing_serves_resolves_to_nothing() -> None:
    assert match_request("GET", "/v1/nothing-here") is None


def test_the_streaming_endpoints_are_marked_as_one() -> None:
    streaming = [endpoint for endpoint in CONSOLE_ENDPOINTS if endpoint.streaming]
    assert sorted(endpoint.path for endpoint in streaming) == sorted(
        ["/v1/investigations/{run_id}/stream", "/v1/events/stream"]
    )
    assert all(endpoint.source is EndpointSource.GATEWAY for endpoint in streaming)
