"""Run feature-scoped validation with the repository's existing test harness.

The spec workflow owns orchestration, while this module owns the deterministic
boundary between a feature directory and the console/browser lifecycle. Browser
tests never start their own servers: ``tools.console_e2e`` builds the standalone
console, starts the selected backing, provisions the pinned browser, chooses free
ports, runs Playwright, and tears everything down.

Usage::

    uv run python -m tools.spec_validation browser \
        --feature specs_v5/001-fundacao-vocabulario-ux \
        --test console/tests/e2e/vocabulary.spec.ts
    uv run python -m tools.spec_validation all \
        --feature specs_v5/001-fundacao-vocabulario-ux
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from config.constants.fixtures import DEFAULT_FIXTURE_SCENARIO
from tools import console_gate
from tools.console_e2e import HarnessError, run_staging
from tools.console_e2e import run as run_browser
from tools.console_toolchain import ToolchainError, console_root
from tools.console_visual import VisualError
from tools.console_visual import run as run_visual

REPO_ROOT = Path(__file__).resolve().parents[1]


def feature_path(raw: str) -> Path:
    """Return ``raw`` resolved relative to the repository root."""
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def validate_feature_directory(feature: Path) -> None:
    """Raise when ``feature`` does not contain the minimum spec-kit shape."""
    if not feature.is_dir():
        raise ValueError(f"feature directory does not exist: {feature}")

    for required in ("spec.md", "plan.md", "tasks.md"):
        if not (feature / required).is_file():
            raise ValueError(f"feature is missing {required}: {feature}")


def normalise_test_path(raw: str, console_directory: Path) -> str:
    """Return a Playwright test path relative to ``console_directory``."""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(console_directory.resolve()).as_posix()
        except ValueError as error:
            raise ValueError(f"Playwright test is outside console/: {raw}") from error

    parts = candidate.parts
    if parts and parts[0] == console_directory.name:
        parts = parts[1:]
    if not parts:
        raise ValueError(f"Playwright test path is empty: {raw}")
    return Path(*parts).as_posix()


def build_console() -> int:
    """Build the standalone console required by the browser lifecycle harness."""
    return console_gate.one("build")


def run_browser_validation(
    *,
    feature: Path,
    tests: Sequence[str],
    backing: str,
    scenario: str,
    project: str,
    repeat: int,
    build: bool,
    evidence_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Build and run the requested Playwright project for one feature.

    Raises:
        HarnessError: an argument that only makes sense for a backing which
            brings up its own environment was passed together with
            ``backing="staging"`` — a data scenario or a rebuild request,
            neither of which a shared, already-running deployment can honour.
            Refused rather than silently ignored: an argument that quietly
            does nothing is how somebody learns a flag works when it does not.
    """
    validate_feature_directory(feature)
    if repeat < 1:
        raise ValueError("repeat must be at least 1")

    console_directory = console_root()
    extra = tuple(normalise_test_path(test, console_directory) for test in tests)
    selected = ", ".join(extra) if extra else "the complete Playwright project"

    if backing == "staging":
        if scenario != DEFAULT_FIXTURE_SCENARIO:
            raise HarnessError(
                f"--scenario {scenario!r} does not apply to the staging backing — "
                "staging is one already-seeded deployment, not a dataset this "
                "harness chooses"
            )
        if not build:
            raise HarnessError(
                "--no-build does not apply to the staging backing — nothing here "
                "is ever built, so there is no existing build to reuse either"
            )
        if dry_run:
            print(
                f"spec browser: would run {project} against staging ({selected}, repeat={repeat})",
                flush=True,
            )
            return 0
        print(f"spec browser: {feature} -> {project}: {selected}", flush=True)
        return run_staging(
            project=project,
            evidence_dir=evidence_dir,
            repeat=repeat,
            extra=extra,
        )

    if dry_run:
        build_step = "build, then " if build else "reuse the existing build, then "
        print(
            f"spec browser: would {build_step}run {project} against {backing} "
            f"({selected}, repeat={repeat})",
            flush=True,
        )
        return 0
    if build:
        status = build_console()
        if status != 0:
            return status
    print(f"spec browser: {feature} -> {project}: {selected}", flush=True)
    return run_browser(
        backing=backing,
        scenario=scenario,
        project=project,
        repeat=repeat,
        extra=extra,
    )


def run_visual_validation(*, feature: Path, build: bool, dry_run: bool = False) -> int:
    """Build and compare the pinned visual Playwright suite for one feature."""
    validate_feature_directory(feature)
    if dry_run:
        build_step = "build, then " if build else "reuse the existing build, then "
        print(f"spec visual: would {build_step}compare committed visual baselines", flush=True)
        return 0
    if build:
        status = build_console()
        if status != 0:
            return status
    print(f"spec visual: {feature} -> committed visual baselines", flush=True)
    return run_visual()


def _add_browser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feature", required=True, help="spec-kit feature directory")
    parser.add_argument(
        "--test",
        dest="tests",
        action="append",
        default=[],
        help="Playwright test path, relative to the repository or console (repeatable)",
    )
    parser.add_argument("--backing", choices=("mock", "compose", "staging"), default="mock")
    parser.add_argument("--scenario", default=DEFAULT_FIXTURE_SCENARIO)
    parser.add_argument("--project", choices=("behaviour", "first-day"), default="behaviour")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="where the staging backing writes its full-page captures (staging only)",
    )
    parser.add_argument(
        "--no-build",
        dest="build",
        action="store_false",
        help="reuse the existing standalone build instead of rebuilding it",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan without starting services"
    )
    parser.set_defaults(build=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec_validation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    browser = commands.add_parser("browser", help="run feature-scoped behaviour Playwright tests")
    _add_browser_arguments(browser)

    visual = commands.add_parser("visual", help="compare the pinned visual Playwright suite")
    visual.add_argument("--feature", required=True, help="spec-kit feature directory")
    visual.add_argument("--no-build", dest="build", action="store_false")
    visual.add_argument(
        "--dry-run", action="store_true", help="print the plan without starting services"
    )
    visual.set_defaults(build=True)

    complete = commands.add_parser("all", help="run behaviour and visual validation")
    _add_browser_arguments(complete)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected spec validation flow and return its process status."""
    arguments = _parser().parse_args(list(argv) if argv is not None else None)
    feature = feature_path(arguments.feature)

    try:
        if arguments.command == "browser":
            return run_browser_validation(
                feature=feature,
                tests=arguments.tests,
                backing=arguments.backing,
                scenario=arguments.scenario,
                project=arguments.project,
                repeat=arguments.repeat,
                build=arguments.build,
                evidence_dir=arguments.evidence_dir,
                dry_run=arguments.dry_run,
            )
        if arguments.command == "visual":
            return run_visual_validation(
                feature=feature,
                build=arguments.build,
                dry_run=arguments.dry_run,
            )

        status = run_browser_validation(
            feature=feature,
            tests=arguments.tests,
            backing=arguments.backing,
            scenario=arguments.scenario,
            project=arguments.project,
            repeat=arguments.repeat,
            build=arguments.build,
            evidence_dir=arguments.evidence_dir,
            dry_run=arguments.dry_run,
        )
        if status != 0:
            return status
        return run_visual_validation(
            feature=feature,
            build=False,
            dry_run=arguments.dry_run,
        )
    except (HarnessError, ToolchainError, VisualError, ValueError) as error:
        print(f"spec validation: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_console",
    "feature_path",
    "main",
    "normalise_test_path",
    "run_browser_validation",
    "run_visual_validation",
    "validate_feature_directory",
]
