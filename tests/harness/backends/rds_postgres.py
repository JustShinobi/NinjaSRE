"""The managed PostgreSQL vendor, and what an idle database's control plane says.

RDS speaks the AWS query protocol for its control plane and CloudWatch's JSON
for its metrics, so its empty answers are AWS's — but the suite that exercises
it is a database suite, and the shapes worth getting right here are database
shapes: an instance list with no instances, and a metric series with no points.

It has its own module rather than a row in ``aws.py`` because that is the unit a
contributor thinks in. Somebody porting a slow-query scenario is working on
PostgreSQL, not on the eighth AWS service, and the module they have to open
should be the one their scenario is about.
"""

from __future__ import annotations

from typing import Final

from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends.aws import empty as aws_empty
from tests.harness.backends.base import MockBackend

#: The integration this repository ships for managed PostgreSQL.
INTEGRATION: Final = "aws_rds"


def empty(request: OutboundRequest) -> OutboundResponse:
    """Return what an RDS endpoint with nothing to report answers."""
    return aws_empty(request)


BACKENDS: Final[tuple[MockBackend, ...]] = (
    MockBackend(
        integration=INTEGRATION,
        empty=empty,
        recorded_from="aws rds describe-db-instances / aws cloudwatch get-metric-data --debug",
    ),
)


__all__ = ["BACKENDS", "INTEGRATION", "empty"]
