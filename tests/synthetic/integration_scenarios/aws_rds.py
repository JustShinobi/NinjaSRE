"""AWS RDS, end to end: capability, client, proxy, injection, vendor.

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
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="aws_rds-resource-inventory",
    integration="aws_rds",
    capability="aws_rds_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "DBInstanceStatus"},
    responses=(
        xml_response(
            '<?xml version="1.0"?><DescribeDBInstancesResponse><DBInstances><DBInstance><DBInstanceIdentifier>checkout</DBInstanceIdentifier><DBInstanceStatus>available</DBInstanceStatus></DBInstance><DBInstance><DBInstanceIdentifier>reporting</DBInstanceIdentifier><DBInstanceStatus>modifying</DBInstanceStatus></DBInstance></DBInstances></DescribeDBInstancesResponse>'
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 resources across",
    expected_paths=("/",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="aws_rds-recent-changes",
    integration="aws_rds",
    capability="aws_rds_recent_changes",
    arguments={"kind": "", "start": "", "end": "", "limit": 10},
    responses=(
        xml_response(
            '<?xml version="1.0"?><DescribeEventsResponse><Events><Event><SourceIdentifier>checkout</SourceIdentifier><Message>Multi-AZ failover completed</Message></Event></Events></DescribeEventsResponse>'
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from AWS RDS",
    expected_paths=("/",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
