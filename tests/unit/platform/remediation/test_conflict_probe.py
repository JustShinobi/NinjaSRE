"""Whether the approval layer's conflict check can name what it is about to change."""

from __future__ import annotations

from capabilities.tools.remediation.proxmox.plane import _guest_of
from platform.approvals.models import ChangeTarget
from platform.remediation.execution import _probe_action


def test_the_conflict_probe_carries_the_arguments_its_capability_addresses_the_target_by() -> None:
    """A guest is addressed by three facts, and the probe is built from a string.

    ``RequestBuilder.queue`` hands the approval layer a ``ChangeTarget`` holding
    the target string and the capability, on the stated bet that "which of the
    seven remediation capabilities knows how to read this workload is exactly
    what it needs". The conflict check then rebuilds an action from those two
    fields — deliberately minimal, so that it invents no requester and no
    intent — and asks that capability's reader for the target's state.

    A hypervisor does not address a guest that way. ``_guest_of`` takes the
    node, the number and the kind from the *arguments*, and says why in its own
    comment: reconstructing them from ``name@environment`` would be a naming
    convention standing in for all three. So the probe arrives with ``{}`` and
    the read raises — inside the call that creates the approval.

    Measured against staging on 2026-08-25. An investigation called
    ``proxmox_start_guest`` with node, vmid and kind all present; the gate's
    hook failed with "was given {}"; the hook registry reads a crashing
    ``pre_tool_use`` as Allow, so the call fell through to the capability body,
    and its ungated refusal is what the model was handed. No approval row has
    ever been written in that deployment, through four windows and five earlier
    explanations for the zero.
    """
    probe = _probe_action(
        ChangeTarget(identifier="122@homelab", node_id=None, path="proxmox_start_guest"),
        "proxmox_start_guest",
        proposed={"arguments": {"node": "pve01", "vmid": 122, "kind": "lxc"}},
    )

    node, vmid, kind = _guest_of(probe)

    assert (node, vmid, kind) == ("pve01", 122, "lxc")
