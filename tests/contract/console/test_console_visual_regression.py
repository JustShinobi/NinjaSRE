"""A seeded pixel change fails the run, and leaves an image saying what changed.

The visual gate's whole value is that somebody looks at the difference. That
needs two things to be true and neither is obvious from a configuration file:
the comparison has to fail on a change, and it has to produce an artefact a
reviewer can open. A suite that failed with "images differ" and no image would
be a suite people accept blind.

The seeded change is a baseline replaced with a blank image of the same size,
which is the cheapest way to produce a difference that is unambiguously a
difference. The real baseline is restored whatever happens.

Needs the pinned capture image, so it skips where there is no container runtime
— the same rule the rest of the visual half runs under, and CI turns the skip
into a failure.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from config.constants.console import (
    CONSOLE_BASELINE_DIR_NAME,
    CONSOLE_SCREEN_REGISTRY_FILENAME,
    CONSOLE_VISUAL_DIR_NAME,
    NINJASRE_CONSOLE_TOOLCHAIN_ENV,
)
from tools.console_gate import REQUIRED
from tools.console_toolchain import REPO_ROOT, console_root, is_provisioned

pytestmark = [pytest.mark.contract, pytest.mark.console]

BASELINES = console_root() / CONSOLE_VISUAL_DIR_NAME / CONSOLE_BASELINE_DIR_NAME
RESULTS = console_root() / "test-results"
REGISTRY = console_root() / CONSOLE_VISUAL_DIR_NAME / CONSOLE_SCREEN_REGISTRY_FILENAME


def _required() -> bool:
    return os.environ.get(NINJASRE_CONSOLE_TOOLCHAIN_ENV, "").strip().lower() == REQUIRED


needs_capture_image = pytest.mark.skipif(
    not _required() and (shutil.which("docker") is None or not is_provisioned()),
    reason=(
        "the visual baselines are captured in one pinned container image; without a "
        f"container runtime there is nothing meaningful to compare. Set "
        f"{NINJASRE_CONSOLE_TOOLCHAIN_ENV}={REQUIRED} to make this a failure"
    ),
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    """Return one PNG chunk, length-prefixed and CRC-suffixed."""
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _dimensions(png: bytes) -> tuple[int, int]:
    """Return the width and height declared in a PNG's header."""
    # 8 bytes of signature, then a 4-byte length, then ``IHDR``, then the size.
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def blank_like(png: bytes) -> bytes:
    """Return an opaque black PNG of the same size as ``png``.

    Written from scratch rather than by editing the original: decoding a PNG
    means implementing five scanline filters, and none of that is what this test
    is about. What matters is that the image is the same size — so the
    comparison reports a pixel difference rather than a size mismatch, which is
    a different failure with a different message.
    """
    width, height = _dimensions(png)
    # Filter type 0 on every scanline, then four zero bytes per pixel, with the
    # alpha byte set so the result is opaque black rather than transparent.
    row = bytes([0]) + bytes([0, 0, 0, 255] * width)
    raw = row * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def committed_baselines() -> tuple[Path, ...]:
    """Return every committed baseline image."""
    return tuple(sorted(BASELINES.glob("*.png")))


def compared_baselines() -> tuple[Path, ...]:
    """Return the baselines the visual run actually compares.

    A screen the registry marks `pending` keeps its image and is not captured,
    so damaging that image proves nothing: the run passes and the seeded change
    is reported as an accepted one. Selecting from the *compared* set is what
    keeps this test about the comparison rather than about which filename sorts
    first — it was the latter, and the day a pending screen took the front of
    the alphabet the test began asserting nothing.
    """
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    baselined = {
        str(screen["id"]) for screen in registry["screens"] if screen["status"] == "baselined"
    }
    return tuple(path for path in committed_baselines() if path.stem in baselined)


def test_there_is_at_least_one_baseline_to_regress() -> None:
    """A visual suite with no baselines passes by having nothing to compare."""
    assert committed_baselines(), f"no baselines are committed under {BASELINES}"


@needs_capture_image
def test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff() -> None:
    """The comparison fails, names the screen, and writes an image of the change."""
    baseline = compared_baselines()[0]
    original = baseline.read_bytes()
    shutil.rmtree(RESULTS, ignore_errors=True)

    baseline.write_bytes(blank_like(original))
    try:
        finished = subprocess.run(
            [sys.executable, "-m", "tools.console_visual", "compare"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, NINJASRE_CONSOLE_TOOLCHAIN_ENV: REQUIRED},
        )
    finally:
        baseline.write_bytes(original)

    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, f"a changed screen was accepted:\n{output}"
    assert baseline.stem in output, f"the failure did not name the screen:\n{output}"

    diffs = sorted(RESULTS.rglob("*-diff.png"))
    assert diffs, f"the run failed but produced no diff image under {RESULTS}:\n{output}"
    assert diffs[0].stat().st_size > 0


@needs_capture_image
def test_the_untouched_baselines_still_match() -> None:
    """The other half: the comparison is not simply always red."""
    finished = subprocess.run(
        [sys.executable, "-m", "tools.console_visual", "compare"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, NINJASRE_CONSOLE_TOOLCHAIN_ENV: REQUIRED},
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
