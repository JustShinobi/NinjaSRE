"""Fail the build on an environment-variable name outside the constants tier.

FR-009 puts every environment-variable name under ``config/constants/``. FR-010
makes it enforceable. This is the enforcement.

Two rules, and the second is the one that actually holds the line:

``env-name-literal``
    A string literal shaped like an environment-variable name — ``NINJASRE_*``
    or one of the vendor prefixes below — written anywhere but the constants
    tier. Pattern matching, so the prefix list is never complete.

``env-lookup``
    A string literal passed to an environment lookup: ``os.getenv(...)``,
    ``os.environ[...]``, ``os.environ.get(...)``, or the bare ``environ`` and
    ``getenv`` names imported from ``os``. This catches any variable, from any
    vendor, whatever it is called — including the tenth provider nobody has
    added a prefix for yet.

``tests/`` is not scanned. A test that sets or clears an environment variable is
doing its job, and forcing it through a constant would only hide what it does.

Usage::

    python tools/check_constants.py [path ...]

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

REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_NAME_RULE = "env-name-literal"
ENV_LOOKUP_RULE = "env-lookup"

#: The tier that owns environment-variable names, identified by these
#: consecutive path parts so the check works on any checkout root.
CONSTANTS_TIER_PARTS = ("config", "constants")

#: Roots scanned when none are given: the seven first-party packages plus
#: repository tooling.
DEFAULT_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "core",
    REPO_ROOT / "gateway",
    REPO_ROOT / "integrations",
    REPO_ROOT / "platform",
    REPO_ROOT / "surfaces",
    REPO_ROOT / "tools",
)

SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".venv", ".git", "_research", "node_modules"})

#: An environment-variable name is SCREAMING_SNAKE with at least one underscore
#: separating non-empty segments. ``GET`` is not one; ``NINJASRE_HOME_DIR`` is.
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")

#: Prefixes worth flagging on sight. Deliberately not exhaustive — the
#: ``env-lookup`` rule is what covers everything else.
VENDOR_ENV_PREFIXES: tuple[str, ...] = (
    "ANTHROPIC_",
    "AWS_",
    "AZURE_",
    "DATABASE_",
    "GEMINI_",
    "GOOGLE_",
    "NVIDIA_",
    "OLLAMA_",
    "OPENAI_",
    "OPENROUTER_",
    "POSTGRES_",
    "VERTEX_",
    "VLLM_",
    "XDG_",
)

NINJASRE_ENV_PREFIX = "NINJASRE_"

_ENVIRON_ATTRIBUTE = "environ"
_GETENV_FUNCTIONS = frozenset({"getenv"})


@dataclass(frozen=True, order=True)
class Violation:
    """One environment-variable name written where it does not belong."""

    path: Path
    line: int
    name: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.name!r}"


def is_exempt(path: Path) -> bool:
    """Return whether ``path`` lives in the tier that owns these names."""
    parts = path.parts
    window = len(CONSTANTS_TIER_PARTS)
    return any(
        parts[index : index + window] == CONSTANTS_TIER_PARTS
        for index in range(len(parts) - window + 1)
    )


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


def _is_environ(node: ast.expr) -> bool:
    """Return whether ``node`` is ``os.environ`` or a bare imported ``environ``."""
    if isinstance(node, ast.Attribute):
        return node.attr == _ENVIRON_ATTRIBUTE
    return isinstance(node, ast.Name) and node.id == _ENVIRON_ATTRIBUTE


def _string_literal(node: ast.expr | None) -> tuple[ast.Constant, str] | None:
    """Return ``node`` and its narrowed value when it is a string constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node, node.value
    return None


def _environment_lookup_literal(node: ast.AST) -> tuple[ast.Constant, str] | None:
    """Return the literal key of an environment lookup, if ``node`` is one."""
    if isinstance(node, ast.Subscript) and _is_environ(node.value):
        return _string_literal(node.slice)

    if not isinstance(node, ast.Call) or not node.args:
        return None

    function = node.func

    # os.getenv("NAME") and a bare getenv("NAME")
    if isinstance(function, ast.Attribute) and function.attr in _GETENV_FUNCTIONS:
        return _string_literal(node.args[0])
    if isinstance(function, ast.Name) and function.id in _GETENV_FUNCTIONS:
        return _string_literal(node.args[0])

    # os.environ.get("NAME") and a bare environ.get("NAME")
    if (
        isinstance(function, ast.Attribute)
        and function.attr == "get"
        and _is_environ(function.value)
    ):
        return _string_literal(node.args[0])

    return None


def looks_like_env_name(value: str) -> bool:
    """Return whether ``value`` is shaped like an environment-variable name."""
    if not ENV_NAME_PATTERN.match(value):
        return False
    if value.startswith(NINJASRE_ENV_PREFIX):
        return True
    return value.startswith(VENDOR_ENV_PREFIXES)


def module_violations(path: Path, source: str) -> list[Violation]:
    """Return every violation in one module's source."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"{path}: could not be parsed: {error}") from error

    violations: list[Violation] = []
    reported: set[int] = set()

    for node in ast.walk(tree):
        found = _environment_lookup_literal(node)
        if found is None:
            continue
        literal, name = found
        if id(literal) not in reported:
            reported.add(id(literal))
            violations.append(Violation(path, literal.lineno, name, ENV_LOOKUP_RULE))

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in reported
            and looks_like_env_name(node.value)
        ):
            reported.add(id(node))
            violations.append(Violation(path, node.lineno, node.value, ENV_NAME_RULE))

    return violations


def find_violations(roots: Iterable[Path]) -> list[Violation]:
    """Return every violation under ``roots``, sorted for a stable report."""
    violations: list[Violation] = []

    for root in roots:
        for path in python_files(Path(root)):
            if is_exempt(path):
                continue
            violations.extend(module_violations(path, path.read_text(encoding="utf-8")))

    return sorted(violations)


def main(argv: Sequence[str] | None = None) -> int:
    """Scan ``argv`` paths, or the default roots, and report what was found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to scan (default: the first-party packages and tools/)",
    )
    arguments = parser.parse_args(argv)

    roots = tuple(arguments.paths) or DEFAULT_SCAN_ROOTS
    violations = find_violations(roots)

    if not violations:
        return 0

    print(
        f"{len(violations)} environment-variable name(s) outside "
        f"{'/'.join(CONSTANTS_TIER_PARTS)}/:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nDeclare the name in its domain module under config/constants/ and "
        "import the constant instead (FR-009, FR-010).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
