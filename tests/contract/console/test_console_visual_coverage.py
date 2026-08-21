"""Every design reference is accounted for, and every baseline was reviewed.

This is the mechanism the fidelity requirements of the console features depend
on. Without it, "the console matches the design" is an intention: somebody
compares a screen to a picture once, nothing records that they did, and the next
change to the screen is reviewed against the screen rather than against the
design.

With it, three things hold at once, and each of them is a failure with a name:

- a design reference in ``console/visual/mockups/`` that appears in neither the
  screen registry nor the pending list fails, so a design cannot arrive and be
  forgotten;
- a reference marked pending must say which surface will implement it, so
  "pending" is a plan rather than a shrug;
- a screen marked baselined must have a committed baseline image *and* an
  acceptance record saying which reference it was first reviewed against, so
  the first acceptance is a review and every one after it is ordinary visual
  regression.

None of this needs the toolchain: it reads committed files, so it holds on every
machine and in every job.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from config.constants.console import (
    CONSOLE_BASELINE_DIR_NAME,
    CONSOLE_MOCKUP_DIR_NAME,
    CONSOLE_SCREEN_REGISTRY_FILENAME,
    CONSOLE_VISUAL_DIR_NAME,
)
from tools.console_toolchain import console_root

pytestmark = pytest.mark.contract

VISUAL = console_root() / CONSOLE_VISUAL_DIR_NAME
MOCKUPS = VISUAL / CONSOLE_MOCKUP_DIR_NAME
BASELINES = VISUAL / CONSOLE_BASELINE_DIR_NAME
REGISTRY = VISUAL / CONSOLE_SCREEN_REGISTRY_FILENAME

BASELINED = "baselined"
PENDING = "pending"


def registry() -> Mapping[str, Any]:
    """Return the committed screen registry."""
    loaded: Any = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{REGISTRY} does not hold an object"
    return loaded


def screens() -> tuple[Mapping[str, Any], ...]:
    """Return every registered screen."""
    return tuple(registry()["screens"])


def mockups() -> tuple[Mapping[str, Any], ...]:
    """Return every registered design reference."""
    return tuple(registry()["mockups"])


def test_the_registry_exists_and_is_readable() -> None:
    """Without it there is no coverage claim to check."""
    assert REGISTRY.is_file(), f"{REGISTRY} is missing"
    assert screens(), "the registry declares no screens"


def test_every_committed_reference_is_registered() -> None:
    """A design that arrives and is not registered fails, naming the file."""
    on_disk = {path.name for path in MOCKUPS.glob("*.png")}
    registered = {str(entry["file"]) for entry in mockups()}

    unregistered = sorted(on_disk - registered)
    assert not unregistered, (
        f"design references with no entry in {CONSOLE_SCREEN_REGISTRY_FILENAME}: "
        f"{', '.join(unregistered)}. Register each one, either as the reference a "
        f"screen was accepted against or as pending with the surface that will "
        f"implement it."
    )


def test_every_registered_reference_is_committed() -> None:
    """A registry entry for a file nobody committed is coverage that does not exist."""
    on_disk = {path.name for path in MOCKUPS.glob("*.png")}
    missing = sorted(str(entry["file"]) for entry in mockups() if str(entry["file"]) not in on_disk)
    assert not missing, f"registered design references that are not committed: {missing}"


@pytest.mark.parametrize("entry", mockups(), ids=lambda entry: str(entry["file"]))
def test_a_pending_reference_names_the_surface_that_will_implement_it(
    entry: Mapping[str, Any],
) -> None:
    """ "Pending" has to be a plan, or it is a place designs go to be forgotten."""
    if entry["status"] != PENDING:
        return
    surface = str(entry.get("surface", "")).strip()
    assert surface, (
        f"{entry['file']} is pending but names no surface. Say which part of the console "
        f"will render it, so the gap is a plan rather than an omission."
    )


@pytest.mark.parametrize("entry", mockups(), ids=lambda entry: str(entry["file"]))
def test_a_reference_is_either_pending_or_owned_by_a_baselined_screen(
    entry: Mapping[str, Any],
) -> None:
    """The only two honest states, and the second one has to point at a real screen."""
    status = entry["status"]
    assert status in {PENDING, BASELINED}, f"{entry['file']} has an unknown status: {status}"
    if status != BASELINED:
        return
    owning = {
        str(screen["id"])
        for screen in screens()
        if str(screen.get("accepted", {}).get("against", "") or "") == str(entry["file"])
    }
    assert owning, (
        f"{entry['file']} is marked baselined but no screen records having been accepted against it"
    )


@pytest.mark.parametrize("screen", screens(), ids=lambda screen: str(screen["id"]))
def test_a_baselined_screen_has_a_committed_baseline(screen: Mapping[str, Any]) -> None:
    """A screen the suite claims to cover, with no image to compare against."""
    if screen["status"] != BASELINED:
        return
    baseline: Path = BASELINES / f"{screen['id']}.png"
    assert baseline.is_file(), (
        f"{screen['id']} is registered as baselined but {baseline.name} is not committed. "
        f"Capture it with `make console-visual-accept` and commit the result."
    )
    assert baseline.stat().st_size > 0, f"{baseline.name} is empty"


@pytest.mark.parametrize("screen", screens(), ids=lambda screen: str(screen["id"]))
def test_a_baselined_screen_records_what_its_first_acceptance_was_reviewed_against(
    screen: Mapping[str, Any],
) -> None:
    """The acceptance record, which is what makes the fidelity claim checkable.

    Either it names the design reference the screen was compared to, or it says
    in prose why there is no reference — which is a sentence a reviewer can
    argue with, unlike a missing field.
    """
    if screen["status"] != BASELINED:
        return
    accepted = screen.get("accepted")
    assert isinstance(accepted, dict), f"{screen['id']} records no acceptance"

    against = accepted.get("against")
    if against is not None:
        assert (MOCKUPS / str(against)).is_file(), (
            f"{screen['id']} was accepted against {against}, which is not committed"
        )
        return
    reason = str(accepted.get("reason", "")).strip()
    assert len(reason) > 40, (
        f"{screen['id']} was accepted against no design reference and gives no reason "
        f"worth reading. Say why the screen has no reference."
    )


def test_no_baseline_belongs_to_a_screen_nobody_registered() -> None:
    """An orphaned baseline is an image the suite no longer compares anything to."""
    if not BASELINES.is_dir():
        return
    registered = {str(screen["id"]) for screen in screens()}
    orphans = sorted(path.stem for path in BASELINES.glob("*.png") if path.stem not in registered)
    assert not orphans, f"baselines with no registered screen: {orphans}"
