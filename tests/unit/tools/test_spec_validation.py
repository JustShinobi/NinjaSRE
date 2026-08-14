"""The spec browser gate delegates to the repository's existing console harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.spec_validation import main, normalise_test_path, validate_feature_directory

pytestmark = pytest.mark.unit


def test_normalise_test_path_removes_repository_and_console_prefixes() -> None:
    """Playwright receives paths relative to ``console/`` regardless of the caller."""
    console = Path("/workspace/NinjaSRE/console")

    assert normalise_test_path("console/tests/e2e/settings.spec.ts", console) == (
        "tests/e2e/settings.spec.ts"
    )
    assert normalise_test_path(
        "/workspace/NinjaSRE/console/tests/e2e/settings.spec.ts", console
    ) == ("tests/e2e/settings.spec.ts")


def test_normalise_test_path_keeps_console_relative_playwright_paths() -> None:
    """A path already relative to the console is passed through unchanged."""
    assert normalise_test_path("tests/e2e/settings.spec.ts", Path("/console")) == (
        "tests/e2e/settings.spec.ts"
    )


def test_validate_feature_directory_requires_the_spec_shape(tmp_path: Path) -> None:
    """A generic workflow refuses a directory that cannot be a spec feature."""
    feature = tmp_path / "001-example"
    feature.mkdir()
    (feature / "spec.md").write_text("# Example\n", encoding="utf-8")
    (feature / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (feature / "tasks.md").write_text("# Tasks\n", encoding="utf-8")

    validate_feature_directory(feature)


def test_validate_feature_directory_names_missing_files(tmp_path: Path) -> None:
    """The failure names the missing artifact instead of failing later in Playwright."""
    feature = tmp_path / "001-example"
    feature.mkdir()
    (feature / "spec.md").write_text("# Example\n", encoding="utf-8")
    (feature / "plan.md").write_text("# Plan\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tasks.md"):
        validate_feature_directory(feature)


def test_browser_dry_run_validates_the_feature_without_starting_services(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The workflow can be checked safely before it consumes a browser run."""
    feature = tmp_path / "001-example"
    feature.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        (feature / name).write_text(f"# {name}\n", encoding="utf-8")

    assert (
        main(
            [
                "browser",
                "--feature",
                str(feature),
                "--test",
                "console/tests/e2e/example.spec.ts",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "would build, then run behaviour against mock" in capsys.readouterr().out
