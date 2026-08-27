"""Fail the build when a run status a fixture serves, or the console declares,
is not a member of the persistence store's own enumeration.

There are three vocabularies for one fact in this repository, and only one of
them is the one the gateway actually serves: ``platform.persistence.ports.
run_trace_store.RunStatus`` is written verbatim into ``InvestigationSummary.
status`` (``gateway/http/routes/investigations.py::summary_of``), which is
what both ``GET /v1/runs`` and ``GET /v1/runs/{run_id}`` return. Neither the
runtime's own status (``core.agent.runtime_port.RunStatus`` — how one loop
iteration ended) nor a spelling a fixture happened to be written with is that
enumeration, and this check exists because both have been mistaken for it.

Two rules, checked in both directions, because a mismatch in either direction
is a real defect and not just an inconsistency:

``fixture-value``
    A committed fixture serves a run status outside the domain enumeration.
    The suite that reads this fixture is testing an invention, not the
    product — a run this shape never comes out of the gateway.

``console-excess`` / ``console-missing``
    The console's own closed vocabulary (``console/src/design/status.ts::
    RUN_STATUSES``) declares a word the gateway never serves, or fails to
    declare one it does. The first draws a screen nobody will ever see; the
    second sends a real run down the console's fallback rendering path.

The domain enumeration is read as data — imported, not copied into a literal
list here, which would just be a fourth vocabulary for the check itself to
drift from.

Usage::

    python -m tools.check_run_status_vocabulary [--fixtures-root PATH]
        [--console-status-path PATH]

Exits 0 when clean, 1 when a violation is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two mockplane endpoint slugs whose body carries a run's own ``status``
#: field — confirmed against ``gateway/http/routes/runs.py`` and ``gateway/
#: http/routes/investigations.py::summary_of``, which writes
#: ``status=run.status.value`` with no translation in between. Every fixture
#: file is named ``<slug>.json``, so the filename stem is the slug.
RUN_LIST_SLUG = "runs"
RUN_DETAIL_SLUG = "run-detail"
RUN_STATUS_SLUGS = frozenset({RUN_LIST_SLUG, RUN_DETAIL_SLUG})

DEFAULT_FIXTURES_ROOT = REPO_ROOT / "fixtures" / "scenarios"
DEFAULT_CONSOLE_STATUS_PATH = REPO_ROOT / "console" / "src" / "design" / "status.ts"

FIXTURE_VALUE_RULE = "fixture-value"
CONSOLE_EXCESS_RULE = "console-excess"
CONSOLE_MISSING_RULE = "console-missing"

_RUN_STATUSES_PATTERN = re.compile(
    r"export const RUN_STATUSES\s*=\s*\[(?P<body>.*?)\]\s*as const;", re.DOTALL
)
_STRING_LITERAL_PATTERN = re.compile(r"'([^']*)'")


@dataclass(frozen=True, order=True)
class Violation:
    """One run status word that is not where the domain enumeration says it should be."""

    location: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.location}: {self.rule}: {self.detail}"


def domain_values() -> tuple[str, ...]:
    """Return every value the persistence store's own ``RunStatus`` declares.

    Imported rather than duplicated: a fourth list, hand-kept in this file,
    is exactly the failure mode ``FR-061``/``FR-062`` exist to end one layer
    up. Run as a module (``python -m tools.check_run_status_vocabulary``) so
    that ``platform/`` wins its name over the standard-library module of the
    same name, the way every other check that imports a first-party package
    already has to.
    """
    from platform.persistence.ports.run_trace_store import RunStatus

    return tuple(status.value for status in RunStatus)


@dataclass(frozen=True)
class FixtureStatus:
    """One run status value one fixture file served, at one JSON path."""

    path: Path
    value: str


def _fixture_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        candidate for candidate in root.rglob("*.json") if candidate.stem in RUN_STATUS_SLUGS
    )


def fixture_statuses(root: Path) -> list[FixtureStatus]:
    """Return every run status every ``runs``/``run-detail`` fixture serves.

    A response whose body carries no ``status`` string — the 404 stub scenarios
    answer with, an empty run list — contributes nothing rather than raising:
    absence is not an invented value.
    """
    found: list[FixtureStatus] = []

    for path in _fixture_files(root):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}: not valid JSON: {error}") from error

        responses = document.get("responses") if isinstance(document, dict) else None
        if not isinstance(responses, list):
            continue

        for response in responses:
            if not isinstance(response, dict):
                continue
            body = response.get("body")
            if not isinstance(body, dict):
                continue

            if path.stem == RUN_LIST_SLUG:
                for run in body.get("runs", []):
                    if isinstance(run, dict) and isinstance(run.get("status"), str):
                        found.append(FixtureStatus(path=path, value=run["status"]))
            else:  # RUN_DETAIL_SLUG
                if isinstance(body.get("status"), str):
                    found.append(FixtureStatus(path=path, value=body["status"]))

    return found


def console_vocabulary(path: Path) -> tuple[str, ...]:
    """Return the run statuses ``console/src/design/status.ts`` declares.

    Parsed out of the ``RUN_STATUSES`` array literal rather than imported —
    this is a Python tool reading TypeScript source — so a malformed or
    renamed declaration is an error the check raises rather than a silent
    empty vocabulary that would make every fixture value look like an excess.
    """
    text = path.read_text(encoding="utf-8")
    match = _RUN_STATUSES_PATTERN.search(text)
    if match is None:
        raise ValueError(f"{path}: could not find a `RUN_STATUSES = [...] as const;` declaration")
    return tuple(_STRING_LITERAL_PATTERN.findall(match.group("body")))


def _display_path(path: Path) -> str:
    """Return ``path`` relative to the repository root, or as given outside it.

    Outside it is only a test's temporary directory — production callers
    always pass a path under ``REPO_ROOT``, and a report is more readable
    without the repository's own absolute prefix repeated on every line.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def find_violations(fixtures_root: Path, console_status_path: Path) -> list[Violation]:
    """Return every run status word that disagrees with the domain enumeration."""
    domain = frozenset(domain_values())
    violations: list[Violation] = []

    for entry in fixture_statuses(fixtures_root):
        if entry.value not in domain:
            violations.append(
                Violation(
                    location=_display_path(entry.path),
                    rule=FIXTURE_VALUE_RULE,
                    detail=f"serves run status {entry.value!r}, which is not in {sorted(domain)}",
                )
            )

    declared = frozenset(console_vocabulary(console_status_path))
    console_location = _display_path(console_status_path)

    for excess in sorted(declared - domain):
        violations.append(
            Violation(
                location=console_location,
                rule=CONSOLE_EXCESS_RULE,
                detail=f"declares {excess!r} in RUN_STATUSES, which the gateway never serves",
            )
        )

    for missing in sorted(domain - declared):
        violations.append(
            Violation(
                location=console_location,
                rule=CONSOLE_MISSING_RULE,
                detail=f"does not declare {missing!r} in RUN_STATUSES, which the gateway serves",
            )
        )

    return sorted(violations)


def main(argv: Sequence[str] | None = None) -> int:
    """Scan fixtures and the console vocabulary, and report what disagrees."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures-root", type=Path, default=DEFAULT_FIXTURES_ROOT)
    parser.add_argument("--console-status-path", type=Path, default=DEFAULT_CONSOLE_STATUS_PATH)
    arguments = parser.parse_args(argv)

    violations = find_violations(arguments.fixtures_root, arguments.console_status_path)

    if not violations:
        return 0

    print(f"{len(violations)} run status vocabulary violation(s):", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nA run status is a member of platform.persistence.ports.run_trace_store."
        "RunStatus, or it is not a run status this deployment ever produces. Migrate "
        "the fixture to the domain value the situation actually describes, or bring "
        "console/src/design/status.ts::RUN_STATUSES in line with the enumeration — "
        "never widen either to make this pass.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
