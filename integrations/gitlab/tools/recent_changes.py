"""Reading a capped number of GitLab's changes, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: GitLab's ``/api/v4/merge_requests``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.gitlab.client import GitlabClient
from integrations.gitlab.schema import INTEGRATION

TOOL_NAME = "gitlab_recent_changes"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "identifying the release that lines up with the start of a symptom",
    "reading what changed in a service between two known-good times",
)

_ANTI_EXAMPLES = (
    "how much changed overall, which the statistics answer more cheaply",
    "a configuration change made outside version control",
)


@tool(
    name=TOOL_NAME,
    display_name="GitLab recent changes",
    description=(
        "Return the changes merged into a repository in a window, newest first and capped, with title and author. This is what turns a time correlation into a specific change somebody can read."
    ),
    domain="vcs",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "vcs",
        "gitlab",
        "git",
        "changes",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def gitlab_recent_changes(
    repository: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of GitLab's changes, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(GitlabClient, capability=TOOL_NAME)
    try:
        found = await client.list_pull_requests(
            repository, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "repository": repository,
            "start": start,
            "end": end,
            "changes": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CHANGE,
                summary=f"{len(entries)} changes from GitLab{tail}",
                reference=f"gitlab:recent_changes:{repository or 'all'}",
            ),
        ),
    )
