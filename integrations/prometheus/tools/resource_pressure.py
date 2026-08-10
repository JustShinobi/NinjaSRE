"""What a guest is short of, read from the host rather than from inside it.

The other Prometheus capability takes a query somebody wrote. This one takes a
*resource* and builds the query, and the reason that difference exists is a
correctness rule rather than a convenience.

A container shares the host's kernel. Every memory, CPU and disk counter visible
inside it is the host's cgroup accounting seen through a namespace that was
never designed to publish it, so a query aimed at an in-guest collector returns
a well-formed series with a plausible number in it that is about something else.
Nothing downstream can tell that apart from a correct answer — not the result
shape, not the status code, not the model reading it.

So the selector is not written here. It is derived from the estate's signal map,
which is the one place the rule lives: the map says *Prometheus, keyed by vmid*,
and this capability turns that into a host-side series filtered by that guest's
own identifier. The query it built travels in the result, so a conclusion drawn
from it can be checked against the question that was actually asked.

Source of truth: the host's exporter, through ``/api/v1/query_range``.
"""

from __future__ import annotations

from typing import Any

from config.constants.signals import VERIFY_WINDOW_MINUTES
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.prometheus.client import PrometheusClient
from integrations.prometheus.pressure import PressureQuery, pressure_queries, pressure_source
from integrations.prometheus.schema import INTEGRATION

TOOL_NAME = "prometheus_resource_pressure"

#: How many samples of one series are read. The question is "is it under
#: pressure", which a handful of points answers; a full window of samples is a
#: chart nobody is drawing.
MAX_SAMPLES = 20

_USE_CASES = (
    "how much memory, CPU or disk a hypervisor guest is using, without asking inside it",
    "checking whether a container that is being OOM-killed is at its own ceiling",
    "resource usage for a guest where no agent runs and nothing can be installed",
)

_ANTI_EXAMPLES = (
    "an arbitrary PromQL expression, which prometheus_metric_statistics evaluates",
    "which alerts are firing, which prometheus_active_alerts answers",
    "reading a log line, which a metric never contains",
)


@tool(
    name=TOOL_NAME,
    display_name="Prometheus resource pressure",
    description=(
        "Return what one estate resource is short of — memory, CPU, disk — with the query "
        "built from the signal map rather than written by hand. For a container the series "
        "read are the host's, keyed by the guest's own identifier, because a container "
        "shares the host's kernel and counters read from inside it report the host's "
        "figures under the guest's name."
    ),
    domain="metrics",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("metrics", "prometheus", "promql", "pressure", "estate"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def prometheus_resource_pressure(
    resource_kind: str,
    vmid: int = 0,
    address: str = "",
    start: str = "",
    end: str = "",
) -> CapabilityResult:
    """Return what the host says one guest is short of.

    ``resource_kind`` is the estate's own kind — ``container``, ``virtual_machine``,
    ``node`` — and it plus the key is what the signal map resolves. A kind the map
    has no pressure series for, or a guest the estate holds no identifier for, is
    refused with the reason rather than answered with an unfiltered query: a
    selector with nothing in it matches every guest on the cluster, and the number
    that comes back looks exactly like an answer.
    """
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    source = pressure_source(resource_kind, vmid=vmid, address=address)
    if source is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            (
                f"the signal map answers no pressure question about a {resource_kind!r} "
                f"keyed by {vmid or address or 'nothing'}"
            ),
            detail=(
                "either this kind publishes no resource-usage series, or the estate holds "
                "no identifier to filter one by. A query built without one matches every "
                "guest on the cluster, and the number that comes back looks exactly like "
                "an answer about this one."
            ),
        )

    queries = pressure_queries(source, kind=resource_kind)
    client = access.client(PrometheusClient, capability=TOOL_NAME)
    readings: list[dict[str, Any]] = []
    try:
        for query in queries:
            found = await client.query_metric(query.promql, start=start, end=end, limit=MAX_SAMPLES)
            readings.append(
                {
                    **query.to_record(),
                    "series": len(found),
                    "samples": list(found.items),
                    "truncated": found.truncated,
                }
            )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "resource_kind": resource_kind,
            "keyed_by": source.keyed_by,
            "key": source.key,
            "why_this_source": source.detail,
            "readings": readings,
        },
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.METRIC,
                summary=_summary(resource_kind, source.key, queries, readings),
                reference=f"prometheus:pressure:{source.keyed_by}/{source.key}",
            ),
        ),
    )


def _summary(
    resource_kind: str,
    key: str,
    queries: tuple[PressureQuery, ...],
    readings: list[dict[str, Any]],
) -> str:
    """Return the one line a conclusion can be checked against.

    It names the key the series were filtered by, deliberately. A summary that
    said only "memory is at 94%" is one nobody can check against the guest it was
    supposed to be about.
    """
    answered = [reading for reading in readings if int(reading["series"]) > 0]
    if not answered:
        return (
            f"the host published no {', '.join(query.name for query in queries)} series for "
            f"{resource_kind} {key} over this window — which is a gap in the exporter rather "
            f"than a guest under no pressure"
        )
    named = ", ".join(str(reading["name"]) for reading in answered)
    return (
        f"{resource_kind} {key}: {named} read from the host's own series, filtered by this "
        f"guest's identifier, over the last {VERIFY_WINDOW_MINUTES} minutes or the window given"
    )


__all__ = ["MAX_SAMPLES", "TOOL_NAME", "prometheus_resource_pressure"]
