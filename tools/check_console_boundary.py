"""Fail the build on a Python import of the console, or a console import of Python.

The console is a TypeScript application at the root of the repository, a peer of
the Python tiers rather than a member of one. That is a boundary, and a boundary
nothing enforces is a convention — so this is the enforcement.

It is a script rather than an ``import-linter`` contract for one reason:
``import-linter`` reasons about importable Python packages, and ``console/`` is
not one. Giving it an ``__init__.py`` so that a contract could name it would
create exactly the thing the boundary exists to prevent.

Two rules, one in each direction:

``python-imports-console``
    A first-party Python module importing ``console``. The console is served
    over HTTP by a process of its own; a Python module that imported it would be
    reaching across a language boundary at import time, which cannot work and
    would have to be a directory named ``console`` inside the Python tree —
    which is the state this feature exists to leave behind.

``console-imports-python``
    A console source file reaching into the Python tree — ``../gateway``,
    ``../platform`` and the rest. The console is a client of the REST API and
    nothing else. Reading a Python module's source, or a package's data files,
    would make the console depend on the application's internals rather than on
    its published contract.

The committed copy of the OpenAPI document and the committed fixture dataset are
both allowed: they are data, they are generated from the application by checks
that already exist, and reading them is how the console stays a client rather
than becoming a second implementation.

Usage::

    python tools/check_console_boundary.py [path ...]

Exits 0 when clean, 1 when a violation is found.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from config.constants.console import CONSOLE_DIR_NAME

REPO_ROOT: Final = Path(__file__).resolve().parents[1]

PYTHON_RULE: Final = "python-imports-console"
CONSOLE_RULE: Final = "console-imports-python"

#: The Python packages a console file must not reach into. ``config`` is on the
#: list too: a shared constant is a shared constant whichever tier owns it, and
#: the console's own pins live in its own tree.
PYTHON_PACKAGES: Final[tuple[str, ...]] = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
    "tests",
    "tools",
)

#: What the console may read from outside its own directory: generated data,
#: and nothing that is code.
PERMITTED_FROM_CONSOLE: Final[tuple[str, ...]] = ("fixtures",)

#: Python roots scanned when none are given.
DEFAULT_PYTHON_ROOTS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "core",
    REPO_ROOT / "gateway",
    REPO_ROOT / "integrations",
    REPO_ROOT / "platform",
    REPO_ROOT / "surfaces",
)

#: Where a console file names a path outside its own directory.
_RELATIVE_PARENT = re.compile(r"""['"`](\.\./[^'"`]*)['"`]""")

#: The console's own source, excluding what it did not write.
_CONSOLE_SUFFIXES: Final[tuple[str, ...]] = (".ts", ".tsx", ".mjs", ".js", ".mts")

_CONSOLE_IGNORED: Final[frozenset[str]] = frozenset(
    {"node_modules", ".next", ".toolchain", "coverage", "test-results", "playwright-report"}
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One import that crosses the boundary, named where it is written."""

    rule: str
    path: Path
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self._location()}:{self.line}: [{self.rule}] {self.detail}"

    def _location(self) -> Path:
        """Return the path as short as it can be said without becoming ambiguous."""
        try:
            return self.path.relative_to(REPO_ROOT)
        except ValueError:
            return self.path


def _python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
        elif root.is_dir():
            yield from sorted(root.rglob("*.py"))


def check_python(roots: Iterable[Path]) -> list[Violation]:
    """Return every Python import of the console."""
    found: list[Violation] = []
    for path in _python_files(roots):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == CONSOLE_DIR_NAME or alias.name.startswith(
                        f"{CONSOLE_DIR_NAME}."
                    ):
                        found.append(
                            Violation(
                                PYTHON_RULE,
                                path,
                                node.lineno,
                                f"imports {alias.name}; the console is served over HTTP by a "
                                f"process of its own and is not a Python package",
                            )
                        )
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                module = node.module or ""
                if module == CONSOLE_DIR_NAME or module.startswith(f"{CONSOLE_DIR_NAME}."):
                    found.append(
                        Violation(
                            PYTHON_RULE,
                            path,
                            node.lineno,
                            f"imports from {module}; the console is served over HTTP by a "
                            f"process of its own and is not a Python package",
                        )
                    )
    return found


def _console_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.suffix not in _CONSOLE_SUFFIXES:
            continue
        if _CONSOLE_IGNORED.intersection(path.relative_to(root).parts):
            continue
        yield path


def check_console(root: Path) -> list[Violation]:
    """Return every console reference that reaches into the Python tree."""
    found: list[Violation] = []
    for path in _console_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            for match in _RELATIVE_PARENT.finditer(line):
                target = match.group(1)
                head = target.removeprefix("../").split("/", 1)[0]
                if head in PERMITTED_FROM_CONSOLE:
                    continue
                if head in PYTHON_PACKAGES:
                    found.append(
                        Violation(
                            CONSOLE_RULE,
                            path,
                            number,
                            f"reads {target}; the console is a client of the REST API and "
                            f"nothing else",
                        )
                    )
    return found


def check(python_roots: Iterable[Path], console: Path) -> list[Violation]:
    """Return every violation of the boundary, in both directions."""
    return [*check_python(python_roots), *check_console(console)]


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--console", type=Path, default=REPO_ROOT / CONSOLE_DIR_NAME)
    arguments = parser.parse_args(argv)

    roots = tuple(arguments.paths) if arguments.paths else DEFAULT_PYTHON_ROOTS
    violations = check(roots, arguments.console)
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        print(
            f"\n{len(violations)} boundary violation(s). The console is a peer of the Python "
            f"tiers, not a member of one.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
