"""Removing the fault, on every way out of a run — including the ones nobody plans.

Three exits, and they take three different paths. A run that finishes normally
leaves through the block's end; a run that raises leaves through ``finally``; a
run that is *signalled* does not leave through the block at all, because
``SIGTERM``'s default disposition ends the process without unwinding anything.
Only the third one leaves a fault running against somebody else's cluster, and
it is the one a CI cancellation sends.

So the handler removes the fault and then raises ``RunInterrupted`` rather than
letting the signal through. Raising is a deliberate choice over re-sending the
signal with its default disposition restored: it means the caller sees the
interruption as an outcome it can record, the ledger's ``finally`` still runs,
and a test can deliver a real ``SIGTERM`` without ending the test session.

**The ledger is not the only line of defence.** ``SIGKILL`` runs no handler at
all, and a machine that loses power runs nothing. Every resource this suite
applies carries a label, and ``sweep_orphans`` removes what carries it whoever
put it there — which is also what the preflight check refuses to start on top of.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from tests.chaos.framework.cluster import Cluster, ClusterResource
from tests.chaos.framework.preflight import preflight
from tests.support.interruption import INTERRUPT_SIGNALS, RunInterrupted, on_interrupt


@dataclass(frozen=True, slots=True)
class FaultRecord:
    """One applied fault, as cleanup needs to name it.

    Registered *before* the manifest is applied. Registering afterwards leaves a
    window in which the fault exists and nothing knows to remove it, and that
    window is exactly where an interruption lands often enough to matter.
    """

    experiment_id: str
    kind: str
    name: str
    namespace: str = ""

    @property
    def identifier(self) -> str:
        """Return the string a report names this fault by."""
        return (
            f"{self.kind}/{self.namespace}/{self.name}"
            if self.namespace
            else (f"{self.kind}/{self.name}")
        )

    def as_resource(self) -> ClusterResource:
        """Return this record as the resource the cluster port deletes."""
        return ClusterResource(kind=self.kind, name=self.name, namespace=self.namespace)


@dataclass(slots=True)
class CleanupLedger:
    """What this run has applied and is therefore responsible for removing."""

    entries: list[FaultRecord] = field(default_factory=list)

    def register(self, record: FaultRecord) -> FaultRecord:
        """Record that ``record`` is about to exist, and return it."""
        if record not in self.entries:
            self.entries.append(record)
        return record

    def forget(self, record: FaultRecord) -> None:
        """Drop ``record``, because it has been removed."""
        self.entries = [found for found in self.entries if found != record]

    def __len__(self) -> int:
        """Return how many faults are outstanding."""
        return len(self.entries)


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """What cleanup removed, what it could not, and whether the cluster came back."""

    removed: tuple[str, ...] = ()
    swept: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    baseline_restored: bool = True
    baseline_reasons: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        """Return whether the cluster is fit for the next experiment."""
        return not self.failures and self.baseline_restored


def sweep_orphans(cluster: Cluster) -> tuple[str, ...]:
    """Remove every fault carrying this suite's label and return what went.

    Independent of any ledger, and that is the point: the run whose faults these
    were is gone. Called by cleanup at the end of every run and by the preflight
    remedy path, so a killed run costs the next one a sweep rather than an
    afternoon.
    """
    swept: list[str] = []
    for resource in cluster.active_faults():
        cluster.delete(resource)
        swept.append(resource.identifier)
    return tuple(swept)


def clean_up(
    cluster: Cluster, ledger: CleanupLedger, *, verify_baseline: bool = True
) -> CleanupReport:
    """Remove everything ``ledger`` is responsible for and report what happened.

    Never raises. Cleanup that raised half way through would leave the rest of
    the faults applied, which is the failure this whole module exists to prevent
    — so a deletion that fails is recorded and the next one is still attempted.
    """
    removed: list[str] = []
    failures: list[str] = []

    for record in list(ledger.entries):
        try:
            cluster.delete(record.as_resource())
        except Exception as failure:  # noqa: BLE001 - a failed delete must not stop the rest
            failures.append(f"{record.identifier}: {failure}")
            continue
        ledger.forget(record)
        removed.append(record.identifier)

    swept: list[str] = []
    for resource in cluster.active_faults():
        try:
            cluster.delete(resource)
        except Exception as failure:  # noqa: BLE001 - same reason
            failures.append(f"{resource.identifier}: {failure}")
            continue
        swept.append(resource.identifier)

    if not verify_baseline:
        return CleanupReport(removed=tuple(removed), swept=tuple(swept), failures=tuple(failures))

    report = preflight(cluster)
    return CleanupReport(
        removed=tuple(removed),
        swept=tuple(swept),
        failures=tuple(failures),
        baseline_restored=report.healthy,
        baseline_reasons=report.reasons,
    )


@contextmanager
def deferred_cleanup(
    cluster: Cluster,
    *,
    ledger: CleanupLedger | None = None,
    signals: tuple[signal.Signals, ...] = INTERRUPT_SIGNALS,
    verify_baseline: bool = True,
) -> Iterator[CleanupLedger]:
    """Yield a ledger whose faults are removed on every way out of the block.

    Raises:
        RunInterrupted: one of ``signals`` arrived; the faults were removed first.
    """
    book = ledger if ledger is not None else CleanupLedger()

    def remove_everything() -> None:
        clean_up(cluster, book, verify_baseline=False)

    try:
        with on_interrupt(remove_everything, signals=signals, what="the chaos run"):
            yield book
    finally:
        clean_up(cluster, book, verify_baseline=verify_baseline)


__all__ = [
    "INTERRUPT_SIGNALS",
    "CleanupLedger",
    "CleanupReport",
    "FaultRecord",
    "RunInterrupted",
    "clean_up",
    "deferred_cleanup",
    "sweep_orphans",
]
