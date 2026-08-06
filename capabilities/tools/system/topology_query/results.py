"""Turning a traversal into something an operator could paste into an incident update.

Three things are in the shaped answer that a naive rendering would leave out, and
each of them changes what the agent does with it.

**The two directions are labelled by what they are for.** Dependencies are where
the cause can be; dependents are the impact statement. An agent shown one
undifferentiated list of neighbours writes an impact statement that includes the
database the service reads from, which is not affected by the service being down.

**Truncation is a sentence, not a flag.** A blast radius cut at the result bound
is a *lower* bound on the impact, and an operator reading "four services
affected" when the real answer is "at least four" has published a wrong incident
update. The sentence says so in words the model will repeat.

**Verification travels with every service.** Topology is a claim about the estate
made at a particular moment by a particular source, and the honest way to present
one nobody has confirmed for a fortnight is beside the claim rather than in a
footnote. An unverified edge is marked in line.

The evidence returned is the *topology*, not the services. The claim it supports
is "the graph, as last verified, records these dependencies" — a recorded fact
about the graph rather than an observation of the running system, and presenting
it as the latter would be a fabricated citation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config.prompts.knowledge import (
    TOPOLOGY_EDGE,
    TOPOLOGY_EDGE_STALE,
    TOPOLOGY_EMPTY,
    TOPOLOGY_HEADER,
    TOPOLOGY_TRUNCATED,
)
from core.capability.metadata import EvidenceSource, EvidenceType
from core.capability.result import Evidence
from platform.knowledge.topology.models import ServiceNode
from platform.knowledge.topology.queries import ServiceTopology

#: What each direction is *for*, said in the answer rather than left to be
#: inferred from which list a service is in.
DEPENDENCY_RELATION = "a dependency — its failure can cause this one"
DEPENDENT_RELATION = "a dependent — it is affected when this one fails"

#: Prefixes the reference on a topology claim, so a reader can tell a graph
#: record from something observed during this investigation.
TOPOLOGY_REFERENCE_PREFIX = "topology"


def describe_service(service: ServiceNode, *, relation: str, moment: datetime) -> str:
    """Return one service as the model is shown it, staleness included."""
    line = TOPOLOGY_EDGE.format(
        name=service.node_id,
        kind=service.kind.value,
        relation=relation,
        verified=service.verified_at.date().isoformat() if service.verified_at else "never",
    )
    return f"{line}{TOPOLOGY_EDGE_STALE}" if service.stale_at(moment) else line


def render(answer: ServiceTopology, *, moment: datetime) -> str:
    """Return the whole answer as one block of text, empty answers included."""
    if answer.empty:
        return TOPOLOGY_EMPTY.format(service=answer.service)

    lines = [
        TOPOLOGY_HEADER.format(
            service=answer.service,
            depth=answer.depth,
            dependencies=len(answer.dependencies.services),
            dependents=len(answer.dependents.services),
        )
    ]
    if answer.dependencies.services:
        lines.append("Depends on:")
        lines.extend(
            describe_service(service, relation=DEPENDENCY_RELATION, moment=moment)
            for service in answer.dependencies.services
        )
    if answer.dependents.services:
        lines.append("Depended on by:")
        lines.extend(
            describe_service(service, relation=DEPENDENT_RELATION, moment=moment)
            for service in answer.dependents.services
        )
    if answer.blast_radius.reaches:
        lines.append(
            "Blast radius, nearest first: "
            + ", ".join(
                f"{entry.service.node_id} ({entry.depth} hop(s))"
                for entry in answer.blast_radius.reaches
            )
        )
    if answer.truncated:
        lines.append(TOPOLOGY_TRUNCATED)

    return "\n".join(lines)


def evidence_for(answer: ServiceTopology) -> tuple[Evidence, ...]:
    """Return one evidence entry for the topology this answer records.

    One entry rather than one per service. The claim is about the graph — "as
    last verified, these are the recorded dependencies" — and splitting it into
    a claim per edge would put twenty observations in the trace where one
    recorded fact belongs.
    """
    if answer.empty:
        return ()
    return (
        Evidence(
            source=EvidenceSource.KNOWLEDGE_BASE,
            evidence_type=EvidenceType.TOPOLOGY,
            summary=(
                f"The topology graph records {len(answer.dependencies.services)} "
                f"dependency(ies) and {len(answer.dependents.services)} dependent(s) for "
                f"{answer.service}, with {len(answer.blast_radius.reaches)} service(s) within "
                f"a depth-{answer.depth} blast radius"
                f"{' (partial: the result bound was reached)' if answer.truncated else ''}. "
                f"This is what the graph records, not an observation of the running system."
            ),
            reference=f"{TOPOLOGY_REFERENCE_PREFIX}:{answer.service}",
        ),
    )


def shape(answer: ServiceTopology, *, moment: datetime) -> dict[str, Any]:
    """Return the structured value the tool hands back.

    Both a rendered block and the structured topology. The text is what the model
    reads; the structure is what the trace, the console, and the evaluation
    harness read, and deriving one from the other afterwards is how the two come
    to disagree.
    """
    return {
        "service": answer.service,
        "depth": answer.depth,
        "truncated": answer.truncated,
        "text": render(answer, moment=moment),
        "dependencies": [_service(service, moment) for service in answer.dependencies.services],
        "dependents": [_service(service, moment) for service in answer.dependents.services],
        "blast_radius": [
            {**_service(entry.service, moment), "hops": entry.depth}
            for entry in answer.blast_radius.reaches
        ],
    }


def _service(service: ServiceNode, moment: datetime) -> dict[str, Any]:
    """Return one service as the structured value carries it."""
    return {
        "id": service.node_id,
        "kind": service.kind.value,
        "environment": service.environment,
        "owner": service.owner,
        "annotations": dict(service.annotations),
        "verified_at": service.verified_at.isoformat() if service.verified_at else None,
        "unverified": service.stale_at(moment),
        "discovered_by": service.source,
    }


__all__ = [
    "DEPENDENCY_RELATION",
    "DEPENDENT_RELATION",
    "TOPOLOGY_REFERENCE_PREFIX",
    "describe_service",
    "evidence_for",
    "render",
    "shape",
]
