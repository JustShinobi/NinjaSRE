"""Two postures, and the preview that stands between the operator and the second one.

The default is propose-only, and that is the most consequential decision in this
feature. An autonomous system that acts on somebody's home infrastructure on the
day it is installed will eventually do something they did not expect, and they
will turn it off — and the thing they turn off is the part that was catching the
ZFS pool at eighty per cent, not the part that surprised them.

So a fresh deployment proposes and does nothing else, for as long as the
operator wants. When they are ready there is exactly one named alternative,
because a menu of postures is a decision nobody makes: the recommended preset
raises autonomy on the small set of actions that are reversible, cheap and
boring, and leaves everything else exactly where it was.

**Nothing is applied without a preview first.** Feature 040 already replays
recorded history against a proposed policy and reports which decisions would
change. Applying a posture blind is applying a diff of a configuration document,
and the two documents can look almost identical while the answer changes
completely.

**The preset is a policy document, not a code path.** It is built from the same
rules an operator writes by hand, resolved by the same resolver, and gated by the
same gate. Anything else would be a second autonomy system whose drift from the
first is invisible until it acts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from config.constants.autonomy import (
    AUTONOMY_SCOPE_CAPABILITY,
    AUTONOMY_SCOPE_DEPLOYMENT,
    RISK_CLASS_LOW,
    RISK_CLASS_MODERATE,
    RISK_CLASS_TRIVIAL,
)
from config.constants.guardian import (
    POSTURE_PRESET_PROPOSE_ONLY,
    POSTURE_PRESET_RECOMMENDED,
)
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.preview import PolicyChange

#: The capabilities the recommended preset lets run unattended, and why each one
#: is on this list rather than a longer one.
#:
#: The test each had to pass is the same: its blast radius is one resource, and
#: doing it wrongly costs minutes rather than data. Anything that destroys,
#: stops, moves, resizes, reconfigures the cluster or touches the network is
#: deliberately absent — a homelab has no second copy of most of it, and the
#: operator is not on a rota.
#:
#: Nothing here reclassifies a capability. The risk classes belong to the
#: remediation risk table, which is deliberately not this feature's to edit; what
#: the preset chooses is the *bound* it is willing to act up to, per capability,
#: and it states why whenever that bound is above the deployment's default.
RECOMMENDED_AUTONOMOUS_CAPABILITIES: tuple[tuple[str, str, str], ...] = (
    (
        "proxmox_unlock_guest",
        RISK_CLASS_LOW,
        "a lock left behind by a cancelled task is written back in one call, and the guest "
        "returns to exactly its prior state; leaving it blocks every later action on that "
        "guest, including the backup whose cancellation caused it",
    ),
    (
        "proxmox_start_guest",
        RISK_CLASS_LOW,
        "starting a guest the inventory says should be running is restoring the declared "
        "state rather than changing it, and shutting it down again is one call",
    ),
    (
        "proxmox_resume_guest",
        RISK_CLASS_LOW,
        "resuming restores a memory image that already exists, and suspending again undoes "
        "it exactly",
    ),
    (
        "proxmox_retry_backup",
        RISK_CLASS_MODERATE,
        "the bound is raised above the default for this one capability, and the reason is "
        "asymmetry: a backup that ran cannot be un-run, but it writes a new copy and "
        "removes none, so the worst outcome of retrying wrongly is a second failure saying "
        "what the first said. The worst outcome of not retrying is a gap in the backups "
        "that is discovered when they are needed",
    ),
    (
        "proxmox_resync_replication",
        RISK_CLASS_MODERATE,
        "the same asymmetry as a backup retry, with the same worst case: a sync that ran "
        "cannot be un-run, and a replica that is hours behind is the amount of data a node "
        "loss would cost",
    ),
)


class PosturePreset(StrEnum):
    """The two postures a homelab deployment picks between."""

    #: Diagnose and propose; act on nothing. What a fresh deployment resolves to
    #: with no policy at all, so it is what happens when nobody chooses.
    PROPOSE_ONLY = POSTURE_PRESET_PROPOSE_ONLY
    #: Act on the small, reversible, one-resource things; ask about the rest.
    RECOMMENDED = POSTURE_PRESET_RECOMMENDED

    def describe(self) -> str:
        """Return the paragraph an operator reads before applying this."""
        return _PRESET_DESCRIPTIONS[self]


_PRESET_DESCRIPTIONS: dict[PosturePreset, str] = {
    PosturePreset.PROPOSE_ONLY: (
        "Nothing runs without you. Every detector still watches, every incident is still "
        "raised and investigated, and every remediation is written down as a proposal "
        "with the evidence behind it — but the deployment executes none of them. This is "
        "what a new installation does, and it is a reasonable place to stay."
    ),
    PosturePreset.RECOMMENDED: (
        "Five things happen without asking: a stuck guest lock clears, a guest that "
        "should be running gets started, a suspended guest resumes, a failed backup "
        "retries, and a failed replication resyncs. Each affects one resource, and the "
        "worst outcome of each being wrong costs minutes rather than data. Everything "
        "else — anything that deletes, stops, moves, resizes, reconfigures the cluster "
        "or touches the network — still asks you first."
    ),
}


@dataclass(frozen=True, slots=True)
class PostureProposal:
    """A named posture, the document it is, and what applying it would have changed.

    The three together, because an operator deciding this needs all three and
    getting them from three calls is how one of them gets skipped. ``preview``
    is ``None`` only when nothing has been recorded yet — a deployment on its
    first day — and that is itself worth saying rather than rendering an empty
    list.
    """

    preset: PosturePreset
    document: dict[str, Any]
    preview: PolicyChange | None = None

    @property
    def has_history_to_judge_by(self) -> bool:
        """Return whether there is recorded history this preview means anything against."""
        return self.preview is not None and bool(self.preview.previewed)

    def summarise(self) -> str:
        """Return what an operator is shown above the preview's list."""
        if self.preview is None:
            return (
                f"{self.preset.describe()} Nothing has been recorded yet, so there is no "
                f"history to show you what this would have changed. Watching for a week "
                f"first is the point of the default."
            )
        return f"{self.preset.describe()} {self.preview.summarise()}"

    def to_record(self) -> dict[str, Any]:
        """Return the document the API returns and the console renders."""
        return {
            "preset": self.preset.value,
            "description": self.preset.describe(),
            "document": self.document,
            "summary": self.summarise(),
            "preview": self.preview.to_record() if self.preview is not None else None,
        }


