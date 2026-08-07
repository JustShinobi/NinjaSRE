"""Fail the build on SQL or Cypher written outside ``platform/persistence/``.

FR-003 and Constitution Article XI: one datastore, reached through repository
ports, and nothing above tier 3 knows it is PostgreSQL. That rule is worth
stating because it is the one that decays quietly — a pipeline stage that needs
one more field is three lines away from a ``SELECT`` that works perfectly, and
by the time anybody notices, the ports are no longer where storage lives.

Three rules, in ascending order of how much they actually hold the line.

``sql-literal`` and ``cypher-literal``
    A string literal that parses as a statement. Pattern matching, so it is
    neither complete nor the point — it catches the obvious case and reads well
    in a failure message. Docstrings are exempt: this module's own prose
    contains more SQL keywords than most queries.

``query-execution``
    A call to ``execute``, ``executemany``, ``fetchrow``, and friends. Catches
    the query built by concatenation, which is invisible to the literal rules
    and is also the one with an injection hazard attached.

``database-driver-import``
    An import of SQLAlchemy, asyncpg, psycopg, Alembic, or pgvector. This is the
    rule that does the work: a module that cannot import a driver cannot issue a
    query however it phrases one, and the ``importlib`` way round is covered
    too, for the same reason ``check_vendor_sdks.py`` covers it — a contributor
    reaching for it is solving a problem, not evading a rule, and the boundary
    is gone either way.

``tests/`` and ``integrations/`` are scanned for the last two rules but not for
the literal ones. A test whose fixture is a query-shaped string is doing its
job — ``test_redaction.py`` proves a leaked ``SELECT`` gets redacted, and it
needs a ``SELECT`` to do it. A vendor client whose API *is* SQL is doing its job
too: ClickHouse and Snowflake take a statement as the body of an HTTP request,
which is their request grammar rather than access to this system's storage.

A module in either tree that *imports a driver* or *calls execute* is reaching
behind the ports, is asserting something they do not promise, and will keep
passing after they stop promising it. That still fails.

Usage::

    python tools/check_raw_sql.py [path ...]

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

SQL_LITERAL_RULE = "sql-literal"
CYPHER_LITERAL_RULE = "cypher-literal"
QUERY_EXECUTION_RULE = "query-execution"
DRIVER_IMPORT_RULE = "database-driver-import"

#: The tree that owns storage, identified by these consecutive path parts so the
#: check works on any checkout root.
ALLOWED_TREE_PARTS = ("platform", "persistence")

#: Path part marking the test suite, where the literal rules do not apply.
TEST_TREE_PART = "tests"

#: Path part marking the vendor tree, where the literal rules do not apply
#: either. A handful of catalogued vendors take SQL as their request payload
#: over HTTP; see ``scans_literals`` for why that is a different thing from
#: reaching this repository's own datastore, and for what still applies there.
VENDOR_QUERY_TREE_PART = "integrations"

#: The one test tree that is *about* storage. Its whole job is to drive the
#: repositories against a real PostgreSQL, which means creating databases,
#: seeding a hundred thousand vectors, and reading back what the backend wrote.
#: A suite that had to go through the ports to check the ports could not check
#: much. Everywhere else in ``tests/`` the boundary holds.
ALLOWED_TEST_TREE_PARTS = ("tests", "contract", "persistence")

#: Roots scanned when none are given: the seven first-party packages plus the
#: test suite. Root ``tools/`` is excluded because this file lives there and is
#: made entirely of SQL keywords.
DEFAULT_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "core",
    REPO_ROOT / "gateway",
    REPO_ROOT / "integrations",
    REPO_ROOT / "platform",
    REPO_ROOT / "surfaces",
    REPO_ROOT / "tests",
)

SKIPPED_DIRECTORY_NAMES = frozenset({"__pycache__", ".venv", ".git", "_research", "node_modules"})

#: Distributions that speak to a database. Importing one is how a module comes
#: to be able to issue a query at all.
DRIVER_MODULES = frozenset(
    {
        "alembic",
        "asyncpg",
        "pgvector",
        "psycopg",
        "psycopg2",
        "sqlalchemy",
        "sqlite3",
    }
)

#: Methods that run a statement. Deliberately not ``fetch`` alone — it is a word
#: with too many other jobs, and the driver-import rule catches its callers.
EXECUTION_METHODS = frozenset(
    {
        "execute",
        "executemany",
        "executescript",
        "execute_many",
        "fetchrow",
        "fetchval",
    }
)

_DYNAMIC_IMPORT_FUNCTIONS = frozenset({"import_module", "__import__"})

#: Receivers whose ``execute`` is not a database's.
#:
#: ``execute`` is a word several boundaries in this repository want. A cursor
#: executes a statement; a ``Sandbox`` executes a capability's command and a
#: ``JobExecutor`` executes a scheduled firing, and that verb is part of both
#: their ports. Exempting the *receiver* rather than the method keeps the rule
#: intact everywhere else — ``connection.execute`` and ``session.execute`` still
#: fail, and so does a bare ``execute(...)``.
#:
#: Named receivers rather than a pattern, deliberately. A regular expression
#: over variable names would eventually exempt something nobody intended, and
#: this list is meant to stay short enough to read in one glance.
NON_STORAGE_EXECUTE_RECEIVERS = frozenset({"sandbox", "executor"})

#: Prose ends in a full stop; a statement does not. This one guard is what
#: keeps "Select a provider from the registry." out of the report, and it costs
#: nothing real — nobody writes ``"SELECT 1 FROM t."``.
_SENTENCE_ENDING = re.compile(r"[.!?]$")

#: Every pattern is anchored at the start of the literal, because a string that
#: *is* a query starts with the verb, while a sentence that merely contains the
#: word does not. A statement genuinely buried inside prose goes unreported, and
#: that is the accepted cost of a heuristic whose job is readability — the
#: driver-import rule is what actually holds the boundary.
SQL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^SELECT\b[\s\S]+?\bFROM\b", re.IGNORECASE),
    re.compile(r"^WITH\b[\s\S]+?\bAS\s*\(", re.IGNORECASE),
    re.compile(r"^INSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"^UPDATE\b[\s\S]+?\bSET\b", re.IGNORECASE),
    re.compile(r"^DELETE\s+FROM\b", re.IGNORECASE),
    re.compile(
        r"^CREATE\s+(?:OR\s+REPLACE\s+|UNIQUE\s+)?"
        r"(?:TABLE|INDEX|SCHEMA|EXTENSION|VIEW|FUNCTION|TRIGGER)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^ALTER\s+(?:TABLE|INDEX|SCHEMA)\b", re.IGNORECASE),
    re.compile(r"^DROP\s+(?:TABLE|INDEX|SCHEMA|EXTENSION|VIEW)\b", re.IGNORECASE),
    re.compile(r"^TRUNCATE\s+TABLE\b", re.IGNORECASE),
)

CYPHER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^OPTIONAL\s+MATCH\b", re.IGNORECASE),
    re.compile(r"^MATCH\s*\(", re.IGNORECASE),
    re.compile(r"^MERGE\s*\(", re.IGNORECASE),
    re.compile(r"^DETACH\s+DELETE\b", re.IGNORECASE),
)


@dataclass(frozen=True, order=True)
class Violation:
    """One query, or the means to run one, outside the storage tree."""

    path: Path
    line: int
    detail: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def _contains(parts: tuple[str, ...], window: tuple[str, ...]) -> bool:
    """Return whether ``window`` appears as consecutive path parts."""
    size = len(window)
    return any(parts[index : index + size] == window for index in range(len(parts) - size + 1))


def is_allowed(path: Path) -> bool:
    """Return whether ``path`` sits in a tree permitted to know about storage."""
    parts = path.parts
    return _contains(parts, ALLOWED_TREE_PARTS) or _contains(parts, ALLOWED_TEST_TREE_PARTS)


def scans_literals(path: Path) -> bool:
    """Return whether the literal rules apply to ``path``.

    They do not apply in two trees, for the same reason in both.

    ``tests/`` is full of strings that look like queries precisely because
    something has to prove queries are handled correctly.

    ``integrations/`` holds vendors whose *API* is SQL. ClickHouse, Snowflake,
    and OpenObserve take a statement as the request payload of an HTTP call;
    the statement is the vendor's request grammar, the way a LogQL selector or
    a JQL expression is elsewhere in that tree, and there is no repository port
    to bypass because the data is not this system's.

    The exemption is narrow on purpose: it is the *literal* heuristic that stops
    applying. The driver-import and execution rules — the two the module
    docstring calls the ones that hold the line — still apply in both trees, so
    a module under ``integrations/`` still cannot import ``asyncpg`` or call
    ``execute``, and a client that reached this repository's own datastore would
    fail here exactly as it does anywhere else.
    """
    return TEST_TREE_PART not in path.parts and VENDOR_QUERY_TREE_PART not in path.parts


def root_module(name: str) -> str:
    """Return the top-level distribution ``name`` belongs to."""
    return name.split(".", 1)[0]


def is_driver(name: str) -> bool:
    """Return whether ``name`` names a database driver or migration tool."""
    return root_module(name) in DRIVER_MODULES


def classify(text: str) -> str | None:
    """Return the rule a string literal breaks, or ``None`` if it is innocent."""
    statement = text.strip().rstrip(";").strip()
    if not statement or _SENTENCE_ENDING.search(statement):
        return None
    if any(pattern.search(statement) for pattern in SQL_PATTERNS):
        return SQL_LITERAL_RULE
    if any(pattern.search(statement) for pattern in CYPHER_PATTERNS):
        return CYPHER_LITERAL_RULE
    return None


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


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Return the ``id()`` of every string constant that is a docstring.

    Documentation about storage is not storage. Exempting docstrings is what
    lets a port explain what it forbids in the same file that forbids it.
    """
    holders: list[ast.AST] = [tree]
    holders.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    )

    found: set[int] = set()
    for holder in holders:
        body = getattr(holder, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def _called_name(node: ast.Call) -> str:
    """Return the trailing identifier of whatever ``node`` calls."""
    function = node.func
    if isinstance(function, ast.Attribute):
        return function.attr
    if isinstance(function, ast.Name):
        return function.id
    return ""


def _receiver_name(node: ast.Call) -> str:
    """Return the identifier a method was called on, or the empty string.

    ``sandbox.execute(...)`` gives ``sandbox`` and ``self._sandbox.execute(...)``
    gives ``_sandbox``. A bare ``execute(...)`` gives nothing, which is what
    stops an unqualified call being exempted by accident.
    """
    function = node.func
    if not isinstance(function, ast.Attribute):
        return ""
    receiver = function.value
    if isinstance(receiver, ast.Name):
        return receiver.id
    if isinstance(receiver, ast.Attribute):
        return receiver.attr
    return ""


def _dynamic_import_literal(node: ast.Call) -> tuple[int, str] | None:
    """Return the module name a dynamic import names, if ``node`` is one."""
    if not node.args or _called_name(node) not in _DYNAMIC_IMPORT_FUNCTIONS:
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

    docstrings = _docstring_nodes(tree)
    literals_apply = scans_literals(path)
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            violations.extend(
                Violation(path, node.lineno, alias.name, DRIVER_IMPORT_RULE)
                for alias in node.names
                if is_driver(alias.name)
            )
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module of its own to check.
            if node.level == 0 and node.module and is_driver(node.module):
                violations.append(Violation(path, node.lineno, node.module, DRIVER_IMPORT_RULE))
        elif isinstance(node, ast.Constant):
            if literals_apply and isinstance(node.value, str) and id(node) not in docstrings:
                rule = classify(node.value)
                if rule is not None:
                    violations.append(Violation(path, node.lineno, _excerpt(node.value), rule))
        elif isinstance(node, ast.Call):
            dynamic = _dynamic_import_literal(node)
            if dynamic is not None and is_driver(dynamic[1]):
                violations.append(Violation(path, dynamic[0], dynamic[1], DRIVER_IMPORT_RULE))
            elif (
                _called_name(node) in EXECUTION_METHODS
                and _receiver_name(node) not in NON_STORAGE_EXECUTE_RECEIVERS
            ):
                violations.append(
                    Violation(path, node.lineno, f"{_called_name(node)}(…)", QUERY_EXECUTION_RULE)
                )

    return violations


def _excerpt(text: str, limit: int = 60) -> str:
    """Return a one-line excerpt of a literal, for the failure message."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"


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
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to scan (default: the first-party packages and tests)",
    )
    arguments = parser.parse_args(argv)

    violations = find_violations(tuple(arguments.paths) or DEFAULT_SCAN_ROOTS)

    if not violations:
        return 0

    print(
        f"{len(violations)} query or driver import outside {'/'.join(ALLOWED_TREE_PARTS)}/:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nStorage is reached through the repository ports in "
        "platform.persistence.ports. One datastore behind one boundary is what "
        "lets an operator back up, upgrade, and monitor a single thing — and it "
        "stops being true the first time a query is written somewhere else.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
