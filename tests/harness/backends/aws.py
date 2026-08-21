"""AWS's vendors, which answer in two protocols, and the empty document of each.

AWS is not one API. The services that predate JSON — EC2, ELB, and their
relatives — take a form-encoded ``Action`` and answer XML; the ones that came
later take a JSON body with an ``X-Amz-Target`` header and answer JSON. Both
are reached through the same signer and the same proxy, so the boundary has to
tell them apart from the request rather than from the integration name.

The tell is the request, not a table: a form-encoded body carrying ``Action=``
is the query protocol, and everything else is JSON. That is what the signer
already keys on, so the two stay in agreement without either knowing about the
other.

The empty XML document is deliberately a bare envelope. A query-protocol client
reads the elements it wants and finds none, which is exactly what a region with
no instances, no load balancers, and no events looks like on the wire.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.base import MockBackend, json_response, xml_response

#: The AWS integrations whose empty answer this module supplies. ``aws_rds`` is
#: not here: its scenarios are a database suite of their own, and its backend
#: lives beside them.
AWS_INTEGRATIONS: Final[tuple[str, ...]] = (
    "aws",
    "aws_cloudtrail",
    "aws_ec2",
    "aws_ecs",
    "aws_eks",
    "aws_elb",
    "aws_lambda",
    "aws_s3",
)

_QUERY_PROTOCOL_MARKER: Final = b"Action="

#: The bare query-protocol envelope. No operation name, because the client
#: reads its own elements out of it and finds none either way, and inventing an
#: operation here would mean guessing which call this was.
_EMPTY_XML: Final = "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"


def _is_query_protocol(request: OutboundRequest) -> bool:
    """Return whether ``request`` is a form-encoded query-protocol call."""
    body = request.body or b""
    if _QUERY_PROTOCOL_MARKER in body:
        return True
    return _QUERY_PROTOCOL_MARKER.decode() in request.url


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what an AWS service with nothing to report answers."""
    if _is_query_protocol(request):
        return xml_response(_EMPTY_XML)
    return json_response({})


BACKENDS: Final[tuple[MockBackend, ...]] = tuple(
    MockBackend(
        integration=name,
        empty=empty,
        recorded_from="aws <service> <operation> --debug, with the signed request headers dropped",
    )
    for name in AWS_INTEGRATIONS
)


__all__ = ["AWS_INTEGRATIONS", "BACKENDS", "empty"]
