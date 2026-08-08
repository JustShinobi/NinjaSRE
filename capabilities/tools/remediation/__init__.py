"""The write actions, and the four components every one of them declares.

Remediation is cross-vendor by nature: restarting a workload, rolling back a
release, and changing a replica count are the same three actions whether the
control plane is Kubernetes, ECS, or a virtual machine fleet. Putting them in
one package rather than in each vendor's is what stops the approval rules being
re-implemented, slightly differently, eighty-five times.

Every tool here is above ``read_sensitive``, and the metadata type enforces what
that means: approval is required, the reason a human is being asked is written
down, and a rollback plan or a planner exists at declaration time rather than
being looked for afterwards.

**Each capability is a package of four components, not a function.** A state
reader, an applier, a rollback generator, and a verifier — called at four
different moments by four different parts of ``platform.remediation``. The tool
function itself does not perform the action: it refuses, by name, and points at
the gate. That is not a placeholder. A capability that could be invoked directly
would be a capability that could run without an approval and without a plan, and
the refusal is what makes "every write went through the gate" true of every
entry point rather than of the ones somebody remembered.

**Each capability also declares how anybody would know it worked.** The four
components say what to do and how to undo it; ``verification`` says which
signals the *effect* appears in and how long to wait before they mean anything.
``toggle_feature_flag`` declares itself unverifiable with its reason, which is
the same disposition as ``clear_cache`` below and exists for the same reason:
the branch is exercised by the shipped catalogue rather than by nothing.

``clear_cache`` is in this set on purpose. It is the one action with no
derivable rollback, so the waiver path — refuse unless an operator explicitly
accepts it, and audit the acceptance — is exercised by the shipped catalogue
rather than being a branch nobody has run.
"""

from __future__ import annotations

from collections.abc import Sequence

from capabilities.tools.remediation import (
    clear_cache,
    cordon_drain_node,
    restart_workload,
    rollback_deployment,
    scale_workload,
    toggle_feature_flag,
    update_resource_limits,
)
from capabilities.tools.remediation.control_plane import ControlPlane, ControlPlaneState
from platform.remediation.components import ComponentRegistry, RemediationComponents

#: The four components of each shipped capability, in one place. A caller wiring
#: a deployment registers these; a contract test walks them and asserts all four
#: exist and behave. The list is explicit rather than discovered because "which
#: writes can this deployment perform" is a question an operator should be able
#: to answer by reading one value.
COMPONENTS: tuple[RemediationComponents, ...] = (
    restart_workload.components,
    rollback_deployment.components,
    scale_workload.components,
    cordon_drain_node.components,
    update_resource_limits.components,
    toggle_feature_flag.components,
    clear_cache.components,
)


def registry(*, known_signals: Sequence[str] | None = None) -> ComponentRegistry:
    """Return a registry holding every shipped remediation capability.

    ``known_signals`` is what this deployment's observation sources produce.
    Passing it makes a capability naming a signal nothing emits fail here rather
    than verify against nothing forever — and a composition root that has wired
    observation has the list to hand, because it built the sources.
    """
    return ComponentRegistry().register_all(COMPONENTS, known_signals=known_signals)


__all__ = [
    "COMPONENTS",
    "ComponentRegistry",
    "ControlPlane",
    "ControlPlaneState",
    "RemediationComponents",
    "registry",
]
