"""Fail the build if a vendor LLM SDK is imported outside ``core/llm/``.

Provider neutrality is not a preference, it is the property that makes a
deployment with no permitted egress a real deployment. It survives exactly as
long as there is one place that knows what a vendor's client looks like. The
first ``import anthropic`` in a pipeline stage does not break anything that day;
it breaks the operator who wanted to run on a local model, six months later,
with no obvious culprit.

So the rule is mechanical: the vendor SDKs are importable from ``core/llm/`` and
nowhere else. ``tests/`` is scanned too — a test that reaches for a vendor SDK
is a test that cannot run in a no-egress CI, and it would take the suite with it.

Two forms are caught, and the second is the one that would otherwise slip
through:

``vendor-import``
    ``import anthropic`` / ``from openai import ...`` outside the allowed tree.

``vendor-dynamic-import``
    ``importlib.import_module("anthropic")`` and ``__import__("openai")``,
    which is how somebody works around the first rule without meaning to
    work around anything.

Usage::

    python tools/check_vendor_sdks.py [path ...]

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

VENDOR_IMPORT_RULE = "vendor-import"
VENDOR_DYNAMIC_IMPORT_RULE = "vendor-dynamic-import"

#: The one tree allowed to know what a vendor client looks like, identified by
#: consecutive path parts so the check works from any checkout root.
ALLOWED_TREE_PARTS = ("core", "llm")

#: Top-level distributions that talk to a model provider. Matching is on the
#: *root* module, so ``openai.types.chat`` is the same violation as ``openai``.
VENDOR_MODULES: frozenset[str] = frozenset(
    {
        "anthropic",
        "boto3",
        "botocore",
        "cohere",
        "google",
        "google_genai",
        "groq",
        "litellm",
        "mistralai",
        "ollama",
        "openai",
        "together",
        "vertexai",
    }
)

#: Roots scanned when none are given: the seven first-party packages, repository
#: tooling, and the test suite.
DEFAULT_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "core",
    REPO_ROOT / "gateway",
    REPO_ROOT / "integrations",
    REPO_ROOT / "platform",
    REPO_ROOT / "surfaces",
    REPO_ROOT / "tests",
    REPO_ROOT / "tools",
)

SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".venv", ".git", "_research", "node_modules"})

_DYNAMIC_IMPORT_FUNCTIONS = frozenset({"import_module", "__import__"})


@dataclass(frozen=True, order=True)
class Violation:
    """One vendor SDK imported where it does not belong."""

    path: Path
    line: int
    module: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.module!r}"


def is_allowed(path: Path) -> bool:
    """Return whether ``path`` sits in the tree that owns provider integration."""
    parts = path.parts
    window = len(ALLOWED_TREE_PARTS)
    return any(
        parts[index : index + window] == ALLOWED_TREE_PARTS
        for index in range(len(parts) - window + 1)
    )


def root_module(name: str) -> str:
    """Return the top-level distribution ``name`` belongs to."""
    return name.split(".", 1)[0]


def is_vendor(name: str) -> bool:
    """Return whether ``name`` names a vendor SDK."""
    return root_module(name) in VENDOR_MODULES


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


def _dynamic_import_literal(node: ast.AST) -> tuple[int, str] | None:
    """Return the module name a dynamic import names, if ``node`` is one."""
    if not isinstance(node, ast.Call) or not node.args:
        return None

    function = node.func
    called = ""
    if isinstance(function, ast.Attribute):
        called = function.attr
    elif isinstance(function, ast.Name):
        called = function.id
    if called not in _DYNAMIC_IMPORT_FUNCTIONS:
        return None

    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.lineno, first.value
    return None


def module_violations(path: Path, source: str) -> list[Violation]:
    """Return every violation in one module's source."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"{path}: could not be parsed: {error}") from error

    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_vendor(alias.name):
                    violations.append(Violation(path, node.lineno, alias.name, VENDOR_IMPORT_RULE))
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module of its own to check.
            if node.level == 0 and node.module and is_vendor(node.module):
                violations.append(Violation(path, node.lineno, node.module, VENDOR_IMPORT_RULE))
        else:
            found = _dynamic_import_literal(node)
            if found is not None:
                line, name = found
                if is_vendor(name):
                    violations.append(Violation(path, line, name, VENDOR_DYNAMIC_IMPORT_RULE))

    return violations


def find_violations(roots: Iterable[Path]) -> list[Violation]:
    """Return every violation under ``roots``, sorted for a stable report."""
    violations: list[Violation] = []

    for root in roots:
        for path in python_files(Path(root)):
            if is_allowed(path):
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
        help="files or directories to scan (default: the first-party packages, tests, and tools)",
    )
    arguments = parser.parse_args(argv)

    violations = find_violations(tuple(arguments.paths) or DEFAULT_SCAN_ROOTS)

    if not violations:
        return 0

    print(
        f"{len(violations)} vendor SDK import(s) outside {'/'.join(ALLOWED_TREE_PARTS)}/:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nEvery model call goes through core.llm.get_llm(). A deployment where "
        "nothing leaves the operator's infrastructure has to stay fully "
        "functional, and it only does while one package knows what a vendor "
        "client looks like.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
