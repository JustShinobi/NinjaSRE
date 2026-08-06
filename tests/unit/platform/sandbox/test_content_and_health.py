"""Immutable content delivery, and the four numbers that say isolation is working.

The content tests are the interesting half. Immutability rests on two mechanisms —
modes that refuse a write, and a digest that detects one anyway — and both are
asserted, because a mount option that silently did not apply leaves the first
untrue and the second is what catches it.
"""

from __future__ import annotations

import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from platform.sandbox import (
    ContentBundle,
    ContentTampered,
    ReapReport,
    SandboxHealth,
    SandboxProfile,
)
from platform.sandbox.content import ContentEntry
from platform.sandbox.selection import guarantees_for
from platform.sandbox.trace import (
    CollectingSandboxEvents,
    SandboxEvent,
    SandboxEventKind,
    latency_percentile,
)

pytestmark = pytest.mark.unit


def test_a_bundles_digest_is_a_property_of_its_content_not_its_order() -> None:
    first = ContentBundle.from_mapping({"a.md": "one", "b.md": "two"})
    second = ContentBundle.from_mapping({"b.md": "two", "a.md": "one"})
    assert first.digest == second.digest
    assert first.entries[0].path == "a.md"

    changed = ContentBundle.from_mapping({"a.md": "one", "b.md": "three"})
    assert changed.digest != first.digest


def test_the_empty_bundle_still_has_a_stable_digest() -> None:
    assert ContentBundle.empty().digest == ContentBundle.empty().digest
    assert ContentBundle.empty().total_bytes == 0


def test_an_entry_cannot_escape_the_content_mount() -> None:
    """A path outside the mount is a path the read-only guarantee does not cover."""
    with pytest.raises(ValueError, match="not a relative path"):
        ContentEntry(path="/etc/passwd", data=b"x")
    with pytest.raises(ValueError, match="not a relative path"):
        ContentEntry(path="../outside.md", data=b"x")


def test_two_entries_cannot_claim_the_same_path() -> None:
    with pytest.raises(ValueError, match="two entries at the same path"):
        ContentBundle(
            entries=(ContentEntry(path="a.md", data=b"1"), ContentEntry(path="a.md", data=b"2"))
        )


def test_materialised_content_is_readable_and_carries_no_write_bit(tmp_path: Path) -> None:
    bundle = ContentBundle.from_mapping({"skills/triage.md": "# triage", "tool.py": "x = 1"})
    destination = tmp_path / "content"
    bundle.materialise(destination)

    assert (destination / "skills" / "triage.md").read_text() == "# triage"
    if sys.platform != "win32":
        for entry in bundle.entries:
            mode = (destination / entry.path).stat().st_mode
            assert not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        assert not destination.stat().st_mode & stat.S_IWUSR

    bundle.release(destination)


