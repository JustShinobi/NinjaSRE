"""Ask the declared questions of a live database and write down what came back.

The unit of output is one file per station, holding the query **and the literal
answer**. Not a summary of the answer, not a count extracted from it, not a
sentence about it — the bytes the database returned, between two markers, so
that a reader who was not present can disagree with the conclusion and still
have the evidence.

Three refusals shape everything here.

**Anything that is not one ``SELECT`` is refused.** A tool that collects
evidence from a live staging database is one careless edit away from being a
tool that changes it, and the guard is at the point of execution rather than at
the point of declaration so a query assembled at runtime is caught too.

**Any parameter that could close a string literal is refused.** The values this
takes are identifiers — an organisation, a run, an incident address, an
approval, a resource — and none of them contains a quote, a space or a
semicolon. Refusing the rest is cheaper and stronger than quoting it.

**Nothing about how the database was reached is written down.** The runner is
opaque to the writer: it takes SQL and returns text. A connection string cannot
end up in a file that this module writes because this module never sees one.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from tools.demo_evidence.queries import STATIONS, VOCABULARY, Query, Station

#: What an identifier this tool substitutes into SQL may contain. Deliberately
#: narrow, and wide enough for the two shapes staging really writes: a short
#: opaque incident address, and the composed alert identifier that predates it
#: (``alert:alertmanager:<digest>@<timestamp>``), which carries colons, an at
#: sign and a plus.
IDENTIFIER: Final = re.compile(r"\A[A-Za-z0-9_./:@+-]*\Z")

#: A parameter reference in a template: one colon, not two, so a PostgreSQL
#: cast (``detail::text``) is never mistaken for something to substitute.
PLACEHOLDER: Final = re.compile(r"(?<!:):([a-z_]+)")

#: Line comments and block comments, stripped before a statement is judged.
_LINE_COMMENT: Final = re.compile(r"--[^\n]*")
_BLOCK_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)

#: A statement this tool will run. ``WITH`` is excluded on purpose: a common
#: table expression can carry ``DELETE ... RETURNING``, which reads like a
#: query and is not one.
_OPENS_A_READ: Final = re.compile(r"\Aselect\b", re.IGNORECASE)

OUTPUT_OPENS: Final = "--- output ---"
OUTPUT_CLOSES: Final = "--- end of output ---"
REFUSAL_OPENS: Final = "--- the collector could not run this query ---"
REFUSAL_CLOSES: Final = "--- end of failure ---"
NOT_COLLECTED: Final = "NOT COLLECTED"


class NotASelect(RuntimeError):
    """Raised when a statement would do something other than read."""


class UnusableParameter(ValueError):
    """Raised when a value could not be substituted into SQL safely."""


@dataclass(frozen=True, slots=True)
class Parameters:
    """What one collection is about: the tenant, and the things being proved.

    Only ``org`` is required. The rest are filled in as the loop produces them —
    a run identifier appears once the investigation has run, an approval once a
    proposal exists — and a query whose parameter is still empty is written down
    as not collected rather than run against a blank.
    """

    org: str
    run: str = ""
    incident: str = ""
    approval: str = ""
    resource: str = ""

    def __post_init__(self) -> None:
        """Refuse anything that could end the string literal it is placed in."""
        for name in ("org", "run", "incident", "approval", "resource"):
            value = getattr(self, name)
            if not IDENTIFIER.fullmatch(value):
                raise UnusableParameter(
                    f"--{name} is not an identifier: {value!r}. "
                    "Letters, digits and _ . / : @ + - only; anything that could "
                    "close a quote is refused rather than escaped."
                )
        if not self.org:
            raise UnusableParameter(
                "--org is required: every query is scoped to one organisation, and "
                "an unscoped count could be a neighbouring tenant's."
            )

    def get(self, name: str) -> str:
        """Return one parameter, or one declared word, by the name a statement uses.

        The deployment's own vocabulary — an audit resource kind, an approval
        state — resolves here too, from the modules that declare it. A statement
        therefore never spells a product word out, and renaming one breaks the
        query loudly instead of making it quietly return nothing.
        """
        if name in VOCABULARY:
            return VOCABULARY[name]
        try:
            return str(getattr(self, name))
        except AttributeError as unknown:
            raise UnusableParameter(
                f"no parameter is called {name!r}; the statement refers to one that "
                "does not exist, which is a typo rather than a missing value."
            ) from unknown

    def missing(self, needs: Iterable[str]) -> tuple[str, ...]:
        """Return which of ``needs`` has no value yet."""
        return tuple(name for name in needs if not self.get(name))

    def described(self) -> str:
        """Return the parameters as a line for the head of an evidence file."""
        return " ".join(
            f"{name}={getattr(self, name) or '(none)'}"
            for name in ("org", "run", "incident", "approval", "resource")
        )


def only_select(sql: str) -> str:
    """Return ``sql`` when it is one read, and raise naming it when it is not."""
    stripped = _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql)).strip()
    body = stripped.rstrip(";").strip()
    if not body:
        raise NotASelect("an empty statement is not a query")
    if ";" in body:
        raise NotASelect(
            f"two statements were given where one read was expected: {sql.strip()!r}. "
            "A collector that runs a second statement is a write path with a "
            "reassuring name."
        )
    if not _OPENS_A_READ.match(body):
        first = body.split(None, 1)[0]
        raise NotASelect(
            f"{first!r} is not a read, and this tool only reads. "
            "Evidence is collected from a live staging database; a statement that "
            "is not a SELECT changes the thing it was meant to measure."
        )
    return sql


def render(sql: str, parameters: Parameters) -> str:
    """Return ``sql`` with every parameter reference replaced by its value.

    One pass, so a value that itself contains a colon — every composed alert
    identifier does — cannot be rescanned and partly substituted a second time.
    """

    def replace(found: re.Match[str]) -> str:
        name = found.group(1)
        return f"'{parameters.get(name)}'"

    return PLACEHOLDER.sub(replace, sql)


def _slug(title: str) -> str:
    """Return a file-name fragment from a station's title."""
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-").split("-")
    return "-".join(word for word in words if word)[:48].rstrip("-")


