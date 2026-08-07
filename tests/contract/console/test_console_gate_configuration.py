"""What the gate claims about the console, asserted against its own configuration.

Every number in ``config/constants/console.py`` is a claim about a file the
Python suite does not otherwise read: a coverage floor the JavaScript runner
enforces, a container image the capture runs in, a pinned browser. A claim
nobody checks drifts, and drifts silently — the constant still says ninety while
the runner says fifty, and the only symptom is that nothing ever fails.

So each one is compared against the file that actually acts on it. None of this
needs the toolchain provisioned: it reads committed text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from config.constants.console import (
    CONSOLE_COVERAGE_THRESHOLD,
    CONSOLE_DIR_NAME,
    CONSOLE_GENERATED_CLIENT_PATH,
    CONSOLE_LOCKFILE_FILENAME,
    CONSOLE_MANIFEST_FILENAME,
    CONSOLE_VISUAL_IMAGE,
    CONSOLE_VISUAL_MAX_DIFFERING_PIXELS,
    NINJASRE_CONSOLE_API_URL_ENV,
    NINJASRE_CONSOLE_BASE_PATH_ENV,
    NINJASRE_CONSOLE_BASE_URL_ENV,
)
from config.constants.fixtures import FIXTURE_CONTRACT_DIR_NAME, FIXTURE_OPENAPI_FILENAME
from tools.console_gate import ORDER, SCRIPTED
from tools.console_toolchain import REPO_ROOT, console_root, read_pin

pytestmark = pytest.mark.contract

CONSOLE = console_root()
MAKEFILE = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")


def manifest() -> dict[str, Any]:
    """Return the console's package manifest."""
    loaded: Any = json.loads((CONSOLE / CONSOLE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_console_is_not_a_python_package() -> None:
    """An ``__init__.py`` here would make it a tier, which is the thing it is not."""
    assert not (CONSOLE / "__init__.py").exists()
    assert not list(CONSOLE.glob("*.py"))


def test_the_console_lives_at_the_repository_root() -> None:
    """A peer of the tiers, not a directory inside one."""
    assert CONSOLE.parent == REPO_ROOT
    assert CONSOLE.name == CONSOLE_DIR_NAME
    assert not (REPO_ROOT / "surfaces" / "console" / "package.json").exists()


def test_the_manifest_and_the_lockfile_are_both_committed() -> None:
    """One directory, one manifest, one lockfile."""
    assert (CONSOLE / CONSOLE_MANIFEST_FILENAME).is_file()
    assert (CONSOLE / CONSOLE_LOCKFILE_FILENAME).is_file()


def test_the_coverage_floor_the_runner_enforces_is_the_declared_one() -> None:
    """The number in the constants tier is the number the runner fails on."""
    configuration = (CONSOLE / "vitest.config.ts").read_text(encoding="utf-8")
    thresholds = re.search(r"thresholds:\s*\{(.*?)\}", configuration, re.DOTALL)
    assert thresholds is not None, "the unit runner declares no coverage thresholds"

    declared = {int(value) for value in re.findall(r":\s*(\d+)", thresholds.group(1))}
    assert declared == {int(CONSOLE_COVERAGE_THRESHOLD)}, (
        f"the runner enforces {sorted(declared)} but the constants tier declares "
        f"{CONSOLE_COVERAGE_THRESHOLD}"
    )


def test_the_visual_suite_tolerates_no_differing_pixels() -> None:
    """A threshold is where a visual gate goes to become advisory."""
    configuration = (CONSOLE / "playwright.config.ts").read_text(encoding="utf-8")
    found = re.search(r"maxDiffPixels:\s*(\d+)", configuration)
    assert found is not None, "the browser configuration declares no pixel budget"
    assert int(found.group(1)) == CONSOLE_VISUAL_MAX_DIFFERING_PIXELS


def test_the_capture_image_is_pinned_by_digest() -> None:
    """A tag moves, and a moved tag is a suite of differences that mean nothing."""
    assert "@sha256:" in CONSOLE_VISUAL_IMAGE
    lock: Any = json.loads((CONSOLE / "toolchain.lock.json").read_text(encoding="utf-8"))
    assert lock["playwright"]["image"] == CONSOLE_VISUAL_IMAGE


def test_the_browser_the_image_carries_is_the_browser_the_manifest_pins() -> None:
    """Two versions of the browser is two sets of baselines that disagree."""
    lock: Any = json.loads((CONSOLE / "toolchain.lock.json").read_text(encoding="utf-8"))
    pinned = str(lock["playwright"]["version"])

    assert manifest()["devDependencies"]["@playwright/test"] == pinned
    assert f"v{pinned}-" in CONSOLE_VISUAL_IMAGE


def test_the_node_and_package_manager_pins_agree_with_the_manifest() -> None:
    """The version a contributor provisions is the version CI provisions."""
    pin = read_pin()
    engines = manifest()["engines"]

    assert engines["node"] == pin.node_version
    assert manifest()["packageManager"] == f"pnpm@{pin.pnpm_version}"


def test_the_client_is_generated_from_the_committed_api_document() -> None:
    """Offline, from a copy in the repository, so an air-gapped build works."""
    generation = manifest()["scripts"]["client"]
    document = REPO_ROOT / "fixtures" / FIXTURE_CONTRACT_DIR_NAME / FIXTURE_OPENAPI_FILENAME

    assert FIXTURE_OPENAPI_FILENAME in generation
    assert CONSOLE_GENERATED_CLIENT_PATH in generation
    assert document.is_file(), "the committed OpenAPI document is missing"
    assert (CONSOLE / CONSOLE_GENERATED_CLIENT_PATH).is_file(), "the client is not committed"
    assert "http" not in generation, "the generation reaches for a running gateway"


@pytest.mark.parametrize("check", ORDER)
def test_every_check_is_individually_runnable_from_the_makefile(check: str) -> None:
    """A contributor iterating on one check need not run all of them."""
    assert f"\nconsole-{check}:" in MAKEFILE, f"there is no `make console-{check}` target"


def test_the_gate_runs_every_console_check() -> None:
    """`make verify` is the definition of done, so nothing may sit outside it."""
    verify = MAKEFILE.split("\nverify:", 1)[1].split("## The single quality gate")[0]
    assert "console-check" in verify

    scripted = {check.name for check in SCRIPTED}
    assert scripted <= set(ORDER), "a scripted check is not in the order `all` runs"
    for required in ("format-check", "lint", "typecheck", "test", "build", "e2e", "visual"):
        assert required in ORDER, f"the gate does not run {required}"


def test_the_build_output_is_servable_behind_a_proxy_on_a_configured_path() -> None:
    """One built artefact, served wherever the operator's proxy puts it."""
    configuration = (CONSOLE / "next.config.ts").read_text(encoding="utf-8")

    assert "standalone" in configuration, "the build does not produce a self-contained server"
    assert NINJASRE_CONSOLE_BASE_PATH_ENV in configuration, (
        "the base path is not configurable, so the console can only be served at the root"
    )


def test_the_gateway_address_is_read_at_run_time_rather_than_baked_in() -> None:
    """A build that baked it in would only run on the machine that built it."""
    client: Path = CONSOLE / "src" / "lib" / "api.ts"
    assert NINJASRE_CONSOLE_API_URL_ENV in client.read_text(encoding="utf-8")


def test_the_browser_suite_is_told_where_the_console_is() -> None:
    """The harness owns process lifecycle; the suite is handed an address."""
    configuration = (CONSOLE / "playwright.config.ts").read_text(encoding="utf-8")
    assert NINJASRE_CONSOLE_BASE_URL_ENV in configuration
    assert "webServer" not in configuration, (
        "a browser suite that also owns process lifecycle is one that hangs"
    )


def test_the_browser_suite_never_retries() -> None:
    """A retry hides a flake, and a hidden flake is why suites get disabled."""
    configuration = (CONSOLE / "playwright.config.ts").read_text(encoding="utf-8")
    found = re.search(r"retries:\s*(\d+)", configuration)
    assert found is not None and int(found.group(1)) == 0


def test_the_seeded_failure_fixtures_are_outside_every_check() -> None:
    """They are broken on purpose; a check that walked into them would never pass."""
    for configuration, name in (
        ((CONSOLE / "eslint.config.mjs").read_text(encoding="utf-8"), "the lint configuration"),
        ((CONSOLE / ".prettierignore").read_text(encoding="utf-8"), "the format configuration"),
        ((CONSOLE / "tsconfig.json").read_text(encoding="utf-8"), "the type configuration"),
    ):
        assert "fixtures" in configuration, f"{name} does not exclude the seeded failures"
