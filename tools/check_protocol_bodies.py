"""Fail the build on a ``Protocol`` method body that is anything but a docstring.

FR-018. The failure this prevents is subtle and expensive. A ``Protocol`` method
whose body is ``...`` or ``pass`` type-checks perfectly, but the moment the
protocol is used as a concrete base — which happens, because it looks like an
ABC — the stub silently becomes the implementation and the method returns
``None``. ``raise NotImplementedError`` is the same mistake wearing a warning
label: it converts a static contract into a runtime landmine, and turns a class
of error mypy would have caught into one only production finds.

The contract is the signature and the docstring. Everything below is filler.

The docstring-then-filler form is called out separately in FR-018 for a reason:
it is the one that reads as finished.

Usage::

    python tools/check_protocol_bodies.py [path ...]

Exits 0 when clean, 1 when a violation is found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ELLIPSIS_BODY = "ellipsis-body"
PASS_BODY = "pass-body"
NOT_IMPLEMENTED_BODY = "not-implemented-body"

PROTOCOL_NAME = "Protocol"
NOT_IMPLEMENTED_ERROR = "NotImplementedError"

#: Roots scanned when none are given: the seven first-party packages. Repository
#: tooling declares no protocols, and the architecture fixtures are broken on
#: purpose.
DEFAULT_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "core",
    REPO_ROOT / "gateway",
    REPO_ROOT / "integrations",
    REPO_ROOT / "platform",
    REPO_ROOT / "surfaces",
)

SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".venv", ".git", "_research", "node_modules"})

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, order=True)
class Violation:
    """One protocol method whose body says more than its docstring."""

    path: Path
    line: int
    qualified_name: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.qualified_name}"


def _base_names(node: ast.ClassDef) -> set[str]:
    """Return the trailing identifier of every base, however it is written."""
    names: set[str] = set()

    for base in node.bases:
        candidate: ast.expr = base
        # Protocol[T] -> Protocol
        if isinstance(candidate, ast.Subscript):
            candidate = candidate.value
        # typing.Protocol -> Protocol
        if isinstance(candidate, ast.Attribute):
            names.add(candidate.attr)
        elif isinstance(candidate, ast.Name):
            names.add(candidate.id)

    return names


def is_protocol(node: ast.ClassDef) -> bool:
    """Return whether ``node`` declares a typing Protocol."""
    return PROTOCOL_NAME in _base_names(node)


def _raises_not_implemented(statement: ast.stmt) -> bool:
    """Return whether ``statement`` raises ``NotImplementedError``, called or not."""
    if not isinstance(statement, ast.Raise) or statement.exc is None:
        return False

    raised = statement.exc
    if isinstance(raised, ast.Call):
        raised = raised.func

    if isinstance(raised, ast.Attribute):
        return raised.attr == NOT_IMPLEMENTED_ERROR
    return isinstance(raised, ast.Name) and raised.id == NOT_IMPLEMENTED_ERROR


def _statement_rule(statement: ast.stmt) -> str | None:
    """Return the rule ``statement`` breaks as a protocol body, if any."""
    if isinstance(statement, ast.Pass):
        return PASS_BODY
    if (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    ):
        return ELLIPSIS_BODY
    if _raises_not_implemented(statement):
        return NOT_IMPLEMENTED_BODY
    return None


def _method_violations(path: Path, class_name: str, method: _FunctionNode) -> list[Violation]:
    """Return the violations in one protocol method's body."""
    return [
        Violation(path, statement.lineno, f"{class_name}.{method.name}", rule)
        for statement in method.body
        if (rule := _statement_rule(statement)) is not None
    ]


def module_violations(path: Path, source: str) -> list[Violation]:
    """Return every protocol-body violation in one module's source."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"{path}: could not be parsed: {error}") from error

    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not is_protocol(node):
            continue
        for member in node.body:
            if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                violations.extend(_method_violations(path, node.name, member))

    return violations


def python_files(root: Path) -> list[Path]:
    """Return the Python files under ``root``, skipping caches and vendored trees."""
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    if not root.is_dir():
        return []

    return sorted(
        candidate
        for candidate in root.rglob("*.py")
        if not SKIPPED_DIRECTORY_NAMES.intersection(candidate.parts)
    )


def find_violations(roots: Iterable[Path]) -> list[Violation]:
    """Return every violation under ``roots``, sorted for a stable report."""
    violations: list[Violation] = []

    for root in roots:
        for path in python_files(Path(root)):
            violations.extend(module_violations(path, path.read_text(encoding="utf-8")))

    return sorted(violations)


def main(argv: Sequence[str] | None = None) -> int:
    """Scan ``argv`` paths, or the default roots, and report what was found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to scan (default: the first-party packages)",
    )
    arguments = parser.parse_args(argv)

    violations = find_violations(tuple(arguments.paths) or DEFAULT_SCAN_ROOTS)

    if not violations:
        return 0

    print(f"{len(violations)} protocol method(s) with a filled body:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nA Protocol method body is its docstring and nothing else (FR-018). "
        "A stub that is `...`, `pass`, or `raise NotImplementedError` becomes "
        "the implementation the moment the protocol is used as a concrete base.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
