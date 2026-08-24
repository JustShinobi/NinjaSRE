"""The evidence collector, and the properties that stop it corrupting the proof.

This tool exists because somebody, at eleven at night, will otherwise type a
``SELECT`` from memory and paste the result under the wrong heading. Four
properties keep it honest, and each is checked here rather than reviewed:

- it reads and only reads — anything that is not a single ``SELECT`` is refused
  loudly, so the collector cannot become a write path into a live database;
- every question it asks is scoped to one organisation, so a count from a
  neighbouring tenant can never be presented as this deployment's;
- what it writes is the query **and the literal output**, byte for byte, never
  a re-rendering of it, because a claim about output is not output;
- the file name says which station the evidence belongs to, so a reader who was
  not in the room can match a number to the thing it was supposed to prove.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.demo_evidence import (
    STATIONS,
    NotASelect,
    Parameters,
    UnusableParameter,
    collect,
    only_select,
    plan,
    render,
)

pytestmark = pytest.mark.unit

FIXED = datetime(2026, 8, 24, 21, 3, 41, tzinfo=UTC)

#: A real ``psql`` answer, trailing blank line and all. Kept verbatim so the
#: literalness check has something with whitespace worth preserving.
PSQL_ANSWER = " count \n-------\n     5\n(1 row)\n\n"


def _clock() -> datetime:
    """Return the one instant every file in a test collection is stamped with."""
    return FIXED


def _answers(_: str) -> str:
    """Return the same recorded answer for whatever is asked."""
    return PSQL_ANSWER


def _refuses(_: str) -> str:
    """Fail the way a database that is unreachable fails."""
    raise ConnectionError("could not connect to server: Connection refused")


def _full() -> Parameters:
    """Return every parameter filled, as the whole loop's collection has them."""
    return Parameters(
        org="org-staging",
        run="run-0007",
        incident="inc_a1b2c3d4e5f60718",
        approval="apr-0001",
        resource="proxmox:lxc:122",
    )


# --- It reads, and only reads -------------------------------------------------


def test_every_declared_query_is_a_select() -> None:
    """No station asks the database to change anything."""
    for station in STATIONS:
        for query in station.queries:
            assert only_select(query.sql) is not None, f"{station.name}/{query.name}"


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM approvals WHERE org_id = 'x'",
        "UPDATE incidents SET state = 'closed'",
        "INSERT INTO evidence (run_id) VALUES ('x')",
        "DROP TABLE run_turns",
        "TRUNCATE tool_calls",
        "WITH x AS (DELETE FROM approvals RETURNING *) SELECT * FROM x",
    ],
)
def test_a_statement_that_is_not_a_select_is_refused(statement: str) -> None:
    """The guard that stops an evidence collector becoming a write path."""
    with pytest.raises(NotASelect) as refusal:
        only_select(statement)
    assert statement.split()[0].lower() in str(refusal.value).lower()


def test_a_select_carrying_a_second_statement_is_refused() -> None:
    """One statement per query: a trailing semicolon may not hide a second one."""
    with pytest.raises(NotASelect):
        only_select("SELECT 1; DROP TABLE run_turns")


def test_a_trailing_semicolon_alone_is_allowed() -> None:
    """The ordinary way anyone writes SQL is not an error."""
    assert only_select("SELECT 1;")


# --- Every question is scoped to one organisation -----------------------------


def test_every_declared_query_is_scoped_to_one_organisation() -> None:
    """A count from a neighbouring tenant is never this deployment's evidence."""
    for station in STATIONS:
        for query in station.queries:
            assert ":org" in query.sql, f"{station.name}/{query.name} is not org-scoped"


def test_the_rendered_query_carries_the_organisation_it_was_given() -> None:
    """Substitution reaches the SQL that actually runs, not only the template."""
    rendered = render("SELECT count(*) FROM run_turns WHERE org_id = :org", _full())
    assert "'org-staging'" in rendered
    assert ":org" not in rendered


def test_a_cast_is_not_mistaken_for_a_parameter() -> None:
    """``detail::text`` is a cast; a parameter is a single colon."""
    rendered = render("SELECT detail::text FROM audit_events WHERE org_id = :org", _full())
    assert "detail::text" in rendered


def test_a_placeholder_nothing_supplies_is_refused_by_name() -> None:
    """A typo in a template fails loudly rather than querying nothing."""
    with pytest.raises(UnusableParameter) as refusal:
        render("SELECT 1 FROM x WHERE org_id = :orgg", _full())
    assert "orgg" in str(refusal.value)


