"""AWS S3, end to end: capability, client, proxy, injection, vendor.

The seventh parity artefact. Everything else about an integration can look
finished while nothing exercises the path a real call takes — and the first
thing to notice that is the investigation which needed it.

So these drive the whole path: the registered capability, the client, the real
credential proxy with this integration's own injection rule, and a scripted
vendor on the far side. Nothing is mocked between the tool and the wire, which
is what makes a renamed response field fail here rather than at 03:00.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import (
    IntegrationScenario,
    xml_response,
)

#: Not a real credential. The suite asserts that none of these values reaches a
#: client, a result, or a trace, which is the property SC-003 is about.
CREDENTIAL: Final[dict[str, str]] = {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
    "bucket": "acme-observability",
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="aws_s3-resource-inventory",
    integration="aws_s3",
    capability="aws_s3_resource_inventory",
    arguments={"kind": "logs/", "start": "", "end": "", "group_by": "StorageClass"},
    responses=(
        xml_response(
            '<?xml version="1.0"?><ListBucketResult><Contents><Key>logs/a</Key><StorageClass>STANDARD</StorageClass></Contents><Contents><Key>logs/b</Key><StorageClass>GLACIER</StorageClass></Contents></ListBucketResult>'
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/acme-observability",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_s3-recent-changes",
    integration="aws_s3",
    capability="aws_s3_recent_changes",
    arguments={"kind": "logs/", "start": "", "end": "", "limit": 10},
    responses=(
        xml_response(
            '<?xml version="1.0"?><ListVersionsResult><Version><Key>logs/a</Key><VersionId>v2</VersionId><LastModified>2026-08-07T11:50:00Z</LastModified></Version></ListVersionsResult>'
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS S3",
    expected_paths=("/acme-observability",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
