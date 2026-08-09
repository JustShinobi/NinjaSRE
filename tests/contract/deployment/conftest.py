"""The deployment artefacts, parsed once, for the tests that assert about them.

These tests read files rather than starting containers, and that is not a
compromise. The properties they check — four containers, non-root, an
`.env.example` that documents every setting, a chart whose sandbox pods cannot
egress — are all properties of the declarations, and a suite that needed a
Docker daemon to check them would be a suite that runs on somebody's machine
once a week instead of on every change.

The things that genuinely need infrastructure — a real image build, a Kind
install, a real backup and restore — run in their own CI jobs and skip cleanly
with a message when the infrastructure is absent, which is the pattern the
chaos and end-to-end suites already established here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# The scenario fixtures live with the harness's own tests, which is where they
# belong: they are what that suite uses to drive a real investigation. Importing
# them here rather than writing a second scenario means the egress monitor
# watches the same run the harness suite already exercises.
from tests.unit.harness.conftest import (  # noqa: F401 — re-exported as fixtures
    runnable_scenario,
    write_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "deploy"
COMPOSE = DEPLOY / "compose"
IMAGES = DEPLOY / "images"
CHART = DEPLOY / "helm" / "ninjasre"
OPS = DEPLOY / "ops"


def load_compose(path: Path) -> dict[str, Any]:
    """Return a compose file as a mapping.

    ``yaml.safe_load`` copes with everything in these files: the merge key in
    the standard profile's build anchor is YAML 1.1 and PyYAML resolves it,
    which is what lets the test see the same services Docker will.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path} is not a YAML mapping"
    return document


@pytest.fixture(scope="session")
def standard_compose() -> dict[str, Any]:
    """Return the standard profile's compose file."""
    return load_compose(COMPOSE / "docker-compose.yml")


@pytest.fixture(scope="session")
def dev_compose() -> dict[str, Any]:
    """Return the dev profile's compose file."""
    return load_compose(COMPOSE / "docker-compose.dev.yml")


@pytest.fixture(scope="session")
def homelab_compose() -> dict[str, Any]:
    """Return the homelab profile's compose file."""
    return load_compose(COMPOSE / "docker-compose.homelab.yml")


@pytest.fixture(scope="session")
def chart_values() -> dict[str, Any]:
    """Return the chart's default values."""
    document = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


@pytest.fixture(scope="session")
def chart_metadata() -> dict[str, Any]:
    """Return ``Chart.yaml``."""
    document = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def dockerfiles() -> tuple[Path, ...]:
    """Return every Dockerfile this repository ships for a deployment."""
    return tuple(sorted(IMAGES.glob("*.Dockerfile")))


def template_text(name: str) -> str:
    """Return one chart template's source, unrendered."""
    return (CHART / "templates" / name).read_text(encoding="utf-8")
