"""Fail the build on code that reaches for a credential instead of a handle.

FR-017 and Constitution Article IV. The invariant is that no credential reaches
the agent, and the ways it decays are all cheap to write and invisible in
review. Four rules, in ascending order of how much each actually holds the line.

``credential-env-name``
    A credential-shaped environment-variable name written anywhere outside
    ``config/constants/`` and ``platform/``. Pattern matching over *suffixes* —
    ``_API_KEY``, ``_TOKEN``, ``_SECRET`` — rather than vendor prefixes, because
    the vendor list is never complete and the suffix is what distinguishes a
    secret from a setting.

``credential-env-lookup``
    Any read of the process environment from ``integrations/`` or
    ``capabilities/``. Not only credential-shaped ones: a vendor client and an
    agent-callable tool have no business reading the environment at all. Their
    configuration comes from the hierarchy and their credentials from the proxy,
    so a lookup here is either a credential or a setting in the wrong place. This
    catches the computed key that the name rule cannot see.

``credential-store-import``
    Importing ``CredentialStore`` or ``SecretValue`` outside
    ``platform/credentials/`` and ``platform/persistence/``. This is the rule
    that does the work: a module that cannot name the store cannot read one
    however it phrases the call, which is the same reasoning
    ``check_raw_sql.py`` uses for driver imports.

``credential-reveal``
    A ``reveal`` call outside ``platform/credentials/proxy/``.
    ``CredentialStore.reveal`` is the single method in NinjaSRE that returns
    plaintext, and the whole of Article IV rests on the proxy being its only
    caller.

**What is deliberately not flagged.** A capability legitimately needs a region,
a site, a namespace, a cluster name. ``AWS_REGION`` and ``DATADOG_SITE`` are
configuration, and flagging them would train contributors to reach for
``# noqa``, which is how a check stops catching what it was written for.

**What is exempt, and why.** ``platform/persistence/`` implements the store, so
it names the types and calls ``reveal`` — that is what an implementation is.
``tests/contract/persistence/`` is the contract suite *for* that port, and a
suite that could not exercise ``reveal`` would not be testing it. ``core/llm/``
resolves provider credentials through its own ``CredentialResolver`` port rather
than reading them directly, which is the indirection that lets the vault be
substituted for the environment-backed reference without touching an adapter.

Usage::

    python tools/check_direct_credentials.py [path ...]

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

ENV_LOOKUP_RULE = "credential-env-lookup"
CREDENTIAL_ENV_NAME_RULE = "credential-env-name"
CREDENTIAL_REVEAL_RULE = "credential-reveal"
CREDENTIAL_STORE_RULE = "credential-store-import"

#: The path that may call ``reveal``, identified by consecutive parts so the
#: check works from any checkout root. Moving the resolver moves the permission,
#: which is the intended behaviour: the exemption belongs to the trust boundary,
#: not to a file name.
PROXY_TIER_PARTS = ("platform", "credentials", "proxy")

#: The package that may name a ``CredentialStore``. Wider than the proxy path
#: because the vault writes credentials and the health check lists them, and
#: neither reads one.
CREDENTIALS_PACKAGE_PARTS = ("platform", "credentials")

#: Where the store is *implemented* — the port, the fakes, and the Postgres
#: repository all name the types and call ``reveal``, because that is what an
#: implementation of it is. Scanning them would report the storage layer for
#: being the storage layer.
PERSISTENCE_PACKAGE_PARTS = ("platform", "persistence")

#: The contract suite for the store, which has to exercise ``reveal`` to prove
#: the port works. Narrow on purpose: it is one directory, and widening it is an
#: edit somebody has to justify.
PERSISTENCE_CONTRACT_PARTS = ("tests", "contract", "persistence")

#: The tier that owns environment-variable names.
CONSTANTS_TIER_PARTS = ("config", "constants")

#: The trusted side of Article IV's boundary. ``platform/`` reads the operator's
#: vault key and the proxy's own configuration; the agent's tiers do not.
TRUSTED_ENV_ROOTS = ("platform",)

#: Where a process-environment read is forbidden outright. A vendor client and
#: an agent-callable tool take their configuration from the hierarchy and their
#: credentials from the proxy, so *any* environment lookup in these two is
#: something in the wrong place — which is what catches the computed key the
#: name rule cannot see.
NO_ENVIRONMENT_ROOTS = ("integrations", "capabilities")

#: The names that identify the credential store in an import.
CREDENTIAL_STORE_TYPES = frozenset({"CredentialStore", "SecretValue"})

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

#: A name ending in one of these is a credential. Suffixes rather than vendor
#: prefixes, because the vendor list is never complete and the suffix list is
#: what actually distinguishes a secret from a setting.
CREDENTIAL_SUFFIXES: tuple[str, ...] = (
    "_API_KEY",
    "_ACCESS_KEY",
    "_APP_KEY",
    "_APPLICATION_KEY",
    "_AUTH",
    "_CLIENT_SECRET",
    "_CREDENTIALS",
    "_LICENSE_KEY",
    "_PASSWORD",
    "_PRIVATE_KEY",
    "_SECRET",
    "_SECRET_ACCESS_KEY",
    "_SECRET_KEY",
    "_SIGNING_SECRET",
    "_TOKEN",
    "_WEBHOOK_URL",
)

#: Names that are credentials and carry no underscore at all, so the suffix
#: rules cannot see them. One entry, and the shortness is the point: a list that
#: grew would mean the suffixes were chosen badly.
#:
#: Everything else worth naming here — ``AWS_SECRET_ACCESS_KEY``,
#: ``GOOGLE_APPLICATION_CREDENTIALS``, ``AWS_SESSION_TOKEN`` — already ends in a
#: suffix above, and writing them out would also make this module fail
#: ``check_constants.py`` for cataloguing the names it exists to catch.
CREDENTIAL_EXACT_NAMES: frozenset[str] = frozenset({"KUBECONFIG"})

#: An environment-variable name is SCREAMING_SNAKE with at least one underscore.
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")

_ENVIRON_ATTRIBUTE = "environ"
_GETENV_FUNCTIONS = frozenset({"getenv"})
_REVEAL_METHOD = "reveal"


@dataclass(frozen=True, order=True)
class Violation:
    """One place a credential was reached for instead of a handle."""

    path: Path
    line: int
    name: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.name!r}"


def _within(path: Path, parts: tuple[str, ...]) -> bool:
    """Return whether ``path`` lies under the consecutive path ``parts``."""
    resolved = path.parts
    window = len(parts)
    return any(
        resolved[index : index + window] == parts for index in range(len(resolved) - window + 1)
    )


def may_reveal_secrets(path: Path) -> bool:
    """Return whether ``path`` may call ``reveal``.

    The proxy's resolver, because it is the trust boundary; the persistence
    layer, because it implements the method; and the persistence contract suite,
    because a suite that could not call it would not be testing the port.
    """
    return (
        _within(path, PROXY_TIER_PARTS)
        or _within(path, PERSISTENCE_PACKAGE_PARTS)
        or _within(path, PERSISTENCE_CONTRACT_PARTS)
    )


def may_hold_credential_store(path: Path) -> bool:
    """Return whether ``path`` may name a ``CredentialStore`` or a ``SecretValue``."""
    return (
        _within(path, CREDENTIALS_PACKAGE_PARTS)
        or _within(path, PERSISTENCE_PACKAGE_PARTS)
        or _within(path, PERSISTENCE_CONTRACT_PARTS)
    )


def may_read_environment(path: Path) -> bool:
    """Return whether ``path`` is on the trusted side of Article IV's boundary."""
    if _within(path, CONSTANTS_TIER_PARTS):
        return True
    return any(root in path.parts for root in TRUSTED_ENV_ROOTS)


