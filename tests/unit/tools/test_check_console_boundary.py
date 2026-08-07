"""The console boundary, and the deliberate violations that prove it fires.

The boundary is that the console is a peer of the Python tiers rather than a
member of one: nothing in the Python tree imports it, and it reaches into no
Python package. A check nobody has watched fail is a check that might be
scanning an empty list of roots, and the repository would look exactly as clean
either way — so each direction has a fixture that breaks it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_console_boundary import (
    CONSOLE_RULE,
    DEFAULT_PYTHON_ROOTS,
    PYTHON_RULE,
    REPO_ROOT,
    check,
    check_console,
    check_python,
)

pytestmark = pytest.mark.unit

#: A Python module that reached for the console. It cannot work — the console is
#: TypeScript — and the only way to make it work is the thing the boundary
#: exists to prevent.
PYTHON_VIOLATION = '''
"""A gateway route that reached across the boundary."""

from __future__ import annotations

import console
from console.pages import runs


def render() -> str:
    """Return a page the console should have rendered over HTTP."""
    return runs.render(console.theme())
'''

#: A console file that reached into the application's internals rather than
#: calling its published contract.
CONSOLE_VIOLATION = """
import { PERMISSIONS } from '../platform/identity/permissions';
import catalogue from '../config/constants/surfaces.py';

export const roles = PERMISSIONS ?? catalogue;
"""

#: What the console is allowed to read from outside its own directory: generated
#: data, checked against the application by the checks that generate it.
CONSOLE_PERMITTED = """
import runs from '../fixtures/scenarios/populated/runs.json';

export default runs;
"""


def test_a_python_import_of_the_console_is_reported(tmp_path: Path) -> None:
    """Both spellings of the import, each named where it is written."""
    module = tmp_path / "routes.py"
    module.write_text(PYTHON_VIOLATION, encoding="utf-8")

    violations = check_python([tmp_path])

    assert len(violations) == 2, violations
    assert {violation.rule for violation in violations} == {PYTHON_RULE}
    assert all(violation.path == module for violation in violations)
    assert all(violation.line > 0 for violation in violations)


def test_a_console_reach_into_the_python_tree_is_reported(tmp_path: Path) -> None:
    """A path out of the console and into a package is a violation, not a shortcut."""
    console = tmp_path / "console"
    console.mkdir()
    source = console / "roles.ts"
    source.write_text(CONSOLE_VIOLATION, encoding="utf-8")

    violations = check_console(console)

    assert len(violations) == 2, violations
    assert {violation.rule for violation in violations} == {CONSOLE_RULE}
    assert "platform" in str(violations[0]) or "platform" in str(violations[1])


def test_the_console_may_read_the_committed_dataset(tmp_path: Path) -> None:
    """The fixtures are data, generated from the application by a check of their own."""
    console = tmp_path / "console"
    console.mkdir()
    (console / "data.ts").write_text(CONSOLE_PERMITTED, encoding="utf-8")

    assert check_console(console) == []


def test_what_the_toolchain_installs_is_not_scanned(tmp_path: Path) -> None:
    """A dependency's own source is not the console's, and there are 40,000 files of it."""
    console = tmp_path / "console"
    vendored = console / "node_modules" / "some-package"
    vendored.mkdir(parents=True)
    (vendored / "index.ts").write_text(CONSOLE_VIOLATION, encoding="utf-8")

    assert check_console(console) == []


def test_a_violation_names_the_file_and_the_line(tmp_path: Path) -> None:
    """A report that does not say where is a report somebody has to go looking for."""
    module = tmp_path / "reaching.py"
    module.write_text("import console\n", encoding="utf-8")

    (violation,) = check_python([tmp_path])

    assert str(violation).startswith(f"{module}:1: [{PYTHON_RULE}]")


def test_the_repository_keeps_the_boundary() -> None:
    """The rule this feature added, asserted against the tree it was added to."""
    assert check(DEFAULT_PYTHON_ROOTS, REPO_ROOT / "console") == []
