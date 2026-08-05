"""${message}

Revision: ${up_revision}
Parent: ${down_revision | comma,n}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the change."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Undo the change.

    Every migration has one, and it is tested. A schema change that cannot be
    rolled back turns a bad release into an outage with no way back.
    """
    ${downgrades if downgrades else "pass"}
