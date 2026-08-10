"""Asking what changed for a resource before it broke, correlated rather than timed.

The question an SRE asks first, and the one an investigation could not ask until
now. Everything about the shape of this tool is chosen to keep the model from
turning a coincidence into a cause.

**It takes a resource, not a time range alone.** A tool that answered "what
changed in the last thirty minutes" would return whatever a busy cluster did in
half an hour, and the model would pick the plausible-sounding one. Answering per
resource means the correlation runs through the estate — a path names a
component, a component's own state names what it built — and the result says how
far along that chain it got.

**The correlation is done before the model sees it.** The rule is a property of
the deployment's repository layout and its apply record, and a model asked to
re-derive it from paths would re-derive it differently each run. What arrives is
already graded.

**The empty answer is an answer.** A quiet resource comes back with a sentence
naming what was consulted and how many changes were in the window at all, and a
deployment with nothing configured comes back unavailable rather than quiet.
Those are three different things and only one of them means "changes are not the
cause here".

Source of truth: whichever change sources the deployment composed — the
repository's own apply record, and any git host it has a credential for.
"""

from __future__ import annotations

from datetime import UTC, datetime

from capabilities.tools.changes import binding, results
from config.constants.changes import CHANGES_TOOL_NAME, DEFAULT_CHANGE_WINDOW_HOURS
from config.prompts.changes import NO_CHANGE_SOURCE
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.changes.errors import ChangeWindowInvalid
from platform.changes.models import ChangeWindow

TOOL_NAME = CHANGES_TOOL_NAME

_USE_CASES = (
    "checking whether anything was deployed shortly before a symptom started",
    "ruling deploys out, so an investigation stops looking at them and looks elsewhere",
    "finding which apply touched the component that manages an affected workload",
)

# Anti-examples suppress this capability when they describe the incident. The
# first is the important one: called on the alert text before an affected
# resource is established, this returns whatever the cluster did in the window
# and invites the model to pick one.
_ANTI_EXAMPLES = (
    "asking on the alert text before an affected resource has been identified",
    "reading what a change contained, which this deliberately never reports",
    "listing a repository's history, which is a report rather than an investigation",
)


@tool(
    name=TOOL_NAME,
    display_name="Changes in window",
    description=(
        "Return what changed for a specific resource in a window, correlated through the "
        "resource rather than by time: each result says whether the change altered something "
        "that manages this resource, touched policy the resource shares, or merely landed in "
        "the same window. A change reported as a temporal coincidence is not evidence of a "
        "cause. An empty answer is a finding — it states that nothing touched this resource, "
        "and names what was consulted to establish it. Call this once you know which resource "
        "is affected, not on the alert text."
    ),
    domain="changes",
    evidence_source=results.CHANGE_EVIDENCE_SOURCE,
    evidence_type=EvidenceType.CHANGE,
    # Reads a repository's apply record and a git host's commit listing, and
    # writes nothing anywhere. Sensitive rather than plain read because the
    # result carries commit messages, which are text people wrote.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    # No integration is declared. The infra-apply source reads a directory and
    # needs no credential, so gating this on a vendor would hide it from the
    # deployment it is most useful to; what is missing is reported at call time.
    tags=("changes", "deploy", "git", "vcs", "correlation", "blast-radius"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def changes_in_window(
    resource: str,
    hours: float = DEFAULT_CHANGE_WINDOW_HOURS,
) -> CapabilityResult:
    """Return what changed for ``resource`` in the last ``hours``, graded.

    Four outcomes, because the next move differs for each. Correlated changes
    narrow the investigation to something somebody did. An answer with only
    temporal coincidences rules deploys out and says so. A resource this estate
    does not hold is an alert naming something nobody is watching, which is its
    own finding. And an unconfigured deployment is told what to point at, rather
    than being handed a negative it did not earn.
    """
    access = binding.current()
    if access is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            NO_CHANGE_SOURCE,
            detail=f"asked about {resource!r} over {hours} hour(s)",
        )

    try:
        window = ChangeWindow.ending(datetime.now(UTC), hours=hours)
    except ChangeWindowInvalid as refusal:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            str(refusal),
            detail=f"asked about {resource!r}",
        )

    answer = await access.changes_for(resource, window=window)
    if answer is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.NOT_FOUND,
            f"this estate holds no resource called {resource!r}, so there is nothing to "
            f"correlate a change against. An alert naming something the estate does not "
            f"hold is itself a finding.",
            detail=f"over the {hours} hour(s) ending now",
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value=results.shape(answer),
        evidence=results.evidence_for(answer),
        truncated=answer.truncated,
    )


__all__ = ["TOOL_NAME", "changes_in_window"]
