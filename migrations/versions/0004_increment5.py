"""Durable monotonic observed time; reconciliation may precede a draft."""

from pathlib import Path

from alembic import op

revision = "0004_increment5"
down_revision = "0003_increment4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Evidence-preserving migration; restore a separate database")
