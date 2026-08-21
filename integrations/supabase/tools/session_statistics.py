"""Counting Supabase's sessions before reading any of them.

The first call of an investigation that reaches Supabase, and the one
most often skipped. A large answer has a shape — which group, which state, how
that distribution differs from an hour ago — and the shape decides which few
records are worth reading. Records chosen before the shape is known tell you
about those records and nothing else.

Source of truth: Supabase's ``/v1/projects``, read through the
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
from integrations.supabase.client import SupabaseClient
from integrations.supabase.schema import INTEGRATION

TOOL_NAME = "supabase_session_statistics"

#: The field the distribution is taken across when the caller names none. The
#: one that concentrates a failure most often for this vendor.
DEFAULT_GROUP_BY = "status"

#: How many records are read before the counting stops. The distribution is over
#: what was read, and the result says so — a statistic quoted as if it covered
#: everything is worse than no statistic.
MAX_RECORDS = 500

_USE_CASES = (
    "a latency alert on a service whose database may be the constraint",
    "deciding whether connections are exhausted or queries are simply slow",
)

# Anti-examples suppress this capability when they describe the incident. They
# are the field most often left empty, and without them the tool competes for a
# slot on every incident that happens to share a tag.
_ANTI_EXAMPLES = (
    "the text of a specific slow query, which the query capability returns",
    "application errors that never reached the database",
)


@tool(
    name=TOOL_NAME,
    display_name="Supabase session statistics",
    description=(
        "Group the current sessions by state or wait, so the answer says whether the database is blocked, saturated, or idle. This is the first database call in an investigation, before anything is asked about a query plan."
    ),
    domain="database",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    # Returns counts rather than record bodies, so nothing a user typed reaches
    # the result. The sampling sibling, which does return bodies, is a level up.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "database",
        "supabase",
        "postgres",
        "paas",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def supabase_session_statistics(
    scope: str = "",
    start: str = "",
    end: str = "",
    group_by: str = DEFAULT_GROUP_BY,
) -> CapabilityResult:
    """Return the distribution of Supabase's sessions across ``group_by``.

    ``start`` and ``end`` are Supabase's own time expressions. Both are
    passed through rather than defaulted here, because a capability that let the
    vendor choose the window would read the wrong hours without saying so.
    """
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(SupabaseClient, capability=TOOL_NAME)
    try:
        found = await client.list_sessions(scope, start=start, end=end, limit=MAX_RECORDS)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    buckets = counted(found.items, group_by)
    total = total_of(buckets)
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "scope": scope,
            "start": start,
            "end": end,
            "group_by": group_by,
            "buckets": list(buckets),
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.METRIC,
                summary=_summary(total, group_by, buckets, found.truncated),
                reference=f"supabase:session_statistics:{scope or 'all'}",
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
        return "no sessions were returned by Supabase for this request"
    leader = leader_of(buckets)
    tail = ", and more matched than were counted" if truncated else ""
    return (
        f"{total} sessions across {len(buckets)} {group_by} group(s); the largest is "
        f"{leader!r}{tail}"
    )
