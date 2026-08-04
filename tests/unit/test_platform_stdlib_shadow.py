"""The ``platform`` package shadows the stdlib name without breaking it.

``platform/`` deliberately shares its name with Python's stdlib ``platform``
module. That is only acceptable while every caller of the stdlib API — including third-party
dependencies that have never heard of NinjaSRE — keeps working unchanged.

Two things must hold at once, and each has a test below:

1. The shadow is real. With the repository root leading ``sys.path``, which is
   how every NinjaSRE process runs, ``import platform`` reaches the first-party
   package, so ``platform.observability`` and its siblings are importable.
2. The shadow is transparent. The stdlib module's public API is re-exported, so
   ``platform.system()`` still returns a value for a caller that wanted the
   stdlib and knows nothing about this repository.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import platform

REPO_ROOT = Path(__file__).resolve().parents[2]

# A representative slice of the stdlib module's public API. If the re-export
# mechanism regresses, these disappear before anything else does.
STDLIB_PLATFORM_ATTRIBUTES = (
    "machine",
    "node",
    "platform",
    "processor",
    "python_version",
    "release",
    "system",
    "version",
)

pytestmark = pytest.mark.unit


def test_platform_resolves_to_the_first_party_package() -> None:
    """The shadow is real: ``import platform`` reaches the repository package."""
    module_file = platform.__file__
    assert module_file is not None
    assert Path(module_file).resolve().is_relative_to(REPO_ROOT)
    assert hasattr(platform, "__path__"), "the shadowing module must be a package"


@pytest.mark.parametrize("attribute", STDLIB_PLATFORM_ATTRIBUTES)
def test_stdlib_platform_api_is_re_exported(attribute: str) -> None:
    """Every re-exported name is present and callable."""
    assert hasattr(platform, attribute), f"stdlib platform.{attribute} was not re-exported"
    assert callable(getattr(platform, attribute))


def test_system_returns_a_value() -> None:
    """The canonical call from the acceptance criterion returns a real answer."""
    assert platform.system()
    assert platform.python_version().startswith("3.")


def test_third_party_import_of_platform_still_works() -> None:
    """A plain interpreter rooted in the repository gets a working module.

    This is the case that matters and the one the test suite cannot fake: no
    conftest, no fixtures, just an import from a working directory where the
    package shadows the stdlib name — exactly what a third-party dependency
    inside the virtual environment sees at runtime.
    """
    probe = (
        "import platform;"
        "print(platform.__file__);"
        "print(platform.system());"
        "print(platform.python_version())"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    resolved_file, system, python_version = result.stdout.strip().splitlines()

    assert Path(resolved_file).resolve().is_relative_to(REPO_ROOT), (
        "the repository package did not shadow the stdlib name"
    )
    assert system, "platform.system() returned nothing through the shadowing package"
    assert python_version.startswith("3.")
