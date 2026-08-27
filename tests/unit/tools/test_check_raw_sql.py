"""The storage-boundary check, and the deliberate violation that proves it fires.

SC-004 asks for a fixture the check fails on. A check nobody has watched fail is
a check that might be scanning an empty list of roots, and the repository would
look exactly as clean either way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_raw_sql import (
    CYPHER_LITERAL_RULE,
    DRIVER_IMPORT_RULE,
    DRIVER_MODULES,
    QUERY_EXECUTION_RULE,
    SQL_LITERAL_RULE,
    classify,
    find_violations,
    is_allowed,
    is_driver,
    module_violations,
    scans_literals,
)

pytestmark = pytest.mark.unit

#: The fixture SC-004 asks for: a module doing the thing the boundary forbids,
#: in each of the ways it can be done.
VIOLATION_FIXTURE = '''
"""A stage that reached for the database. Every line here is a defect."""

from __future__ import annotations

import asyncpg
from sqlalchemy import text


async def recent_runs(connection: object) -> list[str]:
    """Return the run ids, straight from the table."""
    rows = await connection.fetchrow("SELECT run_id FROM agent_runs LIMIT 10")
    return [row[0] for row in rows]


async def blast_radius(connection: object, service: str) -> list[str]:
    """Ask the graph directly."""
    return await connection.execute(
        "MATCH (s:Service)<-[:DEPENDS_ON*1..3]-(d) WHERE s.name = $1 RETURN d"
    )
'''


def test_the_check_fails_on_a_deliberate_violation(tmp_path: Path) -> None:
    offender = tmp_path / "core" / "pipeline" / "shortcut.py"
    offender.parent.mkdir(parents=True)
    offender.write_text(VIOLATION_FIXTURE, encoding="utf-8")

    found = find_violations([tmp_path])
    rules = {violation.rule for violation in found}

    assert rules == {
        DRIVER_IMPORT_RULE,
        QUERY_EXECUTION_RULE,
        SQL_LITERAL_RULE,
        CYPHER_LITERAL_RULE,
    }


def test_the_same_module_inside_the_storage_tree_is_fine(tmp_path: Path) -> None:
    """The boundary is a location, not a taboo. Somebody has to write the SQL."""
    allowed = tmp_path / "platform" / "persistence" / "postgres" / "repositories.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text(VIOLATION_FIXTURE, encoding="utf-8")

    assert find_violations([tmp_path]) == []


@pytest.mark.parametrize(
    "path",
    [
        Path("platform/persistence/postgres/engine.py"),
        Path("platform/persistence/migrations/env.py"),
        Path("/srv/checkout/platform/persistence/fakes/gateway.py"),
    ],
)
def test_the_storage_tree_is_allowed_to_know_about_databases(path: Path) -> None:
    assert is_allowed(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("core/pipeline/diagnose.py"),
        Path("capabilities/tools/kubernetes.py"),
        Path("gateway/api/runs.py"),
        # Nearly right, and therefore worth pinning: a package called
        # `persistence` somewhere else is not the storage tree.
        Path("integrations/datadog/persistence/cache.py"),
    ],
)
def test_everywhere_else_is_not(path: Path) -> None:
    assert is_allowed(path) is False


@pytest.mark.parametrize("module", sorted(DRIVER_MODULES))
def test_every_listed_driver_is_recognised(module: str) -> None:
    assert is_driver(module) is True
    assert is_driver(f"{module}.ext.asyncio") is True


def test_a_driver_reached_through_importlib_is_still_a_driver(tmp_path: Path) -> None:
    # A contributor who cannot import asyncpg and reaches for importlib is
    # solving a problem, not evading a rule. The boundary is gone either way.
    offender = tmp_path / "core" / "sneaky.py"
    offender.parent.mkdir(parents=True)
    offender.write_text(
        "import importlib\n\ndriver = importlib.import_module('asyncpg')\n",
        encoding="utf-8",
    )

    assert [v.rule for v in find_violations([tmp_path])] == [DRIVER_IMPORT_RULE]


@pytest.mark.parametrize(
    "text",
    [
        "SELECT run_id FROM agent_runs",
        "insert into episodes (id) values ($1)",
        "UPDATE config_nodes SET values = $1",
        "DELETE FROM sessions WHERE updated_at < $1",
        "CREATE EXTENSION IF NOT EXISTS vector",
        "CREATE UNIQUE INDEX CONCURRENTLY ix_runs ON agent_runs (run_id)",
        "ALTER TABLE agent_runs ADD COLUMN model_id text",
        "DROP INDEX ix_runs",
        "TRUNCATE TABLE claims",
        "WITH recent AS (SELECT run_id FROM agent_runs) SELECT * FROM recent",
        # Leading whitespace, as a triple-quoted statement in real code has.
        "\n    SELECT run_id\n    FROM agent_runs\n    ",
        # A trailing semicolon is still a statement.
        "SELECT 1 FROM agent_runs;",
    ],
)
def test_sql_statements_are_recognised(text: str) -> None:
    assert classify(text) == SQL_LITERAL_RULE


@pytest.mark.parametrize(
    "text",
    [
        "MATCH (s:Service) RETURN s",
        "OPTIONAL MATCH (a)-[:DEPENDS_ON]->(b)",
        "MERGE (s:Service {name: $name})",
        "DETACH DELETE s",
    ],
)
def test_cypher_statements_are_recognised(text: str) -> None:
    assert classify(text) == CYPHER_LITERAL_RULE


@pytest.mark.parametrize(
    "text",
    [
        # Prose. The word is not the statement.
        "Select a provider from the registry.",
        "This update sets the stage.",
        "The catalogue has a MATCH scoring term.",
        "Return the nearest neighbours.",
        # An identifier that happens to read like one.
        "delete_before",
        "",
        # The one that started this rule: a sentence whose second word is a
        # table-shaped noun and whose fourth is "from".
        "Select the rows from the registry.",
    ],
)
def test_prose_is_left_alone(text: str) -> None:
    assert classify(text) is None


def test_a_docstring_explaining_the_rule_does_not_break_it(tmp_path: Path) -> None:
    # Otherwise no module could document what it forbids, starting with the
    # check itself.
    documented = tmp_path / "core" / "documented.py"
    documented.parent.mkdir(parents=True)
    documented.write_text(
        '"""Never write SELECT run_id FROM agent_runs here."""\n\n'
        "def helper() -> None:\n"
        '    """Not the place for MATCH (s:Service) RETURN s either."""\n',
        encoding="utf-8",
    )

    assert find_violations([tmp_path]) == []


@pytest.mark.parametrize(
    ("path", "applies"),
    [
        (Path("core/pipeline/diagnose.py"), True),
        (Path("tests/unit/core/llm/test_redaction.py"), False),
        (Path("/srv/checkout/tests/contract/persistence/conftest.py"), False),
    ],
)
def test_the_literal_rules_stop_at_the_test_suite(path: Path, applies: bool) -> None:
    assert scans_literals(path) is applies


def test_a_test_that_reaches_behind_the_ports_still_fails(tmp_path: Path) -> None:
    """The rules that matter do not stop at ``tests/``."""
    offender = tmp_path / "tests" / "unit" / "test_shortcut.py"
    offender.parent.mkdir(parents=True)
    offender.write_text(
        "import asyncpg\n\n\n"
        "async def test_it(connection: object) -> None:\n"
        '    await connection.execute("truncate table agent_runs")\n',
        encoding="utf-8",
    )

    rules = {violation.rule for violation in find_violations([tmp_path])}

    assert rules == {DRIVER_IMPORT_RULE, QUERY_EXECUTION_RULE}


def test_a_sandbox_executing_a_command_is_not_a_query(tmp_path: Path) -> None:
    """``execute`` is a verb two boundaries want, and only one of them is storage.

    The ``Sandbox`` port runs a capability's command; a cursor runs a statement.
    Exempting the receiver keeps the rule intact for the second — the assertions
    below are as much about what still fails as about what no longer does.
    """
    module = tmp_path / "core" / "runner.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "async def run(sandbox: object, connection: object, request: object) -> None:\n"
        "    await sandbox.execute(request)\n"
        "    await connection.execute(request)\n",
        encoding="utf-8",
    )

    violations = find_violations([tmp_path])

    assert len(violations) == 1
    assert violations[0].line == 3


def test_an_unqualified_execute_is_never_exempt(tmp_path: Path) -> None:
    """A bare call has no receiver to vouch for it, so it is still a violation."""
    module = tmp_path / "core" / "runner.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def run(execute: object) -> None:\n    execute('anything')\n", encoding="utf-8"
    )

    assert [violation.rule for violation in find_violations([tmp_path])] == [QUERY_EXECUTION_RULE]


@pytest.mark.sweep
def test_the_repository_writes_no_query_outside_the_storage_tree() -> None:
    """The check, run over the repository it guards."""
    assert find_violations([Path(__file__).resolve().parents[3]]) == []


def test_an_unparseable_module_is_reported_rather_than_skipped(tmp_path: Path) -> None:
    # Silently skipping a file the parser choked on is how a check comes to
    # cover less than it claims.
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")

    with pytest.raises(ValueError, match="could not be parsed"):
        module_violations(broken, broken.read_text(encoding="utf-8"))


class TestVendorQueryLanguages:
    """A vendor whose API *is* SQL is not this repository's datastore.

    ClickHouse, Snowflake, and OpenObserve take a statement as their request
    payload over HTTP. There is no repository port for a client to bypass — the
    data is not ours — and the two rules that actually hold the boundary still
    apply: a module under ``integrations/`` still cannot import a driver or call
    ``execute``.
    """

    def test_a_vendor_client_may_carry_the_statement_its_api_takes(self, tmp_path: Path) -> None:
        path = tmp_path / "integrations" / "clickhouse" / "client.py"
        path.parent.mkdir(parents=True)
        path.write_text('QUERY = "SELECT query_id FROM system.processes"\n', encoding="utf-8")

        assert not module_violations(path, path.read_text(encoding="utf-8"))

    def test_a_driver_import_under_integrations_still_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "integrations" / "clickhouse" / "client.py"
        path.parent.mkdir(parents=True)
        path.write_text("import asyncpg\n", encoding="utf-8")

        assert [
            found.rule for found in module_violations(path, path.read_text(encoding="utf-8"))
        ] == [DRIVER_IMPORT_RULE]

    def test_calling_execute_under_integrations_still_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "integrations" / "clickhouse" / "client.py"
        path.parent.mkdir(parents=True)
        path.write_text("connection.execute(statement)\n", encoding="utf-8")

        assert [
            found.rule for found in module_violations(path, path.read_text(encoding="utf-8"))
        ] == [QUERY_EXECUTION_RULE]

    def test_a_statement_outside_both_trees_still_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "core" / "pipeline" / "stage.py"
        path.parent.mkdir(parents=True)
        path.write_text('QUERY = "SELECT id FROM investigations"\n', encoding="utf-8")

        assert [
            found.rule for found in module_violations(path, path.read_text(encoding="utf-8"))
        ] == [SQL_LITERAL_RULE]
