"""Kubernetes' vendor, and what an API server with nothing to report answers.

Two shapes, because the API server has two. Everything addressed at a resource
collection answers a ``List`` — empty ``items`` and an empty ``continue``
token, which is what the client's pagination reads as "last page" — and the log
subresource answers plain text, because it is a stream and not a document.

Getting the second one wrong is the interesting failure. A JSON ``{}`` handed
to a log reader is not an empty log; it is a log with one line in it that says
``{}``, and a scenario would score an agent for reading evidence that was never
planted.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response, text_response

#: The subresource whose answer is a stream rather than a document.
_LOG_SUBRESOURCE: Final = "/log"


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what a Kubernetes API server with nothing to report answers."""
    if request.path.endswith(_LOG_SUBRESOURCE):
        return text_response("")
    return json_response(
        {"kind": "List", "apiVersion": "v1", "metadata": {"continue": ""}, "items": []}
    )


BACKENDS: Final[tuple[MockBackend, ...]] = (
    MockBackend(
        integration="kubernetes",
        empty=empty,
        recorded_from="kubectl get -o json / kubectl logs against a namespace in a test cluster",
    ),
)


__all__ = ["BACKENDS", "empty"]
