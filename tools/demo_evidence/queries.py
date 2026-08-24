"""The questions the demonstration asks of a live database, one per station.

**The SQL is not in this file.** It lives beside it, in ``sql/``, one statement
per file named for the station and the question it settles. Two reasons, and the
second is the one that decided it.

A statement written as a Python string cannot be pasted into a session, cannot
be diffed without the quoting getting in the way, and has to be re-indented by
whoever reads it. As a file it is the thing itself.

And the repository forbids a SQL statement literal in any Python module outside
the storage tree — one datastore, reached through repository ports. That rule is
about product code and this is an instrument, but the check that enforces it
scans every module in the tree, and the right answer to a rule that catches you
is to satisfy it rather than to carve out an exception. Nothing here issues a
query: it reads a file and hands the text to a command somebody named.

Every statement is a ``SELECT``, every one is scoped to a single organisation,
and every one that claims something was recorded carries the value measured
**before** this work started. "Three tool calls" is a number; "nought to three,
for this run, read back after a reload" is a proof.

Two absences are deliberate.

**No column that could hold a secret is named anywhere.** Not the credential
store, not a token hash, not a stored passphrase. A collector that never asks
for one cannot print one into a file somebody commits.

**No vocabulary is spelled out in the SQL.** The audit resource kinds, the
approval state and the change kind arrive as parameters, resolved from the
modules that declare them, so a statement cannot go on asking about a word the
product stopped using.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from config.constants.security import (
    APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
    REMEDIATION_AUDIT_RESOURCE_KIND,
)
from platform.persistence.ports.approval_store import ApprovalState

#: Where the statements live, beside this module.
SQL_DIRECTORY: Final = Path(__file__).resolve().parent / "sql"

#: The change kind a remediation approval is stored under.
REMEDIATION_CHANGE_TYPE: Final = "remediation"

#: Words the product declares, substituted into the statements the same way an
#: identifier is. Read from the declaring modules rather than written down, so
#: a renamed audit kind or a renamed state breaks the query loudly instead of
#: making it quietly return nothing.
VOCABULARY: Final[dict[str, str]] = {
    "approval_audit_kind": APPROVAL_AUDIT_RESOURCE_KIND_REQUEST,
    "remediation_audit_kind": REMEDIATION_AUDIT_RESOURCE_KIND,
    "rejected_state": ApprovalState.REJECTED.value,
    "remediation_change_type": REMEDIATION_CHANGE_TYPE,
}


@dataclass(frozen=True, slots=True)
class Query:
    """One question, what it proves, and what the answer was before this work."""

    station: str
    name: str
    #: One sentence: what a reader should conclude from the answer.
    asks: str
    #: The parameters this query cannot run without.
    needs: tuple[str, ...]
    #: What this same query returned before the wave, when that is known.
    #: Empty when there is no earlier reading to contrast against.
    baseline: str = ""
    #: The statement, read from ``sql/<station>-<name>.sql`` at import.
    sql: str = field(default="", compare=False)

    @property
    def source(self) -> Path:
        """Return the file this query's statement is read from."""
        return SQL_DIRECTORY / f"{self.station}-{self.name}.sql"


def _query(
    station: str, name: str, *, asks: str, needs: tuple[str, ...], baseline: str = ""
) -> Query:
    """Return one query with its statement loaded from ``sql/``."""
    path = SQL_DIRECTORY / f"{station}-{name}.sql"
    return Query(
        station=station,
        name=name,
        asks=asks,
        needs=needs,
        baseline=baseline,
        sql=path.read_text(encoding="utf-8"),
    )


@dataclass(frozen=True, slots=True)
class Station:
    """One point of the loop, and the questions that decide whether it held."""

    name: str
    title: str
    queries: tuple[Query, ...]


E3 = Station(
    name="E3",
    title="the incident opens legible, over a subject the estate resolves",
    queries=(
        _query(
            "E3",
            "incident",
            asks="the incident exists, is addressable, and is named by a title rather than an id",
            needs=("org", "incident"),
            baseline="every alert incident's detail was unrecoverable",
        ),
        _query(
            "E3",
            "estate",
            asks="the estate holds real resources rather than being empty",
            needs=("org",),
            baseline="0 — the estate was empty and every incident showed an unplaced zone",
        ),
        _query(
            "E3",
            "subject",
            asks="the resource the incident points at is one the estate actually holds",
            needs=("org", "resource"),
            baseline="no row — nothing to point at",
        ),
    ),
)


