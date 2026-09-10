"""Operational recovery quarantine and release compatibility."""

from pathlib import Path

from alembic import op

revision = "0005_increment6"
down_revision = "0004_increment5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Restore a separate database; do not erase operational evidence")
