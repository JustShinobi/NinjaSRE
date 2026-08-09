"""What an upgrade must keep, and the one thing it has to tell the operator about.

Everything a deployment has learned about somebody's cluster lives in the
database: the estate, the incidents, the history, the policies, and the
overrides that say where the shipped numbers were wrong. Upgrading is a container
image change over the same volume, so all of that survives by construction — the
state is not in the image.

The shipped detector set is the exception, and it is the reason this module
exists. It ships *in* the image. A release that lowers a threshold, adds a
condition, or changes what a detector watches changes what the deployment does,
and doing that silently is the failure worth engineering against: an operator
who tuned a threshold six months ago and finds it behaving differently has no
way to connect the two events.

So the shipped definitions are fingerprinted, the fingerprints are stored, and an
upgrade reports the difference in the operator's terms — added, removed, and for
each change, what it was and what it is now. Overrides are unaffected either way:
they are the deployment's own document and an upgrade does not touch them, which
is exactly why FR-016 asks for overrides rather than for editing the set.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from platform.guardian.catalogue import SHIPPED_DETECTORS, ShippedDetector

#: What a shipped definition's fingerprint is taken over. The parts that change
#: what the detector *does* — not its prose. A release that improves a rationale
#: without moving a number has changed nothing an operator needs to review, and
#: reporting it would train them to skip the report.
_FINGERPRINTED = (
    "signal",
    "condition_kind",
    "comparison",
    "fire_value",
    "clear_value",
    "to_state",
    "from_state",
    "silent_after_seconds",
    "for_seconds",
    "recovery_seconds",
    "severity",
    "resource_kinds",
    "topology",
)


@dataclass(frozen=True, slots=True)
class DefinitionChange:
    """One shipped detector whose behaviour changed across an upgrade."""

    detector_id: str
    was: str
    now: str
    #: True when this deployment has an override on the detector, because that
    #: is the case the operator most needs to look at: their number may now be
    #: solving a problem the new definition already solves, or contradicting it.
    overridden: bool = False

    def describe(self) -> str:
        """Return the line the upgrade report shows for this detector."""
        line = f"{self.detector_id}: {self.was} → {self.now}"
        if self.overridden:
            return (
                f"{line}. You have an override on this one — worth checking whether it is "
                f"still doing what you wanted."
            )
        return line


@dataclass(frozen=True, slots=True)
class UpgradeReport:
    """What changed in the shipped set, and confirmation that nothing else did."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[DefinitionChange, ...] = ()
    #: What the upgrade preserved, counted. Reported rather than assumed: an
    #: upgrade that silently emptied the estate would otherwise be discovered by
    #: an operator wondering why the console is blank.
    preserved: Mapping[str, int] | None = None

    @property
    def anything_changed(self) -> bool:
        """Return whether the shipped set differs from the one that was running."""
        return bool(self.added or self.removed or self.changed)

    def describe(self) -> str:
        """Return the paragraph an operator reads after an upgrade."""
        if not self.anything_changed:
            return "No shipped detector's definition changed in this release."
        parts: list[str] = []
        if self.added:
            parts.append(f"{len(self.added)} detector(s) added: {', '.join(self.added)}.")
        if self.removed:
            parts.append(
                f"{len(self.removed)} removed: {', '.join(self.removed)}. Any override you "
                f"had on those now changes nothing."
            )
        if self.changed:
            parts.append(
                f"{len(self.changed)} changed definition(s): "
                + "; ".join(change.describe() for change in self.changed)
                + "."
            )
        return " ".join(parts)

    def to_record(self) -> dict[str, Any]:
        """Return the document the upgrade report is stored and rendered as."""
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": [
                {
                    "detector_id": change.detector_id,
                    "was": change.was,
                    "now": change.now,
                    "overridden": change.overridden,
                }
                for change in self.changed
            ],
            "preserved": dict(self.preserved or {}),
            "summary": self.describe(),
        }


def fingerprint(detector: ShippedDetector) -> str:
    """Return a short digest of what ``detector`` does, ignoring how it is worded."""
    parts: list[str] = []
    for name in _FINGERPRINTED:
        value = getattr(detector, name)
        if isinstance(value, tuple):
            parts.append(",".join(str(item) for item in value))
        else:
            parts.append(str(value))
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def fingerprints(
    catalogue: Sequence[ShippedDetector] = SHIPPED_DETECTORS,
) -> dict[str, str]:
    """Return the fingerprint of every shipped detector, keyed by identifier.

    Stored after every start, so the next start has something to compare
    against. A deployment with nothing stored is one being upgraded from before
    this existed, and it reports no changes rather than reporting every detector
    as new.
    """
    return {detector.detector_id: fingerprint(detector) for detector in catalogue}


def compare(
    stored: Mapping[str, str],
    *,
    catalogue: Sequence[ShippedDetector] = SHIPPED_DETECTORS,
    overridden: Sequence[str] = (),
    preserved: Mapping[str, int] | None = None,
) -> UpgradeReport:
    """Return what changed between ``stored`` and the set this release ships.

    An empty ``stored`` produces an empty report rather than one naming every
    detector as added. The first start after an upgrade from an older release
    has nothing to compare against, and a report listing forty-six additions is
    a report nobody reads — including the next time, when it means something.
    """
    if not stored:
        return UpgradeReport(preserved=preserved)

    current = fingerprints(catalogue)
    by_id = {detector.detector_id: detector for detector in catalogue}
    overridden_ids = set(overridden)

    added = tuple(sorted(set(current) - set(stored)))
    removed = tuple(sorted(set(stored) - set(current)))
    changed = tuple(
        DefinitionChange(
            detector_id=detector_id,
            was=stored[detector_id],
            now=current[detector_id],
            overridden=detector_id in overridden_ids,
        )
        for detector_id in sorted(set(stored) & set(current))
        if stored[detector_id] != current[detector_id] and detector_id in by_id
    )
    return UpgradeReport(added=added, removed=removed, changed=changed, preserved=preserved)


__all__ = [
    "DefinitionChange",
    "UpgradeReport",
    "compare",
    "fingerprint",
    "fingerprints",
]
