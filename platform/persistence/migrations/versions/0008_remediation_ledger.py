"""Record what each remediation did, and whether it worked.

Two tables: the outcome of one action, and the patterns the outcomes raise.

The load-bearing index is ``ix_remediation_due``, and it is partial. The
verification sweep asks "what is owed now" every thirty seconds; a total index
would make that a walk over every remediation the deployment has ever
performed. Restricted to the rows still owed it is a lookup over a handful,
however much history accumulates.

``ix_remediation_history`` carries the three dimensions effectiveness is sliced
by — resource, capability, condition — in the order a query narrows, with the
instant last so a windowed count is a range scan on the tail of the index rather
than a filter after it.

``ix_remediation_age`` is on ``executed_at`` alone and not tenant-scoped,
because retention sweeps the whole deployment at once — the same reasoning the
incidents' and the estate's history indexes carry.

The verdict is a string rather than an enum type. Adding a member to a
PostgreSQL enum is a migration in every deployment; the closed set is enforced
where it is read, and ``VerificationVerdict`` is the one place that says what
the five are.

Revision: 0008_remediation_ledger
Parent: 0007_incidents
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_remediation_ledger"
down_revision = "0007_incidents"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``VerificationState``,
#: ``VerificationVerdict`` and ``RollbackDisposition``, with room to spare.
_STATE_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "remediation_outcomes",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("action_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("capability", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("condition_key", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("incident_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("run_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("plan_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settle_seconds", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("verdict", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("signal_names", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("before_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("rollback", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("rollback_detail", sa.Text(), nullable=False),
        sa.Column("autonomous", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_holder", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("org_id", "action_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    # Partial: the sweep only ever asks about obligations that are still owed.
    op.create_index(
        "ix_remediation_due",
        "remediation_outcomes",
        ["org_id", "due_at"],
        postgresql_where=sa.text("state <> 'verified'"),
    )
    op.create_index(
        "ix_remediation_history",
        "remediation_outcomes",
        ["org_id", "resource_id", "capability", "condition_key", "executed_at"],
    )
    op.create_index("ix_remediation_age", "remediation_outcomes", ["executed_at"])

    op.create_table(
        "remediation_problems",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("problem_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("pattern_key", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("capability", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("title", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("action_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("incident_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("suppresses_autonomy", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=False),
        sa.Column("closed_by", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "problem_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_remediation_live_pattern",
        "remediation_problems",
        ["org_id", "pattern_key"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_remediation_problems_raised",
        "remediation_problems",
        ["org_id", "raised_at"],
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("remediation_problems")
    op.drop_table("remediation_outcomes")
