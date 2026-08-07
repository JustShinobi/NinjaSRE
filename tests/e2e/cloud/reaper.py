"""The sweep that destroys what a killed run left behind, knowing nothing about it.

Independent of any run, by design. The deferred teardown covers every exit that
unwinds; this covers the ones that do not — a lost machine, a ``SIGKILL``, a
provisioning step that hung past its timeout and took the runner with it. Two
mechanisms because teardown itself can fail, and "the thing that cleans up is the
thing that broke" is a bill that keeps arriving.

Three rules keep it from being the outage rather than the fix.

**Only what this suite tagged.** The suite tag is the entire selector, so a
resource somebody else made is invisible here whatever else is true of it.

**Only what it can attribute.** A resource carrying the suite tag but no run tag
and no timestamp is reported and left alone: the sweep cannot tell it from a live
run's, and guessing is unrecoverable.

**Only what is old enough, and not held by a live run.** Provisioning takes time,
and a sweep that reaped a stack that was still coming up would break the run it
was protecting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.chaos import CLOUD_ORPHAN_MAX_AGE_SECONDS
from tests.e2e.cloud.provisioning import Provisioner, ProvisioningError, Resource


@dataclass(frozen=True, slots=True)
class ReapReport:
    """What a sweep destroyed, what it left, and what it could not decide about."""

    reaped: tuple[str, ...] = field(default_factory=tuple)
    kept: tuple[str, ...] = field(default_factory=tuple)
    unattributable: tuple[str, ...] = field(default_factory=tuple)
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        """Return whether the account holds nothing this sweep should have removed."""
        return not self.failures and not self.unattributable

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this sweep."""
        return {
            "reaped": list(self.reaped),
            "kept": list(self.kept),
            "unattributable": list(self.unattributable),
            "failures": list(self.failures),
            "clean": self.clean,
        }

    def render(self) -> str:
        """Return what an operator reads after a sweep."""
        lines = [f"reaped {len(self.reaped)} orphaned resources, kept {len(self.kept)}"]
        if self.unattributable:
            lines.append(
                "carrying this suite's tag but no run or timestamp — left alone, and worth "
                "looking at by hand:"
            )
            lines.extend(f"  {identifier}" for identifier in self.unattributable)
        if self.failures:
            lines.append("could not be destroyed:")
            lines.extend(f"  {failure}" for failure in self.failures)
        return "\n".join(lines)


def orphans(
    resources: Sequence[Resource],
    *,
    now: datetime | None = None,
    max_age_seconds: float = CLOUD_ORPHAN_MAX_AGE_SECONDS,
    active_runs: Sequence[str] = (),
) -> tuple[tuple[Resource, ...], tuple[Resource, ...], tuple[Resource, ...]]:
    """Return ``resources`` split into orphaned, kept, and unattributable."""
    moment = now if now is not None else datetime.now(UTC)
    live = set(active_runs)

    orphaned: list[Resource] = []
    kept: list[Resource] = []
    unknown: list[Resource] = []

    for resource in resources:
        if not resource.attributable:
            unknown.append(resource)
        elif resource.run_id in live or resource.age_seconds(now=moment) < max_age_seconds:
            kept.append(resource)
        else:
            orphaned.append(resource)

    return tuple(orphaned), tuple(kept), tuple(unknown)


def reap(
    provisioner: Provisioner,
    *,
    now: datetime | None = None,
    max_age_seconds: float = CLOUD_ORPHAN_MAX_AGE_SECONDS,
    active_runs: Sequence[str] = (),
    dry_run: bool = False,
) -> ReapReport:
    """Destroy every attributable orphan the account holds, and report the sweep.

    ``dry_run`` reports what would go without touching anything, which is what
    somebody runs the first time they point this at an account.
    """
    inventory = provisioner.inventory()
    orphaned, kept, unknown = orphans(
        inventory, now=now, max_age_seconds=max_age_seconds, active_runs=active_runs
    )

    if dry_run:
        return ReapReport(
            reaped=tuple(sorted(resource.identifier for resource in orphaned)),
            kept=tuple(sorted(resource.identifier for resource in kept)),
            unattributable=tuple(sorted(resource.identifier for resource in unknown)),
        )

    reaped: list[str] = []
    failures: list[str] = []
    for run_id in sorted({resource.run_id for resource in orphaned}):
        try:
            reaped.extend(provisioner.destroy_by_run(run_id))
        except ProvisioningError as failure:
            failures.append(f"{run_id}: {failure}")

    return ReapReport(
        reaped=tuple(sorted(set(reaped))),
        kept=tuple(sorted(resource.identifier for resource in kept)),
        unattributable=tuple(sorted(resource.identifier for resource in unknown)),
        failures=tuple(failures),
    )


def leaked(provisioner: Provisioner, *, run_id: str) -> tuple[str, ...]:
    """Return what ``run_id`` left behind, which a finished run needs to be empty."""
    return tuple(
        sorted(
            resource.identifier for resource in provisioner.inventory() if resource.run_id == run_id
        )
    )


__all__ = ["ReapReport", "leaked", "orphans", "reap"]