def test_verification_detects_a_change_the_modes_did_not_prevent(tmp_path: Path) -> None:
    """The digest is the backstop for a mount option that did not apply."""
    bundle = ContentBundle.from_mapping({"tool.py": "x = 1"})
    destination = tmp_path / "content"
    bundle.materialise(destination)
    bundle.verify(destination)

    os.chmod(destination, destination.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    target = destination / "tool.py"
    os.chmod(target, 0o644)
    target.write_text("x = 2")

    with pytest.raises(ContentTampered, match="tool.py"):
        bundle.verify(destination)

    bundle.release(destination)


def test_verification_detects_a_deleted_entry(tmp_path: Path) -> None:
    bundle = ContentBundle.from_mapping({"tool.py": "x = 1"})
    destination = tmp_path / "content"
    bundle.materialise(destination)

    bundle.release(destination)
    (destination / "tool.py").unlink()
    with pytest.raises(ContentTampered):
        bundle.verify(destination)


def test_a_bundle_reads_a_directory_eagerly(tmp_path: Path) -> None:
    """A lazily-read bundle would deliver whatever the source said at execution time."""
    source = tmp_path / "skills"
    (source / "nested").mkdir(parents=True)
    (source / "a.md").write_text("one")
    (source / "nested" / "b.md").write_text("two")
    (source / "ignored.txt").write_text("three")

    bundle = ContentBundle.from_directory(source, suffixes=(".md",))
    assert [entry.path for entry in bundle.entries] == ["a.md", "nested/b.md"]

    (source / "a.md").write_text("rewritten")
    assert bundle.entries[0].data == b"one"


def test_release_makes_a_sealed_tree_removable(tmp_path: Path) -> None:
    import shutil

    bundle = ContentBundle.from_mapping({"nested/tool.py": "x = 1"})
    destination = tmp_path / "content"
    bundle.materialise(destination)

    bundle.release(destination)
    shutil.rmtree(destination)
    assert not destination.exists()


def _provisioned(seconds: float) -> SandboxEvent:
    """Return a provisioning event that took ``seconds``."""
    return SandboxEvent(
        kind=SandboxEventKind.PROVISIONED,
        sandbox_id="sbx",
        profile=SandboxProfile.KUBERNETES,
        org_id="acme",
        team_id="platform",
        investigation_id="inv-1",
        duration_seconds=seconds,
    )


async def test_health_reports_provisioning_latency_from_what_actually_happened() -> None:
    events = CollectingSandboxEvents()
    for seconds in (0.01, 0.02, 0.03, 0.04, 5.0):
        await events.record(_provisioned(seconds))

    health = SandboxHealth(
        profile=SandboxProfile.KUBERNETES,
        guarantees=guarantees_for(SandboxProfile.KUBERNETES, system="linux"),
        events=events,
    )
    report = health.report(active=2, pool_size=2, pool_idle=1)

    assert report.provisioning_p50_seconds == 0.03
    assert report.provisioning_p95_seconds == 5.0
    assert report.within_latency_budget
    assert not report.pool_exhausted
    assert report.healthy


async def test_an_exhausted_pool_and_a_dirty_sweep_are_both_unhealthy() -> None:
    events = CollectingSandboxEvents()
    health = SandboxHealth(
        profile=SandboxProfile.KUBERNETES,
        guarantees=guarantees_for(SandboxProfile.KUBERNETES, system="linux"),
        events=events,
    )

    exhausted = health.report(pool_size=2, pool_idle=0)
    assert exhausted.pool_exhausted
    assert not exhausted.healthy

    dirty = health.report(
        pool_size=2,
        pool_idle=2,
        last_sweep=ReapReport(swept_at=datetime.now(UTC), failures=("sbx: refused",)),
    )
    assert not dirty.healthy
    assert dirty.to_record()["last_sweep"]


async def test_a_deployment_that_has_provisioned_nothing_is_not_over_budget() -> None:
    """An unmeasured budget is not a breached one."""
    health = SandboxHealth(
        profile=SandboxProfile.PROCESS,
        guarantees=guarantees_for(SandboxProfile.PROCESS, system="linux"),
        events=CollectingSandboxEvents(),
    )
    report = health.report()
    assert report.provisioning_p50_seconds is None
    assert report.within_latency_budget
    assert report.healthy
    assert report.to_record()["guarantees"]


async def test_a_slow_deployment_reports_itself_over_budget() -> None:
    events = CollectingSandboxEvents()
    for _ in range(3):
        await events.record(_provisioned(30.0))

    report = SandboxHealth(
        profile=SandboxProfile.KUBERNETES,
        guarantees=guarantees_for(SandboxProfile.KUBERNETES, system="linux"),
        events=events,
    ).report(pool_size=1, pool_idle=1)
    assert not report.within_latency_budget
    assert not report.healthy


def test_a_percentile_over_no_measurements_is_none() -> None:
    assert latency_percentile((), percentile=0.5, kind=SandboxEventKind.PROVISIONED) is None


async def test_the_event_window_drops_the_oldest_rather_than_growing_without_bound() -> None:
    events = CollectingSandboxEvents(limit=3)
    for seconds in (1.0, 2.0, 3.0, 4.0):
        await events.record(_provisioned(seconds))
    assert [event.duration_seconds for event in events.events] == [2.0, 3.0, 4.0]