def file_name_for(station: Station) -> str:
    """Return the file this station's evidence is written to.

    The station name leads, so a directory listing sorts into the order the
    loop passes through and a reader can match a number to the claim it was
    supposed to settle.
    """
    return f"{station.name}-{_slug(station.title)}.txt"


def _query_block(query: Query, parameters: Parameters, runner: Callable[[str], str]) -> str:
    """Return one query, its provenance, and whatever came back — or why not."""
    head = [f"## {query.name} — {query.asks}"]
    if query.baseline:
        head.append(f"## before the wave: {query.baseline}")

    absent = parameters.missing(query.needs)
    if absent:
        asked_for = ", ".join(f"--{name}" for name in absent)
        head.append(
            f"## {NOT_COLLECTED}: this query needs {asked_for}, which was not given. "
            "Nothing was asked of the database. A station without evidence is not a "
            "station that passed."
        )
        return "\n".join(head) + "\n"

    statement = render(only_select(query.sql), parameters).strip()
    try:
        answer = runner(statement)
    except Exception as failure:  # noqa: BLE001 — one bad query must not lose the rest
        return "\n".join(
            [*head, "", statement, "", REFUSAL_OPENS, f"{failure}", REFUSAL_CLOSES, ""]
        )
    return "\n".join([*head, "", statement, "", OUTPUT_OPENS, answer, OUTPUT_CLOSES, ""])


def _station_text(
    station: Station,
    parameters: Parameters,
    runner: Callable[[str], str],
    stamped: datetime,
) -> str:
    """Return the whole file for one station."""
    lines = [
        f"# {station.name} — {station.title}",
        f"# collected at {stamped.isoformat()}",
        f"# parameters: {parameters.described()}",
        "",
    ]
    for query in station.queries:
        lines.append(_query_block(query, parameters, runner))
        lines.append("")
    return "\n".join(lines)


def collect(
    *,
    parameters: Parameters,
    runner: Callable[[str], str],
    destination: Path,
    stations: Sequence[Station] = STATIONS,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[Path, ...]:
    """Write one evidence file per station and return what was written."""
    destination.mkdir(parents=True, exist_ok=True)
    stamped = now()
    written: list[Path] = []
    for station in stations:
        path = destination / file_name_for(station)
        path.write_text(_station_text(station, parameters, runner, stamped), encoding="utf-8")
        written.append(path)
    return tuple(written)


def plan(*, parameters: Parameters, stations: Sequence[Station] = STATIONS) -> str:
    """Return every question, fully substituted, without touching a database.

    What this is for: reading the SQL before it runs, and pasting it into a
    session somebody already has open. A dry read of the plan is also the
    cheapest way to notice that a query is measuring the wrong thing, which is
    the failure mode a collector cannot detect for itself.
    """
    lines: list[str] = []
    for station in stations:
        lines.append(f"-- {station.name} — {station.title}")
        for query in station.queries:
            lines.append(f"-- {query.name}: {query.asks}")
            if query.baseline:
                lines.append(f"-- before the wave: {query.baseline}")
            absent = parameters.missing(query.needs)
            if absent:
                asked_for = ", ".join(f"--{name}" for name in absent)
                lines.append(f"-- {NOT_COLLECTED}: needs {asked_for}")
                lines.append("")
                continue
            lines.append(render(only_select(query.sql), parameters).strip())
            lines.append("")
        lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ShellFreeRunner:
    """Run one read through a command that takes SQL on standard input.

    ``argv`` is split from a single string with :mod:`shlex` and handed to the
    process directly. No shell of this machine ever sees it, and the SQL travels
    on standard input rather than as an argument, so nothing that runs here is
    visible in a process listing.

    The command is expected to be something like a ``psql`` invocation, possibly
    wrapped in ``ssh`` and ``kubectl exec``. Whatever resolves the connection
    string does so at the far end; this side never holds one.
    """

    argv: tuple[str, ...]
    timeout_seconds: int = 60

    @classmethod
    def of_command(cls, command: str) -> ShellFreeRunner:
        """Return the runner one command line describes."""
        argv = tuple(shlex.split(command))
        if not argv:
            raise ValueError("--exec was empty; there is nothing to run the query with")
        return cls(argv=argv)

    def __call__(self, sql: str) -> str:
        """Return, verbatim, what the command printed for ``sql``."""
        finished = subprocess.run(  # noqa: S603 — argv is explicit and no shell is used
            list(self.argv),
            input=sql,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if finished.returncode != 0:
            raise RuntimeError(
                f"exit {finished.returncode}: {finished.stderr.strip() or 'no message'}"
            )
        return finished.stdout


__all__ = [
    "NOT_COLLECTED",
    "OUTPUT_CLOSES",
    "OUTPUT_OPENS",
    "REFUSAL_CLOSES",
    "REFUSAL_OPENS",
    "NotASelect",
    "Parameters",
    "ShellFreeRunner",
    "UnusableParameter",
    "collect",
    "file_name_for",
    "only_select",
    "plan",
    "render",
]
