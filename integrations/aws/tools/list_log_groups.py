"""Finding out which log groups exist before querying one that does not.

The cheapest call in the integration, and the one that saves the most time when
it is made first. A CloudWatch query against a log group whose name is off by a
prefix returns an error that names the group, and an investigation that guessed
the name spends a turn discovering the guess was wrong. Listing by prefix costs
one call and removes the whole class.

It is also the AWS half of "narrow before you read": CloudWatch has no
server-side aggregation, so the group *is* the first dimension, and choosing it
deliberately is what the statistics call does for vendors that have one.

Source of truth: CloudWatch Logs ``DescribeLogGroups``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.aws.client import CloudWatchLogsClient
from integrations.aws.schema import INTEGRATION

TOOL_NAME = "aws_list_log_groups"

_USE_CASES = (
    "confirming a log group's exact name before querying it",
    "finding which log groups a service writes to when the naming is not obvious",
    "checking whether a Lambda or ECS task logs anywhere at all",
)

_ANTI_EXAMPLES = (
    "reading log content, which filtering events does",
    "listing every group in a large account with no prefix, which returns noise",
    "discovering non-logging AWS resources, which this cannot see",
)


@tool(
    name=TOOL_NAME,
    display_name="AWS list log groups",
    description=(
        "List CloudWatch log groups in the configured region, optionally narrowed by name "
        "prefix. Call it before filtering events when the exact group name is not certain "
        "— a query against a mistyped group fails in a way that costs a turn. Returns "
        "names, retention, and stored size."
    ),
    domain="logstore",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    # Names and metadata of log groups. No log content, so nothing here can
    # carry what an application wrote.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("logs", "cloudwatch", "aws", "logstore"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def aws_list_log_groups(prefix: str = "") -> CapabilityResult:
    """Return the CloudWatch log groups whose names start with ``prefix``."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(CloudWatchLogsClient, capability=TOOL_NAME)
    try:
        groups = await client.describe_log_groups(prefix=prefix)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    described = [_group(group) for group in groups]
    return CapabilityResult.ok(
        TOOL_NAME,
        value={"prefix": prefix, "region": client.region, "log_groups": described},
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CONFIGURATION,
                summary=(
                    f"{len(described)} CloudWatch log group(s) in {client.region}"
                    + (f" starting with {prefix!r}" if prefix else "")
                ),
                reference=f"aws:logs:{client.region}:describe-log-groups:{prefix}",
            ),
        ),
    )


def _group(group: dict[str, Any]) -> dict[str, Any]:
    """Return the fields of one log group that decide what to query next.

    Retention matters most: a group retaining three days cannot answer a
    question about last week, and an empty result from one is not evidence that
    nothing happened.
    """
    return {
        "name": str(group.get("logGroupName", "")),
        "retention_days": group.get("retentionInDays"),
        "stored_bytes": group.get("storedBytes"),
    }
