"""The committed scores, and the gate that compares a run against them.

A baseline that lives in somebody's cache is a baseline nobody reviews. This one
is a file beside the corpus, so moving a number is a diff on a pull request with
the scenario's name in it — which is the only mechanism that has ever stopped a
suite from being quietly re-baselined until it agreed with whatever the code now
does.

The tolerance is zero, and that is a property of *this* suite rather than a
principle. The fixture path runs recorded transcripts over recorded readings with
no model in the loop, so nothing about it is stochastic. Any movement is
somebody's change, and a gate that forgave movement here would be forgiving the
only thing it can see.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from config.constants.hypervisor_scenarios import HYPERVISOR_BASELINE_FILENAME
from tests.harness.proxmox.report import Comparison, SuiteReport


class Regressed(Exception):
    """This run is worse than the committed baseline, and here is exactly how."""

    def __init__(self, comparison: Comparison) -> None:
        self.comparison = comparison
        super().__init__(
            "the hypervisor scenario suite scored worse than its committed baseline.\n\n"
            + comparison.describe()
            + "\n\nIf the new behaviour is the intended one, re-record the baseline and let "
            "the change be reviewed as a change."
        )


def baseline_path(root: Path) -> Path:
    """Return where ``root``'s committed scores live."""
    return Path(root) / HYPERVISOR_BASELINE_FILENAME


def read_baseline(path: Path) -> dict[str, Any]:
    """Return the stored baseline at ``path``.

    Raises:
        FileNotFoundError: there is no baseline, which is a different problem
            from a baseline that disagrees and should not be silently treated as
            a run with nothing to beat.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_baseline(report: SuiteReport, path: Path, *, note: str = "") -> Path:
    """Store ``report`` as the baseline at ``path``, and return where it went.

    The duration is deliberately left out of the stored record. It is the one
    number that differs between two machines running identical code, and a
    baseline that changed because somebody's laptop was busy would be a baseline
    people stop believing.
    """
    stored = report.to_record()
    stored.pop("duration_seconds", None)
    if note:
        stored["note"] = note
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def gate(report: SuiteReport, baseline: Mapping[str, Any]) -> Comparison:
    """Return what moved, raising when any of it is a regression.

    Raises:
        Regressed: a scenario stopped passing, an action became harmful, a
            scenario in the baseline is absent from the run, or the aggregate
            fell past the tolerance.
    """
    comparison = report.compare(baseline)
    if comparison.is_regression:
        raise Regressed(comparison)
    return comparison


__all__ = ["Regressed", "baseline_path", "gate", "read_baseline", "write_baseline"]
