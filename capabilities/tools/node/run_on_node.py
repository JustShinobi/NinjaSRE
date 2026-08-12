"""Reading something from a node that only its command line knows.

Three readings decided this cluster's only total outage and none of them is a
REST endpoint: a node's failed systemd units, whether its configured bridges
exist, and a thin pool's metadata fill — which stops writes while the data
percentage still reads comfortable.

Reaching them means something holds an SSH identity. Article IV forbids that
something being the agent, so the agent names a command and an executor holds
the key. This is the naming.

**The command is named, never composed.** The argument is an identifier from a
closed list, not a command line. A tool that took a command line would be the
authority the whole arrangement exists to avoid, moved one layer up.

**It cannot make a change.** There is no parameter for it. A change goes through
the remediation path that requires an approval, and a read tool able to write
would be that path's way around itself.

**Four outcomes, because an investigation acts differently on each.** The node
answered; the node answered unhappily; the command was not one anybody declared;
nobody could reach the node. Collapsing them into "failed" loses which happened,
and only one of the four says anything about the node's health.
"""

from __future__ import annotations

from typing import Any

from capabilities.tools.node import binding
from config.constants.executor import NODE_COMMAND_TOOL_NAME
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence

TOOL_NAME = NODE_COMMAND_TOOL_NAME

_USE_CASES = (
    "reading a node's failed systemd units, which no Proxmox endpoint reports",
    "checking whether a configured bridge exists before blaming the guests behind it",
    "reading a thin pool's metadata fill, which stops writes while its data fill looks fine",
)

_ANTI_EXAMPLES = (
    "running an arbitrary command, which this deliberately cannot do",
    "changing anything on a node, which goes through the path that requires an approval",
    "reaching a guest's own shell, which this never does — every command runs on the host",
)


def _text(result: Any, name: str) -> str:
    return str(getattr(result, name, "") or "")


@tool(
    name=TOOL_NAME,
    display_name="Read from a node",
    description=(
        "Run one command from a closed, declared list on a cluster node and return what it "
        "said. Used for the readings a hypervisor's API does not have — failed systemd "
        "units, bridge state, thin-pool metadata fill — each of which has decided a real "
        "outage and none of which is a REST endpoint. The command is named, never composed: "
        "this cannot run arbitrary commands and cannot change anything."
    ),
    domain="estate",
    evidence_source="node",
    evidence_type=EvidenceType.CONFIGURATION,
    # Reads a host's own state through an executor that holds the identity. Not
    # a write: the declared list distinguishes them and this tool asks for reads.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    tags=("node", "hypervisor", "systemd", "storage", "cli"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def run_on_node(node: str, command_id: str) -> CapabilityResult:
    """Return what ``command_id`` said on ``node``."""
    access = binding.current()
    if access is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            "this deployment has no node executor configured, so nothing was read. The "
            "readings this answers are absent from every API, so their absence here is "
            "not evidence that the node is well.",
            detail=f"asked {node!r} for {command_id!r}",
        )

    outcome = await access.run(node=node, command_id=command_id)

    if getattr(outcome, "refused", False):
        # The deployment is fine; the caller asked for something nobody declared.
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.INVALID_ARGUMENTS,
            f"{command_id!r} is not a command this deployment declares. The list is "
            f"closed on purpose: {_text(outcome, 'reason')}",
            detail=f"asked {node!r}",
        )

    if getattr(outcome, "unreachable", False):
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            f"the node did not answer: {_text(outcome, 'reason')}. Nothing can be "
            f"concluded about {node!r} from this.",
            detail=f"asked for {command_id!r}",
        )

    code = int(getattr(outcome, "exit_code", 0) or 0)
    if code != 0:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UPSTREAM_ERROR,
            f"{command_id!r} exited {code} on {node!r}: {_text(outcome, 'stderr')}",
            detail=_text(outcome, "stdout"),
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "node": node,
            "command_id": command_id,
            "stdout": _text(outcome, "stdout"),
            "stderr": _text(outcome, "stderr"),
        },
        evidence=(
            Evidence(
                source="node",
                evidence_type=EvidenceType.CONFIGURATION,
                summary=f"{command_id} on {node}: {_text(outcome, 'stdout')[:400]}",
                reference=f"node:{node}:{command_id}",
            ),
        ),
    )


__all__ = ["TOOL_NAME", "run_on_node"]
