"""Reading a capped number of Argo CD's runs, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Argo CD's ``/api/v1/applications``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.argocd.client import ArgocdClient
from integrations.argocd.schema import INTEGRATION

TOOL_NAME = "argocd_failed_runs"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "finding the first failing run after a period of green ones",
    "checking whether a deployment succeeded before blaming the release",
)

_ANTI_EXAMPLES = (
    "whether failures are unusual, which the statistics answer",
    "an application error unrelated to any build",
)


@tool(
    name=TOOL_NAME,
    display_name="Argo CD failed runs",
    description=(
        "Return the failed runs for a project in a window, newest first and capped, with the stage that failed. Use it after the statistics: the first failure in a run of them is the one worth reading."
    ),
    domain="cicd",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    # Returns records the vendor's control plane produced rather than anything
    # a user typed, so a plain read is the honest level.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "cicd",
        "argocd",
        "gitops",
        "deployments",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def argocd_failed_runs(
    project: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Argo CD's runs, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ArgocdClient, capability=TOOL_NAME)
    try:
        found = await client.list_failed_runs(
            project, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "project": project,
            "start": start,
            "end": end,
            "runs": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.EVENT,
                summary=f"{len(entries)} runs from Argo CD{tail}",
                reference=f"argocd:failed_runs:{project or 'all'}",
            ),
        ),
    )
