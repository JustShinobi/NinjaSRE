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


# --- The staging backing: exposed on the CLI, and refuses what does not apply --


def test_a_dry_run_against_staging_never_mentions_building(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Staging is announced as itself — nothing here is ever built."""
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
                "--backing",
                "staging",
                "--dry-run",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "build" not in out, out
    assert "staging" in out


def test_a_scenario_other_than_the_default_is_refused_against_staging(
    tmp_path: Path,
) -> None:
    """A data scenario is a `mock` concept; staging is one deployment, already seeded."""
    feature = tmp_path / "001-example"
    feature.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        (feature / name).write_text(f"# {name}\n", encoding="utf-8")

    status = main(
        [
            "browser",
            "--feature",
            str(feature),
            "--backing",
            "staging",
            "--scenario",
            "degraded",
        ]
    )
    assert status != 0


def test_no_build_is_refused_against_staging_rather_than_ignored(tmp_path: Path) -> None:
    """`--no-build` names a concept — reuse an existing build — staging has no build to reuse."""
    feature = tmp_path / "001-example"
    feature.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        (feature / name).write_text(f"# {name}\n", encoding="utf-8")

    status = main(
        [
            "browser",
            "--feature",
            str(feature),
            "--backing",
            "staging",
            "--no-build",
        ]
    )
    assert status != 0


def test_staging_never_calls_build_console_even_though_build_defaults_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default `build=True` never reaches a build step when the backing is staging."""
    import tools.spec_validation as spec_validation

    feature = tmp_path / "001-example"
    feature.mkdir()
    for name in ("spec.md", "plan.md", "tasks.md"):
        (feature / name).write_text(f"# {name}\n", encoding="utf-8")

    def _must_not_build() -> int:
        pytest.fail("build_console() was called for the staging backing")
        return 1

    def _fake_run_staging(**_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(spec_validation, "build_console", _must_not_build)
    monkeypatch.setattr(spec_validation, "run_staging", _fake_run_staging)

    status = main(["browser", "--feature", str(feature), "--backing", "staging"])
    assert status == 0
