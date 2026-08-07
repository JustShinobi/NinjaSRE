"""The version-control vendors, whose collections are arrays and whose search
results are not.

GitHub answers a collection endpoint with a JSON array and a search endpoint
with ``{"total_count": 0, "items": []}``. Both are "nothing found"; only one of
them is a list, and a client that indexed into the wrong one would fail in a
scenario that simply had no matching commits in the window.

The rule here is the path's own shape rather than a list of endpoints: a path
whose last meaningful segment is a plural collection name answers an array. It
is a heuristic, and it is the right kind of heuristic — wrong in the direction
of ``{}``, which every client in this repository reads without raising.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response

#: Path segments whose endpoint answers a bare array when empty.
_COLLECTIONS: Final[frozenset[str]] = frozenset(
    {
        "branches",
        "comments",
        "commits",
        "deployments",
        "events",
        "issues",
        "jobs",
        "labels",
        "pulls",
        "releases",
        "repos",
        "reviews",
        "runs",
        "statuses",
        "tags",
        "workflows",
    }
)

_SEARCH_PREFIX: Final = "/search/"


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a repository with nothing to report answers."""
    if request.path.startswith(_SEARCH_PREFIX):
        return json_response({"total_count": 0, "incomplete_results": False, "items": []})
    segments = [segment for segment in request.path.split("/") if segment]
    if segments and segments[-1] in _COLLECTIONS:
        return json_response([])
    if "/actions/runs" in request.path:
        return json_response({"total_count": 0, "workflow_runs": []})
    return json_response({})


BACKENDS: Final[tuple[MockBackend, ...]] = tuple(
    MockBackend(
        integration=name,
        empty=empty,
        recorded_from="gh api <endpoint>, with author emails and private repository names removed",
    )
    for name in ("github", "gitlab", "bitbucket")
)


__all__ = ["BACKENDS", "empty"]
