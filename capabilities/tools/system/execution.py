"""Computation over gathered evidence, and the sandbox it is not allowed without.

Some analysis is arithmetic a language model should not be doing in its head:
correlating two thousand log timestamps against a deploy history, or fitting a
trend across a week of metric points. Running code is the right answer for
those.

Running code is also the single largest blast radius in the system, which is
why the declaration requires a sandbox profile and why this module executes
nothing until one exists. A tool that ran the code anyway "because the sandbox
is coming" would be arbitrary execution with the safety documented rather than
implemented, and the gap between those two is where the incident lives.

The declaration lands now because the catalogue's shape has to be right for
selection and evaluation to be measured against it. The execution lands with
the sandbox, and until then the unavailability is explicit, classified, and
visible in the trace.
"""

from __future__ import annotations

from core.capability.decorator import tool
from core.capability.metadata import (
    EvidenceSource,
    EvidenceType,
    Requirements,
    SideEffectLevel,
)
from core.capability.result import CapabilityErrorClass, CapabilityResult

#: The profile this tool runs under: no network, no credentials, and access
#: only to evidence the investigation has already gathered.
ANALYSIS_SANDBOX_PROFILE = "analysis"

_ANALYSIS_USE_CASES = (
    "correlate timestamps across two evidence sets too large to read directly",
    "compute a distribution or percentile over gathered metric points",
    "diff two configuration snapshots field by field",
)

_ANALYSIS_ANTI_EXAMPLES = (
    "calling an external API, which belongs to that vendor's own tool",
    "running a command against a production system",
)

_UNAVAILABLE = (
    f"The {ANALYSIS_SANDBOX_PROFILE!r} sandbox profile is not available in this "
    "deployment, and analysis code is never executed outside one. Reason over the "
    "evidence directly, or gather a narrower slice of it."
)


@tool(
    name="run_analysis_code",
    display_name="Run analysis code",
    description=(
        "Execute Python over evidence already gathered in this investigation, inside a "
        "sandbox with no network and no credentials. Use for arithmetic over large "
        "evidence sets, never to reach an external system."
    ),
    domain="methodology",
    evidence_source=EvidenceSource.SANDBOX,
    evidence_type=EvidenceType.ANALYSIS,
    # Not `read`: the code sees whatever evidence the investigation has gathered,
    # which may include masked customer identifiers. The sandbox bounds what it
    # can reach; it does not change what it can see.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=False,
    requires=Requirements(sandbox_profiles=(ANALYSIS_SANDBOX_PROFILE,)),
    tags=("analysis", "computation", "sandbox"),
    use_cases=_ANALYSIS_USE_CASES,
    anti_examples=_ANALYSIS_ANTI_EXAMPLES,
)
def run_analysis_code(code: str, evidence_references: list[str]) -> CapabilityResult:
    """Return the computation's result, or an explicit unavailability.

    There is no path through this function that executes ``code``. The sandbox
    binding is a later feature, and a tool that ran first and was contained
    afterwards would be the wrong way round.

    The detail records the size of what was refused and the evidence it would
    have read, without putting the code itself into the trace — a refused
    program is not evidence, and it may be long.
    """
    return CapabilityResult.failed(
        "run_analysis_code",
        CapabilityErrorClass.UNAVAILABLE,
        _UNAVAILABLE,
        detail=(
            f"refused {len(code)} characters of analysis code over "
            f"{len(evidence_references)} evidence reference(s)"
        ),
    )
