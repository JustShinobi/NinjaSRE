"""Fail the build on a forgotten comma inside a capability's prose metadata.

Python concatenates adjacent string literals. Inside a list of use cases, that
turns::

    use_cases=[
        "find the failing endpoint"
        "list recent deploys",
    ]

into a single entry reading "find the failing endpointlist recent deploys" —
valid, silent, and one signal short. Selection scores on these entries, so the
capability stops matching the incident it was written for and nothing reports
it. The list is still a list; it is just wrong.

The rule is deliberately narrow. Implicit concatenation is the idiomatic way to
write a long string in Python, and FR-020's remedy for long prose is to move it
into a module constant — so only *entries of a metadata collection* are
checked, and a constant holding one concatenated sentence stays legal.

Usage::

    python tools/check_metadata_literals.py [path ...]

Exits 0 when clean, 1 when a violation is found.
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
import token as token_module
import tokenize
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The declaration fields whose entries are prose the scorer reads. Names are
#: matched both as keyword arguments and as assigned module or class constants,
#: because a capability may inline the list or point at one.
METADATA_FIELDS = frozenset(
    {
        "use_cases",
        "anti_examples",
        "examples",
        "tags",
        "applies_when",
        "alert_sources",
        "directs_tools",
    }
)

DEFAULT_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "core",
    REPO_ROOT / "integrations",
)

SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".venv", ".git", "_research", "node_modules"})

#: Tokens that may appear between two string tokens without breaking a run of
#: implicit concatenation. Inside brackets a newline is `NL`, not `NEWLINE`.
_IGNORED_BETWEEN_STRINGS = frozenset(
    {token_module.NL, token_module.COMMENT, token_module.INDENT, token_module.DEDENT}
)

_STRING_TOKENS = frozenset({token_module.STRING, token_module.FSTRING_START})


@dataclass(frozen=True, order=True)
class Violation:
    """One metadata collection whose entries were merged by a missing comma."""

    path: Path
    line: int
    column: int
    field: str

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.column}: implicit string concatenation in "
            f"{self.field} — a missing comma merges two entries into one"
        )


@dataclass(frozen=True)
class _Region:
    """The source span of one metadata collection literal."""

    field: str
    start: tuple[int, int]
    end: tuple[int, int]

    def contains(self, position: tuple[int, int]) -> bool:
        """Return whether ``position`` falls inside this literal."""
        return self.start <= position < self.end


def _collection_region(field: str, node: ast.expr) -> _Region | None:
    """Return the span of ``node`` when it is a list or tuple literal."""
    if not isinstance(node, ast.List | ast.Tuple | ast.Set):
        return None
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    return _Region(
        field=field,
        start=(node.lineno, node.col_offset),
        end=(node.end_lineno, node.end_col_offset),
    )


def metadata_regions(tree: ast.AST) -> list[_Region]:
    """Return the span of every metadata collection literal in ``tree``."""
    regions: list[_Region] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in METADATA_FIELDS:
                    region = _collection_region(keyword.arg, keyword.value)
                    if region is not None:
                        regions.append(region)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.lower() in METADATA_FIELDS:
                    region = _collection_region(target.id, node.value)
                    if region is not None:
                        regions.append(region)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id.lower() in METADATA_FIELDS:
                region = _collection_region(target.id, node.value) if node.value else None
                if region is not None:
                    regions.append(region)

    return regions


def concatenation_positions(source: str) -> list[tuple[int, int]]:
    """Return the position of every second-and-later token in a concatenated run.

    The AST cannot answer this: adjacent literals are folded into one
    ``Constant`` before anything downstream can see there were two. Only the
    token stream still knows.
    """
    positions: list[tuple[int, int]] = []
    previous_was_string = False

    for produced in tokenize.generate_tokens(io.StringIO(source).readline):
        if produced.type in _IGNORED_BETWEEN_STRINGS:
            continue
        if produced.type in _STRING_TOKENS:
            if previous_was_string:
                positions.append(produced.start)
            previous_was_string = True
            continue
        if produced.type == token_module.FSTRING_END:
            continue
        previous_was_string = False

    return positions


def module_violations(path: Path, source: str) -> list[Violation]:
    """Return every merged-entry violation in one module's source."""
    try:
        tree = ast.parse(source, filename=str(path))
        positions = concatenation_positions(source)
    except (SyntaxError, tokenize.TokenError) as error:
        raise ValueError(f"{path}: could not be parsed: {error}") from error

    if not positions:
        return []

    regions = metadata_regions(tree)
    violations = [
        Violation(path=path, line=position[0], column=position[1], field=region.field)
        for position in positions
        for region in regions
        if region.contains(position)
    ]
    return sorted(set(violations))


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


def find_violations(roots: Iterable[Path] | None) -> list[Violation]:
    """Return every violation under ``roots``, or under the default roots."""
    violations: list[Violation] = []

    for root in roots if roots is not None else DEFAULT_SCAN_ROOTS:
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
        help="files or directories to scan (default: the capability packages)",
    )
    arguments = parser.parse_args(argv)

    violations = find_violations(tuple(arguments.paths) or None)

    if not violations:
        return 0

    print(f"{len(violations)} metadata collection(s) with a merged entry:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nAdjacent string literals concatenate. Add the missing comma, or move "
        "the long string into a module constant and reference it (FR-020).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
