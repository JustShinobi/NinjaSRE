"""The database's own refusal to let an audit record change.

The application layer already has no way to update or delete one: the port has
no such method, neither backend implements one, and a startup guard fails the
process if either grows one. This module is the layer beneath that, and it
exists because the layers above it are code — code gets refactored, an ORM will
happily issue whatever statement somebody builds, and a superuser with a psql
prompt is not bound by any of it.

A trigger is bound by all of it. After this migration runs, an ``UPDATE`` or a
``DELETE`` against ``audit_events`` raises inside the database, whoever issued
it and however. That is the difference between an audit log and evidence.

The names are constants rather than literals because the security suite asserts
they are the ones the migration created, and a rename that only happened in one
of the two places would leave the assertion passing against a trigger that no
longer exists.
"""

from __future__ import annotations

from typing import Final

from config.constants.security import (
    AUDIT_IMMUTABILITY_FUNCTION_NAME,
    AUDIT_IMMUTABILITY_TRIGGER_NAME,
)

#: The table the guard protects. Not derived from the ORM model, because a
#: migration must keep saying what it said on the day it ran.
AUDIT_TABLE_NAME: Final = "audit_events"

#: Creates the refusal, one statement per element.
#:
#: **Separate statements, deliberately.** asyncpg runs everything through a
#: prepared statement and PostgreSQL will not prepare two commands at once, so a
#: single string holding both of these fails at migration time — and fails in
#: the least helpful way, because the aborted transaction swallows the original
#: error behind the migration runner's own cleanup.
#:
#: ``BEFORE`` rather than ``AFTER`` so the statement never reaches the heap, and
#: ``FOR EACH STATEMENT`` so a mutation that would have matched no rows is
#: refused too — an operator learning that their delete was rejected only when
#: it happened to match something is an operator who believes audit rows are
#: deletable.
AUDIT_APPEND_ONLY_STATEMENTS: Final[tuple[str, ...]] = (
    f"""
    CREATE OR REPLACE FUNCTION {AUDIT_IMMUTABILITY_FUNCTION_NAME}() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION
            'audit_events is append-only, % is refused'
            , TG_OP
            USING ERRCODE = 'restrict_violation';
    END;
    $$ LANGUAGE plpgsql
    """,
    f"""
    CREATE TRIGGER {AUDIT_IMMUTABILITY_TRIGGER_NAME}
    BEFORE UPDATE OR DELETE OR TRUNCATE ON {AUDIT_TABLE_NAME}
    FOR EACH STATEMENT EXECUTE FUNCTION {AUDIT_IMMUTABILITY_FUNCTION_NAME}()
    """,
)

#: Undoes it. Present because a migration that cannot be reversed is one nobody
#: dares run, and absent from every other code path on purpose.
AUDIT_APPEND_ONLY_DROP_STATEMENTS: Final[tuple[str, ...]] = (
    f"DROP TRIGGER IF EXISTS {AUDIT_IMMUTABILITY_TRIGGER_NAME} ON {AUDIT_TABLE_NAME}",
    f"DROP FUNCTION IF EXISTS {AUDIT_IMMUTABILITY_FUNCTION_NAME}()",
)

#: The same thing as one readable block. For reading and for asserting against;
#: never for executing, for the reason above.
AUDIT_APPEND_ONLY_DDL: Final = ";\n".join(AUDIT_APPEND_ONLY_STATEMENTS)
AUDIT_APPEND_ONLY_DROP_DDL: Final = ";\n".join(AUDIT_APPEND_ONLY_DROP_STATEMENTS)


__all__ = [
    "AUDIT_APPEND_ONLY_DDL",
    "AUDIT_APPEND_ONLY_DROP_DDL",
    "AUDIT_APPEND_ONLY_DROP_STATEMENTS",
    "AUDIT_APPEND_ONLY_STATEMENTS",
    "AUDIT_TABLE_NAME",
]