@pytest.mark.parametrize(
    "hostile",
    ["x' OR 1=1 --", "a b", "x;DROP TABLE y", 'x"y', "x\nY"],
)
def test_an_identifier_that_could_end_the_literal_is_refused(hostile: str) -> None:
    """Values are identifiers, not prose: anything that could close a quote is out."""
    with pytest.raises(UnusableParameter):
        Parameters(org=hostile)


def test_the_identifiers_staging_really_uses_are_accepted() -> None:
    """The shapes this deployment writes: a public address and a composed alert id."""
    accepted = Parameters(
        org="org-staging",
        incident="alert:alertmanager:9f8e7d6c@2026-08-23T21:03:41+00:00",
        resource="proxmox:lxc:122",
    )
    assert accepted.incident.startswith("alert:")


# --- No query can read a credential ------------------------------------------


def test_no_query_reads_a_column_that_could_hold_a_secret() -> None:
    """A column that could carry a credential is in no query, so none can leak."""
    forbidden = (
        "credentials",
        "api_tokens",
        "token_hash",
        "local_password_hash",
        "password",
        "secret",
        "private_key",
    )
    for station in STATIONS:
        for query in station.queries:
            lowered = query.sql.lower()
            for name in forbidden:
                assert name not in lowered, f"{station.name}/{query.name} names {name}"


def test_the_command_that_reached_the_database_is_not_written_into_the_evidence(
    tmp_path: Path,
) -> None:
    """A connection string is not a fact about the loop, and it is not recorded."""
    written = collect(
        parameters=_full(),
        runner=_answers,
        destination=tmp_path,
        now=_clock,
    )
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "postgresql://" not in text
        assert "NINJASRE_DATABASE_URL" not in text


# --- What it writes is the query and the literal output -----------------------


def test_the_file_name_identifies_the_station(tmp_path: Path) -> None:
    """A reader matches a number to the thing it was supposed to prove."""
    written = collect(parameters=_full(), runner=_answers, destination=tmp_path, now=_clock)
    names = {path.name for path in written}
    for station in STATIONS:
        assert any(name.startswith(f"{station.name}-") for name in names), station.name


def test_the_file_holds_the_query_and_the_output_byte_for_byte(tmp_path: Path) -> None:
    """A claim about output is not output: what came back is what is written."""
    written = collect(parameters=_full(), runner=_answers, destination=tmp_path, now=_clock)
    body = written[0].read_text(encoding="utf-8")
    assert PSQL_ANSWER in body
    first = STATIONS[0].queries[0]
    assert render(first.sql, _full()) in body


def test_each_file_carries_the_instant_it_was_collected(tmp_path: Path) -> None:
    """The order of the loop is auditable only if each reading is stamped."""
    written = collect(parameters=_full(), runner=_answers, destination=tmp_path, now=_clock)
    assert FIXED.isoformat() in written[0].read_text(encoding="utf-8")


def test_a_recording_claim_carries_the_value_from_before_the_wave(tmp_path: Path) -> None:
    """Three tool calls is a number; nought to three is a proof."""
    written = collect(parameters=_full(), runner=_answers, destination=tmp_path, now=_clock)
    recorded = {path.name.split("-")[0]: path for path in written}
    body = recorded["E4"].read_text(encoding="utf-8")
    assert "before the wave" in body
    assert "0" in body


# --- A station without its parameters says so ---------------------------------


def test_a_query_missing_its_parameter_is_written_as_not_collected(
    tmp_path: Path,
) -> None:
    """A station with no evidence is not a station that passed."""
    asked: list[str] = []

    def counting(sql: str) -> str:
        asked.append(sql)
        return PSQL_ANSWER

    written = collect(
        parameters=Parameters(org="org-staging", run="run-0007"),
        runner=counting,
        destination=tmp_path,
        now=_clock,
    )
    bodies = "\n".join(path.read_text(encoding="utf-8") for path in written)
    assert "NOT COLLECTED" in bodies
    assert "--approval" in bodies
    assert all("approvals" not in sql or ":approval" not in sql for sql in asked)


def test_a_query_the_database_refused_is_recorded_as_refused(tmp_path: Path) -> None:
    """One unreachable query does not silently become an empty result."""
    written = collect(parameters=_full(), runner=_refuses, destination=tmp_path, now=_clock)
    body = written[0].read_text(encoding="utf-8")
    assert "could not run this query" in body
    assert "Connection refused" in body


# --- Planning needs no database ----------------------------------------------


def test_planning_asks_nothing_of_any_database() -> None:
    """The SQL can be read, and pasted, without a connection existing."""
    text = plan(parameters=_full())
    for station in STATIONS:
        assert station.name in text
    assert "'org-staging'" in text
