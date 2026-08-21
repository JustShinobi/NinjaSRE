"""Counting AWS ECS's resources before reading any of them.

The first call of an investigation that reaches AWS ECS, and the one
most often skipped. A large answer has a shape — which group, which state, how
that distribution differs from an hour ago — and the shape decides which few
records are worth reading. Records chosen before the shape is known tell you
about those records and nothing else.

Source of truth: AWS ECS's ``/``, read through the
bounded page walk in ``client.py`` and grouped by one field.
"""

from __future__ import annotations

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations._base.payload import counted, leader_of, total_of
from integrations.aws_ecs.client import AwsEcsClient
from integrations.aws_ecs.schema import INTEGRATION

TOOL_NAME = "aws_ecs_resource_inventory"

#: The field the distribution is taken across when the caller names none. The
#: one that concentrates a failure most often for this vendor.
DEFAULT_GROUP_BY = "cluster"

#: How many records are read before the counting stops. The distribution is over
#: what was read, and the result says so — a statistic quoted as if it covered
#: everything is worse than no statistic.
MAX_RECORDS = 500

_USE_CASES = (
    "an alert naming a service whose current state is unknown",
    "establishing whether a failure is one resource or a whole class of them",
)

# Anti-examples suppress this capability when they describe the incident. They
# are the field most often left empty, and without them the tool competes for a
# slot on every incident that happens to share a tag.
_ANTI_EXAMPLES = (
    "why a resource changed, which the change history answers",
    "application-level errors, which a control plane never sees",
)


@tool(
    name=TOOL_NAME,
    display_name="AWS ECS resource inventory",
    description=(
        "List the resources of one kind, grouped by state, so the answer is the distribution rather than every resource. Reach for it when the question is how much of the estate is in a bad state rather than which one is."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    # Returns counts rather than record bodies, so nothing a user typed reaches
    # the result. The sampling sibling, which does return bodies, is a level up.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "cloud_control_plane",
        "aws_ecs",
        "aws",
        "containers",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def aws_ecs_resource_inventory(
    kind: str = "",
    start: str = "",
    end: str = "",
    group_by: str = DEFAULT_GROUP_BY,
) -> CapabilityResult:
    """Return the distribution of AWS ECS's resources across ``group_by``.

    ``start`` and ``end`` are AWS ECS's own time expressions. Both are
    passed through rather than defaulted here, because a capability that let the
    vendor choose the window would read the wrong hours without saying so.
    """
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(AwsEcsClient, capability=TOOL_NAME)
    try:
        found = await client.list_resources(kind, start=start, end=end, limit=MAX_RECORDS)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    buckets = counted(found.items, group_by)
    total = total_of(buckets)
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "kind": kind,
            "start": start,
            "end": end,
            "group_by": group_by,
            "buckets": list(buckets),
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CONFIGURATION,
                summary=_summary(total, group_by, buckets, found.truncated),
                reference=f"aws_ecs:resource_inventory:{kind or 'all'}",
            ),
        ),
    )


def _summary(
    total: int,
    group_by: str,
    buckets: tuple[dict[str, object], ...],
    truncated: bool,
) -> str:
    """Return the one line a conclusion can be checked against."""
    if not buckets:
        return "no resources were returned by AWS ECS for this request"
    leader = leader_of(buckets)
    tail = ", and more matched than were counted" if truncated else ""
    return (
        f"{total} resources across {len(buckets)} {group_by} group(s); the largest is "
        f"{leader!r}{tail}"
    )
