"""What a sweep concluded beyond the counts, kept with the sweep.

One nullable JSONB column on ``estate_discovery_sweeps``. It holds what a
post-step produced — today the enrichment's divergence report: entries a
declared inventory names and the provider does not, resources the provider
reports and the inventory does not, and addresses no declared network covers.

It sits on the sweep rather than on the resources because the half of a
divergence that matters most is the entry that *has* no resource. A machine
somebody deleted last April is still in the file, and there is nowhere on a
resource to record something that is not one.

Nullable rather than defaulted to ``{}``. A sweep that ran before this column
existed concluded nothing extra, and an empty object would claim it had looked
and found nothing.

Revision: 0009_sweep_findings
Parent: 0008_remediation_ledger
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_sweep_findings"
down_revision = "0008_remediation_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the findings column."""
    op.add_column(
        "estate_discovery_sweeps",
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop it again."""
    op.drop_column("estate_discovery_sweeps", "findings")
