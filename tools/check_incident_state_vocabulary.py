"""Fail the build when the console's incident vocabulary and the store's
enumeration disagree.

The sibling of ``tools/check_run_status_vocabulary.py``, for the enumeration
that had no guard. ``platform.persistence.ports.incident_store.IncidentState``
is written verbatim into ``IncidentSummaryView.state``
(``gateway/http/routes/incidents.py::_row``, ``state=incident.state.value``),
which is what ``GET /v1/incidents`` returns, and the route's own filter
validation refuses by name any word outside it. So the enumeration is not one
opinion about incident states — it is the only one the wire carries.

Two rules, checked in both directions:

``console-missing``
    The console does not declare a state the gateway serves. It falls through
    to the neutral "unknown" rendering, so a resolved incident is drawn in the
    same grey as a word the console has never seen.

``console-excess``
    The console declares an incident state the gateway cannot serve. Every
    comparison against it is dead: the overview's ``state === 'closed'`` skip
    never fired, and a finished investigation was counted as one waiting on a
    person.

The enumeration is imported, not copied into a literal here, which would just
be another vocabulary for this check to drift from.

Usage::

    python -m tools.check_incident_state_vocabulary [--console-status-path PATH]

Exits 0 when clean, 1 when a violation is found.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from platform.persistence.ports.incident_store import IncidentState

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONSOLE_STATUS_PATH = REPO_ROOT / "console" / "src" / "design" / "status.ts"

_INCIDENT_STATES_PATTERN = re.compile(
    r"export const INCIDENT_STATES\s*=\s*\[(?P<body>.*?)\]\s*as const;", re.DOTALL
)
_ATTENTION_STATUSES_PATTERN = re.compile(
    r"export const ATTENTION_STATUSES\s*=\s*\[(?P<body>.*?)\]\s*as const;", re.DOTALL
)
_STRING_LITERAL_PATTERN = re.compile(r"'([^']*)'")


@dataclass(frozen=True, slots=True)
class Violation:
    """One disagreement, in the terms the fixer needs."""

    rule: str
    detail: str

    def render(self) -> str:
        """Return the one line this violation prints."""
        return f"{self.rule}: {self.detail}"


def _literals(text: str, pattern: re.Pattern[str], name: str, path: Path) -> tuple[str, ...]:
    """Return the string literals of one ``as const`` array in ``text``."""
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"{path}: could not find a `{name} = [...] as const;` declaration")
    return tuple(_STRING_LITERAL_PATTERN.findall(match.group("body")))


def console_vocabulary(path: Path) -> tuple[str, ...]:
    """Return the incident states ``console/src/design/status.ts`` declares.

    Parsed out of the ``INCIDENT_STATES`` array literal rather than imported —
    this is a Python tool reading TypeScript source — so a renamed or malformed
    declaration raises rather than yielding a silently empty vocabulary, which
    would make every enumeration member look missing.
    """
    return _literals(
        path.read_text(encoding="utf-8"), _INCIDENT_STATES_PATTERN, "INCIDENT_STATES", path
    )


def console_presentation(path: Path) -> tuple[str, ...]:
    """Return the words ``ATTENTION_STATUSES`` gives a role and a shape to."""
    return _literals(
        path.read_text(encoding="utf-8"), _ATTENTION_STATUSES_PATTERN, "ATTENTION_STATUSES", path
    )


def violations(declared: Sequence[str], presented: Sequence[str] = ()) -> tuple[Violation, ...]:
    """Return every disagreement between the console's vocabulary and the enumeration.

    ``declared`` is the closed set (``INCIDENT_STATES``) and is held exactly:
    it is this enumeration and nothing else, so both directions are equality
    rather than a guess about which words look like a state. ``presented`` is
    the shared presentation vocabulary, which legitimately also carries
    severities and decision outcomes — it is only checked for *omission*, so a
    real state cannot end up drawn as an unknown word.
    """
    served = {state.value for state in IncidentState}
    present = set(declared)
    found: list[Violation] = []
    for missing in sorted(served - present):
        found.append(
            Violation(
                rule="console-missing",
                detail=(
                    f"does not declare {missing!r} in INCIDENT_STATES, which the gateway "
                    "serves verbatim from IncidentState"
                ),
            )
        )
    for excess in sorted(present - served):
        found.append(
            Violation(
                rule="console-excess",
                detail=(
                    f"declares {excess!r} in INCIDENT_STATES, which IncidentState does not "
                    "contain, so the gateway can never serve it"
                ),
            )
        )
    undrawn = sorted(served - set(presented)) if presented else []
    for missing in undrawn:
        found.append(
            Violation(
                rule="console-undrawn",
                detail=(
                    f"gives {missing!r} no role or shape in ATTENTION_STATUSES, so a real "
                    "incident is drawn as a status the console has never heard of"
                ),
            )
        )
    return tuple(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Check the vocabulary and report, returning the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--console-status-path",
        type=Path,
        default=DEFAULT_CONSOLE_STATUS_PATH,
        help="the console's status module",
    )
    args = parser.parse_args(argv)

    found = violations(
        console_vocabulary(args.console_status_path),
        console_presentation(args.console_status_path),
    )
    if not found:
        print(f"incident-state vocabulary: {len(IncidentState)} states, console agrees")
        return 0
    for violation in found:
        print(violation.render(), file=sys.stderr)
    print(
        f"\n{len(found)} violation(s). Bring console/src/design/status.ts::INCIDENT_STATES "
        "in line with platform.persistence.ports.incident_store.IncidentState.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