E4 = Station(
    name="E4",
    title="the investigation records its turns, its calls, its evidence and its cost",
    queries=(
        _query(
            "E4",
            "turns",
            asks="the run recorded turns, read back from the store rather than the process",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
        ),
        _query(
            "E4",
            "tool-calls",
            asks="the run recorded the capability calls it made",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
        ),
        _query(
            "E4",
            "evidence",
            asks="the run recorded the observations it cited",
            needs=("org", "run"),
            baseline="0, across 37 completed runs",
        ),
        _query(
            "E4",
            "trace-events",
            asks="the run's own log exists beside the counts above",
            needs=("org", "run"),
            baseline="73 for the whole instance, across 37 completed runs",
        ),
        _query(
            "E4",
            "cost-per-turn",
            asks=(
                "cost is recorded turn by turn, and an unpriced turn is empty rather than nought"
            ),
            needs=("org", "run"),
            baseline="no turn was recorded at all, so no cost could be",
        ),
        _query(
            "E4",
            "what-each-call-returned",
            asks="each call carries what it returned, in the order it was recorded",
            needs=("org", "run"),
            baseline="no row",
        ),
    ),
)


E5 = Station(
    name="E5",
    title="the sentence naming the run is not the document",
    queries=(
        _query(
            "E5",
            "sentence-and-document",
            asks="the sentence does not open with markdown syntax, and the document still does",
            needs=("org", "run"),
            baseline="every recent summary opened with ###, and no separate sentence existed",
        ),
    ),
)


E7 = Station(
    name="E7",
    title="the proposal waits, with the plan that would undo it",
    queries=(
        _query(
            "E7",
            "proposal",
            asks=(
                "exactly one proposal exists for this run, and its state is still "
                f"{ApprovalState.PENDING.value!r} — the word the approvals port uses for a "
                "decision nobody has taken"
            ),
            needs=("org", "run"),
            baseline="no row, for any run",
        ),
        _query(
            "E7",
            "rollback-plan",
            asks="the undo was recorded, and it was recorded before anything ran",
            needs=("org", "approval"),
            baseline="no row",
        ),
        _query(
            "E7",
            "every-remediation-proposal",
            asks=(
                "how many remediation proposals this deployment has ever queued; nought here "
                "means nothing bound a control plane, which the process log says outright"
            ),
            needs=("org",),
            baseline="0 — no control plane was bound, so no write could be proposed",
        ),
    ),
)


E8 = Station(
    name="E8",
    title="the decision, its author and its instant, recorded before any effect",
    queries=(
        _query(
            "E8",
            "decision",
            asks="who decided, when, and why — on the row the execution was authorised from",
            needs=("org", "approval"),
            baseline="no row",
        ),
        _query(
            "E8",
            "audit-of-the-decision",
            asks="the decision reached the audit trail with author, action, subject and result",
            needs=("org", "approval"),
            baseline="no row",
        ),
        _query(
            "E8",
            "nothing-executed-unattended",
            asks=(
                "no action above reading executed without a recorded human decision; this must "
                "read nought at the end of the demonstration"
            ),
            needs=("org",),
            baseline="0 — nothing executed at all",
        ),
    ),
)


E9 = Station(
    name="E9",
    title="the execution went through the gate, and what it produced was recorded",
    queries=(
        _query(
            "E9",
            "outcome",
            asks=(
                "the execution produced a recorded outcome for this resource — a named failure "
                "is an outcome, a silent one is not"
            ),
            needs=("org", "resource"),
            baseline="no row",
        ),
        _query(
            "E9",
            "episode",
            asks="what a later investigation would be told about this one",
            needs=("org", "run"),
            baseline="no row for a run",
        ),
    ),
)


E10 = Station(
    name="E10",
    title="the incident reflects the outcome instead of stopping at the diagnosis",
    queries=(
        _query(
            "E10",
            "timeline",
            asks="the action left an entry on the incident's own timeline",
            needs=("org", "incident"),
            baseline="no entry for an action, because no action happened",
        ),
        _query(
            "E10",
            "incident-after",
            asks="the incident itself carries the outcome, the run and the action",
            needs=("org", "incident"),
            baseline="the incident stopped at the diagnosis",
        ),
    ),
)


R = Station(
    name="R",
    title="the refusal path, exercised on a different occurrence",
    queries=(
        _query(
            "R",
            "rejections",
            asks="a rejection was recorded with its reason, and a reason is not optional",
            needs=("org",),
            baseline="no row",
        ),
        _query(
            "R",
            "both-decisions-in-the-audit",
            asks=(
                "the approval and the rejection both appear, with author, action, subject "
                "and result"
            ),
            needs=("org",),
            baseline="no row",
        ),
    ),
)


#: Every station, in the order the loop passes through them. E1, E2 and E6 are
#: absent on purpose: what proves them is an alert router, an intake screen and
#: a transcript, none of which is a row in this database. Inventing a query for
#: them would be measuring the adjacent thing and calling it the answer.
STATIONS: Final[tuple[Station, ...]] = (E3, E4, E5, E7, E8, E9, E10, R)


__all__ = [
    "E3",
    "E4",
    "E5",
    "E7",
    "E8",
    "E9",
    "E10",
    "R",
    "REMEDIATION_CHANGE_TYPE",
    "SQL_DIRECTORY",
    "STATIONS",
    "VOCABULARY",
    "Query",
    "Station",
]
