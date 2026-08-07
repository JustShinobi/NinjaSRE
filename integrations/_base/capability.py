"""The two results every vendor capability returns without thinking about it.

A capability that reaches a vendor has exactly two failure paths it did not
write itself: nothing bound the integration, and the vendor said no. Both are
values rather than exceptions — a tool that raises ends the turn and takes the
trace with it — and both have a right classification that is easy to get subtly
wrong.

Getting them wrong is expensive in a way that does not show up in review. A tool
reporting an unconfigured integration as an empty answer teaches the
investigation that Datadog had no matching logs, and the conclusion drawn from
that is "the errors are not in the logs" rather than "we did not look". A tool
reporting a 429 as ``INTERNAL`` makes the loop stop retrying something that would
have worked on the second attempt.

So both are written once here, and a vendor capability's own code is the part
that is actually about the vendor.
"""

from __future__ import annotations

from core.capability.result import CapabilityErrorClass, CapabilityResult
from integrations._base.errors import IntegrationError


def unconfigured(capability: str, integration: str) -> CapabilityResult:
    """Return what a capability reports when nothing bound its integration.

    ``UNAVAILABLE`` rather than an empty answer, and the message names the
    integration: an investigation told "no results" concludes something about
    the estate, and one told "datadog is not configured for this team" concludes
    something about the deployment. Only the second is true.
    """
    return CapabilityResult.failed(
        capability,
        CapabilityErrorClass.UNAVAILABLE,
        f"{integration} is not configured for this team, so nothing was read. This is a "
        f"deployment gap rather than a finding: the absence of results here says nothing "
        f"about the estate.",
        detail=f"no {integration} access is bound in this process",
    )


def vendor_failure(capability: str, error: IntegrationError) -> CapabilityResult:
    """Return one vendor failure as the classified value the model reads back.

    The classification comes from the error rather than from the call site, so
    two capabilities against the same vendor cannot disagree about what a 403
    means — and the loop's behaviour therefore does not depend on which of them
    it happened to call.
    """
    classified = error.to_capability_error()
    return CapabilityResult.failed(
        capability,
        classified.classification,
        classified.message,
        detail=classified.detail,
    )


__all__ = [
    "unconfigured",
    "vendor_failure",
]
