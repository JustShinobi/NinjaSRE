"""The scheduled job's entry point, over the corpus this repository actually ships.

Not a mocked corpus. The point of a CI entry point is that it works on the thing
CI will point it at, and every failure this file has caught so far has been in the
seam between the scoring harness and the corpus rather than inside either.

It runs offline, on recorded transcripts, for zero tokens — which is what makes it
affordable enough to be a gate at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.regression.baseline import BaselineStore
from tests.harness.regression.ci import main, measure

pytestmark = pytest.mark.unit


async def test_the_corpus_scores_on_all_five_axes(tmp_path: Path) -> None:
    """SC-001 against the shipped corpus rather than against a fixture."""
    suite = await measure(Path("tests/synthetic"), label="under test")

    assert suite.scenarios, "the corpus is empty, so this proves nothing"
    for found in suite.scenarios:
        assert len(found.axes) == 5
    assert suite.corpus_version


def test_recording_then_gating_against_the_recording_passes(tmp_path: Path) -> None:
    """The loop a release runs: establish a point, then measure against it."""
    arguments = ["--root", "tests/synthetic", "--baselines", str(tmp_path)]

    assert main([*arguments, "--record", "v-test", "--note", "a test baseline"]) == 0
    assert BaselineStore(root=tmp_path).identifiers() == ("v-test",)
    assert main([*arguments, "--baseline", "v-test"]) == 0


def test_gating_against_a_baseline_that_does_not_exist_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    """Exit two rather than one: nothing regressed, the invocation was wrong."""
    assert (
        main(["--root", "tests/synthetic", "--baselines", str(tmp_path), "--baseline", "nope"]) == 2
    )


def test_asking_for_neither_a_baseline_nor_a_recording_refuses(tmp_path: Path) -> None:
    """A comparison with no baseline is a pass rate wearing a delta's name."""
    assert main(["--root", "tests/synthetic", "--baselines", str(tmp_path)]) == 2


def test_listing_baselines_works_on_an_empty_store(tmp_path: Path) -> None:
    """The first thing anybody runs, before there is anything to list."""
    assert main(["--baselines", str(tmp_path), "--list"]) == 0