def preset_document(preset: PosturePreset, *, team_node_id: str = "") -> dict[str, Any]:
    """Return ``preset`` as an autonomy policy document, ready to be written.

    A configuration document rather than a ``PolicySet``, because applying it
    goes through the configuration service — which is what gives it the merge,
    the locked fields, the approval gate, the provenance and the audit row that
    every other policy change gets. A preset that wrote straight to storage
    would be the one change nobody could see who made.
    """
    if preset is PosturePreset.PROPOSE_ONLY:
        return {
            "rules": [
                {
                    "scope": _scope(AUTONOMY_SCOPE_DEPLOYMENT, team_node_id=team_node_id),
                    "level": AutonomyLevel.PROPOSE_ONLY.value,
                    "risk_bound": RISK_CLASS_TRIVIAL,
                }
            ]
        }

    rules: list[dict[str, Any]] = [
        {
            "scope": _scope(AUTONOMY_SCOPE_DEPLOYMENT, team_node_id=team_node_id),
            "level": AutonomyLevel.PROPOSE_ONLY.value,
            "risk_bound": RISK_CLASS_TRIVIAL,
        }
    ]
    rules.extend(
        {
            "scope": _scope(
                AUTONOMY_SCOPE_CAPABILITY, team_node_id=team_node_id, capability=capability
            ),
            "level": AutonomyLevel.ACT_ON_LOW_RISK.value,
            "risk_bound": risk_bound,
        }
        for capability, risk_bound, _reason in RECOMMENDED_AUTONOMOUS_CAPABILITIES
    )
    return {"rules": rules}


def is_propose_only(policies: PolicySet) -> bool:
    """Return whether ``policies`` acts on nothing at all.

    Read from the resolved set rather than from the document, because a
    deployment inherits policy down a tree and "the document is empty" and
    "nothing resolves to acting" are different claims. SC-004 is about the
    second one.
    """
    return all(not rule.level.acts for rule in policies.rules)


def _scope(kind: str, *, team_node_id: str = "", capability: str = "") -> dict[str, str]:
    """Return one policy scope, with only the fields its kind requires."""
    scope = {"kind": kind}
    if team_node_id:
        scope["team_node_id"] = team_node_id
    if capability:
        scope["capability"] = capability
    return scope


__all__ = [
    "RECOMMENDED_AUTONOMOUS_CAPABILITIES",
    "PosturePreset",
    "PostureProposal",
    "is_propose_only",
    "preset_document",
]