def scans_environment(path: Path) -> bool:
    """Return whether the credential-name rule applies to ``path``.

    ``tests/`` and ``tools/`` are excluded. A test that sets a variable is doing
    its job, and repository tooling runs outside the agent process entirely.
    """
    return "tests" not in path.parts and "tools" not in path.parts


def forbids_environment_reads(path: Path) -> bool:
    """Return whether ``path`` may not touch the process environment at all.

    ``integrations/`` and ``capabilities/``: a vendor client takes its
    configuration from the hierarchy and its credential from the proxy, so an
    environment read there is one or the other in the wrong place.
    """
    return any(root in path.parts for root in NO_ENVIRONMENT_ROOTS)


def is_credential_name(name: str) -> bool:
    """Return whether ``name`` looks like an environment variable holding a secret."""
    if name in CREDENTIAL_EXACT_NAMES:
        return True
    if not ENV_NAME_PATTERN.fullmatch(name):
        return False
    return name.endswith(CREDENTIAL_SUFFIXES)


def python_files(root: Path) -> list[Path]:
    """Return the Python files under ``root``, skipping caches and vendored trees."""
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*.py") if not SKIPPED_DIRECTORY_NAMES.intersection(path.parts)
    )


def module_violations(path: Path, source: str) -> list[Violation]:
    """Return every violation in one module's source."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Not this check's business. ``ruff`` reports it, and reporting it twice
        # in two voices makes the real failure harder to find.
        return []

    found: list[Violation] = []
    check_names = scans_environment(path) and not may_read_environment(path)
    check_lookups = forbids_environment_reads(path)
    check_reveal = not may_reveal_secrets(path)
    check_store = not may_hold_credential_store(path)

    for node in ast.walk(tree):
        if check_names:
            found.extend(_credential_name_violations(path, node))
        if check_lookups:
            found.extend(_environment_lookup_violations(path, node))
        if check_reveal:
            found.extend(_reveal_violations(path, node))
        if check_store:
            found.extend(_store_import_violations(path, node))
    return sorted(set(found))


def _credential_name_violations(path: Path, node: ast.AST) -> Iterable[Violation]:
    """Yield credential-shaped environment-variable names written in one node."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and is_credential_name(node.value)
    ):
        yield Violation(path=path, line=node.lineno, name=node.value, rule=CREDENTIAL_ENV_NAME_RULE)


