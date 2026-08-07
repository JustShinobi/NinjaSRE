"""When a workload last changed, which is usually the answer.

The control-plane methodology is "recent changes first", and in Kubernetes the
recent change is a rollout. A deployment's replica sets *are* its history:
Kubernetes keeps one per revision, each stamped with when it was created and
which image it ran, and comparing the current one's timestamp against the
symptom's onset answers "did something ship" in a single call.

The comparison is deliberately left to the caller. This returns the revisions
and their times; whether four minutes before the alert is a coincidence is a
judgement that depends on how often this team deploys, and a capability that
asserted causality would be asserting something it cannot know.

Source of truth: the apps API's deployment object and its replica sets, matched
by the deployment's own selector labels.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.kubernetes.client import KubernetesClient
from integrations.kubernetes.schema import INTEGRATION

TOOL_NAME = "kubernetes_rollout_history"

#: The annotation Kubernetes stamps a replica set with to record which revision
#: of the deployment it is.
REVISION_ANNOTATION = "deployment.kubernetes.io/revision"

_USE_CASES = (
    "checking whether a deployment rolled out shortly before a symptom appeared",
    "finding which image the previous revision ran, to decide what a rollback restores",
    "establishing that nothing shipped, which rules out a whole class of cause",
)

_ANTI_EXAMPLES = (
    "changes that did not go through this deployment — a config map, a feature flag",
    "why a rollout failed, which the workload's events say and this does not",
    "the code in a change, which the version-control integration reads",
)


@tool(
    name=TOOL_NAME,
    display_name="Kubernetes rollout history",
    description=(
        "Return a deployment's revisions, newest first, with the image and creation time "
        "of each. Answers 'did something ship, and when' in one call — compare the newest "
        "revision's time against the symptom's onset. It reports the timeline and does "
        "not claim causality."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    # Deployment and replica-set metadata: images, revisions, timestamps.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("kubernetes", "deploy", "rollout", "change", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def kubernetes_rollout_history(deployment: str, namespace: str) -> CapabilityResult:
    """Return ``deployment``'s revisions in ``namespace``, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(KubernetesClient, capability=TOOL_NAME)
    try:
        found = await client.deployment(deployment, namespace=namespace)
        replica_sets = await client.replica_sets(
            namespace=namespace, label_selector=_selector(found)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    revisions = sorted(
        (_revision(replica_set) for replica_set in replica_sets),
        key=lambda revision: revision["revision"] or 0,
        reverse=True,
    )
    return CapabilityResult.ok(
        TOOL_NAME,
        value={"deployment": deployment, "namespace": namespace, "revisions": revisions},
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CHANGE,
                summary=_summary(deployment, revisions),
                reference=f"kubernetes:deployment:{namespace}/{deployment}",
            ),
        ),
    )


def _selector(deployment: dict[str, Any]) -> str:
    """Return the deployment's own label selector, as a query string.

    Matching replica sets by the deployment's selector rather than by name
    prefix: a deployment called ``checkout`` and one called ``checkout-canary``
    share a prefix and do not share a selector, and a prefix match would put one
    workload's rollout history into the other's investigation.
    """
    spec = deployment.get("spec", {})
    selector = spec.get("selector", {}) if isinstance(spec, dict) else {}
    labels = selector.get("matchLabels", {}) if isinstance(selector, dict) else {}
    if not isinstance(labels, dict):
        return ""
    return ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def _revision(replica_set: dict[str, Any]) -> dict[str, Any]:
    """Return one replica set as a revision record."""
    metadata = replica_set.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    annotations = metadata.get("annotations", {})
    annotations = annotations if isinstance(annotations, dict) else {}
    raw_revision = str(annotations.get(REVISION_ANNOTATION, ""))
    return {
        "revision": int(raw_revision) if raw_revision.isdigit() else None,
        "name": str(metadata.get("name", "")),
        "created_at": str(metadata.get("creationTimestamp", "")),
        "image": _image(replica_set),
        "replicas": replica_set.get("status", {}).get("replicas"),
    }


def _image(replica_set: dict[str, Any]) -> str:
    """Return the first container image this revision runs, or an empty string."""
    spec = replica_set.get("spec", {})
    template = spec.get("template", {}) if isinstance(spec, dict) else {}
    pod_spec = template.get("spec", {}) if isinstance(template, dict) else {}
    containers = pod_spec.get("containers", ()) if isinstance(pod_spec, dict) else ()
    for container in containers:
        if isinstance(container, dict) and container.get("image"):
            return str(container["image"])
    return ""


def _summary(deployment: str, revisions: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not revisions:
        return f"no rollout history for {deployment} — nothing has shipped that is still recorded"
    newest = revisions[0]
    return (
        f"{deployment} is on revision {newest['revision']} "
        f"({newest['image'] or 'no image recorded'}), created {newest['created_at']}; "
        f"{len(revisions)} revision(s) retained"
    )
