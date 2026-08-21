"""AWS, end to end: capability, client, proxy-side SigV4, vendor.

These are the scenarios that would catch a signing regression, which is the
failure mode unique to this integration. The proxy signs; if it stopped, or
signed the wrong scope, the vendor would answer 403 and nothing else in the
suite would notice — the client's own tests assert the request it *built*, and
by construction that one is unsigned.

The second scenario walks CloudWatch's next token, which is the other silent
break: ``nextToken`` returned as an empty string on the last page rather than
omitted, so an emptiness check is what terminates the walk and a presence check
would follow the same page until the ceiling.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

CREDENTIAL: Final[dict[str, str]] = {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
}

LIST_LOG_GROUPS: Final = IntegrationScenario(
    key="aws-list-log-groups",
    integration="aws",
    capability="aws_list_log_groups",
    arguments={"prefix": "/aws/lambda/checkout"},
    responses=(
        json_response(
            {
                "logGroups": [
                    {
                        "logGroupName": "/aws/lambda/checkout",
                        "retentionInDays": 14,
                        "storedBytes": 8_402_112,
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 CloudWatch log group(s) in us-east-1",
)

FILTER_LOG_EVENTS: Final = IntegrationScenario(
    key="aws-filter-log-events",
    integration="aws",
    capability="aws_filter_log_events",
    arguments={
        "log_group": "/aws/lambda/checkout",
        "start_ms": 1_770_000_000_000,
        "end_ms": 1_770_000_600_000,
        "pattern": "?ERROR",
        "limit": 5,
    },
    responses=(
        json_response(
            {
                "events": [
                    {
                        "timestamp": 1_770_000_120_000,
                        "logStreamName": "2026/08/07/[$LATEST]abc",
                        "message": "ERROR Runtime exited: signal: killed",
                    }
                ],
                "nextToken": "page-2",
            }
        ),
        json_response(
            {
                "events": [
                    {
                        "timestamp": 1_770_000_180_000,
                        "logStreamName": "2026/08/07/[$LATEST]abc",
                        "message": "ERROR Task timed out after 30.00 seconds",
                    }
                ],
                # CloudWatch returns an empty token rather than omitting it, and
                # a presence check here would follow this page to the ceiling.
                "nextToken": "",
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="2 CloudWatch event(s) in /aws/lambda/checkout",
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (LIST_LOG_GROUPS, FILTER_LOG_EVENTS)

__all__ = ["CREDENTIAL", "FILTER_LOG_EVENTS", "LIST_LOG_GROUPS", "SCENARIOS"]