def _environment_lookup_violations(path: Path, node: ast.AST) -> Iterable[Violation]:
    """Yield reads of the process environment in one node."""
    if not isinstance(node, ast.Subscript | ast.Call):
        return
    name = _environment_lookup_name(node)
    if name is not None:
        yield Violation(path=path, line=node.lineno, name=name, rule=ENV_LOOKUP_RULE)


def _environment_lookup_name(node: ast.AST) -> str | None:
    """Return the variable an environment lookup names, or ``None``.

    Every lookup, not only credential-shaped ones — the rule is about the call,
    which is what catches the key built by concatenation.
    """
    if isinstance(node, ast.Subscript):
        return _subscript_lookup(node)
    if isinstance(node, ast.Call):
        return _call_lookup(node)
    return None


def _subscript_lookup(node: ast.Subscript) -> str | None:
    """Return the name in ``os.environ[...]`` or ``environ[...]``."""
    target = node.value
    is_environ = (isinstance(target, ast.Attribute) and target.attr == _ENVIRON_ATTRIBUTE) or (
        isinstance(target, ast.Name) and target.id == _ENVIRON_ATTRIBUTE
    )
    if not is_environ:
        return None
    key = node.slice
    return (
        key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else "<computed>"
    )


def _call_lookup(node: ast.Call) -> str | None:
    """Return the name in ``os.getenv(...)`` or ``os.environ.get(...)``."""
    function = node.func
    if isinstance(function, ast.Attribute):
        owner = function.value
        is_environ_get = function.attr == "get" and (
            (isinstance(owner, ast.Attribute) and owner.attr == _ENVIRON_ATTRIBUTE)
            or (isinstance(owner, ast.Name) and owner.id == _ENVIRON_ATTRIBUTE)
        )
        if function.attr in _GETENV_FUNCTIONS or is_environ_get:
            return _first_string_argument(node)
    elif isinstance(function, ast.Name) and function.id in _GETENV_FUNCTIONS:
        return _first_string_argument(node)
    return None


def _first_string_argument(node: ast.Call) -> str:
    """Return the first positional string argument, or a placeholder."""
    if node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return "<computed>"


def _reveal_violations(path: Path, node: ast.AST) -> Iterable[Violation]:
    """Yield ``reveal`` calls made outside the credential proxy."""
    if not isinstance(node, ast.Call):
        return
    function = node.func
    if isinstance(function, ast.Attribute) and function.attr == _REVEAL_METHOD:
        yield Violation(
            path=path,
            line=node.lineno,
            name=f"{ast.unparse(function)}()",
            rule=CREDENTIAL_REVEAL_RULE,
        )


def _store_import_violations(path: Path, node: ast.AST) -> Iterable[Violation]:
    """Yield imports of the credential store's types outside the packages that own them.

    An import rather than an attribute access, for the same reason
    ``check_raw_sql.py`` watches driver imports: a module that cannot name the
    type cannot use one however it phrases the call, and matching on an
    attribute called ``credentials`` would flag every unrelated object that has
    one.
    """
    if not isinstance(node, ast.ImportFrom):
        return
    for alias in node.names:
        if alias.name in CREDENTIAL_STORE_TYPES:
            yield Violation(
                path=path,
                line=node.lineno,
                name=alias.name,
                rule=CREDENTIAL_STORE_RULE,
            )


def find_violations(roots: Sequence[Path] | None = None) -> list[Violation]:
    """Return every violation under ``roots``, defaulting to the whole repository."""
    scanned = tuple(roots) if roots else DEFAULT_SCAN_ROOTS
    found: list[Violation] = []
    for root in scanned:
        for path in python_files(root):
            found.extend(module_violations(path, path.read_text(encoding="utf-8")))
    return sorted(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check and return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to scan; defaults to the first-party packages",
    )
    arguments = parser.parse_args(argv)

    violations = find_violations(arguments.paths or None)
    if not violations:
        return 0

    print(
        f"{len(violations)} credential-boundary violation(s). Article IV says no "
        f"credential reaches the agent: integrations carry a handle and the proxy "
        f"injects the secret at the network edge.",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
