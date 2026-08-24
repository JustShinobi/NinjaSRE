"""Command line for the evidence collector.

Two verbs, and the separation is the point.

``plan``
    Print every question, fully substituted, and touch no database. This is how
    the SQL is read before it runs, and how it is pasted into a session
    somebody already has open.

``collect``
    Run the questions through a command given with ``--exec`` and write one
    file per station, each holding the query and the literal answer.

Usage::

    uv run python -m tools.demo_evidence plan --org <org> --run <run>

    uv run python -m tools.demo_evidence collect \\
        --org <org> --run <run> --incident <incident> \\
        --out <directory> \\
        --exec "ssh <host> kubectl exec -i -n <namespace> deploy/app -- \\
                sh -c 'psql -X -q -v ON_ERROR_STOP=1 \\"$<the url variable>\\"'"

``--exec`` is split into arguments with :mod:`shlex` and run directly; no shell
of this machine sees it. The statement travels on standard input, so it is not
visible in a process listing, and whatever resolves the connection string does
so at the far end. Nothing here holds one, and nothing here writes one down.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.demo_evidence.collector import (
    NotASelect,
    Parameters,
    ShellFreeRunner,
    UnusableParameter,
    collect,
    plan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parameters(arguments: argparse.Namespace) -> Parameters:
    """Return the parameters the command line describes."""
    return Parameters(
        org=arguments.org,
        run=arguments.run,
        incident=arguments.incident,
        approval=arguments.approval,
        resource=arguments.resource,
    )


def _add_parameters(parser: argparse.ArgumentParser) -> None:
    """Declare the identifiers every verb takes."""
    parser.add_argument("--org", required=True, help="the organisation every query is scoped to")
    parser.add_argument("--run", default="", help="the investigation being proved")
    parser.add_argument(
        "--incident", default="", help="the incident, by its short address or its internal id"
    )
    parser.add_argument("--approval", default="", help="the proposal that was decided")
    parser.add_argument("--resource", default="", help="the resource the action targeted")


def build_parser() -> argparse.ArgumentParser:
    """Return the parser for both verbs."""
    parser = argparse.ArgumentParser(prog="tools.demo_evidence", description=__doc__)
    verbs = parser.add_subparsers(dest="verb", required=True)

    printed = verbs.add_parser("plan", help="print the SQL without touching a database")
    _add_parameters(printed)

    gathered = verbs.add_parser("collect", help="run the SQL and write the literal answers")
    _add_parameters(gathered)
    gathered.add_argument(
        "--out",
        required=True,
        help="directory the per-station evidence files are written to",
    )
    gathered.add_argument(
        "--exec",
        dest="command",
        default="psql",
        help="the command that reads one statement on standard input and prints the answer",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one verb and return the exit code."""
    arguments = build_parser().parse_args(argv)
    try:
        parameters = _parameters(arguments)
        if arguments.verb == "plan":
            sys.stdout.write(plan(parameters=parameters))
            return 0

        destination = Path(arguments.out)
        if not destination.is_absolute():
            destination = REPO_ROOT / destination
        written = collect(
            parameters=parameters,
            runner=ShellFreeRunner.of_command(arguments.command),
            destination=destination,
        )
    except (NotASelect, UnusableParameter, ValueError) as refused:
        sys.stderr.write(f"{refused}\n")
        return 2

    for path in written:
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
