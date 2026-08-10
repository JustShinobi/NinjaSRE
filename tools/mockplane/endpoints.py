"""Every endpoint the console consumes, and which of the two sources answers it.

The console reaches a deployment through one module, ``surfaces/console/client.py``,
so this list is enumerable rather than a matter of opinion — and a contract test
reads that module's source and fails when it names a path this catalogue does
not.

The split is the load-bearing part. The gateway serves runs, interactions,
approvals, memory, knowledge, configuration, identity, audit, the estate
inventory and continuous observation today. It does not serve anything
Proxmox-shaped — the node view, the storage view, the backup jobs. Those are
captured by reading the cluster directly and *projecting* the result into the
shape the future endpoint will return. When that work lands, the projection is
deleted rather than kept as a fallback: a fallback is how two sources of truth
start.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class EndpointSource(StrEnum):
    """Where a fixture for this endpoint comes from."""

    #: The live deployment answered it. The fixture is a recording.
    GATEWAY = "gateway"
    #: Nothing serves it yet; the fixture is projected from a direct read of the
    #: cluster into the shape the endpoint will return.
    PROJECTED = "projected"


@dataclass(frozen=True, slots=True)
class ConsoleEndpoint:
    """One endpoint the console calls, and everything the dataset needs about it."""

    method: str
    #: The path as the API document spells it, ``{name}`` for each variable part.
    path: str
    #: The fixture file's stem. Chosen rather than derived, because a filename a
    #: person can read is a filename a person can review.
    slug: str
    source: EndpointSource
    #: What the payload is *of*, in one phrase, for the coverage report.
    summary: str
    #: The key holding the list, when the payload is a collection. Empty when the
    #: payload is a single object.
    records_key: str = ""
    #: For a projection: the work that will serve it, so the fixture has somebody
    #: to hand over to. Empty for a gateway endpoint.
    arrives_with: str = ""
    #: Server-sent events rather than a JSON body. Validated as a stream, not
    #: against a response schema.
    streaming: bool = False
    #: Query parameters the console sends, so a coverage report can say what a
    #: fixture was recorded under.
    query: tuple[str, ...] = field(default_factory=tuple)


_GATEWAY: Final = EndpointSource.GATEWAY
_PROJECTED: Final = EndpointSource.PROJECTED

#: Names the work rather than a feature number, because a contributor cloning
#: this repository has the code and not the plan.
_PROXMOX: Final = "the Proxmox integration"


CONSOLE_ENDPOINTS: Final[tuple[ConsoleEndpoint, ...]] = (
    # --- Who is looking ---------------------------------------------------------
    ConsoleEndpoint(
        method="POST",
        path="/auth/sign-in",
        slug="sign-in",
        source=_GATEWAY,
        summary="exchange the local account's name and passphrase for a token",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/auth/me",
        slug="principal",
        source=_GATEWAY,
        summary="the calling principal and the permissions it holds",
    ),
    # --- Runs -------------------------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/runs",
        slug="runs",
        source=_GATEWAY,
        summary="recent runs, newest first",
        records_key="runs",
        query=("limit",),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/runs/{run_id}",
        slug="run-detail",
        source=_GATEWAY,
        summary="one run",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/runs/{run_id}/replay",
        slug="run-replay",
        source=_GATEWAY,
        summary="a run rebuilt from its recorded events alone",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/investigations/{run_id}/threads",
        slug="run-threads",
        source=_GATEWAY,
        summary="one run's conversation, its capability calls attached",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/investigations",
        slug="investigation-start",
        source=_GATEWAY,
        summary="starting an investigation",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/investigations/{run_id}/messages",
        slug="investigation-message",
        source=_GATEWAY,
        summary="queueing a message for the run's next turn",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/investigations/{run_id}/cancel",
        slug="investigation-cancel",
        source=_GATEWAY,
        summary="asking a run to stop at its next safe point",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/investigations/{run_id}/stream",
        slug="run-stream",
        source=_GATEWAY,
        summary="a run's events, live",
        streaming=True,
    ),
    # --- Interactions -----------------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/investigations/{run_id}/interactions",
        slug="interactions",
        source=_GATEWAY,
        summary="one run's open questions and approvals",
        records_key="interactions",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/interactions/{interaction_id}/answer",
        slug="interaction-answer",
        source=_GATEWAY,
        summary="answering a pending question",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/interactions/{interaction_id}/approve",
        slug="interaction-approve",
        source=_GATEWAY,
        summary="approving a pending change",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/interactions/{interaction_id}/reject",
        slug="interaction-reject",
        source=_GATEWAY,
        summary="rejecting a pending change, with a reason",
    ),
    # --- Approvals and rollback -------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/approvals",
        slug="approvals",
        source=_GATEWAY,
        summary="undecided approvals, longest-waiting first",
        records_key="approvals",
        query=("run_id", "limit"),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/approvals/{approval_id}",
        slug="approval-detail",
        source=_GATEWAY,
        summary="one approval with its rollback plan",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/approvals/{approval_id}/rollback",
        slug="approval-rollback",
        source=_GATEWAY,
        summary="recording that a stored rollback plan was executed",
    ),
    # --- Memory and knowledge ---------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/memory/search",
        slug="episodes",
        source=_GATEWAY,
        summary="episodes involving a component, most recent first",
        records_key="episodes",
        query=("component", "limit"),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/memory/stats",
        slug="memory-stats",
        source=_GATEWAY,
        summary="what the episodic corpus holds",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/topology/{node_id}",
        slug="topology",
        source=_GATEWAY,
        summary="a service's dependencies, dependents and blast radius",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/knowledge/documents",
        slug="documents",
        source=_GATEWAY,
        summary="the ingested knowledge documents",
        records_key="documents",
        query=("limit",),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/knowledge/documents/{document_id}",
        slug="document-detail",
        source=_GATEWAY,
        summary="one knowledge document with its passages",
    ),
    # --- Configuration ----------------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/config",
        slug="config-tree",
        source=_GATEWAY,
        summary="the organisation tree",
        records_key="nodes",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/autonomy/policy/{node_id}",
        slug="autonomy-policy",
        source=_GATEWAY,
        summary="what a node may do without asking, inheritance applied",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/autonomy/policy/{node_id}/bounds",
        slug="autonomy-bounds",
        source=_GATEWAY,
        summary="the freezes, budgets, overrides and stop bounding a node",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/config/{node_id}",
        slug="config-effective",
        source=_GATEWAY,
        summary="a node's effective configuration, every value attributed",
    ),
    ConsoleEndpoint(
        method="PUT",
        path="/v1/config/{node_id}",
        slug="config-write",
        source=_GATEWAY,
        summary="applying a patch to a node's own settings",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/config/{node_id}/preview",
        slug="config-preview",
        source=_GATEWAY,
        summary="what saving a patch would resolve to",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/config/{node_id}/catalogue",
        slug="config-catalogue",
        source=_GATEWAY,
        summary="what a node can run, and why anything else it cannot",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/autonomy/kill-switch",
        slug="kill-switch",
        source=_GATEWAY,
        summary="whether every automated write is currently stopped",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/config/{node_id}/fields",
        slug="config-fields",
        source=_GATEWAY,
        summary="every editable field, its type and range, and where its value comes from",
        records_key="fields",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/config/{node_id}/guardian",
        slug="config-guardian",
        source=_GATEWAY,
        summary="the shipped detector set as this node runs it, with its reasoning",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/config/{node_id}/integration-schemas",
        slug="config-integration-schemas",
        source=_GATEWAY,
        summary="the schemas a credential form is generated from",
        records_key="schemas",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/integrations",
        slug="integrations",
        source=_GATEWAY,
        summary="every installed integration",
        records_key="integrations",
    ),
    ConsoleEndpoint(
        method="PUT",
        path="/v1/integrations/{name}/credential",
        slug="credential-write",
        source=_GATEWAY,
        summary="storing a credential, described without any part of it being readable",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/integrations/{name}/verify",
        slug="integration-verify",
        source=_GATEWAY,
        summary="whether this team's credential for an integration is present and usable",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/v1/providers/{provider_id}/verify",
        slug="provider-verify",
        source=_GATEWAY,
        summary="what a real request to the provider's endpoint came back with",
    ),
    # --- Setting the deployment up ------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/setup/checklist",
        slug="setup-checklist",
        source=_GATEWAY,
        summary="what is left to set up, each step verified against its dependency",
        records_key="steps",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/providers",
        slug="providers",
        source=_GATEWAY,
        summary="every supported model provider and this deployment's state for it",
        records_key="providers",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/providers/{provider_id}",
        slug="provider-detail",
        source=_GATEWAY,
        summary="one provider, with everything a form needs in order to set it up",
    ),
    # --- Administration ---------------------------------------------------------
    ConsoleEndpoint(
        method="GET",
        path="/identity/principals",
        slug="principals",
        source=_GATEWAY,
        summary="everyone in this organisation",
        records_key="users",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/identity/grants",
        slug="grants",
        source=_GATEWAY,
        summary="the role grants held in this organisation",
        records_key="grants",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/identity/tokens",
        slug="tokens",
        source=_GATEWAY,
        summary="this organisation's machine tokens",
        records_key="tokens",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/identity/tokens",
        slug="token-create",
        source=_GATEWAY,
        summary="issuing a machine token",
    ),
    ConsoleEndpoint(
        method="POST",
        path="/identity/tokens/revoke",
        slug="token-revoke",
        source=_GATEWAY,
        summary="revoking tokens by id or by owner",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/audit/events",
        slug="audit-events",
        source=_GATEWAY,
        summary="matching audit events, most recent first",
        records_key="events",
        query=("actor", "action", "limit"),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/capabilities",
        slug="capabilities",
        source=_GATEWAY,
        summary="every declared tool and skill",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/health/ready",
        slug="health",
        source=_GATEWAY,
        summary="what the deployment reports about itself",
    ),
    # --- The estate ---------------------------------------------------------------
    # Served by the gateway. The projection these three used to carry is gone
    # rather than kept as a fallback, which is what the split at the top of this
    # module says happens when the work lands: a fallback is how two sources of
    # truth start.
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/summary",
        slug="estate-summary",
        source=_GATEWAY,
        summary="the estate in one line per kind, with the counts a tile shows",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/resources",
        slug="estate-resources",
        source=_GATEWAY,
        summary="every discovered resource",
        records_key="resources",
        query=("kind", "health", "source", "label", "parent", "limit"),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/resources/{resource_id}",
        slug="estate-resource-detail",
        source=_GATEWAY,
        summary="one resource, its health, its history and what touched it",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/ingress/sources",
        slug="ingress-sources",
        source=_GATEWAY,
        summary="where an alert router posts, and what body each receiver parses",
        records_key="sources",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/unresolved-alert-targets",
        slug="estate-unresolved-targets",
        source=_GATEWAY,
        summary="alerts that arrived for something this estate does not hold",
        records_key="targets",
    ),
    # --- Projected: what the Proxmox integration will serve ------------------------
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/nodes",
        slug="estate-nodes",
        source=_PROJECTED,
        summary="the cluster's nodes, their load and their failed units",
        records_key="nodes",
        arrives_with=_PROXMOX,
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/storage",
        slug="estate-storage",
        source=_PROJECTED,
        summary="datastores, thin pools and per-guest volume fill",
        records_key="datastores",
        arrives_with=_PROXMOX,
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/estate/backups",
        slug="estate-backups",
        source=_PROJECTED,
        summary="backup jobs, what they cover and whether they are enabled",
        records_key="jobs",
        arrives_with=_PROXMOX,
    ),
    # --- Continuous observation ----------------------------------------------------
    # Served by the gateway. The projection these four used to carry is gone
    # rather than kept as a fallback, for the reason the estate's was: a
    # fallback is how two sources of truth start.
    ConsoleEndpoint(
        method="GET",
        path="/v1/incidents",
        slug="incidents",
        source=_GATEWAY,
        summary="open and recently closed incidents",
        records_key="incidents",
        query=("state", "limit"),
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/incidents/{incident_id}",
        slug="incident-detail",
        source=_GATEWAY,
        summary="one incident, its subjects and the observations behind it",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/detectors",
        slug="detectors",
        source=_GATEWAY,
        summary="every declared detector, its coverage and what it concludes now",
        records_key="detectors",
    ),
    ConsoleEndpoint(
        method="GET",
        path="/v1/observations",
        slug="observations",
        source=_GATEWAY,
        summary="what the detectors see, most recent first",
        records_key="observations",
        query=("subject", "limit"),
    ),
)


_BY_SLUG: Final[Mapping[str, ConsoleEndpoint]] = {
    endpoint.slug: endpoint for endpoint in CONSOLE_ENDPOINTS
}


def gateway_endpoints() -> tuple[ConsoleEndpoint, ...]:
    """Return the endpoints a live deployment already answers."""
    return tuple(
        endpoint for endpoint in CONSOLE_ENDPOINTS if endpoint.source is EndpointSource.GATEWAY
    )


def projected_endpoints() -> tuple[ConsoleEndpoint, ...]:
    """Return the endpoints whose fixtures are projected from a direct read."""
    return tuple(
        endpoint for endpoint in CONSOLE_ENDPOINTS if endpoint.source is EndpointSource.PROJECTED
    )


def endpoint_by_slug(slug: str) -> ConsoleEndpoint:
    """Return the endpoint whose fixture file is named ``slug``.

    Raises:
        KeyError: no endpoint uses that slug.
    """
    return _BY_SLUG[slug]


def path_variables(path: str) -> tuple[str, ...]:
    """Return the names of the ``{variable}`` segments in ``path``, in order."""
    return tuple(
        segment[1:-1]
        for segment in path.split("/")
        if segment.startswith("{") and segment.endswith("}")
    )


def render_path(path: str, arguments: Mapping[str, str]) -> str:
    """Return ``path`` with each ``{name}`` replaced by ``arguments[name]``.

    Raises:
        KeyError: ``arguments`` does not name every variable in ``path``.
    """
    return "/".join(
        arguments[segment[1:-1]] if segment.startswith("{") and segment.endswith("}") else segment
        for segment in path.split("/")
    )


def _bind(template: str, path: str) -> dict[str, str] | None:
    """Return the variables ``path`` binds in ``template``, or ``None`` if it does not."""
    expected = template.split("/")
    actual = path.split("/")
    if len(expected) != len(actual):
        return None
    bound: dict[str, str] = {}
    for want, have in zip(expected, actual):
        if want.startswith("{") and want.endswith("}"):
            if not have:
                return None
            bound[want[1:-1]] = have
        elif want != have:
            return None
    return bound


def match_request(method: str, path: str) -> tuple[ConsoleEndpoint, dict[str, str]] | None:
    """Return the endpoint ``method path`` names and the variables it binds.

    A literal segment wins over a templated one, so ``/v1/knowledge/documents``
    resolves to the collection rather than being swallowed by the detail
    endpoint's template. Returns ``None`` when nothing in the catalogue serves
    it — which is a 404 at the mock, not a fallthrough to anything real.
    """
    wanted = method.upper()
    trimmed = path.split("?", 1)[0]
    best: tuple[ConsoleEndpoint, dict[str, str]] | None = None
    best_variables = len(trimmed.split("/")) + 1

    for endpoint in CONSOLE_ENDPOINTS:
        if endpoint.method != wanted:
            continue
        bound = _bind(endpoint.path, trimmed)
        if bound is None:
            continue
        if len(bound) < best_variables:
            best = (endpoint, bound)
            best_variables = len(bound)
    return best


__all__ = [
    "CONSOLE_ENDPOINTS",
    "ConsoleEndpoint",
    "EndpointSource",
    "endpoint_by_slug",
    "gateway_endpoints",
    "match_request",
    "path_variables",
    "projected_endpoints",
    "render_path",
]
