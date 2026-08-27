"""No telemetry package reaches the runtime dependency tree.

Article X is unambiguous: NinjaSRE contains no first-party telemetry, analytics,
crash reporting, or usage tracking that transmits off-host. A direct dependency
would be caught in review; a transitive one, pulled in three levels down by a
library nobody read the changelog of, would not. FR-014 and SC-005 make it a
build failure either way.
"""

from __future__ import annotations

import pytest

from tools.check_dependencies import (
    TELEMETRY_DENY_LIST,
    find_banned_dependencies,
    normalise_package_name,
    runtime_dependency_names,
)

pytestmark = pytest.mark.unit

ROOT_PACKAGE = "ninjasre"


def lock(*packages: str) -> str:
    """Return a uv.lock document containing ``packages``."""
    return 'version = 1\nrequires-python = ">=3.12"\n\n' + "\n".join(packages)


def package(
    name: str,
    dependencies: tuple[str, ...] = (),
    dev_dependencies: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
) -> str:
    """Return one ``[[package]]`` block."""
    block = [f'[[package]]\nname = "{name}"\nversion = "1.0.0"']

    if dependencies:
        entries = ", ".join(f'{{ name = "{item}" }}' for item in dependencies)
        block.append(f"dependencies = [{entries}]")

    if optional:
        entries = ", ".join(f'{{ name = "{item}" }}' for item in optional)
        block.append(f"[package.optional-dependencies]\nextra = [{entries}]")

    if dev_dependencies:
        entries = ", ".join(f'{{ name = "{item}" }}' for item in dev_dependencies)
        block.append(f"[package.dev-dependencies]\ndev = [{entries}]")

    return "\n".join(block) + "\n"


# --- Name normalisation ------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("sentry-sdk", "sentry-sdk"),
        ("sentry_sdk", "sentry-sdk"),
        ("Sentry.SDK", "sentry-sdk"),
        ("SEGMENT__ANALYTICS_PYTHON", "segment-analytics-python"),
    ],
)
def test_normalises_names_the_way_the_index_does(written: str, expected: str) -> None:
    """A deny-list that only matched one spelling would be trivially evaded."""
    assert normalise_package_name(written) == expected


# --- Walking the tree --------------------------------------------------------


def test_walks_transitive_runtime_dependencies() -> None:
    document = lock(
        package(ROOT_PACKAGE, dependencies=("structlog",)),
        package("structlog", dependencies=("typing-extensions",)),
        package("typing-extensions"),
    )

    assert runtime_dependency_names(document, ROOT_PACKAGE) == {
        "structlog",
        "typing-extensions",
    }


def test_the_root_package_is_not_its_own_dependency() -> None:
    document = lock(package(ROOT_PACKAGE, dependencies=("structlog",)), package("structlog"))

    assert ROOT_PACKAGE not in runtime_dependency_names(document, ROOT_PACKAGE)


def test_survives_a_dependency_cycle() -> None:
    """A malformed or vendored lock must not hang the build."""
    document = lock(
        package(ROOT_PACKAGE, dependencies=("alpha",)),
        package("alpha", dependencies=("beta",)),
        package("beta", dependencies=("alpha",)),
    )

    assert runtime_dependency_names(document, ROOT_PACKAGE) == {"alpha", "beta"}


def test_development_dependencies_are_not_runtime() -> None:
    document = lock(
        package(ROOT_PACKAGE, dependencies=("structlog",), dev_dependencies=("pytest",)),
        package("structlog"),
        package("pytest"),
    )

    assert runtime_dependency_names(document, ROOT_PACKAGE) == {"structlog"}


def test_optional_extras_are_exempt() -> None:
    """An extra is opted into deliberately; it is not what ships by default."""
    document = lock(
        package(ROOT_PACKAGE, dependencies=("structlog",), optional=("posthog",)),
        package("structlog"),
        package("posthog"),
    )

    assert runtime_dependency_names(document, ROOT_PACKAGE) == {"structlog"}


# --- The deny-list -----------------------------------------------------------


def test_the_deny_list_covers_the_named_packages() -> None:
    named_in_the_spec = {
        "amplitude-analytics",
        "analytics-python",
        "mixpanel",
        "posthog",
        "segment-analytics-python",
        "sentry-sdk",
    }

    assert named_in_the_spec.issubset(TELEMETRY_DENY_LIST)


def test_flags_a_direct_telemetry_dependency() -> None:
    document = lock(package(ROOT_PACKAGE, dependencies=("posthog",)), package("posthog"))

    assert find_banned_dependencies(document, ROOT_PACKAGE) == ["posthog"]


def test_flags_a_telemetry_dependency_three_levels_down() -> None:
    """The case review misses."""
    document = lock(
        package(ROOT_PACKAGE, dependencies=("alpha",)),
        package("alpha", dependencies=("beta",)),
        package("beta", dependencies=("sentry_sdk",)),
        package("sentry_sdk"),
    )

    assert find_banned_dependencies(document, ROOT_PACKAGE) == ["sentry-sdk"]


def test_reports_every_match_in_a_stable_order() -> None:
    document = lock(
        package(ROOT_PACKAGE, dependencies=("posthog", "mixpanel")),
        package("posthog"),
        package("mixpanel"),
    )

    assert find_banned_dependencies(document, ROOT_PACKAGE) == ["mixpanel", "posthog"]


def test_a_clean_tree_reports_nothing() -> None:
    document = lock(package(ROOT_PACKAGE, dependencies=("structlog",)), package("structlog"))

    assert find_banned_dependencies(document, ROOT_PACKAGE) == []


def test_a_missing_root_package_is_an_error() -> None:
    """Silently passing on an unreadable lock would defeat the whole check."""
    with pytest.raises(ValueError, match=ROOT_PACKAGE):
        runtime_dependency_names(lock(package("structlog")), ROOT_PACKAGE)


# --- The repository itself ---------------------------------------------------


@pytest.mark.sweep
def test_the_repository_ships_no_telemetry() -> None:
    """SC-005: zero runtime dependencies match the deny-list."""
    from tools.check_dependencies import LOCK_FILE, PROJECT_NAME

    banned = find_banned_dependencies(LOCK_FILE.read_text(encoding="utf-8"), PROJECT_NAME)

    assert banned == []
